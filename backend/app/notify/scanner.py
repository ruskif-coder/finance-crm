"""Сканер состояниевых алертов — то, что никто не «эмитит»: просрочка, зависший
документ, простой. Запускается по расписанию (cron на сервере, как бэкапы).

    docker exec finance_backend python -m app.notify.scanner --dry-run
    docker exec finance_backend python -m app.notify.scanner

Два предохранителя, без которых система превращается в спам и её отключают:

1. ПОВТОР СЧИТАЕТСЯ ОТ ФАКТА последней отправки (alert_state.last_sent_at), а не по
   календарной кратности. Сервер лежал сутки — следующий прогон увидит, что прошло
   11 дней, и отправит. Даты плавают на день-два, зато напоминание не теряется.
2. --dry-run: считает, пишет в журнал прогонов, НО не отправляет. Первую неделю живём
   так, смотрим объёмы и крутим пороги.

Смена ступени (наступил срок, ушёл в просрочку) отправляется НЕМЕДЛЕННО, не дожидаясь
конца интервала: это переход, а не повтор.

Закрытие: если объект больше не подпадает под правило (оплатили, согласовали), строка
состояния помечается resolved_at и повторы прекращаются сами.
"""
import sys
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.notify import registry
from app.notify.bus import emit
from app.notify.models import NotificationAlertState, NotificationScanRun


# ─────────────────────────── общий механизм ───────────────────────────

class Hit:
    """Сработка правила по конкретному объекту."""
    def __init__(self, entity_type: str, entity_id: int, stage: str, title: str,
                 body: str = None, link: str = None, due_date: date = None,
                 ctx: dict = None, payload: dict = None):
        self.entity_type, self.entity_id, self.stage = entity_type, entity_id, stage
        self.title, self.body, self.link = title, body, link
        self.due_date, self.ctx, self.payload = due_date, ctx or {}, payload or {}


def _param(ev: registry.Event, name: str, default: int) -> int:
    v = (ev.params or {}).get(name, default)
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _state(db: Session, event_key: str, hit: Hit) -> NotificationAlertState:
    st = (db.query(NotificationAlertState)
          .filter(NotificationAlertState.event_key == event_key,
                  NotificationAlertState.entity_type == hit.entity_type,
                  NotificationAlertState.entity_id == hit.entity_id).first())
    if st is None:
        st = NotificationAlertState(event_key=event_key, entity_type=hit.entity_type,
                                    entity_id=hit.entity_id)
        db.add(st)
        db.flush()
    return st


def _should_send(st: NotificationAlertState, hit: Hit, repeat_days: int, now: datetime) -> bool:
    if st.last_sent_at is None:
        return True
    if st.stage != hit.stage:            # переход между ступенями — шлём сразу
        return True
    return (now - st.last_sent_at) >= timedelta(days=repeat_days)


def _resolve_gone(db: Session, event_key: str, alive_ids: set, entity_type: str, now: datetime):
    """Объекты, переставшие подпадать под правило, закрываем — иначе повторы вечны."""
    rows = (db.query(NotificationAlertState)
            .filter(NotificationAlertState.event_key == event_key,
                    NotificationAlertState.entity_type == entity_type,
                    NotificationAlertState.resolved_at.is_(None)).all())
    closed = 0
    for st in rows:
        if st.entity_id not in alive_ids:
            st.resolved_at = now
            st.resolve_note = "объект больше не подпадает под правило"
            closed += 1
    return closed


# ─────────────────────────── правила ───────────────────────────

def rule_invoice_overdue(db: Session, ev: registry.Event) -> List[Hit]:
    """Неоплаченные счета. Срок и возраст долга берутся ИЗ reports.py — той же
    функцией, что считает дебиторку в отчёте. Дублировать формулу нельзя: расхождение
    между письмом и экраном мгновенно убивает доверие к алерту.

    Ступени:
      warning  — до срока оплаты осталось не больше before_days;
      due      — срок наступил, идёт буфер GRACE_DAYS («текущая задолженность»);
      overdue  — буфер кончился, долг просрочен.
    """
    from app.models import Operation, Counterparty
    from app.routers.reports import (_due_date, _term_days_for_counterparty,
                                     GRACE_DAYS)

    today = date.today()
    before_days = _param(ev, "before_days", 10)

    ops = (db.query(Operation)
           .filter(Operation.status == "ПЛАН ПОСТУПЛЕНИЙ", Operation.income > 0).all())
    cps = {c.id: c for c in db.query(Counterparty).all()}

    hits = []
    for op in ops:
        cp = cps.get(op.counterparty_id)
        due = _due_date(op.period, _term_days_for_counterparty(cp))
        if not due:
            continue
        left = (due - today).days
        if left > before_days:
            continue                                   # ещё рано
        if left > 0:
            stage, human = "warning", f"срок оплаты через {left} дн."
        elif (today - due).days <= GRACE_DAYS:
            stage, human = "due", ("срок оплаты наступил сегодня" if left == 0
                                   else f"срок оплаты прошёл {(today - due).days} дн. назад")
        else:
            stage, human = "overdue", f"просрочка {(today - due).days - GRACE_DAYS} дн. сверх буфера"

        name = (cp.name if cp else None) or "контрагент не указан"
        amount = f"{(op.income or 0):,.0f}".replace(",", " ")
        # Отсрочка по умолчанию — повод для оговорки: у 2 контрагентов из 209 срок задан
        # явно, у остальных подставляется DEFAULT_TERM_DAYS, и цифра может врать.
        term_note = "" if (cp and cp.term_days is not None) else " · срок отсрочки не подтверждён"
        hits.append(Hit(
            entity_type="operation", entity_id=op.id, stage=stage, due_date=due,
            title=f"{name}: {amount} ₽ — {human}",
            body=f"Период {op.period}, срок оплаты {due.strftime('%d.%m.%Y')}{term_note}",
            link="/finance/operations",
            payload={"amount": op.income, "period": op.period, "due": due.isoformat()},
        ))
    return hits


def rule_mp_stuck(db: Session, ev: registry.Event) -> List[Hit]:
    """Медиапланы, застрявшие на согласовании. Возраст считаем по updated_at —
    статус меняется через ORM, поэтому отметка обновляется при отправке на согласование."""
    from app.sales.models import SalesMediaPlan

    after_days = _param(ev, "after_days", 3)
    edge = datetime.utcnow() - timedelta(days=after_days)

    plans = (db.query(SalesMediaPlan)
             .filter(SalesMediaPlan.status == "review",
                     SalesMediaPlan.updated_at < edge).all())
    hits = []
    for p in plans:
        days = (datetime.utcnow() - p.updated_at).days if p.updated_at else after_days
        hits.append(Hit(
            entity_type="media_plan", entity_id=p.id, stage="due",
            title=f"МП ждёт согласования {days} дн.: {p.title or ('#' + str(p.id))}",
            link=f"/accounts/mp/{p.id}", ctx={"media_plan": p},
            payload={"days": days},
        ))
    return hits


# ──────────────── очередь сделок: одна функция срочности на шесть событий ────────────────

# Вердикты за прогон считаются ОДИН раз и раздаются шести правилам по Verdict.kind.
# Без кэша был бы шестикратный проход по всем сделкам с теми же джойнами.
# Сбрасывается в начале scan(): держать его между прогонами нельзя — данные меняются.
_verdicts: Optional[list] = None

# Горизонт РАССЫЛКИ (не расчёта): уведомляем только про сделки, чьё размещение
# закончилось не позже полугода назад. Дальше начинается разбор истории, а он делается
# разовой чисткой, а не потоком напоминаний. Порог нужен из-за реальных данных: без него
# первый боевой прогон отправил бы около 400 писем про сделки 2024-2025 годов, и раздел
# уведомлений выключили бы целиком — ровно то, от чего защищают предохранители сверху.
#
# Очередь на дашборде горизонтом НЕ ограничена: там строки фильтруются и никого не будят.
# Правила при этом одни и те же (Verdict.kind и reason не меняются) — лента просто
# подмножество очереди, а не другой расчёт.
SCAN_HORIZON_DAYS = 180


def _deal_facts(db: Session):
    """Сделки в пределах горизонта рассылки → их срочность.

    Сам перевод «база → DealFacts» живёт в app/sales/urgency_db.py и используется
    ещё и очередью на дашборде: два сборщика фактов разошлись бы молча."""
    from app.sales.models import SalesDeal
    from app.sales.urgency_db import facts_for_deals

    today = date.today()
    horizon = today - timedelta(days=SCAN_HORIZON_DAYS)

    deals = []
    for d in db.query(SalesDeal).all():
        last_date = d.period_to or d.period_from
        if last_date and last_date < horizon:
            continue                     # за горизонтом рассылки — см. SCAN_HORIZON_DAYS
        if last_date is None and d.our_stage_id is None:
            # Ни периода, ни стадии — незаполненная болванка из синка (238 таких).
            # Уведомлять о ней некого и незачем: в очереди на дашборде она видна
            # под фильтром «Незаполненные», разбирается пачкой, а не письмами.
            continue
        deals.append(d)
    return facts_for_deals(db, deals, today)


def _deal_rule(kind: str):
    """Правило-обёртка: берёт из общего расчёта только сработки своего вида."""
    def rule(db: Session, ev: registry.Event) -> List[Hit]:
        global _verdicts
        if _verdicts is None:
            _verdicts = _deal_facts(db)
        hits = []
        for d, v in _verdicts:
            if v.kind != kind:
                continue
            where = " · ".join(x for x in (d.title, d.product) if x) or f"#{d.code or d.id}"
            hits.append(Hit(
                entity_type="deal", entity_id=d.id,
                # Ступень = уровень срочности: переход soon → overdue шлётся немедленно,
                # не дожидаясь конца интервала повтора (см. _should_send).
                stage=v.urgency, due_date=v.due,
                title=f"{where}: {v.reason}",
                link=f"/sales/deals/{d.code or d.id}",
                ctx={"deal": d},
                payload={"urgency": v.urgency, "cta": v.cta,
                         "due": v.due.isoformat() if v.due else None},
            ))
        return hits
    return rule


# ──────────────── сейлзы: годовой план и конструктор МП ────────────────

MONTHS_RU = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль",
             "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]

# Насколько далеко в прошлое напоминаем про пустой месяц плана. Дальше это уже не работа
# на сегодня, а разбор истории: план прошлого полугодия правят разом, а не по письму
# на каждую ячейку. Та же логика, что у SCAN_HORIZON_DAYS для сделок.
PLAN_MONTH_HORIZON_DAYS = 60


def plan_month_stage(month_start: date, today: date, before_days: int) -> Optional[str]:
    """Ступень для ячейки плана или None, если сообщать рано/поздно.

    Вынесено чистой функцией: границы окна — единственное, что здесь легко сломать,
    и проверяются они без базы."""
    left = (month_start - today).days
    if left > before_days:
        return None                              # ещё рано
    if left < -PLAN_MONTH_HORIZON_DAYS:
        return None                              # за горизонтом напоминаний
    return "soon" if left > 0 else "overdue"


def rule_plan_month_empty(db: Session, ev: registry.Event) -> List[Hit]:
    """Месяц строки годового плана включён и с суммой, а сделок в ячейку не привязано.

    Что считается «запланировано» и «сколько денег в ячейке», решают функции самого
    годового плана (_planned_months / _intended_amount / _is_locked) — повторять их
    здесь значило бы завести второе мнение о том же плане.
    """
    from app.sales.models import (SalesDeal, SalesYearPlanLine, SalesAdvertiser, SalesBrand)
    from app.routers.year_plan import _planned_months, _intended_amount, _is_locked

    today = date.today()
    before_days = _param(ev, "before_days", 14)

    lines = db.query(SalesYearPlanLine).filter(SalesYearPlanLine.sales_rep_id.isnot(None)).all()
    if not lines:
        return []
    adv = dict(db.query(SalesAdvertiser.id,
                        func.coalesce(SalesAdvertiser.short_name, SalesAdvertiser.name)).all())
    brands = dict(db.query(SalesBrand.id, SalesBrand.name).all())

    # Одним запросом: какие (строка, месяц) уже наполнены сделками.
    filled = set(db.query(SalesDeal.year_plan_line_id, SalesDeal.plan_month)
                 .filter(SalesDeal.year_plan_line_id.isnot(None)).distinct().all())

    hits = []
    for line in lines:
        for m in _planned_months(line):
            if _is_locked(line, m):              # замок — осознанная заморозка месяца
                continue
            if (line.id, m) in filled:
                continue
            amount = _intended_amount(line, m)
            if amount <= 0:
                continue
            stage = plan_month_stage(date(line.year, m + 1, 1), today, before_days)
            if stage is None:
                continue
            who = " · ".join(x for x in (adv.get(line.advertiser_id),
                                         brands.get(line.brand_id)) if x) or f"строка #{line.id}"
            money = f"{amount:,.0f}".replace(",", " ")
            hits.append(Hit(
                # entity_id — синтетический ключ ячейки (строка × месяц): состояние алерта
                # ведётся по ячейке, а не по строке, иначе напоминание про март гасило бы
                # напоминание про апрель.
                entity_type="year_plan_month", entity_id=line.id * 12 + m, stage=stage,
                due_date=date(line.year, m + 1, 1),
                title=f"{who}: {MONTHS_RU[m]} {line.year} запланирован на {money} ₽, сделок нет",
                link="/sales/year-plan", ctx={"rep_id": line.sales_rep_id},
                payload={"line_id": line.id, "month": m, "amount": amount},
            ))
    return hits


def rule_mp_draft_stale(db: Session, ev: registry.Event) -> List[Hit]:
    """Черновики МП, брошенные в конструкторе.

    Планы, собранные конвейером годового плана, исключены: про них есть своё событие
    mp_verify, адресованное аккаунту. Иначе один и тот же непроверенный автоплан
    порождал бы два разных напоминания двум людям — верный способ, чтобы оба решили,
    что это дело другого.
    """
    from app.sales.models import SalesMediaPlan, SalesDeal

    after_days = _param(ev, "after_days", 7)
    edge = datetime.utcnow() - timedelta(days=after_days)

    conveyor = {d for (d,) in db.query(SalesDeal.id)
                .filter(SalesDeal.year_plan_line_id.isnot(None)).all()}
    plans = (db.query(SalesMediaPlan)
             .filter(SalesMediaPlan.status == "draft",
                     SalesMediaPlan.created_by.isnot(None),
                     SalesMediaPlan.updated_at < edge).all())
    hits = []
    for p in plans:
        if p.deal_id and p.deal_id in conveyor:
            continue
        days = (datetime.utcnow() - p.updated_at).days if p.updated_at else after_days
        hits.append(Hit(
            entity_type="media_plan", entity_id=p.id, stage="due",
            title=f"Черновик МП лежит {days} дн.: {p.title or ('#' + str(p.id))}",
            link=f"/accounts/mp/{p.id}", ctx={"media_plan": p},
            payload={"days": days},
        ))
    return hits


def backlog_overdue_hits(items, today: date, now: datetime, repeat_days: int = 7) -> List[Hit]:
    """Чистая часть правила: из списка записей выбрать те, о просрочке которых
    пора напомнить. Вынесена отдельно, чтобы проверяться без базы.

    Два отсева:
      * записи в CLOSED_STATUSES — сняты с наблюдения, срок им уже не важен;
      * записи, о которых напоминали меньше repeat_days назад (overdue_notified_at).
    """
    from app.backlog_models import CLOSED_STATUSES

    hits = []
    for it in items:
        if it.status in CLOSED_STATUSES:
            continue
        if not it.watch_until or it.watch_until >= today:
            continue
        last = it.overdue_notified_at
        if last is not None and (now - last) < timedelta(days=repeat_days):
            continue
        days = (today - it.watch_until).days
        hits.append(Hit(
            entity_type="backlog", entity_id=it.id, stage="overdue",
            due_date=it.watch_until,
            title=f"Срок наблюдения истёк {days} дн. назад: {it.title}",
            body=(it.signal_bad or it.context or None),
            link="/settings/backlog",
            payload={"days": days, "watch_until": it.watch_until.isoformat()},
        ))
    return hits


def rule_backlog_overdue(db: Session, ev: registry.Event) -> List[Hit]:
    """Записи бэклога отладки, у которых прошёл watch_until, а статус так и остался
    наблюдательным. Никто этого не «делает» — потому и сканер, а не emit из роутера."""
    from app.backlog_models import BacklogItem

    repeat_days = _param(ev, "repeat_days", 7)
    items = db.query(BacklogItem).filter(BacklogItem.watch_until.isnot(None)).all()
    return backlog_overdue_hits(items, date.today(), datetime.utcnow(), repeat_days)


def _after_backlog_overdue(db: Session, hit: Hit, now: datetime):
    from app.backlog_models import BacklogItem
    it = db.query(BacklogItem).filter(BacklogItem.id == hit.entity_id).first()
    if it:
        it.overdue_notified_at = now


# Правила сканера: ключ события в реестре → функция. Событие без функции здесь
# в сканер не попадает (и наоборот — функция без записи в реестре не запустится).
# Шесть событий очереди сделок обслуживает ОДНА функция срочности (app.sales.urgency),
# та же, что строит очередь на дашборде аккаунта; обёртка лишь разбирает её вердикты
# по видам. invoice_overdue и mp_stuck на неё не переезжают: они считаются по операциям
# и по медиапланам, а не по сделкам — у них другая сущность и другой адресат.
DEAL_QUEUE_EVENTS = ["deal_mp_missing", "mp_verify", "mp_unapproved", "mp_rework", "booking_confirm",
                     "act_missing", "stage_stuck", "stage_unmapped"]

RULES = {
    "invoice_overdue": rule_invoice_overdue,
    "mp_stuck": rule_mp_stuck,
    "plan_month_empty": rule_plan_month_empty,
    "mp_draft_stale": rule_mp_draft_stale,
    "backlog_overdue": rule_backlog_overdue,
    **{k: _deal_rule(k) for k in DEAL_QUEUE_EVENTS},
}

# Хуки «после реальной отправки» (в сухом прогоне НЕ вызываются): нужны правилам,
# которые держат отметку о напоминании в собственной таблице, а не только в alert_state.
AFTER_SEND = {
    "backlog_overdue": _after_backlog_overdue,
}


# ─────────────────────────── прогон ───────────────────────────

def scan(dry_run: bool = False, only: Optional[str] = None) -> Dict[str, int]:
    global _verdicts
    _verdicts = None          # расчёт срочности переиспользуется внутри прогона, но не между
    db = SessionLocal()
    now = datetime.utcnow()
    run = NotificationScanRun(dry_run=dry_run)
    db.add(run)
    db.flush()
    stats = {"rules": 0, "matches": 0, "sent": 0, "skipped": 0, "closed": 0}
    try:
        for event_key, fn in RULES.items():
            if only and event_key != only:
                continue
            ev = registry.get(event_key)
            if ev is None:
                print(f"  ! {event_key}: нет в реестре — пропуск")
                continue
            stats["rules"] += 1
            hits = fn(db, ev)
            stats["matches"] += len(hits)
            repeat_days = _param(ev, "repeat_days", 10)
            print(f"[{event_key}] сработок: {len(hits)}")

            by_type = {}
            for hit in hits:
                by_type.setdefault(hit.entity_type, set()).add(hit.entity_id)
                st = _state(db, event_key, hit)
                if st.resolved_at and st.stage == hit.stage:
                    continue                       # уже закрывали и ничего не изменилось
                if not _should_send(st, hit, repeat_days, now):
                    stats["skipped"] += 1
                    continue
                if dry_run:
                    stats["sent"] += 1
                    print(f"    (сухой прогон) {hit.stage}: {hit.title}")
                    continue
                got = emit(db, event_key, title=hit.title, body=hit.body, link=hit.link,
                           entity_type=hit.entity_type, entity_id=hit.entity_id,
                           ctx=hit.ctx)
                st.stage = hit.stage
                st.due_date = hit.due_date
                st.payload = hit.payload
                st.last_sent_at = now
                st.sent_count = (st.sent_count or 0) + 1
                st.resolved_at = None
                hook = AFTER_SEND.get(event_key)
                if hook:
                    hook(db, hit, now)
                stats["sent"] += 1
                print(f"    {hit.stage}: {hit.title} → получателей {len(got)}")

            for entity_type, ids in by_type.items():
                stats["closed"] += _resolve_gone(db, event_key, ids, entity_type, now)

        run.finished_at = datetime.utcnow()
        run.rules_run = stats["rules"]
        run.matches = stats["matches"]
        run.sent = stats["sent"]
        run.suppressed = stats["skipped"]
        if dry_run:
            # Строку прогона сохраняем всегда — иначе «сканер не запускался» не отличить
            # от «запускался и ничего не нашёл».
            db.commit()
        else:
            db.commit()
        print(f"Итого: правил {stats['rules']}, сработок {stats['matches']}, "
              f"отправок {stats['sent']}, пропущено по интервалу {stats['skipped']}, "
              f"закрыто {stats['closed']}" + (" (СУХОЙ ПРОГОН)" if dry_run else ""))
        return stats
    except Exception as e:
        db.rollback()
        run2 = NotificationScanRun(dry_run=dry_run, finished_at=datetime.utcnow(),
                                   error=str(e)[:600])
        db.add(run2)
        db.commit()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    only = None
    for a in sys.argv[1:]:
        if a.startswith("--only="):
            only = a.split("=", 1)[1]
    scan(dry_run="--dry-run" in sys.argv, only=only)
