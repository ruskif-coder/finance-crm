# -*- coding: utf-8 -*-
"""«Ещё не дошли» на экране бухгалтера (владелец 09.11.2026: «все что после итоговой сверки»): сделки закрываемого месяца со
стадии «Итоговая сверка» и дальше, чьи документы до бухгалтера ещё не дошли — сверка не отправлена, пакет в черновике или
на согласовании. Объём оставшейся работы по закрытию периода.

Поломки, которые ловит набор:
- считаются сделки до «Итоговой сверки» (ещё крутятся) — объём завышен;
- пакет уже «ждём 1С» (заявка у бухгалтера) — а сделка всё ещё в «не дошли», двойной счёт;
- сделка другого месяца попадает в счётчик закрываемого.
Живые данные стенда, транзакция откатывается."""
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401


@pytest.fixture
def db():
    from app.database import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _stage(db, name):
    return db.execute(text("SELECT id FROM sales_stages WHERE name = :n"), {"n": name}).scalar()


def _ids(out, bucket=None):
    return {x["deal_id"] for x in out["deals"] if bucket is None or x["bucket"] == bucket}


def test_deal_on_final_recon_counts_and_one_still_running_does_not(db):
    from app.onec_desk import upstream as UP
    d = db.execute(text("""SELECT d.id FROM sales_deals d LEFT JOIN master_deal_items i ON i.deal_id = d.id
                           WHERE i.id IS NULL AND d.period_from IS NOT NULL AND NOT d.is_self_promo ORDER BY d.id LIMIT 1""")).scalar()
    if d is None:
        pytest.skip("нет сделки вне пакетов")
    db.execute(text("UPDATE sales_deals SET our_stage_id = :s, period_from = DATE '2031-03-05' WHERE id = :d"),
               {"s": _stage(db, "Итоговая сверка"), "d": d})
    out = UP.upstream(db, "2031-03")
    assert d in _ids(out, "recon") and out["counts"]["recon"] >= 1
    assert d not in _ids(UP.upstream(db, "2031-04")), "чужой месяц"
    db.execute(text("UPDATE sales_deals SET our_stage_id = :s WHERE id = :d"), {"s": _stage(db, "В размещении"), "d": d})
    assert d not in _ids(UP.upstream(db, "2031-03")), "до итоговой сверки — не считаем"


def test_package_in_agreement_counts_until_it_reaches_the_accountant(db):
    from app.onec_desk import upstream as UP
    row = db.execute(text("""SELECT m.id, i.deal_id FROM master_deals m JOIN master_deal_items i ON i.master_deal_id = m.id
                             JOIN sales_deals d ON d.id = i.deal_id WHERE NOT d.is_self_promo ORDER BY m.id LIMIT 1""")).first()
    if row is None:
        pytest.skip("нет пакетов")
    db.execute(text("UPDATE sales_deals SET our_stage_id = :s, period_from = DATE '2031-03-05' WHERE id = :d"),
               {"s": _stage(db, "Подготовка ДС"), "d": row.deal_id})
    db.execute(text("UPDATE master_deals SET status = 'согласование' WHERE id = :m"), {"m": row.id})
    assert row.deal_id in _ids(UP.upstream(db, "2031-03"), "agree")
    db.execute(text("UPDATE master_deals SET status = 'черновик' WHERE id = :m"), {"m": row.id})
    assert row.deal_id in _ids(UP.upstream(db, "2031-03"), "draft")
    db.execute(text("UPDATE master_deals SET status = 'ждём 1С' WHERE id = :m"), {"m": row.id})
    assert row.deal_id not in _ids(UP.upstream(db, "2031-03")), "заявка уже у бухгалтера"


def test_board_carries_upstream_of_the_closing_month(db):
    from app.onec_desk import board as BD
    out = BD.board(db)
    up = out["upstream"]
    assert up["month"] == out["settings"]["month"] and up["total"] == len(up["deals"]) == sum(up["counts"].values())


def test_self_promo_counts_too(db):
    """Самореклама — площадок, не наша: клиенту за неё выставляем, документы идут тем же путём (владелец 09.11.2026)."""
    from app.onec_desk import upstream as UP
    d = db.execute(text("""SELECT d.id FROM sales_deals d LEFT JOIN master_deal_items i ON i.deal_id = d.id
                           WHERE i.id IS NULL ORDER BY d.id LIMIT 1""")).scalar()
    if d is None:
        pytest.skip("нет сделки вне пакетов")
    db.execute(text("UPDATE sales_deals SET our_stage_id = :s, period_from = DATE '2031-03-05', is_self_promo = true WHERE id = :d"),
               {"s": _stage(db, "Итоговая сверка"), "d": d})
    assert d in _ids(UP.upstream(db, "2031-03"), "recon")
