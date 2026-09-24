"""Дашборд аккаунт-менеджера: очередь «Что делать».

Отдельный роутер, а не ещё триста строк в sales_dashboard.py (там уже 2200): у очереди
свой экран, своё право (accounts_dashboard) и свой deals_scope. Общие с реестром вещи —
own-scope, каталог стадий, разбор ссылки на сделку — импортируются из sales_dashboard,
чтобы не появилось второй реализации тех же правил.

Монтируется тем же префиксом /api/sales (см. main.py): адреса эндпоинтов не менялись.

Очередь и лента уведомлений считаются ОДНОЙ функцией срочности (app/sales/urgency.py)
через общий сборщик фактов (app/sales/urgency_db.py): расхождение между ними было бы
багом, а не двумя мнениями.
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Annotated

from app.database import get_db
from app.models import User
from app.permissions import require_permission
from app.audit import log_action
from app.sales.models import (SalesDeal, SalesRep, SalesAdvertiser, SalesBrand,
                              SalesAgency, SalesDealSnooze, SalesMediaPlan)
from app.sales.catalog import Catalog, stage_public
from app.sales import stage_move
from app.sales.mp_amounts import mp_amounts_by_deal, eff_net, gross_of
from app.sales.row_context import load_row_context
from app.sales.urgency import queue_sort_key
from app.sales.urgency_db import facts_for_deals
# Общие правила видимости берём из реестра — второй реализации own-scope быть не должно.
from app.routers.sales_dashboard import (_own_rep_ids_or_all, _apply_own_scope,
                                         _deal_owned, _deal_by_ref)
from sqlalchemy import or_

router = APIRouter()


# ══════════════════ ДАШБОРД АККАУНТА: очередь «Что делать» ══════════════════
# ТЗ — docs/«кабинет аккаунта v1» (README, части 1.4-1.6). Очередь и лента уведомлений
# считаются ОДНОЙ функцией срочности (app/sales/urgency.py) через общий сборщик фактов
# (app/sales/urgency_db.py): расхождение между ними было бы багом, а не двумя мнениями.
#
# Горизонта рассылки (SCAN_HORIZON_DAYS у сканера) здесь нет намеренно: очередь никого
# не будит, её строки фильтруются, и прятать от аккаунта его же старые сделки незачем.

# Группы очереди: порядок фиксирован, соответствует уровням срочности.
QUEUE_GROUPS = [("overdue", "Просрочено"), ("today", "Сегодня"),
                ("soon", "На неделе"), ("normal", "Остальное")]


class SnoozeIn(BaseModel):
    note: Optional[str] = None
    return_at: Optional[date] = None


def _queue_deals(db: Session, current_user: User, rep_id=None, all_reps: bool = False):
    """Сделки для очереди — конкретного сотрудника, свои или раздел целиком.

    Видимость берётся от СВОЕЙ секции accounts_dashboard: у дашборда аккаунта свой
    5-уровневый контроль в матрице ролей (нет / свои смотреть-редактировать / все),
    как у продаж, медиапланов и годового плана. Наследовать scope от sales_registry
    было неверно: аккаунту можно дать свою очередь, не давая реестр сделок вовсе.

    Роль со scope='own' селектором чужого не обманешь: _apply_own_scope отсекает
    чужие сделки раньше, чем применится rep_id.

    Возвращает (сделки, мой rep_id или None, можно ли смотреть чужих)."""
    own = _own_rep_ids_or_all(db, current_user, "accounts_dashboard")
    q = _apply_own_scope(db.query(SalesDeal), own)
    my_rep = db.query(SalesRep.id).filter(SalesRep.user_id == current_user.id).first()
    my_rep = my_rep[0] if my_rep else None

    if rep_id:
        pick = [int(rep_id)]
    elif all_reps or my_rep is None:
        # Без привязки к SalesRep «свои сделки» — понятие пустое, и экран по умолчанию
        # оказался бы пустым (так и вышло у админа). Такой пользователь получает раздел
        # целиком. Сузить видимость это не может: роль со scope='own' уже отсечена выше.
        pick = None
    else:
        pick = [my_rep]

    if pick:
        q = q.filter(or_(SalesDeal.account_manager_id.in_(pick),
                         SalesDeal.sales_rep_id.in_(pick)))
    return q.all(), my_rep, own is None


@router.get("/account-queue")
def account_queue(
    rep_id: Optional[int] = None,
    all_reps: bool = False,
    day: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("accounts_dashboard", "view")),
):
    """Очередь «Что делать»: группы по срочности + свёрнутая группа «Отложено».

    day — фильтр по дню из полосы событий (старт или закрытие периода в этот день)."""
    today = date.today()
    cat = Catalog(db)
    deals, my_rep, can_view_others = _queue_deals(db, current_user, rep_id, all_reps)
    rows = facts_for_deals(db, deals, today)

    # НАШ медиаплан сделки — чтобы кнопка «Проверить» открывала конструктор, а не
    # карточку. Берём последнюю версию (max id внутри сделки): проверяют актуальный
    # план, а не первый собранный конвейером.
    # Обе выборки ограничены сделками ТЕКУЩЕЙ очереди: без фильтра аккаунт с двадцатью
    # сделками вычитывал бы sales_media_plans и sales_deal_files целиком на каждый
    # рефреш дашборда. Тот же приём, что page_ids в реестре.
    queue_ids = [d.id for d, _ in rows]
    # Разметка стадий по услугам — один раз на очередь, а не на строку (аудит, 3.L2).
    from app.sales import stage_scope
    stage_marks = stage_scope.stage_services(db)
    mp_by_deal = {}
    if queue_ids:
        for did, mid in (db.query(SalesMediaPlan.deal_id, SalesMediaPlan.id)
                         .filter(SalesMediaPlan.deal_id.in_(queue_ids))
                         .order_by(SalesMediaPlan.id).all()):
            mp_by_deal[did] = mid        # порядок по возрастанию → остаётся последняя версия

    # Деньги — по общему правилу «есть наш МП, значит цена из него» (app/sales/mp_amounts).
    # Здесь его НЕ БЫЛО до 15.09.2026: очередь показывала сумму Битрикса, а реестр и
    # карточка — сумму плана, и одна сделка стоила на двух экранах разного. Правило одно
    # на систему, второй реализации быть не должно.
    mp_amt = mp_amounts_by_deal(db, queue_ids)

    # Цвет услуги и документы — тот же контекст, что у реестра сделок.
    row_ctx = load_row_context(db, queue_ids)

    snoozes = {s.deal_id: s for s in db.query(SalesDealSnooze)
               .filter(SalesDealSnooze.deal_id.in_(queue_ids)).all()} if queue_ids else {}
    advertisers = {a.id: a.short_name or a.name for a in db.query(SalesAdvertiser).all()}
    brands = {b.id: b.name for b in db.query(SalesBrand).all()}
    # short_name, а не name: в справочнике `name` — длинная историческая форма
    # («OKKAM / оккам», «Media instinct (Медиа инстинкт)»), и на экране она читается
    # как непочищенное старое имя. Везде в дашбордах продаж берётся именно короткое
    # (sales_dashboard.py: 655, 688, 1444, 1797) — здесь это единственное место,
    # где оно было пропущено; строкой выше у рекламодателей всё верно.
    agencies = {a.id: (a.short_name or a.name) for a in db.query(SalesAgency).all()}
    repnames = {r.id: r.name for r in db.query(SalesRep).all()}
    def row_public(d, v, sn):
        return row_ctx.apply({
            "id": d.id, "code": d.code, "title": d.title,
            "advertiser": advertisers.get(d.advertiser_id),
            "brand": brands.get(d.brand_id),
            "agency": agencies.get(d.agency_id),
            "product": d.product,
            # product_color и docs дописывает row_ctx.apply ниже.
            # id нашего МП (или null, если план приехал файлом из Битрикса и в
            # конструкторе его нет) — от этого зависит, куда ведёт «Проверить».
            "mp_id": mp_by_deal.get(d.id),
            # Поля ниже нужны фильтрам тулбара. Отдаём и id, и имя: фильтр сверяет id
            # (имена меняются), человек видит имя. «Незаполненные» считаются по этим же
            # пустотам, поэтому пустое поле возвращается как null, а не как прочерк.
            "advertiser_id": d.advertiser_id, "brand_id": d.brand_id, "agency_id": d.agency_id,
            "pipeline": d.pipeline,
            "account_manager_id": d.account_manager_id,
            "account_manager": repnames.get(d.account_manager_id),
            "sales_rep_id": d.sales_rep_id,
            "sales_rep": repnames.get(d.sales_rep_id),
            "payer_name": d.payer_name, "payer_counterparty_id": d.payer_counterparty_id,
            # Сумма с НДС — тем же правилом, что реестр и карточка (`gross_of`): план →
            # сохранённая сумма → ставка закона на период (ревью 23.09.2026).
            "amount": eff_net(d, mp_amt), "amount_with_vat": gross_of(d, mp_amt),
            "period_from": d.period_from, "period_to": d.period_to,
            "our_stage": stage_public(cat.by_id.get(d.our_stage_id), cat),
            # id — для фильтра «Незаполненные → нет стадии»: он смотрит `!r.our_stage_id`,
            # и без этого поля «пусто» было у КАЖДОЙ строки (аудит 23.09.2026).
            "our_stage_id": d.our_stage_id,
            "our_next_stage": stage_public(stage_move.next_stage(db, d, cat, marks=stage_marks)),
            "urgency": v.urgency, "reason": v.reason, "cta": v.cta, "kind": v.kind,
            "due": v.due,
            "note": sn.note if sn else None,
            "return_at": sn.return_at if sn else None,
        }, d)

    groups = {k: [] for k, _ in QUEUE_GROUPS}
    snoozed = []
    for d, v in rows:
        st = cat.by_id.get(d.our_stage_id)
        if st is not None and (st.is_terminal or st.is_lost):
            continue                      # закрытые исходы в рабочей очереди не нужны
        if day and d.period_from != day and d.period_to != day:
            continue
        sn = snoozes.get(d.id)
        # Отложенная уходит из очереди, пока дата возврата в будущем. Заметка без даты
        # строку не убирает — она только помечает её скрепкой (см. ТЗ 1.5).
        if sn and sn.return_at and sn.return_at > today:
            snoozed.append((d, v, sn))
            continue
        groups[v.urgency].append((d, v, sn))

    out = []
    for key, label in QUEUE_GROUPS:
        items = sorted(groups[key], key=lambda t: queue_sort_key(t[1]))
        out.append({"key": key, "label": label, "count": len(items),
                    "rows": [row_public(d, v, sn) for d, v, sn in items]})

    snoozed.sort(key=lambda t: t[2].return_at)
    returning = [t for t in snoozed if t[2].return_at <= today + timedelta(days=7)]
    out.append({
        "key": "snoozed", "label": "Отложено", "count": len(snoozed),
        # Подзаголовок группы: сколько вернётся на этой неделе — иначе свёрнутая
        # группа выглядит свалкой, из которой ничего не вернётся никогда.
        "hint": (f"{len(returning)} вернутся до "
                 + max(t[2].return_at for t in returning).strftime("%d.%m")
                 if returning else None),
        "rows": [row_public(d, v, sn) for d, v, sn in snoozed],
    })
    # rep_id — кого показали на самом деле (None = раздел целиком). Админ и любой без
    # профиля в sales_reps первым экраном получают раздел: «своих» сделок у них нет,
    # и пустая очередь была бы неотличима от «всё сделано».
    shown = int(rep_id) if rep_id else (None if (all_reps or my_rep is None) else my_rep)
    return {"today": today, "rep_id": shown, "my_rep_id": my_rep,
            "view": ("own" if (shown is not None and shown == my_rep)
                     else ("rep" if shown else "master")),
            "can_view_others": can_view_others,
            "groups": out,
            # total — всё, что в очереди (включая отложенные и спокойные строки),
            # actionable — только те, у кого правило нашло, что делать. Раньше отдавалось
            # одно число, и шапка «Что делать 618» спорила с блоком «Требует действия 443»
            # прямо под ней.
            "total": sum(g["count"] for g in out),
            "actionable": sum(1 for g in out if g["key"] not in ("snoozed", "normal")
                              for r in g["rows"] if r["kind"])}


@router.get("/account-calendar")
def account_calendar(
    # Границы обязательны: без них days=100000 строит стотысячный ответ и утаскивает
    # в выборку все сделки портала. Тот же приём, что у limit/offset в реестре.
    days: Annotated[int, Query(ge=1, le=31)] = 10,
    rep_id: Optional[int] = None,
    all_reps: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("accounts_dashboard", "view")),
):
    """Полоса событий: N дней вперёд, по типам. Клик по дню фильтрует очередь (day=).

    Три типа, которые система действительно знает. Дедлайна креативов здесь нет
    намеренно: согласование креативов уезжает в модуль «Сбор запуска» со своей
    логикой, и показывать сейчас упрощённую версию значило бы обещать не то."""
    today = date.today()
    horizon = today + timedelta(days=days - 1)
    cat = Catalog(db)
    brands = {b.id: b.name for b in db.query(SalesBrand).all()}

    buckets = {}
    for d in _queue_deals(db, current_user, rep_id, all_reps)[0]:
        st = cat.by_id.get(d.our_stage_id)
        if st is not None and (st.is_terminal or st.is_lost):
            continue
        events = [("start", d.period_from), ("closing", d.period_to)]
        if d.period_to:
            # Дедлайн закрывающих — тот же порог, по которому срабатывает act_missing.
            events.append(("docs", d.period_to + timedelta(days=5)))
        for kind, when in events:
            if not when or not (today <= when <= horizon):
                continue
            b = buckets.setdefault(when, {"total": 0, "kinds": {}, "brands": set()})
            b["total"] += 1
            b["kinds"][kind] = b["kinds"].get(kind, 0) + 1
            if brands.get(d.brand_id):
                b["brands"].add(brands[d.brand_id])

    out = []
    for i in range(days):
        day = today + timedelta(days=i)
        b = buckets.get(day)
        out.append({"date": day, "total": b["total"] if b else 0,
                    "kinds": b["kinds"] if b else {},
                    "brands": sorted(b["brands"])[:4] if b else []})
    return {"days": out}


def _assert_queue_scope(db: Session, user: User, deal):
    """Own-scope дашборда аккаунта на одной сделке. Тот же приём, что
    _assert_deal_in_scope для реестра, только секция своя."""
    own = _own_rep_ids_or_all(db, user, "accounts_dashboard")
    if own is None:
        return
    if not _deal_owned(deal.sales_rep_id, deal.account_manager_id, own):
        raise HTTPException(status_code=403, detail="Эта сделка не в вашей очереди")


@router.post("/deals/{deal_id}/snooze")
def snooze_deal(
    deal_id: str,
    payload: SnoozeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("accounts_dashboard", "edit")),
):
    # Проверка «своя ли сделка» идёт по accounts_dashboard (см. _assert_queue_scope):
    # по sales_registry роль без такой строки получала бы «все» и могла бы откладывать
    # чужие сделки, имея доступ только к своей очереди.
    """Отложить сделку («вернуть к дате») или оставить заметку без даты.

    Запись одна на сделку — повторный вызов перезаписывает: две даты возврата
    сделали бы неопределённым, когда именно сделка вернётся в очередь."""
    deal = _deal_by_ref(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_queue_scope(db, current_user, deal)
    if payload.return_at and payload.return_at <= date.today():
        raise HTTPException(status_code=400,
                            detail="Дата возврата должна быть в будущем")
    if not (payload.note or "").strip() and not payload.return_at:
        raise HTTPException(status_code=400, detail="Нужна заметка или дата возврата")

    row = (db.query(SalesDealSnooze)
           .filter(SalesDealSnooze.deal_id == deal.id).first())
    if row is None:
        row = SalesDealSnooze(deal_id=deal.id)
        db.add(row)
    row.note = (payload.note or "").strip() or None
    row.return_at = payload.return_at
    row.author_id = current_user.id
    db.commit()
    log_action(db, current_user, "snooze_deal", "sales_deal", deal.id,
               f"до {payload.return_at or '—'}: {row.note or '—'}")
    return {"message": "Отложено", "note": row.note, "return_at": row.return_at}


@router.delete("/deals/{deal_id}/snooze")
def unsnooze_deal(
    deal_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("accounts_dashboard", "edit")),
):
    """Вернуть сделку в очередь руками, не дожидаясь return_at."""
    deal = _deal_by_ref(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_queue_scope(db, current_user, deal)
    row = (db.query(SalesDealSnooze)
           .filter(SalesDealSnooze.deal_id == deal.id).first())
    if row:
        db.delete(row)
        db.commit()
        log_action(db, current_user, "unsnooze_deal", "sales_deal", deal.id,
                   "возвращена в очередь")
    return {"message": "Возвращена в очередь"}
