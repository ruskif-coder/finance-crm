# -*- coding: utf-8 -*-
"""Эталон выгрузки HTML-креатива ДО выноса сборки в `app/dsp/assemble.py` (13.10.2026).

Рефакторинг без изменения поведения: тот же запрос к DSP, тот же порядок вызовов. Значения ниже
сняты с прежнего кода и держат его: после выноса тест обязан остаться зелёным без правки.
"""
from tests.test_dsp_provision_once import FakeMs, _camp, _db, wired  # noqa: F401

from app.dsp import provision as prov


def test_html_creative_request_and_call_order_are_frozen(wired):  # noqa: F811
    ms = FakeMs()
    out = prov.provision(_db(), _camp(990901), client=ms)
    assert out["done"] and not out["failed"], out
    assert ms.calls == ["Campaign.getListByPartner", "Campaign.add", "Creative.add", "Creative.edit"]
    params = ms.added[0]
    assert params == FROZEN_PARAMS, params
    assert ms.cabinet[out["done"][0]["xxhash"]] == FROZEN_HTML


FROZEN_PARAMS = {
    "title": "баннер 1", "link": "https://landing.test", "size": "300x250", "erid": "Kra23test",
    "self_inn": "7700000000", "self_name": "ООО Тест", "adomain": "https://landing.test",
    "limits": {"show": {"total": 250}}}
FROZEN_HTML = ('<head>' + chr(10) + '<meta name="erid" content="Kra23test">' + chr(10)
               + '</head>' + chr(10) + '<div>баннер</div>')


def test_targeting_copy_core_request_is_frozen(wired):  # noqa: F811
    """Копия нацеливания: тот же конвейер, другие параметры (свой adomain, без метки и пикселя)."""
    from app.dsp import targeting_creative as tc
    ms = FakeMs()
    xx = tc._copy_core(ms, "CAMP", ref="tc1", known=None, title="копия", link="https://landing.test",
                       erid="Kra23test", get_zip=lambda: (b"PK", "b.zip"), viewability_src="")
    assert ms.calls == ["Creative.add", "Creative.edit"]
    assert ms.added[0] == {"title": "копия", "link": "https://landing.test", "size": "300x250",
                           "erid": "Kra23test", "adomain": tc.TARGETING_ADOMAIN}, ms.added[0]
    assert ms.cabinet[xx] == FROZEN_HTML
    # повтор: креатив с кодом на месте — ни add, ни edit
    ms.calls.clear()
    assert tc._copy_core(ms, "CAMP", ref="tc1", known=xx, title="копия", link="https://landing.test",
                         erid="Kra23test", get_zip=lambda: (b"PK", "b.zip"), viewability_src="") == xx
    assert "Creative.add" not in ms.calls and "Creative.edit" not in ms.calls


def test_creative_is_created_only_through_the_assembly_gate():
    """Правило владельца 13.10.2026: движения с DSP — через `app/dsp`, цепочку сборки заново не собирать.
    `creative_add(` зовут только шлюз сборки, его формат тизера, клиент и ручной демо-экран."""
    import pathlib
    app = pathlib.Path(__file__).resolve().parent.parent / "app"
    allowed = {"dsp/client.py", "dsp/assemble.py", "dsp/teaser.py", "routers/dsp_demo.py"}
    offenders = [p.relative_to(app).as_posix() for p in app.rglob("*.py")
                 if ".creative_add(" in p.read_text(encoding="utf-8")
                 and p.relative_to(app).as_posix() not in allowed]
    assert not offenders, offenders
