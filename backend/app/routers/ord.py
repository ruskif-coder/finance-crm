"""Эндпоинты обвязки ОРД, этап 1.

Читают зеркало и отдают экрану состояние цепочки сборки. Записи в ОРД здесь нет —
она появится на этапе 2, когда будет доступ к API. Единственная запись сейчас —
привязка выбранного изначального договора к сделке.

Каждая ступень ответа несёт `reason` — обоснование того, что подставлено. Это не
украшение: связи нашего рекламодателя с юрлицом ОРД нет по решению владельца, поэтому
подсказка бывает догадкой, и человек должен видеть какой именно.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.models import Contract, Counterparty, User
from app import own_company
from app.ord import importer
from app.ord.enums import (ACTION_TYPES, CONTRACT_TYPES, INITIAL_CONTRACT_TYPES,
                           SUBJECT_TYPES, label_by_code)
from app.launch_prep.models import LaunchPrepCreativeSet
from app.ord.matching import propose_initial, resolve_final
from app.ord.models import (OrdFinalMirror, OrdInitialContract, OrdInitialFinalLink,
                            OrdKktu)
from app.ord.registry import ENV_WHEN_UNKNOWN
from app.permissions import require_permission
from app.routers.sales_dashboard import _assert_deal_in_scope
from app.sales.models import SalesAgencyCounterparty, SalesBrand, SalesDeal

router = APIRouter()

ASSEMBLY_KEYS = ('payer', 'final', 'initial', 'creatives')
STEP_TITLES = {
    'payer': 'Плательщик',
    'final': 'Доходный договор',
    'initial': 'Изначальный договор',
    'creatives': 'Креативы и ЕРИД',
}
# Поля, которые обязана нести каждая ступень ответа. Экран рисует по ним, и
# отсутствие любого ломает ступень молча.
STEP_FIELDS = ('title', 'ok', 'reason')

# Поля договора, без которых ЕРИД не выпустить и акт не сдать. Адрес добавлен по
# изменениям МедиаСкаута от 01.09.2026: без него регистрация акта блокируется.
CONTRACT_FILL_FIELDS = (
    ('contract_number', 'номер договора'),
    ('contract_date', 'дата договора'),
    ('inn', 'ИНН контрагента'),
    ('__address', 'адрес контрагента'),
    ('payment_term_days', 'срок оплаты'),
    ('payment_term_condition', 'условие оплаты'),
)


def _contract_fill(db, contract):
    """Заполненность карточки договора: сколько обязательных полей из скольких.

    Это призыв аккаунту дозаполнить договор в реестре, а не проверка на входе:
    без этих полей ЕРИД не выпустить и акт не сдать, но узнаётся это через месяц,
    на сдаче, и чинится задним числом.
    """
    if contract is None:
        return None
    missing = []
    filled = 0
    for field, label in CONTRACT_FILL_FIELDS:
        if field == '__address':
            cp = (db.query(Counterparty)
                    .filter(Counterparty.id == contract.counterparty_id).first())
            value = cp.address if cp else None
        else:
            value = getattr(contract, field, None)
        if value not in (None, ''):
            filled += 1
        else:
            missing.append(label)
    return [filled, len(CONTRACT_FILL_FIELDS), ', '.join(missing) or 'карточка заполнена']


def _initial_out(c: Optional[OrdInitialContract]) -> Optional[dict]:
    if c is None:
        return None
    return {
        'id': c.id,
        'ord_id': c.ord_id,
        'number': c.number,
        'date': c.date,
        'status': c.status,
        'type': label_by_code(CONTRACT_TYPES, c.type),
        'subject_type': label_by_code(SUBJECT_TYPES, c.subject_type),
        'advertiser': {'inn': c.advertiser_inn, 'name': c.advertiser_name},
        'contractor': {'inn': c.contractor_inn, 'name': c.contractor_name},
        # ОТКУДА строка. `origin` этого не отвечает: и файл, и API кладут 'ord'.
        # Отвечает контур: у синхронизированных он проставлен, у загруженных файлом —
        # пуст. Различать обязательно, потому что демо и прод дают РАЗНЫЕ идентификаторы
        # одному и тому же договору, и перед боевым синком демовские надо снять.
        'source': c.ord_env or ('ручная' if c.origin == 'manual' else 'файл'),
        'synced_at': c.synced_at,
        # Связь с нашим доходным договором: удалять такую строку — рвать сборку.
        'links': len(c.final_links or []),
    }


def _contract_out(c: Optional[Contract]) -> Optional[dict]:
    if c is None:
        return None
    return {
        'id': c.id,
        'number': c.contract_number,
        'date': c.contract_date,
        'counterparty': c.counterparty_name,
        'ord_contract_id': c.ord_contract_id,
        'ord_kind': c.ord_kind,
        'ord_status': c.ord_status,
    }


def _bound_initial_reason(bound: OrdInitialContract, proposal) -> str:
    """Обоснование уже привязанной ступени — не пустая строка (находка ревью I4,
    2026-08-25: раньше reason привязанной ступени возвращался пустым ровно после
    того, как человек подтвердил подстановку — обоснование пропадало в момент,
    когда оно уже было бы всего нужнее для проверки задним числом).

    `proposal` пересчитан заново (см. deal_assembly — теперь безусловно, а не
    только пока не привязано): совпал с тем, что сейчас привязано, — называем то
    же основание, что видел человек, когда подтверждал. Разошёлся (выбрали руками
    из полного списка через «показать все»/«сменить», или автоподбор с тех пор
    стал предлагать другое) — говорим прямо, что привязка ручная, и называем, что
    именно привязано.
    """
    when = bound.date.strftime('%d.%m.%Y') if bound.date else 'без даты'
    label = f'{bound.number or bound.ord_id} от {when}'
    if proposal and proposal.contract and proposal.contract.id == bound.id:
        return f'Привязан {label}. {proposal.reason}'
    return (f'Привязан вручную: {label} — '
           f'{bound.advertiser_name or "рекламодатель не указан"} через '
           f'{bound.contractor_name or "исполнитель не указан"}.')


# ── зависшие отправки ────────────────────────────────────────────────────────
#
# Обрыв связи оставляет строку журнала незакрытой, и это НАМЕРЕННО: неизвестно,
# создалась запись в ЕРИР или нет, а повтор вслепую даёт дубль, который не отозвать.
# Но до 30.08.2026 у этого состояния не было выхода: `_assert_no_pending` советовал
# «проверьте договор в кабинете», а записать результат проверки было негде — ни ручки,
# ни экрана, только SQL. Состояние, в которое можно войти и нельзя выйти, — это не
# осторожность, а тупик.

class OrdResolveIn(BaseModel):
    found: bool                      # нашлась ли запись в кабинете ОРД
    ord_id: Optional[str] = None     # её идентификатор, если нашлась
    note: Optional[str] = None


@router.get("/submissions/pending")
def ord_pending_submissions(db: Session = Depends(get_db),
                            current_user: User = Depends(require_permission("ord", "view"))):
    """Отправки без ответа. Пока такая висит, повтор по этой записи закрыт."""
    from app.ord.models import OrdSubmission
    rows = (db.query(OrdSubmission)
            .filter(OrdSubmission.finished_at.is_(None))
            .order_by(OrdSubmission.started_at.desc()).all())
    return {"rows": [{"id": r.id, "kind": r.kind, "local_id": r.local_id, "env": r.env,
                      "started_at": r.started_at, "error": r.error} for r in rows]}


@router.post("/submissions/{sub_id}/resolve")
def ord_resolve_submission(sub_id: int, payload: OrdResolveIn,
                           db: Session = Depends(get_db),
                           current_user: User = Depends(require_permission("ord", "edit"))):
    """Закрыть зависшую попытку СО СЛОВ ЧЕЛОВЕКА, сходившего в кабинет ОРД.

    Два исхода, и они не симметричны:

    · **записи нет** — попытка закрывается как неудачная, повтор разрешён. Это безопасно:
      дубля не будет, потому что дублировать нечего;
    · **запись есть** — попытка закрывается с найденным идентификатором, но повтор
      ОСТАЁТСЯ закрытым: отправить ещё раз означало бы завести второй объект в ЕРИР.
      Привязка идентификатора к нашей записи делается обычной сверкой, а не отсюда: она
      умеет сопоставлять по ИНН и номеру и не полагается на то, что человек не ошибся
      строкой при наборе.

    Отметка о ручном закрытии остаётся в `error` навсегда — через год «почему у этой
    записи не тот путь» будет вопросом без ответа, если стереть след.
    """
    from datetime import datetime
    from app.ord.models import OrdSubmission

    row = db.query(OrdSubmission).filter(OrdSubmission.id == sub_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Отправка не найдена")
    if row.finished_at is not None:
        raise HTTPException(status_code=400, detail="Эта попытка уже закрыта")

    who = current_user.name or f"user {current_user.id}"
    note = (payload.note or "").strip()
    if payload.found:
        ord_id = (payload.ord_id or "").strip()
        if not ord_id:
            raise HTTPException(status_code=400,
                                detail="Укажите идентификатор записи, найденной в кабинете")
        row.ord_id = ord_id
        row.ord_status = "подтверждено вручную"
        mark = f"запись НАЙДЕНА в кабинете ({ord_id})"
    else:
        # `finished_at` снимает блокировку: `pending()` ищет ровно по нему.
        mark = "записи в кабинете НЕТ — повтор разрешён"

    row.finished_at = datetime.utcnow()
    row.error = " · ".join(filter(None, [row.error, f"проверил {who}: {mark}", note]))
    db.commit()
    log_action(db, current_user, "ord_resolve_submission", "ord_submission", row.id, mark)
    return {"id": row.id, "retry_allowed": not payload.found, "mark": mark}


@router.get("/connection")
def ord_connection(current_user: User = Depends(require_permission("ord", "view"))):
    """Состояние подключения к ОРД — чтобы экран не предлагал кнопку в пустоту."""
    from app.ord import client
    return {"configured": client.is_configured(), "env": client.env(),
            "base_url": client.base_url()}


class SyncLimit(BaseModel):
    # Первая проба — на десятке: посмотреть отчёт глазами, прежде чем трогать две сотни.
    limit: Optional[int] = None


@router.post("/sync/clients")
def ord_sync_clients(payload: SyncLimit, db: Session = Depends(get_db),
                     current_user: User = Depends(require_permission("ord", "edit"))):
    """Фаза 1: проставить `ord_client_id` по ИНН. В ОРД ничего не пишет.

    Право `ord.edit`, а не `ord_submit`: `ord_submit` отделён под НЕОБРАТИМОЕ — запись
    в ЕРИР. Здесь только чтение из кабинета в наши колонки, и держать его за тем же
    правом значило бы приучать выдавать право на необратимое ради безопасного.
    """
    from app.ord import client, sync
    if not client.is_configured():
        raise HTTPException(status_code=400,
                            detail="Доступ к ОРД не настроен: нужны ORD_LOGIN и ORD_PASSWORD")
    report = sync.sync_clients(db, limit=payload.limit)
    log_action(db, current_user, "ord_sync_clients", "counterparty", 0,
               f"контур {report['env']}: сверено {report['looked']}, "
               f"проставлено {report['matched']}, нет в ОРД {len(report['not_in_ord'])}, "
               f"неоднозначных {len(report['ambiguous'])}, отказов {len(report['failed'])}"
               + (f", перепроверено после смены контура {report['requeued']}"
                  if report.get('requeued') else "")
               + (f", снято чужих идентификаторов {report['cleared']}"
                  if report.get('cleared') else ""))
    return report


@router.post("/sync/contracts")
def ord_sync_contracts(db: Session = Depends(get_db),
                       current_user: User = Depends(require_permission("ord", "edit"))):
    """Фаза 1: прочитать договоры из ОРД и обновить зеркало. В ОРД ничего не пишет.

    Заменяет ручную загрузку выгрузки кабинета. Сама загрузка файлом остаётся рабочей:
    пока доступа к API нет, это единственный путь, и отнимать его нельзя.
    """
    from app.ord import client, sync
    if not client.is_configured():
        raise HTTPException(status_code=400,
                            detail="Доступ к ОРД не настроен: нужны ORD_LOGIN и ORD_PASSWORD")
    report = sync.sync_contracts(db)
    read = report.get('read', {})
    log_action(db, current_user, "ord_sync_contracts", "contract", 0,
               f"контур {report['env']}: прочитано доходных {read.get('final', 0)}, "
               f"расходных {read.get('outer', 0)}, изначальных {read.get('initial', 0)}; "
               f"размечено {report['written']['contracts']}, "
               f"изначальных {report['written']['initial']}, связей {report['written']['links']}")
    return report


@router.post("/sync/kktu")
def ord_sync_kktu(db: Session = Depends(get_db),
                  current_user: User = Depends(require_permission("ord", "edit"))):
    """Фаза 1: залить справочник ККТУ в наше зеркало. В ОРД ничего не пишет.

    Право `ord.edit` — то же, что у остальных синков: пишем только в свои таблицы.
    """
    from app.ord import client, sync
    if not client.is_configured():
        raise HTTPException(status_code=400,
                            detail="Доступ к ОРД не настроен: нужны ORD_LOGIN и ORD_PASSWORD")
    report = sync.sync_kktu(db)
    log_action(db, current_user, "ord_sync_kktu", "settings", 0,
               f"контур {report['env']}: прочитано {report['read']}, "
               f"добавлено {report['added']}, обновлено {report['updated']}, "
               f"в справочнике {report['total']}")
    return report


@router.post("/contract/{contract_id}/register")
def ord_register_final(contract_id: int, db: Session = Depends(get_db),
                       current_user: User = Depends(require_permission("ord_submit", "create"))):
    """Фаза 2: зарегистрировать доходный договор в ОРД.

    Право `ord_submit` — то самое, что отделено под НЕОБРАТИМОЕ: маркер, ушедший в
    ЕРИР, не отзывается. Все проверки живут в `app/ord/submit.py`, здесь только
    перевод отказов в HTTP: отказ на входе — 400, отказ ОРД — его собственный код.
    """
    from app.ord import client, submit
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if contract is None:
        raise HTTPException(status_code=404, detail="Договор не найден")
    if not client.is_configured():
        raise HTTPException(status_code=400, detail="Доступ к ОРД не настроен")
    try:
        result = submit.register_final_contract(db, contract, current_user)
    except submit.OrdSubmitRefused as e:
        raise HTTPException(status_code=400, detail=str(e))
    except client.OrdError as e:
        raise HTTPException(status_code=502, detail=e.message)
    log_action(db, current_user, "ord_register_final", "contract", contract.id,
               f"договор {contract.contract_number or contract.id} зарегистрирован "
               f"в ОРД ({result['env']}): {result['ord_id']}, статус {result['status']}")
    return result


@router.get("/contract/{contract_id}/status")
def ord_contract_status(contract_id: int, db: Session = Depends(get_db),
                        current_user: User = Depends(require_permission("ord", "view"))):
    """Обновить статус договора: регистрация асинхронная, Active приходит позже."""
    from app.ord import client, submit
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if contract is None:
        raise HTTPException(status_code=404, detail="Договор не найден")
    if not client.is_configured():
        raise HTTPException(status_code=400, detail="Доступ к ОРД не настроен")
    try:
        return submit.refresh_final_status(db, contract)
    except submit.OrdSubmitRefused as e:
        raise HTTPException(status_code=400, detail=str(e))
    except client.OrdError as e:
        raise HTTPException(status_code=502, detail=e.message)


class RegisterInitial(BaseModel):
    # Пусто — берём доходный, который резолвится у сделки. Явное значение нужно, когда
    # тот же изначальный прикрепляют ко второму доходному (второй конец M:N).
    final_ord_id: Optional[str] = None


@router.post("/deal/{deal_id}/initial/register")
def ord_register_initial(deal_id: int, payload: RegisterInitial,
                         db: Session = Depends(get_db),
                         current_user: User = Depends(require_permission("ord_submit", "create"))):
    """Фаза 3: зарегистрировать в ОРД изначальный договор, привязанный к сделке.

    Заводит при необходимости обе стороны (рекламодателя и исполнителя) — у нас они
    хранятся атрибутами, а API требует идентификаторы юрлиц в ОРД.
    """
    from app.ord import client, submit
    deal = _deal_or_404(db, current_user, deal_id)
    if not deal.ord_initial_contract_id:
        raise HTTPException(status_code=400, detail="К сделке не привязан изначальный договор")
    initial = (db.query(OrdInitialContract)
                 .filter(OrdInitialContract.id == deal.ord_initial_contract_id).first())
    if initial is None:
        raise HTTPException(status_code=404, detail="Изначальный договор не найден")
    if not client.is_configured():
        raise HTTPException(status_code=400, detail="Доступ к ОРД не настроен")

    final_ord_id = payload.final_ord_id or resolve_final(db, deal).final_ord_id
    try:
        if initial.ord_id and not str(initial.ord_id).startswith('local-'):
            result = submit.attach_initial(db, initial, final_ord_id, current_user)
            action, what = "ord_attach_initial", f"прикреплён к {final_ord_id}"
        else:
            result = submit.register_initial_contract(db, initial, final_ord_id, current_user)
            action, what = "ord_register_initial", f"зарегистрирован: {result.get('ord_id')}"
    except submit.OrdSubmitRefused as e:
        raise HTTPException(status_code=400, detail=str(e))
    except client.OrdError as e:
        raise HTTPException(status_code=502, detail=e.message)

    log_action(db, current_user, action, "sales_deal", deal.id,
               f"изначальный договор {initial.number or initial.id} — {what} "
               f"(контур {result['env']})")
    return result


@router.get("/enums")
def ord_enums(current_user: User = Depends(require_permission("sales_registry", "view"))):
    """Перечисления МедиаСкаута для форм заведения.

    Отдаются с бэкенда, а не повторяются в JS: в этом проекте уже расходились
    продублированные константы (формула НДС в четырёх копиях, форматтеры денег в
    тринадцати). Здесь цена расхождения выше обычной — неверный вид договора уезжает
    в ЕРИР молча.
    """
    def out(m, only=None):
        return [{"code": k, "label": v} for k, v in m.items()
                if only is None or k in only]
    return {"contract_types": out(CONTRACT_TYPES),
            # Для изначального звена — только те два, что мы используем. Остальные
            # четыре там появиться не могут: саморекламный договор у нас с площадкой,
            # ДС мы не ведём, виртуальный доходный и ЕКИД — другие звенья.
            "initial_contract_types": out(CONTRACT_TYPES, INITIAL_CONTRACT_TYPES),
            "subject_types": out(SUBJECT_TYPES),
            "action_types": out(ACTION_TYPES)}


@router.get("/initial")
def list_initial(q: Optional[str] = None, final_ord_id: Optional[str] = None,
                 source: Optional[str] = None,
                 limit: int = 200, db: Session = Depends(get_db),
                 current_user: User = Depends(require_permission("ord", "view"))):
    """Справочник изначальных договоров.

    `source` — откуда строка: `файл` (загружена выгрузкой, контур не проставлен),
    `demo` или `prod` (пришла синком с этого контура), `ручная` (заведена руками).
    Отбор нужен перед боевым синком: демовские идентификаторы к проду отношения не
    имеют, и чистить их надо прицельно, а не «всё подряд».
    """
    query = db.query(OrdInitialContract)
    if source:
        src = source.strip()
        if src == 'файл':
            query = query.filter(OrdInitialContract.ord_env.is_(None),
                                 OrdInitialContract.origin != 'manual')
        elif src == 'ручная':
            query = query.filter(OrdInitialContract.origin == 'manual')
        else:
            query = query.filter(OrdInitialContract.ord_env == src)
    if final_ord_id:
        query = (query.join(OrdInitialFinalLink,
                            OrdInitialFinalLink.initial_contract_id == OrdInitialContract.id)
                      .filter(OrdInitialFinalLink.final_ord_id == final_ord_id))
    if q:
        like = f'%{q.strip()}%'
        query = query.filter((OrdInitialContract.advertiser_name.ilike(like)) |
                             (OrdInitialContract.contractor_name.ilike(like)) |
                             (OrdInitialContract.number.ilike(like)) |
                             (OrdInitialContract.advertiser_inn.ilike(like)))
    rows = query.order_by(OrdInitialContract.date.desc()).limit(min(limit, 1000)).all()
    return [_initial_out(c) for c in rows]


class InitialDrop(BaseModel):
    ids: List[int]
    # Признание, а не флажок «я подтверждаю»: строка со связью держит сборку доходного
    # договора, и снос её — отдельное решение, которое человек принимает глазами.
    with_links: bool = False


@router.post("/initial/delete")
def drop_initial(payload: InitialDrop, db: Session = Depends(get_db),
                 current_user: User = Depends(require_permission("ord", "edit"))):
    """Удалить изначальные договоры пачкой — чистка зеркала перед сменой контура.

    Право пока `ord.edit`, а не отдельное `ord.delete`. Сознательно и с оговоркой:
    новое действие в секции требует решения владельца, кому его выдать, и бэкфилла
    `role_permissions` — иначе право по умолчанию запрещено всем, и чистка окажется
    недоступна тому, кто её и затевал. Разделять — когда будет это решение.

    В ОРД НИЧЕГО НЕ УДАЛЯЕТСЯ. Это наше зеркало: строка уйдёт отсюда и вернётся следующим
    синком, если в кабинете она есть. Именно поэтому чистка безопасна и именно поэтому
    она нужна — демовские идентификаторы к боевому контуру отношения не имеют.

    СВЯЗАННЫЕ ЗАЩИЩЕНЫ ПО УМОЛЧАНИЮ. Изначальный договор, привязанный к нашему доходному,
    участвует в сборке креатива: снеся его молча, мы получим сборку, которая перестанет
    собираться, и причину будем искать в другом месте. Поэтому такие строки отбрасываются
    и НАЗЫВАЮТСЯ в ответе, а снести их можно только отдельным признанием `with_links`.
    """
    ids = [int(i) for i in (payload.ids or [])]
    if not ids:
        raise HTTPException(status_code=400, detail="Не выбрано ни одной строки")
    rows = (db.query(OrdInitialContract)
              .filter(OrdInitialContract.id.in_(ids)).all())
    if not rows:
        raise HTTPException(status_code=404, detail="Строки не найдены")

    kept, doomed = [], []
    for c in rows:
        if c.final_links and not payload.with_links:
            kept.append({'id': c.id, 'number': c.number,
                         'advertiser': c.advertiser_name, 'links': len(c.final_links)})
        else:
            doomed.append(c)

    links = sum(len(c.final_links or []) for c in doomed)
    for c in doomed:
        db.delete(c)          # связи уходят каскадом delete-orphan
    log_action(db, current_user, "ord_initial_delete", "settings", None,
               f"удалено изначальных договоров {len(doomed)}"
               + (f", вместе с ними связей {links}" if links else "")
               + (f"; пропущено со связями {len(kept)}" if kept else ""))
    db.commit()
    return {'deleted': len(doomed), 'links_deleted': links, 'kept': kept}


@router.get("/contracts")
def list_contracts(db: Session = Depends(get_db),
                   current_user: User = Depends(require_permission("ord", "view"))):
    """Наши договоры с отметкой ОРД. Без отметки не показываем: две трети реестра
    к ОРД отношения не имеют, и показывать их здесь было бы шумом."""
    rows = (db.query(Contract)
              .filter(Contract.ord_contract_id.isnot(None))
              .order_by(Contract.contract_date.desc().nullslast()).all())
    return [_contract_out(c) for c in rows]


# ── Доходные договоры кабинета ОРД ───────────────────────────────────────────
# Зеркало (`ord_final_mirror`) отвечает на два вопроса сразу, и это ОДИН запрос с разным
# условием, а не два механизма: что из кабинета сошлось с нашим реестром (и значит несёт
# отметку ОРД) и чего у нас нет вовсе. Раньше второй ответ существовал только строкой
# предупреждения в отчёте о загрузке и умирал вместе с ним.

def _final_mirror_out(m: OrdFinalMirror, contract: Optional[Contract]) -> dict:
    return {
        'id': m.id, 'ord_id': m.ord_id, 'env': m.ord_env,
        'number': m.number, 'date': m.date, 'type': label_by_code(CONTRACT_TYPES, m.type),
        'client_inn': m.client_inn, 'client_name': m.client_name,
        'status': m.status, 'error_text': m.error_text,
        'match_note': m.match_note,
        'review_state': m.review_state, 'review_note': m.review_note,
        'reviewed_at': m.reviewed_at,
        # Наш договор — НЕ колонка зеркала: отметка живёт на самом договоре, и вторая
        # копия того же факта со временем разошлась бы с первой.
        'contract': _contract_out(contract),
        'first_seen_at': m.first_seen_at, 'synced_at': m.synced_at,
    }


def _finals_with_contracts(db: Session, rows: List[OrdFinalMirror]) -> List[tuple]:
    """Сопоставить строки зеркала с нашими договорами одним запросом, не по одному.

    Контур обязателен в ключе: демо и прод выдают РАЗНЫЕ идентификаторы одному и тому же
    договору, и без него демовская строка нашла бы боевой договор. Пустой контур у
    нашего договора читается как боевой — то же правило, что в `app/ord/registry.py`.
    """
    ids = [m.ord_id for m in rows]
    ours = {}
    if ids:
        for c in db.query(Contract).filter(Contract.ord_contract_id.in_(ids)).all():
            ours[(c.ord_contract_id, c.ord_env or ENV_WHEN_UNKNOWN)] = c
    return [(m, ours.get((m.ord_id, m.ord_env))) for m in rows]


@router.get("/finals")
def list_final_mirror(state: str = "all", db: Session = Depends(get_db),
                      current_user: User = Depends(require_permission("ord", "view"))):
    """Доходные договоры кабинета ОРД.

    `state`: `all` — всё зеркало; `todo` — только на разбор (не сошлись и человек ещё не
    решил, что с ними делать); `matched` — сошедшиеся с нашим реестром.
    """
    q = db.query(OrdFinalMirror)
    if state == 'todo':
        q = q.filter(OrdFinalMirror.match_note.isnot(None),
                     OrdFinalMirror.review_state == 'new')
    elif state == 'matched':
        q = q.filter(OrdFinalMirror.match_note.is_(None))
    rows = q.order_by(OrdFinalMirror.client_name, OrdFinalMirror.number).all()
    pairs = _finals_with_contracts(db, rows)
    total = db.query(OrdFinalMirror).count()
    todo = (db.query(OrdFinalMirror)
              .filter(OrdFinalMirror.match_note.isnot(None),
                      OrdFinalMirror.review_state == 'new').count())
    return {'items': [_final_mirror_out(m, c) for m, c in pairs],
            'total': total, 'todo': todo}


class FinalLinkIn(BaseModel):
    contract_id: int


@router.post("/finals/{mirror_id}/link")
def link_final_mirror(mirror_id: int, payload: FinalLinkIn, db: Session = Depends(get_db),
                      current_user: User = Depends(require_permission("ord", "edit"))):
    """Привязать доходный из ОРД к нашему договору руками.

    Отметка пишется туда же, куда её пишет загрузка, — на сам договор. Зеркало хранит
    только решение человека (`review_*`): вторая колонка «наш договор» была бы вторым
    ответом на один вопрос, и он разошёлся бы с первым.
    """
    m = db.query(OrdFinalMirror).filter(OrdFinalMirror.id == mirror_id).first()
    if m is None:
        raise HTTPException(status_code=404, detail="Строка зеркала не найдена")
    c = db.query(Contract).filter(Contract.id == payload.contract_id).first()
    if c is None:
        raise HTTPException(status_code=404, detail="Договор не найден")
    if c.ord_contract_id and c.ord_contract_id != m.ord_id:
        raise HTTPException(
            status_code=400,
            detail=f"У договора уже стоит другая отметка ОРД ({c.ord_contract_id}). "
                   f"Снимите её, если она ошибочна.")
    taken = (db.query(Contract)
               .filter(Contract.ord_contract_id == m.ord_id, Contract.id != c.id).first())
    if taken is not None:
        raise HTTPException(
            status_code=400,
            detail=f"Этот идентификатор ОРД уже стоит на договоре "
                   f"«{taken.contract_number or taken.id}» ({taken.counterparty_name})")
    c.ord_contract_id = m.ord_id
    c.ord_kind = 'final'
    c.ord_status = m.status
    c.ord_env = m.ord_env
    c.ord_synced_at = datetime.utcnow()
    m.match_note = None
    m.review_state = 'linked'
    m.reviewed_by, m.reviewed_at = current_user.id, datetime.utcnow()
    db.commit()
    log_action(db, current_user, "ord_link_final", "contract", c.id,
               f"доходный ОРД {m.ord_id} (№ {m.number or 'б/н'}) привязан вручную")
    return {'ok': True}


class FinalDeferIn(BaseModel):
    note: str


@router.post("/finals/{mirror_id}/defer")
def defer_final_mirror(mirror_id: int, payload: FinalDeferIn, db: Session = Depends(get_db),
                       current_user: User = Depends(require_permission("ord", "edit"))):
    """Отложить строку с объяснением — она уходит из списка на разбор.

    Объяснение обязательно: «отложено» без причины через месяц неотличимо от «забыли»,
    и разбирать придётся заново.
    """
    m = db.query(OrdFinalMirror).filter(OrdFinalMirror.id == mirror_id).first()
    if m is None:
        raise HTTPException(status_code=404, detail="Строка зеркала не найдена")
    note = (payload.note or '').strip()
    if not note:
        raise HTTPException(status_code=400,
                            detail="Напишите, почему откладываем: без причины строка "
                                   "через месяц неотличима от забытой")
    m.review_state = 'deferred'
    m.review_note = note
    m.reviewed_by, m.reviewed_at = current_user.id, datetime.utcnow()
    db.commit()
    log_action(db, current_user, "ord_defer_final", "ord", m.id,
               f"доходный ОРД {m.ord_id} отложен: {note}")
    return {'ok': True}


@router.post("/finals/{mirror_id}/reopen")
def reopen_final_mirror(mirror_id: int, db: Session = Depends(get_db),
                        current_user: User = Depends(require_permission("ord", "edit"))):
    """Вернуть отложенное в список на разбор."""
    m = db.query(OrdFinalMirror).filter(OrdFinalMirror.id == mirror_id).first()
    if m is None:
        raise HTTPException(status_code=404, detail="Строка зеркала не найдена")
    m.review_state = 'new'
    m.review_note = None
    m.reviewed_by, m.reviewed_at = current_user.id, datetime.utcnow()
    db.commit()
    log_action(db, current_user, "ord_reopen_final", "ord", m.id,
               f"доходный ОРД {m.ord_id} возвращён на разбор")
    return {'ok': True}


def _brand_marking(db: Session, deal) -> Optional[dict]:
    """Код ККТУ и объект рекламирования у бренда сделки.

    Один хелпер с тем, что отдаёт готовность к ЕРИД (`launch_prep._brand_marking_out`),
    держать не стали: там он опирается на комплект, здесь — на сделку, и общей у них
    только форма ответа. Расшифровка кода берётся из зеркала справочника; нет зеркала —
    показываем голый код, это честнее выдуманного названия.
    """
    brand = (db.query(SalesBrand).filter(SalesBrand.id == deal.brand_id).first()
             if getattr(deal, 'brand_id', None) else None)
    if brand is None:
        return None
    name = None
    if brand.kktu_code:
        row = db.query(OrdKktu.name).filter(OrdKktu.code == brand.kktu_code).first()
        name = row[0] if row else None
    return {'id': brand.id, 'name': brand.name, 'kktu_code': brand.kktu_code,
            'kktu_name': name, 'ad_object_description': brand.ad_object_description}


def _creatives_step(db: Session, deal, bound) -> dict:
    """Четвёртая ступень — теперь рабочая, а не заглушка.

    До 27.08.2026 она честно объявляла себя пустой: креативов не было как данных.
    Теперь есть и они, и выпуск маркера, поэтому ступень отвечает тем же, чем прочие, —
    состоянием и обоснованием. `ok` — когда маркирован КАЖДЫЙ креатив сделки: один
    маркированный из трёх означает, что работа не закончена, и зелёный тут соврал бы.
    """
    brand = _brand_marking(db, deal)
    sets = (db.query(LaunchPrepCreativeSet)
              .filter(LaunchPrepCreativeSet.deal_id == deal.id)
              .order_by(LaunchPrepCreativeSet.no).all())
    marked = [s for s in sets if s.erid]

    if bound is None:
        reason = 'Откроется, когда договорная цепочка сойдётся.'
    elif not sets:
        reason = 'Креативов нет — прикрепите материал в блоке «Креативы».'
    elif brand and not brand.get('kktu_code'):
        reason = 'Не заполнен код ККТУ у бренда — без него маркер не выпустить.'
    elif not marked:
        reason = 'Ни один креатив не маркирован.'
    elif len(marked) < len(sets):
        reason = f'Маркировано {len(marked)} из {len(sets)}.'
    else:
        reason = ('Маркированы все.' if len(sets) > 1
                  else f'Маркирован, ЕРИД {marked[0].erid}.')

    return {
        'title': STEP_TITLES['creatives'],
        'ok': bool(sets) and len(marked) == len(sets),
        'reason': reason,
        'total': len(sets),
        'marked': len(marked),
        # Контур каждого маркера: демовский снаружи неотличим от боевого, а отдать
        # в размещение можно только настоящий.
        'erids': [{'no': s.no, 'erid': s.erid, 'env': s.ord_env} for s in marked],
        # Маркировка бренда — справочная часть ступени, а не отдельный экран: код ККТУ
        # уходит в каждый креатив этой сделки, и смотреть на него логично там же, где на
        # договорную цепочку.
        'brand': brand,
    }


@router.get("/deal/{deal_id}/assembly")
def deal_assembly(deal_id: int, db: Session = Depends(get_db),
                  current_user: User = Depends(require_permission("sales_registry", "view"))):
    """Состояние цепочки сборки. На этом ответе стоит весь экран."""
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)

    fr = resolve_final(db, deal)
    bound = (db.query(OrdInitialContract)
               .filter(OrdInitialContract.id == deal.ord_initial_contract_id).first()
             if deal.ord_initial_contract_id else None)

    final_ord_id = fr.final_ord_id
    # Считается безусловно, а не только пока не привязано (находка I4): список
    # кандидатов нужен и ПОСЛЕ привязки тоже — иначе «показать все»/«сменить»
    # нечем наполнить, а привязывали как раз по подсказке, которую экран сам
    # называет догадкой ("это догадка, проверьте") и которую должно быть можно
    # переиграть.
    proposal = propose_initial(db, deal, final_ord_id) if final_ord_id else None

    # Заполненность карточки договора — только для ступеней, у которых договор это
    # наша строка в `contracts`. Доходный (final) всегда ею и является. Изначальный
    # (initial) — сущность из зеркала ОРД (OrdInitialContract), не нашего реестра;
    # у нас есть карточка на него, только если тот же договор отдельно помечен в
    # своём реестре тем же ord_contract_id (см. CONTRACT_FILL_FIELDS выше и
    # app/ord/matching.py, где то же сопоставление используется для имени в подсказке).
    # Нет своей строки — заполненность не считается (не "0 из 6", а вовсе не показываем).
    final_fill = _contract_fill(db, fr.contract) if fr.contract is not None else None
    initial_contract = (db.query(Contract)
                          .filter(Contract.ord_contract_id == bound.ord_id).first()
                        if bound is not None else None)
    initial_fill = _contract_fill(db, initial_contract) if initial_contract is not None else None

    payer_ok = fr.reason_code not in ('no_payer', 'payer_unknown')
    return {
        'deal_id': deal.id,
        'payer': {
            'title': STEP_TITLES['payer'],
            'ok': payer_ok,
            'reason': '' if payer_ok else fr.reason,
            # Имя и id берутся из НАЙДЕННОГО контрагента (fr.payer), а не из полей
            # сделки: deal.payer_name — исходная метка Битрикса с названием
            # агентства, а не плательщика, и у части сделок пуста вовсе (см.
            # докстринг resolve_final в app/ord/matching.py). Контрагент не найден —
            # name остаётся None, и ступень рисует «Плательщик не определён».
            'counterparty_id': fr.payer.id if fr.payer else None,
            'name': fr.payer.name if fr.payer else None,
        },
        'final': {
            'title': STEP_TITLES['final'],
            'ok': fr.contract is not None,
            'reason': fr.reason,
            'reason_code': fr.reason_code,
            'contract': _contract_out(fr.contract),
            'final_ord_id': final_ord_id,
            'candidates': [_contract_out(c) for c in fr.candidates],
            'fill': final_fill,
        },
        'initial': {
            'title': STEP_TITLES['initial'],
            'ok': bound is not None,
            'reason': (_bound_initial_reason(bound, proposal) if bound is not None
                      else (proposal.reason if proposal else '')),
            'reason_code': ('bound' if bound is not None
                            else (proposal.reason_code if proposal else 'no_final')),
            'bound': _initial_out(bound),
            # Только пока не привязано: после привязки одна кнопка «подтвердить»
            # по единственной подсказке не нужна — есть «сменить», которое ведёт
            # прямо в список candidates (см. ниже, он остаётся полным всегда).
            'proposal': _initial_out(proposal.contract) if (proposal and bound is None) else None,
            'candidates': [_initial_out(c) for c in (proposal.candidates if proposal else [])],
            'fill': initial_fill,
        },
        'creatives': _creatives_step(db, deal, bound),
    }


def _cp_out(db, cp: Counterparty, agency_linked: bool) -> dict:
    """Юрлицо для выбора на ступени «Плательщик».

    Несёт не только имя: человек выбирает не строку справочника, а то, поедет ли по
    ней цепочка дальше. Поэтому сразу видно, есть ли у юрлица договор и помечен ли
    он ОРД — иначе выбор делается вслепую и упирается в следующую ступень.
    """
    total = db.query(Contract).filter(Contract.counterparty_id == cp.id).count()
    ord_marked = (db.query(Contract)
                    .filter(Contract.counterparty_id == cp.id,
                            Contract.ord_contract_id.isnot(None)).count())
    return {"id": cp.id, "name": cp.name, "inn": cp.inn,
            "address": cp.address, "agency_linked": agency_linked,
            "contracts": total, "ord_contracts": ord_marked}


def _deal_or_404(db, current_user, deal_id: int) -> SalesDeal:
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)
    return deal


@router.get("/deal/{deal_id}/payer-options")
def payer_options(deal_id: int, q: Optional[str] = None, db: Session = Depends(get_db),
                  current_user: User = Depends(require_permission("sales_registry", "view"))):
    """Юрлица для ступени «Плательщик»: сперва привязанные к агентству сделки.

    Поиск `q` ищет по всему справочнику — 57 из 92 агентств не имеют ни одного
    привязанного юрлица (мерено 26.08.2026), и без поиска ступень у них была бы
    пустой формой без вариантов.
    """
    deal = _deal_or_404(db, current_user, deal_id)
    linked_ids = set()
    if deal.agency_id:
        linked_ids = {r.counterparty_id for r in
                      db.query(SalesAgencyCounterparty.counterparty_id)
                        .filter(SalesAgencyCounterparty.agency_id == deal.agency_id).all()}

    rows = []
    if linked_ids:
        rows += db.query(Counterparty).filter(Counterparty.id.in_(linked_ids)).all()
    text = (q or '').strip()
    if text:
        found = (db.query(Counterparty)
                   .filter(Counterparty.name.ilike(f'%{text}%')
                           | Counterparty.inn.ilike(f'{text}%'))
                   .order_by(Counterparty.name).limit(30).all())
        rows += [c for c in found if c.id not in linked_ids]

    return {"agency_id": deal.agency_id,
            "items": [_cp_out(db, c, c.id in linked_ids) for c in rows]}


class SetPayer(BaseModel):
    counterparty_id: int
    link_to_agency: bool = True


@router.put("/deal/{deal_id}/payer")
def set_payer(deal_id: int, payload: SetPayer, db: Session = Depends(get_db),
              current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """Назначить плательщика сделки, попутно привязав юрлицо к агентству.

    Привязка по умолчанию: человек, выбравший это юрлицо плательщиком у этого
    агентства, уже сообщил, что они связаны. Заставлять его повторить то же самое
    в справочнике — способ получить справочник, который никто не ведёт.
    """
    deal = _deal_or_404(db, current_user, deal_id)
    cp = db.query(Counterparty).filter(Counterparty.id == payload.counterparty_id).first()
    if cp is None:
        raise HTTPException(status_code=404, detail="Контрагент не найден")

    linked = False
    if payload.link_to_agency and deal.agency_id:
        exists = (db.query(SalesAgencyCounterparty)
                    .filter(SalesAgencyCounterparty.agency_id == deal.agency_id,
                            SalesAgencyCounterparty.counterparty_id == cp.id).first())
        if exists is None:
            db.add(SalesAgencyCounterparty(agency_id=deal.agency_id, counterparty_id=cp.id))
            linked = True

    deal.payer_counterparty_id = cp.id
    # Доходный договор был выбран у ПРЕЖНЕГО плательщика — он больше не относится
    # к сделке. Молча оставленный, он дал бы цепочку, где договор чужого юрлица.
    if deal.ord_final_contract_id:
        prev = db.query(Contract).filter(Contract.id == deal.ord_final_contract_id).first()
        if prev is None or prev.counterparty_id != cp.id:
            deal.ord_final_contract_id = None
    db.commit()
    log_action(db, current_user, "ord_set_payer", "sales_deal", deal.id,
               f"плательщик {cp.name}" + (" (привязан к агентству)" if linked else ""))
    return {"ok": True, "linked_to_agency": linked}


class NewCounterparty(BaseModel):
    name: str
    inn: str
    address: str


@router.post("/deal/{deal_id}/payer")
def create_payer(deal_id: int, payload: NewCounterparty, db: Session = Depends(get_db),
                 current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """Завести юрлицо прямо со ступени и сразу поставить его плательщиком.

    Поля обязательны все три (решение владельца 26.08.2026): без ИНН и адреса ЕРИД не
    выпустить, а узнаётся это через месяц, на сдаче. Дешевле спросить сейчас.
    """
    deal = _deal_or_404(db, current_user, deal_id)
    name = (payload.name or '').strip()
    inn = (payload.inn or '').strip()
    address = (payload.address or '').strip()
    if not (name and inn and address):
        raise HTTPException(status_code=400,
                            detail="Нужны название, ИНН и адрес — без них ЕРИД не выпустить")

    dup = db.query(Counterparty).filter(Counterparty.inn == inn).first()
    if dup is not None:
        raise HTTPException(
            status_code=400,
            detail=f"Контрагент с таким ИНН уже есть: «{dup.name}». Выберите его в списке.")

    cp = Counterparty(name=name, inn=inn, address=address, status='действующий')
    db.add(cp)
    db.flush()
    if deal.agency_id:
        db.add(SalesAgencyCounterparty(agency_id=deal.agency_id, counterparty_id=cp.id))
    deal.payer_counterparty_id = cp.id
    deal.ord_final_contract_id = None      # у нового юрлица договоров ещё нет
    db.commit()
    log_action(db, current_user, "ord_create_payer", "counterparty", cp.id,
               f"{name}, ИНН {inn} — заведён со сборки ОРД сделки {deal.code or deal.id}")
    return {"ok": True, "counterparty": _cp_out(db, cp, True)}


@router.get("/deal/{deal_id}/final-options")
def final_options(deal_id: int, db: Session = Depends(get_db),
                  current_user: User = Depends(require_permission("sales_registry", "view"))):
    """Договоры плательщика для ступени «Доходный договор» — все, не только ОРД."""
    deal = _deal_or_404(db, current_user, deal_id)
    fr = resolve_final(db, deal)
    if fr.payer is None:
        return {"payer": None, "items": []}
    rows = (db.query(Contract)
              .filter(Contract.counterparty_id == fr.payer.id)
              .order_by(Contract.contract_date.desc().nullslast()).all())
    return {"payer": {"id": fr.payer.id, "name": fr.payer.name},
            "chosen_id": deal.ord_final_contract_id,
            "items": [dict(_contract_out(c), fill=_contract_fill(db, c)) for c in rows]}


class SetFinal(BaseModel):
    contract_id: Optional[int] = None      # None — снять выбор, вернуться к вычислению


@router.put("/deal/{deal_id}/final")
def set_final(deal_id: int, payload: SetFinal, db: Session = Depends(get_db),
              current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """Выбрать доходный договор вручную. None — снять выбор и вернуть вычисление."""
    deal = _deal_or_404(db, current_user, deal_id)
    if payload.contract_id is None:
        deal.ord_final_contract_id = None
        db.commit()
        log_action(db, current_user, "ord_set_final", "sales_deal", deal.id,
                   "выбор доходного договора снят")
        return {"ok": True, "contract": None}

    c = db.query(Contract).filter(Contract.id == payload.contract_id).first()
    if c is None:
        raise HTTPException(status_code=404, detail="Договор не найден")
    fr = resolve_final(db, deal)
    # Договор чужого юрлица — цепочка, которой не существует. Та же проверка, что у
    # привязки изначального: экран не должен уметь сохранить несуществующую связь.
    if fr.payer is None or c.counterparty_id != fr.payer.id:
        raise HTTPException(status_code=400,
                            detail="Этот договор принадлежит другому юрлицу, не плательщику сделки")
    deal.ord_final_contract_id = c.id
    db.commit()
    log_action(db, current_user, "ord_set_final", "sales_deal", deal.id,
               f"доходный договор {c.contract_number or c.id}")
    return {"ok": True, "contract": _contract_out(c)}


class NewFinalContract(BaseModel):
    number: str
    date: str                              # ГГГГ-ММ-ДД
    payment_term_days: int
    payment_term_condition: str
    # Идентификатора ОРД тут нет намеренно — см. докстринг create_final ниже.


@router.post("/deal/{deal_id}/final")
def create_final(deal_id: int, payload: NewFinalContract, db: Session = Depends(get_db),
                 current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """Завести договор с плательщиком прямо со ступени и выбрать его.

    Идентификатор ОРД здесь не принимается вовсе — его выдаёт ОРД, а не человек.
    Договор рождается без него и получает его одним из двух путей: регистрацией по API
    (появится с доступом к кабинету) либо следующей загрузкой выгрузки — `_tag_contract`
    в app/ord/importer.py ищет наш договор по номеру с уточнением по ИНН СРЕДИ ТЕХ, У
    КОГО ord_contract_id ещё пуст, и проставляет его сам. Поле для ручного ввода было бы
    приглашением вписать туда похожее, а неверный идентификатор уезжает в ЕРИР молча.
    """
    from datetime import date as _date
    deal = _deal_or_404(db, current_user, deal_id)
    fr = resolve_final(db, deal)
    if fr.payer is None:
        raise HTTPException(status_code=400,
                            detail="Сначала определите плательщика — договор заводится с ним")
    number = (payload.number or '').strip()
    condition = (payload.payment_term_condition or '').strip()
    if not (number and condition):
        raise HTTPException(status_code=400, detail="Нужны номер договора и условие оплаты")
    try:
        when = _date.fromisoformat((payload.date or '').strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Дата договора должна быть в виде ГГГГ-ММ-ДД")

    c = Contract(counterparty_id=fr.payer.id, counterparty_name=fr.payer.name,
                 inn=fr.payer.inn, contract_number=number, contract_date=when,
                 payment_term_days=payload.payment_term_days,
                 payment_term_condition=condition,
                 own_company_id=own_company.sole_id(db))
    db.add(c)
    db.flush()
    deal.ord_final_contract_id = c.id
    db.commit()
    log_action(db, current_user, "ord_create_final", "contract", c.id,
               f"{number} от {when.strftime('%d.%m.%Y')} с {fr.payer.name} — заведён со сборки ОРД")
    return {"ok": True, "contract": _contract_out(c)}


@router.get("/deal/{deal_id}/initial-options")
def initial_options(deal_id: int, q: Optional[str] = None, db: Session = Depends(get_db),
                    current_user: User = Depends(require_permission("sales_registry", "view"))):
    """Изначальные договоры для ступени: сперва те, что под доходным сделки, потом поиск.

    Список под доходным бывает и полным, и бесполезным одновременно: у сделки HCLA6E
    под её доходным лежат семь договоров, и ни один не относится к рекламодателю
    сделки — связи из выгрузки описывают чужие цепочки на том же нашем договоре.
    Поэтому поиск идёт по всему зеркалу (126 договоров), а не по семи.

    Каждая строка помечена `linked`: под доходным сделки она или нет. Без пометки
    поиск по всей базе превратил бы выбор в лотерею — снаружи эти строки неотличимы.
    """
    deal = _deal_or_404(db, current_user, deal_id)
    fr = resolve_final(db, deal)
    linked_ids = set()
    if fr.final_ord_id:
        linked_ids = {r.initial_contract_id for r in
                      db.query(OrdInitialFinalLink.initial_contract_id)
                        .filter(OrdInitialFinalLink.final_ord_id == fr.final_ord_id).all()}

    rows = []
    if linked_ids:
        rows += (db.query(OrdInitialContract)
                   .filter(OrdInitialContract.id.in_(linked_ids))
                   .order_by(OrdInitialContract.date.desc()).all())
    text = (q or '').strip()
    if text:
        like = f'%{text}%'
        found = (db.query(OrdInitialContract)
                   .filter(OrdInitialContract.advertiser_name.ilike(like)
                           | OrdInitialContract.contractor_name.ilike(like)
                           | OrdInitialContract.number.ilike(like)
                           | OrdInitialContract.advertiser_inn.ilike(f'{text}%'))
                   .order_by(OrdInitialContract.date.desc()).limit(50).all())
        rows += [c for c in found if c.id not in linked_ids]

    return {
        "final": ({"ord_id": fr.final_ord_id,
                   "number": fr.contract.contract_number if fr.contract else None}
                  if fr.final_ord_id else None),
        "chosen_id": deal.ord_initial_contract_id,
        "items": [dict(_initial_out(c), linked=c.id in linked_ids) for c in rows],
    }


class NewInitialContract(BaseModel):
    number: str
    date: str
    advertiser_inn: str
    advertiser_name: str
    contractor_inn: str
    contractor_name: str
    type: str                              # тип договора — в выгрузке заполнен у всех 126
    subject_type: Optional[str] = None     # «Вид» в реестре; пуст у 4 из 126
    action_type: Optional[str] = None      # вид деятельности; пуст у 64 из 126


@router.post("/deal/{deal_id}/initial")
def create_initial(deal_id: int, payload: NewInitialContract, db: Session = Depends(get_db),
                   current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """Завести изначальный договор, которого нет в выгрузке ОРД, и привязать к сделке.

    `ord_id` — идентификатор кабинета, он NOT NULL UNIQUE и его неоткуда взять, пока
    договор в ОРД не заведён. Ставится местная заглушка `local-<hex>` — тем же приёмом,
    что `bitrix_id` у сделок, созданных у нас. `origin='manual'` отделяет такие строки
    от 126 зеркальных: при следующей загрузке выгрузки они не должны выглядеть
    пришедшими из ОРД, и настоящий идентификатор подменит заглушку.

    Связь с доходным (`ord_initial_final_links`) заводится, только если у доходного уже
    есть идентификатор ОРД: связь без него — запись о цепочке, которой в ОРД нет.
    """
    from datetime import date as _date
    import uuid as _uuid
    deal = _deal_or_404(db, current_user, deal_id)
    number = (payload.number or '').strip()
    if not number:
        raise HTTPException(status_code=400, detail="Нужен номер договора")
    for field, label in (('advertiser_inn', 'ИНН рекламодателя'),
                         ('advertiser_name', 'название рекламодателя'),
                         ('contractor_inn', 'ИНН исполнителя'),
                         ('contractor_name', 'название исполнителя')):
        if not (getattr(payload, field) or '').strip():
            raise HTTPException(status_code=400, detail=f"Нужно указать {label}")
    try:
        when = _date.fromisoformat((payload.date or '').strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Дата договора должна быть в виде ГГГГ-ММ-ДД")

    # Коды перечислений проверяются, а не принимаются на веру: подставленный не тот вид
    # договора уезжает в ЕРИР молча (см. докстринг app/ord/enums.py). Тип обязателен —
    # в выгрузке он заполнен у всех 126 договоров, пустой означал бы недозаполненный.
    if payload.type not in INITIAL_CONTRACT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Изначальный договор бывает услуговым или посредническим")
    for value, mapping, label in ((payload.subject_type, SUBJECT_TYPES, 'Вид договора'),
                                  (payload.action_type, ACTION_TYPES, 'Вид деятельности')):
        if value and value not in mapping:
            raise HTTPException(status_code=400, detail=f"{label}: неизвестное значение")

    c = OrdInitialContract(
        ord_id='local-' + _uuid.uuid4().hex, origin='manual',
        number=number, date=when, type=payload.type,
        advertiser_inn=payload.advertiser_inn.strip(),
        advertiser_name=payload.advertiser_name.strip(),
        contractor_inn=payload.contractor_inn.strip(),
        contractor_name=payload.contractor_name.strip(),
        subject_type=payload.subject_type, action_type=payload.action_type)
    db.add(c)
    db.flush()

    fr = resolve_final(db, deal)
    if fr.final_ord_id:
        db.add(OrdInitialFinalLink(initial_contract_id=c.id, final_ord_id=fr.final_ord_id,
                                   contract_id=fr.contract.id if fr.contract else None))
    deal.ord_initial_contract_id = c.id
    db.commit()
    log_action(db, current_user, "ord_create_initial", "sales_deal", deal.id,
               f"изначальный договор {number} заведён вручную ({payload.advertiser_name.strip()})")
    return {"ok": True, "initial": _initial_out(c)}


class BindInitial(BaseModel):
    initial_contract_id: int
    # Привязать договор, которого нет среди связей выгрузки под доходным сделки.
    # По умолчанию запрещено: см. проверку ниже.
    force: bool = False


@router.put("/deal/{deal_id}/initial")
def bind_initial(deal_id: int, payload: BindInitial, db: Session = Depends(get_db),
                 current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """Привязать изначальный договор к сделке.

    Проверяется, что договор действительно лежит под тем доходным, который резолвится
    у сделки. Без этой проверки экран сохранил бы цепочку, которой не существует —
    изначальный от одного заказчика под доходным другого, — и она уехала бы в ЕРИР.
    """
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)
    contract = (db.query(OrdInitialContract)
                  .filter(OrdInitialContract.id == payload.initial_contract_id).first())
    if contract is None:
        raise HTTPException(status_code=404, detail="Изначальный договор не найден")

    fr = resolve_final(db, deal)
    if not fr.final_ord_id:
        raise HTTPException(status_code=400,
                            detail=f"Доходный договор не определён: {fr.reason}")
    linked = (db.query(OrdInitialFinalLink)
                .filter(OrdInitialFinalLink.initial_contract_id == contract.id,
                        OrdInitialFinalLink.final_ord_id == fr.final_ord_id).first())
    # Связи берутся из выгрузки ОРД: их отсутствие означает, что в кабинете такой
    # цепочки нет. Это по-прежнему запрещено по умолчанию — но не наглухо: выгрузка
    # бывает неполной, а человек видит договор своими глазами. Поэтому запрет
    # снимается только явным `force`, и в журнале это отдельная запись, а не такая же.
    if linked is None and not payload.force:
        raise HTTPException(
            status_code=400,
            detail="Этот изначальный договор не относится к доходному договору сделки")

    deal.ord_initial_contract_id = contract.id
    db.commit()
    log_action(db, current_user,
               "ord_bind_initial_forced" if linked is None else "ord_bind_initial",
               "sales_deal", deal.id,
               f"изначальный договор {contract.number or contract.ord_id}"
               + ("" if linked is not None else " — вне связей выгрузки ОРД"))
    return {"ok": True, "initial": _initial_out(contract)}


@router.post("/import")
async def import_export(initial: Optional[UploadFile] = File(None),
                        final: Optional[UploadFile] = File(None),
                        outer: Optional[UploadFile] = File(None),
                        db: Session = Depends(get_db),
                        current_user: User = Depends(require_permission("ord", "edit"))):
    """Загрузка выгрузки из кабинета. Повторная загрузка обновляет, а не плодит."""
    if not any((initial, final, outer)):
        raise HTTPException(status_code=400, detail="Не приложено ни одного файла")
    stat = importer.upsert(
        db,
        initial=await initial.read() if initial else None,
        final=await final.read() if final else None,
        outer=await outer.read() if outer else None,
    )
    log_action(db, current_user, "ord_import", "ord", None,
               f"изначальных {stat['initial']}, связей {stat['links']}, "
               f"договоров помечено {stat['contracts']}")
    return stat
