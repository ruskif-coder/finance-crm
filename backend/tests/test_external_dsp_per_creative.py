"""Буква D в строке креатива — про ЭТОТ креатив (владелец 24.10.2026).

Площадка крутит креатив №3 — копия №10 той же площадки ещё черновик, и «крутится» у неё
было неправдой: состояние DSP считалось по площадке РК целиком. Weborama остаётся общей —
вставка и пиксель живут у площадки.
"""
from types import SimpleNamespace

from app.ad import external as ex


def _pl(**kw):
    return SimpleNamespace(id=1, is_direct=False, weborama_pixel="px", status="запущен", **kw)


def _cr(set_id, hash_=None):
    return SimpleNamespace(id=set_id * 10, root_set_id=set_id, ms_creative_xxhash=hash_, status="запущен")


def _row(p, crs):
    from app.ad.external import _state_of
    base = _state_of(p, {}, set(), crs)
    return ex.with_dsp_by_set(base, p, crs)


def test_draft_creative_is_not_running_because_another_one_is():
    p = _pl()
    row = _row(p, [_cr(3, "abc")])
    assert row["dsp"]["state"] == ex.RUNNING                     # площадка целиком — крутится
    assert ex.for_set(row, 3)["dsp"]["state"] == ex.RUNNING
    draft = ex.for_set(row, 10)
    assert draft["dsp"]["state"] == ex.MISSING, "черновик не может быть «ок» в DSP"
    assert draft["weborama"]["state"] == ex.READY                 # пиксель — у площадки


def test_registered_but_not_running_is_per_creative():
    p = _pl()
    row = _row(p, [_cr(3, "abc"), _cr(10)])
    assert ex.for_set(row, 10)["dsp"]["state"] == ex.MISSING
    assert "dsp_by_set" not in ex.for_set(row, 10)


def test_not_needed_stays_for_every_creative():
    p = _pl()
    p.is_direct = True
    row = _row(p, [])
    assert ex.for_set(row, 10)["dsp"]["state"] == ex.NOT_NEEDED


def test_placement_turns_partial_when_a_new_creative_is_not_uploaded():
    """Новый согласованный креатив при уже выгруженных: площадка в дашборде трафика — жёлтая,
    «готово к выгрузке» загорается (владелец 24.10.2026)."""
    p = _pl()
    new = _cr(10)
    new.status = "согласован"
    row = _row(p, [_cr(3, "abc"), new])
    assert row["dsp"]["state"] == ex.PARTIAL
    assert ex.for_set(row, 3)["dsp"]["state"] == ex.RUNNING
    assert ex.for_set(row, 10)["dsp"]["state"] == ex.MISSING
    assert ex.totals({1: row})["dsp"] == {"done": 0, "need": 1}


def test_rejected_creative_does_not_make_placement_partial():
    p = _pl()
    gone = _cr(10)
    gone.status = "отклонён"
    assert _row(p, [_cr(3, "abc"), gone])["dsp"]["state"] == ex.RUNNING
