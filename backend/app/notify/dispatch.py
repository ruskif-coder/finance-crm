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


def flush(dry_run: bool = False) -> dict:
    db = SessionLocal()
    stats = {"queued": 0, "sent": 0, "skipped": 0, "expired": 0, "failed": 0}
    now = datetime.utcnow()
    try:
        rows = (db.query(NotificationDelivery)
                .filter(NotificationDelivery.status == "queued",
                        NotificationDelivery.channel.in_(("tg", "mail")))
                .order_by(NotificationDelivery.id).limit(500).all())
        stats["queued"] = len(rows)
        for r in rows:
            age = now - (r.created_at or now)
            if age > timedelta(hours=MAX_AGE_HOURS):
                stats["expired"] += 1
                if not dry_run:
                    r.status = "suppressed"
                    r.suppress_reason = "expired"
                continue
            ev = registry.get(r.event_key)
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
                    continue
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
                continue

            if not telegram.configured() or ch is None or not ch.tg_chat_id or not ch.tg_verified_at:
                stats["skipped"] += 1
                continue
            if ev is not None and quiet_now(ch, ev):
                stats["skipped"] += 1          # всё ещё тихие часы — придём в следующий раз
                continue
            if dry_run:
                stats["sent"] += 1
                print(f"    (сухой прогон) → {r.user_id}: {r.title}")
                continue
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
        db.commit()
        print(f"Очередь досылки: в очереди {stats['queued']}, отправлено {stats['sent']}, "
              f"отложено {stats['skipped']}, протухло {stats['expired']}, "
              f"ошибок {stats['failed']}" + (" (СУХОЙ ПРОГОН)" if dry_run else ""))
        return stats
    finally:
        db.close()


if __name__ == "__main__":
    flush(dry_run="--dry-run" in sys.argv)
