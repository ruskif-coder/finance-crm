# -*- coding: utf-8 -*-
"""Импорт отчёта Adfox (02.10.2026): разбор, сопоставление, сверка с загруженным, запись.

Образец — настоящий отчёт 1–2.10: «День · Название кампании · Показы · Переходы ·
Уникальные показы», имена с хвостовыми пробелами и переводами строк, строка «Всего».
"""
from datetime import date, datetime
from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import text

from app.database import SessionLocal
from app.traffic import adfox_import as ai


def _xlsx(rows, head=("День", "Название кампании", "Показы", "Переходы", "Уникальные показы")):
    wb = Workbook()
    ws = wb.active
    ws.append(list(head))
    for r in rows:
        ws.append(list(r))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_real_shape():
    data = _xlsx([
        (datetime(2026, 10, 1), "PFPYGX-MXV-cr3-01_AK\r\n ", 4126, 0, 1185),
        (datetime(2026, 10, 2), "T6WY5G-MXV-cr1-01_AK ", 2284, 1, 525),
        ("Всего", None, 6410, 1, 1710),
        (None, None, None, None, None),
    ])
    rows = ai.parse(data)
    assert [r["name"] for r in rows] == ["PFPYGX-MXV-cr3-01_AK", "T6WY5G-MXV-cr1-01_AK"]
    assert rows[0]["day"] == date(2026, 10, 1) and rows[0]["uniques"] == 1185
    assert rows[1]["clicks"] == 1


def test_parse_refuses_foreign_file():
    with pytest.raises(ai.ImportError_):
        ai.parse(_xlsx([(1, 2, 3)], head=("a", "b", "c")))
    with pytest.raises(ai.ImportError_):
        ai.parse(b"not an xlsx")


def _pool(monkeypatch, creatives):
    monkeypatch.setattr(ai, "_creatives_of", lambda db, deals, allowed: [
        c for c in creatives if c["deal"] in set(deals)])


def _c(cid, deal, pub, no, pl=None):
    return {"creative_id": cid, "creative_no": no, "creative_status": "согласован",
            "placement_id": pl or cid * 10, "campaign_id": 1, "placement_status": "запущен",
            "deal": deal, "pub": pub, "pub_name": pub.lower() + ".ru", "domain": None}


def _row(name, line=2):
    return {"line": line, "day": date(2026, 10, 1), "name": name, "shows": 10, "clicks": 0,
            "uniques": 3}


def test_resolve_statuses(monkeypatch):
    _pool(monkeypatch, [_c(1, "AAAAAA", "MXV", 1), _c(2, "AAAAAA", "MXV", 2),
                        _c(3, "AAAAAA", "ZDS", 1),
                        _c(4, "BBBBBB", "MXV", 1, pl=40), _c(5, "BBBBBB", "MXV", 1, pl=50)])
    got = {r["name"]: r for r in ai.resolve(None, [
        _row("AAAAAA-MXV-cr2-01_AK", 2),     # ровно один
        _row("AAAAAA-MXV-cr3-01_AK", 3),     # номера нет — варианты той же площадки
        _row("AAAAAA-APT-cr1-01_AK", 4),     # площадки нет в РК
        _row("BBBBBB-MXV-cr1-01_AK", 5),     # web + app — два размещения
        _row("ZZZZZZ-MXV-cr1-01_AK", 6),     # сделки нет
        _row("мусор", 7),
    ])}
    assert got["AAAAAA-MXV-cr2-01_AK"]["status"] == ai.MATCHED
    assert got["AAAAAA-MXV-cr2-01_AK"]["creative_id"] == 2
    amb = got["AAAAAA-MXV-cr3-01_AK"]
    assert amb["status"] == ai.AMBIGUOUS
    # ближайший номер той же площадки — первым
    assert amb["candidates"][0]["creative_id"] == 2 and "№2 вместо №3" in amb["candidates"][0]["why"]
    assert got["AAAAAA-APT-cr1-01_AK"]["status"] == ai.AMBIGUOUS
    assert len(got["BBBBBB-MXV-cr1-01_AK"]["candidates"]) == 2
    assert got["ZZZZZZ-MXV-cr1-01_AK"]["status"] == ai.UNMATCHED
    assert got["мусор"]["status"] == ai.UNMATCHED


def test_aggregate_sums_creatives_of_one_placement():
    rows = [{"campaign_id": 1, "placement_id": 7, "day": date(2026, 10, 1), "shows": 5,
             "clicks": 1, "uniques": 2, "line": 2},
            {"campaign_id": 1, "placement_id": 7, "day": date(2026, 10, 1), "shows": 3,
             "clicks": 0, "uniques": None, "line": 3}]
    a = ai.aggregate(rows)[(1, 7, date(2026, 10, 1))]
    # уникальные двух креативов не складываются — NULL (ревью 03.10.2026)
    assert (a["shows"], a["clicks"], a["uniques"], a["lines"]) == (8, 1, None, [2, 3])


@pytest.fixture
def placement():
    db = SessionLocal()
    row = db.execute(text(
        "SELECT pl.id, pl.campaign_id FROM ad_campaign_placement pl ORDER BY pl.id LIMIT 1")).first()
    if row is None:
        db.close()
        pytest.skip("на стенде нет размещений")
    day = date(2001, 1, 1)          # заведомо вне любых данных стенда
    yield db, row[0], row[1], day
    db.execute(text("DELETE FROM ad_campaign_stat WHERE source = 'adfox' AND date = :d"), {"d": day})
    db.commit()
    db.close()


def test_write_then_rewrite_is_update_not_duplicate(placement):
    db, pl, camp, day = placement
    agg = ai.aggregate([{"campaign_id": camp, "placement_id": pl, "day": day, "shows": 100,
                         "clicks": 2, "uniques": 30}])
    assert ai.diff(db, agg)[(camp, pl, day)]["state"] == ai.NEW
    ai.write(db, agg)
    db.commit()
    assert ai.diff(db, agg)[(camp, pl, day)]["state"] == ai.SAME
    agg2 = ai.aggregate([{"campaign_id": camp, "placement_id": pl, "day": day, "shows": 150,
                          "clicks": 2, "uniques": 40}])
    d = ai.diff(db, agg2)[(camp, pl, day)]
    assert d["state"] == ai.UPDATE and d["was"]["shows"] == 100
    ai.write(db, agg2)
    db.commit()
    rows = db.execute(text("SELECT shows, uniques FROM ad_campaign_stat WHERE source='adfox' "
                           "AND placement_id=:p AND date=:d"), {"p": pl, "d": day}).all()
    assert rows == [(150, 40)]


def test_adfox_is_our_combat_fact():
    from app.ad import stat_sources as ss
    assert ai.SOURCE in ss.OWN and ai.SOURCE in ss.COMBAT and ai.SOURCE not in ss.VERIFIER


def test_routes_need_traffic_dashboard_edit():
    import inspect
    from app.routers import traffic_adfox
    src = inspect.getsource(traffic_adfox)
    assert 'require_permission("traffic_dashboard", "edit")' in src
    for fn in ("preview", "state", "search", "apply", "done"):
        assert "Depends(EDIT)" in inspect.getsource(getattr(traffic_adfox, fn)), fn
    assert "_allowed(" in inspect.getsource(traffic_adfox._bind)


# ── правки по ревью 03.10.2026 ───────────────────────────────────────────────

def test_uniques_of_two_creatives_are_not_summed():
    """Уникальные не складываются: два креатива площадки за день — сумма неизвестна."""
    rows = [{"campaign_id": 1, "placement_id": 7, "day": date(2026, 10, 1), "shows": 5,
             "clicks": 0, "uniques": 4, "line": 2},
            {"campaign_id": 1, "placement_id": 7, "day": date(2026, 10, 1), "shows": 3,
             "clicks": 0, "uniques": 2, "line": 3}]
    assert ai.aggregate(rows)[(1, 7, date(2026, 10, 1))]["uniques"] is None


def test_parse_caps_rows():
    data = _xlsx([(datetime(2026, 10, 1), f"AAAAAA-MXV-cr1-{i:02d}_AK", 1, 0, 1)
                  for i in range(ai.MAX_ROWS + 1)])
    with pytest.raises(ai.ImportError_):
        ai.parse(data)


def test_bind_refuses_placement_with_dsp_fact():
    """Отчёт Adfox на размещение, которое крутится в нашей DSP, задвоил бы день."""
    import inspect
    from app.routers import traffic_adfox
    assert "dsp_fact" in inspect.getsource(traffic_adfox._bind)


# ── отчёт 01–02.10 с прода (03.10.2026): 12 строк из 48 не сопоставились ──────

def test_excel_escaped_newline_is_cleaned():
    """Перевод строки в ячейке Adfox пишет как `_x000D_`, и openpyxl оставляет его текстом."""
    assert ai.clean_name("PFPYGX-MXV-cr3-01_AK_x000D_ ") == "PFPYGX-MXV-cr3-01_AK"
    assert ai.clean_name("AZTCWD-ZDS-cr8-01_AK_x000D__x000A_") == "AZTCWD-ZDS-cr8-01_AK"


def test_adfox_default_campaign_is_skipped_not_an_error(monkeypatch):
    monkeypatch.setattr(ai, "_creatives_of", lambda db, deals, allowed: [])
    r = ai.resolve(None, [{"line": 2, "day": date(2026, 10, 1), "name": "Кампания по умолчанию",
                           "shows": 5, "clicks": 0, "uniques": 1}])[0]
    assert r["status"] == ai.SKIPPED
