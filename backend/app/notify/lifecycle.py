# -*- coding: utf-8 -*-
"""Жизненный цикл уведомлений в панели: гашение и срок жизни (владелец 27.09.2026).

До этого строка колокольчика жила вечно: удаления не было ни в коде, ни в кроне, и за
месяц у отдельных сотрудников накопилось по 130 непрочитанных — счётчик перестал что-либо
значить. Решения владельца:

1. **Срок жизни.** Прочитанное и погашенное удаляется через 30 дней, непрочитанное —
   через 90. Журнал отправок — через 180 (он нужен, чтобы разобрать «почему не пришло
   письмо»); строки очереди дайджеста (`queued`) не трогаются никогда — это недоставленное.
2. **Гашение по снятой причине.** Для правил сканера оно уже было (`scanner._resolve_gone`),
   здесь — то, что сканер не покрывал:
   * уведомления-ЗАДАЧИ от событий (не сканера): «материал на проверку», «креатив на
     переделку», «нужен пиксель». Гаснут, когда работа сделана или сделка закрыта;
   * строки правил сканера, записанные ДО схлопывания (14.09.2026, `dedup_key` пуст).
     Сканер гасит по ключу, и эти строки не гаснут никогда: на проде их 150 непрочитанных.
3. **Крестик** — `POST /notifications/{id}/dismiss`, в роутере.

Погашенное из панели пропадает сразу (`resolved_at`), из базы — по сроку жизни.
Уведомления-ФАКТЫ («сделка ушла в бронь», «ЕРИД выпущен») не гасятся ничем: снимать
у них нечего, они уходят по сроку.

Запуск: `python -m app.notify.lifecycle [--dry-run]` — крон ежечасно. Всё идемпотентно:
повторный прогон ничего не меняет.
"""
import argparse
from datetime import datetime, timedelta

from sqlalchemy import text

from app.database import SessionLocal

READ_DAYS = 30          # прочитанное и погашенное
UNREAD_DAYS = 90        # непрочитанное
DELIVERY_DAYS = 180     # журнал отправок, кроме очереди дайджеста


# ── задачи: жива ли ещё причина ────────────────────────────────────────────────

def _open_deals(db, ids) -> set:
    """Сделки из списка, которые ещё в работе: закрытая сделка снимает любую задачу по ней."""
    if not ids:
        return set()
    rows = db.execute(text("""
        SELECT d.id FROM sales_deals d
        LEFT JOIN sales_stages s ON s.id = d.our_stage_id
        WHERE d.id = ANY(:ids) AND NOT COALESCE(s.is_terminal OR s.is_lost, false)
    """), {"ids": list(ids)}).all()
    return {r[0] for r in rows}


def _alive_traffic_new_work(db, ids) -> set:
    """Материал ждёт трафика, пока у сделки есть проверка трафиков без вердикта."""
    rows = db.execute(text("""
        SELECT DISTINCT s.deal_id FROM launch_prep_review r
        JOIN launch_prep_creative_set s ON s.id = r.set_id
        WHERE r.kind = 'трафики' AND r.verdict IS NULL AND s.deal_id = ANY(:ids)
    """), {"ids": list(ids)}).all()
    return {r[0] for r in rows}


def _alive_traffic_rework(db, ids) -> set:
    """Переделка — это новый комплект (`traffic._apply_verdict`): вердикт у старого
    остаётся навсегда. Поэтому причина снята, когда после вердикта сделка отправила
    трафику новый комплект."""
    rows = db.execute(text("""
        SELECT DISTINCT s.deal_id FROM launch_prep_review r
        JOIN launch_prep_creative_set s ON s.id = r.set_id
        WHERE r.kind = 'трафики' AND r.verdict = 'на переделку' AND s.deal_id = ANY(:ids)
          AND NOT EXISTS (
              SELECT 1 FROM launch_prep_creative_set s2
              WHERE s2.deal_id = s.deal_id AND s2.sent_at > r.decided_at)
    """), {"ids": list(ids)}).all()
    return {r[0] for r in rows}


def _alive_weborama_pixel(db, ids) -> set:
    """Пиксель нужен, пока он заказан и проверка «Пиксель Weborama» не зелёная — та же
    функция, что у чек-листа стадии, а не своё правило."""
    from app.sales.models import SalesDeal
    from app.sales.stage_checks import OK, REGISTRY, Ctx
    alive = set()
    for d in db.query(SalesDeal).filter(SalesDeal.id.in_(list(ids))).all():
        if not d.weborama_pixel:
            continue
        if REGISTRY["weborama_pixel"].fn(Ctx(db, d)).state != OK:
            alive.add(d.id)
    return alive


# Событие → функция «какие из этих сделок ещё требуют действия». Сделка тут всегда
# объект события: `sales_deal` у креативов и `deal` у пикселя (так их эмитят).
ACTION_RESOLVERS = {
    "traffic_new_work": _alive_traffic_new_work,
    "traffic_rework": _alive_traffic_rework,
    "weborama_pixel_needed": _alive_weborama_pixel,
}


def resolve_actions(db, now: datetime, dry_run: bool = False) -> dict:
    from app.models import Notification
    out = {}
    for key, alive_of in ACTION_RESOLVERS.items():
        rows = (db.query(Notification)
                .filter(Notification.kind == key, Notification.resolved_at.is_(None),
                        Notification.entity_id.isnot(None)).all())
        ids = {n.entity_id for n in rows}
        if not ids:
            out[key] = 0
            continue
        alive = alive_of(db, ids) & _open_deals(db, ids)
        gone = [n for n in rows if n.entity_id not in alive]
        if not dry_run:
            for n in gone:
                n.resolved_at = now
        out[key] = len(gone)
    return out


# ── строки сканера до схлопывания ────────────────────────────────────────────────

def resolve_legacy_scan_rows(db, now: datetime, dry_run: bool = False) -> dict:
    """Строки правил сканера без `dedup_key` (записаны до 14.09.2026).

    * есть более новая строка того же человека по тому же объекту — старая гаснет,
      иначе в панели две записи об одном;
    * у сканера нет открытого состояния по объекту — причина снята, строка гаснет;
    * причина жива — строке проставляется ключ, и дальше её гасит сам сканер.
    """
    from app.models import Notification
    from app.notify import registry
    from app.notify.bus import dedup_key

    scan_keys = [k for k, ev in registry.EVENTS.items() if ev.scan]
    rows = (db.query(Notification)
            .filter(Notification.kind.in_(scan_keys), Notification.dedup_key.is_(None),
                    Notification.resolved_at.is_(None), Notification.entity_id.isnot(None))
            .all())
    open_states = {(k, t, i) for k, t, i in db.execute(text("""
        SELECT event_key, entity_type, entity_id FROM notification_alert_state
        WHERE resolved_at IS NULL""")).all()}
    stats = {"duplicate": 0, "gone": 0, "keyed": 0}
    for n in rows:
        key = dedup_key(n.kind, n.entity_type, n.entity_id)
        newer = (db.query(Notification.id)
                 .filter(Notification.user_id == n.user_id, Notification.dedup_key == key,
                         Notification.resolved_at.is_(None), Notification.id != n.id)
                 .first())
        if newer:
            stats["duplicate"] += 1
            if not dry_run:
                n.resolved_at = now
        elif (n.kind, n.entity_type, n.entity_id) not in open_states:
            stats["gone"] += 1
            if not dry_run:
                n.resolved_at = now
        else:
            stats["keyed"] += 1
            if not dry_run:
                n.dedup_key = key
    return stats


# ── срок жизни ──────────────────────────────────────────────────────────────────

# Удаление — поимённое исключение стража `test_startup_ddl` (там же причина). Счёт для
# пробного прогона — отдельными запросами с тем же условием, а не срезкой текста DELETE:
# страж должен видеть оба удаления целиком.
NOTIF_EXPIRED = """
    (resolved_at IS NOT NULL AND resolved_at < :read_edge)
    OR (resolved_at IS NULL AND is_read AND created_at < :read_edge)
    OR (resolved_at IS NULL AND NOT is_read AND created_at < :unread_edge)"""
# Очередь дайджеста (`queued`) — недоставленное, её срок жизни не касается.
DELIVERY_EXPIRED = "status <> 'queued' AND created_at < :delivery_edge"

PURGE = {
    "notifications": ("SELECT count(*) FROM notifications WHERE " + NOTIF_EXPIRED,
                      "DELETE FROM notifications WHERE " + NOTIF_EXPIRED),
    "deliveries": ("SELECT count(*) FROM notification_deliveries WHERE " + DELIVERY_EXPIRED,
                   "DELETE FROM notification_deliveries WHERE " + DELIVERY_EXPIRED),
}


def purge(db, now: datetime, dry_run: bool = False) -> dict:
    params = {"read_edge": now - timedelta(days=READ_DAYS),
              "unread_edge": now - timedelta(days=UNREAD_DAYS),
              "delivery_edge": now - timedelta(days=DELIVERY_DAYS)}
    out = {}
    for name, (count_sql, delete_sql) in PURGE.items():
        if dry_run:
            out[name] = db.execute(text(count_sql), params).scalar()
        else:
            out[name] = db.execute(text(delete_sql), params).rowcount
    return out


def run(dry_run: bool = False, now: datetime = None) -> dict:
    now = now or datetime.utcnow()
    db = SessionLocal()
    try:
        out = {"actions": resolve_actions(db, now, dry_run),
               "legacy": resolve_legacy_scan_rows(db, now, dry_run),
               "purge": purge(db, now, dry_run), "dry_run": dry_run}
        if dry_run:
            db.rollback()
        else:
            db.commit()
        return out
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Гашение и срок жизни уведомлений панели")
    ap.add_argument("--dry-run", action="store_true")
    res = run(dry_run=ap.parse_args().dry_run)
    print(("(пробный прогон, ничего не записано) " if res["dry_run"] else "")
          + f"погашено задач: {res['actions']}; старые строки сканера: {res['legacy']}; "
          + f"удалено по сроку: {res['purge']}")
