# -*- coding: utf-8 -*-
"""«Статусы продаж» — матрица клиент × месяц × вероятность (владелец 22.10.2026; хендофф docs/статусы продаж.zip).

Замена листа Excel продаж. Цифры не вводятся руками — это сделки: колонка вероятности = светофор реестра
(`probability_color`: green — факт, orange — средняя, grey — низкая; не задан — по стадии: Бронь — средняя, Медиаплан —
низкая); сделки после Брони стоят в «факте» и заперты. Своё здесь — встречи и комментарии на бренд (`sales_status_notes`)
и ручная дата статуса сделки. Перенос пина меняет период и светофор сделки — пачкой, по «Сохранить» (`/apply`).
Новые сделки создаются обычным путём (`POST /sales/deals`). Все суммы — без НДС (`amount`)."""
from datetime import date, datetime, timedelta
from datetime import date as Day   # поле `date` в DateIn иначе перекрывает тип
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.models import User
from app.permissions import require_permission
from app.sales.models import SalesDeal
from app.sales.scope import own_rep_ids_or_all
from app.sales.probability import IN_WORK as LOCKED
from app.sales.status_reminders import row_label as _row_label
from app.sales.status_models import MEETINGS, SalesStatusNote, SalesStatusReminder

router = APIRouter()
VIEW = require_permission("sales_status", "view")
EDIT = require_permission("sales_status", "edit")


def _month(s: str) -> date:
    try:
        y, m = (int(x) for x in s.split("-"))
        return date(y, m, 1)
    except (ValueError, AttributeError):
        raise HTTPException(400, f"Месяц — ГГГГ-ММ, а пришло «{s}»")


def _shift(d: date, months: int) -> date:
    """Та же дата на `months` месяцев позже; день — не дальше конца месяца."""
    import calendar
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _shift_month(ym: Optional[str], months: int) -> Optional[str]:
    """«ГГГГ-ММ» на `months` месяцев; не месяц («разово» у допов, пусто) — как есть."""
    if not ym or len(ym) != 7 or ym[4] != "-" or not (ym[:4] + ym[5:]).isdigit():
        return ym
    return _shift(date(int(ym[:4]), int(ym[5:]), 1), months).strftime("%Y-%m")


def _shift_media_plans(db, deal_id: int, months: int) -> list:
    """Медиаплан едет вместе со сделкой (владелец 27.10.2026): период, даты и месяц допов. Двигаются только незапущенные
    сделки — их медиаплан ещё не зафиксирован. → строки для журнала."""
    from app.sales.models import SalesMediaPlan, SalesMediaPlanExtra
    out = []
    for p in db.query(SalesMediaPlan).filter(SalesMediaPlan.deal_id == deal_id).all():
        old = (p.period, p.date_from, p.date_to)
        p.period = _shift_month(p.period, months)
        p.date_from = _shift(p.date_from, months) if p.date_from else None
        p.date_to = _shift_end(p.date_to, months) if p.date_to else None
        for x in db.query(SalesMediaPlanExtra).filter(SalesMediaPlanExtra.plan_id == p.id).all():
            x.period = _shift_month(x.period, months)
        if (p.period, p.date_from, p.date_to) != old:
            out.append(f"медиаплан №{p.id}: {old[0] or '—'} → {p.period or '—'}")
    return out


def _shift_end(d: date, months: int) -> date:
    """Конец периода: последний день месяца остаётся последним (01.11–30.11 → 01.12–31.12; ревью 22.10.2026),
    иначе туда-обратно январь сжимался бы до 28-го. Не конец месяца — как `_shift`."""
    import calendar
    if d.day == calendar.monthrange(d.year, d.month)[1]:
        s = _shift(d.replace(day=1), months)
        return s.replace(day=calendar.monthrange(s.year, s.month)[1])
    return _shift(d, months)


def _registry_edit(db, user) -> bool:
    """Перенос меняет период и светофор сделки — то же, что правка реестра: нужно и его право (ревью 22.10.2026)."""
    from app.permissions import get_permissions_for_user
    try:
        return bool(get_permissions_for_user(db, user).get("sales_registry", {}).get("edit"))
    except AttributeError:
        return False


_DEALS = text("""
    SELECT d.id, d.code, d.title, to_char(d.period_from, 'YYYY-MM') AS month, d.period_from, d.period_to,
           round(coalesce(d.amount, 0)::numeric, 2) AS amount, d.probability_color AS light,
           d.advertiser_id, coalesce(nullif(a.short_name, ''), a.name) AS advertiser,
           d.brand_id, b.name AS brand, coalesce(nullif(g.short_name, ''), g.name) AS agency,
           coalesce(sv.name, d.product) AS service, d.sales_rep_id, r.name AS sales, d.account_manager_id, ac.name AS account,
           s.name AS stage, s.stage_key, coalesce(s.is_lost, false) AS lost,
           d.realization_pipeline_id, d.service_id,
           d.status_date_manual, (SELECT max(h.at) FROM sales_deal_stage_history h WHERE h.deal_id = d.id) AS stage_at,
           d.date_modify
      FROM sales_deals d
      LEFT JOIN sales_advertisers a ON a.id = d.advertiser_id
      LEFT JOIN sales_brands b ON b.id = d.brand_id
      LEFT JOIN sales_agencies g ON g.id = d.agency_id
      LEFT JOIN sales_services sv ON sv.id = d.service_id
      LEFT JOIN sales_reps r ON r.id = d.sales_rep_id
      LEFT JOIN sales_reps ac ON ac.id = d.account_manager_id
      LEFT JOIN sales_stages s ON s.id = d.our_stage_id
     WHERE d.period_from >= :a AND d.period_from < :b                -- как реестр: окно по period_from, самореклама тоже
       AND (CAST(:own AS integer[]) IS NULL OR d.sales_rep_id = ANY(:own) OR d.account_manager_id = ANY(:own))
     ORDER BY advertiser NULLS LAST, brand NULLS LAST, d.period_from, d.id
""")


def _status_date(r) -> dict:
    if r.status_date_manual:
        return {"status_date": r.status_date_manual.isoformat(), "status_date_kind": "manual"}
    if r.stage_at:
        return {"status_date": r.stage_at.date().isoformat(), "status_date_kind": "history"}
    return {"status_date": r.date_modify.date().isoformat() if r.date_modify else None, "status_date_kind": "modify"}


def _note_out(n: SalesStatusNote) -> dict:
    return {"id": n.id, "advertiser_id": n.advertiser_id, "brand_id": n.brand_id, "client_name": n.client_name,
            "meet_brand": n.meet_brand, "meet_agency": n.meet_agency, "comment_sales": n.comment_sales,
            "comment_head": n.comment_head, "from_excel": list(n.from_excel or []),
            "updated_at": n.updated_at.isoformat() if n.updated_at else None}


@router.get("")
def matrix(frm: str, to: str, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Сделки с периодом в [frm, to] (месяцы ГГГГ-ММ включительно), заметки по брендам и соседи для формы.
    Область «свои» — от реестра сделок: роль «свои» видит только свои сделки (продавец или аккаунт)."""
    a, last = _month(frm), _month(to)
    if last < a:
        raise HTTPException(400, "Конец окна раньше начала")
    if (last.year - a.year) * 12 + last.month - a.month > 23:
        raise HTTPException(400, "Окно — не больше двух лет")
    own = own_rep_ids_or_all(db, user, "sales_registry")
    rows = db.execute(_DEALS, {"a": a, "b": _shift(last, 1), "own": (list(own) or [-1]) if own is not None else None}).all()
    # Сумма — как в реестре: из медиаплана, если он посчитан, иначе из сделки (владелец 22.10.2026: сделка рождается
    # заявкой на МП с примерной суммой, потом сумму даёт медиаплан). Одна функция с реестром — `mp_amounts.eff_net`.
    from app.sales.mp_amounts import mp_amounts_by_deal
    mp = mp_amounts_by_deal(db, [r.id for r in rows])
    # Реальный старт, опоздание старта и темп к закрытию — пачкой (владелец 23.10.2026, app/sales/status_launch.py)
    from app.sales import status_launch
    from app.timez import msk_now
    launch = status_launch.collect(db, rows, msk_now().date())
    deals = []
    for r in rows:
        deals.append({
            "id": r.id, "code": r.code, "title": r.title, "month": r.month,
            "period_from": r.period_from.isoformat() if r.period_from else None,
            "period_to": r.period_to.isoformat() if r.period_to else None,
            "amount": round(float(mp[r.id][0]), 2) if r.id in mp else float(r.amount), "light": r.light,
            "advertiser_id": r.advertiser_id, "advertiser": r.advertiser, "brand_id": r.brand_id, "brand": r.brand,
            "agency": r.agency, "service": r.service, "sales_rep_id": r.sales_rep_id, "sales": r.sales,
            "account_manager_id": r.account_manager_id, "account": r.account,
            "stage": r.stage, "stage_key": r.stage_key, "lost": bool(r.lost), "locked": r.stage_key in LOCKED,
            **_status_date(r), **launch.get(r.id, {}),
        })
    notes = [_note_out(n) for n in db.query(SalesStatusNote).order_by(SalesStatusNote.id).all()]
    # Названия — для строк «без сделки в окне»: у заметки только id рекламодателя и бренда
    names = {(r[0], r[1]): (r[2], r[3]) for r in db.execute(text(
        "SELECT a.id, b.id, coalesce(nullif(a.short_name, ''), a.name), b.name FROM sales_advertisers a "
        "LEFT JOIN sales_brands b ON b.advertiser_id = a.id WHERE a.id = ANY(:a)"),
        {"a": list({n["advertiser_id"] for n in notes if n["advertiser_id"]}) or [0]})}
    adv_names = {a: v[0] for (a, _), v in names.items()}
    for n in notes:
        if n["advertiser_id"]:
            n["advertiser"] = adv_names.get(n["advertiser_id"])
            n["brand"] = names.get((n["advertiser_id"], n["brand_id"]), (None, None))[1] if n["brand_id"] else None
    span = db.execute(text("SELECT to_char(min(period_from), 'YYYY-MM'), to_char(max(period_from), 'YYYY-MM') FROM sales_deals "
                           "WHERE period_from >= date_trunc('year', now()) - interval '1 year' "
                           "AND period_from < date_trunc('year', now()) + interval '2 year'")).first()
    # Все наши рекламодатели и их бренды (владелец 22.10.2026: «в этой таблице отображаются все наши рекламодатели и бренды»):
    # строка есть и без сделки в окне — туда ложатся встречи и комментарии; «скрыть пустое» их убирает.
    directory = {}
    for aid, an, bid, bn in db.execute(text(
            "SELECT a.id, coalesce(nullif(a.short_name, ''), a.name), b.id, b.name FROM sales_advertisers a "
            "LEFT JOIN sales_brands b ON b.advertiser_id = a.id AND b.is_active WHERE a.is_active ORDER BY 2, 4")):
        e = directory.setdefault(aid, {"id": aid, "name": an, "brands": []})
        if bid:
            e["brands"].append({"id": bid, "name": bn})
    return {"from": frm, "to": to, "deals": deals, "notes": notes, "directory": list(directory.values()),
            "reminders": reminders_out(db, user),
            "range": {"min": span[0], "max": span[1]} if span and span[0] else None,
            "can_edit": _can_edit(db, user)}


def _can_edit(db, user) -> bool:
    from app.permissions import get_permissions_for_user
    try:
        p = get_permissions_for_user(db, user)
        return bool(p.get("sales_status", {}).get("edit") and p.get("sales_registry", {}).get("edit"))
    except AttributeError:
        return False


class NoteIn(BaseModel):
    advertiser_id: Optional[int] = None
    brand_id: Optional[int] = None
    client_name: Optional[str] = None
    field: Literal["meet_brand", "meet_agency", "comment_sales", "comment_head"]
    value: Optional[str] = None


@router.put("/note")
def save_note(data: NoteIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Встреча или комментарий бренда. Правленое поле теряет метку «из Excel». Запись — одна на бренд (upsert)."""
    name = (data.client_name or "").strip() or None
    if (data.advertiser_id is None) == (name is None):
        raise HTTPException(400, "Нужен рекламодатель или название клиента — что-то одно")
    if data.brand_id is not None and data.advertiser_id is None:
        raise HTTPException(400, "Бренд — только вместе с рекламодателем")
    value = (data.value or "").strip() or None
    if data.field in ("meet_brand", "meet_agency") and value is not None and value not in MEETINGS:
        raise HTTPException(400, f"Встреча: пусто, {' или '.join(MEETINGS)}")
    if data.brand_id is not None:
        ok = db.execute(text("SELECT 1 FROM sales_brands WHERE id = :b AND advertiser_id = :a"),
                        {"b": data.brand_id, "a": data.advertiser_id}).first()
        if not ok:
            raise HTTPException(400, "Бренд не принадлежит рекламодателю")
    # Строка — ON CONFLICT DO NOTHING, затем под замок: два одновременных первых сохранения по бренду иначе давали 500
    # на уникальном индексе (ревью 22.10.2026).
    if name is not None:
        db.execute(text("INSERT INTO sales_status_notes (client_name) VALUES (:c) "
                        "ON CONFLICT (lower(client_name)) WHERE client_name IS NOT NULL DO NOTHING"), {"c": name})
    else:
        db.execute(text("INSERT INTO sales_status_notes (advertiser_id, brand_id) VALUES (:a, :b) "
                        "ON CONFLICT (advertiser_id, coalesce(brand_id, 0)) WHERE advertiser_id IS NOT NULL DO NOTHING"),
                   {"a": data.advertiser_id, "b": data.brand_id})
    q = db.query(SalesStatusNote)
    if name is not None:
        n = q.filter(text("lower(client_name) = lower(:c)")).params(c=name).with_for_update().populate_existing().one()
    else:
        q = q.filter(SalesStatusNote.advertiser_id == data.advertiser_id)
        q = q.filter(SalesStatusNote.brand_id.is_(None) if data.brand_id is None else SalesStatusNote.brand_id == data.brand_id)
        n = q.with_for_update().populate_existing().one()
    old = getattr(n, data.field)
    setattr(n, data.field, value)
    n.from_excel = [f for f in (n.from_excel or []) if f != data.field]
    n.updated_by, n.updated_at = user.id, datetime.utcnow()
    db.commit()
    who = name or f"рекламодатель {data.advertiser_id}" + (f", бренд {data.brand_id}" if data.brand_id else "")
    log_action(db, user, "sales_status_note", "sales_status_note", n.id,
               f"{who}: {data.field} — «{(old or '')[:120]}» → «{(value or '')[:120]}»")
    return _note_out(n)


class DateIn(BaseModel):
    date: Optional[Day] = None

    # Ввод с клавиатуры шлёт «0002-10-21» на первой цифре года — такое не сохраняем (ревью 22.10.2026)
    @field_validator("date")
    @classmethod
    def _sane(cls, v):
        if v is not None and not 2000 <= v.year <= 2100:
            raise ValueError("Год даты — от 2000 до 2100")
        return v


def _deal_for_edit(db: Session, deal_id: int, user) -> SalesDeal:
    d = db.query(SalesDeal).filter(SalesDeal.id == deal_id).with_for_update().first()
    if d is None:
        raise HTTPException(404, "Сделка не найдена")
    own = own_rep_ids_or_all(db, user, "sales_registry")
    if own is not None and d.sales_rep_id not in own and d.account_manager_id not in own:
        raise HTTPException(403, "Сделка вне вашей зоны видимости")
    return d


@router.put("/deal/{deal_id}/date")
def set_status_date(deal_id: int, data: DateIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Дата статуса вручную; пусто — снова считается сама (история стадий, иначе последняя правка)."""
    d = _deal_for_edit(db, deal_id, user)
    old = d.status_date_manual
    d.status_date_manual = data.date
    db.commit()
    log_action(db, user, "sales_status_date", "sales_deal", d.id, f"{d.code}: дата статуса {old or 'авто'} → {data.date or 'авто'}")
    return {"id": d.id, "status_date_manual": data.date.isoformat() if data.date else None}


class MoveIn(BaseModel):
    deal_id: int
    month: str
    light: Optional[Literal["green", "orange", "grey"]] = None
    # Что экран видел, когда двигал: если реестр с тех пор поменял период или светофор — не затираем (22.10.2026)
    from_month: Optional[str] = None
    from_light: Optional[str] = None


class ApplyIn(BaseModel):
    moves: List[MoveIn]


@router.post("/apply")
def apply_moves(data: ApplyIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """«Сохранить» панели «В реестр запишется»: переносы пинов — период и светофор сделок, одной транзакцией.
    Запущенную сделку (после Брони) и сорванную не двигаем — отказ 409 с перечнем, ничего не пишется."""
    if not data.moves:
        return {"saved": []}
    if not _registry_edit(db, user):
        raise HTTPException(403, "Переносить сделки может тот, у кого есть правка реестра сделок")
    stages = {r[0]: (r[1], bool(r[2])) for r in db.execute(text("SELECT id, stage_key, coalesce(is_lost, false) FROM sales_stages"))}
    deals, refused, changed = [], [], []
    for mv in sorted(data.moves, key=lambda x: x.deal_id):          # один порядок блокировок — без взаимного затора
        d = _deal_for_edit(db, mv.deal_id, user)
        key, lost = stages.get(d.our_stage_id, (None, False))
        if key in LOCKED or lost:
            refused.append(d.code or str(d.id))
        cur_month = d.period_from.strftime("%Y-%m") if d.period_from else None
        if (mv.from_month is not None and mv.from_month != cur_month) or (
                "from_light" in mv.model_fields_set and (mv.from_light or None) != (d.probability_color or None)):
            changed.append(d.code or str(d.id))
        deals.append((d, mv))
    if refused:
        db.rollback()
        raise HTTPException(409, f"Проект запущен или сделка сорвана — не двигаются: {', '.join(refused)}")
    if changed:
        db.rollback()
        raise HTTPException(409, f"Сделки изменили в реестре, пока перенос ждал сохранения: {', '.join(changed)}. "
                                 "Обновите экран и перенесите заново")
    saved = []
    for d, mv in deals:
        target = _month(mv.month)
        notes = []
        if d.period_from is None:
            raise HTTPException(409, f"{d.code}: у сделки нет периода")
        delta = (target.year - d.period_from.year) * 12 + target.month - d.period_from.month
        if delta:
            old = (d.period_from, d.period_to)
            d.period_from = _shift(d.period_from, delta)
            d.period_to = _shift_end(d.period_to, delta) if d.period_to else None
            notes.append(f"период {old[0]}–{old[1]} → {d.period_from}–{d.period_to}")
            notes += _shift_media_plans(db, d.id, delta)
        if mv.light != d.probability_color:
            notes.append(f"светофор {d.probability_color or 'не задан'} → {mv.light or 'не задан'}")
            d.probability_color = mv.light
        if notes:
            d.date_modify = datetime.utcnow()
            saved.append({"id": d.id, "code": d.code, "changes": notes})
    db.commit()
    for x in saved:
        log_action(db, user, "sales_status_move", "sales_deal", x["id"], f"{x['code']}: " + "; ".join(x["changes"]))
    return {"saved": saved}


# ── Будильник на строку (владелец 23.10.2026) ────────────────────────────────────────────────────────────────────────
# Себе, на дату: в 09:00 МСК этого дня сканер уведомлений шлёт его в Telegram и на почту (`sales_status_reminder`).
# Один на строку у каждого: новая дата переписывает старую и снова взводит отправку. Право — просмотр экрана: это
# напоминание человека самому себе, данных сделок оно не меняет.

def reminders_out(db, user) -> list:
    """Будильники экрана (владелец 27.10.2026): каждому — свои; кто видит реестр целиком (мастера, админ) — все."""
    q = (db.query(SalesStatusReminder, User.name).join(User, User.id == SalesStatusReminder.user_id)
         .filter(SalesStatusReminder.remind_on >= date.today() - timedelta(days=30)))  # отработавшие — месяц, дальше не мешают
    if own_rep_ids_or_all(db, user, "sales_registry") is not None:
        q = q.filter(SalesStatusReminder.user_id == user.id)
    rows = q.order_by(SalesStatusReminder.remind_on).all()
    return [{"id": r.id, "advertiser_id": r.advertiser_id, "brand_id": r.brand_id, "client_name": r.client_name,
             "remind_on": r.remind_on.isoformat(), "note": r.note, "sent": r.sent_at is not None,
             "user": name, "mine": r.user_id == user.id} for r, name in rows]


class ReminderIn(BaseModel):
    advertiser_id: Optional[int] = None
    brand_id: Optional[int] = None
    client_name: Optional[str] = None
    remind_on: Day
    note: Optional[str] = None


@router.put("/reminder")
def set_reminder(data: ReminderIn, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    name = (data.client_name or "").strip()[:300] or None
    if (data.advertiser_id is None) == (name is None):
        raise HTTPException(400, "Нужен рекламодатель или название клиента — что-то одно")
    if data.advertiser_id is not None and not db.execute(
            text("SELECT 1 FROM sales_advertisers WHERE id = :a"), {"a": data.advertiser_id}).first():
        raise HTTPException(400, "Рекламодатель не найден")
    if data.brand_id is not None:
        ok = db.execute(text("SELECT 1 FROM sales_brands WHERE id = :b AND advertiser_id = :a"),
                        {"b": data.brand_id, "a": data.advertiser_id}).first()
        if not ok:
            raise HTTPException(400, "Бренд не принадлежит рекламодателю")
    from app.timez import msk_now
    if data.remind_on < msk_now().date():
        raise HTTPException(400, "Дата будильника уже прошла — выберите сегодня или позже")
    note = (data.note or "").strip()[:500] or None
    key = {"u": user.id, "a": data.advertiser_id or 0, "b": data.brand_id or 0, "c": (name or "").lower()}
    row = db.execute(text("""SELECT id FROM sales_status_reminders WHERE user_id = :u AND coalesce(advertiser_id, 0) = :a
                               AND coalesce(brand_id, 0) = :b AND lower(coalesce(client_name, '')) = :c FOR UPDATE"""), key).scalar()
    r = db.get(SalesStatusReminder, row) if row else SalesStatusReminder(
        user_id=user.id, advertiser_id=data.advertiser_id, brand_id=data.brand_id, client_name=name)
    r.remind_on, r.note, r.sent_at, r.updated_at = data.remind_on, note, None, datetime.utcnow()
    if not row:
        db.add(r)
    try:
        db.commit()
    except IntegrityError:   # двойной клик: второй запрос вставил ту же строку раньше — не 500 (ревью 23.10.2026)
        db.rollback()
        raise HTTPException(409, "Будильник уже ставится — обновите страницу")
    log_action(db, user, "status_reminder_set", "sales_status_reminder", r.id,
               f"{_row_label(db, r.advertiser_id, r.brand_id, r.client_name)}: {r.remind_on.strftime('%d.%m.%Y')}"
               + (f" — {note}" if note else ""))
    return {"id": r.id, "remind_on": r.remind_on.isoformat(), "note": r.note}


@router.delete("/reminder/{rid}")
def delete_reminder(rid: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Снять можно только свой: чужой будильник — чужое напоминание себе."""
    r = db.query(SalesStatusReminder).filter(SalesStatusReminder.id == rid, SalesStatusReminder.user_id == user.id).first()
    if not r:
        raise HTTPException(404, "Будильник не найден")
    what = _row_label(db, r.advertiser_id, r.brand_id, r.client_name)
    db.delete(r)
    db.commit()
    log_action(db, user, "status_reminder_off", "sales_status_reminder", rid, what)
    return {"ok": True}

