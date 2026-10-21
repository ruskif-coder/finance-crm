# -*- coding: utf-8 -*-
"""Итоговая сверка сделки (владелец 15.10.2026, схема docs/СХЕМА_контур_закрытия_еФарм.md, макет docs/Макет_закрытие_по_услугам.html).

ОДИН расчёт для блока в карточке, конструктора закрытия и ДС пакета:
- строки — из той же функции, что собирает таблицу ДС (`annex.plan_rows`): базовая услуга и допы (платные / бонусом);
- план и факт показов — из РК (`ad_campaign_stat`, свои источники), план — объём РК, без РК — объём CPM-строк МП;
- бонусный трафик — особенность РК (`bonus_traffic_mode/value`), в показы пересчитывается здесь;
- сумма базовой услуги — пином: fact (факт, не больше МП) · plan (сумма МП) · manual (руками, ≤ МП, только мастер/админ).

До «Отправить в ДО» всё считается на лету; нажатие замораживает показы и итог (`final_recon_deals`)."""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.final_recon.models import FinalReconDeal

MODES = ("fact", "plan", "manual")


class ClosingError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _r2(v) -> float:
    return round(float(v or 0) + 1e-9, 2)


def bonus_shows(mode: Optional[str], value, plan_shows: float, base_net: float) -> float:
    """Бонус в показах: % от плана, количество как есть, сумма — по CPM плана. Не заказан — 0."""
    v = float(value or 0)
    if not mode or v <= 0:
        return 0.0
    if mode == "pct":
        return plan_shows * v / 100.0
    if mode == "qty":
        return v
    if mode == "rub":
        cpm = (base_net / plan_shows * 1000.0) if plan_shows else 0.0
        return v / cpm * 1000.0 if cpm else 0.0
    return 0.0


def default_mode(plan_shows: float, fact_shows: Optional[float]) -> str:
    """План выполнен — по умолчанию «Под МП», иначе «По факту» (владелец 14.10)."""
    return "plan" if fact_shows is not None and plan_shows and fact_shows >= plan_shows else "fact"


UNDER_PCT, OVER_PCT = 97.0, 103.0       # пороги вывода и цвета факта — одни (дизайн 15.10.2026, docs/IS.zip)


def _sp(n) -> str:
    return f"{round(n):,}".replace(",", " ")


def verdict(plan: float, fact: Optional[float], bonus: float) -> dict:
    """Вывод по выполнению плана показов: < 97 % — недокрут; 97–103 % — в плане; выше — перекрут, но в пределах заказанного
    бонуса перекрутом не считается (бонус меняет только подпись, не сумму)."""
    if fact is None:
        return {"code": "no_fact", "tone": "off", "text": "Факта ещё нет"}
    if not plan:
        return {"code": "no_plan", "tone": "off", "text": "Плана показов нет"}
    pct = fact / plan * 100
    if pct < UNDER_PCT:
        return {"code": "under", "tone": "bad",
                "text": f"Недокрут {_sp(plan - fact)} · {f'{100 - pct:.1f}'.replace('.', ',')} %"}
    if pct <= OVER_PCT or (bonus and fact <= plan + bonus):
        return {"code": "in_plan", "tone": "ok", "text": "В плане"}
    over = fact - plan - (bonus or 0)
    return {"code": "over", "tone": "warn", "text": f"Перекрут {_sp(over)}"}


def period_of_deal(deal) -> Optional[str]:
    return deal.period_from.strftime("%Y-%m") if deal.period_from else None


def adfox_freshness(last_by_source: dict, date_end, yesterday) -> Optional[dict]:
    """Плашка «данные Adfox на <дату> — уточни у трафика» (долг 14.10).

    Adfox грузится руками и отстаёт от ночного съёма DSP. Опора — последний день DSP,
    а без него — конец РК (не позже вчера). None — Adfox у РК нет или он не отстаёт."""
    ad = last_by_source.get("adfox")
    if not ad:
        return None
    ref = last_by_source.get("dsp") or last_by_source.get("ms")
    if ref is None and date_end is not None:
        ref = min(date_end, yesterday)
    if ref is None or ad >= ref:
        return None
    return {"adfox_as_of": ad.isoformat(), "reference": ref.isoformat()}


def _last_days(db: Session, campaign_id: int) -> dict:
    from sqlalchemy import text
    rows = db.execute(text("SELECT source, max(date) FROM ad_campaign_stat WHERE campaign_id = :c "
                           "GROUP BY source"), {"c": campaign_id}).all()
    return {r[0]: r[1] for r in rows}


def _freshness(db: Session, deal) -> Optional[dict]:
    from datetime import timedelta

    from app.dsp.stat_daily import today_msk
    from app.sales.deal_delivery import campaigns_by_deal
    camp = campaigns_by_deal(db, [deal.id]).get(deal.id)
    if not camp:
        return None
    return adfox_freshness(_last_days(db, camp.id), getattr(camp, "date_end", None),
                           today_msk() - timedelta(days=1))


def _facts(db: Session, deal) -> tuple:
    """(план показов, факт показов | None) по РК сделки; без РК — план из CPM-строк МП, факта нет."""
    from app.sales.deal_delivery import campaigns_by_deal
    from app.traffic import delivery_facts as td
    camp = campaigns_by_deal(db, [deal.id]).get(deal.id)
    if not camp:
        return None, None
    f = td._facts(db, [camp.id]).get(camp.id)
    return float(camp.plan_show or 0), (float(f["shows"]) if f and f.get("shows") is not None else None)


# Что вводит аккаунт — по МОДЕЛИ строки МП, не по названию услуги (макет «Закрытие по услугам» 14.10, владелец 19.10.2026):
#   cpm   — показы + клики;  video — показы + досмотры 100 % + клики, VTR считается;
#   cpc   — клики (объём строки в кликах);  fix — объём пакетами + показы справочно (на сумму не влияют).
FIX_MODELS = {"FIX", "ФИКС", "ПАКЕТ"}
_VIDEO = ("видео", "video", "in-stream", "instream", "olv")


def row_kind(r: dict) -> str:
    from app.sales import mp_row
    m = (r.get("model") or "").strip().upper()
    if m in FIX_MODELS:
        return "fix"
    if mp_row.is_cpc(m):
        return "cpc"
    text_ = " ".join(str(r.get(k) or "") for k in ("format", "position")).lower()
    return "video" if any(w in text_ for w in _VIDEO) else "cpm"


def _num_or_none(v):
    if v is None or v == "":
        return None
    v = float(v)
    if v < 0:
        raise ClosingError(400, "Факт — число не меньше нуля")
    return v


def _entries(db: Session, deal_id: int) -> dict:
    """Факт, введённый аккаунтом: {строка МП: запись}."""
    from app.final_recon.models import FinalReconFactEntry
    return {e.mp_row_id: e for e in db.query(FinalReconFactEntry).filter(FinalReconFactEntry.deal_id == deal_id).all()}


def _entry_rows(base: list) -> list:
    """Строки МП, по которым вводится факт: базовые, с объёмом и id."""
    return [r for r in base if r.get("row_id") and (r.get("volume") or 0) > 0]


def _fact_entry(db: Session, deal, base: list, has_rk: bool, frozen: bool) -> dict:
    """Ввод факта аккаунтом (владелец 19.10.2026): только в контуре аккаунта. Факт сделки — когда введены ВСЕ строки."""
    from app.models import User
    ent = _entries(db, deal.id)
    rows = _entry_rows(base)
    last = max(ent.values(), key=lambda e: e.entered_at, default=None)
    by = db.get(User, last.entered_by) if last and last.entered_by else None
    complete = bool(rows) and all(r["row_id"] in ent for r in rows)
    from app.sales.models import SalesDealFile
    rep = db.query(SalesDealFile).filter(SalesDealFile.deal_id == deal.id, SalesDealFile.kind == "report").first()

    def _row(r):
        e = ent.get(r["row_id"])
        shows = float(e.fact_volume) if e else None
        done = int(e.fact_views_completed) if e and e.fact_views_completed is not None else None
        return {"row_id": r["row_id"], "kind": row_kind(r),
                "name": " · ".join(x for x in (r.get("position"), r.get("device")) if x),
                "model": r.get("model"), "volume": float(r.get("volume") or 0),
                "fact": shows,
                "clicks": int(e.fact_clicks) if e and e.fact_clicks is not None else None,
                "completed": done,
                "vtr": round(done / shows * 100, 1) if (done is not None and shows) else None,
                "reference_shows": int(e.fact_reference_shows) if e and e.fact_reference_shows is not None else None}
    return {"can_enter": (not has_rk) and (not frozen) and bool(rows),
            "report": {"filename": rep.filename} if rep else None,
            "complete": complete,
            "rows": [_row(r) for r in rows],
            "total": float(sum(ent[r["row_id"]].fact_volume for r in rows)) if complete else None,
            "plan": float(sum(r.get("volume") or 0 for r in rows)),
            "note": last.source_note if last else None,
            "by": (by.name or by.email) if by else None,
            "at": last.entered_at.isoformat(timespec="seconds") if last else None}


def save_fact(db: Session, deal, values: dict, note: Optional[str], user) -> dict:
    """Сохранить факт по строкам МП. Только контур аккаунта (полный цикл — факт из статистики) и до «Отправить в ДО»."""
    from app.final_recon.models import FinalReconFactEntry
    from app.sales import annex as annex_mod
    from app.final_recon import flow as FLOW
    if not FLOW.is_account(db, deal):
        raise ClosingError(409, "Услуга полного цикла — факт приходит из статистики DSP / Adfox, вручную не вводится")
    rec = db.get(FinalReconDeal, deal.id)
    if rec and rec.sent_at:
        raise ClosingError(409, "Сделка уже отправлена в ДО — факт не меняется")
    allowed = {r["row_id"] for r in _entry_rows([r for r in annex_mod.plan_rows(db, [deal.id]) if r.get("kind") != "extra"])}
    if not values:
        raise ClosingError(400, "Введите факт хотя бы по одной строке")
    norm = {}
    for rid, v in values.items():
        if rid not in allowed:
            raise ClosingError(400, "Строки нет в медиаплане сделки — обновите страницу")
        v = v if isinstance(v, dict) else {"fact": v}     # старый вызов — одно число на строку
        fact = _num_or_none(v.get("fact"))
        if fact is None:
            raise ClosingError(400, "Основной факт строки (показы / пакеты / клики) — обязателен")
        norm[rid] = (fact, _num_or_none(v.get("clicks")), _num_or_none(v.get("completed")), _num_or_none(v.get("reference_shows")))
    ent = _entries(db, deal.id)
    now = datetime.utcnow()
    for rid, (fact, clicks, done, ref) in norm.items():
        e = ent.get(rid) or FinalReconFactEntry(deal_id=deal.id, mp_row_id=rid)
        e.fact_volume = round(fact, 2)
        e.fact_clicks = int(clicks) if clicks is not None else None
        e.fact_views_completed = int(done) if done is not None else None
        e.fact_reference_shows = int(ref) if ref is not None else None
        e.source_note = (note or "").strip()[:300] or None
        e.entered_by, e.entered_at = getattr(user, "id", None), now
        db.add(e)
    if rec:
        rec.confirmed_at = rec.confirmed_by = None      # факт изменился — подтверждение сверки снимается
    db.flush()
    return compute(db, deal, rec=rec)


def _user_name(db: Session, uid: Optional[int]) -> Optional[str]:
    from app.models import User
    u = db.get(User, uid) if uid else None
    return (u.name or u.email) if u else None


def _closing_to(db: Session, deal) -> Optional[dict]:
    """На кого закрываем: контрагент доходного договора сделки (у контура аккаунта — посредник; владелец 19.10.2026:
    посредника присоединяем к агентству как контрагента, своей схемы «первичного заказчика» нет)."""
    if not deal.ord_final_contract_id:
        return None
    from app.models import Contract, Counterparty
    c = db.get(Contract, deal.ord_final_contract_id)
    cp = db.get(Counterparty, c.counterparty_id) if c and c.counterparty_id else None
    name = (cp.name if cp else None) or (c.counterparty_name if c else None)
    return {"name": name, "inn": (cp.inn if cp else None) or (c.inn if c else None),
            "contract": c.contract_number if c else None} if (c and name) else None


def save_cost(db: Session, deal, cost: Optional[float], user) -> dict:
    """Себестоимость сделки без НДС — вносит аккаунт на закрытии (макет 14.10). Пусто — снять. После «Отправить в ДО» — нельзя."""
    rec = _rec(db, deal.id)
    if rec.sent_at:
        raise ClosingError(409, "Сделка уже отправлена в ДО — себестоимость не меняется")
    if cost is not None and float(cost) < 0:
        raise ClosingError(400, "Себестоимость — число не меньше нуля")
    rec.cost_net = _r2(float(cost)) if cost is not None else None
    rec.updated_by, rec.updated_at = getattr(user, "id", None), datetime.utcnow()
    db.flush()
    return compute(db, deal, rec=rec)


def _plan_fact(db: Session, deal, rec, base: list, base_net: float) -> dict:
    """План, факт и бонус в показах. Контур аккаунта (владелец 19.10.2026): факт вводит аккаунт — решает ЦИКЛ услуги, а не наличие РК
    (у части таких сделок стадии заводят пустую РК, и по ней «факта нет» навсегда). Отправленная в ДО сверка — замороженные числа."""
    from app.final_recon import flow as FLOW
    from app.sales import mp_row
    plan_mp = float(sum((r["volume"] or 0) for r in base if mp_row.is_cpm(r.get("model"))))
    account = FLOW.is_account(db, deal)
    plan_rk, fact = (None, None) if account else _facts(db, deal)
    frozen = bool(rec and rec.sent_at)
    entry = _fact_entry(db, deal, base, not account, frozen)
    source = "stats" if fact is not None else None
    if account and entry["complete"]:
        plan_mp, fact, source = entry["plan"], entry["total"], "entered"
    if frozen:
        plan, fact = float(rec.plan_shows or 0), (float(rec.fact_shows) if rec.fact_shows is not None else None)
        bonus = float(rec.bonus_shows or 0)
    else:
        plan = plan_rk or plan_mp
        bonus = bonus_shows(deal.bonus_traffic_mode, deal.bonus_traffic_value, plan, base_net)
    return {"plan": plan, "fact": fact, "bonus": bonus, "source": source, "entry": entry, "frozen": frozen}


def _money(db: Session, deal, rec, pf: dict, base_net: float, extras: list) -> dict:
    """Режим и суммы ДС: по факту / под МП / вручную, платные допы, НДС, СК. СК (владелец 14.10): «скидка в счёт» уменьшает сумму ДС;
    «постоплата» — отдельным документом потом, сумму ДС не трогает."""
    from app.final_recon import sk as SK
    from app.sales.mp_amounts import mp_amounts_by_deal, vat_pct_of
    plan, fact = pf["plan"], pf["fact"]
    mode = (rec.ds_mode if rec and rec.ds_mode else None) or default_mode(plan, fact)
    by_fact = _r2(min(fact, plan) / plan * base_net) if (fact is not None and plan) else None
    amounts = {"fact": by_fact, "plan": base_net,
               "manual": _r2(rec.ds_manual_net) if rec and rec.ds_manual_net is not None else None}
    base_ds = amounts.get(mode)
    if pf["frozen"] and rec.base_net is not None:
        base_ds = _r2(rec.base_net)
    paid_extras = _r2(sum((e["amount"] or 0) for e in extras if not e.get("bonus")))
    vat = vat_pct_of(deal, mp_amounts_by_deal(db, [deal.id]))
    total_net = _r2((base_ds or 0) + paid_extras) if base_ds is not None else None
    sk = SK.of_deal(db, deal)
    sk_net = _r2(total_net * float(sk["percent"] or 0) / 100.0) if (total_net is not None and sk["mode"] and sk["percent"]) else 0.0
    if sk["mode"] == "скидка в счёт" and total_net is not None:
        total_net = _r2(total_net - sk_net)
    return {"mode": mode, "amounts": amounts, "base_ds": base_ds, "paid_extras": paid_extras, "vat": vat, "total_net": total_net,
            "sk": {**sk, "amount_net": sk_net,
                   "before_net": _r2(total_net + sk_net) if (total_net is not None and sk["mode"] == "скидка в счёт") else total_net}}


def _lines(base: list, extras: list, pf: dict) -> list:
    """Строки блока. Название — как в ДС: позиция и поверхность; факт строки — введённый аккаунтом, иначе доля факта РК по её объёму."""
    fact, entry = pf["fact"], pf["entry"]
    vol_base = float(sum((r.get("volume") or 0) for r in base)) or 0.0
    entered = {x["row_id"]: x["fact"] for x in entry["rows"]} if pf["source"] == "entered" else {}

    def row_fact(r):
        if r.get("row_id") in entered:
            return round(entered[r.get("row_id")])
        return round(fact * (r.get("volume") or 0) / vol_base) if (fact is not None and vol_base) else None
    return ([{"kind": "base", "name": " · ".join(x for x in (r.get("position"), r.get("device")) if x),
              "model": r.get("model"), "volume": r.get("volume"), "unit_price": r.get("unit_price"), "fact": row_fact(r),
              "plan_net": _r2(r["amount"])} for r in base]
            + [{"kind": "extra", "name": e.get("position"), "model": e.get("model"), "bonus": bool(e.get("bonus")),
                "unit_price": None if e.get("bonus") else e.get("unit_price"),
                "net": 0.0 if e.get("bonus") else _r2(e["amount"])} for e in extras])


def _meta(db: Session, rec, frozen: bool, base_net: float, paid_extras: float) -> dict:
    """Отметки сверки: подтверждение, отправка, себестоимость, «закрыть без документов», кто поставил ручную сумму."""
    has = rec is not None
    return {
        "frozen": frozen, "sent_at": rec.sent_at if has else None,
        "confirmed": bool(has and rec.confirmed_at), "confirmed_at": rec.confirmed_at if has else None,
        "cost_net": _r2(float(rec.cost_net)) if has and rec.cost_net is not None else None,
        # Бонусное размещение (19.10.2026): сумма МП 0 ₽ (база и платные допы) → «Закрыть без документов», сразу в архив, без ДС.
        "no_docs": {"eligible": (not frozen) and abs(base_net or 0) < 0.005 and abs(paid_extras or 0) < 0.005,
                    "closed_at": rec.closed_no_docs_at.isoformat(timespec="seconds") if has and rec.closed_no_docs_at else None,
                    "closed_by": _user_name(db, rec.closed_no_docs_by) if has and rec.closed_no_docs_by else None},
        "manual_by": _user_name(db, rec.updated_by) if (has and rec.ds_mode == "manual") else None,   # подпись на пине «Вручную»
        "manual_volume": int(rec.ds_manual_volume) if has and rec.ds_manual_volume else None,
        "mode_set": bool(has and rec.ds_mode),
    }


def compute(db: Session, deal, *, rec: Optional[FinalReconDeal] = None) -> dict:
    """Состояние блока «Итоговая сверка» сделки. `rec` — строка сверки (если уже загружена). Шаги — `_plan_fact`, `_money`, `_lines`, `_meta`."""
    from app.sales import annex as annex_mod
    rec = rec if rec is not None else db.get(FinalReconDeal, deal.id)
    rows = annex_mod.plan_rows(db, [deal.id])
    base = [r for r in rows if r.get("kind") != "extra"]
    extras = [r for r in rows if r.get("kind") == "extra"]
    base_net = _r2(sum(r["amount"] or 0 for r in base))
    pf = _plan_fact(db, deal, rec, base, base_net)
    mo = _money(db, deal, rec, pf, base_net, extras)
    plan, fact, mode, total_net = pf["plan"], pf["fact"], mo["mode"], mo["total_net"]
    meta = _meta(db, rec, pf["frozen"], base_net, mo["paid_extras"])
    return {
        "deal_id": deal.id, "deal_code": deal.code,
        "calculated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "period": period_of_deal(deal),
        "fact_pct": round(fact / plan * 100, 1) if (fact is not None and plan) else None,
        "thresholds": {"under": UNDER_PCT, "over": OVER_PCT},     # пороги недо/перекрута — экран читает отсюда, своей копии не держит
        "sk": mo["sk"], **meta,
        "plan_shows": round(plan) if plan else 0,
        "fact_shows": round(fact) if fact is not None else None,
        "bonus": {"mode": deal.bonus_traffic_mode, "value": float(deal.bonus_traffic_value) if deal.bonus_traffic_value else None,
                  "shows": round(pf["bonus"])},
        "bonus_fact_shows": round(max((fact or 0) - plan, 0)) if fact is not None else None,
        "verdict": verdict(plan, fact, pf["bonus"]),
        "adfox_stale": _freshness(db, deal),
        "fact_source": pf["source"],
        "closing_to": _closing_to(db, deal),
        "fact_entry": pf["entry"],
        "lines": _lines(base, extras, pf),
        "base_plan_net": base_net,
        # Единицы в ДС: ручные — при «Вручную», по факту — факт (не больше плана), иначе план.
        "ds_volume": (int(rec.ds_manual_volume) if (mode == "manual" and rec and rec.ds_manual_volume)
                      else (round(min(fact, plan)) if (mode == "fact" and fact is not None) else round(plan) if plan else None)),
        "amounts": mo["amounts"],
        "mode": mode, "mode_default": default_mode(plan, fact),
        "base_ds_net": mo["base_ds"],
        "paid_extras_net": mo["paid_extras"],
        "vat_rate": mo["vat"],
        "total_net": total_net,
        "total_gross": _r2(total_net * (1 + (mo["vat"] or 0) / 100.0)) if total_net is not None else None,
    }


def _rec(db: Session, deal_id: int) -> FinalReconDeal:
    rec = db.get(FinalReconDeal, deal_id)
    if rec is None:
        rec = FinalReconDeal(deal_id=deal_id)
        db.add(rec)
        # Сразу в сессию: `db.get` не видит НЕзаписанный объект, и второй вызов после отказа (400) создал бы дубль ключа.
        db.flush()
    return rec


def set_mode(db: Session, deal, mode: str, manual_net: Optional[float], user, *, privileged: bool,
             manual_volume: Optional[float] = None) -> dict:
    """Пин суммы ДС. «Вручную» — только мастер/админ и не больше суммы МП; после «Отправить в ДО» — тоже только они."""
    if mode not in MODES:
        raise ClosingError(400, "Сумма в ДС: по факту / под МП / вручную")
    rec = _rec(db, deal.id)
    if rec.sent_at and not privileged:
        raise ClosingError(403, "Сделка уже отправлена в ДО — сумму меняет мастер или админ")
    if mode == "manual":
        if not privileged:
            raise ClosingError(403, "Ручная сумма — только мастер или админ")
        state = compute(db, deal, rec=rec)
        v = float(manual_net or 0)
        if v <= 0:
            raise ClosingError(400, "Укажите сумму больше нуля")
        if v > state["base_plan_net"] + 0.005:
            raise ClosingError(400, f"Сумма не больше суммы МП ({state['base_plan_net']:,.2f})".replace(",", " "))
        rec.ds_manual_net = _r2(v)
        rec.ds_manual_volume = int(round(manual_volume)) if manual_volume and manual_volume > 0 else None
    rec.ds_mode = mode
    rec.confirmed_at = rec.confirmed_by = None      # расчёт изменился — подтверждение снимается
    rec.updated_by = getattr(user, "id", None)
    rec.updated_at = datetime.utcnow()
    if rec.sent_at:                      # отправленная: итог пересчитывается под новый пин
        rec.base_net = None
        db.flush()
        rec.base_net = compute(db, deal, rec=rec)["base_ds_net"]
    db.flush()
    return compute(db, deal, rec=rec)


def freeze(db: Session, deal, user) -> dict:
    """«Отправить в ДО»: заморозить показы, бонус, пин и итог базовой услуги. Повтор — не перезаписывает."""
    rec = _rec(db, deal.id)
    if rec.sent_at:
        return compute(db, deal, rec=rec)
    state = compute(db, deal, rec=rec)
    if state["base_ds_net"] is None:
        raise ClosingError(409, "Сумма в ДС не определена: факта ещё нет — выберите «Под МП» или дождитесь статистики")
    rec.plan_shows = state["plan_shows"]
    rec.fact_shows = state["fact_shows"]
    rec.bonus_shows = state["bonus"]["shows"]
    rec.ds_mode = state["mode"]
    rec.base_net = state["base_ds_net"]
    rec.sent_at = datetime.utcnow()
    rec.sent_by = getattr(user, "id", None)
    db.flush()
    return compute(db, deal, rec=rec)


def confirm(db: Session, deal, on: bool, user) -> dict:
    """«Подтвердить сверку» / снять подтверждение. После «Отправить в ДО» не меняется."""
    rec = _rec(db, deal.id)
    if rec.sent_at:
        raise ClosingError(409, "Сделка уже отправлена в ДО — сверка зафиксирована")
    state = compute(db, deal, rec=rec)
    if on and state["base_ds_net"] is None:
        raise ClosingError(409, "Сверка не посчиталась: факта ещё нет — выберите «Под МП» или дождитесь статистики")
    rec.confirmed_at = datetime.utcnow() if on else None
    rec.confirmed_by = getattr(user, "id", None) if on else None
    db.flush()
    return compute(db, deal, rec=rec)
