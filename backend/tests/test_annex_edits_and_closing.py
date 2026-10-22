# -*- coding: utf-8 -*-
"""ДС: быстрая правка блоков зоны аккаунта и основание для закрывающих документов (14.10.2026).

Сборка проверяется на подставленных строках плана; ручка правки — на настоящем черновике, который убирается по id после теста
(и строки журнала тоже — по id, а не по окну времени).
"""
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import func, text

import app.model_registry  # noqa: F401
from app.annex_tpl import assemble as AS
from app.annex_tpl.assemble import CLOSING_KEY, validate_edit
from app.database import SessionLocal
from app.routers import annexes as A
from app.sales.models import SalesAnnex
from tests.test_annex_tpl_document import SAMPLE, _contract, _version, stub_plan  # noqa: F401  (stub_plan — фикстура)


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _assemble(db, edits=None, blocks=None):
    return AS.assemble(db, _contract(db), _version(blocks), period_from=date(2026, 11, 1), period_to=date(2026, 11, 30),
                       deal_ids=[1, 2], no=7, edits=edits)


def test_edit_of_an_account_block_is_applied_and_keeps_the_substitutions_live(db, stub_plan):  # noqa: F811
    m = _assemble(db, edits={"p1": "Услуги для бренда {бренд}: правка аккаунта."})
    p1 = next(b for b in m["blocks"] if b["id"] == "p1")
    assert p1["edited"] is True and p1["text"].endswith("правка аккаунта.") and "{" not in p1["text"]
    assert p1["source_text"] == "Услуги для бренда {бренд}: правка аккаунта."        # в редактор уходит текст с подстановками
    assert p1["template_text"] != p1["source_text"]
    assert m["edits"] == {"p1": "Услуги для бренда {бренд}: правка аккаунта."}


def test_edit_of_a_lawyer_block_is_ignored_by_assembly(db, stub_plan):  # noqa: F811
    """Блок после таблицы МП аккаунт не правит: даже если правка попала в хранилище, сборка её не применяет."""
    m = _assemble(db, edits={"p11": "Подмена стоимости."})
    cost = next(b for b in m["blocks"] if b["id"] == "p11")
    assert cost["edited"] is False and "Подмена" not in cost["text"]


def test_closing_basis_follows_the_owners_sample(db, stub_plan, monkeypatch):  # noqa: F811
    monkeypatch.setattr(AS, "_brands_only", lambda db, ids: "Магне В6")
    m = _assemble(db)
    cb = m["closing_basis"]
    # в заглушке плана есть и размещение, и допы — основание смешанного ДС (владелец 21.10.2026)
    assert cb["edited"] is False and cb["template"] == AS.closing_template_for([{"kind": "base"}, {"kind": "extra"}])
    assert cb["text"].startswith("Размещение рекламных материалов и оказание дополнительных услуг (")
    assert "бренда «Магне В6», в сети SIMB-AD, согласно Доп.соглашению 7 от " in cb["text"]
    assert cb["text"].endswith("г., с 01.11.2026 по 30.11.2026г.")
    assert m["values"]["сеть"] == "SIMB-AD" and len(m["values"]["дата_дс_кратко"]) == 8          # ДД.ММ.ГГ
    mine = _assemble(db, edits={CLOSING_KEY: "Услуги по {бренд_название}, ДС {номер_дс}."})["closing_basis"]
    assert mine["edited"] is True and mine["text"].startswith("Услуги по Магне В6, ДС 7")


def test_validate_edit_rules():
    blocks = SAMPLE
    assert validate_edit(blocks, "p1", "Нормальный текст {бренд}.") is None
    assert "только юрист" in validate_edit(blocks, "p11", "Текст стоимости.")
    assert "Нет такого" in validate_edit(blocks, "нет", "Текст пункта.")
    assert "Неизвестная подстановка" in validate_edit(blocks, "p1", "Текст {что_это}.")
    assert "пустым" in validate_edit(blocks, "p1", "  ")
    assert validate_edit(blocks, CLOSING_KEY, "Основание {номер_дс}.") is None            # основание — любому с правом на приложения


# ── ручка правки на настоящем черновике ───────────────────────────────────────────────────────

@pytest.fixture
def draft_env():
    s = SessionLocal()
    high_a = s.query(func.max(SalesAnnex.id)).scalar() or 0
    high_l = s.execute(text("select coalesce(max(id), 0) from audit_log")).scalar()
    s.close()
    yield
    s = SessionLocal()
    s.execute(text("delete from sales_deal_annex_allocation where annex_id > :a"), {"a": high_a})
    s.execute(text("delete from sales_annexes where id > :a"), {"a": high_a})
    s.execute(text("delete from audit_log where id > :l"), {"l": high_l})
    s.commit()
    s.close()


def test_edit_endpoint_on_a_draft_stores_edits_and_refuses_the_lawyer_zone(draft_env):
    db = SessionLocal()
    try:
        c = _contract(db)
        actor = SimpleNamespace(id=None, name="тест", role=SimpleNamespace(key="admin", is_master=True))
        d = A.create_annex(A.AnnexIn(contract_id=c.id, period_from=date(2026, 6, 1), period_to=date(2026, 6, 30), total_amount=1000), db, actor)
        out = A.edit_block(d["id"], A.EditIn(key="p1", text="Правка {бренд} аккаунтом."), db, actor)
        assert out["edits"] == {"p1": "Правка {бренд} аккаунтом."}
        assert db.query(SalesAnnex).get(d["id"]).blocks == {"edits": {"p1": "Правка {бренд} аккаунтом."}}
        with pytest.raises(HTTPException) as e:
            A.edit_block(d["id"], A.EditIn(key="p11", text="Подмена стоимости."), db, actor)
        assert e.value.status_code == 400 and "юрист" in e.value.detail
        back = A.edit_block(d["id"], A.EditIn(key="p1", text=None), db, actor)           # вернуть по шаблону
        assert back["edits"] == {} and db.query(SalesAnnex).get(d["id"]).blocks is None
    finally:
        db.close()


def test_a_document_frozen_before_the_closing_basis_existed_is_upgraded_for_the_screen(db, stub_plan, monkeypatch):  # noqa: F811
    """Экран падал на замороженном документе без `closing_basis` (приложение 766 пересоздали до появления блока, 14.10.2026)."""
    from app.annex_tpl import document as D
    monkeypatch.setattr(AS, "_brands_only", lambda db, ids: "Магне В6")
    old = {"blocks": [{"id": "p1", "text": "Замороженный текст."}], "values": {"бренд": "Старый"}, "amount": 1.0}
    annex = SimpleNamespace(blocks=old, no=3, date=date(2026, 10, 31), template_version_id=None, period_from=date(2026, 11, 1),
                            period_to=date(2026, 11, 30), total_amount=1000.0)
    up = D.upgrade_frozen(db, annex, _contract(db), [1, 2])
    assert up["blocks"][0]["text"] == "Замороженный текст." and up["values"]["бренд"] == "Старый"      # замороженное не тронуто
    assert "бренда «Магне В6»" in up["closing_basis"]["text"] and up["edits"] == {}
    assert "closing_basis" not in old                                                           # исходный документ не изменён на месте


def test_old_frozen_blocks_get_source_text_so_the_editor_is_not_empty(db, stub_plan):  # noqa: F811
    """Окно правки пункта открывалось пустым у документа, замороженного до появления `source_text` (скриншот владельца 14.10.2026)."""
    from app.annex_tpl import document as D
    old = {"blocks": [{"id": "pre", "sys": "pre"}, {"id": "p1", "title": "Предмет", "zone": "acc", "template_text": "Текст {бренд}.", "text": "Текст Икс."},
                      {"id": "mp", "sys": "table"}, {"id": "p11", "title": "Стоимость", "zone": "law", "template_text": "Деньги.", "text": "Деньги."}],
           "values": {}, "edits": {"p1": "Правка {бренд}."}, "closing_basis": {}}
    annex = SimpleNamespace(blocks=old, no=3, date=date(2026, 10, 31), template_version_id=None, period_from=date(2026, 11, 1),
                            period_to=date(2026, 11, 30), total_amount=1000.0)
    up = D.upgrade_frozen(db, annex, _contract(db), [1, 2])
    p1 = next(b for b in up["blocks"] if b["id"] == "p1")
    law = next(b for b in up["blocks"] if b["id"] == "p11")
    assert p1["source_text"] == "Правка {бренд}." and p1["edited"] is True          # правка аккаунта — в редактор с подстановками
    assert law["source_text"] == "Деньги." and law["edited"] is False
    assert all("source_text" not in b for b in old["blocks"])                        # исходный документ не изменён на месте


# ── пункт 1 и основание по умолчанию — из прошлого ДС договора ─────────────────────────────────

def _annex_row(db, contract, number, edits):
    row = SalesAnnex(contract_id=contract.id, number=number, period_from=date(2026, 6, 1), period_to=date(2026, 6, 30),
                     blocks={"edits": edits} if edits is not None else None)
    db.add(row)
    db.flush()
    return row


def test_previous_annex_edit_becomes_the_default_and_reset_stops_it(db):
    from app.annex_tpl import document as D
    c = _contract(db)
    _annex_row(db, c, "Приложение № 1", {"p1": "Текст из первого ДС {бренд}.", "closing_basis": "Основание из первого."})
    _annex_row(db, c, "Приложение № 2", {"p1": "Свежий текст из второго ДС."})
    third = _annex_row(db, c, None, None)
    prev = D.previous_defaults(db, third, c)
    assert prev["p1"] == {"text": "Свежий текст из второго ДС.", "from": "Приложение № 2"}          # самая свежая правка ключа
    assert prev["closing_basis"]["from"] == "Приложение № 1"                                        # цепочка: ключ берётся там, где он есть
    _annex_row(db, c, "Приложение № 3", {"p1": None})                                                # явный сброс «по шаблону»
    fourth = _annex_row(db, c, None, None)
    assert "p1" not in D.previous_defaults(db, fourth, c) and "closing_basis" in D.previous_defaults(db, fourth, c)


def test_assembly_applies_inherited_text_by_template_block_id_and_marks_it(db, stub_plan):  # noqa: F811
    defaults = {"p1": {"text": "Унаследованный пункт для {бренд}.", "from": "Приложение № 2"},
                "p11": {"text": "Подмена стоимости.", "from": "Приложение № 2"},                  # юридический блок — привязка не применяется
                "нет_такого": {"text": "Пункта нет в шаблоне.", "from": "Приложение № 2"},
                "closing_basis": {"text": "Основание из прошлого ДС {номер_дс}.", "from": "Приложение № 2"}}
    m = AS.assemble(db, _contract(db), _version(), period_from=date(2026, 11, 1), period_to=date(2026, 11, 30), deal_ids=[1, 2], no=7, defaults=defaults)
    p1 = next(b for b in m["blocks"] if b["id"] == "p1")
    assert p1["edited"] is False and p1["inherited_from"] == "Приложение № 2" and p1["text"].startswith("Унаследованный пункт для ")
    cost = next(b for b in m["blocks"] if b["id"] == "p11")
    assert cost["inherited_from"] is None and "Подмена" not in cost["text"]
    assert m["closing_basis"]["inherited_from"] == "Приложение № 2" and m["closing_basis"]["text"] == "Основание из прошлого ДС 7."
    assert m["edits"] == {"p1": "Унаследованный пункт для {бренд}.", "closing_basis": "Основание из прошлого ДС {номер_дс}."}   # эффективные — их заморозит подтверждение
    own = AS.assemble(db, _contract(db), _version(), period_from=date(2026, 11, 1), period_to=date(2026, 11, 30), deal_ids=[1, 2], no=7,
                      edits={"p1": "Свой текст."}, defaults=defaults)
    assert next(b for b in own["blocks"] if b["id"] == "p1")["text"] == "Свой текст." and next(b for b in own["blocks"] if b["id"] == "p1")["inherited_from"] is None
    reset = AS.assemble(db, _contract(db), _version(), period_from=date(2026, 11, 1), period_to=date(2026, 11, 30), deal_ids=[1, 2], no=7,
                        edits={"p1": None, "closing_basis": None}, defaults=defaults)
    assert next(b for b in reset["blocks"] if b["id"] == "p1")["inherited_from"] is None
    assert reset["closing_basis"]["template"] == AS.closing_template_for([{"kind": "base"}, {"kind": "extra"}])
    assert reset["edits"]["p1"] is None and reset["edits"]["closing_basis"] is None        # сброс замораживается и обрывает цепочку для следующего ДС

