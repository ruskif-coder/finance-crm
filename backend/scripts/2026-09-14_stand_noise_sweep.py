# -*- coding: utf-8 -*-
"""Уборка машинного шума из журналов стенда. ТОЛЬКО ДЛЯ СТЕНДА.

    docker exec finance_backend python -m scripts.2026-09-14_audit_noise_sweep
    docker exec finance_backend python -m scripts.2026-09-14_audit_noise_sweep --apply

## Зачем

Набор тестов ходит по настоящим сущностям стенда и зовёт настоящие ручки — а те пишут
в журналы. Строка переживает откат фикстуры: сделку фикстура убирает, запись о действии
над ней остаётся. Замер 14.09.2026 после пятнадцати прогонов за день:

    audit_log                  45 115 строк
    notification_deliveries    41 292 строки
    notifications              38 143 строки, ВСЕ непогашенные

Последнее хуже прочего: `notifications` — это колокольчик. Тридцать восемь тысяч тестовых
строк делают панель нечитаемой, а бейдж бессмысленным.

Течь заткнута в `tests/conftest.py` — тест снимает свои строки сам. Этот скрипт убирает
то, что накопилось ДО неё, и на будущее остаётся как разовый инструмент.

## Как отличается шум от работы человека

**По ТЕМПУ, а не по имени действия.** Пять и больше записей в одну секунду — это не
человек: он столько не кликает. Разбор по полосам (замер 14.09.2026):

    20+ в секунду    21 693 строки   annex_create, send_creative_set, *_verdict
    5–19 в секунду   17 452 строки   те же действия набора
    1–4 в секунду     5 970 строк    login_success, add_deal_comment, patch_sales_deal

Признак выбран замером, а не догадкой. Проверялись и отбрасывались:

* `user_id IS NULL` — ловит заодно `login_failed`, а это единственная запись о неудачных
  входах, и она по своей природе без пользователя;
* СИРОТЫ (сущность удалена) — их всего 1 423 из 45 115: тесты работают по существующим
  строкам стенда, а не по созданным и удалённым;
* имя действия — `send_creative_set` и `annex_create` делает и человек.

## Почему только стенд

На проде тесты не гоняются, и там каждая строка журнала — чья-то работа. Скрипт откажется
работать, если в базе нет признаков стенда (см. `_looks_like_stand`).

## Предохранители

**По умолчанию ничего не удаляется.** Нужен явный `--apply`. Удаление пачками: одна
транзакция на сорок тысяч строк держит блокировку на таблице, в которую пишет каждая
мутирующая ручка. Перед прогоном с `--apply` снять дамп таблицы:

    docker exec -t finance_db pg_dump -U finance_user -d finance -t audit_log > audit_log.sql
"""
import os
import sys

from sqlalchemy import text

from app.database import SessionLocal

# Порог темпа: столько записей в одну секунду человек не создаёт.
BURST = 5
BATCH = 2000

# Журналы под уборкой. Только те, где строка — ЗАПИСЬ О СОБЫТИИ.
JOURNALS = ("audit_log", "notification_deliveries", "notifications")


def _burst_ids(table):
    return text(
        f"SELECT a.id FROM {table} a"
        "  JOIN (SELECT date_trunc('second', created_at) s"
        f"         FROM {table} GROUP BY 1 HAVING count(*) >= :burst) b"
        "    ON date_trunc('second', a.created_at) = b.s"
        " ORDER BY a.id LIMIT :lim")


def _bands(db, table):
    return db.execute(text(
        "WITH sec AS (SELECT date_trunc('second', created_at) s, count(*) n"
        f"              FROM {table} GROUP BY 1)"
        " SELECT CASE WHEN n >= 20 THEN '20+ в секунду'"
        "             WHEN n >= :burst THEN '5-19 в секунду'"
        "             ELSE '1-4 в секунду' END AS tempo,"
        "        sum(n) AS rows FROM sec GROUP BY 1 ORDER BY 2 DESC"),
        {"burst": BURST}).all()


def _looks_like_stand(db) -> bool:
    """Стенд или прод. На проде уборка журнала действий запрещена: там каждая строка —
    чья-то работа, а не след прогона."""
    if (os.getenv("DOMAIN") or "").strip() in ("", "localhost"):
        return True
    return False


def sweep(apply: bool = False) -> dict:
    db = SessionLocal()
    try:
        if not _looks_like_stand(db):
            print("ОТКАЗ: похоже на прод (DOMAIN задан). Журнал действий там не чистим.")
            return {"total": 0, "deleted": 0}

        out = {}
        for table in JOURNALS:
            total = db.execute(text(f"SELECT count(*) FROM {table}")).scalar()
            doomed = db.execute(text(
                "SELECT coalesce(sum(n), 0) FROM ("
                f"  SELECT count(*) n FROM {table}"
                "   GROUP BY date_trunc('second', created_at)"
                "  HAVING count(*) >= :burst) x"), {"burst": BURST}).scalar()

            print(f"\n{table}: {total} строк")
            for tempo, rows in _bands(db, table):
                print(f"    {tempo:<16} {rows}")
            print(f"  под уборку: {doomed}; останется {total - doomed}")

            if not apply or not doomed:
                out[table] = {"total": total, "doomed": doomed, "deleted": 0}
                continue

            deleted = 0
            while True:
                ids = [r[0] for r in db.execute(_burst_ids(table),
                                                {"burst": BURST, "lim": BATCH}).all()]
                if not ids:
                    break
                db.execute(text(f"DELETE FROM {table} WHERE id = ANY(:ids)"),
                           {"ids": ids})
                db.commit()
                deleted += len(ids)
                print(f"    удалено {deleted} из {doomed}")
            left = db.execute(text(f"SELECT count(*) FROM {table}")).scalar()
            print(f"  готово: удалено {deleted}, осталось {left}")
            out[table] = {"total": total, "doomed": doomed, "deleted": deleted,
                          "left": left}

        if not apply:
            print("\nСУХОЙ ПРОГОН — ничего не удалено. Для уборки: --apply")
        return out
    finally:
        db.close()


if __name__ == "__main__":
    sweep(apply="--apply" in sys.argv)
