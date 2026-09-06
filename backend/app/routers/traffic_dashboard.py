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

from app.ad import build
from app.ad.flight import (CAMPAIGN_MANUAL, CREATIVE_MANUAL, CREATIVE_STATUSES,
                           GRAIN_DAYS, campaign_chain_status, effective_campaign_status,
                           PLACEMENT_CHAIN, PLACEMENT_MANUAL, PLACEMENT_RUNNING,
                           PLACEMENT_STATUSES, PLACEMENT_OFF, PLACEMENT_READY,
                           best_chain_status, can_start_placement,
                           creative_counts, culprits, daily_buckets,
                           distribute, effective_status, flight_of, progress, split_evenly)
from app.ad.models import AdCampaign, AdCampaignCreative, AdCampaignPlacement
from app.traffic import urgency
from app.audit import log_action
from app.database import get_db
from app.models import User
from app.permissions import require_permission
from app.routers.traffic import _apply_scope, _is_master
from app.sales.models import SalesDeal, SalesRep
from app.sales.reps import staff_users
from app.sales.row_context import load_row_context

router = APIRouter()

VIEW = require_permission("traffic_dashboard", "view")
EDIT = require_permission("traffic_dashboard", "edit")

CAMPAIGN_STATUSES = ("ожидает сборки", "готова", "запущена", "пауза",
                     "остановлена", "окончена", "архив")
RUNNING = ("запущена", "пауза")


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


def _facts(db: Session, campaign_ids: List[int]) -> dict:
    if not campaign_ids:
        return {}
    rows = db.execute(text(
        "SELECT campaign_id, sum(shows) AS shows, sum(clicks) AS clicks "
        "FROM ad_campaign_stat WHERE campaign_id = ANY(:i) GROUP BY campaign_id"),
        {"i": campaign_ids}).mappings().all()
    return {r["campaign_id"]: dict(r) for r in rows}


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


def _creatives_of(db: Session, campaign_id: int) -> dict:
    """Креативы РК по площадкам: {placement_id: [строки]}.

    Имя человеческое берётся у КОМПЛЕКТА-корня (`launch_prep_creative_set.title`), полный
    индекс — из `ms_title` (`<код сделки>-<код площадки>-cr<№>`). Два разных имени, и оба
    нужны: первое человек дал сам, второе видно в кабинете DSP.
    """
    rows = db.execute(text("""
        SELECT c.id, c.placement_id, c.creative_no, c.status, c.ms_title, c.erid,
               c.ms_creative_xxhash, c.root_set_id, c.pair_id,
               s.title AS name, s.no AS set_no,
               pr.code AS pair_code,
               cur.no AS version_no, cur.origin
          FROM ad_campaign_creative c
          LEFT JOIN launch_prep_creative_set s ON s.id = c.root_set_id
          LEFT JOIN launch_prep_pair pr ON pr.id = c.pair_id
          LEFT JOIN launch_prep_creative_set cur ON cur.id = pr.set_id
         WHERE c.campaign_id = :c
         ORDER BY c.placement_id, c.creative_no
    """), {"c": campaign_id}).mappings().all()
    out: dict = {}
    for r in rows:
        out.setdefault(r["placement_id"], []).append(dict(r))
    return out


# Словари площадки и креатива различаются одним словом: согласованное состояние у
# площадки зовётся «ждёт запуска», у креатива — «согласован». Перевод нужен там, где
# статус площадки собирается из статусов её креативов.
def _as_placement_scale(creative_status: str) -> str:
    return PLACEMENT_READY if creative_status == "согласован" else creative_status


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
                 WHERE s.placement_id = p.id) AS fact
          FROM ad_campaign_placement p
          JOIN sales_publishers pub ON pub.id = p.publisher_id
         WHERE p.campaign_id = ANY(:i)
    """), {"i": campaign_ids}).mappings().all()
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
        "FROM ad_campaign_stat WHERE campaign_id = ANY(:i) "
        "GROUP BY campaign_id, date"), {"i": campaign_ids}).mappings().all()
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
            shows = by_day.get(d, (None, None))[0]
            cells.append({
                "date": d,
                "shows": shows,
                "ratio": round(shows / per_day, 3) if (shows is not None and per_day) else None,
                "ahead": d > today,
            })
        out.append({"id": r["id"], "deal_code": r["deal_code"], "cells": cells,
                    "done_pct": r["done_pct"]})
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
            asked_at=r["asked_at"].date() if r["asked_at"] else None,
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
    today = date.today()
    stages = dict(db.execute(text("SELECT id, name FROM sales_stages")).all())
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
    culprit_rows = []
    dist_by_camp: dict = {}
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
        dist_by_camp[c.id] = distribute(c.plan_show, facts.get(c.id, {}).get("shows"),
                                        fl, pls)["rows"]
        culprit_rows += dist_by_camp[c.id]

    rows = []
    for c, d in pairs:
        f = facts.get(c.id, {})
        pls = places.get(c.id, [])
        fc = progress(c.plan_show, f.get("shows"), c.date_start, c.date_end, today)
        by_pl = cr_all.get(c.id, {})
        chain_st = campaign_chain_status(
            has_plan=bool(c.plan_show), placements=len(pls),
            running=sum(1 for p in pls if p["status"] in PLACEMENT_RUNNING),
            can_start=any(can_start_placement(by_pl.get(p["id"], [])) for p in pls))
        rows.append({
            "id": c.id, "deal_id": d.id, "deal_code": d.code, "deal_title": d.title,
            # Ответственный трафик — прямо в строке: по нему подсвечивается
            # нераспределённое, и он же объясняет, почему РК видно в «Моих».
            "traffic": traf_name.get(d.traffic_manager_id),
            "traffic_rep_id": d.traffic_manager_id,
            "product": d.product, "inventory": row_ctx.inventory(d.id, d.product),
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
        "today": today,
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
               (SELECT sum(s.shows) FROM ad_campaign_stat s WHERE s.placement_id = p.id) AS fact,
               (SELECT sum(s.clicks) FROM ad_campaign_stat s WHERE s.placement_id = p.id) AS fact_clicks
        FROM ad_campaign_placement p
        JOIN sales_publishers pub ON pub.id = p.publisher_id
        WHERE p.campaign_id = :c
        ORDER BY p.weight DESC NULLS LAST, lower(pub.name)
    """), {"c": campaign_id}).mappings().all()

    fl = flight_of(c.date_start, c.date_end)
    fact_total = _facts(db, [c.id]).get(c.id, {}).get("shows")
    creatives = _creatives_of(db, c.id)

    prepared = []
    for p in pls:
        d = dict(p)
        mine = creatives.get(p["id"], [])
        # Статус площадки собирается из ЕЁ КРЕАТИВОВ — самый продвинутый из них
        # (владелец 04.09.2026: «площадка запущена только при хоть одном согласованном
        # креативе»). Ручной статус трафика перекрывает расчёт.
        d["status"] = effective_status(
            p["status"], best_chain_status(_as_placement_scale(x["status"]) for x in mine))
        d["can_start"] = can_start_placement(x["status"] for x in mine)
        d["creative_counts"] = creative_counts(mine)
        prepared.append(d)
    out = distribute(c.plan_show, fact_total, fl, prepared)

    # Третий этаж: план площадки делится ПОРОВНУ между её работающими креативами.
    for row in out["rows"]:
        row["creatives"] = split_evenly(row.get("plan_show"), creatives.get(row["id"], []))

    by_pl = {p["id"]: [x["status"] for x in creatives.get(p["id"], [])] for p in pls}
    chain_st = campaign_chain_status(
        has_plan=bool(c.plan_show), placements=len(pls),
        running=sum(1 for x in prepared if x["status"] in PLACEMENT_RUNNING),
        can_start=any(can_start_placement(v) for v in by_pl.values()))

    return {
        "id": c.id, "status": effective_campaign_status(c.status, chain_st),
        "status_chain": chain_st, "plan_show": c.plan_show,
        "date_start": c.date_start, "date_end": c.date_end,
        "placements": out["rows"], "share_sum": out["share_sum"],
        "creative_manual": list(CREATIVE_MANUAL),
        "creative_statuses": list(CREATIVE_STATUSES),
        **progress(c.plan_show, fact_total, c.date_start, c.date_end),
        # Словарь целиком + какие значения можно ВЫБРАТЬ: экран не должен предлагать
        # в поповере то, что ставит конвейер.
        "placement_statuses": list(PLACEMENT_STATUSES),
        "placement_manual": list(PLACEMENT_MANUAL),
        "deal_id": deal.id,
        "owners": _owners(db, deal, user),
        # KPI приёмки из медиаплана — рядом с фактом, чтобы трафик видел, к чему его
        # открутку будут принимать, не открывая карточку сделки (владелец 05.09.2026).
        "goals": build.deal_goals(db, deal.id),
        # «Цели и особенности РК» — то самое послание аккаунта трафику с карточки сделки.
        # Здесь оно ЧИТАЕТСЯ, а не правится: писал аккаунт, и правка из чужого экрана
        # означала бы, что задачу можно молча переписать за него.
        "traffic_brief": (deal.traffic_brief or "").strip(),
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
    fl = flight_of(c.date_start, c.date_end)
    out = daily_buckets(c.plan_show, fact, fl, by_day, grain=grain,
                        date_from=date_from, date_to=date_to)
    if out is None:
        # Ни плана, ни дат — рисовать нечего, и это не ошибка, а состояние экрана.
        return {"buckets": [], "grain": grain, "need_per_day": None,
                "days_left": None, "speed": None, "totals": None}

    # Сводка под графиком: «сегодня» и «за период». Клики отдаются вместе с показами —
    # CTR считается от них, и второй запрос ради него был бы лишним.
    today = date.today()
    t_shows, t_clicks = by_day.get(today, (0, 0))
    all_shows = sum(v[0] or 0 for v in by_day.values())
    all_clicks = sum(v[1] or 0 for v in by_day.values())
    out["totals"] = {
        "today": {"shows": t_shows, "clicks": t_clicks,
                  "ctr": round(t_clicks / t_shows * 100, 2) if t_shows else None},
        "period": {"shows": all_shows, "clicks": all_clicks,
                   "ctr": round(all_clicks / all_shows * 100, 2) if all_shows else None},
    }
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
            p.status = target
            n += 1
    if n:
        # Доли считаются по крутящим: снятая площадка отдаёт объём остальным, а при
        # «пауза» доля сохраняется — обе ветки живут в `flight.distribute`, здесь только
        # повод пересчитать.
        build.recompute_shares(db, campaign_id)
    return n


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
    old, c.status = c.status, payload.status

    raised = 0
    if payload.status == "запущена" and payload.with_placements:
        # Поднимаем и отключённые, и стоящие на паузе — но только те, которым ЕСТЬ ЧЕМ
        # крутить: без согласованного креатива запуск запрещён тем же правилом, что и
        # поштучно (`can_start_placement`). Молча обойти его здесь значило бы завести
        # чёрный ход в обход собственной проверки.
        creatives = _creatives_of(db, c.id)
        for p in db.query(AdCampaignPlacement).filter_by(campaign_id=c.id).all():
            if p.status in (PLACEMENT_OFF, "пауза") and can_start_placement(
                    x["status"] for x in creatives.get(p.id, [])):
                p.status = "запущен"
                raised += 1
        if raised:
            build.recompute_shares(db, c.id)

    stopped = _cascade_placements(db, c.id, payload.status)

    db.commit()
    log_action(db, user, "ad_campaign_status", "sales_deal", c.deal_id,
               f"РК #{c.id}: {old} → {c.status}"
               + (f"; поднято площадок {raised}" if raised else "")
               + (f"; спущено на площадки {stopped}" if stopped else ""))
    return {"id": c.id, "status": c.status, "placements_raised": raised,
            "placements_stopped": stopped}


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
    поровну между работающими (`flight.split_evenly`). Пересчитывать после смены статуса
    нечего — потому и нет второго места, где эта арифметика могла бы разойтись.
    """
    if payload.status not in CREATIVE_MANUAL:
        raise HTTPException(400, f"Выбрать можно {CREATIVE_MANUAL}; "
                                 f"остальное ставит согласование креативов")
    cr = db.query(AdCampaignCreative).get(creative_id)
    if not cr:
        raise HTTPException(404, "Креатив не найден")
    _campaign_in_scope(db, cr.campaign_id, user)   # область видимости — та же
    old, cr.status = cr.status, payload.status
    db.commit()
    log_action(db, user, "ad_creative_status", "sales_publisher", None,
               f"креатив {cr.ms_title}: {old} → {cr.status}")
    return {"id": cr.id, "status": cr.status}


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
    from app.sales.catalog import Catalog
    from app.sales.models import SalesDealStageHistory

    c, deal = _campaign_in_scope(db, campaign_id, user)
    cat = Catalog(db)
    target = next((st for st in cat.stages if st.name == RECON_STAGE), None)
    if target is None:
        raise HTTPException(400, f"В каталоге стадий нет «{RECON_STAGE}»")

    moved = None
    if deal.our_stage_id != target.id and cat.is_before(deal.our_stage_id, target.id):
        moved = cat.by_id.get(deal.our_stage_id)
        deal.our_stage_id = target.id
        db.add(SalesDealStageHistory(
            deal_id=deal.id, from_stage_id=moved.id if moved else None,
            to_stage_id=target.id, user_id=user.id,
            reason="РК завершена трафиком"))

    old, c.status = c.status, "окончена"
    # Завершение — тот же каскад: РК окончена, а площадки продолжают крутить, это не
    # состояние, а рассогласование.
    stopped = _cascade_placements(db, c.id, "окончена")
    db.commit()
    log_action(db, user, "ad_campaign_finish", "sales_deal", deal.id,
               f"РК #{c.id}: {old} → окончена"
               + (f"; сделка {moved.name} → {target.name}" if moved else "")
               + (f"; остановлено площадок {stopped}" if stopped else ""))
    return {"id": c.id, "status": c.status, "placements_stopped": stopped,
            "stage": target.name if moved else (cat.by_id.get(deal.our_stage_id) or target).name,
            "moved": bool(moved)}


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
    # «Площадка запущена только при хоть одном согласованном креативе» (владелец
    # 04.09.2026). Запрет НА СЕРВЕРЕ, а не серой кнопкой: спрятанная кнопка возвращается
    # первым же рефакторингом, а запущенная площадка без согласованного материала — это
    # показ несогласованного баннера.
    if payload.status == "запущен":
        mine = [r["status"] for r in
                _creatives_of(db, p.campaign_id).get(p.id, [])]
        if not can_start_placement(mine):
            raise HTTPException(400, "Нет ни одного согласованного креатива — "
                                     "площадку нельзя запустить")
    old, p.status = p.status, payload.status
    build.recompute_shares(db, p.campaign_id)
    db.commit()
    log_action(db, user, "ad_placement_status", "sales_publisher", p.publisher_id,
               f"РК #{p.campaign_id}: площадка {old} → {p.status}")
    return {"id": p.id, "status": p.status}
