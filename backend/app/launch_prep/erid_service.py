# -*- coding: utf-8 -*-
"""Выпуск и объявление ЕРИД — сервис, общий для ручек сбора запуска и крона автовыпуска.

Вынесен из `app/routers/launch_prep.py` 02.10.2026 (аудит интеграций): крон
`erid_auto` импортировал роутер, то есть фоновая задача зависела от слоя HTTP-ручек.
Порог автовыпуска, договорная цепочка ОРД, выпуск маркера, его объявление и опрос
статуса живут здесь; роутер только принимает запрос и зовёт эти функции.

Когда маркер ГОТОВ — правило `app.ord.readiness`, не здесь.
"""
import base64
import logging
from types import SimpleNamespace
from typing import List

from fastapi import HTTPException
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.audit import log_action
from app.files_safe import inside_uploads
from app.launch_prep import pub_rules
from app.launch_prep.models import (LaunchPrepCreativeFile, LaunchPrepCreativeSet, LaunchPrepPair,
                                    LaunchPrepSetTarget, LaunchPrepTarget)
from app.notify import emit
from app.ord import client as ord_client
from app.ord import readiness, registry
from app.ord import submit as ord_submit
from app.ord.client import OrdError
from app.ord.matching import resolve_final
from app.ord.models import OrdInitialContract
from app.ord.payloads import OrdPayloadError
from app.sales.deal_label import deal_label
from app.sales.models import SalesBrand, SalesDeal

log = logging.getLogger("finance.launch_prep")


def moved_to_rework(db: Session, set_ids) -> dict:
    """Площадки, ушедшие из комплекта в доработку: {(set_id, publisher_id): № нового}.

    Доработка заводит НОВЫЙ комплект на одну площадку и ссылается на заменяемый
    (`replaces_set_id`). С этого момента площадка работает там, и в прежнем комплекте её
    держать незачем: она не «молчит» и не «отказала» — она переехала.

    Признак ВЫЧИСЛЯЕТСЯ по этой ссылке, а не хранится колонкой. Хранить пришлось бы
    синхронизировать: удалили новый комплект — старая пара обязана вернуться в строй, и
    забытая синхронизация дала бы пару, ушедшую в никуда.

    Пара при этом остаётся: в ней вердикт «на доработку» с причиной и автором, то есть
    ответ на вопрос «почему креатив переделывали трижды». Удалить её значило бы стереть
    историю ради чистоты списка.
    """
    if not set_ids:
        return {}
    rows = (db.query(LaunchPrepCreativeSet.replaces_set_id,
                     LaunchPrepCreativeSet.publisher_id, LaunchPrepCreativeSet.no)
            .filter(LaunchPrepCreativeSet.replaces_set_id.in_(list(set_ids)),
                    LaunchPrepCreativeSet.publisher_id.isnot(None)).all())
    return {(old_id, pub_id): no for old_id, pub_id, no in rows}


# Доля согласовавших, при которой ЕРИД выпускается АВТОМАТИЧЕСКИ (`app.launch_prep.
# erid_auto`, крон раз в полчаса) — решение владельца 27.09.2026: «20-процентный лимит».
# Кнопку порог не запирает: человек вправе выпустить раньше (порог как запрет снят 31.08).
# Значение читается из настроек, константа — запасное дно.
ERID_THRESHOLD_KEY = "creatives_erid_threshold"


ERID_THRESHOLD_DEFAULT = 0.20


def auto_need(sent: int, share: float) -> int:
    """Сколько согласований нужно автовыпуску: доля от адресатов, вверх, минимум одно.
    20 % от пяти — одно, от десяти — два, от одиннадцати — три."""
    import math
    return max(1, math.ceil(round(sent * share, 6))) if sent else 0


def early_state(st: dict, share: float) -> dict:
    """Ранний ли сейчас выпуск: согласовавших меньше, чем нужно автовыпуску.

    Порог кнопку не запирает (27.09.2026), но выпуск до него требует подтверждения
    (владелец 28.09.2026: на проде маркер выпустили через десять секунд после отправки,
    площадка ещё ничего не согласовала). Одна функция на экран и на ручку — иначе окно
    предупреждало бы по одному счёту, а ручка отказывала бы по другому."""
    need = auto_need(st["sent"], share)
    return {"need_auto": need, "early": st["agreed"] < need}


def erid_threshold(db: Session) -> float:
    """Доля для автовыпуска (`app.launch_prep.erid_auto`). Ручную кнопку не запирает."""
    row = db.execute(sa_text("SELECT value FROM company_settings WHERE key = :k"),
                     {"k": ERID_THRESHOLD_KEY}).first()
    try:
        return float(row[0]) if row and row[0] else ERID_THRESHOLD_DEFAULT
    except (TypeError, ValueError):
        return ERID_THRESHOLD_DEFAULT


def threshold_state(db: Session, set_id: int, share: float = 0) -> dict:
    # `share` не читается с 31.08.2026 (порог снят) — параметр оставлен со значением
    # по умолчанию, чтобы вызовы не пришлось править и чтобы возврат порога был
    # правкой одной функции.
    """Знаменатель — те, КОМУ КОМПЛЕКТ АДРЕСОВАН, а не те, кто согласовал.

    Отказ остаётся в знаменателе намеренно: иначе четверть считалась бы от одних
    довольных, и маркер выпускался бы раньше срока. Округление вверх, минимум один —
    четверть от трёх это один, а не ноль.

    После разворота цепочки (28.08.2026) формула НЕ изменилась, и это осознанно. Пары
    заводятся всё так же все сразу, просто теперь между парой и вопросом площадке стоит
    проверка трафика. Знаменатель от этого тот же, а числитель может расти только после
    двух «ок» — значит порог стал строже сам собой, без правки правила. Проверять здесь
    ещё и вердикт трафика было бы вторым местом, где записан один и тот же порядок.
    """
    return threshold_numbers(active_pairs(db, set_id), share)


def active_pairs(db: Session, set_id: int):
    """Пары комплекта, по которым ещё есть чего ждать.

    Ушедшие в доработку исключаются (31.08.2026). Отказ остаётся — он ОТВЕТ, и от него
    порог не должен смягчаться; доработка ответом не является: площадка теперь работает
    по другому комплекту, и ждать её здесь значит ждать вечно. До этой правки счётчик
    показывал «согласовали 0 из 3» там, где спрашивать осталось двоих.
    """
    # Отозванные у площадки (28.09.2026) не ждут ничего — как и ушедшие в доработку.
    pairs = db.query(LaunchPrepPair).filter(LaunchPrepPair.set_id == set_id,
                                            LaunchPrepPair.withdrawn_at.is_(None)).all()
    gone = moved_to_rework(db, [set_id])
    if not gone or not pairs:
        return pairs
    targets = {t.id: t for t in db.query(LaunchPrepTarget).filter(
        LaunchPrepTarget.id.in_([p.target_id for p in pairs]))}
    return [p for p in pairs
            if (set_id, getattr(targets.get(p.target_id), "publisher_id", None)) not in gone]


def threshold_numbers(pairs, share: float = 0) -> dict:
    """Сколько площадок спросили и сколько ответили согласием. Без базы — чтобы
    проверялось комбинациями, а не фикстурами.

    ПОРОГ СНЯТ 31.08.2026 (владелец: «от него отказались»). Раньше здесь считалась доля
    согласовавших, и маркер не выпускался, пока она не набрана. Теперь числа остаются
    справкой — «согласовали 1 из 3» отвечает на вопрос «сколько уже ответили», — но ничего
    не запирают. `need` и `ready` сохранены в ответе ради совместимости с экраном и
    приборами: `need` всегда 0, `ready` всегда True при непустом списке.

    Параметр `share` не читается. Оставлен, чтобы вызовы не пришлось править по всему
    коду, и чтобы возврат порога был правкой одной функции, а не раскопками."""
    sent = len(pairs)
    agreed = len([p for p in pairs if p.agreed_at])
    return {"sent": sent, "agreed": agreed, "need": 0, "ready": bool(sent)}


def _files_with_content(db: Session, set_id: int):
    """Файлы комплекта вместе с содержимым: в ОРД материал уезжает base64.

    Ссылкой нельзя: схема требует URL, доступный БЕЗ авторизации, а превью креативов
    живёт в песочнице и наружу не открыто.
    """
    out = []
    for f in db.query(LaunchPrepCreativeFile).filter(
            LaunchPrepCreativeFile.set_id == set_id).order_by(LaunchPrepCreativeFile.id):
        # Граница хранилища — ЗДЕСЬ она дороже, чем где-либо ещё: содержимое уходит в
        # ОРД и регистрируется в ЕРИР необратимо. Отправить по испорченному пути чужой
        # файл значит зарегистрировать его навсегда. Поэтому отказ, а не пропуск, и
        # отдельным сообщением: «путь неверный» — это про запись в базе, «файла нет» —
        # про диск, и чинятся они по-разному.
        full = inside_uploads(f.path)
        if full is None:
            raise HTTPException(
                status_code=400,
                detail=f"У файла «{f.original_name}» некорректный путь в базе — "
                       "отправка в ОРД отменена")
        try:
            with open(full, "rb") as fh:
                content = base64.b64encode(fh.read()).decode()
        except OSError:
            raise HTTPException(status_code=400,
                                detail=f"Файл «{f.original_name}» не найден в хранилище")
        out.append(SimpleNamespace(original_name=f.original_name,
                                   is_archive=f.is_archive, content_b64=content))
    return out


def _ord_chain(db: Session, deal: SalesDeal):
    """Идентификаторы договорной цепочки сделки в ОРД.

    Креатив нельзя создать, не назвав доходный договор, — поэтому цепочка собирается
    раньше маркера, и её отсутствие объясняется здесь, а не отказом реестра.
    """
    # Доходный договор — НАШ договор из реестра, помеченный колонками ord_*: своей
    # таблицы у него нет (зеркало завело её только изначальным, чужим договорам).
    #
    # СПРАШИВАЕМ ТУ ЖЕ ФУНКЦИЮ, ЧТО И ЭКРАН СБОРКИ (`resolve_final`), а не колонку
    # ручного выбора. Колонка — только переопределение, и она пуста у всех сделок:
    # обычный случай — договор ВЫЧИСЛЯЕТСЯ по плательщику. Читая колонку, мы получали
    # None там, где лестница показывает зелёное, и уходили в запасную ветку ниже.
    # И берём идентификаторы ТОГО контура, на который сейчас отправляем: демо и прод
    # выдают разные, и договор, зарегистрированный в обоих, зовётся там по-разному.
    env = ord_client.env()

    fr = resolve_final(db, deal)
    final_ord_id = None
    if fr.contract is not None:
        final_ord_id = registry.known_id(db, 'final_contract', fr.contract.id, env,
                                         fr.contract.ord_contract_id,
                                         fr.contract.ord_env)

    initial_ord_id = None
    if deal.ord_initial_contract_id:
        row = db.query(OrdInitialContract).filter(
            OrdInitialContract.id == deal.ord_initial_contract_id).first()
        if row:
            initial_ord_id = registry.known_id(db, 'initial_contract', row.id, env,
                                               row.ord_id, row.ord_env)
        # Запасной ветки «взять доходный из первой попавшейся связи» здесь БЫЛО, и она
        # была опасна: изначальный договор бывает привязан к нескольким доходным (22 из
        # 126, до трёх у одного), `first()` брал произвольный, и на HCLA6E это давал
        # ЧУЖОЙ договор, которого у нас в реестре нет вовсе, — при том что экран
        # показывал договор плательщика. Креатив ушёл бы в ЕРИР под чужим доходным
        # и не отозвался бы. Если доходный не определился, пусть отказ скажет об этом.
    return final_ord_id, initial_ord_id


def _target_urls(db: Session, set_id: int) -> List[str]:
    """Посадочные страницы получателей ЭТОГО комплекта: у каждой площадки своя.

    Вынесено из `issue_erid` не ради красоты. Тот же запрос стоял там строкой с
    `.with_entities(LaunchPrepTarget)` и распаковкой `for (t,) in ...` — а запрос,
    просящий ОДНУ сущность, отдаёт саму сущность, а не кортеж из неё. Выпуск маркера
    падал на `TypeError`, и не находилось это годами по одной причине: шаг стоит в самом
    конце цепочки, в тестах не вызывается (там сеть), а руками до него доходят редко.
    Отдельная функция проверяется прибором без обращения к ОРД.

    Пустые ссылки не отсеиваются здесь: их убирает сборка тела (`ord/payloads.py`),
    и второе место с тем же правилом однажды разошлось бы с первым.
    """
    # С 25.09.2026 посадочная — у строки состава креатива, не у площадки сделки.
    # В ОРД — веб-адрес: диплинк приложения там не ссылка (02.10.2026).
    return [pub_rules.web_url(m.advertiser_url) for m in
            db.query(LaunchPrepSetTarget)
              .join(LaunchPrepPair, (LaunchPrepPair.set_id == LaunchPrepSetTarget.set_id)
                    & (LaunchPrepPair.target_id == LaunchPrepSetTarget.target_id))
              .filter(LaunchPrepPair.set_id == set_id).all()]


def _mark_targets_erid(db: Session, set_id: int):
    """Согласовавшие получатели этого комплекта переходят в «ерид получен».

    Дальше их двигает модуль трафиков («заведён в DSP») и запуск — вручную, потому что
    ни того, ни другого система пока не знает.
    """
    for pair in db.query(LaunchPrepPair).filter(
            LaunchPrepPair.set_id == set_id, LaunchPrepPair.agreed_at.isnot(None)).all():
        t = db.query(LaunchPrepTarget).filter(
            LaunchPrepTarget.id == pair.target_id).first()
        if t and t.state == "согласован":
            t.state = "ерид получен"


def issue_marker_for_set(db: Session, s, deal, actor) -> dict:
    """Выпуск маркера — одна функция на кнопку и на автовыпуск (`erid_auto`).

    `actor` — пользователь у кнопки или None у автовыпуска: в журнале и уведомлениях это
    видно как действие системы. Отказ — `HTTPException(400)` с текстом для человека.
    """
    # Порог согласовавших как ЗАПРЕТ кнопки снят 31.08.2026. Но дно осталось: маркер
    # выпускается НА МАТЕРИАЛ, показанный хоть кому-то. Комплект без живых адресатов —
    # либо ещё не собранный, либо целиком ушедший в доработку; регистрировать его в ЕРИР
    # нечем и незачем, а запись оттуда не отзывается.
    if not active_pairs(db, s.id):
        raise HTTPException(status_code=400,
                            detail="В комплекте нет ни одной площадки — маркер выпускать не на что")

    final_ord_id, initial_ord_id = _ord_chain(db, deal)
    brand = (db.query(SalesBrand).filter(SalesBrand.id == deal.brand_id).first()
             if deal.brand_id else None)
    files = _files_with_content(db, s.id)
    urls = _target_urls(db, s.id)

    try:
        # Регистрация — или опрос, если комплект уже зарегистрирован без маркера:
        # повторная регистрация дала бы второй креатив в ЕРИР (аудит 23.09.2026, 4.H5).
        out = ord_submit.issue_marker(db, s, files, deal, brand, final_ord_id,
                                      initial_ord_id, actor,
                                      advertiser_urls=urls)
    except (ord_submit.OrdSubmitRefused, OrdPayloadError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OrdError as e:
        raise HTTPException(status_code=400, detail=e.message)

    # Маркер не готов — получателей не двигаем и никому не пишем. Иначе площадка
    # получала «ЕРИД None» и ставила в эфир материал без маркировки. Готов — единое
    # правило `app.ord.readiness` (02.10.2026): выданный маркер в RegistrationRequired
    # ещё не готов, его объявит опрос статуса (`refresh_and_announce`), когда ОРД
    # передаст креатив в ЕРИР.
    if not readiness.erid_ready(s):
        db.commit()
        what = (readiness.waiting_text(s) if (s.erid or "").strip()
                else f"зарегистрирован, маркер ещё не выдан (статус {out.get('status')})")
        log_action(db, actor, "issue_erid", "sales_deal", deal.id,
                   f"комплект №{s.no}: {what}" + ("" if actor else " — автовыпуск"))
        return out

    announce_marker(db, s, deal, actor, out)
    return out


def announce_marker(db: Session, s, deal, actor, out: dict) -> None:
    """Маркер получен: получатели — «ерид получен», маркер — в РК, журнал, уведомления.

    Отдельно от выпуска, потому что маркер приходит и позже — при опросе статуса
    автовыпуском. До 27.09.2026 такой поздний маркер оседал в комплекте молча: площадки
    не переходили в «ерид получен» и в РК его не было.
    """
    _mark_targets_erid(db, s.id)
    db.commit()
    # Маркер обязан доехать до кампании СРАЗУ: без него выгрузка в DSP отказывает, и
    # человек, только что выпустивший ЕРИД, читал бы «нет ЕРИД» до следующего утра.
    from app.ad.build import sync_deal_quietly
    sync_deal_quietly(db, deal.id)
    log_action(db, actor, "issue_erid", "sales_deal", deal.id,
               f"комплект №{s.no}: ЕРИД {out.get('erid')}" + ("" if actor else " — автовыпуск"))
    emit(db, "creative_erid_issued",
         title=f"ЕРИД выпущен · {deal_label(deal)}",
         body=f"Комплект №{s.no}: {out.get('erid')}. Статус регистрации: {out.get('status')}",
         link=f"/sales/deals/{deal.code or deal.id}",
         entity_type="sales_deal", entity_id=deal.id, actor=actor,
         ctx={"deal": deal})
    # И площадке: её материал принят и промаркирован — можно ставить в эфир.
    _tell_publisher_erid(db, s, deal)
    db.commit()


def _has_unannounced(db: Session, set_id: int) -> bool:
    """Остались ли согласовавшие площадки, которым маркер ещё не объявлен.

    Это и есть признак «объявлен ли маркер»: объявление переводит их в «ерид получен»,
    а согласие по комплекту с готовым маркером ставит «ерид получен» сразу. Переход
    статуса ОРД признаком быть не может (ревью 02.10.2026): опрос фиксирует статус сам,
    и упавшее после него объявление потеряло бы переход навсегда."""
    return db.query(LaunchPrepPair.id).join(
        LaunchPrepTarget, LaunchPrepTarget.id == LaunchPrepPair.target_id).filter(
        LaunchPrepPair.set_id == set_id, LaunchPrepPair.agreed_at.isnot(None),
        LaunchPrepTarget.state == "согласован").first() is not None


def _sync_marker(db: Session, deal_id: int) -> None:
    from app.ad.build import sync_deal_quietly
    sync_deal_quietly(db, deal_id)


def refresh_and_announce(db: Session, s, deal, actor) -> dict:
    """Опросить статус регистрации; готовый, но не объявленный маркер — объявить.

    Одна функция на кнопку «обновить статус» и на крон (`erid_auto.refresh_statuses`).
    Объявленный уже маркер второй раз площадкам не пишется — только доезжает до РК
    (так у комплектов, объявленных по правилу до 02.10)."""
    out = ord_submit.refresh_creative_status(db, s)
    if readiness.erid_ready(s):
        if _has_unannounced(db, s.id):
            announce_marker(db, s, deal, actor, {"erid": s.erid, "status": s.ord_status})
        else:
            _sync_marker(db, deal.id)
    return out


def announce_pending(db: Session, dry_run: bool = False) -> list:
    """Готовые маркеры нашего ОРД, которые так и не объявлены (сбой при объявлении,
    статус уже конечный и опросом не пересматривается). Крон догоняет их каждый прогон."""
    sets = (db.query(LaunchPrepCreativeSet)
            .filter(LaunchPrepCreativeSet.erid.isnot(None),
                    LaunchPrepCreativeSet.erid_source == readiness.OWN_SOURCE,
                    LaunchPrepCreativeSet.ord_env == ord_client.env(),
                    LaunchPrepCreativeSet.ord_status.in_(readiness.READY_STATUSES))
            .order_by(LaunchPrepCreativeSet.id).all())
    done = []
    for s in sets:
        if not readiness.erid_ready(s) or not _has_unannounced(db, s.id):
            continue
        deal = db.query(SalesDeal).filter(SalesDeal.id == s.deal_id).first()
        if deal is None:
            continue
        if not dry_run:
            announce_marker(db, s, deal, None, {"erid": s.erid, "status": s.ord_status})
        done.append(s.id)
    return done


def _deal_brand_name(db: Session, deal) -> str:
    """Бренд сделки для подстановки в письмо ПЛОЩАДКЕ. Нет бренда — рекламодатель:
    письмо «Готовим размещение  на Икс» читается как ошибка, а не как отсутствие бренда.

    Запасная ветка НЕ отдаёт наш код, номер и НАЗВАНИЕ сделки (правило владельца
    14.09.2026): это письмо наружу. До 23.09.2026 она откатывалась к `deal.title` — а
    название сделки внутреннее, в нём бывают рабочие пометки и имя посредника, и им
    собирался контекст всех писем площадке (аудит, 5.L10). Рекламодатель площадке и так
    виден в кабинете. Имя — `short_name`, наш стандарт, а не битриксовское `name`.
    """
    from app.sales.models import SalesAdvertiser, SalesBrand
    if deal.brand_id:
        row = db.query(SalesBrand.name).filter(SalesBrand.id == deal.brand_id).first()
        if row and (row[0] or "").strip():
            return row[0].strip()
    if getattr(deal, "advertiser_id", None):
        row = (db.query(SalesAdvertiser.short_name, SalesAdvertiser.name)
               .filter(SalesAdvertiser.id == deal.advertiser_id).first())
        if row:
            return (row[0] or row[1] or "").strip()
    return ""


def deal_period_text(deal) -> str:
    """Период размещения словами: «09.2026» или «09.2026 — 11.2026».

    У сделки НЕТ поля `period` — есть `period_from` и `period_to`. Обращение к
    несуществующему полю жило в письме-запросе посадочной незамеченным: ветка
    выполняется только при живой отправке, а в тестах сети нет. Нашлось 14.09.2026,
    когда второй отправитель скопировал ту же строку и уронил прогон.
    """
    a, b = getattr(deal, "period_from", None), getattr(deal, "period_to", None)
    if a and b and (a.year, a.month) != (b.year, b.month):
        return f"{a.strftime('%m.%Y')} — {b.strftime('%m.%Y')}"
    d = a or b
    return d.strftime("%m.%Y") if d else ""


def _tell_publisher_erid(db: Session, cset, deal) -> None:
    """Сказать площадкам комплекта, что ЕРИД выпущен.

    Веером по ПЛОЩАДКАМ комплекта, а не одним письмом на сделку: у площадки своя пара,
    свой креатив и свой эфир, и «по сделке выпущен ЕРИД» не говорит ей, можно ли ставить
    её баннер.
    """
    from app.notify.outward import notify_publisher
    from app.launch_prep.models import LaunchPrepPair, LaunchPrepTarget
    from app.sales.models import SalesPublisher

    rows = (db.query(SalesPublisher, LaunchPrepPair)
            .join(LaunchPrepTarget, LaunchPrepTarget.publisher_id == SalesPublisher.id)
            .join(LaunchPrepPair, LaunchPrepPair.target_id == LaunchPrepTarget.id)
            .filter(LaunchPrepPair.set_id == cset.id,
                    LaunchPrepPair.withdrawn_at.is_(None))
            .order_by(LaunchPrepPair.id).all())
    brand = _deal_brand_name(db, deal)
    period = deal_period_text(deal)
    # Одно письмо на ПЛОЩАДКУ: у площадки с web и app две пары одного комплекта, и она
    # получала два одинаковых письма (аудит 01.10.2026, С-5). ЕРИД у комплекта один.
    seen = set()
    for pub, pair in rows:
        if pub.id in seen:
            continue
        seen.add(pub.id)
        context = " · ".join(x for x in ((pub.domain or pub.name), brand, period) if x)
        try:
            notify_publisher(
                db, "ерид выпущен", pub.id,
                title="Креатив согласован, ЕРИД выпущен",
                body="Материал принят и промаркирован — можно ставить в эфир.",
                facts=[("комплект", f"№{cset.no}"),
                       ("ЕРИД", (getattr(cset, "erid", "") or "—"))],
                context=context, link="/", entity_type="launch_prep_pair",
                entity_id=pair.id, values={"бренд": brand, "период": period})
        except Exception as e:                               # noqa: BLE001
            # Сессию — в рабочее состояние: сбой базы внутри рассылки оставил бы её в
            # упавшей транзакции, и следующая запись (журнал, другие площадки) дала бы 500
            # при уже записанном действии (ревью 24.09.2026).
            db.rollback()
            log.warning("Площадке %s не ушло «ерид выпущен»: %s", pub.id, e)
