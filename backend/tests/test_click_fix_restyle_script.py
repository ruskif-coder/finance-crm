# -*- coding: utf-8 -*-
"""Скрипт перевыгрузки фикса клика (09.11.2026): сухой прогон в DSP не пишет; с --apply — бэкап исходного HTML и одна правка
`html_code`, больше ничего (статус, лимиты, ссылка клика не трогаются)."""
import importlib

import pytest

from app.dsp import creatives as cr

S = importlib.import_module("scripts.2026-11-09_click_fix_restyle")
OLD = ('<html><head><style data-simb-click-fix>body>a{display:block;position:absolute;inset:0;z-index:2147483000;'
       'cursor:pointer}</style></head><body><a href="{LINK_UNESC}"><div></div></a></body></html>')


class FakeDsp:
    def __init__(self, html):
        self.html, self.edits = html, []

    def creative_get_info(self, xxhash):
        return {"status": "active", "data": {"html_code": self.html}}

    def creative_edit(self, xxhash, params, local_ref=None):
        self.edits.append((xxhash, params))
        self.html = params["data"]["html_code"]


def _one(monkeypatch):
    monkeypatch.setattr(S, "candidates", lambda db, st, only=None: [
        {"id": 1, "xxhash": "H1", "title": "T-P-cr1", "status": "запущен"}])


def test_dry_run_writes_nothing(monkeypatch):
    _one(monkeypatch)
    dsp = FakeDsp(OLD)
    rep = S.run(apply=False, client=dsp, db=object())
    assert len(rep["planned"]) == 1 and dsp.edits == []
    assert "z-index" in rep["planned"][0]["old"] and "z-index" not in rep["planned"][0]["new"]


def test_apply_backs_up_and_edits_only_html(monkeypatch, tmp_path):
    _one(monkeypatch)
    monkeypatch.setattr(S, "BACKUP_DIR", str(tmp_path))
    dsp = FakeDsp(OLD)
    rep = S.run(apply=True, client=dsp, db=object())
    assert [list(p) for _, p in dsp.edits] == [["data"]]
    assert cr.CLICK_FIX_STYLE in dsp.html
    assert open(rep["applied"][0]["backup"], encoding="utf-8").read() == OLD
    assert S.run(apply=True, client=dsp, db=object())["ok"] == 1            # повтор — без правок


# ── нацеливание (владелец 10.11.2026: «надо накатить и на все нацеливания») ──────────────────────────────────────

def test_targeting_mode_takes_targeting_copies_and_demo_client(monkeypatch, tmp_path):
    """Копии нацеливания живут у демоклиента (другой partner_xxhash) и в РК не входят — режим `targeting` берёт их из
    комплектов (`ms_targeting_creative_xxhash`) и правит клиентом демоклиента. Ломается, если режим возьмёт креативы РК или
    пойдёт в DSP не от демоклиента."""
    monkeypatch.setattr(S, "BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(S, "targeting_candidates", lambda db, only=None: [
        {"id": 7, "xxhash": "TGT0000000000001", "title": "tgt7", "status": None}])
    monkeypatch.setattr(S, "candidates", lambda *a, **k: pytest.fail("в режиме нацеливания креативы РК не берём"))
    opened = []
    dsp = FakeDsp(OLD)
    monkeypatch.setattr(S, "targeting_client", lambda db: opened.append("demo") or dsp)
    rep = S.run(apply=True, db=object(), mode="targeting")
    assert opened == ["demo"] and [x["xxhash"] for x in rep["applied"]] == ["TGT0000000000001"]
    assert "z-index" not in dsp.edits[0][1]["data"]["html_code"]


def test_targeting_candidates_are_sets_with_a_copy(monkeypatch):
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        got = S.targeting_candidates(db)
        want = db.execute(__import__("sqlalchemy").text(
            "SELECT count(*) FROM launch_prep_creative_set WHERE ms_targeting_creative_xxhash IS NOT NULL")).scalar()
        assert len(got) == want and all(x["xxhash"] for x in got)
    finally:
        db.close()


def test_targeting_client_opens_demo_partner_from_config():
    """Настоящий путь без подмен: кабинет нацеливания — из `dsp.config.targeting_cabinet` (ломалось на импорте 10.11.2026)."""
    from app.database import SessionLocal
    from app.dsp.config import targeting_cabinet
    db = SessionLocal()
    try:
        partner, _ = targeting_cabinet(db)
        if not partner:
            pytest.skip("на стенде не задан кабинет нацеливания")
        assert S.targeting_client(db).partner_xxhash == partner
    finally:
        db.close()
