# -*- coding: utf-8 -*-
"""«План продаж» — цели по месяцам и их выполнение (владелец 24.10.2026, docs/ПЛАН_план_продаж.md).

Цели вводятся (`sales_targets`), выполнение — считается из сделок, руками не вводится:
  · факт      — фактический слой (документооборот, архив);
  · в работе  — реализуемый слой (со «Сборки»);
  · выполнено — факт + в работе: с этим сравнивается цель;
  · прогноз   — выполнено + планируемые по светофору: зелёный 100 %, оранжевый 50 %, серый 0.
Месяц — финансовый период сделки (`period_from`), сумма — как в реестре (`mp_amounts.eff_net`), без НДС. Сорвавшиеся
и рекламодатели «не в выручке» не считаются — как на дашборде продаж. Светофор — одним правилом с остальной системой
(`probability.effective`).

Разрезы независимые: общая цель, по услуге, по продажнику. Сделка без услуги / продажника — в строке «без услуги» /
«без продажника» (в общую цель входит), иначе сумма разреза ложно не сходилась бы с общей.

Модуль не импортирует роутеры: его зовёт ночной снимок (`python -m app.sales.plan_snapshot`).
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import func, text

from app.sales import probability

SCOPES = ("общий", "услуга", "продажник")
NO_SERVICE, NO_REP = "без услуги", "без продажника"
ORANGE_SHARE = 0.5
KEEP_DAYS = 90
Key = Tuple[str, int]


def empty() -> dict:
    return {"fact": 0.0, "work": 0.0, "green": 0.0, "orange": 0.0, "grey": 0.0}


def done(c: dict) -> float:
    return c["fact"] + c["work"]


def forecast(c: dict) -> float:
    return done(c) + c["green"] + c["orange"] * ORANGE_SHARE


def _bucket(d) -> Optional[str]:
    if d.layer == "фактические":
        return "fact"
    if d.layer == "реализуемые":
        return "work"
    if d.layer == "планируемые":
        return probability.effective(d.light, d.stage_key) or "grey"
    return None


def aggregate(deals: Iterable) -> Dict[Key, List[dict]]:
    """{(разрез, id): [12 ячеек]} по сделкам с полями month (1–12), layer, light, stage_key, amount, service_id,
    sales_rep_id. Разрез «общий» и строки «без …» — с id 0."""
    out: Dict[Key, List[dict]] = {}
    for d in deals:
        b = _bucket(d)
        if b is None:
            continue
        keys = [("общий", 0),
                ("услуга", d.service_id) if d.service_id else (NO_SERVICE, 0),
                ("продажник", d.sales_rep_id) if d.sales_rep_id else (NO_REP, 0)]
        for k in keys:
            row = out.setdefault(k, [empty() for _ in range(12)])
            row[d.month - 1][b] += float(d.amount or 0)
    return out


_DEALS = text("""
    SELECT d.id, d.code, d.title, extract(month FROM d.period_from)::int AS month, d.service_id, d.sales_rep_id,
           d.probability_color AS light, s.stage_key, s.name AS stage, s.money_layer AS layer, d.amount,
           coalesce(nullif(a.short_name, ''), a.name) AS advertiser, b.name AS brand, r.name AS rep, sv.name AS service
      FROM sales_deals d
      JOIN sales_stages s ON s.id = d.our_stage_id
      LEFT JOIN sales_advertisers a ON a.id = d.advertiser_id
      LEFT JOIN sales_brands b ON b.id = d.brand_id
      LEFT JOIN sales_reps r ON r.id = d.sales_rep_id
      LEFT JOIN sales_services sv ON sv.id = d.service_id
     WHERE d.period_from >= make_date(:y, 1, 1) AND d.period_from < make_date(:y + 1, 1, 1)
       AND NOT coalesce(s.is_lost, false) AND s.money_layer IS NOT NULL
       AND NOT coalesce(a.exclude_from_revenue, false)
""")


def deals_of(db, year: int) -> list:
    """Сделки года с суммой как в реестре (медиаплан, иначе сделка)."""
    from app.sales.mp_amounts import mp_amounts_by_deal
    rows = db.execute(_DEALS, {"y": year}).all()
    mp = mp_amounts_by_deal(db, [r.id for r in rows])
    return [_Deal(r, float(mp[r.id][0]) if r.id in mp else float(r.amount or 0)) for r in rows]


class _Deal:
    __slots__ = ("id", "code", "title", "month", "service_id", "sales_rep_id", "light", "stage_key", "stage", "layer",
                 "amount", "advertiser", "brand", "rep", "service")

    def __init__(self, r, amount: float):
        for k in self.__slots__:
            setattr(self, k, getattr(r, k, None))
        self.amount = amount


def targets_of(db, year: int) -> Dict[Key, List[Optional[float]]]:
    out: Dict[Key, List[Optional[float]]] = {}
    for scope, sid, rid, month, amount in db.execute(text(
            "SELECT scope, service_id, sales_rep_id, month, amount FROM sales_targets WHERE year = :y"), {"y": year}).all():
        k = (scope, sid or rid or 0)
        out.setdefault(k, [None] * 12)[month - 1] = float(amount)
    return out


def week_ago(db, year: int, today: date) -> Dict[Key, List[Optional[float]]]:
    """Прогноз по последнему снимку не позже чем неделю назад: {(разрез, id): [12 прогнозов]}."""
    day = db.execute(text("SELECT max(day) FROM sales_plan_snapshots WHERE year = :y AND day <= :d"),
                     {"y": year, "d": today - timedelta(days=7)}).scalar()
    out: Dict[Key, List[Optional[float]]] = {}
    if day is None:
        return out
    for scope, key, month, fc in db.execute(text(
            "SELECT scope, key_id, month, forecast FROM sales_plan_snapshots WHERE year = :y AND day = :d"),
            {"y": year, "d": day}).all():
        out.setdefault((scope, key), [None] * 12)[month - 1] = float(fc)
    return out


def _names(db, keys: Iterable[Key]) -> Tuple[dict, dict]:
    """Услуги {id: (id, имя, группа, порядок, действующая)} и продажники {id: (имя, активен)}. Продажник неактивен,
    если отключён профиль или его учётка."""
    sids = [k for s, k in keys if s == "услуга"]
    rids = [k for s, k in keys if s == "продажник"]
    svc = {r[0]: r for r in db.execute(text(
        'SELECT id, name, "group", sort_order, is_active FROM sales_services WHERE is_active OR id = ANY(:i)'),
        {"i": sids or [0]}).all()}
    reps = {r[0]: (r[1], bool(r[2])) for r in db.execute(text(
        "SELECT r.id, r.name, r.is_active AND coalesce(u.is_active, 1) = 1 FROM sales_reps r "
        "LEFT JOIN users u ON u.id = r.user_id WHERE r.id = ANY(:i)"), {"i": rids or [0]}).all()}
    return svc, reps


def _active_sellers(db) -> set:
    """Активные продавцы — по роли (staff_group 'seller'), а не по справочнику профилей: строкой всегда, чтобы
    поставить цель новичку без сделок."""
    return {r[0] for r in db.execute(text(
        "SELECT r.id FROM sales_reps r JOIN users u ON u.id = r.user_id JOIN roles ro ON ro.id = u.role_id "
        "WHERE r.is_active AND u.is_active = 1 AND ro.staff_group = 'seller'")).all()}


def screen(db, year: int, own: Optional[list] = None, today: Optional[date] = None) -> dict:
    """Строки экрана: общая цель, продажники (+ «без продажника»), услуги по группам (+ «без услуги»).
    `own` — id продажников «своих» (None — все): «свои» видят общую цель и свою строку."""
    from app.timez import msk_now
    today = today or msk_now().date()
    rows = rows_for(db, year, aggregate(deals_of(db, year)), targets_of(db, year), week_ago(db, year, today), own)
    return {"year": year, "today": today.isoformat(), "rows": rows, "own": own is not None}


def rows_for(db, year: int, cells: dict, goals: dict, week: dict, own: Optional[list] = None) -> List[dict]:
    """Строки по готовым ячейкам. Неактивный продажник (владелец 24.10.2026) — последним среди продажников, если за год
    есть выполненное (факт + в работе); без него — скрыт, даже с целью."""
    keys = set(cells) | set(goals) | {("общий", 0)} | {("продажник", r) for r in _active_sellers(db)}
    svc, reps = _names(db, keys)
    keys |= {("услуга", sid) for sid, r in svc.items() if r[4]}   # все действующие услуги — строкой, даже без цели
    rows = []
    for scope, key in keys:
        if own is not None and not (scope == "общий" or (scope == "продажник" and key in own)):
            continue
        cs = cells.get((scope, key)) or [empty() for _ in range(12)]
        rep_name, rep_active = reps.get(key, (None, True)) if scope == "продажник" else (None, True)
        if scope == "продажник" and not rep_active and not sum(done(c) for c in cs):
            continue
        gl = goals.get((scope, key)) or [None] * 12
        wk = week.get((scope, key)) or [None] * 12
        row = {"scope": scope, "key_id": key, "months": [
            {**{k: round(v, 2) for k, v in c.items()}, "done": round(done(c), 2), "forecast": round(forecast(c), 2),
             "goal": gl[m], "forecast_week_ago": wk[m]} for m, c in enumerate(cs)]}
        if scope == "общий":
            row.update(name="Общая цель", order=(0, 0, 0, ""))
        elif scope == "продажник":
            row.update(name=rep_name or f"продажник #{key}", inactive=not rep_active,
                       order=(1, 0, 0 if rep_active else 1, rep_name or ""))
        elif scope == NO_REP:
            row.update(name="Без продажника", order=(1, 1, 0, ""))
        elif scope == "услуга":
            r = svc.get(key)
            row.update(name=r[1] if r else f"услуга #{key}", group=(r[2] if r else None) or "—",
                       order=(2, 0, 0, f"{(r[2] if r else '') or '~'}|{(r[3] if r else 0):05d}|{r[1] if r else ''}"))
        elif scope == NO_SERVICE:
            row.update(name="Без услуги", group=None, order=(2, 1, 0, ""))
        rows.append(row)
    rows.sort(key=lambda r: r.pop("order"))
    return rows


# ── цели ────────────────────────────────────────────────────────────────────
class TargetItem(BaseModel):
    month: int
    scope: str
    key_id: Optional[int] = None
    amount: Optional[float] = None          # None — снять цель


def _label(year: int, month: int, scope: str, key: int) -> str:
    """Начало строки журнала — ключ ячейки: по нему же находится история (`history`)."""
    return f"{year}-{month:02d} · {scope} #{key or 0}"


def _rub(v: Optional[float]) -> str:
    return "—" if v is None else f"{round(v):,}".replace(",", " ")


def _check(db, item: TargetItem) -> Tuple[Optional[int], Optional[int]]:
    if not 1 <= item.month <= 12:
        raise HTTPException(400, "Месяц — от 1 до 12")
    if item.scope not in SCOPES:
        raise HTTPException(400, f"Разрез: {', '.join(SCOPES)}")
    if item.amount is not None and item.amount < 0:
        raise HTTPException(400, "Цель не может быть отрицательной")
    if item.scope == "общий":
        return None, None
    if not item.key_id:
        raise HTTPException(400, f"Для разреза «{item.scope}» нужен id")
    table = "sales_services" if item.scope == "услуга" else "sales_reps"
    if not db.execute(text(f"SELECT 1 FROM {table} WHERE id = :i"), {"i": item.key_id}).first():
        raise HTTPException(404, ("Услуга" if item.scope == "услуга" else "Продажник") + " не найден(а)")
    return (item.key_id, None) if item.scope == "услуга" else (None, item.key_id)


def save_targets(db, year: int, items: List[TargetItem], user) -> int:
    """Сохранить цели пачкой: одна транзакция, каждая правка — строка журнала «было → стало». → сколько изменено.
    Прошлые месяцы правятся так же (владелец 24.10.2026: без замка, под запись)."""
    from app.models import AuditLog
    from app.sales.plan_models import SalesTarget
    if not 2000 <= year <= 2100:
        raise HTTPException(400, "Год вне допустимого диапазона")
    checked = [(it, *_check(db, it)) for it in items]
    changed = 0
    for it, sid, rid in checked:
        row = (db.query(SalesTarget).filter(SalesTarget.year == year, SalesTarget.month == it.month,
                                            SalesTarget.scope == it.scope,
                                            SalesTarget.service_id.is_(None) if sid is None else SalesTarget.service_id == sid,
                                            SalesTarget.sales_rep_id.is_(None) if rid is None else SalesTarget.sales_rep_id == rid)
               .with_for_update().first())
        was = float(row.amount) if row else None
        now = round(float(it.amount), 2) if it.amount is not None else None
        if was == now:
            continue
        if now is None:
            db.delete(row)
        elif row is None:
            row = SalesTarget(year=year, month=it.month, scope=it.scope, service_id=sid, sales_rep_id=rid,
                              amount=now, updated_by=getattr(user, "id", None))
            db.add(row)
        else:
            row.amount, row.updated_by = now, getattr(user, "id", None)
            row.updated_at = func.now()
        db.flush()
        db.add(AuditLog(user_id=getattr(user, "id", None), user_name=getattr(user, "name", None),
                        action="sales_target_set", entity_type="sales_target", entity_id=getattr(row, "id", None),
                        details=f"{_label(year, it.month, it.scope, sid or rid or 0)}: было {_rub(was)} → стало {_rub(now)}"))
        changed += 1
    db.commit()
    return changed


_HIST = re.compile(r"было ([\d —]+?) → стало ([\d —]+)$")


def _num(s: str) -> Optional[float]:
    s = s.replace(" ", "").strip()
    return None if s in ("", "—") else float(s)


def history(db, year: int, m_from: int, m_to: int, scope: str, key: int) -> List[dict]:
    """История цели ячейки (месяцы m_from..m_to): кто, когда, было → стало; свежие сверху."""
    pats = [_label(year, m, scope, key) + ":%" for m in range(m_from, m_to + 1)]
    out = []
    for at, who, det in db.execute(text(
            "SELECT created_at, user_name, details FROM audit_log WHERE action = 'sales_target_set' "
            "AND details LIKE ANY(:p) ORDER BY created_at DESC, id DESC"), {"p": pats}).all():
        m = _HIST.search(det or "")
        if not m:
            continue
        out.append({"at": at.isoformat() if at else None, "by": who, "month": int(det[5:7]),
                    "was": _num(m.group(1)), "now": _num(m.group(2))})
    return out


# ── ячейка: сделки и «что может закрыть разрыв» ─────────────────────────────
def cell(db, year: int, m_from: int, m_to: int, scope: str, key: int, own: Optional[list] = None) -> dict:
    if scope not in SCOPES + (NO_SERVICE, NO_REP):
        raise HTTPException(400, "Неизвестный разрез")
    if own is not None and not (scope == "общий" or (scope == "продажник" and key in own)):
        raise HTTPException(403, "Эта строка плана вам не видна")
    picked = []
    for d in deals_of(db, year):
        if not m_from <= d.month <= m_to:
            continue
        ok = (scope == "общий" or (scope == "услуга" and d.service_id == key) or (scope == NO_SERVICE and not d.service_id)
              or (scope == "продажник" and d.sales_rep_id == key) or (scope == NO_REP and not d.sales_rep_id))
        if ok and (b := _bucket(d)):
            picked.append({"id": d.id, "code": d.code, "title": d.title, "stage": d.stage, "bucket": b,
                           "amount": round(d.amount, 2), "rep": d.rep, "service": d.service,
                           "client": " · ".join(x for x in (d.advertiser, d.brand) if x)})
    order = {"fact": 0, "work": 1, "green": 2, "orange": 3, "grey": 4}
    picked.sort(key=lambda x: (order[x["bucket"]], -x["amount"]))
    # Что может закрыть разрыв (владелец 24.10.2026): планируемые сделки ячейки по убыванию суммы — без формулы
    # «перекрасить светофор»: перекраска двигает прогноз, а не деньги.
    cands = sorted((x for x in picked if x["bucket"] in ("green", "orange", "grey")), key=lambda x: -x["amount"])
    return {"deals": picked, "candidates": cands[:15],
            "history": history(db, year, m_from, m_to, scope, key) if scope in SCOPES else []}


# ── ночной снимок ───────────────────────────────────────────────────────────
def write_snapshot(db, year: int, cells: Dict[Key, List[dict]], today: date) -> int:
    """Записать снимок дня (перезапись, если за день уже был) и убрать старше 90 дней. → строк записано.
    Удаление — через ORM, не сырым SQL (прибор test_startup_ddl)."""
    from app.sales.plan_models import SalesPlanSnapshot as S
    db.query(S).filter(S.year == year, S.day == today).delete(synchronize_session=False)
    rows = [S(day=today, year=year, month=m + 1, scope=scope, key_id=key or 0,
              done=round(done(c), 2), forecast=round(forecast(c), 2))
            for (scope, key), months in cells.items() for m, c in enumerate(months)]
    db.add_all(rows)
    db.query(S).filter(S.day < today - timedelta(days=KEEP_DAYS)).delete(synchronize_session=False)
    db.commit()
    return len(rows)
