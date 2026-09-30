# -*- coding: utf-8 -*-
"""Площадка в РК: наша DSP / внешняя / смешанная (владелец 29–30.09.2026).

Режим — по поверхностям площадки в сделке и их каналам из «Особенностей площадок», а не
по признаку «наш код»: у Максавита web через Adfox, app — через нашу DSP. Внешней DSP не
нужна (не держит запуск/стоп РК), пиксель Weborama — нужен.
"""
from types import SimpleNamespace

from sqlalchemy import text

from app.ad import external as X
from app.database import SessionLocal
from app.launch_prep import pub_rules as R


def _pl(**kw):
    base = dict(id=1, is_direct=False, weborama_pixel=None, status="ждёт запуска")
    base.update(kw)
    return SimpleNamespace(**base)


def test_external_needs_no_dsp_but_still_weborama():
    st = X._state_of(_pl(), {}, set(), [], offsite=True)
    assert st["dsp"]["state"] == X.NOT_NEEDED
    assert st["weborama"]["state"] == X.MISSING, "пиксель Weborama внешней площадке нужен"


def test_mixed_still_needs_dsp_and_says_which_part_is_external():
    st = X._state_of(_pl(), {}, set(), [], external_surfaces=["web"])
    assert st["dsp"]["state"] == X.MISSING and "web — во внешней DSP" in st["dsp"]["why"]


def test_external_does_not_lock_campaign_buttons():
    from app.routers.traffic_dashboard import dsp_block_reason
    states = {1: X._state_of(_pl(), {}, set(), [], offsite=True)}
    assert dsp_block_reason(X.totals(states), None) is None


def test_provision_refuses_only_external_surface():
    from app.dsp import provision as P
    row = {"creative": SimpleNamespace(status=next(iter(P.CREATIVE_OK)), erid="X"),
           "placement": SimpleNamespace(is_direct=False, status=next(iter(P.PLACEMENT_OK)),
                                        weborama_pixel="p"),
           "file": SimpleNamespace(is_archive=True), "publisher": SimpleNamespace(domain="a.ru"),
           "target": SimpleNamespace(advertiser_url="https://a.ru", deeplink_url=None),
           "rule": {"channel": "adfox"}}
    assert "внешней DSP" in (P._blocker(row) or "")
    row["rule"] = {"channel": "dsp"}
    assert P._blocker(row) is None, "app Максавита через нашу DSP запирать нельзя"


def test_modes_follow_surfaces_not_our_code():
    """На живых данных: площадка, у которой в сделке отправлялось только на поверхности с
    внешним каналом, — внешняя; только на DSP-поверхности — наша, даже без «нашего кода»."""
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT t.deal_id, t.publisher_id,
                   array_agg(DISTINCT t.surface_kind) AS kinds,
                   array_agg(DISTINCT coalesce(s.placement_channel, 'dsp')) AS chans
              FROM launch_prep_target t
              JOIN launch_prep_pair p ON p.target_id = t.id AND p.sent_at IS NOT NULL
              LEFT JOIN sales_publisher_surfaces s
                     ON s.publisher_id = t.publisher_id AND s.kind = t.surface_kind
             GROUP BY 1, 2 LIMIT 300""")).all()
        modes = R.placement_modes(db, {(d, p) for d, p, _, _ in rows})
        for d, p, _kinds, chans in rows:
            ext = [c for c in chans if c in R.EXTERNAL_CHANNELS]
            want = (R.MODE_EXTERNAL if ext and len(ext) == len(chans)
                    else R.MODE_MIXED if ext else R.MODE_DSP)
            assert modes[(d, p)]["mode"] == want, (d, p, chans)
    finally:
        db.close()


def test_fallback_uses_working_surfaces_only():
    """Нет сборки по площадке в сделке — считаем по поверхностям, с которыми РАБОТАЕМ:
    у Adfox-площадок app «не работаем», и он не должен делать их смешанными (30.09.2026)."""
    db = SessionLocal()
    try:
        row = db.execute(text("""
            SELECT c.deal_id, pl.publisher_id FROM ad_campaign_placement pl
              JOIN ad_campaign c ON c.id = pl.campaign_id
             WHERE NOT EXISTS (SELECT 1 FROM launch_prep_target t
                                WHERE t.deal_id = c.deal_id AND t.publisher_id = pl.publisher_id)
               AND EXISTS (SELECT 1 FROM sales_publisher_surfaces s WHERE s.publisher_id = pl.publisher_id
                             AND s.we_work AND s.placement_channel = 'adfox')
               AND NOT EXISTS (SELECT 1 FROM sales_publisher_surfaces s WHERE s.publisher_id = pl.publisher_id
                             AND s.we_work AND coalesce(s.placement_channel, 'dsp') = 'dsp')
             LIMIT 1""")).first()
        if not row:
            import pytest
            pytest.skip("нет РК с Adfox-площадкой без сборки")
        m = R.placement_modes(db, {tuple(row)})[tuple(row)]
        assert m["mode"] == R.MODE_EXTERNAL and m["external"] == ["web"]
    finally:
        db.close()
