"""Строка очереди аккаунта: что показать по стадии и куда ведёт кнопка (макет «акки 3»).

Решения владельца 27–28.09.2026: один список вместо групп; строка говорит на языке своей
стадии — 2–4 факта и одна кнопка; ЭДО и Оплата внизу, спокойные сделки в самом конце.
Состав фактов по стадиям — ТЗ `docs/ТЗ_дашборд_аккаунта_v2_для_дизайна.md`, §4.

Новых правил здесь НЕТ, и заводить их нельзя:

* чек-чипы — это проверки перехода из `stage_checks.REGISTRY`, те же функции, что на
  карточке и в диалоге движения. Красный ✗ — проверка запирает переход ЭТОЙ сделки
  (разметка следующей стадии); серый — не запирает. «Проверить нечем» не рисуется: ✗
  там, где системе просто нечего знать, было бы неправдой;
* срочность и её причина — из `urgency.py`, одной функцией с лентой уведомлений;
* открутка — `sales/deal_delivery.py`, тем же расчётом, что у дашборда трафика.

Модуль делится на две половины. `load` грузит окружение всех сделок очереди пачкой —
запросов столько же на три сделки, сколько на шестьсот. `row_state` — чистая функция
от `Bundle`: что показать и какая кнопка; она проверяется без базы.

Элементы колонки «Что сделать» — четыре типа из ТЗ §3.2:
  {"type": "fact", "k", "v"} · {"type": "progress", "k", "x", "y", "unit"?}
  {"type": "check", "v", "ok", "optional"} · {"type": "alert", "tone": bad|warn, "v"}
  · {"type": "status", "tone": "good", "v"} — состояние РК плашкой (01.10.2026)
Кнопка — {"label", "do", "url"?, "hint"}; `do` понимает страница: mp · move · confirm ·
prep · link · expand. Нет кнопки — `action: None` и подпись `note` («ведёт трафик»).
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import text

from app.sales.stage_checks import REGISTRY, Ctx, OK, NOT_YET
from app.sales.stage_slots import TAIL_SLOTS, slot_of
from app.sales.urgency import LAG_ALARM_PCT, Verdict, delivery_lag_pct, DealFacts

# Проверки, которые очередь считает сама. Для каждой `load` подкладывает окружение,
# и тест держит равенство с поштучным расчётом карточки по всем ним.
CHECK_KEYS = ("mp_linked", "payer_set", "final_contract", "ord_initial_contract",
              "realization_pipeline", "creatives_accepted", "placements_approved",
              "erid_issued", "campaign_ready", "weborama_pixel", "fact_collected",
              "annex_generated", "signatory_filled", "ds_signed", "invoice_issued",
              "upd_issued", "report_attached")

# Чипы стадии: проверка → короткая подпись. Порядок — порядок в строке (макет).
SLOT_CHECKS = {
    "booking": (("payer_set", "Плательщик"), ("final_contract", "Договор ОРД"),
                ("realization_pipeline", "Воронка")),
    "prep": (("campaign_ready", "РК в DSP"), ("weborama_pixel", "Пиксель")),
    "recon": (("fact_collected", "Факт собран"),),
    "ds_prep": (("annex_generated", "Приложение"), ("signatory_filled", "Подписант")),
    "closing": (("invoice_issued", "Счёт"), ("upd_issued", "УПД"), ("report_attached", "Отчёт")),
}
# Отчёт по РК владелец считает необязательным (17.08.2026): серым, даже если размечен.
ALWAYS_OPTIONAL = {"report_attached"}


def _rub(n) -> str:
    return f"{round(n):,}".replace(",", " ") + " ₽"


def _pct(n: float) -> str:
    """7.0 → «7», 22.5 → «22,5»; минус типографский."""
    s = f"{abs(n):.1f}".rstrip("0").rstrip(".").replace(".", ",")
    return ("−" if n < 0 else "+" if n > 0 else "") + s


def _dm(d: Optional[date]) -> str:
    return d.strftime("%d.%m") if d else "—"


# ─────────────────────────────── чистая часть ───────────────────────────────

@dataclass
class Bundle:
    """Всё, что строка знает о сделке. Заполняет `load`, тесты — руками."""
    slot: Optional[str]
    code: str = ""
    stage_days: Optional[int] = None
    start_in: Optional[int] = None          # дней до старта РК (минус — прошёл)
    end_in: Optional[int] = None
    verdict: Verdict = field(default_factory=lambda: Verdict("normal"))
    has_mp: bool = False
    amount: Optional[float] = None          # до НДС, по правилу плана
    gross: Optional[float] = None           # с НДС
    checks: Dict[str, object] = field(default_factory=dict)   # ключ → Result
    required: set = field(default_factory=set)                # запирают переход этой сделки
    creatives: Optional[tuple] = None       # (согласовано пар, всего пар)
    sets: int = 0                           # комплектов креативов
    erids: List[str] = field(default_factory=list)
    kktu: bool = True                       # у бренда есть код ККТУ
    erid_share: int = 20                    # порог автовыпуска, %
    pixel_ordered: bool = False
    delivery: Optional[dict] = None         # sales/deal_delivery
    annex_no: str = ""
    annex_sum: Optional[float] = None
    pay_due: Optional[date] = None
    today: Optional[date] = None


def _fact(k, v):
    return {"type": "fact", "k": k, "v": v}


def _alert(v, tone="bad"):
    return {"type": "alert", "tone": tone, "v": v}


def _start(b: Bundle):
    n = b.start_in
    if n is None:
        return _alert("даты не заданы", "warn")
    if n == 0:
        return _alert("старт сегодня")
    if n < 0:
        return _alert(f"старт прошёл {-n} дн. назад")
    return _fact("старт", f"через {n} дн.")


def _check_chips(b: Bundle) -> list:
    out = []
    for key, label in SLOT_CHECKS.get(b.slot, ()):
        if key == "weborama_pixel" and not b.pixel_ordered:
            continue
        r = b.checks.get(key)
        if r is None or r.state not in (OK, NOT_YET):
            continue
        out.append({"type": "check", "v": label, "ok": r.state == OK,
                    "optional": key in ALWAYS_OPTIONAL or key not in b.required})
    return out


def _first_missing(b: Bundle) -> Optional[str]:
    """Первая по порядку строки проверка, которая ЗАПИРАЕТ переход и не выполнена."""
    for key, _ in SLOT_CHECKS.get(b.slot, ()):
        r = b.checks.get(key)
        if (r is not None and r.state == NOT_YET and key in b.required
                and key not in ALWAYS_OPTIONAL):
            return key
    return None


def _card(b: Bundle, anchor: str) -> str:
    return f"/sales/deals/{b.code}#{anchor}"


def _move(label, hint=""):
    return {"label": label, "do": "move", "hint": hint}


# Старые кнопки срочности — для стадии, которую дашборд не знает по имени.
_LEGACY_DO = {"deal_mp_missing": "mp", "booking_confirm": "confirm", "stage_stuck": "move",
              "stage_unmapped": "move", "act_missing": "expand"}


def _by_slot(b: Bundle):
    """(элементы, кнопка, подпись без кнопки) для слота."""
    s, v = b.slot, b.verdict
    if s == "unmapped":
        return ([_alert("стадия не отнесена — отчёты врут")],
                _move("Разобрать", "Стадия не отнесена к слою денег — выберите, где сделка"), "")

    if s == "mp_prep":
        state = [_start(b)]
        if b.has_mp:
            state.append(_fact("МП", "есть"))
            return state, _move("Отправить", "План есть — отдать клиенту"), ""
        state.append(_alert("МП нет") if v.urgency == "overdue" else _fact("МП", "нет"))
        return state, {"label": "Собрать МП", "do": "mp",
                       "hint": "Собрать медиаплан в конструкторе"}, ""

    if s == "mp_sent":
        state = []
        if b.stage_days is not None:
            state.append(_fact("у клиента", f"{b.stage_days} дн."))
        if b.amount:
            state.append(_fact("МП", _rub(b.amount)))
        state.append(_start(b))
        return state, _move("Бронь", "Клиент согласовал медиаплан — перевести в «Бронь»"), ""

    if s == "booking":
        state = [_start(b)] + _check_chips(b)
        miss = _first_missing(b)
        if miss == "payer_set":
            return state, {"label": "Плательщик", "do": "link", "url": _card(b, "head"),
                           "hint": "Укажите плательщика в шапке сделки"}, ""
        if miss == "final_contract":
            return state, {"label": "Договор ОРД", "do": "link", "url": _card(b, "ord"),
                           "hint": "Выберите договор в блоке ОРД карточки"}, ""
        if miss == "realization_pipeline":
            return state, {"label": "Воронка", "do": "confirm",
                           "hint": "Воронка выбирается при подтверждении брони"}, ""
        return state, {"label": "Подтвердить", "do": "confirm",
                       "hint": "Подтвердить бронь — сделка уйдёт на сбор запуска"}, ""

    if s == "prep":
        state = []
        done, total = b.creatives or (0, 0)
        if not b.sets:
            state.append(_alert("креативов нет", "warn"))
        elif not total:
            state.append(_fact("креативы", "не отправлены"))
        else:
            state.append({"type": "progress", "k": "креативы", "x": done, "y": total})
        if b.sets and len(b.erids) >= b.sets:
            state.append(_fact("ЕРИД", b.erids[0] if b.sets == 1 else f"{len(b.erids)} / {b.sets}"))
        elif b.sets and not b.kktu:
            state.append(_alert("ЕРИД: нет ККТУ", "warn"))
        elif b.sets:
            state.append(_fact("ЕРИД", f"ждёт {b.erid_share} %"))
        state += _check_chips(b)
        # Кнопка — первое несделанное по ходу сборки: креативы → ЕРИД → РК и пиксель.
        if not b.sets or not total or done < total:
            return state, {"label": "Креативы", "do": "prep",
                           "hint": "Сбор запуска: комплекты и согласование площадок"}, ""
        if len(b.erids) < b.sets and not b.kktu:
            return state, {"label": "ККТУ", "do": "link", "url": "/directory/advertisers",
                           "hint": "Без кода ККТУ у бренда ЕРИД не выпустить"}, ""
        blocked = any(r.state == NOT_YET for k, r in b.checks.items() if k in b.required)
        if len(b.erids) < b.sets or blocked:
            return state, {"label": "Сбор запуска", "do": "prep",
                           "hint": "Чек-лист сбора запуска"}, ""
        return state, _move("В размещение", "Запуск собран — перевести в «В размещении»"), ""

    if s == "live":
        dl = b.delivery
        if dl is None:
            state = [_alert("РК не собрана", "warn")]
        elif dl.get("done_pct") is None:
            state = [_fact("открутка", "статистики нет")]
        else:
            state = [{"type": "progress", "k": "открутка", "x": round(dl["done_pct"]),
                      "y": 100, "unit": "%"}]
            # Та же функция и те же условия, что у срочности: после конца флайта
            # недокрут — итог, а не отставание (иначе точка серая, а чип красный).
            lag = delivery_lag_pct(DealFacts(delivery_done_pct=dl.get("done_pct"),
                                             delivery_pace=dl.get("closed_pace")))
            if not dl.get("flight_over") and lag is not None and lag >= LAG_ALARM_PCT:
                state.append(_alert(f"отставание {_pct(lag).lstrip('+')} %"))
        if v.kind == "placement_ended":
            state.append(_alert("период закончился", "warn"))
        if dl is not None:
            state.append(_fact("площадок", f"{dl.get('placements_on', 0)} / {dl.get('placements', 0)}"))
            # РК реально крутится — первой плашкой, зелёной (владелец 01.10.2026): аккаунт
            # видит запуск, не открывая дашборд трафика.
            if dl.get("placements_on"):
                state.insert(0, {"type": "status", "tone": "good", "v": "запущена"})
        return state, None, "ведёт трафик"

    if s == "recon":
        state = _check_chips(b)
        dl = b.delivery or {}
        if dl.get("done_pct") is not None:
            state.append(_fact("расхождение", f"{_pct(dl['done_pct'] - 100)} %"))
        if dl.get("fact_shows") and dl.get("plan_show") and dl.get("plan_budget"):
            # Оценка «по цене плана», как в блоке РК карточки: настоящая цена закрытия
            # определится сверкой (владелец 28.09.2026 — показывать оценку).
            state.append(_fact("к закрытию ≈",
                               _rub(dl["fact_shows"] / dl["plan_show"] * dl["plan_budget"])))
        r = b.checks.get("fact_collected")
        if r is not None and r.state == OK:
            return state, _move("В ДО", "Факт собран — в документооборот"), ""
        return state, {"label": "Сверить", "do": "expand",
                       "hint": "Сводка РК — в раскрытой строке"}, ""

    if s == "ds_prep":
        state = _check_chips(b)
        if b.annex_sum:
            state.append(_fact("сумма ДС", _rub(b.annex_sum)))
        miss = _first_missing(b)
        if miss == "annex_generated":
            return state, {"label": "Сформировать ДС", "do": "link", "url": "/directory/annexes",
                           "hint": "Собрать приложение в конструкторе"}, ""
        if miss == "signatory_filled":
            return state, {"label": "Подписант", "do": "link", "url": "/directory/counterparties",
                           "hint": "Дозаполнить подписанта у плательщика"}, ""
        return state, _move("Согласовать", "Отправить ДС на согласование"), ""

    if s == "ds_agree":
        state = []
        if b.stage_days is not None:
            state.append(_fact("у клиента", f"{b.stage_days} дн."))
        if b.annex_no:
            state.append(_fact("приложение", b.annex_no))
        return state, _move("ДС подписано", "Приложите подписанное ДС и переведите дальше"), ""

    if s == "closing":
        state = _check_chips(b)
        if _first_missing(b):
            return state, {"label": "Документы", "do": "expand",
                           "hint": "Приложите документы в раскрытой строке"}, ""
        return state, _move("В ЭДО", "Документы собраны — в ЭДО"), ""

    if s == "edo":
        state = [_fact("на стадии", f"{b.stage_days} дн.")] if b.stage_days is not None else []
        return state, None, "у финменеджера"

    if s == "ord":
        state = [_fact("ЕРИД", str(len(b.erids)))] if b.erids else []
        return state, {"label": "Отчёт в ОРД", "do": "link", "url": "/accounts/ord",
                       "hint": "Подать акты в ОРД"}, ""

    if s == "pay":
        state = []
        if b.pay_due and b.today:
            left = (b.pay_due - b.today).days
            state.append(_fact("срок", _dm(b.pay_due)))
            state.append(_fact("до срока", f"{left} дн.") if left >= 0
                         else _alert(f"срок прошёл {-left} дн.", "warn"))
            if b.gross:
                state.append(_fact("к оплате", _rub(b.gross)))
            if left < 0:
                return state, {"label": "Дебиторка", "do": "link", "url": "/finance/receivables",
                               "hint": "Срок оплаты прошёл — проверить поступление"}, ""
        return state, None, "дебиторка у финансов"

    # Стадия, которой нет в таблице слотов (переименовали или завели новую): говорим
    # причиной срочности и её же кнопкой, как дашборд говорил до 28.09.2026.
    state = [_fact("", v.reason)] if v.reason else []
    act = None
    if v.cta:
        do = _LEGACY_DO.get(v.kind, "link")
        act = {"label": v.cta, "do": do, "hint": v.reason}
        if do == "link":
            act["url"] = ("/finance/receivables" if v.kind == "payment_overdue"
                          else f"/sales/deals/{b.code}")
    return state, act, ""


def row_state(b: Bundle) -> dict:
    state, action, note = _by_slot(b)
    has_alert = any(e["type"] == "alert" for e in state)
    pay_late = b.slot == "pay" and any(e["type"] == "alert" for e in state)
    tail = b.slot in TAIL_SLOTS and not pay_late
    return {
        "slot": b.slot, "stage_days": b.stage_days, "state": state,
        "action": action, "note": note,
        # ЭДО и Оплата — участок финменеджера: внизу списка. Просроченная оплата
        # всплывает в рабочую часть (владелец 27.09.2026).
        "tail": tail,
        # «Без срочности» — ничего не горит и тревог в строке нет: в самом конце списка.
        "calm": (not tail) and b.verdict.urgency == "normal" and not has_alert,
    }


# ─────────────────────────────── загрузка пачкой ───────────────────────────────

@dataclass
class Batch:
    ctxs: Dict[int, Ctx]
    erids: Dict[int, List[str]]
    set_count: Dict[int, int]
    pairs: Dict[int, tuple]
    kktu: Dict[int, bool]
    annex: Dict[int, tuple]          # сделка → (номер последнего приложения, сумма по сделке)
    campaigns: Dict[int, object]


def load(db, deals, today: date) -> Batch:
    """Окружение всех сделок очереди. Каждое свойство `stage_checks.Ctx` — одним
    запросом на всех; потом каждому Ctx подкладывается его доля."""
    from app.launch_prep.models import LaunchPrepCreativeSet
    from app.models import Counterparty
    from app.ad.stat_sources import OWN
    from app.sales.deal_delivery import campaigns_by_deal
    from app.sales.models import (SalesAnnex, SalesBrand, SalesDealAnnexAllocation,
                                  SalesDealFile, SalesMediaPlan)

    deals = list(deals)
    ids = [d.id for d in deals]
    empty = not ids

    kinds: dict = {}
    for did, kind in ([] if empty else db.query(SalesDealFile.deal_id, SalesDealFile.kind)
                      .filter(SalesDealFile.deal_id.in_(ids)).all()):
        kinds.setdefault(did, set()).add(kind)

    plans: dict = {}
    for p in ([] if empty else db.query(SalesMediaPlan)
              .filter(SalesMediaPlan.deal_id.in_(ids), SalesMediaPlan.status != "rejected")
              .order_by(SalesMediaPlan.deal_id, SalesMediaPlan.version.desc()).all()):
        plans.setdefault(p.deal_id, p)

    sets: dict = {}
    for s in ([] if empty else db.query(LaunchPrepCreativeSet)
              .filter(LaunchPrepCreativeSet.deal_id.in_(ids))
              .order_by(LaunchPrepCreativeSet.id).all()):
        sets.setdefault(s.deal_id, []).append(s)
    set_ids = [s.id for lst in sets.values() for s in lst]
    deal_of_set = {s.id: s.deal_id for lst in sets.values() for s in lst}

    reviews: dict = {}
    pairs: dict = {}
    if set_ids:
        for r in db.execute(text("""
            SELECT set_id, verdict FROM launch_prep_review
             WHERE kind = 'первичная_тт' AND pair_id IS NULL AND set_id = ANY(:s)
        """), {"s": set_ids}).mappings().all():
            reviews.setdefault(deal_of_set[r["set_id"]], []).append(r)
        for r in db.execute(text("""
            SELECT p.set_id, p.id, p.agreed_at, coalesce(pub.name, 'без имени') AS publisher
              FROM launch_prep_pair p
              JOIN launch_prep_target t ON t.id = p.target_id
              LEFT JOIN sales_publishers pub ON pub.id = t.publisher_id
             WHERE p.set_id = ANY(:s)
        """), {"s": set_ids}).mappings().all():
            pairs.setdefault(deal_of_set[r["set_id"]], []).append(r)

    campaigns = campaigns_by_deal(db, ids)
    cids = [c.id for c in campaigns.values()]
    deal_of_c = {c.id: did for did, c in campaigns.items()}
    placements: dict = {}
    facts: dict = {}
    if cids:
        for r in db.execute(text("""
            SELECT pl.campaign_id, pl.id, coalesce(pub.name, 'без имени') AS publisher,
                   pub.our_code, pl.weborama_pixel, pl.is_direct
              FROM ad_campaign_placement pl
              LEFT JOIN sales_publishers pub ON pub.id = pl.publisher_id
             WHERE pl.campaign_id = ANY(:c)
        """), {"c": cids}).mappings().all():
            placements.setdefault(deal_of_c[r["campaign_id"]], []).append(r)
        for r in db.execute(text("""
            SELECT campaign_id, placement_id, source, sum(shows) AS shows
              FROM ad_campaign_stat
             WHERE campaign_id = ANY(:c) AND source = ANY(:src)
             GROUP BY campaign_id, placement_id, source
        """), {"c": cids, "src": list(OWN)}).mappings().all():
            slot = (facts.setdefault(deal_of_c[r["campaign_id"]], {})
                    .setdefault(r["placement_id"], {"real": 0, "demo": 0}))
            slot["demo" if r["source"] == "demo" else "real"] += int(r["shows"] or 0)

    annex_n: dict = {}
    annex: dict = {}
    for did, amount, no, number in ([] if empty else db.query(
            SalesDealAnnexAllocation.deal_id, SalesDealAnnexAllocation.amount,
            SalesAnnex.no, SalesAnnex.number)
            .join(SalesAnnex, SalesAnnex.id == SalesDealAnnexAllocation.annex_id)
            .filter(SalesDealAnnexAllocation.deal_id.in_(ids))
            .order_by(SalesDealAnnexAllocation.id).all()):
        annex_n[did] = annex_n.get(did, 0) + 1
        label = (number or "").replace("Приложение", "").strip() or (f"№ {no}" if no else "")
        prev = annex.get(did, ("", 0.0))
        annex[did] = (label or prev[0], prev[1] + (amount or 0))

    cp_ids = {d.payer_counterparty_id or d.counterparty_id for d in deals} - {None}
    payers = ({c.id: c for c in db.query(Counterparty).filter(Counterparty.id.in_(cp_ids)).all()}
              if cp_ids else {})
    brand_ids = {d.brand_id for d in deals} - {None}
    kktu_of = ({b.id: bool(b.kktu_code) for b in db.query(SalesBrand)
                .filter(SalesBrand.id.in_(brand_ids)).all()} if brand_ids else {})

    ctxs = {}
    for d in deals:
        ctxs[d.id] = Ctx(db, d).preload(
            file_kinds=kinds.get(d.id, set()), plan=plans.get(d.id),
            sets=sets.get(d.id, []), first_reviews=reviews.get(d.id, []),
            pairs=pairs.get(d.id, []), campaign=campaigns.get(d.id),
            placements=placements.get(d.id, []), fact=facts.get(d.id, {}),
            annex_count=annex_n.get(d.id, 0),
            payer=payers.get(d.payer_counterparty_id or d.counterparty_id))

    return Batch(
        ctxs=ctxs,
        erids={did: [s.erid for s in lst if (s.erid or "").strip()] for did, lst in sets.items()},
        set_count={did: len(lst) for did, lst in sets.items()},
        pairs={did: (sum(1 for p in lst if p["agreed_at"]), len(lst)) for did, lst in pairs.items()},
        kktu={d.id: kktu_of.get(d.brand_id, False) for d in deals},
        annex=annex, campaigns=campaigns)


def build(db, deals, verdicts: Dict[int, Verdict], today: date,
          amounts: Optional[Dict[int, tuple]] = None) -> Dict[int, dict]:
    """Состояние строки для каждой сделки очереди: {сделка: row_state + stage_days}.

    `amounts` — {сделка: (до НДС, с НДС)} по правилу плана; роутер их уже посчитал."""
    from app.models import Counterparty
    from app.routers import launch_prep as lp
    from app.sales import stage_scope
    from app.sales.catalog import Catalog
    from app.sales.deal_delivery import delivery_by_deal
    from app.sales.mp_amounts import eff_net, gross_of, mp_amounts_by_deal
    from app.sales.models import SalesStageCheck
    from app.sales.stage_checks import scope_matches
    from app.sales.urgency import payment_due
    from app.sales.urgency_db import stage_since

    deals = list(deals)
    if not deals:
        return {}
    ids = [d.id for d in deals]
    cat = Catalog(db)
    marks = stage_scope.stage_services(db)
    batch = load(db, deals, today)
    since = stage_since(db, ids)
    rows_of: dict = {}
    for r in db.query(SalesStageCheck).all():
        rows_of.setdefault(r.stage_id, []).append(r)
    if amounts is None:
        mp_amt = mp_amounts_by_deal(db, ids)
        amounts = {d.id: (eff_net(d, mp_amt), gross_of(d, mp_amt)) for d in deals}
    slots = {d.id: slot_of(cat.by_id.get(d.our_stage_id)) for d in deals}
    delivery = delivery_by_deal(
        db, {did: c for did, c in batch.campaigns.items() if slots.get(did) in ("live", "recon")},
        today)
    share = round(lp.erid_threshold(db) * 100)
    pay_ids = {d.payer_counterparty_id or d.counterparty_id for d in deals
               if slots[d.id] == "pay"} - {None}
    terms = ({c.id: c.term_days for c in db.query(Counterparty.id, Counterparty.term_days)
              .filter(Counterparty.id.in_(pay_ids)).all()} if pay_ids else {})

    out = {}
    for d in deals:
        slot = slots[d.id]
        ctx = batch.ctxs[d.id]
        nxt = stage_scope.next_for(d, cat, marks)
        required = {r.check_key for r in rows_of.get(nxt.id if nxt else None, [])
                    if r.is_blocking and scope_matches(r.applies_when, d)}
        keys = [k for k, _ in SLOT_CHECKS.get(slot, ())]
        entered = since.get((d.id, d.our_stage_id))
        net, gross = amounts.get(d.id, (None, None))
        cp = d.payer_counterparty_id or d.counterparty_id
        b = Bundle(
            slot=slot, code=d.code or str(d.id),
            stage_days=(today - entered).days if entered else None,
            start_in=(d.period_from - today).days if d.period_from else None,
            end_in=(d.period_to - today).days if d.period_to else None,
            verdict=verdicts.get(d.id) or Verdict("normal"),
            has_mp=bool(ctx.plan) or "mp" in ctx.file_kinds,
            amount=net, gross=gross,
            checks={k: REGISTRY[k].fn(ctx) for k in keys},
            required=required,
            creatives=batch.pairs.get(d.id), sets=batch.set_count.get(d.id, 0),
            erids=batch.erids.get(d.id, []), kktu=batch.kktu.get(d.id, False),
            erid_share=share, pixel_ordered=bool(getattr(d, "weborama_pixel", False)),
            delivery=delivery.get(d.id),
            annex_no=(batch.annex.get(d.id) or ("", None))[0],
            annex_sum=(batch.annex.get(d.id) or ("", None))[1],
            pay_due=(payment_due(DealFacts(period_to=d.period_to, term_days=terms.get(cp)))
                     if slot == "pay" else None),
            today=today)
        out[d.id] = row_state(b)
    return out
