# -*- coding: utf-8 -*-
"""Скрипт `2026-11-15_viewability_dedupe`: сухой прогон ничего не пишет, `--apply` пишет только креативы с дублем."""
import importlib

from tests.test_viewability_once import DOUBLE, DSP_HTML

S = importlib.import_module("scripts.2026-11-15_viewability_dedupe")


class FakeClient:
    def __init__(self, htmls):
        self.htmls, self.edits = dict(htmls), []

    def creative_get_info(self, xx):
        return {"status": "ACTIVE", "data": {"html_code": self.htmls[xx]}}

    def creative_edit(self, xx, body, local_ref=None):
        self.edits.append(xx)
        self.htmls[xx] = body["data"]["html_code"]


class FakeDb:
    def rollback(self):
        pass

    def close(self):
        pass


def _rows(monkeypatch):
    rows = [{"id": 1, "xxhash": "AA", "title": "двойной", "status": "согласован"},
            {"id": 2, "xxhash": "BB", "title": "одинарный", "status": "согласован"}]
    monkeypatch.setattr(S._base, "candidates", lambda db, statuses, only=None: rows)


def test_dry_run_writes_nothing(monkeypatch, tmp_path):
    _rows(monkeypatch)
    monkeypatch.setattr(S, "BACKUP_DIR", str(tmp_path))
    c = FakeClient({"AA": DOUBLE, "BB": DSP_HTML})
    rep = S.run(client=c, db=FakeDb())
    assert [p["xxhash"] for p in rep["planned"]] == ["AA"] and rep["ok"] == 1
    assert c.edits == [] and not list(tmp_path.iterdir())


def test_apply_fixes_only_the_double_and_keeps_a_backup(monkeypatch, tmp_path):
    _rows(monkeypatch)
    monkeypatch.setattr(S, "BACKUP_DIR", str(tmp_path))
    c = FakeClient({"AA": DOUBLE, "BB": DSP_HTML})
    rep = S.run(apply=True, client=c, db=FakeDb())
    assert c.edits == ["AA"] and c.htmls["AA"].count("viewability.js") == 1
    assert (tmp_path / rep["applied"][0]["backup"].split("/")[-1]).read_text(encoding="utf-8") == DOUBLE
    assert S.run(apply=True, client=c, db=FakeDb())["planned"] == []      # повтор — ничего
