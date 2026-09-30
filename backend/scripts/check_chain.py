# -*- coding: utf-8 -*-
"""Сквозные инварианты цепочки запуска — прибор, а не отчёт (30.09.2026).

Проверяет на живых данных то, что держат разные модули по отдельности и что ломается
на стыках: креатив → ЕРИД → Weborama → DSP → запуск, доли и потолок балансировщика,
площадки вне нашей DSP, отметки получателей, имена файлов кабинета. Только чтение.

    docker exec finance_backend python -m scripts.check_chain [--sync]

`--sync` сначала прогоняет ночной `build.sync_all` в транзакции (без записи) и проверяет
состояние ПОСЛЕ него — то, что увидят утром. Код выхода 1, если есть нарушения (BAD).
"""
import sys

from sqlalchemy import text

import app.main  # noqa: F401 — все модели в реестре SQLAlchemy
from app.database import SessionLocal

OPEN_RK = "coalesce(c.status,'') NOT IN ('окончена','остановлена','архив')"

# (уровень, название, SQL → строки-нарушители). BAD — нарушение, INFO — к сведению.
CHECKS = [
    ("BAD", "креатив в DSP без ЕРИД", """
        SELECT d.code, p.domain FROM ad_campaign_creative cr
          JOIN ad_campaign_placement pl ON pl.id = cr.placement_id
          JOIN ad_campaign c ON c.id = pl.campaign_id JOIN sales_deals d ON d.id = c.deal_id
          JOIN sales_publishers p ON p.id = pl.publisher_id
         WHERE coalesce(cr.ms_creative_xxhash,'') <> '' AND cr.erid IS NULL"""),
    ("BAD", "креатив в DSP не согласован", """
        SELECT d.code, cr.status FROM ad_campaign_creative cr
          JOIN ad_campaign c ON c.id = cr.campaign_id JOIN sales_deals d ON d.id = c.deal_id
         WHERE coalesce(cr.ms_creative_xxhash,'') <> ''
           AND cr.status NOT IN ('согласован','запущен','пауза','отклонён')"""),
    ("BAD", "площадка «запущен» без согласованного креатива", """
        SELECT d.code, p.domain FROM ad_campaign_placement pl
          JOIN ad_campaign c ON c.id = pl.campaign_id JOIN sales_deals d ON d.id = c.deal_id
          JOIN sales_publishers p ON p.id = pl.publisher_id
         WHERE pl.status = 'запущен' AND NOT EXISTS (SELECT 1 FROM ad_campaign_creative cr
               WHERE cr.placement_id = pl.id AND cr.status IN ('согласован','запущен','пауза'))"""),
    ("BAD", "РК запущена/пауза без кампании в DSP", """
        SELECT d.code, c.status FROM ad_campaign c JOIN sales_deals d ON d.id = c.deal_id
         WHERE c.status IN ('запущена','пауза') AND coalesce(c.ms_campaign_xxhash,'') = ''"""),
    ("BAD", "получатель «согласован», а у комплекта уже есть ЕРИД", """
        SELECT d.code, count(*) FROM launch_prep_target t JOIN sales_deals d ON d.id = t.deal_id
         WHERE t.state = 'согласован' AND EXISTS (SELECT 1 FROM launch_prep_pair pr
               JOIN launch_prep_creative_set s ON s.id = pr.set_id
               WHERE pr.target_id = t.id AND pr.agreed_at IS NOT NULL
                 AND pr.withdrawn_at IS NULL AND s.erid IS NOT NULL) GROUP BY 1"""),
    ("BAD", "креатив «на переделку» висит «у трафика/у площадки»", """
        SELECT d.code, count(*) FROM ad_campaign_creative cr
          JOIN ad_campaign c ON c.id = cr.campaign_id JOIN sales_deals d ON d.id = c.deal_id
          JOIN launch_prep_review rv ON rv.pair_id = cr.pair_id
         WHERE rv.verdict IS NOT NULL AND rv.verdict <> 'ок'
           AND cr.status IN ('у трафика','у площадки')
           AND coalesce(cr.ms_creative_xxhash,'') = '' GROUP BY 1"""),
    ("BAD", "копия ЕРИД в креативе РК расходится с комплектом", """
        SELECT d.code, count(*) FROM ad_campaign_creative cr
          JOIN launch_prep_creative_set s ON s.id = cr.root_set_id
          JOIN ad_campaign c ON c.id = cr.campaign_id JOIN sales_deals d ON d.id = c.deal_id
         WHERE s.erid IS NOT NULL AND cr.erid IS DISTINCT FROM s.erid GROUP BY 1"""),
    ("BAD", "открытая РК: сумма долей не 1 и не 0", f"""
        SELECT d.code, round(sum(pl.share)::numeric, 4) FROM ad_campaign_placement pl
          JOIN ad_campaign c ON c.id = pl.campaign_id JOIN sales_deals d ON d.id = c.deal_id
         WHERE {OPEN_RK} GROUP BY 1 HAVING sum(coalesce(pl.share,0)) > 0.001
            AND abs(sum(coalesce(pl.share,0)) - 1) > 0.001"""),
    ("INFO", "пиксель Weborama на площадке без креатива с ЕРИД (выдан до v2.6.53)", """
        SELECT d.code, p.domain FROM ad_campaign_placement pl
          JOIN ad_campaign c ON c.id = pl.campaign_id JOIN sales_deals d ON d.id = c.deal_id
          JOIN sales_publishers p ON p.id = pl.publisher_id
         WHERE pl.weborama_pixel IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ad_campaign_creative cr
               WHERE cr.placement_id = pl.id AND cr.erid IS NOT NULL
                 AND cr.status IN ('согласован','запущен','пауза'))"""),
    ("INFO", "открытые РК без распределения (ни у одной площадки нет веса)", f"""
        SELECT d.code, count(pl.id) FROM ad_campaign c JOIN sales_deals d ON d.id = c.deal_id
          JOIN ad_campaign_placement pl ON pl.campaign_id = c.id
         WHERE {OPEN_RK} GROUP BY 1 HAVING sum(coalesce(pl.share,0)) = 0 AND max(c.plan_show) > 0"""),
]


def _cap_check(db, cap):
    """Доля выше потолка — нарушение. Исключения по правилу `flight.capped_shares`: ручной
    индекс потолку не подчиняется и держит долю по весу; невыполнимый потолок поднимается
    до равной доли остатка среди подчинённых ему площадок."""
    from app.ad.balance import is_capless, manual_scopes
    from app.ad.build import surfaces_by_deal
    manual = manual_scopes(db)
    rows_all = db.execute(text(f"""
        SELECT d.code, c.id, pl.share, pl.publisher_id, c.deal_id
          FROM ad_campaign_placement pl JOIN ad_campaign c ON c.id = pl.campaign_id
          JOIN sales_deals d ON d.id = c.deal_id WHERE {OPEN_RK} AND pl.share > 0""")).all()
    surf = surfaces_by_deal(db, {r[4] for r in rows_all})
    by_rk: dict = {}
    for code, cid, sh, pub, deal in rows_all:
        by_rk.setdefault(cid, []).append((code, sh, is_capless(manual, pub, surf.get(deal, []))))
    bad = []
    for rows in by_rk.values():
        # Выше потолка допустимо только при невыполнимом потолке, и тогда все такие
        # площадки стоят на ОДНОМ уровне заливки: разные доли выше потолка — нарушение.
        over = [r for r in rows if not r[2] and r[1] > cap + 0.002]
        if over and (max(r[1] for r in over) - min(r[1] for r in over) > 0.002
                     or sum(1 for r in rows if not r[2]) * cap >= 1 - sum(r[1] for r in rows if r[2]) + 0.002):
            bad += [(c, round(sh * 100, 1)) for c, sh, _m in over]
    return bad


def _names_check(db):
    from app.launch_prep.download_name import for_pair
    from app.weborama.naming import has_cyrillic
    ids = [r[0] for r in db.execute(text("SELECT id FROM launch_prep_pair"))]
    return [(i, n) for i in ids for n in [for_pair(db, i, "x.zip")] if has_cyrillic(n) or "/" in n]


def _external_in_dsp(db):
    """Площадка «не наш код» с креативом в нашей DSP — такого быть не должно."""
    from app.launch_prep import pub_rules
    rows = db.execute(text("""
        SELECT DISTINCT c.deal_id, pl.publisher_id, d.code, p.domain FROM ad_campaign_creative cr
          JOIN ad_campaign_placement pl ON pl.id = cr.placement_id
          JOIN ad_campaign c ON c.id = pl.campaign_id JOIN sales_deals d ON d.id = c.deal_id
          JOIN sales_publishers p ON p.id = pl.publisher_id
         WHERE coalesce(cr.ms_creative_xxhash,'') <> ''""")).all()
    modes = pub_rules.placement_modes(db, {(r[0], r[1]) for r in rows})
    return [(r[2], r[3]) for r in rows
            if modes.get((r[0], r[1]), {}).get("mode") == pub_rules.MODE_EXTERNAL]


def run(db) -> int:
    from app.ad.balance import share_cap
    cap = share_cap(db) or 1.0
    bad_total = 0
    for level, title, sql in CHECKS:
        rows = db.execute(text(sql)).all()
        mark = "OK " if not rows else level
        bad_total += len(rows) if level == "BAD" else 0
        print(f"[{mark:4}] {title}: {len(rows)}" + (f" — {rows[:6]}" if rows else ""))
    for title, rows in (("доля выше потолка (без ручного, потолок выполним)", _cap_check(db, cap)),
                        ("площадка «не наш код» с креативом в нашей DSP", _external_in_dsp(db)),
                        ("имя файла кабинета с кириллицей или «/»", _names_check(db))):
        bad_total += len(rows)
        print(f"[{'OK ' if not rows else 'BAD':4}] {title}: {len(rows)}" + (f" — {rows[:6]}" if rows else ""))
    return bad_total


def main(sync: bool) -> int:
    db = SessionLocal()
    try:
        if sync:
            from app.ad import build
            db.commit = db.flush             # ночной прогон — внутри транзакции, без записи
            print("ночной sync_all:", build.sync_all(db, commit=False))
            build.refresh_weights(db, commit=False)
        bad = run(db)
        print(f"итого нарушений: {bad}")
        return 1 if bad else 0
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    sys.exit(main("--sync" in sys.argv))
