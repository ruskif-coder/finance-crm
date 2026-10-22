# -*- coding: utf-8 -*-
"""Материал креатива и письмо о правах стираются с диска ПОСЛЕ записи в базу (аудит 2.6.76, п. 1.10; сделано 22.10.2026).
Раньше файл уходил первым: не прошёл commit — строка оставалась со ссылкой на пустоту. Правило файла — `launch_prep.py`:
сначала база, потом диск (как у договоров, `test_contract_doc_replace`)."""
from types import SimpleNamespace

import pytest

from app.routers import launch_prep as LP


class _Db:
    def __init__(self, row, log, fail=False):
        self.row, self.log, self.fail = row, log, fail

    def query(self, model):
        row = self.row
        return SimpleNamespace(filter=lambda *a: SimpleNamespace(first=lambda: row))

    def delete(self, obj):
        self.log.append("delete")

    def commit(self):
        if self.fail:
            raise RuntimeError("commit не прошёл")
        self.log.append("commit")


@pytest.fixture
def wired(monkeypatch):
    log = []
    monkeypatch.setattr(LP, "_deal", lambda *a, **k: None)
    monkeypatch.setattr(LP, "_remove_file", lambda *a, **k: log.append("disk"))
    monkeypatch.setattr(LP, "remove_upload", lambda *a, **k: log.append("disk"))
    monkeypatch.setattr(LP, "log_action", lambda *a, **k: None)
    return log


def _row():
    return SimpleNamespace(id=1, set_id=1, deal_id=1, sent_at=None, path="lp/x.zip", sandbox_token="t", no=1,
                           rights_letter_path="lp/r.pdf", rights_letter_name="r.pdf")


def test_drop_file_commits_before_touching_disk(wired):
    LP.drop_file(1, _Db(_row(), wired), SimpleNamespace(id=1))
    assert wired.index("commit") < wired.index("disk")


def test_drop_file_keeps_the_file_when_commit_fails(wired):
    with pytest.raises(RuntimeError):
        LP.drop_file(1, _Db(_row(), wired, fail=True), SimpleNamespace(id=1))
    assert "disk" not in wired


def test_rights_letter_commits_before_touching_disk(wired):
    LP.drop_rights_letter(1, _Db(_row(), wired), SimpleNamespace(id=1))
    assert wired.index("commit") < wired.index("disk")
