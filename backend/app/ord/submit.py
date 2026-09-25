"""Фаза 2: отправка в ОРД. Единственное место, где мы что-то создаём в чужой системе.

ВСЁ ЗДЕСЬ ПОСТРОЕНО ВОКРУГ ОДНОГО ФАКТА: запись в ЕРИР необратима. Маркер, ушедший в
реестр, не отзывается нажатием «отмена». Отсюда три правила, и каждое стоит своей строки
кода:

1. **Строка журнала пишется и КОММИТИТСЯ до HTTP-запроса.** Если ответ потеряется по
   таймауту, у нас не будет ни идентификатора, ни знания о том, создалась запись или
   нет, — но будет след, что попытка была. Без него повтор «на всякий случай» даёт
   в ЕРИР дубль.

2. **Сетевой обрыв — это НЕ неудача.** Отказ ОРД означает «не создалось»; обрыв связи
   означает «неизвестно». Поэтому при обрыве `finished_at` остаётся пустым, и такая
   попытка блокирует повтор до тех пор, пока человек не сверится с кабинетом. Записать
   её как ошибку значило бы разрешить повтор там, где запись могла уже создаться.
   Наша собственная ошибка внутри отправки блокирует повтор так же — неизвестность
   та же самая, — но НАЗЫВАЕТСЯ иначе (`_break_label`): человеку, который пойдёт
   сверяться, важно знать, чинить сеть или нас.

3. **Проверки идут ДО журнала и до запроса.** Не хватает `clientId`, договор уже
   зарегистрирован, контур боевой без явного разрешения — всё это отказ на входе,
   без единой строки в журнале и без обращения к ОРД.
"""
import os
from datetime import datetime
from types import SimpleNamespace
from typing import Optional

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Contract, Counterparty
from app.ord import client, payloads, registry
from app.ord.models import OrdInitialFinalLink, OrdSubmission


class OrdSubmitRefused(RuntimeError):
    """Отправка не начата: не выполнены условия. До ОРД запрос не дошёл."""


def _assert_write_allowed() -> str:
    """Запись на боевом контуре — только с явного разрешения.

    Читать прод безопасно, писать — необратимо. Один и тот же `ORD_ENV=prod` разрешал
    бы и то, и другое, а «мы же только посмотреть» однажды становится отправкой.
    Поэтому боевая запись требует отдельной переменной, которую невозможно выставить
    случайно, — и сообщение прямо называет, что именно она разрешает.
    """
    env = client.env()
    if env == 'prod' and (os.getenv("ORD_ALLOW_PROD_WRITE") or "").strip() != "1":
        raise OrdSubmitRefused(
            "Контур боевой, а запись в ЕРИР необратима. Чтобы отправлять на прод, "
            "нужна переменная ORD_ALLOW_PROD_WRITE=1 — отдельно от ORD_ENV, чтобы "
            "«читаем на проде» не могло стать отправкой по невнимательности.")
    return env


def pending(db: Session, kind: str, local_id: int, env: str) -> Optional[OrdSubmission]:
    """Незавершённая попытка по этой записи, если есть."""
    return (db.query(OrdSubmission)
              .filter(OrdSubmission.kind == kind,
                      OrdSubmission.local_id == local_id,
                      OrdSubmission.env == env,
                      OrdSubmission.finished_at.is_(None))
              .order_by(OrdSubmission.started_at.desc()).first())


def _assert_no_pending(db: Session, kind: str, local_id: int, env: str) -> None:
    stuck = pending(db, kind, local_id, env)
    if stuck is not None:
        when = stuck.started_at.strftime('%d.%m.%Y %H:%M') if stuck.started_at else '—'
        raise OrdSubmitRefused(
            f"Предыдущая отправка от {when} не завершилась: ответ ОРД не получен, и "
            f"создалась запись или нет — неизвестно. Проверьте договор в кабинете "
            f"({env}) прежде чем повторять, иначе в ЕРИР появится дубль.")


def _start(db: Session, kind: str, local_id: int, env: str, body: dict,
           user) -> OrdSubmission:
    """Завести строку журнала и ЗАФИКСИРОВАТЬ её до запроса.

    Вторым замком — уникальный индекс `uq_ord_submissions_pending` (миграция
    2026-09-11): проверка `_assert_no_pending` выше от ОДНОВРЕМЕННОСТИ не спасает, между
    ней и этой записью блокировки нет, и два нажатия проходили её оба. Отказ базы ловим
    здесь и превращаем в тот же понятный текст, а не в 500: для человека это один и тот
    же случай — «уже отправляется, подождите», — и он не должен зависеть от того,
    выиграл его запрос гонку или нет.
    """
    row = OrdSubmission(kind=kind, local_id=local_id, env=env, request=body,
                        started_at=datetime.utcnow(),
                        user_id=getattr(user, 'id', None))
    db.add(row)
    try:
        db.commit()      # именно здесь: след обязан пережить падение процесса
    except IntegrityError:
        db.rollback()
        raise OrdSubmitRefused(
            "По этому объекту прямо сейчас идёт другая отправка. Дождитесь её "
            "завершения: две отправки подряд создали бы в ЕРИР дубль, который не "
            "отозвать.")
    return row


def _finish(db: Session, row: OrdSubmission, *, http_status=None, ord_id=None,
            ord_status=None, error=None) -> None:
    row.finished_at = datetime.utcnow()
    row.http_status = http_status
    row.ord_id = ord_id
    row.ord_status = ord_status
    row.error = error
    db.commit()


def _break_label(e: Exception) -> str:
    """Чем кончилась попытка, у которой нет ответа ОРД.

    Блокировка повтора остаётся в обоих случаях: неизвестность одинаковая — запрос мог
    уйти и создать запись в ЕРИР. Различается ТЕКСТ, и различается не ради красоты.
    Раньше `except Exception` подписывал любую ошибку как обрыв связи, и падение нашего
    же кода читалось как проблема у провайдера: человек шёл сверяться с кабинетом и
    искать сеть там, где чинить надо нас. Найдено 27.08.2026 на заливке демо —
    `TypeError` в нашем коде лежал в журнале с подписью «связь оборвалась».

    `httpx.RequestError` — это ровно «запрос не удалось довести»: таймаут, обрыв, отказ
    в соединении. Ответ со статусом 4xx/5xx сюда не попадает, он разбирается раньше и
    означает «не создалось».
    """
    if isinstance(e, httpx.RequestError):
        return f"связь оборвалась: {type(e).__name__}: {e}"
    return f"сбой отправки на нашей стороне: {type(e).__name__}: {e}"


def _no_id(db: Session, row: OrdSubmission, status, what: str) -> None:
    """Успех без идентификатора: попытка остаётся ОТКРЫТОЙ, повтор заперт.

    До 23.09.2026 такой ответ закрывал попытку (аудит, 4.L7), и повтор был разрешён —
    хотя запись в ЕРИР могла создаться. Это та же неизвестность, что у обрыва связи, и
    выход из неё тот же: человек сверяется с кабинетом и закрывает попытку руками.
    """
    row.http_status = status
    row.error = "ответ ОРД без идентификатора — исход неизвестен"
    db.commit()
    raise OrdSubmitRefused(
        f"ОРД ответил успехом, но не вернул идентификатор {what} — запись могла "
        f"создаться. Сверьтесь с кабинетом; повтор заперт до сверки.")


def register_final_contract(db: Session, contract: Contract, user) -> dict:
    """Зарегистрировать доходный договор в ОРД и запомнить выданный идентификатор.

    Возвращает `{ord_id, status, env}`. Регистрация асинхронная: ОРД сразу отдаёт id и
    статус `Created`, а `Active` появляется позже — статус обновляется отдельно,
    `refresh_final_status`.
    """
    env = _assert_write_allowed()

    # Повтор запрещён НА ЭТОМ КОНТУРЕ, а не вообще. Раньше проверялась заполненность
    # колонки, и договор с боевым идентификатором нельзя было завести на демо вовсе —
    # то есть песочница была недоступна ровно для тех записей, ради которых нужна.
    already = registry.known_id(db, 'final_contract', contract.id, env,
                                contract.ord_contract_id, contract.ord_env)
    if already:
        raise OrdSubmitRefused(
            f"Договор уже зарегистрирован на контуре {env}: {already}. "
            f"Повторная регистрация создала бы там второй такой же.")

    payer = (db.query(Counterparty)
               .filter(Counterparty.id == contract.counterparty_id).first())
    if payer is None:
        raise OrdSubmitRefused("У договора не указан контрагент — регистрировать не с кем")

    # Идентификатор юрлица свой у каждого контура: ищем его для ТОГО, куда отправляем.
    # Нет его на этом контуре — по умолчанию находим юрлицо в ОРД по ИНН или заводим, как
    # регистрация изначального (владелец, 24.09.2026). До этого был отказ «сначала сверка
    # юрлиц», и договор с новым клиентом не регистрировался вовсе; а идентификатор с
    # другого контура давал отказ даже после пробы в песочнице (ревью 24.09.2026).
    # Поиск перед заведением и отказ на настоящей неоднозначности — в `ensure_client`.
    client_id = registry.known_id(db, 'client', registry.client_key(payer.inn), env,
                                  payer.ord_client_id, payer.ord_env)
    if not client_id:
        client_id = ensure_client(db, payer.inn, payer.name, user)
        # В колонку — только свой контур: демо-прогон не затирает боевой идентификатор.
        # Чужой остаётся в журнале попыток, откуда его достаёт `registry.known_id`.
        if registry.own_contour(payer.ord_client_id, payer.ord_env, env):
            payer.ord_client_id = client_id
            payer.ord_env = env
            payer.ord_synced_at = datetime.utcnow()
        db.commit()

    body = payloads.final_contract(contract, client_id)

    _assert_no_pending(db, 'final_contract', contract.id, env)
    row = _start(db, 'final_contract', contract.id, env, body, user)

    try:
        status, answer = client.post('/webapi/v3/contracts/final', body)
    except client.OrdError as e:
        # Отказ — это ответ: запись НЕ создалась, попытка закрыта, повтор разрешён.
        _finish(db, row, http_status=e.status, error=e.message)
        raise
    except Exception as e:
        # Обрыв связи. finished_at НЕ ставим: неизвестно, создалось ли. Пусть эта
        # попытка блокирует повтор, пока человек не посмотрит в кабинет.
        row.error = _break_label(e)
        db.commit()
        raise

    answer = answer or {}
    ord_id = answer.get('id')
    ord_status = answer.get('status')
    if not ord_id:
        _no_id(db, row, status, "договора")
    _finish(db, row, http_status=status, ord_id=ord_id, ord_status=ord_status)

    # В колонку пишем ТОЛЬКО свой контур. Демовский идентификатор поверх боевого стёр
    # бы настоящую связь с ЕРИР ради песочницы; он остаётся в журнале отправок, откуда
    # его и достаёт `registry.known_id`.
    if registry.own_contour(contract.ord_contract_id, contract.ord_env, env):
        contract.ord_contract_id = ord_id
        contract.ord_kind = 'final'
        contract.ord_status = ord_status
        contract.ord_env = env
        contract.ord_synced_at = datetime.utcnow()
    db.commit()
    return {'ord_id': ord_id, 'status': ord_status, 'env': env}


def refresh_final_status(db: Session, contract: Contract) -> dict:
    """Обновить статус зарегистрированного договора. Только чтение.

    Регистрация асинхронная: `Created` → `Registering` → `Active`, либо
    `RegistrationError`. Пока не `Active`, ЕРИД по договору не выпустить.
    """
    if not contract.ord_contract_id:
        raise OrdSubmitRefused("Договор ещё не зарегистрирован в ОРД")
    found = client.get('/webapi/v3/contracts/final',
                       {'FinalContractId': contract.ord_contract_id}) or []
    if not isinstance(found, list):
        found = [found]
    if not found:
        return {'status': contract.ord_status, 'found': False}
    item = found[0]
    contract.ord_status = item.get('status')
    contract.ord_synced_at = datetime.utcnow()
    db.commit()
    return {'status': contract.ord_status, 'found': True,
            'error_text': item.get('erirValidationError')}


# ── Фаза 3: изначальный договор ──────────────────────────────────────────────
#
# Стороны изначального договора хранятся у нас АТРИБУТАМИ (ИНН и название), а не
# ссылками: 87 из 91 рекламодателя нам не контрагенты, счетов мы им не выставляем.
# А API требует `clientId` и `contractorId` — идентификаторы юрлиц В ОРД. Значит перед
# регистрацией договора обе стороны должны существовать в кабинете, и `ensure_client`
# либо находит их по ИНН, либо заводит. Заведение юрлица — тоже запись, и идёт через
# тот же журнал: своя строка, свой контур, тот же запрет повтора.


def ensure_client(db: Session, inn: str, name: str, user,
                  legal_form: Optional[str] = None) -> str:
    """Найти юрлицо в ОРД по ИНН или завести. Возвращает идентификатор ОРД.

    Поиск ПЕРЕД заведением обязателен: `POST /clients` на существующий ИНН в лучшем
    случае откажет, в худшем заведёт двойника, а разбирать двойников юрлиц в ЕРИР
    некому. Найдено несколько — отказ: выбирать наугад нельзя, «OKKAM» в ОРД это три
    разных юрлица.
    """
    env = _assert_write_allowed()
    digits = ''.join(ch for ch in (inn or '') if ch.isdigit())
    if not digits:
        raise OrdSubmitRefused(f"«{name}»: без ИНН юрлицо в ОРД не найти и не завести")

    found = client.get('/webapi/v3/clients', {'Inn': digits}) or []
    if not isinstance(found, list):
        found = [found]
    found = registry.pick_client(found)      # CL из двух ролей юрлица — не двойник
    if len(found) == 1:
        return found[0].get('id')
    if len(found) > 1:
        raise OrdSubmitRefused(
            f"По ИНН {digits} в ОРД несколько юрлиц ({len(found)}). Выберите нужное "
            f"в кабинете и проставьте идентификатор — угадывать нельзя.")

    body = payloads.client(SimpleNamespace(inn=digits, name=name))
    if legal_form:
        body['legalForm'] = legal_form

    # Ключ попытки — сам ИНН числом: у юрлица нет нашей строки, к которой привязаться,
    # а защищать от дубля надо так же, как договор.
    local_id = int(digits[:9])
    _assert_no_pending(db, 'client', local_id, env)
    row = _start(db, 'client', local_id, env, body, user)
    try:
        status, answer = client.post('/webapi/v3/clients', body)
    except client.OrdError as e:
        _finish(db, row, http_status=e.status, error=e.message)
        raise
    except Exception as e:
        row.error = _break_label(e)
        db.commit()
        raise
    answer = answer or {}
    if not answer.get('id'):
        _no_id(db, row, status, f"юрлица «{name}»")
    _finish(db, row, http_status=status, ord_id=answer.get('id'),
            ord_status=answer.get('status'))
    return answer['id']


def register_initial_contract(db: Session, initial, final_ord_id: str, user) -> dict:
    """Зарегистрировать изначальный договор, прикрепив его к доходному.

    `finalContractId` обязателен по спеке: изначальный всегда создаётся ПРИКРЕПЛЁННЫМ
    к доходному — это и есть подтверждение нашей M:N со стороны самого API. Прикрепить
    существующий к ещё одному доходному умеет `attach_initial` ниже.
    """
    env = _assert_write_allowed()
    already = registry.known_id(db, 'initial_contract', initial.id, env,
                                initial.ord_id, initial.ord_env)
    if already:
        raise OrdSubmitRefused(
            f"Договор уже в ОРД на контуре {env}: {already}. "
            f"Повторная регистрация создала бы там второй такой же.")
    if not final_ord_id:
        raise OrdSubmitRefused(
            "Не указан доходный договор. Изначальный регистрируется только "
            "прикреплённым к доходному — так требует API.")

    client_id = ensure_client(db, initial.advertiser_inn, initial.advertiser_name, user)
    contractor_id = ensure_client(db, initial.contractor_inn, initial.contractor_name, user)
    body = payloads.initial_contract(initial, client_id, contractor_id, final_ord_id)

    _assert_no_pending(db, 'initial_contract', initial.id, env)
    row = _start(db, 'initial_contract', initial.id, env, body, user)
    try:
        status, answer = client.post('/webapi/v3/contracts/initial', body)
    except client.OrdError as e:
        _finish(db, row, http_status=e.status, error=e.message)
        raise
    except Exception as e:
        row.error = _break_label(e)
        db.commit()
        raise

    answer = answer or {}
    ord_id = answer.get('id')
    if not ord_id:
        _no_id(db, row, status, "изначального договора")
    _finish(db, row, http_status=status, ord_id=ord_id, ord_status=answer.get('status'))

    # Местная заглушка `local-<hex>` заменяется настоящим идентификатором. Ради этого
    # она и была: строка не теряет связей со сделкой, а `origin` перестаёт быть 'manual'
    # — договор теперь и правда в кабинете.
    if registry.own_contour(initial.ord_id, initial.ord_env, env):
        initial.ord_id = ord_id
        initial.origin = 'ord'
        initial.status = answer.get('status')
        initial.ord_env = env
        initial.synced_at = datetime.utcnow()

    link = (db.query(OrdInitialFinalLink)
              .filter(OrdInitialFinalLink.initial_contract_id == initial.id,
                      OrdInitialFinalLink.final_ord_id == final_ord_id).first())
    if link is None:
        db.add(OrdInitialFinalLink(initial_contract_id=initial.id,
                                   final_ord_id=final_ord_id))
    db.commit()
    return {'ord_id': ord_id, 'status': answer.get('status'), 'env': env}


def attach_initial(db: Session, initial, final_ord_id: str, user) -> dict:
    """Прикрепить УЖЕ существующий изначальный договор к ещё одному доходному.

    Это второй конец M:N: 22 из 24 повторяющихся изначальных договоров в выгрузке
    привязаны к РАЗНЫМ доходным. Без этой операции такую цепочку в ОРД не собрать.
    """
    env = _assert_write_allowed()
    # Идентификатор ЭТОГО контура, а не колонки: на проде колонки держат демовские id, и
    # прикрепление с ними ушло бы в боевой ЕРИР ссылкой на чужую запись (аудит, 4.M4).
    initial_id = registry.known_id(db, 'initial_contract', initial.id, env,
                                   initial.ord_id, initial.ord_env)
    if not initial_id:
        raise OrdSubmitRefused(
            f"Договор ещё не заведён в ОРД на контуре {env} — сначала регистрация, "
            f"потом прикрепление.")
    if not final_ord_id:
        raise OrdSubmitRefused("Не указан доходный договор")

    existing = (db.query(OrdInitialFinalLink)
                  .filter(OrdInitialFinalLink.initial_contract_id == initial.id,
                          OrdInitialFinalLink.final_ord_id == final_ord_id).first())
    if existing is not None:
        raise OrdSubmitRefused("Эта связь уже есть — прикреплять второй раз нечего")

    body = {'initialContractId': initial_id, 'finalContractId': final_ord_id}
    _assert_no_pending(db, 'attach_initial', initial.id, env)
    row = _start(db, 'attach_initial', initial.id, env, body, user)
    try:
        status, answer = client.post('/webapi/v3/contracts/initial/attachexisting', body)
    except client.OrdError as e:
        _finish(db, row, http_status=e.status, error=e.message)
        raise
    except Exception as e:
        row.error = _break_label(e)
        db.commit()
        raise

    answer = answer or {}
    _finish(db, row, http_status=status, ord_id=answer.get('id'),
            ord_status=answer.get('status'))
    db.add(OrdInitialFinalLink(initial_contract_id=initial.id, final_ord_id=final_ord_id))
    db.commit()
    return {'linked_to': final_ord_id, 'env': env}


def register_creative(db: Session, cset, files, deal, brand, final_ord_id,
                      initial_ord_id, user, campaign_type=None,
                      advertiser_urls=None) -> dict:
    """Зарегистрировать комплект креативов и забрать маркер.

    ЕРИД приходит в ответе СРАЗУ, но регистрация в ЕРИР асинхронная: за выданным
    маркером может не оказаться регистрации, и отвечаем за это мы. Поэтому статус
    сохраняется и обновляется отдельно (`refresh_creative_status`), а веток отказа две,
    и лечатся они по-разному: `RegistrationError` — материалом или полями,
    `MediaDownloadError` — перезаливкой файла.

    Порядок проверок тот же, что у договоров: всё, что можно отклонить до сети,
    отклоняется до сети и следов в журнале не оставляет.
    """
    env = _assert_write_allowed()

    _assert_no_marker(cset, env)
    if cset.erid_source != 'наш':
        # У саморекламы маркер выпускает площадка в своём ОРД: наша регистрация за ним
        # не стоит, и опрашивать его статус тоже нечем.
        raise OrdSubmitRefused(
            "Маркер этого комплекта выпускает площадка — вводится руками, "
            "а не запрашивается у нашего ОРД.")
    # Зарегистрирован, а маркер ещё не пришёл: ОРД выдаёт `id` сразу, а `erid` — бывает,
    # что позже. Проверка одной колонки маркера пропускала повтор, и в ЕРИР уходил второй
    # креатив (аудит 23.09.2026, 4.H5). Такой комплект опрашивают, а не регистрируют.
    known = registry.known_id(db, 'creative', cset.id, env,
                              cset.ord_creative_id, cset.ord_env)
    if known:
        raise OrdSubmitRefused(
            f"Комплект уже зарегистрирован на контуре {env} ({known}), маркер ещё не "
            f"пришёл — обновите статус. Повторная регистрация дала бы второй креатив.")

    body = payloads.creative(cset, files, deal, brand, final_ord_id, initial_ord_id,
                             campaign_type, advertiser_urls)

    _assert_no_pending(db, 'creative', cset.id, env)
    row = _start(db, 'creative', cset.id, env, body, user)

    try:
        status, answer = client.post('/webapi/v3/creatives', body)
    except client.OrdError as e:
        _finish(db, row, http_status=e.status, error=e.message)
        raise
    except Exception as e:
        # Обрыв: неизвестно, создался ли креатив. Попытка остаётся незакрытой и
        # блокирует повтор, пока человек не сверится с кабинетом.
        row.error = _break_label(e)
        db.commit()
        raise

    answer = answer or {}
    ord_id = answer.get('id')
    erid = answer.get('erid')
    ord_status = answer.get('status')
    if not ord_id:
        _no_id(db, row, status, "креатива")
    _finish(db, row, http_status=status, ord_id=ord_id, ord_status=ord_status)

    if registry.own_contour(cset.ord_creative_id, cset.ord_env, env):
        cset.ord_creative_id = ord_id
        cset.erid = erid
        cset.ord_status = ord_status
        cset.ord_error = answer.get('erirValidationError')
        cset.ord_env = env
        cset.ord_synced_at = datetime.utcnow()
    db.commit()
    return {'ord_id': ord_id, 'erid': erid, 'status': ord_status, 'env': env}


def _assert_no_marker(cset, env: str) -> None:
    if cset.erid and (cset.ord_env or registry.ENV_WHEN_UNKNOWN) == env:
        raise OrdSubmitRefused(
            f"У комплекта уже есть маркер {cset.erid} на контуре {env}. "
            f"Повторный выпуск дал бы там второй креатив, который не отозвать.")


def issue_marker(db: Session, cset, files, deal, brand, final_ord_id, initial_ord_id,
                 user, campaign_type=None, advertiser_urls=None) -> dict:
    """Кнопка «выпустить ЕРИД»: регистрация — или опрос, если регистрация уже была.

    Второе нажатие по комплекту, получившему `id` без маркера, — обычное дело: маркер
    приходит позже. Регистрировать его заново значит завести второй креатив в ЕРИР;
    правильный ход — спросить статус и забрать маркер, если он пришёл (4.H5).
    """
    env = _assert_write_allowed()
    _assert_no_marker(cset, env)
    if registry.known_id(db, 'creative', cset.id, env, cset.ord_creative_id, cset.ord_env):
        got = refresh_creative_status(db, cset)
        return {'ord_id': got['ord_id'], 'erid': got['erid'], 'status': got['status'],
                'env': env, 'refreshed': True}
    return register_creative(db, cset, files, deal, brand, final_ord_id, initial_ord_id,
                             user, campaign_type=campaign_type,
                             advertiser_urls=advertiser_urls)


def refresh_creative_status(db: Session, cset) -> dict:
    """Опросить статус креатива. Маркер мог прийти позже — забираем и его.

    Читать прод безопасно, поэтому отдельного разрешения на запись здесь не спрашиваем.
    Идентификатор берётся ТЕКУЩЕГО контура — из колонки или из журнала отправок: контуры
    не общие, и комплект, проверенный на демо, на проде зовётся иначе.
    """
    env = client.env()
    cid = registry.known_id(db, 'creative', cset.id, env,
                            cset.ord_creative_id, cset.ord_env)
    if not cid:
        raise OrdSubmitRefused(f"Комплект ещё не зарегистрирован в ОРД на контуре {env}")

    answer = client.get(f"/webapi/v3/creatives/{cid}/status") or {}
    if isinstance(answer, list):
        answer = answer[0] if answer else {}
    erid = answer.get('erid')
    # В колонки — только свой контур, то же правило, что у регистрации.
    if registry.own_contour(cset.ord_creative_id, cset.ord_env, env):
        same = (cset.ord_env or registry.ENV_WHEN_UNKNOWN) == env
        cset.ord_creative_id = cid
        cset.ord_env = env
        cset.ord_status = answer.get('status') or (cset.ord_status if same else None)
        cset.erid = erid or (cset.erid if same else None)
        cset.ord_error = answer.get('erirValidationError')
        cset.ord_synced_at = datetime.utcnow()
        db.commit()
        erid = cset.erid
    return {'status': answer.get('status') or cset.ord_status, 'erid': erid,
            'error': answer.get('erirValidationError'), 'ord_id': cid, 'env': env}
