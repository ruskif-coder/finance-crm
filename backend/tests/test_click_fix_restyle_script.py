# -*- coding: utf-8 -*-
"""Скрипт перевыгрузки фикса клика (09.11.2026): сухой прогон в DSP не пишет; с --apply — бэкап исходного HTML и одна правка
`html_code`, больше ничего (статус, лимиты, ссылка клика не трогаются)."""
import importlib

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
