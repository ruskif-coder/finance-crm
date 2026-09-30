# -*- coding: utf-8 -*-
"""Услуга Polza: площадка — polza.ru, а не economapteka.ru (владелец 30.09.2026).

В реестре паблишеров услуга Polza была привязана к economapteka.ru (web), а polza.ru —
ни к чему. Креативы аккаунты слали на polza.ru, а РК собиралась по реестру — и трафик
везде видел economapteka.ru. Скрипт:

1. привязывает Polza к polza.ru web и ставит поверхности «работаем»;
2. гасит (is_active = false, строку не удаляет) привязку Polza → economapteka.ru;
3. в РК, где economapteka.ru больше не кандидат, убирает её размещение — только если
   оно не тронуто: «ждёт сборки», без креативов РК, без статистики, без пикселя WR;
4. досыпает кандидатов (`sync_placements`) — polza.ru встаёт в РК с меткой «не наш код».

По умолчанию — пробный прогон. Запись: `--apply`. Повторный прогон ничего не меняет.

    docker exec finance_backend python -m scripts.2026-09-30_polza_publisher_fix [--apply]
"""
import sys

from sqlalchemy import text

import app.models  # noqa: F401 — регистрирует таблицы для FK моделей продаж
from app.ad.build import candidates, deal_plan, sync_placements
from app.ad.models import AdCampaign
from app.database import SessionLocal

SERVICE = "Polza"
RIGHT, WRONG = "polza.ru", "economapteka.ru"
UNTOUCHED = "ждёт сборки"


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        svc = db.execute(text("SELECT id FROM sales_services WHERE name = :n"), {"n": SERVICE}).scalar()
        right = db.execute(text("SELECT id FROM sales_publishers WHERE domain = :d"), {"d": RIGHT}).scalar()
        wrong = db.execute(text("SELECT id FROM sales_publishers WHERE domain = :d"), {"d": WRONG}).scalar()
        if not (svc and right and wrong):
            sys.exit(f"не найдено: услуга={svc} {RIGHT}={right} {WRONG}={wrong}")

        db.execute(text("""UPDATE sales_publisher_surfaces SET we_work = true
                            WHERE publisher_id = :p AND kind = 'web' AND NOT we_work"""), {"p": right})
        db.execute(text("""
            INSERT INTO sales_publisher_services (publisher_id, surface_kind, service_id, is_active)
            VALUES (:p, 'web', :s, true)
            ON CONFLICT (publisher_id, surface_kind, service_id) DO UPDATE SET is_active = true
        """), {"p": right, "s": svc})
        off = db.execute(text("""UPDATE sales_publisher_services SET is_active = false
                                  WHERE publisher_id = :p AND service_id = :s AND is_active"""),
                         {"p": wrong, "s": svc}).rowcount
        print(f"реестр: {SERVICE} → {RIGHT} web (работаем); погашено привязок к {WRONG}: {off}")

        for camp in db.query(AdCampaign).order_by(AdCampaign.id):
            plan = deal_plan(db, camp.deal_id)
            if SERVICE not in (plan.get("services") or []):
                continue
            cand = {c["publisher_id"] for c in candidates(db, plan["services"], plan["surfaces"])}
            removed = 0
            if wrong not in cand:
                removed = db.execute(text("""
                    DELETE FROM ad_campaign_placement pl
                     WHERE pl.campaign_id = :c AND pl.publisher_id = :p AND pl.status = :st
                       AND pl.weborama_pixel IS NULL
                       AND NOT EXISTS (SELECT 1 FROM ad_campaign_creative r WHERE r.placement_id = pl.id)
                       AND NOT EXISTS (SELECT 1 FROM ad_campaign_stat s WHERE s.placement_id = pl.id)
                """), {"c": camp.id, "p": wrong, "st": UNTOUCHED}).rowcount
                kept = db.execute(text("""SELECT count(*) FROM ad_campaign_placement
                                           WHERE campaign_id = :c AND publisher_id = :p"""),
                                  {"c": camp.id, "p": wrong}).scalar()
                if kept:
                    print(f"  РК {camp.id}: {WRONG} ОСТАВЛЕНА — размещение уже в работе, решать руками")
            res = sync_placements(db, camp, commit=False)
            print(f"  РК {camp.id} (сделка {camp.deal_id}): убрано {WRONG}: {removed}, "
                  f"добавлено кандидатов: {res.get('added')}")

        if apply:
            db.commit()
            print("ЗАПИСАНО")
        else:
            db.rollback()
            print("пробный прогон — ничего не записано; для записи --apply")
    finally:
        db.close()


if __name__ == "__main__":
    main("--apply" in sys.argv)
