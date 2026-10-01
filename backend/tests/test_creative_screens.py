# -*- coding: utf-8 -*-
"""«Скрины запуска сняты» на паре «креатив × площадка» (владелец 01.10.2026): чекбокс в
дашборде трафика (вид «по креативам») и индикатор «С» у площадки после Е · W · D."""
import pytest
from fastapi import HTTPException
from sqlalchemy import text

import app.main  # noqa: F401
from app.database import SessionLocal
from app.routers import traffic_dashboard as td


def test_state_counts_live_creatives_only():
    rej = td.CREATIVE_REJECTED
    s = td.screens_state
    assert s([]) == {"state": "none", "got": 0, "total": 0}
    assert s([{"status": "запущен", "screens_done_at": None}])["state"] == "none"
    two = [{"status": "запущен", "screens_done_at": "x"}, {"status": "запущен", "screens_done_at": None}]
    assert s(two) == {"state": "part", "got": 1, "total": 2}
    # Отклонённый не в счёт: скрины по нему снимать нечего.
    assert s([{"status": "запущен", "screens_done_at": "x"},
              {"status": rej, "screens_done_at": None}]) == {"state": "all", "got": 1, "total": 1}


@pytest.fixture
def row():
    db = SessionLocal()
    r = db.execute(text("SELECT id, screens_done_at, screens_done_by FROM ad_campaign_creative "
                        "ORDER BY id LIMIT 1")).first()
    if not r:
        db.close()
        pytest.skip("нет креативов РК")
    admin = db.execute(text("SELECT u.id FROM users u JOIN roles r ON r.id = u.role_id "
                            "WHERE r.key = 'admin' ORDER BY u.id LIMIT 1")).scalar()
    from app.models import User
    yield db, r[0], db.get(User, admin)
    db.rollback()
    db.execute(text("UPDATE ad_campaign_creative SET screens_done_at = :a, screens_done_by = :b "
                    "WHERE id = :i"), {"a": r[1], "b": r[2], "i": r[0]})
    db.commit()
    db.close()


def test_mark_and_unmark(row, monkeypatch):
    db, cid, admin = row
    logged = []
    monkeypatch.setattr(td, "log_action", lambda *a, **k: logged.append(a[2]))
    out = td.set_creative_screens(cid, td.ScreensIn(done=True), db=db, user=admin)
    assert out["screens_done_at"] and out["screens_done_by"] == admin.id
    got = db.execute(text("SELECT screens_done_at, screens_done_by FROM ad_campaign_creative "
                          "WHERE id = :i"), {"i": cid}).first()
    assert got[0] is not None and got[1] == admin.id
    out = td.set_creative_screens(cid, td.ScreensIn(done=False), db=db, user=admin)
    assert out["screens_done_at"] is None and out["screens_done_by"] is None
    assert logged == ["ad_creative_screens", "ad_creative_screens"]


def test_unknown_creative_is_404(row):
    db, _, admin = row
    with pytest.raises(HTTPException) as e:
        td.set_creative_screens(10 ** 9, td.ScreensIn(done=True), db=db, user=admin)
    assert e.value.status_code == 404


def test_route_is_guarded_by_edit_and_scope():
    import inspect
    src = inspect.getsource(td.set_creative_screens)
    assert "_campaign_in_scope" in src
    route = next(r for r in td.router.routes if getattr(r, "path", "") == "/creative/{creative_id}/screens")
    deps = [d.call for d in route.dependant.dependencies]
    assert td.EDIT in deps


def test_dashboard_rows_carry_the_mark():
    """Строка креатива несёт отметку — фронту не нужен отдельный запрос."""
    db = SessionLocal()
    try:
        cid = db.execute(text("SELECT campaign_id FROM ad_campaign_creative LIMIT 1")).scalar()
        if not cid:
            pytest.skip("нет креативов РК")
        rows = [c for v in td._creatives_of(db, cid).values() for c in v]
        assert rows and "screens_done_at" in rows[0] and "screens_by" in rows[0]
    finally:
        db.close()


def test_action_label_is_human():
    from app.audit_labels import ACTION_LABELS
    assert "ad_creative_screens" in ACTION_LABELS


def test_delivery_counts_screens_on_running_placements_only():
    """Очередь аккаунта: считаются креативы запущенных площадок, кроме отклонённых."""
    from app.sales import deal_delivery as dd
    from datetime import date
    db = SessionLocal()
    try:
        r = db.execute(text("""
            SELECT c.id, c.campaign_id, a.deal_id, c.placement_id FROM ad_campaign_creative c
              JOIN ad_campaign a ON a.id = c.campaign_id
             WHERE c.status <> :rej AND c.screens_done_at IS NULL ORDER BY c.id"""),
            {"rej": td.CREATIVE_REJECTED}).all()
        camps = dd.campaigns_by_deal(db, {x[2] for x in r})
        r = next((x for x in r if camps[x[2]].id == x[1]), None)
        if not r:
            pytest.skip("нет креатива в последней РК сделки")
        camps = {r[2]: camps[r[2]]}
        # Площадку запускаем внутри транзакции — в конце откат.
        db.execute(text("UPDATE ad_campaign_placement SET status = 'запущен' WHERE id = :p"), {"p": r[3]})
        before = dd.delivery_by_deal(db, camps, date.today())[r[2]]["screens"]
        db.execute(text("UPDATE ad_campaign_creative SET screens_done_at = now() WHERE id = :i"), {"i": r[0]})
        after = dd.delivery_by_deal(db, camps, date.today())[r[2]]["screens"]
        assert after["total"] == before["total"] > 0 and after["got"] == before["got"] + 1
    finally:
        db.rollback()
        db.close()


def test_deal_card_pair_carries_screens_mark(monkeypatch):
    """Карточка сделки: строка пары несёт `screens_done_at` — из креатива РК этой пары."""
    from app.routers import launch_prep as lp
    from app.models import User
    db = SessionLocal()
    try:
        r = db.execute(text("""SELECT c.id, c.pair_id, s.deal_id FROM ad_campaign_creative c
            JOIN launch_prep_pair pr ON pr.id = c.pair_id JOIN launch_prep_creative_set s ON s.id = pr.set_id
            LIMIT 1""")).first()
        if not r:
            pytest.skip("нет креатива РК с парой")
        db.execute(text("UPDATE ad_campaign_creative SET screens_done_at = now() WHERE id = :i"), {"i": r[0]})
        admin = db.execute(text("SELECT u.id FROM users u JOIN roles ro ON ro.id = u.role_id "
                                "WHERE ro.key = 'admin' ORDER BY u.id LIMIT 1")).scalar()
        out = lp.deal_creatives(r[2], db=db, current_user=db.get(User, admin))
        rows = [x for s in out["sets"] for x in s["recipients"] if x.get("pair_id") == r[1]]
        assert rows and rows[0]["screens_done_at"] is not None
        others = [x for s in out["sets"] for x in s["recipients"]]
        assert all("screens_done_at" in x for x in others)
    finally:
        db.rollback()
        db.close()
