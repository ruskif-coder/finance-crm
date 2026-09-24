"""Досылка отложенного: строки журнала со статусом queued.

Зачем: сообщение может не уйти в момент события — тихие часы у получателя, не привязан
Telegram, не задан токен бота. Терять его нельзя, поэтому оно ложится в журнал как
queued и уходит отсюда, когда причина отпала.

    docker exec finance_backend python -m app.notify.dispatch --dry-run
    docker exec finance_backend python -m app.notify.dispatch

Ставится в cron почаще сканера (раз в час): его задача — не искать события, а
разгребать очередь.

Протухшее не шлём: напоминание «срок оплаты через 10 дней», доставленное через неделю,
хуже, чем недоставленное. Порог — MAX_AGE_HOURS.
"""
import sys
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.notify import registry, telegram
from app.notify import channels
from app.notify.channels import quiet_now
from app.notify.models import NotificationDelivery, UserNotificationChannels
from app.models import User

MAX_AGE_HOURS = 48


class _Busy(RuntimeError):
    pass


def flush(dry_run: bool = False) -> dict:
    """Один прогон за раз (ревью 24.09.2026): крон и ручной запуск, наложившись, брали
    одни и те же строки очереди, и письмо уходило дважды. Второй прогон ничего не шлёт."""
    from app.ext_lock import STAFF_DISPATCH, only_one
    try:
        with only_one(STAFF_DISPATCH, 1, _Busy, "Досылка уведомлений"):
            return _flush(dry_run)
    except _Busy:
        print("досылка: предыдущий прогон ещё идёт — этот пропускаю")
        return {"queued": 0, "sent": 0, "skipped": 0, "expired": 0, "failed": 0,
                "busy": True}


def _flush(dry_run: bool = False) -> dict:
    db = SessionLocal()
    stats = {"queued": 0, "sent": 0, "skipped": 0, "expired": 0, "failed": 0}
    now = datetime.utcnow()
    try:
        rows = (db.query(NotificationDelivery)
                .filter(NotificationDelivery.status == "queued",
                        NotificationDelivery.channel.in_(("tg", "mail")))
                .order_by(NotificationDelivery.id).limit(500).all())
        stats["queued"] = len(rows)
        active = {u.id for u in db.query(User.id).filter(
            User.id.in_({r.user_id for r in rows} or {0}), User.is_active == 1).all()}
        for r in rows:
            # Строка за строкой, каждая своим коммитом (аудит 23.09.2026, 5.M5): один
            # коммит в конце при исключении посреди оставлял отправленное в очереди, и
            # те же письма уходили каждый час до 48 часов.
            try:
                _one(db, r, now, dry_run, stats, active)
            except Exception as e:                  # noqa: BLE001 — одна строка
                db.rollback()
                stats["failed"] += 1
                print(f"  ! строка {r.id}: {type(e).__name__}: {e}")
                continue
            if not dry_run:
                db.commit()
        print(f"Очередь досылки: в очереди {stats['queued']}, отправлено {stats['sent']}, "
              f"отложено {stats['skipped']}, протухло {stats['expired']}, "
              f"ошибок {stats['failed']}" + (" (СУХОЙ ПРОГОН)" if dry_run else ""))
        return stats
    finally:
        db.close()


def _one(db, r, now, dry_run: bool, stats: dict, active: set) -> None:
    """Одна строка очереди. Исход записывается в саму строку; коммитит вызывающий."""
    # Отключённому сотруднику накопленное не досылается (аудит 23.09.2026, 5.L5): человек
    # ушёл, а письма про сделки шли бы ему дальше.
    if r.user_id not in active:
        if not dry_run:
            r.status, r.suppress_reason = "suppressed", "user_inactive"
        stats["skipped"] += 1
        return
    age = now - (r.created_at or now)
    if age > timedelta(hours=MAX_AGE_HOURS):
        stats["expired"] += 1
        if not dry_run:
            r.status = "suppressed"
            r.suppress_reason = "expired"
        return
    ev = registry.get(r.event_key)
    # Событие убрали из реестра, а строка осталась. Раньше она роняла прогон
    # (проверка тихих часов читала поля пустого события) — теперь гасится.
    if ev is None:
        if not dry_run:
            r.status, r.suppress_reason = "suppressed", "event_removed"
        stats["skipped"] += 1
        return
    ch = (db.query(UserNotificationChannels)
          .filter(UserNotificationChannels.user_id == r.user_id).first())

    # Почта разгребается ТОЙ ЖЕ очередью, что телеграм: причина откладывания у
    # них одна и та же — канал не настроен, адреса нет, тихие часы. Отдельная
    # очередь означала бы второе место, где считается протухание и повтор.
    if r.channel == "mail":
        if dry_run:
            u = db.query(User).filter(User.id == r.user_id).first()
            stats["sent"] += 1
            print(f"    (сухой прогон) письмо -> "
                  f"{u.email if u else r.user_id}: {r.title}")
            return
        # Отправляем ТЕМ ЖЕ каналом, что и живую доставку. Пока досылка слала
        # сама, письмо расходилось с живым: телом уходил ЗАГОЛОВОК, без текста,
        # фактов и кнопки. Одно событие, два разных письма, и разницу видел
        # только получатель. Тело и ссылка берутся из журнала — ради этого они
        # там и появились (миграция 2026-09-14_delivery_body_link.sql).
        status, _, reason = channels.deliver_mail(
            db, r.user_id, ev, r.title or "", r.body, r.link,
            r.facts, r.code).partition("|")
        if status == "sent":
            r.status, r.suppress_reason = "sent", None
            stats["sent"] += 1
        elif status == "failed":
            r.status, r.error = "failed", (reason or None)
            stats["failed"] += 1
        else:
            stats["skipped"] += 1       # канал не готов или тихие часы
        return

    if not telegram.configured() or ch is None or not ch.tg_chat_id or not ch.tg_verified_at:
        stats["skipped"] += 1
        return
    if ev is not None and quiet_now(ch, ev):
        stats["skipped"] += 1          # всё ещё тихие часы — придём в следующий раз
        return
    if dry_run:
        stats["sent"] += 1
        print(f"    (сухой прогон) → {r.user_id}: {r.title}")
        return
    try:
        telegram.send_message(
            ch.tg_chat_id,
            channels.tg_text(r.title or "", r.body, r.facts),
            link=r.link)
        r.status, r.suppress_reason = "sent", None
        stats["sent"] += 1
    except Exception as e:
        r.status, r.error = "failed", str(e)[:400]
        stats["failed"] += 1


if __name__ == "__main__":
    flush(dry_run="--dry-run" in sys.argv)
