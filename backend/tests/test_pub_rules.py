# -*- coding: utf-8 -*-
"""Особенности площадок для трафика: ссылки в app, Adfox, запреты (владелец 27–29.09.2026)."""
import io
import zipfile
from types import SimpleNamespace

import pytest

from app.launch_prep import pub_rules as R
from app.launch_prep import sandbox

WEB = "https://maksavit.ru/p/1?a=1&b=2"
DEEP = "maksavit://product/1"
BANNER = ('<html><head></head><body><a href="{LINK_UNESC}"><img src="a.png"></a>'
          '<a href="https://terms.example/">правила</a></body></html>')


def _zip(html, name="index.html"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, html)
        z.writestr("a.png", b"PNG")
    return buf.getvalue()


def _entry(data, name="index.html"):
    return zipfile.ZipFile(io.BytesIO(data)).read(name).decode()


# С 05.10.2026 в href встаёт только ссылка с кликовым макросом DSP (код 2051) —
# подробно test_click_macro_rule.py. Без макроса — None: остаётся макрос DSP.
DEEP_MACRO = "maksavit://product/1?track={LINK_ESC}"


@pytest.mark.parametrize("mode,deep,href", [
    (None, DEEP, None), ("web", DEEP, None), ("both", DEEP, None), ("both", DEEP_MACRO, DEEP_MACRO)])
def test_click_href_by_mode(mode, deep, href):
    assert R.click_href({"app_links": mode}, WEB, deep) == href


def test_web_link_replaces_only_dsp_macro_and_is_escaped():
    out, changed = sandbox.set_click_href(_zip(BANNER), WEB)
    html = _entry(out)
    assert changed and "{LINK_UNESC}" not in html
    assert 'href="https://maksavit.ru/p/1?a=1&amp;b=2"' in html
    assert 'href="https://terms.example/"' in html, "чужую ссылку трогать нельзя"
    assert zipfile.ZipFile(io.BytesIO(out)).read("a.png") == b"PNG"


def test_adfox_macro_goes_right_after_body_once():
    out, changed = sandbox.insert_adfox_macro(_zip(BANNER))
    html = _entry(out)
    assert changed and html.count("%user6%") == 1
    assert html.index("<body>") + len("<body>") == html.index("%user6%")
    again, changed2 = sandbox.insert_adfox_macro(out)
    assert not changed2 and _entry(again).count("%user6%") == 1


def test_problems():
    assert R.pair_problem({"app_links": "both"}, WEB, None)
    assert R.pair_problem({"app_links": "both"}, WEB, DEEP) is None
    assert R.pair_problem({"channel": "adfox", "adfox_code": None}, WEB, None)
    assert R.pair_problem({"channel": "adfox", "adfox_code": "<iframe>"}, WEB, None) is None
    assert R.pair_problem({"channel": "dsp"}, WEB, None) is None


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "data:text/html,x", "noscheme", "x" * 1100])
def test_deeplink_rejects_dangerous(bad):
    with pytest.raises(ValueError):
        R.validate_deeplink(bad)


def test_deeplink_accepts_app_scheme():
    assert R.validate_deeplink("  maksavit://p/1?t={LINK_ESC} ") == "maksavit://p/1?t={LINK_ESC}"
    assert R.validate_deeplink("") is None


def test_provision_blocks_both_without_deeplink():
    from app.dsp import provision as P
    row = {"creative": SimpleNamespace(status="согласован", erid="X", id=1),
           "placement": SimpleNamespace(is_direct=False, status=next(iter(P.PLACEMENT_OK)), weborama_pixel="p"),
           "file": SimpleNamespace(is_archive=True),
           "publisher": SimpleNamespace(domain="maksavit.ru"),
           "target": SimpleNamespace(advertiser_url=WEB, deeplink_url=None),
           "rule": {"app_links": "both"}}
    row["creative"].status = next(iter(P.CREATIVE_OK))
    assert "диплинк" in (P._blocker(row) or "")
    row["target"].deeplink_url = DEEP
    assert P._blocker(row) is None


def test_rule_only_for_matching_surface():
    s = SimpleNamespace(kind="web", placement_channel="adfox", app_links="web", adfox_extra_code="c")
    r = R.rule_of(s)
    assert r["app_links"] is None, "режим ссылок действует только на app"
    assert r["adfox_code"] == "c"


def test_adfox_archive_endpoint_on_stand_pair(monkeypatch):
    """Ручка отдаёт архив с %user6% после <body>; не-Adfox площадке — 409."""
    from fastapi import HTTPException
    from sqlalchemy import text
    from app.database import SessionLocal
    from app.models import User
    from app.routers import traffic as T
    db = SessionLocal()
    try:
        pid = db.execute(text("""SELECT pr.id FROM launch_prep_pair pr
            JOIN launch_prep_creative_file f ON f.set_id = pr.set_id AND f.is_archive
            ORDER BY pr.id DESC LIMIT 1""")).scalar()
        admin = db.execute(text("""SELECT u.id FROM users u JOIN roles r ON r.id = u.role_id
            WHERE r.key = 'admin' AND u.is_active = 1 LIMIT 1""")).scalar()
        if not (pid and admin):
            pytest.skip("на стенде нет пары с архивом")
        user = db.query(User).get(admin)
        monkeypatch.setattr(R, "rules_for", lambda db_, keys: {k: {"channel": "dsp"} for k in keys})
        with pytest.raises(HTTPException) as e:
            T.adfox_archive(pid, db=db, current_user=user)
        assert e.value.status_code == 409
        monkeypatch.setattr(R, "rules_for", lambda db_, keys: {k: {"channel": "adfox"} for k in keys})
        resp = T.adfox_archive(pid, db=db, current_user=user)
        body = resp.body
        z = zipfile.ZipFile(io.BytesIO(body))
        inner = [n for n in z.namelist() if n.lower().endswith(".zip")]
        if inner:                      # несколько архивов в комплекте — zip из zip
            z = zipfile.ZipFile(io.BytesIO(z.read(inner[0])))
        html = z.read(sandbox._pick_entry(z.namelist())).decode("utf-8", "ignore")
        assert "%user6%" in html
    finally:
        db.close()


def test_cp1251_banner_keeps_cyrillic():
    html = '<html><body><a href="{LINK_UNESC}">Купить</a></body></html>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("index.html", html.encode("cp1251"))
    out, changed = sandbox.set_click_href(buf.getvalue(), WEB)
    raw = zipfile.ZipFile(io.BytesIO(out)).read("index.html")
    assert changed and "Купить" in raw.decode("cp1251"), "кириллица cp1251 потеряна"
    out2, _ = sandbox.insert_adfox_macro(buf.getvalue())
    assert "Купить" in zipfile.ZipFile(io.BytesIO(out2)).read("index.html").decode("cp1251")
