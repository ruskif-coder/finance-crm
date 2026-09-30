# -*- coding: utf-8 -*-
"""Разовые поправки данных к v2.6.53 (владелец 30.09.2026).

1. Получатели комплекта, согласовавшие комплект с ЕРИД, но оставшиеся «согласован»:
   ЕРИД — свойство комплекта, отметку ставил только сам выпуск маркера. На проде 30.09 —
   68 получателей в 9 сделках. Переводим в «ерид получен».
2. Креативы РК, возвращённые трафиком или площадкой на переделку, стояли «у трафика» /
   «у площадки»: синк понимал только вердикт «ок». Пересобираем креативы сделок, где такие
   есть (`build.sync_deal`) — после правки кода они становятся «отклонён».
3. Пересчёт долей всех открытых РК (`build.refresh_weights`) — потолок по поверхности.
0. (первым) Состав РК = получатели сделки (владелец 30.09.2026): синк раньше наполнял РК
   всеми площадками услуги, включая архивные (dialog.ru) и не взятые аккаунтом, и доли с
   индексом делились и на них. `build.sync_all` убирает лишние «без следа» (без креативов,
   статистики, пикселя, ручного статуса) и добавляет недостающих получателей.

По умолчанию — пробный прогон. Запись: `--apply`. Повторный прогон ничего не меняет.

    docker exec finance_backend python -m scripts.2026-09-30_chain_fixups [--apply]
"""
import sys

from sqlalchemy import text

import app.main  # noqa: F401 — все модели в реестре SQLAlchemy
from app.ad import build
from app.database import SessionLocal

STUCK_SQL = """
    SELECT t.id FROM launch_prep_target t
     WHERE t.state = 'согласован' AND EXISTS (
           SELECT 1 FROM launch_prep_pair pr
             JOIN launch_prep_creative_set s ON s.id = pr.set_id
            WHERE pr.target_id = t.id AND pr.agreed_at IS NOT NULL
              AND pr.withdrawn_at IS NULL AND s.erid IS NOT NULL)
"""
REWORK_DEALS_SQL = """
    SELECT DISTINCT c.deal_id FROM ad_campaign_creative cr
      JOIN ad_campaign c ON c.id = cr.campaign_id
      JOIN launch_prep_review rv ON rv.pair_id = cr.pair_id
     WHERE rv.verdict IS NOT NULL AND rv.verdict <> 'ок'
       AND cr.status IN ('у трафика', 'у площадки')
"""
COUNT_SQL = """
    SELECT count(*) FROM ad_campaign_creative cr
      JOIN launch_prep_review rv ON rv.pair_id = cr.pair_id
     WHERE rv.verdict IS NOT NULL AND rv.verdict <> 'ок'
       AND cr.status IN ('у трафика', 'у площадки')
"""


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        res0 = build.sync_all(db, commit=False)
        print(f"0. площадок в РК: убрано {res0['placements_removed']}, "
              f"добавлено {res0['placements_added']}")

        ids = [r[0] for r in db.execute(text(STUCK_SQL))]
        if ids:
            db.execute(text("UPDATE launch_prep_target SET state = 'ерид получен' "
                            "WHERE id = ANY(:i)"), {"i": ids})
        print(f"1. получателей «согласован» → «ерид получен»: {len(ids)}")

        before = db.execute(text(COUNT_SQL)).scalar()
        deals = [r[0] for r in db.execute(text(REWORK_DEALS_SQL))]
        codes = dict(db.execute(text("SELECT id, code FROM sales_deals WHERE id = ANY(:d)"),
                                {"d": deals}).all()) if deals else {}
        for d in deals:
            build.sync_deal(db, d, commit=False)
        db.flush()
        after = db.execute(text(COUNT_SQL)).scalar()
        print(f"2. креативов «на переделку», висевших «у трафика/площадки»: {before} → {after}; "
              f"сделки: {', '.join(codes.get(d, str(d)) for d in deals) or '—'}")

        # 3. Доли всех открытых РК — по правилу «ручной индекс снимает потолок только со
        #    своей поверхности» (v2.6.53). До пересчёта сохранённые доли — по старому правилу.
        res = build.refresh_weights(db, commit=False)
        print(f"3. доли пересчитаны: РК {res['campaigns']}, весов изменено {res['weights_changed']}")

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
