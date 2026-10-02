# -*- coding: utf-8 -*-
"""«Обновить данные в DSP» и Adfox вне принудительного старта (владелец 02.10.2026)."""
import inspect
from types import SimpleNamespace


import app.main  # noqa: F401
from app.routers import traffic_dashboard as td


def test_forced_start_skips_external_placements():
    from app.launch_prep import pub_rules
    assert td.mass_start_skip(pub_rules.MODE_EXTERNAL)
    assert td.mass_start_skip(pub_rules.MODE_DSP) is None
    assert td.mass_start_skip(pub_rules.MODE_MIXED) is None
    for fn in (td.set_campaign_status, td.start_plan):
        assert "mass_start_skip(" in inspect.getsource(fn), fn.__name__


def _u(key):
    return SimpleNamespace(role=SimpleNamespace(key=key, is_master=True))


def test_refresh_only_admin_and_traffic_admin():
    from app.dsp import refresh
    assert refresh.may_refresh(_u("admin"))
    assert refresh.may_refresh(_u("role_14"))
    assert not refresh.may_refresh(_u("role_12")), "Мастер траффик — нет (владелец 02.10)"
    assert not refresh.may_refresh(_u("role_13"))


def test_items_equal_ignores_order_and_names():
    from app.dsp import refresh
    a = {"1": {"is_checked": True, "bid_rate": 1, "name": "x"}}
    b = {"1": {"bid_rate": 1, "is_checked": True}}
    assert refresh.same_items(a, b)
    assert not refresh.same_items(a, {"1": {"is_checked": True, "bid_rate": 0}})
    assert not refresh.same_items(a, {"2": {"is_checked": True, "bid_rate": 1}})


def test_creative_wants_from_landing():
    from app.dsp import refresh
    row = {"target": SimpleNamespace(advertiser_url="https://xn--12080-6ve4g.xn--p1ai/p"),
           "rule": None}
    w = refresh.creative_wants(row)
    assert w["link"] == "https://120на80.рф/p" and w["adomain"] == "https://120на80.рф/p"


def test_endpoints_gated():
    src = inspect.getsource(td)
    assert "/campaign/{campaign_id}/dsp-refresh" in src
    assert src.count("_refresh_guard(") >= 3


def test_compare_tolerates_dsp_formats():
    from app.dsp import refresh as R
    a = {"x": {"is_checked": "1", "bid_rate": "1", "bid_start": "100"},
         "y": {"is_checked": False, "bid_rate": 0}}            # неотмеченный пункт справочника
    b = {"x": {"is_checked": True, "bid_rate": 1, "bid_start": 100}}
    assert R.same_items(a, b)
    got = {"settings": {"is_invert_mode": "0"}, "items": b}
    assert R._items_of(got) == (b, False), "инверсия — из settings, «0» — ложь"
    assert R._same_str("https://a.ru/?a=1&amp;b=2 ", "https://a.ru/?a=1&b=2")


def _row(**kw):
    cre = SimpleNamespace(id=7, erid=kw.get("erid", "E1"), status=kw.get("cst", "согласован"),
                          ms_creative_xxhash="H", ms_title="t", file_id=1)
    pl = SimpleNamespace(id=1, is_direct=kw.get("direct", False), status="ждёт запуска",
                         weborama_pixel="<img src='x'>")
    return {"creative": cre, "placement": pl, "publisher": SimpleNamespace(domain="a.ru", name="a"),
            "file": SimpleNamespace(is_archive=True), "rule": kw.get("rule"),
            "target": SimpleNamespace(advertiser_url="https://a.ru/p", deeplink_url=None)}


def test_rows_provision_would_refuse_are_not_touched():
    from app.dsp import refresh as R
    assert R._skip_reason(_row(direct=True), False, None)
    assert R._skip_reason(_row(rule={"channel": "adfox"}), False, None)


def test_unknown_size_keeps_pixel_untouched():
    from app.dsp import refresh as R
    edit, note = R._creative_edit(_row(), {"size": "", "link": "", "adomain": ""}, True, None)
    assert "pixel" not in edit and note and "размер" in note
    assert edit.get("link") == "https://a.ru/p"


def test_item_writes_are_locked_and_logged():
    from app.dsp import refresh as R
    assert "only_one(" in inspect.getsource(R.apply_item)
    assert "log_action(" in inspect.getsource(td.dsp_refresh_item)
