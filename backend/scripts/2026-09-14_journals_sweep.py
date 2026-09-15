# -*- coding: utf-8 -*-
"""Уборка журналов по сроку хранения: почта и доставки уведомлений.

Срок живёт в `app/retention.py` и здесь НЕ повторяется: второй счёт того же правила
однажды разошёлся бы, и мы стёрли бы сообщения раньше обещанного — а экран продолжал бы
обещать три месяца.

    docker exec finance_backend python -m scripts.2026-09-14_journals_sweep
    docker exec finance_backend python -m scripts.2026-09-14_journals_sweep --apply

**По умолчанию НИЧЕГО НЕ УДАЛЯЕТСЯ.** Нужен явный `--apply`: уборка необратима, а
письмо — то, на что ссылаются в споре с площадкой. Сухой прогон печатает ровно то, что
удалил бы, с разбивкой по месяцам: объём должен быть виден ДО уборки, а не после.

Удаление ПАЧКАМИ: одна транзакция на сто тысяч строк держит блокировку на таблице, в
которую в это же время пишет отправка.

Оба журнала в одном скрипте намеренно. Срок у них общий, и два файла с одинаковым
правилом — это два места, где его можно забыть поправить.
"""
import sys

from sqlalchemy import func

from app import retention
from app.database import SessionLocal
from app.mail.models import MailLog
from app.notify.models import NotificationDelivery

BATCH = 1000

# Журналы под уборкой: подпись, модель, колонка времени, колонка статуса.
# `notifications` (строки панели) сюда НЕ входит — это состояние, а не журнал.
JOURNALS = (
    ("журнал писем", MailLog, MailLog.created_at, MailLog.status),
    ("доставки уведомлений", NotificationDelivery,
     NotificationDelivery.created_at, NotificationDelivery.status),
)


def _sweep_one(db, label, model, created, status, edge, apply: bool) -> dict:
    old = created < edge
    doomed = old & status.notin_(retention.KEEP_STATUSES)

    total = db.query(model).filter(doomed).count()
    kept = db.query(model).filter(old, status.in_(retention.KEEP_STATUSES)).count()
    by_month = (db.query(func.to_char(created, "YYYY-MM"), func.count(model.id))
                .filter(doomed).group_by(func.to_char(created, "YYYY-MM"))
                .order_by(func.to_char(created, "YYYY-MM")).all())

    print(f"\n{label}")
    for m, n in by_month:
        print(f"    {m}: {n}")
    print(f"  под уборку: {total}"
          + (f"; в очереди старше границы: {kept} (не трогаем)" if kept else ""))

    if not apply or not total:
        return {"total": total, "deleted": 0, "kept": kept}

    deleted = 0
    while True:
        ids = [r[0] for r in db.query(model.id).filter(doomed)
               .order_by(model.id).limit(BATCH).all()]
        if not ids:
            break
        db.query(model).filter(model.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        deleted += len(ids)
        print(f"    удалено {deleted} из {total}")
    return {"total": total, "deleted": deleted, "kept": kept}


def sweep(apply: bool = False) -> dict:
    db = SessionLocal()
    edge = retention.cutoff()
    try:
        print(f"Срок хранения: {retention.JOURNAL_MONTHS} мес. → "
              f"граница {edge:%d.%m.%Y}")
        out = {}
        for label, model, created, status in JOURNALS:
            out[label] = _sweep_one(db, label, model, created, status, edge, apply)
        if not apply:
            print("\nСУХОЙ ПРОГОН — ничего не удалено. Для уборки: --apply")
        return out
    finally:
        db.close()


if __name__ == "__main__":
    sweep(apply="--apply" in sys.argv)
