# -*- coding: utf-8 -*-
"""Проверка баннера на отправке на согласование (владелец 16.11.2026): пара «креатив × площадка» — наш архив с имитацией
разметки DSP. В очередь — только пары нашей DSP с HTML5-архивом; Adfox, «вне контура» и тизеры проверять нечем.

Пары берутся со стенда (копия прода); строки проверки тест пишет по-настоящему и убирает за собой."""
import pytest
from sqlalchemy import text

from app.dsp import banner_check as bc
from app.dsp import banner_check_pairs as bp

GOOD = {"plaque": True, "n_btns": 1, "styled": 1, "plaque_on_top": True, "erid_shown": True,
        "plaque_click_navigates": False, "center_ok": True}


def _pair(db, channel, archive=True, fmt="HTML"):
    return db.execute(text(f"""
        SELECT p.id FROM launch_prep_pair p
          JOIN launch_prep_target t ON t.id = p.target_id
          JOIN sales_publisher_surfaces s ON s.publisher_id = t.publisher_id AND s.kind = t.surface_kind
         WHERE s.placement_channel = :ch AND coalesce(s.creative_format, 'HTML') = :f AND p.withdrawn_at IS NULL
           AND {'' if archive else 'NOT '}EXISTS (SELECT 1 FROM launch_prep_creative_file f
                        WHERE f.set_id = p.set_id AND f.is_archive AND f.sandbox_token IS NOT NULL)
         ORDER BY p.id DESC LIMIT 1"""), {"ch": channel, "f": fmt}).scalar()


@pytest.fixture
def pairs(db):
    ids = {"dsp": _pair(db, "dsp"), "adfox": _pair(db, "adfox"), "teaser": _pair(db, "dsp", archive=False, fmt="TEASER")}
    if not ids["dsp"]:
        pytest.skip("на стенде нет пары нашей DSP с архивом в песочнице")
    real = [i for i in ids.values() if i]
    keep = db.execute(text("SELECT pair_id FROM dsp_banner_check WHERE pair_id = ANY(:i)"), {"i": real}).scalars().all()
    assert not keep, "у тестовых пар уже есть строки проверки — тест их затёр бы"
    yield ids
    db.rollback()
    db.execute(text("DELETE FROM dsp_banner_check WHERE pair_id = ANY(:i)"), {"i": real})
    db.commit()


def test_only_our_dsp_html_pairs_are_queued(db, pairs):
    queued = bp.enqueue_pairs(db, [i for i in pairs.values() if i])
    assert queued == [pairs["dsp"]]
    rows = db.execute(text("SELECT pair_id, checked_at FROM dsp_banner_check WHERE pair_id = ANY(:i)"),
                      {"i": [i for i in pairs.values() if i]}).all()
    assert [(r[0], r[1]) for r in rows] == [(pairs["dsp"], None)]


def test_pair_markup_is_emulated_and_its_files_go_to_the_browser(db, pairs, monkeypatch):
    seen = {}

    def fake_render(html, erid, opts, files=None, base=None):
        seen.update(html=html, erid=erid, files=files, base=base)
        return {"300x600": GOOD}
    monkeypatch.setattr(bc, "render", fake_render)
    monkeypatch.setattr(bp, "_notify_pair", lambda *a: None)
    bp.enqueue_pairs(db, [pairs["dsp"]])
    rep = bc.run(db, client=object(), limit=50, only_pairs=[pairs["dsp"]])
    assert rep["checked"] == 1
    assert '<meta name="ad.erid" content="' in seen["html"] and '{LINK_UNESC}' in seen["html"]
    assert f'<base href="{bp.BASE}">' in seen["html"] and seen["base"] == bp.BASE
    assert any(k.endswith(".html") for k in seen["files"]) and seen["erid"]
    st = bp.state_of_pairs(db, [pairs["dsp"]])[pairs["dsp"]]
    assert st["state"] == "ok" and st["problems"] is None


def test_failed_pair_notifies_traffic_with_problems(db, pairs, monkeypatch):
    sent = []
    monkeypatch.setattr(bc, "render", lambda html, erid, opts, files=None, base=None:
                        {"300x600": {**GOOD, "plaque_on_top": False, "cover": "DIV.bg"}})
    monkeypatch.setattr(bp, "_notify_pair", lambda db, row, problems: sent.append((row["pair_id"], problems)))
    bp.enqueue_pairs(db, [pairs["dsp"]])
    bc.run(db, client=object(), limit=50, only_pairs=[pairs["dsp"]])
    assert sent == [(pairs["dsp"], {"300x600": ["плашка «Реклама» перекрыта (DIV.bg)"]})]
    assert bp.state_of_pairs(db, [pairs["dsp"]])[pairs["dsp"]]["state"] == "bad"


def test_too_big_banner_is_a_problem_not_a_retry_forever(db, pairs, monkeypatch):
    monkeypatch.setattr(bp, "FILES_CAP", 10)
    monkeypatch.setattr(bp, "_notify_pair", lambda *a: None)
    bp.enqueue_pairs(db, [pairs["dsp"]])
    bc.run(db, client=object(), limit=50, only_pairs=[pairs["dsp"]])
    st = bp.state_of_pairs(db, [pairs["dsp"]])[pairs["dsp"]]
    assert st["state"] == "bad" and "проверка в браузере пропущена" in st["problems"]["разметка"][0]


def test_unexpected_error_on_one_banner_is_recorded_and_does_not_stop_the_run(db, pairs, monkeypatch):
    """16.11.2026: непредвиденная ошибка разбора одного баннера роняла весь прогон — очередь вставала целиком."""
    def boom(db, row):
        raise AttributeError("'NoneType' object has no attribute 'start'")
    monkeypatch.setattr(bp, "_markup", boom)
    monkeypatch.setattr(bp, "_notify_pair", lambda *a: None)
    bp.enqueue_pairs(db, [pairs["dsp"]])
    rep = bc.run(db, client=object(), limit=50, only_pairs=[pairs["dsp"]])
    st = bp.state_of_pairs(db, [pairs["dsp"]])[pairs["dsp"]]
    assert rep["checked"] == 1 and st["state"] == "bad"
    assert st["problems"]["разметка"][0].startswith("проверка не удалась")
