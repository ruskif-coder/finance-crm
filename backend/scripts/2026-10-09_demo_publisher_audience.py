# -*- coding: utf-8 -*-
"""Демо-заявленная аудитория площадок для стенда (экран «Паблишеры → Аудитория», 09.10.2026).

Зачем: на стенде нет ни одного медиакита, колонка «заявлено» пустая, и карта «охват ×
стикинесс» нечего рисовать. Цифры здесь — выдуманные, правдоподобные по виду площадки.

ЗАПУСК (только на локальном стенде):
    docker exec finance_backend python -m scripts.2026-10-09_demo_publisher_audience
    docker exec finance_backend python -m scripts.2026-10-09_demo_publisher_audience --undo

ОБРАТИМО ПОЛНОСТЬЮ: все строки с `source = 'демо'` — откат один DELETE по источнику.
Повторный запуск сначала снимает прежние демо-строки, дублей не плодит.

Берутся АКТИВНЫЕ площадки (статус «СОТРУДНИЧАЕМ»); заполняются все метрики каталога, установки —
только у площадок с app-поверхностью, MAU дополнительно делится по поверхностям. MAU подбирается так, чтобы разрыв
(уники Adfox / MAU) лёг в разные цвета шкалы — зелёный, жёлтый, красный.
"""
import argparse
import random
from datetime import date, timedelta

from sqlalchemy import text

import app.model_registry  # noqa: F401 — разовый скрипт вне uvicorn: регистрирует модели
from app.ad.stat_sources import OWN
from app.database import SessionLocal

SOURCE = "демо"
# Стикинесс по виду площадки: аптеки заходят редко, доставки и такси — каждый день.
STICK = {"Аптеки": (0.06, 0.12), "Доставка": (0.30, 0.50), "Сервисы": (0.35, 0.55),
         "Агрегаторы": (0.10, 0.18), "Маркетплейсы": (0.12, 0.20)}
GAPS = (0.30, 0.17, 0.07)   # уники/MAU → зелёный, жёлтый, красный


ACTIVE = "СОТРУДНИЧАЕМ"


def _pubs(db):
    """Активные площадки (статус «СОТРУДНИЧАЕМ», владелец 09.10.2026) с нашим фактом за 60 дней,
    если он есть; поверхности — чтобы установки класть только на app."""
    return db.execute(text("""
        SELECT p.id, p.kind, p.name,
               (SELECT sum(s.shows) FROM ad_campaign_stat s JOIN ad_campaign_placement pl ON pl.id = s.placement_id
                 WHERE pl.publisher_id = p.id AND s.date >= :d AND s.source = ANY(:own)) AS shows,
               (SELECT sum(s.uniques) FROM ad_campaign_stat s JOIN ad_campaign_placement pl ON pl.id = s.placement_id
                 WHERE pl.publisher_id = p.id AND s.date >= :d AND s.source = 'adfox') AS uniques,
               EXISTS (SELECT 1 FROM sales_publisher_surfaces sf WHERE sf.publisher_id = p.id AND sf.kind = 'app') AS has_app,
               EXISTS (SELECT 1 FROM sales_publisher_surfaces sf WHERE sf.publisher_id = p.id AND sf.kind = 'web') AS has_web
          FROM sales_publishers p
         WHERE p.is_active AND p.status = :st
         ORDER BY 4 DESC NULLS LAST, p.name
    """), {"own": list(OWN), "d": date.today() - timedelta(days=60), "st": ACTIVE}).all()


def seed(db):
    undo(db, quiet=True)
    rnd = random.Random(9102026)
    rows = _pubs(db)
    if not rows:
        print("нет площадок с нашим фактом за 60 дней — нечем сравнивать")
        return
    ins = text("""INSERT INTO sales_publisher_audience
                  (publisher_id, surface_kind, metric, segment, value, source, measured_at, note)
                  VALUES (:p, :sk, :m, :seg, :v, :src, :d, 'демо-строка, снять --undo')""")
    made = 0
    for i, (pid, kind, name, shows, uniques, has_app, has_web) in enumerate(rows):
        lo, hi = STICK.get(kind or "", (0.10, 0.25))
        stick = round(rnd.uniform(lo, hi), 2)
        # MAU от уников (если есть) под нужный цвет разрыва, иначе от показов, иначе просто по виду.
        base = uniques if uniques else max(50_000, int((shows or rnd.randint(300_000, 3_000_000)) * rnd.uniform(0.08, 0.2)))
        mau = int(base / GAPS[i % 3] / 1000) * 1000
        dau = int(mau * stick / 100) * 100
        wau = int(mau * rnd.uniform(0.35, 0.6) / 100) * 100
        measured = date.today() - timedelta(days=rnd.randint(10, 240))
        rows_out = [
            ("mau", None, None, mau), ("dau", None, None, dau), ("wau", None, None, wau),
            ("avg_time", None, None, round(rnd.uniform(2.5, 9.0), 1)),
            ("share", None, "Ж", round(rnd.uniform(55, 78), 1)),
            ("share", None, "25–54", round(rnd.uniform(48, 70), 1)),
            ("share", None, "Москва и МО", round(rnd.uniform(18, 42), 1)),
            ("share", None, "доход B+", round(rnd.uniform(30, 60), 1)),
            ("affinity", None, "фарма", int(rnd.uniform(140, 380))),
            ("affinity", None, "FMCG", int(rnd.uniform(90, 220))),
        ]
        # Поверхности: MAU делится между web и app, установки — только у app.
        if has_app and has_web:
            app_share = rnd.uniform(0.3, 0.7)
            rows_out += [("mau", "web", None, int(mau * (1 - app_share) / 1000) * 1000),
                         ("mau", "app", None, int(mau * app_share / 1000) * 1000)]
        if has_app:
            rows_out.append(("installs", "app", None, int(mau * rnd.uniform(1.5, 4.0) / 1000) * 1000))
        for m, sk, seg, v in rows_out:
            db.execute(ins, {"p": pid, "sk": sk, "m": m, "seg": seg, "v": v, "src": SOURCE, "d": measured})
            made += 1
    db.commit()
    print(f"площадок: {len(rows)}, строк: {made}, источник «{SOURCE}»")


def undo(db, quiet=False):
    n = db.execute(text("DELETE FROM sales_publisher_audience WHERE source = :s"), {"s": SOURCE}).rowcount
    db.commit()
    if not quiet:
        print(f"снято строк: {n}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--undo", action="store_true")
    args = ap.parse_args()
    from scripts._stand_guard import require_stand
    require_stand("демо-аудитория площадок")
    db = SessionLocal()
    try:
        undo(db) if args.undo else seed(db)
    finally:
        db.close()
