# -*- coding: utf-8 -*-
"""Лента журнала (макет design_handoff_journal, 16.11.2026) на данных стенда: контуры, фильтры, счётчики, выгрузка.

Только чтение, кроме записи «журнал выгружен» — её тест убирает."""
import inspect
import io
import types
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.audit import require_admin
from app.journal import export, feed
from app.routers import journal as jr


def _f(**kw):
    return feed.Query(**{"limit": 100, **kw})


def test_staff_contour_is_audit_log_only_newest_first(db):
    out = feed.fetch(db, _f())
    assert out["total"] > 0 and out["items"]
    assert {i["actor"]["kind"] for i in out["items"]} == {"staff"}
    ats = [i["at"] for i in out["items"]]
    assert ats == sorted(ats, reverse=True)
    assert out["facets"]["contours"]["all"] == out["facets"]["contours"]["staff"] + out["facets"]["contours"]["cabinet"]


def test_cabinet_contour_shows_only_publisher_side_actions(db):
    out = feed.fetch(db, _f(contour="cabinet", limit=300))
    if not out["total"]:
        pytest.skip("на стенде нет действий площадок")
    assert {i["actor"]["kind"] for i in out["items"]} == {"cabinet"}
    ours = db.execute(text("SELECT DISTINCT action FROM cabinet_log WHERE actor_side <> 'площадка'")).scalars().all()
    assert not ({i["action"] for i in out["items"]} & set(ours) - {"вход"}), "наши уведомления площадкам — не их активность"


def test_section_pins_add_up_and_section_filter_keeps_only_its_actions(db):
    out = feed.fetch(db, _f())
    secs = out["facets"]["sections"]
    assert sum(secs.values()) == out["total"]
    sid = max(secs, key=secs.get)
    only = feed.fetch(db, _f(section=sid))
    assert only["total"] == secs[sid] and {i["section"] for i in only["items"]} == {sid}
    acts = only["facets"]["actions"]
    assert acts and sum(a["n"] for a in acts.values()) == secs[sid]
    key = max(acts, key=lambda k: acts[k]["n"])
    one = feed.fetch(db, _f(section=sid, action=key))
    assert one["total"] == acts[key]["n"] and {i["action"] for i in one["items"]} == {key}


def test_search_finds_a_deal_by_its_code(db):
    code = db.execute(text("SELECT d.code FROM audit_log a JOIN sales_deals d ON d.id = a.entity_id "
                           "WHERE a.entity_type = 'sales_deal' AND d.code IS NOT NULL ORDER BY a.id DESC LIMIT 1")).scalar()
    if not code:
        pytest.skip("нет записей о сделках")
    out = feed.fetch(db, _f(q=code))
    assert out["total"] > 0
    assert any((i["object"] or {}).get("code") == code or code in (i["details"] or "") for i in out["items"])


def test_period_and_actor_filters(db):
    last = db.execute(text("SELECT user_id, created_at FROM audit_log WHERE user_id IS NOT NULL ORDER BY id DESC LIMIT 1")).first()
    day = (last.created_at + timedelta(hours=3)).date()
    out = feed.fetch(db, _f(date_from=day, date_to=day, actor=f"staff:{last.user_id}"))
    assert out["total"] > 0 and {i["actor"]["id"] for i in out["items"]} == {f"staff:{last.user_id}"}
    assert all((i["at"] + timedelta(hours=3)).date() == day for i in out["items"])
    assert any(a["id"] == f"staff:{last.user_id}" for a in out["facets"]["actors"])
    assert feed.fetch(db, _f(date_from=date(2000, 1, 1), date_to=date(2000, 1, 2)))["total"] == 0


def test_bad_contour_and_reversed_period_are_refused():
    with pytest.raises(Exception) as e:
        jr._query("кто-то", None, None, None, None, None, None)
    assert "Контур" in str(e.value.detail)
    with pytest.raises(Exception) as e:
        jr._query("staff", date(2026, 2, 1), date(2026, 1, 1), None, None, None, None)
    assert "позже" in str(e.value.detail)


def test_export_is_admin_only_writes_every_row_and_journals_itself(db, monkeypatch):
    dep = inspect.signature(jr.journal_export).parameters["current_user"].default
    assert dep.dependency is require_admin
    day = db.execute(text("SELECT max(created_at) FROM audit_log")).scalar() + timedelta(hours=3)
    calls = []
    monkeypatch.setattr(jr, "log_action", lambda db_, user, action, **k: calls.append((action, k.get("details"))))
    resp = jr.journal_export(contour="staff", date_from=day.date(), date_to=day.date(), actor=None, q=None, section=None,
                             action=None, db=db, current_user=types.SimpleNamespace(id=0, name="админ"))
    from openpyxl import load_workbook
    ws = load_workbook(io.BytesIO(resp.body)).active
    n = feed.fetch(db, _f(date_from=day.date(), date_to=day.date()))["total"]
    assert ws.max_row - 1 == n and [c.value for c in ws[1]] == export.HEAD
    assert calls == [("journal_export", calls[0][1])] and f"строк: {n}" in calls[0][1]


def test_export_over_the_cap_is_refused_in_words(db, monkeypatch):
    monkeypatch.setattr(export, "CAP", 1)
    with pytest.raises(export.TooMany) as e:
        export.build(db, _f())
    assert "Сузьте период" in str(e.value)
