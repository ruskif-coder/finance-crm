# -*- coding: utf-8 -*-
"""Раскладка дельты сверки по РК (владелец 14.11.2026).

Площадка прислала свою цифру — менеджер, принимая её, выбирает, как разнести разницу с нашим фактом по РК сверки:
пропорционально нашему факту («равномерно») или целиком на одну РК. От раскладки зависят разаллокация площадке и ОРД
по ЕРИД. Согласие площадки на НАШЕ контрпредложение итог больше не фиксирует — ждёт менеджера с тем же выбором;
согласие с нашими же данными (дельты нет) по-прежнему итог."""
from datetime import date

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.publisher_recon import board as B
from app.publisher_recon import service as S

FACTS = {11: 4_615_412, 12: 498_026, 13: 0}     # форма прода: одна большая РК, одна без показов


# ── чистое правило ──────────────────────────────────────────────────────────────────────────────────

def test_even_spreads_the_delta_by_our_fact():
    out = S.distribute(2_557_719, FACTS, "even")
    assert sum(out.values()) == 2_557_719
    # руками: 2557719 × 4615412/5113438 = 2308608,60; × 498026/5113438 = 249110,40; остаток 1 — большей дробной части
    assert out == {11: 2_308_609, 12: 249_110, 13: 0}


def test_target_puts_the_whole_delta_on_one_campaign():
    assert S.distribute(4_000_000, FACTS, "target", 11) == {11: 3_501_974, 12: 498_026, 13: 0}
    assert S.distribute(5_113_538, FACTS, "target", 13) == {11: 4_615_412, 12: 498_026, 13: 100}


def test_target_cannot_go_below_zero_or_point_outside_the_recon():
    with pytest.raises(S.ReconError) as e:
        S.distribute(4_000_000, FACTS, "target", 12)         # 498 026 − 1 113 438 < 0
    assert e.value.status == 400
    with pytest.raises(S.ReconError) as e:
        S.distribute(4_000_000, FACTS, "target", 99)
    assert e.value.status == 400
    with pytest.raises(S.ReconError) as e:
        S.distribute(4_000_000, FACTS, "target")
    assert e.value.status == 400
    with pytest.raises(S.ReconError):
        S.distribute(4_000_000, FACTS, "куда-то")


# ── в базе (откатывается) ───────────────────────────────────────────────────────────────────────────

class _U:
    def __init__(self, name="Менеджер тест", email="m@test"):
        self.name, self.email, self.id = name, email, None


@pytest.fixture
def ready():
    db = SessionLocal()
    rows = [r for r in B.month_rows(db, "2026-10") if r["status"] == B.READY and r["ours"] > 0]
    if not rows:
        db.close()
        pytest.skip("на стенде нет площадки, готовой к сверке за октябрь")
    yield db, rows[0]
    db.rollback()
    db.close()


def _lines(db, rid):
    return dict(db.execute(text("SELECT target_id, agreed_volume FROM publisher_recon_line WHERE request_id = :r"),
                           {"r": rid}).all())


def test_agree_on_one_campaign_writes_the_delta_there_only(ready):
    """Сломать: игнорировать `mode` в `agree` — дельта размажется по всем РК."""
    db, row = ready
    req = S.send(db, row["publisher_id"], "2026-10", _U(), date(2026, 10, 26))
    facts = B.target_facts(db, req.publisher_id, req.period)
    tid = max(facts, key=facts.get)
    S.publisher_answer(db, req, "Площадка", None, agree=False, volume=row["ours"] - 7, body="у нас меньше")
    S.agree(db, req, _U(), row["ours"] - 7, mode="target", target_id=tid)
    got = _lines(db, req.id)
    assert got[tid] == facts[tid] - 7
    assert all(got[k] == facts[k] for k in facts if k != tid)


def test_preview_shows_the_same_split_that_agree_writes(ready):
    db, row = ready
    req = S.send(db, row["publisher_id"], "2026-10", _U(), date(2026, 10, 26))
    shown = S.preview(db, req, row["ours"] + 1000, "even")
    assert sum(x["agreed"] for x in shown["lines"]) == row["ours"] + 1000
    assert shown["delta"] == 1000
    S.agree(db, req, _U(), row["ours"] + 1000, mode="even")
    assert _lines(db, req.id) == {x["placement_id"]: x["agreed"] for x in shown["lines"]}


def test_publisher_agreeing_to_our_counter_offer_waits_for_the_manager(ready):
    """Владелец 14.11.2026: согласие на контрпредложение — с дельтой, а раскладку выбирает менеджер. Сломать: вернуть
    безусловный `agree_total` в `publisher_answer` — verdict станет «согласовано» без менеджера."""
    db, row = ready
    req = S.send(db, row["publisher_id"], "2026-10", _U(), date(2026, 10, 26))
    S.publisher_answer(db, req, "Площадка", None, agree=False, volume=row["ours"] - 5000, body="у нас меньше")
    S.reply(db, req, _U(), "предлагаем", row["ours"] - 2000, today=date(2026, 10, 27))
    S.publisher_answer(db, req, "Площадка", None, agree=True)
    assert req.verdict is None and req.recon.their_volume == row["ours"] - 2000
    st = next(r for r in B.month_rows(db, "2026-10") if r["publisher_id"] == req.publisher_id)
    assert st["status"] == B.ANSWER
