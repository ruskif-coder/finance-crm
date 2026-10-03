"""Контур «Траффики» → Дашборд: фаза открутки РК (этап 3b).

Рабочий экран трафика: реестр РК со статусами, расхлоп с площадками и динамикой,
управление (старт/стоп/пауза на РК и на каждой площадке).

**Видимость — та же, что у очереди**, и берётся ОТТУДА ЖЕ (`routers/traffic._apply_scope`),
а не переписывается здесь: правило «мастер видит всё и может смотреть чужое, рядовой трафик —
только свои по `traffic_manager_id`» менялось 31.08.2026, и второй его экземпляр разошёлся бы
с первым. Поэтому `deals_scope` у этого права нет — «свои» у трафика это не «сейлз или аккаунт».

Право `traffic_dashboard` (view — смотреть, edit — управлять). Бэкфилл ролей —
`migrations/2026-09-02_traffic_dashboard_perm.sql`: трафики и мастера полный, аккаунты просмотр.

Факт показов берётся из `ad_campaign_stat` — суточного СРЕЗА, который наполняет коннектор
(этап 2c). Пока среза нет, факт и прогноз честно пустые: выдумывать темп не из чего.
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

import logging

from app.dsp import client as ds
from app import timez
from app.ad import balance, build
from app.ad import external as ext_mod
from app.launch_prep import volumes
from app.ad.flight import (CAMPAIGN_MANUAL, CREATIVE_MANUAL, CREATIVE_REJECTED, CREATIVE_STATUSES,
                           GRAIN_DAYS, campaign_chain_status, effective_campaign_status,
                           PLACEMENT_CHAIN, PLACEMENT_MANUAL, PLACEMENT_RUNNING,
                           PLACEMENT_STATUSES, PLACEMENT_OFF, PLACEMENT_READY,
                           as_placement_scale, best_chain_status, can_start_placement, holds,
                           creative_counts, culprits, daily_buckets,
                           distribute, effective_status, flight_of, progress, split_evenly)
from app.ad.models import AdCampaign, AdCampaignCreative, AdCampaignPlacement
from app.dsp.client import MsClient
from app.ad.stat_sources import (VERIFIER, comparable, fact_as_of, fact_sources, is_stale, wr_outside, goal_limit, mismatch_level,
                                 mismatch_pct)
from app.traffic import urgency
from app.audit import log_action
from app.database import get_db
from app.models import User
from app.permissions import require_permission
from app.routers.traffic import _apply_scope, _is_master
from app.dsp import refresh as dsp_refresh
from app.sales.models import SalesDeal, SalesRep
from app.sales.reps import staff_users
from app.sales.row_context import load_row_context

log = logging.getLogger("finance.traffic_dashboard")

router = APIRouter()

VIEW = require_permission("traffic_dashboard", "view")
EDIT = require_permission("traffic_dashboard", "edit")

CAMPAIGN_STATUSES = ("ожидает сборки", "готова", "запущена", "пауза",
                     "остановлена", "окончена", "архив")
RUNNING = ("запущена", "пауза")


class ScreensIn(BaseModel):
    done: bool


class StatusIn(BaseModel):
    status: str
    # Только для запуска РК: поднять заодно отключённые и поставленные на паузу площадки.
    # Спрашивается у человека, а не подразумевается: «остановлена» у площадки могла быть
    # осознанным решением, и включить её молча значит отменить чужое решение.
    with_placements: Optional[bool] = None


# ── расчёты ───────────────────────────────────────────────────────────────
#
# Прогноз, темп, недокрут и распределение считает `app/ad/flight.py` — там же, где
# описано правило. Прежняя локальная `forecast()` считала темп от календарных дат
# и называла `pace` показы в день; в новом ядре `pace` это ДОЛЯ выполнения, а показы
# в день зовутся `speed`. Совпадение имени при смене единицы — самая дорогая ошибка
# в этом месте, поэтому старая функция удалена, а не оставлена рядом.


def _fact_sources(db: Session, campaign_ids: List[int]) -> list:
    """Откуда взят факт у видимых РК.

    Нужно ровно для одного: сказать вслух, когда цифры НЕ настоящие. На стенде весь
    факт — из демо-скрипта (`source='demo'`), а на экране он до 11.09.2026 был
    неотличим от боевого: слова «демо» в интерфейсе не встречалось ни разу, а тянучка
    статистики DSP не написана вовсе, то есть настоящего факта пока неоткуда взяться.

    Показывать правдоподобное вместо правды — худшее, что может делать витрина: по этим
    числам принимают решения о перераспределении объёма.
    """
    if not campaign_ids:
        return []
    # Единственный запрос к таблице БЕЗ фильтра источника, и намеренно: он отвечает на
    # вопрос «что там вообще лежит», а не «сколько показов». Остальные шесть фильтруют
    # через `fact_sources()` — см. `app/ad/stat_sources.py`.
    rows = db.execute(text(
        "SELECT DISTINCT source FROM ad_campaign_stat WHERE campaign_id = ANY(:i)"),
        {"i": campaign_ids}).all()
    from app.ad.stat_sources import non_combat
    return non_combat(r[0] for r in rows if r[0])


def _fact_last_ingest(db: Session, campaign_ids: List[int]):
    """Когда факт приезжал в последний раз.

    Пустые столбики на графике значат две разные вещи: «ещё не крутили» и «данные не
    приходят». Отличить их с экрана было нечем — мёртвый коннектор выглядел как тишина
    в кампании (F5-10 внешнего аудита 11.09.2026). Дата последнего поступления отвечает
    на это одним числом.
    """
    if not campaign_ids:
        return None
    return db.execute(text(
        "SELECT max(imported_at) FROM ad_campaign_stat "
        "WHERE campaign_id = ANY(:i) AND source = ANY(:src)"),
        {"i": campaign_ids, "src": fact_sources()}).scalar()


def _facts(db: Session, campaign_ids: List[int]) -> dict:
    if not campaign_ids:
        return {}
    rows = db.execute(text(
        "SELECT campaign_id, sum(shows) AS shows, sum(clicks) AS clicks "
        "FROM ad_campaign_stat WHERE campaign_id = ANY(:i) AND source = ANY(:src) "
        "GROUP BY campaign_id"),
        {"i": campaign_ids, "src": fact_sources()}).mappings().all()
    return {r["campaign_id"]: dict(r) for r in rows}


def _verifier(db: Session, campaign_ids: List[int], until: Optional[date] = None) -> dict:
    """Показы ВЕРИФИКАТОРА по РК и по каждой площадке — одним запросом на оба уровня.

    Отдельной функцией от `_facts`, а не параметром к ней, СОЗНАТЕЛЬНО. `_facts` отдаёт
    то, что идёт в закрытие; здесь — независимое измерение, которое в закрытие не идёт
    никогда (решение владельца 10.09.2026, `app/ad/stat_sources.py`). Один вызов с
    флажком «а теперь посчитай другое» рано или поздно вызвали бы не с тем флажком, и
    справочная величина попала бы в факт — тихо и правдоподобно.

    Площадки приходят вместе с РК: карточка показывает и итог, и расхлоп по площадкам,
    а два запроса ради этого — лишний обход той же таблицы.
    """
    if not campaign_ids:
        return {}
    # `until` — дата среза (`fact_as_of`): WR позже последнего дня нашего факта в сверку
    # не идёт. Ручной итог за период датирован концом периода — его срез не режет.
    rows = db.execute(text(
        "SELECT campaign_id, placement_id, sum(shows) AS shows "
        "FROM ad_campaign_stat WHERE campaign_id = ANY(:i) AND source = ANY(:src) "
        "AND (CAST(:u AS date) IS NULL OR date <= :u OR source = 'weborama_manual') "
        "GROUP BY campaign_id, placement_id"),
        {"i": campaign_ids, "src": list(VERIFIER), "u": until}).mappings().all()
    out: dict = {}
    for r in rows:
        slot = out.setdefault(r["campaign_id"], {"shows": 0, "by_placement": {}})
        n = r["shows"] or 0
        slot["shows"] += n
        # Строка без площадки — замер по РК целиком: в итог входит, в расхлоп нет.
        if r["placement_id"] is not None:
            slot["by_placement"][r["placement_id"]] = n
    return out


def _wr_mismatch(own, wr, goals):
    """Расхождение факта с Weborama за период и его цвет — `stat_sources.mismatch_level`."""
    pct = mismatch_pct(own, wr)
    return {"pct": pct, "wr": wr, **mismatch_level(pct, goal_limit(goals))} if pct is not None else None


def _campaign_in_scope(db: Session, campaign_id: int, user: User):
    """РК вместе со сделкой, пропущенная через область видимости раздела.

    Правило берётся ОТТУДА ЖЕ, что у очереди (`routers/traffic._apply_scope`) — второй
    его экземпляр разошёлся бы с первым, как это уже было со статусами.

    Сегодня очередь общая (03.09.2026), и фильтр никого не отсекает. Механизм всё равно
    нужен: ручка трогает сделку, и когда правило снова ужесточат — а его меняли дважды
    за четыре дня, — экран не должен оказаться дырой. Прибор `test_deal_scope` держит
    именно это: маршрут, трогающий сделку без области, считается дырой по умолчанию.
    """
    q = (db.query(AdCampaign, SalesDeal)
         .join(SalesDeal, SalesDeal.id == AdCampaign.deal_id)
         .filter(AdCampaign.id == campaign_id))
    row = _apply_scope(q, db, user, all_reps=True).first()
    if not row:
        raise HTTPException(404, "РК не найдена")
    return row


def _creatives_all(db: Session, campaign_ids: List[int]) -> dict:
    """Креативы НЕСКОЛЬКИХ РК: {campaign_id: {placement_id: [статусы]}}.

    Дашборд считает статус каждой РК из её креативов, и запрос на каждую превратил бы
    один экран в шестьдесят обращений — тот же приём, что `page_ids` в реестре сделок.
    """
    if not campaign_ids:
        return {}
    rows = db.execute(text(
        "SELECT campaign_id, placement_id, status FROM ad_campaign_creative "
        "WHERE campaign_id = ANY(:i)"), {"i": campaign_ids}).mappings().all()
    out: dict = {}
    for r in rows:
        out.setdefault(r["campaign_id"], {}).setdefault(r["placement_id"], []).append(r["status"])
    return out


def _uploaded_placements(db: Session, campaign_ids: List[int]) -> set:
    """Площадки, выгруженные в DSP (хоть один креатив с хешем), — пачкой на реестр."""
    if not campaign_ids:
        return set()
    return {pid for (pid,) in db.execute(text(
        "SELECT DISTINCT c.placement_id FROM ad_campaign_creative c "
        "JOIN ad_campaign_placement p ON p.id = c.placement_id "
        "WHERE p.campaign_id = ANY(:i) AND coalesce(c.ms_creative_xxhash, '') <> ''"),
        {"i": campaign_ids})}


def _chain_of(c, placements, creatives: dict) -> str:
    """Цепной статус РК по её площадкам: `placements` — пары (id, сохранённый статус),
    `creatives` — {placement_id: [строки креативов]}.

    Статус площадки собирается из ЕЁ креативов (ручной перекрывает расчёт), РК — из
    площадок. Одно место на расхлоп и на то, чему следует DSP: второй расчёт разошёлся
    бы с первым, и экран говорил бы о кампании одно, а в DSP стояло бы другое.
    """
    running, can, n = 0, False, 0
    for pid, stored in placements:
        n += 1
        mine = [x["status"] for x in creatives.get(pid, [])]
        st = effective_status(stored, best_chain_status(_as_placement_scale(x) for x in mine))
        # Крутит — только площадка НАШЕЙ DSP: Adfox и «вне контура» отмечают «запущен»
        # руками, и РК от этого становилась «запущенной» без единого показа в DSP, а кнопка
        # старта гасла (владелец 02.10.2026, 37ZTY3: «adfox не в счёт»).
        running += st in PLACEMENT_RUNNING and dsp_uploaded(creatives.get(pid, []))
        can = can or can_start_placement(mine)
    return campaign_chain_status(has_plan=bool(c.plan_show), placements=n,
                                 running=running, can_start=can)


def _campaign_chain(db: Session, c) -> str:
    pls = db.query(AdCampaignPlacement).filter_by(campaign_id=c.id).all()
    return _chain_of(c, [(p.id, p.status) for p in pls], _creatives_of(db, c.id))


def _dsp_follow(db: Session, c) -> Optional[str]:
    """Кампания в DSP следует нашему ИТОГОВОМУ статусу РК (владелец 23.09.2026: «кнопка
    управляет»). Звать ПОСЛЕ своих изменений и ДО коммита.

    Итоговому, а не нажатому: «запущена» у нас — факт (крутит хоть одна площадка), и
    «Запустить» без запущенных площадок оставляет РК «готовой» — тогда DSP стоит.

    Сбой DSP откатывает наши изменения: экран не должен говорить о кампании то, чего в
    DSP нет. Крона нет — DSP узнаёт о плане и статусе только нажатием.
    """
    from app.dsp.campaigns import apply_status
    from app.dsp.client import MsError

    db.flush()
    target = effective_campaign_status(c.status, _campaign_chain(db, c))
    try:
        return apply_status(db, c, target)
    except MsError as e:
        db.rollback()
        raise HTTPException(502, f"DSP не принял смену статуса — изменения не сохранены: {e}")


# Что можно поднять массовым стартом РК (владелец 01.10.2026): согласованные и ещё не
# включённые («ждёт запуска»), а также выключенные и на паузе — их человек видит в окне
# и подтверждает. До 01.10 «ждёт запуска» сюда не входил, и «Запустить» на 54ZYCH не
# поднял ни одной из 19 готовых площадок.
START_RAISABLE = (PLACEMENT_READY, PLACEMENT_OFF, "пауза")


def mass_start_skip(mode: Optional[str]) -> Optional[str]:
    """Принудительный старт РК площадки Adfox / вне контура НЕ поднимает (владелец
    02.10.2026): они запускаются своей отметкой у площадки, а кнопка РК — про нашу DSP."""
    from app.launch_prep import pub_rules
    return ("Adfox / вне контура — запускается отметкой у площадки"
            if mode == pub_rules.MODE_EXTERNAL else None)


def start_block(db: Session, c, p, creatives: list, mode: Optional[str] = None) -> Optional[str]:
    """Почему площадку НЕЛЬЗЯ запустить — словами, или None. Одно правило на кнопку
    площадки и на массовый старт РК: разойдясь, они пускали бы разное."""
    if not can_start_placement(x["status"] for x in creatives):
        return "нет согласованного креатива"
    if mode is None:
        from app.launch_prep import pub_rules
        mode = pub_rules.placement_modes(db, {(c.deal_id, p.publisher_id)}).get(
            (c.deal_id, p.publisher_id), {}).get("mode")
    from app.launch_prep import pub_rules
    if mode != pub_rules.MODE_EXTERNAL and not dsp_uploaded(creatives):
        return "креатив не выгружен в DSP — сначала «В DSP»"
    return None


def launch_hint(dsp_block: Optional[str], vol: Optional[dict], closed: bool,
                ready: int, running: int, waiting: int = 0) -> Optional[str]:
    """Почему запуск РК заперт или ничего не поднимет — словами, для подсказки на кнопке
    (владелец 02.10.2026: «выводи подсказку трафику, почему заперт запуск, по всем
    событиям»). Причины — те же, что проверяет сервер при нажатии; None — запускать можно."""
    why = []
    if closed:
        why.append("кампания в DSP в архиве — для продолжения нужна новая РК")
    if dsp_block:
        why.append(dsp_block)
    if vol and vol.get("blocked"):
        why.append(vol.get("message") or "объёмы площадок больше плана РК")
    if not why and not ready and not running:
        why.append("нет площадок, готовых к старту" + (
            f": {waiting} ждут согласования креатива или выгрузки в DSP" if waiting else ""))
    return "; ".join(why) or None


RUNNING_STAGE = "В размещении"


def advance_deal(db: Session, deal, stage_name: str, user, reason: str) -> dict:
    """Перевести сделку ВПЕРЁД на стадию по имени — через общую точку
    (`stage_move`), с её требованиями и историей. Назад не ведёт никогда.
    → {"moved": bool, "stage": имя, "refused": текст | None}. Отказ не роняет
    вызывающего: РК запущена/окончена — это факт, от лестницы он не зависит."""
    from app.sales import catalog as catalog_mod
    from app.sales import stage_move
    cat = catalog_mod.Catalog(db)
    target = next((st for st in cat.stages if st.name == stage_name), None)
    cur = cat.by_id.get(deal.our_stage_id)
    if target is None:
        return {"moved": False, "stage": cur.name if cur else None,
                "refused": (f"Сделка не переведена: в каталоге стадий нет «{stage_name}» — "
                            "стадию переименовали. Переведите вручную и поправьте название.")}
    if deal.our_stage_id == target.id or not cat.is_before(deal.our_stage_id, target.id):
        return {"moved": False, "stage": cur.name if cur else None, "refused": None}
    plan = stage_move.plan_move(db, deal, target, cat)
    if not stage_move.may_move(plan):
        if plan.not_applicable:
            why = (f"Сделка не переведена: стадия «{target.name}» не относится к услуге "
                   "этой сделки — переведите вручную на карточке")
        elif not plan.allowed:
            why = stage_move.refusal_text(plan)
        else:
            why = "Сделка не переведена: у неё не выбрана воронка реализации — выберите на карточке сделки"
        return {"moved": False, "stage": cur.name if cur else None, "refused": why}
    stage_move.apply_move(db, deal, target, user, catalog=cat, reason=reason)
    return {"moved": True, "stage": target.name, "refused": None}


def rk_label(db: Session, campaign_id: int) -> str:
    """Подпись РК в журнале действий — ПОЛНЫМ кодом сделки (владелец 01.10.2026): «РК #45»
    человеку ничего не говорит, а по коду сделку находят поиском."""
    code = db.execute(text("SELECT d.code FROM ad_campaign a JOIN sales_deals d ON d.id = a.deal_id "
                           "WHERE a.id = :c"), {"c": campaign_id}).scalar()
    return f"РК {code}" if code else f"РК #{campaign_id}"


def publisher_name(db: Session, publisher_id) -> str:
    """Имя площадки для журнала — «площадка <имя>», а не безымянное «площадка»."""
    return db.execute(text("SELECT name FROM sales_publishers WHERE id = :i"),
                      {"i": publisher_id}).scalar() or ""


def _wake_quietly(db: Session, deal_id: int) -> dict:
    """Нацеливание после старта — уже ПОСЛЕ коммита статуса. Любой сбой здесь — итог
    словами, не 500: статус принят и DSP запущен, а 500 ещё и терял запись в журнал
    действий (аудит 01.10.2026, С-3)."""
    try:
        return wake_targeting(db, deal_id)
    except Exception as e:  # noqa: BLE001 — после коммита отказывать уже нечем
        db.rollback()      # сессия после SQL-ошибки сломана, а следом — журнал действий
        log.warning("нацеливание после старта сделки %s не разбудилось: %s", deal_id, e,
                    exc_info=True)
        return {"woken": 0, "errors": [f"нацеливание не разбудилось: {e}"]}


def wake_targeting(db: Session, deal_id: int) -> dict:
    """Нацеливание для скриншотов после старта РК (владелец 01.10.2026): «по умолчанию
    заводится в момент старта РК свежая — на 2 дня». Будим демо-кампанию нацеливания и
    запускаем копии креативов нацеливания у комплектов сделки с ЕРИД (`ensure_live`, тот
    же путь, что у кнопки). Только комплекты, где нацеливание вообще покажет.

    Запуск РК уже состоялся и сохранён: любой сбой здесь — итог словами, не отказ."""
    from app.dsp import targeting_creative as tc
    from app.dsp.client import MsError
    from app.launch_prep.models import LaunchPrepCreativeSet
    sets = (db.query(LaunchPrepCreativeSet)
            .filter(LaunchPrepCreativeSet.deal_id == deal_id,
                    LaunchPrepCreativeSet.erid.isnot(None)).all())
    blind = tc.blind_sets(db, [x.id for x in sets])
    woken, errors = 0, []
    for x in sets:
        if x.id in blind:
            continue
        try:
            if tc.ensure_live(db, x).get("active"):
                woken += 1
        except (tc.TargetingCreativeError, MsError) as e:
            errors.append(f"№{x.no}: {e}")
    return {"woken": woken, "errors": errors[:5]}


def erid_state(creatives) -> dict:
    """ЕРИД площадки по её живым креативам (владелец 30.09.2026): серый — ни у одного,
    жёлтый — у части (несколько креативов на площадке), зелёный — у всех."""
    live = [c for c in creatives if c.get("status") != CREATIVE_REJECTED]
    got = sum(1 for c in live if c.get("erid"))
    state = "none" if not got else "all" if got == len(live) else "part"
    return {"state": state, "got": got, "total": len(live)}


def screens_state(creatives) -> dict:
    """Скрины запуска площадки по её живым креативам (владелец 01.10.2026) — тем же
    правилом, что ЕРИД: серый — ни по одному, жёлтый — по части, зелёный — по всем."""
    from app.ad.flight import screens_tone
    live = [c for c in creatives if c.get("status") != CREATIVE_REJECTED]
    return screens_tone(sum(1 for c in live if c.get("screens_done_at")), len(live))


def dsp_uploaded(creatives) -> bool:
    """Выгружена ли площадка в DSP: хоть один креатив получил хеш DSP. Статус не
    фильтруем: креатив, отклонённый уже после выгрузки, в DSP всё равно заведён."""
    return any((c.get("ms_creative_xxhash") or "").strip() for c in creatives)


def button_states(rows: list, creatives: dict, pixels: dict, px: dict) -> dict:
    """Цвет кнопок «ПИКСЕЛЬ WR» и «В DSP» (владелец 30.09.2026):
    go — есть что сделать сейчас (зелёная), done — всё готовое уже сделано (жёлтая),
    idle — делать ещё нечего, ни один комплект не дошёл (серая).

    Готово к действию — ровно то, что пропустят сами кнопки: пиксель — площадке «ждёт
    запуска»/«запущен»/«пауза» с согласованным креативом с ЕРИД; выгрузка — площадке нашей
    DSP с таким креативом без хеша DSP и с пикселем, если он заказан свой."""
    from app.weborama.provision import ERID_CREATIVE_OK, READY_STATUSES
    own_px = px.get("needed") and px.get("mode") != "external"
    n = {"wr_go": 0, "wr_done": 0, "dsp_go": 0, "dsp_done": 0}
    for r in rows:
        live = [x for x in creatives.get(r["id"], []) if x.get("status") != CREATIVE_REJECTED]
        ready = [x for x in live if x.get("status") in ERID_CREATIVE_OK and x.get("erid")]
        stored, px_val = pixels.get(r["id"], (None, None))
        has_px = bool(px_val)
        # Прямые площадки исключены только из Weborama (как в `provision`), не из DSP.
        # Статус — сохранённый, тот же, по которому отбирает заведение пикселя.
        if own_px and not r.get("is_direct"):
            if has_px:
                n["wr_done"] += 1
            elif ready and stored in READY_STATUSES:
                n["wr_go"] += 1
        if r.get("ext_mode") == "external":
            continue
        if dsp_uploaded(creatives.get(r["id"], [])):
            n["dsp_done"] += 1
        if (not own_px or has_px) and any(not (x.get("ms_creative_xxhash") or "").strip()
                                          for x in ready):
            n["dsp_go"] += 1

    def tone(go, done):
        return "go" if go else "done" if done else "idle"
    return {"weborama": {"state": tone(n["wr_go"], n["wr_done"]) if own_px else "off",
                         "go": n["wr_go"], "done": n["wr_done"],
                         "external": bool(px.get("needed") and px.get("mode") == "external")},
            "dsp": {"state": tone(n["dsp_go"], n["dsp_done"]),
                    "go": n["dsp_go"], "done": n["dsp_done"]}}


DSP_NOT_UPLOADED = ("Площадка ещё не выгружена в DSP — сначала «В DSP», потом запуск и "
                    "пауза: иначе кнопка меняет статус у нас, а в DSP нечего включать")


def _creatives_of(db: Session, campaign_id: int) -> dict:
    """Креативы РК по площадкам: {placement_id: [строки]}.

    Имя человеческое берётся у КОМПЛЕКТА строки (`launch_prep_creative_set.title`), полный
    индекс — из `ms_title` (`<код сделки>-<код площадки>-cr<№>`). Два разных имени, и оба
    нужны: первое человек дал сам, второе видно в кабинете DSP.
    """
    rows = db.execute(text("""
        SELECT c.id, c.placement_id, c.creative_no, c.status, c.ms_title, c.erid,
               c.ms_creative_xxhash, c.root_set_id, c.pair_id, pr.set_id,
               s.title AS name, s.no AS set_no,
               pr.code AS pair_code,
               cur.no AS version_no, cur.origin,
               CASE WHEN c.status <> :rej THEN st.plan_show END AS fixed,
               c.screens_done_at, u.name AS screens_by
          FROM ad_campaign_creative c
          LEFT JOIN users u ON u.id = c.screens_done_by
          LEFT JOIN launch_prep_creative_set s ON s.id = c.root_set_id
          LEFT JOIN launch_prep_pair pr ON pr.id = c.pair_id
          LEFT JOIN launch_prep_creative_set cur ON cur.id = pr.set_id
          LEFT JOIN launch_prep_set_target st
                 ON st.set_id = pr.set_id AND st.target_id = pr.target_id
         WHERE c.campaign_id = :c
         ORDER BY c.placement_id, c.creative_no
    """), {"c": campaign_id, "rej": CREATIVE_REJECTED}).mappings().all()
    out: dict = {}
    for r in rows:
        out.setdefault(r["placement_id"], []).append(dict(r))
    return out


# Словари площадки и креатива различаются одним словом: согласованное состояние у
# площадки зовётся «ждёт запуска», у креатива — «согласован». Перевод нужен там, где
# статус площадки собирается из статусов её креативов.
# Перевод шкалы живёт в `ad/flight` — им пользуется и синк. Имя здесь оставлено,
# чтобы не править два десятка мест вызова.
_as_placement_scale = as_placement_scale


def _placements_of(db: Session, campaign_ids: List[int]) -> dict:
    """Площадки всех видимых РК одним запросом — для долей, виновников и счётчиков.

    Раскрывать каждую РК ради этого нельзя: виджет «площадки-виновники» отвечает на
    вопрос «кто тянет вниз ВЕСЬ портфель», и по одной РК он не собирается вовсе.
    """
    if not campaign_ids:
        return {}
    rows = db.execute(text("""
        SELECT p.campaign_id, p.id, p.publisher_id, p.status, p.weight,
               pub.code, pub.domain, pub.name AS publisher,
               (SELECT sum(s.shows) FROM ad_campaign_stat s
                 WHERE s.placement_id = p.id AND s.source = ANY(:src)) AS fact,
               """ + build.PLACEMENT_FIXED_SQL + """ AS fixed
          FROM ad_campaign_placement p
          JOIN sales_publishers pub ON pub.id = p.publisher_id
         WHERE p.campaign_id = ANY(:i)
    """), {"i": campaign_ids, "src": fact_sources()}).mappings().all()
    out: dict = {}
    for r in rows:
        out.setdefault(r["campaign_id"], []).append(dict(r))
    return out


def _stat_by_day(db: Session, campaign_ids: List[int]) -> dict:
    """Суточный факт по РК: {campaign_id: {дата: (показы, клики)}}.

    Нужен «стене дней»: она рисует клетку на КАЖДЫЙ день флайта каждой РК, то есть
    данные требуются сразу по всем видимым, а не только по раскрытой.
    """
    if not campaign_ids:
        return {}
    rows = db.execute(text(
        "SELECT campaign_id, date, sum(shows) AS shows, sum(clicks) AS clicks "
        "FROM ad_campaign_stat WHERE campaign_id = ANY(:i) AND source = ANY(:src) "
        "GROUP BY campaign_id, date"),
        {"i": campaign_ids, "src": fact_sources()}).mappings().all()
    out: dict = {}
    for r in rows:
        out.setdefault(r["campaign_id"], {})[r["date"]] = (r["shows"], r["clicks"])
    return out


# Сколько строк «стены дней» отдаём. Ограничение НЕ косметическое: строка на РК при 57
# кампаниях даёт стену в 57 рядов, где взгляд не находит ничего. Сортировка — по
# выполнению снизу вверх: сверху то, что хуже всего идёт.
#
# Видно из них столько, сколько влезает в окно виджета — оно одной высоты с соседним
# (владелец 05.09.2026), сегодня это восемнадцать рядов, — остальные скроллом. Потолок
# ответа выше видимого ровно затем, чтобы скроллу было что показывать; сама высота живёт
# во фронте, потому что это оформление, а не правило данных.
WALL_LIMIT = 30


def _day_wall(rows: List[dict], stat: dict, today: date) -> List[dict]:
    """Стена дней: строка на РК, клетка на день флайта, отношение факта к нужному темпу.

    Цвет клетки считает ЭКРАН — здесь только отношение, потому что пороги (0.95 / 0.8)
    это оформление, а не бухгалтерия. Клетка без данных отдаётся как None и рисуется
    серым: «ещё не отчитано» и «отчитано ноль» — разные утверждения.

    В клетке лежат план, показы и клики — те же четыре числа, что в карточке дня у
    графика динамики (владелец 13.09.2026: «при наведении на стену дней выводи такую же
    подсказку»). Нового запроса это не стоило: `_stat_by_day` и так забирает показы
    ВМЕСТЕ с кликами, а план на день уже посчитан здесь же для отношения — в ответ
    просто не клали. `product` рядом с кодом нужен подписи карточки, чтобы она читалась
    одинаково в обоих местах.
    """
    out = []
    for r in rows:
        fl = flight_of(r["date_start"], r["date_end"], today)
        if not fl or not r["plan_show"]:
            continue
        per_day = r["plan_show"] / fl.length
        by_day = stat.get(r["id"], {})
        cells = []
        for i in range(fl.length):
            d = fl.date_from + timedelta(days=i)
            shows, clicks = by_day.get(d, (None, None))
            cells.append({
                "date": d,
                "plan": round(per_day),
                "shows": shows,
                "clicks": clicks,
                "ratio": round(shows / per_day, 3) if (shows is not None and per_day) else None,
                "ahead": d > today,
            })
        out.append({"id": r["id"], "deal_code": r["deal_code"], "cells": cells,
                    "product": r.get("product"), "done_pct": r["done_pct"]})
    out.sort(key=lambda x: (x["done_pct"] is None, x["done_pct"] or 0))
    return out[:WALL_LIMIT]


# Сколько пипсов рисуем в строке. Больше восьми в колонке 110 px сливаются в полосу,
# а точное соотношение всё равно читается по счётчику «крутит N из M» рядом.
PIPS_MAX = 8


def _pips(rows: List[dict], limit: int = PIPS_MAX) -> List[dict]:
    """Пипс на площадку: состояние + ЕЁ СОБСТВЕННОЕ выполнение.

    До 05.09.2026 пипсы отвечали на вопрос «включено ли», а полоса рядом — «как идёт»,
    и это были два разных языка про один процесс (владелец: «крутит» и «идёт по темпу»
    — частное и общее одного). Теперь пипс красится тем же правилом, что полоса, только
    по своей площадке: строка читается на двух этажах одинаково, и видно не просто
    «17 из 19 крутят», а на каких именно площадках собрался недокрут РК.

    Берём первые по весу: они несут основной объём, и если проседает одна из них —
    проседает вся РК. `pct` отдаём числом, цвет считает экран той же функцией, что для
    полосы: два набора порогов разъехались бы при первой правке.
    """
    out = []
    for p in sorted(rows, key=lambda x: -(x.get("weight") or 0))[:limit]:
        st = p.get("status")
        out.append({
            "s": ("run" if st in PLACEMENT_RUNNING
                  else "ready" if st == PLACEMENT_READY else "idle"),
            "pct": p.get("done_pct"),
            "domain": p.get("domain"),
        })
    return out


def _queue_badge(db: Session) -> dict:
    """Креативы на проверке: сколько ждёт и сколько просрочено.

    Данные соседнего экрана (владелец 04.09.2026: показывать здесь и дать кнопку
    «Проверить»). Срочность считает ТА ЖЕ функция, что и очередь, — иначе на двух
    экранах одно и то же слово «просрочено» означало бы разное.
    """
    rows = db.execute(text("""
        SELECT r.asked_at, t.period_from, d.period_from AS deal_from, t.state
          FROM launch_prep_review r
          JOIN launch_prep_pair pr ON pr.id = r.pair_id
          JOIN launch_prep_creative_set cs ON cs.id = pr.set_id
          JOIN launch_prep_target t ON t.id = pr.target_id
          JOIN sales_deals d ON d.id = cs.deal_id
         WHERE r.kind = 'трафики' AND r.verdict IS NULL
    """)).mappings().all()
    today = date.today()
    overdue = 0
    for r in rows:
        v = urgency.evaluate(urgency.PairFacts(
            traffic_verdict=None,
            asked_at=timez.msk_date(r["asked_at"]),   # момент UTC → день по Москве
            period_from=r["period_from"] or r["deal_from"],
            is_dropped=(r["state"] == "отказ площадки"),
        ), today)
        if v.urgency == urgency.OVERDUE:
            overdue += 1
    return {"waiting": len(rows), "overdue": overdue}


def _scope_for(db: Session, user: User, scope: Optional[str]):
    """«Чьи РК показывать» → (rep_id для фильтра, как это называется на экране).

    Умолчание считает СЕРВЕР, а не фронт: рядовому трафику открывается «свои», мастеру —
    «все» (владелец 04.09.2026). Иначе экран сперва грузит одно, потом узнаёт роль и
    перегружает другое, и первый кадр врёт.

    Фильтр приходит УЧЁТКОЙ, а не профилем ответственного. Причина ровно та, из-за
    которой список кандидатов в трафики был пустым: `sales_reps` пополняется только
    назначением, и человек без профиля в выборе по профилям просто отсутствует
    (см. `app/sales/reps.py`). Учётка без профиля никуда не назначена — и честно даёт
    пустой список (`-1`), а не молча показывает чужие РК.

    Видимость это НЕ ограничивает: РК открывается по прямой ссылке любому, у кого есть
    право (`_campaign_in_scope` зовётся с `all_reps=True`). Здесь только фильтр экрана.
    """
    if not scope:
        scope = "all" if _is_master(user) else "mine"
    # «Не распределено» фильтрует не по человеку, а по ЕГО ОТСУТСТВИЮ, поэтому профиля
    # здесь нет и быть не может: фильтр накладывается в самом реестре.
    if scope in ("all", "none"):
        return None, scope
    uid = user.id if scope == "mine" else (int(scope) if str(scope).isdigit() else None)
    if uid is None:
        return None, "all"
    rep = db.query(SalesRep.id).filter(SalesRep.user_id == uid).first()
    return (rep[0] if rep else -1), ("mine" if uid == user.id else str(uid))


# ── реестр ────────────────────────────────────────────────────────────────

@router.get("/dashboard")
def dashboard(scope: Optional[str] = None,
              db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Реестр РК в области видимости + сводка. Синк РК делает отдельная ручка `/sync`."""
    rep_id, scope = _scope_for(db, user, scope)
    q = (db.query(AdCampaign, SalesDeal)
         .join(SalesDeal, SalesDeal.id == AdCampaign.deal_id))
    q = _apply_scope(q, db, user, rep_id)
    if scope == "none":
        # Разбор невыбранного: РК, на которых ответственный не стоит вовсе. Сегодня это
        # почти весь список (замерено 04.09.2026: 0 назначений на 57 РК), и именно
        # поэтому пункт нужен — иначе непонятно, что «Мои» пусты не по ошибке.
        q = q.filter(SalesDeal.traffic_manager_id.is_(None))
    pairs = q.order_by(AdCampaign.month.desc().nullslast(), SalesDeal.code).all()

    ids = [c.id for c, _ in pairs]
    facts = _facts(db, ids)
    # План, темп и стена дней — по дате среза, а не по сегодня: факт приходит за вчера
    # (владелец 02.10.2026, `stat_sources.fact_as_of`).
    today = fact_as_of(db)
    stages = dict(db.execute(text("SELECT id, name FROM sales_stages")).all())
    # Бренд — для поиска в реестре (владелец 30.09.2026: номер, название, бренд, услуга).
    brands = dict(db.execute(text("SELECT id, name FROM sales_brands")).all())
    # Услуга и её поверхность — тем же общим контекстом, что в реестре сделок и в
    # очереди аккаунта: трафик подбирает площадки по паре «услуга + поверхность», и
    # WEB-кампания от APP-кампании в списке иначе неотличима.
    row_ctx = load_row_context(db, [d.id for _c, d in pairs])
    # Имена ответственных трафиков — ОДНИМ запросом на весь экран, а не по строке:
    # реестр показывает 57 РК, и запрос на каждую превратил бы его в шестьдесят
    # обращений. Тот же приём, что у площадок и креативов выше.
    traf_ids = {d.traffic_manager_id for _c, d in pairs if d.traffic_manager_id}
    traf_name = dict(db.query(SalesRep.id, SalesRep.name)
                     .filter(SalesRep.id.in_(traf_ids)).all()) if traf_ids else {}

    # Площадки всех видимых РК — сразу и для счётчиков в строке, и для виновников.
    # Статус собирается так же, как в расхлопе: конвейер поверх сохранённого.
    places = _placements_of(db, ids)
    cr_all = _creatives_all(db, ids)
    uploaded = _uploaded_placements(db, ids)
    # Покрытие внешними системами — ОДНИМ расчётом на весь экран (четыре запроса на любое
    # число РК). По одной РК за раз это было бы под двести запросов на реестре из 57.
    ext_totals = ext_mod.totals_by_campaign(db, ids)
    culprit_rows = []
    dist_by_camp: dict = {}
    cap = balance.share_cap(db)   # один раз на запрос, а не на каждую РК
    manual = balance.manual_scopes(db)
    surf_of = build.surfaces_by_deal(db, {c.deal_id for c, _d in pairs})
    for c, d in pairs:
        pls = places.get(c.id, [])
        by_pl = cr_all.get(c.id, {})
        for p in pls:
            # Статус площадки собирается ИЗ ЕЁ КРЕАТИВОВ — ровно тем же выражением, что
            # в расхлопе. До 04.09.2026 реестр считал его от ПАР, а расхлоп от креативов,
            # и один и тот же ряд мог показывать в двух местах разное. Пары остались
            # источником для самих креативов (`build.sync_creatives`), но не для площадки.
            p["status"] = effective_status(p["status"], best_chain_status(
                _as_placement_scale(x) for x in by_pl.get(p["id"], [])))
        fl = flight_of(c.date_start, c.date_end, today)
        # Одно распределение на РК — и виновникам, и пипсам строки. Считать его дважды
        # значило бы завести два ответа на вопрос «сколько эта площадка недокрутила».
        balance.mark_capless(db, pls, surf_of.get(c.deal_id, []), manual)
        dist_by_camp[c.id] = distribute(c.plan_show, facts.get(c.id, {}).get("shows"),
                                        fl, pls, cap=cap)["rows"]
        culprit_rows += dist_by_camp[c.id]

    # Креативы с материалом по сделкам страницы — для «↓ креативы» в раскрытии РК
    # (владелец 27.09.2026): одним запросом, тем же счётом, что и документы сделки.
    from app.routers.sales_dashboard import creatives_ready_by_deal
    cr_ready = creatives_ready_by_deal(db, {d.id for _, d in pairs})
    # Объёмы по площадкам против плана РК — пачкой; план берём у самой РК (его и
    # раскладывают), чтобы строка не спорила с раскрытием (владелец 27.09.2026).
    vol_by_deal = volumes.volumes_by_deal(db, {d.id for _, d in pairs})
    # Расхождение с Weborama за период — для метки «Большое расхождение с WR» в строке
    # РК (владелец 27.09.2026). Показы верификатора и цели сделок — пачкой.
    ver_all = _verifier(db, [c.id for c, _ in pairs], until=today)
    goals_by_deal = build.deal_goals_many(db, {d.id for _, d in pairs})
    rows = []
    for c, d in pairs:
        f = facts.get(c.id, {})
        pls = places.get(c.id, [])
        fc = progress(c.plan_show, f.get("shows"), c.date_start, c.date_end, today, now=date.today())
        by_pl = cr_all.get(c.id, {})
        chain_st = campaign_chain_status(
            has_plan=bool(c.plan_show), placements=len(pls),
            # то же правило, что `_chain_of`: в счёт — только выгруженные в нашу DSP
            running=sum(1 for p in pls if p["status"] in PLACEMENT_RUNNING
                        and p["id"] in uploaded),
            can_start=any(can_start_placement(by_pl.get(p["id"], [])) for p in pls))
        rows.append({
            "id": c.id, "deal_id": d.id, "deal_code": d.code, "deal_title": d.title,
            "creatives_ready": cr_ready.get(d.id, 0),
            "volumes": volumes.evaluate(c.plan_show, vol_by_deal.get(d.id, {})),
            # Сверяются только площадки, которые Weborama мерила (`comparable`).
            "wr_mismatch": _wr_mismatch(*comparable(
                f.get("shows"),
                {r["id"]: r.get("fact_shows") or 0 for r in dist_by_camp.get(c.id, [])},
                ver_all.get(c.id))[:2], goals_by_deal.get(d.id)),
            # Ответственный трафик — прямо в строке: по нему подсвечивается
            # нераспределённое, и он же объясняет, почему РК видно в «Моих».
            "traffic": traf_name.get(d.traffic_manager_id),
            "traffic_rep_id": d.traffic_manager_id,
            "product": d.product, "inventory": row_ctx.inventory(d.id, d.product),
            "brand": brands.get(d.brand_id),
            # Цвет услуги — из справочника, тем же контекстом, что в реестре сделок и в
            # очереди аккаунта. Маркер перед услугой опознаётся быстрее слова, и цвет у
            # одной услуги обязан совпадать на всех экранах.
            "product_color": row_ctx.color(d.product),
            "stage": stages.get(d.our_stage_id), "month": c.month,
            "status": effective_campaign_status(c.status, chain_st),
            "date_start": c.date_start, "date_end": c.date_end,
            "plan_show": c.plan_show, "plan_budget": c.plan_budget,
            "fact_shows": f.get("shows"), "fact_clicks": f.get("clicks"),
            "ms_campaign_xxhash": c.ms_campaign_xxhash,
            # Кнопки запуска/остановки заперты до выкладки в DSP — причина словами.
            "dsp_block": dsp_block_reason(ext_totals.get(c.id), c.ms_campaign_xxhash),
            "launch_hint": launch_hint(
                dsp_block_reason(ext_totals.get(c.id), c.ms_campaign_xxhash),
                volumes.evaluate(c.plan_show, vol_by_deal.get(d.id, {})),
                bool(c.ms_campaign_xxhash and c.status in build.CAMPAIGN_CLOSED),
                ready=sum(1 for p in pls if p["status"] == PLACEMENT_READY),
                running=sum(1 for p in pls if p["status"] in PLACEMENT_RUNNING),
                waiting=sum(1 for p in pls if p["status"] not in PLACEMENT_RUNNING
                            and p["status"] != PLACEMENT_READY and p["status"] != PLACEMENT_OFF)),
            # Покрытие внешними системами прямо в строке: серый — нет, жёлтый — не все,
            # зелёный — все (решение владельца 09.09.2026). Цвет считает экран, числа —
            # сервер, и оба берут их из одного расчёта.
            "external_totals": ext_totals.get(c.id),
            "placements": len(pls),
            "placements_on": sum(1 for p in pls if p["status"] in PLACEMENT_RUNNING),
            "placements_weighted": sum(1 for p in pls if p["weight"]),
            # Согласована, но ещё не запущена. Отдельно от «есть индекс»: до 04.09.2026
            # пипсы в строке красились по НАЛИЧИЮ ВЕСА, а легенда называла их «ждёт
            # согласования» — два разных факта под одним цветом.
            "placements_ready": sum(1 for p in pls if p["status"] == PLACEMENT_READY),
            # Сколько площадок ОТКЛЮЧЕНО. Нужно строке реестра, чтобы спросить про них
            # при перезапуске РК, не раскрывая расхлоп ради одного числа.
            "placements_off": sum(1 for p in pls if p["status"] == PLACEMENT_OFF),
            # Пипсы — по площадке каждый, с её выполнением. Цвет считает экран.
            "pips": _pips(dist_by_camp.get(c.id, [])),
            # Статус РК СЧИТАЕТСЯ, а не читается из поля: «запущена» это факт работы
            # (хоть одна площадка крутит), «готова» — что всё для запуска есть. Ручные
            # решения (пауза, стоп, окончена, архив) расчёт перекрывают.
            "status_chain": chain_st,
            **fc,
        })

    # ── KPI. Считаются ОТ ВИДИМОГО СРЕЗА, а не от всей базы: иначе шапка спорит с
    # таблицей под ней, и человек не знает, какому числу верить.
    #
    # План и факт — по ЗАПУЩЕННЫМ РК (владелец 04.09.2026), то есть по тем же, что
    # считает плитка «РК в работе». Портфель, сложенный по всему видимому, отвечал на
    # вопрос, которого никто не задаёт: в него входили и РК будущих месяцев, и те, что
    # ещё собирают, — и «выполнение» получалось заведомо низким, а с ним и темп. Здесь
    # нужно «сколько мы должны открутить в том, что уже крутится».
    #
    # «Пауза» из счёта НЕ выпадает: приостановка не отменяет обязательство, и суточный
    # план по ней сохраняется — то же правило, что у площадки на паузе.
    live = [r for r in rows if r["status"] in RUNNING]
    plan_sum = sum(r["plan_show"] or 0 for r in live)
    fact_rows = [r for r in live if r["fact_shows"] is not None]
    fact_sum = sum(r["fact_shows"] for r in fact_rows)
    with_plan = [r for r in live if r["plan_show"]]
    # Ожидаемая доля по портфелю — доли флайтов, взвешенные планом. Отвечает на вопрос
    # «а сколько вообще должно было открутиться к этому дню».
    avg_pace = (sum((r["pace"] or 0) * r["plan_show"] for r in with_plan) / plan_sum
                if plan_sum else None)
    attention = [r for r in rows
                 if not r["plan_show"] or not r["placements"] or (r["under"] or 0) > 0]

    return {
        "rows": rows,
        # Источники факта — на экран. Всё, что не боевой коннектор, обязано быть
        # подписано: «19 из 19 крутят» на выдуманных числах читается как настоящее.
        "fact_sources": _fact_sources(db, ids),
        "fact_last_ingest": _fact_last_ingest(db, ids),
        # `today` — дата среза (последний день с фактом DSP), подписью «данные на»;
        # `as_of_stale` — срез старше вчерашнего: съём встал, экран подсвечивает это.
        "today": today,
        "as_of": today,
        "as_of_stale": is_stale(today),
        "kpi": {
            "campaigns": len(rows),
            "running": sum(1 for r in rows if r["status"] in RUNNING),
            "plan_show": plan_sum,
            "fact_shows": fact_sum,
            # Сколько РК стоит за планом и фактом — чтобы подпись плитки не выдумывалась
            # на фронте и не разошлась с числом.
            "plan_campaigns": len(live),
            "done_pct": round(fact_sum / plan_sum * 100, 1) if plan_sum else None,
            "avg_pace": round(avg_pace, 4) if avg_pace is not None else None,
            "placements_on": sum(r["placements_on"] for r in rows),
            "placements": sum(r["placements"] for r in rows),
            "attention": len(attention),
            # Дыры в данных — отдельным числом, а не внутри «требует внимания»: без плана
            # это дефект медиаплана, а не недокрут, и чинится он в другом месте.
            "no_plan": sum(1 for r in rows if not r["plan_show"]),
            "no_stat": sum(1 for r in rows if r["plan_show"] and r["fact_shows"] is None),
            "queue": _queue_badge(db),
        },
        "culprits": culprits(culprit_rows),
        "wall": _day_wall(rows, _stat_by_day(db, ids), today),
        "is_master": _is_master(user),
        # Кнопка «Обновить данные в DSP» — Администратор и «Админ Трафик» (02.10.2026).
        "can_dsp_refresh": dsp_refresh.may_refresh(user),
        # Список для переключателя — ВСЕ активные учётки трафика, с пометкой мастера.
        # Мастера идут первыми (сортировка в `staff_users`), звёздочку рисует фронт.
        "reps": staff_users(db, "traffic"),
        "scope": scope,
        # Себя фронт выкидывает из списка: «Мои» — это уже я, и вторая строка с моим
        # именем означала бы, что это разные фильтры.
        "my_user_id": user.id,
        "statuses": list(CAMPAIGN_STATUSES),
    }


@router.get("/campaign/{campaign_id}")
def campaign(campaign_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Расхлоп РК: площадки с долей, планом и фактом + динамика показов по дням.

    Статус площадки СОБИРАЕТСЯ, а не просто читается: первые три значения словаря
    (`у трафика` / `у площадки` / `ждёт запуска`) — следствие конвейера согласования
    креативов, и человек их не выбирает. В базе живёт либо ручной статус трафика, либо
    засеянное «у трафика»; поверх него накладывается расчёт по вердиктам пары.
    """
    c, deal = _campaign_in_scope(db, campaign_id, user)

    pls = db.execute(text("""
        SELECT p.id, p.publisher_id, p.status, p.weight, p.bid, p.is_direct,
               p.ms_source_key, pub.name AS publisher, pub.code, pub.domain,
               (SELECT sum(s.shows) FROM ad_campaign_stat s
                 WHERE s.placement_id = p.id AND s.source = ANY(:src)) AS fact,
               (SELECT sum(s.clicks) FROM ad_campaign_stat s
                 WHERE s.placement_id = p.id AND s.source = ANY(:src)) AS fact_clicks,
               """ + build.PLACEMENT_FIXED_SQL + """ AS fixed
        FROM ad_campaign_placement p
        JOIN sales_publishers pub ON pub.id = p.publisher_id
        WHERE p.campaign_id = :c
        ORDER BY p.weight DESC NULLS LAST, lower(pub.name)
    """), {"c": campaign_id, "src": fact_sources()}).mappings().all()

    as_of = fact_as_of(db)
    fl = flight_of(c.date_start, c.date_end, as_of)
    fact_total = _facts(db, [c.id]).get(c.id, {}).get("shows")
    creatives = _creatives_of(db, c.id)

    # Режим площадки: наша DSP / внешняя / смешанная — по поверхностям в сделке (30.09.2026).
    from app.launch_prep.pub_rules import placement_modes
    modes = placement_modes(db, {(c.deal_id, p["publisher_id"]) for p in pls})
    prepared = []
    for p in pls:
        d = dict(p)
        m = modes.get((c.deal_id, p["publisher_id"])) or {}
        d["ext_mode"], d["ext_surfaces"] = m.get("mode"), m.get("external", [])
        mine = creatives.get(p["id"], [])
        # Статус площадки собирается из ЕЁ КРЕАТИВОВ — самый продвинутый из них
        # (владелец 04.09.2026: «площадка запущена только при хоть одном согласованном
        # креативе»). Ручной статус трафика перекрывает расчёт.
        d["status"] = effective_status(
            p["status"], best_chain_status(_as_placement_scale(x["status"]) for x in mine))
        d["can_start"] = can_start_placement(x["status"] for x in mine)
        d["creative_counts"] = creative_counts(mine)
        d["erid"] = erid_state(mine)
        d["screens"] = screens_state(mine)
        # Кнопки старт/пауза — только после выгрузки в DSP; внешняя площадка в нашу DSP
        # не идёт, у неё галочка, и запрет её не касается.
        d["dsp_uploaded"] = dsp_uploaded(mine)
        # Почему кнопка старта площадки заперта — тем же правилом, что у сервера (02.10.2026).
        d["start_why"] = start_block(db, c, None, mine, d["ext_mode"] or "dsp")
        prepared.append(d)
    balance.mark_capless(db, prepared, build.deal_plan(db, c.deal_id)["surfaces"])
    out = distribute(c.plan_show, fact_total, fl, prepared, cap=balance.share_cap(db))

    # Третий этаж: план площадки делится ПОРОВНУ между её работающими креативами.
    for row in out["rows"]:
        row["creatives"] = split_evenly(row.get("plan_show"), creatives.get(row["id"], []),
                                        hold=holds(fl))

    # Состояние во внешних системах — ТОЙ ЖЕ функцией, что на карточке сделки. Второй
    # расчёт разошёлся бы с первым, и спорить было бы нечем.
    ext = ext_mod.states_by_placement(db, c.id)
    for row in out["rows"]:
        row["external"] = ext.get(row["id"])

    chain_st = _chain_of(c, [(p["id"], p["status"]) for p in pls], creatives)
    pixels = {r[0]: (r[1], r[2]) for r in db.execute(text(
        "SELECT id, status, weborama_pixel FROM ad_campaign_placement WHERE campaign_id = :c"),
        {"c": c.id}).all()}

    return {
        "id": c.id, "status": effective_campaign_status(c.status, chain_st),
        "buttons": button_states(out["rows"], creatives, pixels, build.pixel_setup(db, c.deal_id)),
        "status_chain": chain_st, "plan_show": c.plan_show,
        "external_totals": ext_mod.totals(ext),
        "date_start": c.date_start, "date_end": c.date_end,
        "placements": out["rows"], "share_sum": out["share_sum"],
        "creative_manual": list(CREATIVE_MANUAL),
        "creative_statuses": list(CREATIVE_STATUSES),
        **progress(c.plan_show, fact_total, c.date_start, c.date_end, as_of, now=date.today()),
        # Словарь целиком + какие значения можно ВЫБРАТЬ: экран не должен предлагать
        # в поповере то, что ставит конвейер.
        "placement_statuses": list(PLACEMENT_STATUSES),
        "placement_manual": list(PLACEMENT_MANUAL),
        "deal_id": deal.id,
        "volumes": volumes.evaluate(c.plan_show, volumes.deal_volumes(db, deal.id)),
        "launch_hint": launch_hint(
            dsp_not_ready(db, c), volumes.evaluate(c.plan_show, volumes.deal_volumes(db, deal.id)),
            bool(c.ms_campaign_xxhash and c.status in build.CAMPAIGN_CLOSED),
            ready=sum(1 for r in out["rows"] if r.get("status") == PLACEMENT_READY),
            running=sum(1 for r in out["rows"] if r.get("status") in PLACEMENT_RUNNING),
            waiting=sum(1 for r in out["rows"] if r.get("start_why"))),
        "owners": _owners(db, deal, user),
        # KPI приёмки из медиаплана — рядом с фактом, чтобы трафик видел, к чему его
        # открутку будут принимать, не открывая карточку сделки (владелец 05.09.2026).
        "goals": build.deal_goals(db, deal.id),
        # «Цели и особенности РК» — то самое послание аккаунта трафику с карточки сделки.
        # Здесь оно ЧИТАЕТСЯ, а не правится: писал аккаунт, и правка из чужого экрана
        # означала бы, что задачу можно молча переписать за него.
        "traffic_brief": (deal.traffic_brief or "").strip(),
        # Шапка брифа медиаплана — вторая вкладка «Задач РК» (владелец 29.09.2026).
        "mp_brief": build.deal_mp_brief(db, deal.id),
    }


def _owners(db: Session, deal, user: User) -> dict:
    """Кто ведёт РК с нашей стороны: аккаунт и трафик.

    Оба лежат на СДЕЛКЕ, а не на кампании: кампания — это открутка одного медиаплана, а
    ответственные назначены на сделку целиком, и второй экземпляр назначения на кампании
    разошёлся бы с карточкой сделки при первой же замене.

    Имя берём из профиля ответственного (`sales_reps`), а не из учётки: назначение
    ссылается именно на профиль, и показать здесь другое имя значило бы показать не того
    человека, на кого записана работа.
    """
    def name(rep_id):
        if not rep_id:
            return None
        r = db.query(SalesRep).filter(SalesRep.id == rep_id).first()
        return r.name if r else None

    traf = (db.query(SalesRep).filter(SalesRep.id == deal.traffic_manager_id).first()
            if deal.traffic_manager_id else None)
    return {
        "account": name(deal.account_manager_id),
        "traffic": traf.name if traf else None,
        "traffic_user_id": traf.user_id if traf else None,
        # Менять трафика может только мастер (владелец 04.09.2026). Рядовому строка
        # показывается текстом: знать, на ком РК, нужно всем.
        "can_change_traffic": _is_master(user),
    }


class TrafficManagerIn(BaseModel):
    user_id: Optional[int] = None                 # None — снять назначение


@router.put("/campaign/{campaign_id}/traffic-manager")
def set_campaign_traffic(campaign_id: int, payload: TrafficManagerIn,
                         db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Сменить ответственного трафика прямо из расхлопа РК.

    Пишет НЕ сама: зовёт ту же ручку сборки, что и карточка сделки. Назначение заводит
    профиль под учёткой (`ensure_rep`), пишет журнал и снимается тем же способом — вторая
    реализация всего этого разъехалась бы с первой на первой же правке.

    Дашборд остаётся при своём праве (`traffic_dashboard:edit`), а внутри проверяется
    мастер: рядовой трафик кампании не передаёт.
    """
    from app.routers import launch_prep as lp

    _c, deal = _campaign_in_scope(db, campaign_id, user)
    if not _is_master(user):
        raise HTTPException(403, "Сменить ответственного может мастер трафика")
    return lp.set_traffic_manager(deal.id, lp.TrafficManagerIn(user_id=payload.user_id),
                                  db, user)


@router.get("/campaign/{campaign_id}/stat")
def campaign_stat(campaign_id: int, grain: str = "day",
                  date_from: Optional[date] = None, date_to: Optional[date] = None,
                  db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Динамика показов: столбцы «план против факта» с пересчётом плана на остаток.

    Отдельной ручкой, а не полем расхлопа: гранулярность и интервал переключают часто,
    и тянуть ради этого заново список площадок с их долями незачем.

    Интервал КЛИПУЕТСЯ К ФЛАЙТУ внутри ядра — столбцов не может быть больше, чем дней
    в РК. Пришли даты вне флайта — вернётся его пересечение с ними, а не пустота:
    человек выбрал месяц, а РК шла две недели, и показать надо эти две недели.
    """
    if grain not in GRAIN_DAYS:
        raise HTTPException(400, f"Гранулярность бывает {tuple(GRAIN_DAYS)}")
    c, _deal = _campaign_in_scope(db, campaign_id, user)
    by_day = _stat_by_day(db, [c.id]).get(c.id, {})
    fact = _facts(db, [c.id]).get(c.id, {}).get("shows")
    today = fact_as_of(db)    # дата среза: «день» сводки — последний отчитанный
    # Наш факт режется тем же срезом, что WR: ручная правка или демо позже среза сделали
    # бы сверку несимметричной с другой стороны (ревью 02.10.2026).
    by_day = {d: v for d, v in by_day.items() if d <= today}
    fl = flight_of(c.date_start, c.date_end, today)
    out = daily_buckets(c.plan_show, fact, fl, by_day, grain=grain,
                        date_from=date_from, date_to=date_to, today=today)
    if out is None:
        # Ни плана, ни дат — рисовать нечего, и это не ошибка, а состояние экрана.
        return {"buckets": [], "grain": grain, "need_per_day": None,
                "days_left": None, "speed": None, "totals": None}

    # Сводка под графиком: «сегодня» и «за период». Клики отдаются вместе с показами —
    # CTR считается от них, и второй запрос ради него был бы лишним.
    t_shows, t_clicks = by_day.get(today, (0, 0))
    all_shows = sum(v[0] or 0 for v in by_day.values())
    all_clicks = sum(v[1] or 0 for v in by_day.values())
    out["totals"] = {
        "as_of": today,
        "today": {"shows": t_shows, "clicks": t_clicks,
                  "ctr": round(t_clicks / t_shows * 100, 2) if t_shows else None},
        "period": {"shows": all_shows, "clicks": all_clicks,
                   "ctr": round(all_clicks / all_shows * 100, 2) if all_shows else None},
    }
    # Weborama рядом с фактом: «факт | WR» и строка расхождения с цветом (владелец
    # 27.09.2026). Верификатор в факт не входит никогда — он только сверка. Нет его
    # данных — поле пустое, и экран пишет прочерк, а не ноль.
    #
    # Сверяется СОПОСТАВИМОЕ (`stat_sources.comparable`, ревью 27.09.2026): мерила
    # Weborama площадки — сравниваются только они, и по дням тоже; замер лишь по РК
    # целиком — вся РК. Ручной итог за период (`weborama_manual`) — одно число на весь
    # период, датированное его концом: в итог «за период» входит, в дни и «сегодня» нет.
    ver_rows = db.execute(text(
        "SELECT date, placement_id, source, sum(shows) AS shows, sum(clicks) AS clicks "
        "FROM ad_campaign_stat WHERE campaign_id = :c AND source = ANY(:src) "
        "AND (date <= :u OR source = 'weborama_manual') "
        "GROUP BY date, placement_id, source"),
        {"c": c.id, "src": list(VERIFIER), "u": today}).mappings().all()
    own_rows = db.execute(text(
        "SELECT date, placement_id, sum(shows) AS shows FROM ad_campaign_stat "
        "WHERE campaign_id = :c AND source = ANY(:src) AND placement_id IS NOT NULL "
        "AND date <= :u GROUP BY date, placement_id"),
        {"c": c.id, "src": fact_sources(), "u": today}).mappings().all()
    own_by_pl: dict = {}
    for r in own_rows:
        own_by_pl[r["placement_id"]] = own_by_pl.get(r["placement_id"], 0) + (r["shows"] or 0)
    for (pid,) in db.execute(text("SELECT id FROM ad_campaign_placement WHERE campaign_id = :c"),
                             {"c": c.id}).all():
        own_by_pl.setdefault(pid, 0)
    ver = _verifier(db, [c.id], until=today).get(c.id)
    own_cmp, wr_cmp, n_covered = comparable(all_shows, own_by_pl, ver)
    covered = ({p for p in (ver or {}).get("by_placement", {}) if own_by_pl.get(p)}
               if n_covered else set())

    # По дням: {дата: (наш, WR показы, WR клики)} — тем же правилом, что итог.
    daily: dict = {}
    if covered:
        for r in own_rows:
            if r["placement_id"] in covered:
                o, w, k = daily.get(r["date"], (0, 0, 0))
                daily[r["date"]] = (o + (r["shows"] or 0), w, k)
        for r in ver_rows:
            if r["placement_id"] in covered:
                o, w, k = daily.get(r["date"], (0, 0, 0))
                daily[r["date"]] = (o, w + (r["shows"] or 0), k + (r["clicks"] or 0))
    else:
        for r in ver_rows:
            if r["placement_id"] is None and r["source"] != "weborama_manual":
                o, w, k = daily.get(r["date"], (by_day.get(r["date"], (0, 0))[0] or 0, 0, 0))
                daily[r["date"]] = (o, w + (r["shows"] or 0), k + (r["clicks"] or 0))
    daily = {d: v for d, v in daily.items() if v[1]}

    limit = goal_limit(build.deal_goals(db, _deal.id))

    def _mm(own, wr):
        pct = mismatch_pct(own, wr)
        return {"pct": pct, **mismatch_level(pct, limit)} if pct is not None else None

    # Тот же WR — в каждый столбец «Динамики показов»: карточка дня показывает его рядом
    # с фактом (владелец 27.09.2026). Нет данных за даты столбца — поле пустое.
    if daily:
        from datetime import timedelta as _td
        for b in out["buckets"]:
            days = [b["date_from"] + _td(days=i) for i in range(b["days"])]
            got = [daily[d] for d in days if d in daily]
            if got and b["days_past"]:
                b["wr_shows"], b["wr_clicks"] = sum(g[1] for g in got), sum(g[2] for g in got)
                b["mismatch"] = _mm(sum(g[0] for g in got), b["wr_shows"])

    wr_period_clicks = (sum(r["clicks"] or 0 for r in ver_rows
                            if not covered or r["placement_id"] in covered)
                        if wr_cmp is not None else None)
    t = daily.get(today)
    for key, own, (w_shows, w_clicks) in (
            ("today", t[0] if t else None, (t[1], t[2]) if t else (None, None)),
            ("period", own_cmp, (wr_cmp, wr_period_clicks))):
        out["totals"][key]["wr"] = {
            "shows": w_shows, "clicks": w_clicks,
            "ctr": round(w_clicks / w_shows * 100, 2) if w_shows else None}
        out["totals"][key]["mismatch"] = _mm(own, w_shows)
    # Охват сверки — «по N из M площадок»: без него процент читается приговором всей РК.
    out["totals"]["wr_placements"] = n_covered
    out["totals"]["wr_outside"] = wr_outside(own_by_pl, ver) or None
    out["totals"]["placements"] = len(own_by_pl)
    return out


# ── управление ────────────────────────────────────────────────────────────

@router.post("/sync")
def sync(db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Догоняет РК по сделкам и добавляет новых кандидатов-площадок (этап 3a)."""
    res = build.sync_all(db)
    log_action(db, user, "traffic_dashboard_sync", "sales_deal", None,
               f"РК создано {res['created']}, площадок добавлено {res['placements_added']}")
    return res


# Что происходит с площадками, когда решение принято НАД РК. Каскад включён владельцем
# 04.09.2026: «Стоп» по РК, не трогающий площадок, оставлял строку, которая сама себе
# противоречит — статус «остановлена» и рядом «крутит 19 из 19». Хуже того, на стенде
# это была правда: площадки действительно оставались запущенными, и после подключения
# коннектора остановленная РК продолжала бы тратить.
#
# Значение каскада берётся из смысла статуса площадки, а не назначается заново:
#   · пауза     → «пауза»: открутка приостановлена, доля из суточного плана НЕ уходит;
#   · остановлена / окончена / архив → «завершена»: немедленная остановка и выход из
#     распределения на следующие сутки.
# Обратный ход у «запущена» уже был и остаётся отдельным: он спрашивает разрешения,
# потому что поднимать чужое отключение молча нельзя.
CASCADE_TO_PLACEMENT = {
    "пауза": "пауза",
    "остановлена": "завершена",
    "окончена": "завершена",
    "архив": "завершена",
}


def _cascade_placements(db: Session, campaign_id: int, campaign_status: str) -> int:
    """Спустить решение по РК на её площадки. → сколько площадок изменилось.

    Трогаем только те, что РАБОТАЮТ («запущен»/«пауза»): площадка в цепочке согласования
    («у трафика», «у площадки», «ждёт запуска») ещё не начинала, и проставить ей
    «завершена» значило бы соврать, что её выключили. Уже завершённую не трогаем тоже —
    повторная запись того же значения ничего не меняет, но попадает в журнал.
    """
    target = CASCADE_TO_PLACEMENT.get(campaign_status)
    if not target:
        return 0
    n = 0
    for p in db.query(AdCampaignPlacement).filter_by(campaign_id=campaign_id).all():
        if p.status in PLACEMENT_MANUAL and p.status not in (target, PLACEMENT_OFF):
            was, p.status = p.status, target
            if was == "запущен":
                build.unmark_target_placed(db, p)
            n += 1
    if n:
        # Доли считаются по крутящим: снятая площадка отдаёт объём остальным, а при
        # «пауза» доля сохраняется — обе ветки живут в `flight.distribute`, здесь только
        # повод пересчитать.
        build.recompute_shares(db, campaign_id)
    return n


DSP_NOT_READY = ("РК ещё не выгружена в DSP — сначала «В DSP». Запуск и остановка "
                 "управляют кампанией в DSP; до выгрузки им нечем управлять")


def dsp_block_reason(totals: Optional[dict], ms_campaign_xxhash) -> Optional[str]:
    """Почему запуск/остановка РК пока бессмысленны, или None (владелец 29.09.2026).
    Одно правило на строку дашборда и на ручку статуса. DSP не нужна ни одной
    площадке (крутят сами) — не запираем."""
    dsp = (totals or {}).get("dsp") or {}
    if not dsp.get("need"):
        return None
    return None if (ms_campaign_xxhash and dsp.get("done")) else DSP_NOT_READY


def dsp_not_ready(db: Session, c) -> Optional[str]:
    return dsp_block_reason(ext_mod.totals(ext_mod.states_by_placement(db, c.id)), c.ms_campaign_xxhash)


@router.put("/campaign/{campaign_id}/status")
def set_campaign_status(campaign_id: int, payload: StatusIn,
                        db: Session = Depends(get_db), user: User = Depends(EDIT)):
    # «Запущена» здесь означает СНЯТЬ ручной оверрайд и вернуть РК под расчёт: сама по
    # себе она запущенной от этого не станет — для этого должна крутить хоть одна
    # площадка. Поэтому список допустимого шире ручного ровно на это одно значение.
    if payload.status not in CAMPAIGN_MANUAL + ("запущена",):
        raise HTTPException(400, f"Выбрать можно {CAMPAIGN_MANUAL + ('запущена',)}; "
                                 f"«ожидает сборки» и «готова» считаются сами")
    c, _deal = _campaign_in_scope(db, campaign_id, user)
    # Объёмы по площадкам больше плана РК — РК не запускаем (владелец 27.09.2026).
    if payload.status == "запущена":
        volumes.guard(db, _deal.id)
    # Из архива DSP назад не включается: вместо вечного «DSP не принял» — отказ сразу.
    if (c.ms_campaign_xxhash and c.status in build.CAMPAIGN_CLOSED
            and payload.status not in build.CAMPAIGN_CLOSED):
        raise HTTPException(400, "Кампания в DSP в архиве и снова не запускается — "
                                 "для продолжения нужна новая РК")
    # ЗАПУСК И ОСТАНОВКА — ПОСЛЕ ВЫКЛАДКИ В DSP (владелец 29.09.2026): до неё кнопки
    # меняли бы только нашу пометку, а в сети ничего бы не менялось — это вводит в
    # заблуждение. Исключение — РК, где DSP не нужна ни одной площадке (крутят сами).
    blocked = dsp_not_ready(db, c)
    if blocked and payload.status in ("запущена", "пауза", "остановлена"):
        raise HTTPException(409, blocked)
    old, c.status = c.status, payload.status

    raised = 0
    started = []        # площадки, запущенные ВПЕРВЫЕ — им письмо «стартовала» (В-4)
    if payload.status == "запущена" and payload.with_placements:
        # Поднимаем и отключённые, и стоящие на паузе — но только те, которым ЕСТЬ ЧЕМ
        # крутить: без согласованного креатива запуск запрещён тем же правилом, что и
        # поштучно (`can_start_placement`). Молча обойти его здесь значило бы завести
        # чёрный ход в обход собственной проверки.
        creatives = _creatives_of(db, c.id)
        from app.launch_prep import pub_rules
        pls = db.query(AdCampaignPlacement).filter_by(campaign_id=c.id).all()
        modes = pub_rules.placement_modes(db, {(c.deal_id, p.publisher_id) for p in pls})
        for p in pls:
            mode = (modes.get((c.deal_id, p.publisher_id)) or {}).get("mode")
            if (p.status in START_RAISABLE and not mass_start_skip(mode)
                    and not start_block(db, c, p, creatives.get(p.id, []), mode)):
                p.status = "запущен"
                if _mark_first_start(p):
                    started.append(p.id)
                build.mark_target_placed(db, p)
                raised += 1
        if raised:
            build.recompute_shares(db, c.id)

    stopped = _cascade_placements(db, c.id, payload.status)
    dsp_status = _dsp_follow(db, c)
    started = _keep_first_starts(db, started, dsp_status)
    # РК крутит — сделка «В размещении» (владелец 01.10.2026), с требованиями стадии.
    stage = (advance_deal(db, _deal, RUNNING_STAGE, user, "РК запущена трафиком")
             if dsp_status == ds.LAUNCHED else None)

    db.commit()
    targeting = (_wake_quietly(db, c.deal_id)
                 if dsp_status == ds.LAUNCHED and old != "запущена" else None)
    # Площадкам — только о СТАРТЕ и только один раз: письмо получает площадка, которую
    # эта кнопка запустила ВПЕРВЫЕ (аудит 01.10.2026, В-4). «Пауза → запущен»
    # повторяется, и письмо «кампания стартовала» на третий раз перестают читать.
    if started:
        _tell_publishers_started(db, c, started)
    log_action(db, user, "ad_campaign_status", "sales_deal", c.deal_id,
               f"{rk_label(db, c.id)}: {old} → {c.status}"
               + (f"; поднято площадок {raised}" if raised else "")
               + (f"; спущено на площадки {stopped}" if stopped else "")
               + (f"; в DSP {dsp_status}" if dsp_status else ""))
    return {"id": c.id, "status": c.status, "placements_raised": raised,
            "placements_stopped": stopped, "dsp_status": dsp_status,
            "dsp_check": getattr(c, "_dsp_check", None), "stage": stage,
            "targeting": targeting}


# Стадия, на которую «Завершить РК» двигает сделку. Резолвим ПО ИМЕНИ, потому что
# `stage_key` здесь не различает: «В размещении» и «Итоговая сверка» обе носят `launch`.
# Тем же приёмом (`stageNames`) их различает дашборд аккаунта — переименование стадии в
# справочнике требует правки в обоих местах, и это записано там же.
RECON_STAGE = "Итоговая сверка"


@router.put("/creative/{creative_id}/status")
def set_creative_status(creative_id: int, payload: StatusIn,
                        db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Вкл/пауза/отклонение креатива на площадке.

    Кнопки и логика те же, что у площадки (владелец 04.09.2026): первые три статуса
    ставит конвейер согласования, три последних — трафик. Пауза долю СОХРАНЯЕТ,
    отклонение отдаёт объём остальным креативам этой площадки.

    Доли креативов нигде не хранятся: они считаются при чтении делением плана площадки
    поровну между работающими (`flight.split_evenly`).

    А планы ПЛОЩАДОК хранятся, и с 27.09.2026 зависят от креативов: площадка на фиксе
    получает сумму объёмов своих креативов, кроме отклонённых (`build.PLACEMENT_FIXED_SQL`).
    Поэтому отклонение и его отмена пересчитывают площадки РК сразу — иначе DSP и
    дашборд крутили бы по устаревшему фиксу до следующей сборки.
    """
    if payload.status not in CREATIVE_MANUAL:
        raise HTTPException(400, f"Выбрать можно {CREATIVE_MANUAL}; "
                                 f"остальное ставит согласование креативов")
    cr = db.query(AdCampaignCreative).get(creative_id)
    if not cr:
        raise HTTPException(404, "Креатив не найден")
    c, _ = _campaign_in_scope(db, cr.campaign_id, user)   # область видимости — та же
    # «Запущен» и «пауза» — только тому, что согласовано (или уже крутилось): иначе кнопка
    # — чёрный ход мимо согласования, в том числе через «пауза → запущен» (аудит
    # 01.10.2026, В-3).
    if payload.status in ("запущен", "пауза") and cr.status not in ("согласован", "пауза", "запущен"):
        raise HTTPException(400, "Креатив не согласован — запускать и ставить на паузу нечего")
    old, cr.status = cr.status, payload.status
    db.flush()
    if (old == CREATIVE_REJECTED) != (cr.status == CREATIVE_REJECTED):
        build.recompute_shares(db, cr.campaign_id)
    # DSP следует за ЭТИМ креативом — одним вызовом (В-3). Раньше пауза и отклонение
    # меняли только нашу пометку, и в DSP креатив продолжал крутиться. Полный проход по
    # РК (план, все креативы, лимиты) здесь не нужен: меняется один креатив.
    dsp = _creative_to_dsp(db, c, cr, old)
    db.commit()
    log_action(db, user, "ad_creative_status", "sales_publisher", None,
               f"креатив {cr.ms_title}: {old} → {cr.status}" + (f"; в DSP {dsp}" if dsp else ""))
    return {"id": cr.id, "status": cr.status, "dsp_status": dsp}


def _creative_to_dsp(db: Session, c, cr, old: str) -> Optional[str]:
    """Статус одного креатива в DSP по нашему. Правило выбора — то же, что у кнопки РК
    (`campaigns.creative_targets`): крутит, только когда крутят и РК, и площадка, и
    креатив. Отклонённый — останавливаем сами (общее правило его не трогает: отозванные
    уже в архиве DSP), но архивный не трогаем: STOPPED вернул бы его оттуда.
    Сбой DSP — откат нашего изменения: вызов один, полусостояния не остаётся."""
    from app.dsp.campaigns import DSP_STATUS_OF, creative_targets
    from app.dsp.client import MsError
    xx = (cr.ms_creative_xxhash or "").strip()
    if not (xx and c.ms_campaign_xxhash):
        return None
    pl = db.query(AdCampaignPlacement).get(cr.placement_id)
    camp_target = DSP_STATUS_OF.get(effective_campaign_status(c.status, _campaign_chain(db, c)))
    ms = MsClient()
    try:
        cur = ((ms.creative_get_info(xx) or {}).get("status") or "").upper()
        if cur == ds.ARCHIVE:
            if old == CREATIVE_REJECTED and cr.status != CREATIVE_REJECTED:
                db.rollback()
                raise HTTPException(400, "Креатив отозван и в DSP в архиве — вернуть его нельзя, "
                                         "нужен новый креатив")
            return cur
        if cr.status == CREATIVE_REJECTED:
            want = ds.STOPPED
        else:
            want = creative_targets([(xx, pl.status if pl else None, cr.status)],
                                    camp_target or ds.STOPPED).get(xx)
        if want and want != cur:
            ms.creative_set_status(xx, want, local_ref=c.id)
        return want or cur
    except MsError as e:
        db.rollback()
        raise HTTPException(502, f"DSP не принял статус креатива — изменения не сохранены: {e}")


@router.put("/creative/{creative_id}/screens")
def set_creative_screens(creative_id: int, payload: ScreensIn,
                         db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """«Скрины запуска сняты» на паре «креатив × площадка» (владелец 01.10.2026). Просто
    отметка трафика: ничего за собой не тянет, снимается так же."""
    from datetime import datetime
    cr = db.query(AdCampaignCreative).get(creative_id)
    if not cr:
        raise HTTPException(404, "Креатив не найден")
    _campaign_in_scope(db, cr.campaign_id, user)
    cr.screens_done_at = datetime.utcnow() if payload.done else None
    cr.screens_done_by = user.id if payload.done else None
    db.commit()
    log_action(db, user, "ad_creative_screens", "sales_publisher", None,
               f"креатив {cr.ms_title}: скрины запуска {'сняты' if payload.done else 'не сняты'}")
    return {"id": cr.id, "screens_done_at": cr.screens_done_at, "screens_done_by": cr.screens_done_by}


@router.put("/campaign/{campaign_id}/finish")
def finish_campaign(campaign_id: int, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Завершить РК: статус «окончена» и сделка уезжает на «Итоговую сверку».

    Конец открутки — момент, когда хозяином сделки снова становится аккаунт: цифры
    финализируют и готовят документальное закрытие. Кнопка стоит у трафика, потому что
    знает об окончании он.

    ТРЕТЬЕ место в системе, которое двигает сделку по каталогу (первые два —
    `/deals/{id}/move` и проверка медиаплана в `media_plans`). Форма перехода та же:
    меняем стадию, пишем СТРОКУ ИСТОРИИ с причиной, логируем. Без записи истории
    «сколько сделка стоит на стадии» считалось бы от неизвестной даты, а автор перехода
    терялся — журнал действий для этого не годится, там свободный текст.

    Назад не двигаем: если сделка уже прошла сверку, «завершить» ничего не меняет и
    молча откатывать её на предыдущий этап нельзя.
    """
    from app.dsp.campaigns import apply_status
    from app.dsp.client import MsError

    c, deal = _campaign_in_scope(db, campaign_id, user)
    # DSP — ПЕРВЫМ, до перевода сделки (он коммитит сам): не вышло — не меняем ничего.
    # Без этого «окончена» у нас, а кампания в DSP крутила бы и тратила дальше.
    try:
        apply_status(db, c, "окончена")
    except MsError as e:
        raise HTTPException(502, f"DSP не принял завершение — РК не завершена: {e}")
    # Стадия ищется ПО ИМЕНИ, а имя правится на экране «Настройки → Стадии». Раньше её
    # отсутствие роняло ручку целиком — и тогда нельзя было завершить РК ВООБЩЕ:
    # статус кампании и остановка площадок стоят ниже, то есть площадки продолжали
    # крутить из-за переименования стадии. Теперь ненайденная стадия только лишает
    # перевода: РК окончена — это факт, он от нашей лестницы не зависит.
    # Статус — ДО перевода сделки: вход в «Итоговую сверку» требует завершённой РК
    # (проверка `campaign_finished`, 01.10.2026), и иначе кнопка заперла бы сама себя.
    old, c.status = c.status, "окончена"
    db.flush()
    adv = advance_deal(db, deal, RECON_STAGE, user, "РК завершена трафиком")
    refused, moved = adv["refused"], adv["moved"]

    # Завершение — тот же каскад: РК окончена, а площадки продолжают крутить, это не
    # состояние, а рассогласование.
    stopped = _cascade_placements(db, c.id, "окончена")
    db.commit()
    log_action(db, user, "ad_campaign_finish", "sales_deal", deal.id,
               f"{rk_label(db, c.id)}: {old} → окончена"
               + (f"; сделка → {adv['stage']}" if moved else "")
               + (f"; остановлено площадок {stopped}" if stopped else "")
               + (f"; {refused}" if refused else ""))
    return {"id": c.id, "status": c.status, "placements_stopped": stopped,
            "stage_refused": refused, "stage": adv["stage"], "moved": bool(moved)}


@router.get("/campaign/{campaign_id}/start-plan")
def start_plan(campaign_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Окно «Запустить РК» (владелец 01.10.2026): по каждой площадке — статус, поднимет
    ли её массовый старт и почему нет. Правило — то же `start_block`, что у кнопок."""
    from app.launch_prep import pub_rules
    from app.sales.models import SalesPublisher
    c, _deal = _campaign_in_scope(db, campaign_id, user)
    creatives = _creatives_of(db, c.id)
    pls = db.query(AdCampaignPlacement).filter_by(campaign_id=c.id).all()
    pubs = {x.id: x for x in db.query(SalesPublisher).filter(
        SalesPublisher.id.in_([p.publisher_id for p in pls] or [0]))}
    modes = pub_rules.placement_modes(db, {(c.deal_id, p.publisher_id) for p in pls})
    rows = []
    for p in pls:
        pub = pubs.get(p.publisher_id)
        mode = (modes.get((c.deal_id, p.publisher_id)) or {}).get("mode")
        why = mass_start_skip(mode) or start_block(db, c, p, creatives.get(p.id, []), mode)
        if p.status == "запущен":
            act = "running"
        elif p.status in START_RAISABLE and not why:
            act = "start"
        else:
            act = "skip"
            why = why or f"статус «{p.status}» — поднимает только согласование"
        rows.append({"placement_id": p.id, "publisher": pub.name if pub else "?",
                     "domain": pub.domain if pub else None, "status": p.status,
                     "external": mode == pub_rules.MODE_EXTERNAL,
                     "action": act, "why": None if act != "skip" else why})
    order = {"start": 0, "running": 1, "skip": 2}
    rows.sort(key=lambda r: (order[r["action"]], r["publisher"]))
    return {"campaign_id": c.id, "status": c.status, "dsp_block": dsp_not_ready(db, c),
            "rows": rows, "start": sum(r["action"] == "start" for r in rows),
            "running": sum(r["action"] == "running" for r in rows),
            "skip": sum(r["action"] == "skip" for r in rows)}


@router.put("/placement/{placement_id}/status")
def set_placement_status(placement_id: int, payload: StatusIn,
                         db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Вкл/пауза/завершение площадки в РК.

    Принимаются ТОЛЬКО ручные статусы. «У трафика», «у площадки» и «ждёт запуска»
    ставит конвейер согласования (владелец 04.09.2026) — присвоить их руками значит
    соврать про то, у кого мяч, и экран тут же пересчитал бы это обратно.

    После смены статуса доли пересчитываются: они считаются по крутящим, и выключенная
    площадка отдаёт свой объём остальным. Без пересчёта план остался бы на строке,
    которая ничего не откручивает.
    """
    if payload.status not in PLACEMENT_MANUAL:
        raise HTTPException(400, f"Выбрать можно {PLACEMENT_MANUAL}; "
                                 f"{PLACEMENT_CHAIN} ставит согласование креативов")
    p = db.query(AdCampaignPlacement).get(placement_id)
    if not p:
        raise HTTPException(404, "Площадка в РК не найдена")
    # Область видимости — та же, что у РК: до 23.09.2026 здесь её не спрашивали вовсе.
    c, _deal = _campaign_in_scope(db, p.campaign_id, user)
    # «Площадка запущена только при хоть одном согласованном креативе» (владелец
    # 04.09.2026). Запрет НА СЕРВЕРЕ, а не серой кнопкой: спрятанная кнопка возвращается
    # первым же рефакторингом, а запущенная площадка без согласованного материала — это
    # показ несогласованного баннера.
    if payload.status == "запущен":
        volumes.guard(db, _deal.id)       # объёмы больше плана РК (27.09.2026)
    # Пауза КРУТЯЩЕЙ площадки не держится никогда: остановить то, что тратит, важнее
    # проверки (ревью 30.09.2026 — креатив вернули на переделку, а площадка крутит).
    if payload.status == "запущен" or (payload.status == "пауза" and p.status != "запущен"):
        why = start_block(db, c, p, _creatives_of(db, p.campaign_id).get(p.id, []))
        if why == "нет согласованного креатива":
            raise HTTPException(400, "Нет ни одного согласованного креатива — "
                                     "площадку нельзя запустить")
        if why:
            raise HTTPException(409, DSP_NOT_UPLOADED)
    old, p.status = p.status, payload.status
    first = _mark_first_start(p)
    build.recompute_shares(db, p.campaign_id)
    # ЗАПУСК — ЕДИНСТВЕННЫЙ ПИСАТЕЛЬ «в размещении» у пары в сборе запуска. Раньше эту
    # строку ставили кнопкой на карточке сделки, и карточка говорила «в размещении» о
    # площадке, которая ждёт запуска, при несобранной РК и ненаступившем сроке
    # (владелец 18.09.2026). Один факт — одно место записи.
    moved = build.mark_target_placed(db, p) if p.status == "запущен" else 0
    # Сняли, не открутив ни показа, — пара возвращается из «в размещении» (01.10.2026).
    if old == "запущен" and p.status != "запущен":
        build.unmark_target_placed(db, p)
    # Площадка меняет и статус РК по факту: первая запущенная делает её «запущена»,
    # последняя остановленная — «готова». DSP следует.
    dsp_status = _dsp_follow(db, c)
    first = bool(_keep_first_starts(db, [p.id] if first else [], dsp_status))
    stage = (advance_deal(db, _deal, RUNNING_STAGE, user, "РК запущена трафиком")
             if dsp_status == ds.LAUNCHED else None)
    db.commit()
    # Первый запуск площадки её кнопкой — то же письмо, что с кнопки РК (В-4).
    if first:
        _tell_publishers_started(db, c, [p.id])
    pub_name = publisher_name(db, p.publisher_id)
    log_action(db, user, "ad_placement_status", "sales_publisher", p.publisher_id,
               f"{rk_label(db, p.campaign_id)}: площадка {pub_name} {old} → {p.status}"
               + (f"; получателей переведено в размещение: {moved}" if moved else ""))
    return {"id": p.id, "status": p.status, "targets_placed": moved,
            "dsp_check": getattr(c, "_dsp_check", None), "stage": stage}


# ── внешние системы: пиксель Weborama и выгрузка в DSP ───────────────────────
#
# Две кнопки в расхлопе РК. Обе НЕОБРАТИМЫ: и вставка Weborama, и креатив в DSP не
# удаляются и не переименовываются по API. Поэтому у каждой две ручки — «что будет»
# и «делай», и первая обязана отвечать ЧИСЛАМИ: подтверждение без цифры «19 площадок»
# ничем не отличается от случайного нажатия.
#
# Порядок между ними не косметика: пиксель показа вшивается В КРЕАТИВ, поэтому Weborama
# идёт первой, а DSP отказывается заводить площадку без пикселя (`dsp.provision._blocker`).

@router.get("/campaign/{campaign_id}/external-plan")
def external_plan(campaign_id: int, db: Session = Depends(get_db),
                  user: User = Depends(VIEW)):
    """Что произойдёт при нажатии каждой из кнопок. Ничего не меняет."""
    from app.dsp import provision as dsp_prov
    from app.weborama import provision as wb_prov

    c, _deal = _campaign_in_scope(db, campaign_id, user)
    try:
        wb = wb_prov.plan(db, c)
        # Посадочная кампании — наш сайт, один на все кампании: у Weborama это поле
        # справочное, а подставлять туда адрес одной из площадок значит выбирать
        # произвольную и путать того, кто читает. Заслона «ни у кого нет ссылки» больше
        # нет: собственный адрес есть всегда.
        wb["landing"] = wb_prov.default_landing(db, c)
    except wb_prov.ProvisionError as e:
        wb = {"ready": 0, "todo": 0, "have": 0, "blocked": str(e)}
    # Зависшие попытки — в том же ответе: человек видит их там, где жмёт кнопку, и
    # сверяется с кабинетом, не уходя с экрана (владелец 23.09.2026).
    from app.ad import unknown
    return {"weborama": wb, "dsp": dsp_prov.plan(db, c),
            "unknown": unknown.list_unknown(db, c)}


class ResolveIn(BaseModel):
    system: str                        # 'dsp' | 'weborama'
    ref: str                           # 'campaign' / 'cr<id>' у DSP, номер попытки у Weborama
    found: bool
    external_id: Optional[str] = None  # хеш DSP или id Weborama — когда «нашёл»


@router.post("/campaign/{campaign_id}/external/resolve")
def resolve_external(campaign_id: int, payload: ResolveIn, db: Session = Depends(get_db),
                     user: User = Depends(EDIT)):
    """Отметка после сверки с кабинетом: «нашёл» (с id) или «в кабинете нет».

    Без неё попытка, ушедшая без ответа, запирала повтор навсегда — снять можно было
    только запросом в базу. Право то же, что у кнопок «DSP» и «ПИКСЕЛЬ WR».
    """
    from app.ad import unknown

    c, deal = _campaign_in_scope(db, campaign_id, user)
    try:
        out = unknown.resolve(db, c, payload.system, payload.ref, found=payload.found,
                              external_id=payload.external_id, user=user)
    except unknown.ResolveError as e:
        raise HTTPException(400, str(e))
    sys_name = "DSP" if payload.system == "dsp" else "Weborama"
    log_action(db, user, "external_resolve", "sales_deal", deal.id,
               f"{rk_label(db, c.id)}: {sys_name}, попытка {payload.ref} — "
               + (f"найден в кабинете: {out.get('id')}" if payload.found
                  else "в кабинете нет, повтор разрешён"))
    return out


@router.post("/campaign/{campaign_id}/weborama")
def run_weborama(campaign_id: int, db: Session = Depends(get_db),
                 user: User = Depends(EDIT)):
    """Завести вставки в Weborama и забрать пиксели показа по готовым площадкам."""
    from app.weborama import provision as wb_prov

    c, deal = _campaign_in_scope(db, campaign_id, user)
    landing = wb_prov.default_landing(db, c)
    try:
        out = wb_prov.provision(db, c, landing, user_id=user.id)
    except wb_prov.ProvisionError as e:
        raise HTTPException(400, str(e))
    log_action(db, user, "weborama_provision", "sales_deal", deal.id,
               f"{rk_label(db, c.id)}: пикселей получено {len(out['done'])}, "
               f"отказов {len(out['failed'])}")
    return out


class WeboramaAttachIn(BaseModel):
    project_id: Optional[str] = None
    campaign_id: Optional[str] = None


@router.post("/campaign/{campaign_id}/weborama/attach")
def attach_weborama(campaign_id: int, payload: WeboramaAttachIn,
                    db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Связать РК с проектом и кампанией, уже заведёнными в Weborama (28.09.2026)."""
    from app.weborama import provision as wb_prov

    c, deal = _campaign_in_scope(db, campaign_id, user)
    try:
        out = wb_prov.attach_existing(db, c, payload.project_id, payload.campaign_id,
                                      user_id=user.id)
    except wb_prov.ProvisionError as e:
        raise HTTPException(400, str(e))
    log_action(db, user, "weborama_attach", "sales_deal", deal.id,
               f"{rk_label(db, c.id)}: привязано к Weborama — "
               + ", ".join(f"{a['kind']} {a['wcm_id']}" for a in out["attached"]))
    return out


@router.get("/weborama/stats")
def weborama_stats_state(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Состояние съёма статистики верификатора: когда забирали и что доехало.

    Отвечает на два разных вопроса, которые легко спутать: «коннектор жив?» и «числа
    доехали до экрана?». Пустой реестр соответствий — это второе: сырьё лежит, съём
    прошёл, а на дашборде не появилось ничего, потому что прицепить показы не к чему.
    """
    from app.weborama.state import stats_state

    return stats_state(db)


@router.post("/weborama/stats")
def weborama_stats_pull(days: int = 3, db: Session = Depends(get_db),
                        user: User = Depends(EDIT)):
    """Снять статистику Weborama сейчас, не дожидаясь суточной задачи.

    Читающая операция снаружи: в чужую систему не пишет ничего, поэтому подтверждения
    не требует — в отличие от кнопок заведения вставок и выгрузки в DSP.
    """
    from app.weborama import daily
    from app.weborama.client import WcmError
    from app.weborama.stats import window

    days = max(1, min(int(days or 3), 92))
    start, end = window(days=days)
    try:
        out = daily.run(start=start, end=end)
    except (WcmError, RuntimeError) as e:
        raise HTTPException(400, str(e))
    log_action(db, user, "weborama_stats_pull", "ad_campaign", None,
               f"Weborama {out['start']}..{out['end']}: строк {out['rows']}, "
               f"на дашборд легло {out['written']}, без соответствия {out['skipped']}")
    return out


@router.post("/campaign/{campaign_id}/dsp")
def run_dsp(campaign_id: int, db: Session = Depends(get_db),
            user: User = Depends(EDIT)):
    """Выгрузить креативы готовых площадок в DSP: кампания, архив, обёртка, креатив."""
    from app.dsp import provision as dsp_prov

    c, deal = _campaign_in_scope(db, campaign_id, user)
    volumes.guard(db, deal.id)            # объёмы больше плана РК (27.09.2026)
    try:
        out = dsp_prov.provision(db, c, user_id=user.id)
    except dsp_prov.DspProvisionError as e:
        raise HTTPException(400, str(e))
    log_action(db, user, "dsp_provision", "sales_deal", deal.id,
               f"{rk_label(db, c.id)}: креативов заведено {len(out['done'])}, "
               f"отказов {len(out['failed'])}")
    return out


def _keep_first_starts(db: Session, ids: list, dsp_status: Optional[str]) -> list:
    """Первый запуск засчитывается, только если РК в DSP и правда пошла — или DSP этой
    РК не нужен (`dsp_status` пуст: кампании в DSP нет). Иначе отметку снимаем: письмо
    «стартовала» уйдёт при настоящем запуске, а не о кампании, которая не крутит."""
    if not ids or dsp_status in (None, ds.LAUNCHED):
        return ids
    for pl in db.query(AdCampaignPlacement).filter(AdCampaignPlacement.id.in_(ids)):
        pl.first_started_at = None
    return []


def _mark_first_start(p) -> bool:
    """Площадка запущена ВПЕРВЫЕ — отметить и вернуть True. Признак — отметка в базе, а
    не статус «было до»: площадку могли поставить на паузу или завершить, ни разу не
    запустив, и по статусу первый настоящий старт не отличить от возобновления
    (владелец 02.10.2026). Письмо «стартовала» уходит по этой отметке один раз."""
    if p.status != "запущен" or getattr(p, "first_started_at", None) is not None:
        return False
    from datetime import datetime
    p.first_started_at = datetime.utcnow()
    return True


def _tell_publishers_started(db: Session, camp, placement_ids) -> None:
    """Сказать площадкам РК, что размещение вышло в эфир.

    Веером по площадкам: у каждой свой план показов и своя цена, и «кампания стартовала»
    без её собственных чисел не говорит ей ничего.

    Письмо НЕ отменяет старт: прослойка возвращает причину, а не бросает исключение.
    """
    from app.notify.outward import notify_publisher
    from app.routers.launch_prep import _deal_brand_name, deal_period_text
    from app.sales.models import SalesDeal, SalesPublisher

    deal = db.query(SalesDeal).filter(SalesDeal.id == camp.deal_id).first()
    if deal is None:
        return
    brand = _deal_brand_name(db, deal)
    period = deal_period_text(deal)
    rows = (db.query(AdCampaignPlacement, SalesPublisher)
            .join(SalesPublisher, SalesPublisher.id == AdCampaignPlacement.publisher_id)
            .filter(AdCampaignPlacement.campaign_id == camp.id).all())
    wanted = set(placement_ids)
    for pl, pub in rows:
        if pl.id not in wanted:
            continue
        context = " · ".join(x for x in ((pub.domain or pub.name), brand, period) if x)
        # ПЛАШЕК У ЭТОГО ПИСЬМА НЕТ (владелец 16.09.2026). План показов убран: письмо
        # сообщает площадке факт выхода в эфир, а наши плановые числа ей не адресованы.
        # Отправитель и каталог обязаны совпадать — иначе экран шаблонов показывает одно,
        # а получатель видит другое; на это стоит прибор.
        try:
            notify_publisher(db, "старт рк", pub.id,
                             title="Кампания стартовала",
                             body="Размещение вышло в эфир.",
                             facts=(), context=context, link="/",
                             entity_type="ad_campaign_placement", entity_id=pl.id,
                             values={"бренд": brand, "период": period})
        except Exception as e:                               # noqa: BLE001
            # Сессию — в рабочее состояние: сбой базы внутри рассылки оставил бы её в
            # упавшей транзакции, и следующая запись (журнал, другие площадки) дала бы 500
            # при уже записанном действии (ревью 24.09.2026).
            db.rollback()
            log.warning("Площадке %s не ушло «старт рк»: %s", pub.id, e)


# ── «Обновить данные в DSP» (владелец 02.10.2026) ────────────────────────────
# Приводит уже заведённое к текущим данным: ссылки, пиксели, таргеты; копии нацеливания —
# только ЕРИД. Правила и сравнение — `app/dsp/refresh.py`.

class RefreshItemIn(BaseModel):
    kind: str
    ref: str


class RefreshDoneIn(BaseModel):
    applied: int = 0
    failed: List[str] = []


def _refresh_guard(db: Session, campaign_id: int, user: User):
    if not dsp_refresh.may_refresh(user):
        raise HTTPException(403, "Обновлять данные в DSP могут Администратор и «Админ Трафик»")
    return _campaign_in_scope(db, campaign_id, user)


@router.get("/campaign/{campaign_id}/dsp-refresh")
def dsp_refresh_plan(campaign_id: int, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Что изменится — по состоянию, прочитанному из DSP. Ничего не пишет."""
    c, _deal = _refresh_guard(db, campaign_id, user)
    return dsp_refresh.plan(db, c)


@router.post("/campaign/{campaign_id}/dsp-refresh/item")
def dsp_refresh_item(campaign_id: int, payload: RefreshItemIn,
                     db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Записать ОДИН пункт — экран ведёт по ним настоящий прогресс."""
    from app.dsp.client import MsError
    c, deal = _refresh_guard(db, campaign_id, user)
    try:
        out = dsp_refresh.apply_item(db, c, payload.kind, payload.ref)
    except (MsError, ValueError) as e:
        raise HTTPException(400, str(e))
    # Журнал — на сервере по каждому записанному пункту: итог от экрана мог не прийти
    # (вкладку закрыли посреди прогона), а запись в боевом кабинете уже состоялась.
    if out.get("changed"):
        log_action(db, user, "dsp_refresh", "sales_deal", deal.id,
                   f"{rk_label(db, c.id)}: {payload.kind} {payload.ref[:60]} — "
                   f"{', '.join(out['changed'])}")
    return out


@router.post("/campaign/{campaign_id}/dsp-refresh/done")
def dsp_refresh_done(campaign_id: int, payload: RefreshDoneIn,
                     db: Session = Depends(get_db), user: User = Depends(EDIT)):
    c, deal = _refresh_guard(db, campaign_id, user)
    # Итог прогона — со слов экрана, поэтому только сводка и с обрезкой: сами записи
    # уже в журнале построчно (`dsp_refresh_item`).
    failed = [str(f)[:200] for f in payload.failed[:10]]
    log_action(db, user, "dsp_refresh", "sales_deal", deal.id,
               f"{rk_label(db, c.id)}: прогон обновления завершён, пунктов {int(payload.applied)}"
               + (f"; не принято: {'; '.join(failed)}" if failed else ""))
    return {"ok": True}
