# -*- coding: utf-8 -*-
"""Архив пакета и скан документа — та же область, что у карточки пакета: ВСЕ сделки пакета свои (ревью 21.10.2026).
Раньше хватало одной своей сделки, и роль «свои» скачивала ДС и сканы чужих сделок того же пакета."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import master_deals as R


@pytest.mark.parametrize("call", [
    lambda db, u: R.master_zip("M-X", db, u),
    lambda db, u: R.master_file_download("M-X", 1, db, u),
])
def test_zip_and_scan_need_every_deal_in_scope(monkeypatch, call):
    m = SimpleNamespace(id=1, code="M-X")
    monkeypatch.setattr(R, "_master", lambda db, code, user, lock=False: m)

    def foreign(db, m_, user):
        raise HTTPException(403, "сделка вне вашей зоны видимости")
    monkeypatch.setattr(R, "_scope_all", foreign)
    with pytest.raises(HTTPException) as e:
        call(None, SimpleNamespace(id=5))
    assert e.value.status_code == 403
