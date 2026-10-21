# -*- coding: utf-8 -*-
"""Шаблоны ДС: ручки (вызов функций роутера напрямую, как в `test_annex_api.py`). Всё внутри транзакции с откатом."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.model_registry  # noqa: F401
from app.annex_tpl import service as S
from app.database import SessionLocal
from app.models import Contract
from app.routers import annex_templates as R
from tests.test_annex_tpl_service import FMT, SAMPLE, _base, leak_counts

USER = SimpleNamespace(id=None, name="тест")


@pytest.fixture
def db(monkeypatch):
    """Ручки коммитят сами (и `log_action` тоже): в тесте коммит превращён в flush, иначе запись остаётся на стенде —
    так 14.10.2026 тест перенёс два формата настоящего шаблона на тестовый. Откат в конце снимает всё."""
    s = SessionLocal()
    before = leak_counts(s)
    monkeypatch.setattr(s, "commit", s.flush)
    try:
        yield s
    finally:
        s.rollback()
        left = leak_counts(s)
        s.close()
        assert left == before, f"тест оставил строки шаблонов ДС на стенде: было {before}, стало {left}"


def test_listing_formats_and_subs(db):
    base = _base(db)
    items = R.list_templates(db=db, user=USER)["items"]
    assert any(i["scope"] == "base" and i["id"] == base.id and i["title"] and i["version"] >= 1 for i in items)
    out = R.formats(db=db, user=USER)
    assert FMT in out["known"] and out["map"][FMT] == base.id
    assert {s["key"] for s in R.subs(user=USER)["items"]} >= {"бренд", "сумма", "ндс_сумма"}


def test_check_endpoint_reports_without_writing(db):
    bad = [dict(b) for b in SAMPLE]
    bad[3] = {**bad[3], "text": "{нет_такой}"}
    out = R.check_blocks(R.BlocksIn(blocks=bad), user=USER)
    assert out["issues"] and "неизвестная подстановка" in out["issues"][0]["text"]


def test_save_with_errors_is_422_with_issues(db):
    base = _base(db)
    bad = [dict(b) for b in S.current(db, base.id).blocks]
    bad[3] = {**bad[3], "text": "{нет_такой}"}
    with pytest.raises(HTTPException) as e:
        R.save(base.id, R.BlocksIn(blocks=bad), db=db, user=USER)
    assert e.value.status_code == 422 and e.value.detail["issues"]


def test_create_variant_from_existing_and_assign_formats(db):
    base = _base(db)
    out = R.create_base(R.BaseIn(title="ТЕСТ вариант API", copy_from=base.id, formats=["Подрядчик"]), db=db, user=USER)
    assert out["scope"] == "base" and out["formats"] == ["Подрядчик"] and out["version"] == 1
    moved = R.set_formats(out["id"], R.FormatsIn(formats=["Подрядчик", "Аптека"]), db=db, user=USER)
    assert moved["formats"] == ["Аптека", "Подрядчик"]
    with pytest.raises(HTTPException) as e:
        R.create_base(R.BaseIn(title="без источника"), db=db, user=USER)
    assert e.value.status_code == 400


def test_for_contract_without_format_explains_why(db):
    c = Contract(contract_number="ТЕСТ-АПИ", counterparty_name="тест")
    db.add(c)
    db.flush()
    out = R.for_contract(c.id, db=db, user=USER)
    assert out["source"] == "none" and "Формат сотрудничества" in out["reason"] and out["template"] is None


def test_unknown_template_and_contract_are_404(db):
    with pytest.raises(HTTPException) as e:
        R.one(10 ** 9, db=db, user=USER)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e2:
        R.for_contract(10 ** 9, db=db, user=USER)
    assert e2.value.status_code == 404
