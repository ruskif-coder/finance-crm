"""Демо-наполнение Weborama для стенда: сверка «факт | WR» на трёх демо-РК.

Зачем: на стенде нет ни одной строки статистики верификатора, и колонки «WR», строка
«Расхождение», карточка дня и метка «Большое расхождение с WR» (владелец 27.09.2026)
показывают прочерки — посмотреть, как они выглядят с данными, не на чем.

ЗАПУСК (только на локальном стенде):
    docker exec finance_backend python -m scripts.2026-09-27_demo_weborama
    docker exec finance_backend python -m scripts.2026-09-27_demo_weborama --undo

ОБРАТИМО ПОЛНОСТЬЮ: строки пишутся с `source = 'weborama_demo'` — это источник СВЕРКИ
(`stat_sources.VERIFIER`), в факт он не входит; откат — один DELETE по источнику.

Цифры — от демо-факта (`source = 'demo'`) тех же РК, по дням и площадкам: Weborama всегда
считает меньше. Три РК — три цвета шкалы: около 5 % (в норме), около 14 % (жёлтый),
около 26 % (красный, «Большое расхождение с WR»).
"""
import argparse
import random

from sqlalchemy import text

from app.database import SessionLocal

SOURCE = "weborama_demo"
# Доля, которую «засчитала» Weborama, — по одной на РК, с небольшим разбросом по дням.
SHARES = (0.95, 0.86, 0.74)


def seed(db):
    camps = [r[0] for r in db.execute(text(
        "SELECT campaign_id FROM ad_campaign_stat WHERE source = 'demo' "
        "GROUP BY campaign_id ORDER BY sum(shows) DESC LIMIT 3")).all()]
    if not camps:
        print("демо-факта нет — сначала scripts.2026-09-04_demo_traffic_month")
        return
    rnd = random.Random(27092026)
    made = 0
    for cid, share in zip(camps, SHARES):
        rows = db.execute(text(
            "SELECT placement_id, date, shows, clicks FROM ad_campaign_stat "
            "WHERE campaign_id = :c AND source = 'demo'"), {"c": cid}).all()
        for pid, d, shows, clicks in rows:
            k = share + rnd.uniform(-0.02, 0.02)
            db.execute(text(
                "INSERT INTO ad_campaign_stat (campaign_id, placement_id, date, shows, clicks, source) "
                "VALUES (:c, :p, :d, :s, :k, :src) ON CONFLICT DO NOTHING"),
                {"c": cid, "p": pid, "d": d, "s": int((shows or 0) * k),
                 "k": int((clicks or 0) * k), "src": SOURCE})
            made += 1
        code = db.execute(text("SELECT d.code FROM ad_campaign c JOIN sales_deals d ON d.id = c.deal_id "
                               "WHERE c.id = :c"), {"c": cid}).scalar()
        print(f"РК {cid} ({code}): WR ≈ {round(share * 100)} % от факта, строк {len(rows)}")
    db.commit()
    print(f"всего строк: {made}; источник '{SOURCE}' — откат: --undo")


def undo(db):
    n = db.execute(text("DELETE FROM ad_campaign_stat WHERE source = :s"), {"s": SOURCE}).rowcount
    db.commit()
    print(f"убрано строк: {n}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--undo", action="store_true", help="убрать демо-данные Weborama")
    args = ap.parse_args()
    from scripts._stand_guard import require_stand
    require_stand("демо-данные Weborama")
    db = SessionLocal()
    try:
        undo(db) if args.undo else seed(db)
    finally:
        db.close()
