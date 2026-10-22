# -*- coding: utf-8 -*-
"""ДС по шаблону: сборка модели документа, названия юрлиц, заморозка при подтверждении (спринт 2, 14.10.2026).

Сборка проверяется на ПОДСТАВЛЕННЫХ строках плана: тест не зависит от того, какие сделки есть на стенде. Записи в базу — внутри
транзакции с откатом (как в тестах шаблонов).
"""
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import func

import app.model_registry  # noqa: F401
from app.annex_tpl import assemble as AS
from app.annex_tpl.legal_name import legal_name
from app.annex_tpl import service as S
from app.database import SessionLocal
from app.models import Contract
from app.routers import annexes as A
from app.sales.models import SalesAnnex
from tests.test_annex_tpl_service import SAMPLE


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _contract(db):
    c = (db.query(Contract).filter(Contract.cooperation_format.isnot(None), Contract.counterparty_id.isnot(None))
         .order_by(Contract.id).first())
    if c is None:
        pytest.skip("нужен договор с форматом сотрудничества и контрагентом")
    return c


def _version(blocks=None):
    return SimpleNamespace(id=1, template_id=1, version=1, blocks=blocks or SAMPLE)


ROWS = [
    {"deal_id": 1, "position": "еФарм", "model": "CPM", "volume": 1000000.0, "amount": 100000.0, "format": "Баннеры", "device": "WEB"},
    {"deal_id": 1, "position": "Sales-Lift", "model": "Бонус", "volume": None, "amount": None, "kind": "extra"},
    {"deal_id": 1, "position": "Комплект", "model": "Полная цена", "volume": None, "amount": 10000.0, "kind": "extra"},
    {"deal_id": 2, "position": "Polza", "model": "CPM", "volume": 500000.0, "amount": 50000.0},
]


@pytest.fixture
def stub_plan(monkeypatch):
    monkeypatch.setattr(AS.A, "plan_rows", lambda db, ids: [dict(r) for r in ROWS])
    monkeypatch.setattr(AS.A, "deal_brands", lambda db, ids: {1: "АО Альфа / Бета", 2: "ООО Гамма"})
    monkeypatch.setattr(AS.A, "deal_brand", lambda db, ids: "АО Альфа / Бета, ООО Гамма")
    monkeypatch.setattr(AS, "_advertisers", lambda db, ids: "АО Альфа, ООО Гамма")


def _model(db, blocks=None):
    return AS.assemble(db, _contract(db), _version(blocks), period_from=date(2026, 11, 1), period_to=date(2026, 11, 30),
                       deal_ids=[1, 2], no=7)


def test_legal_names_are_abbreviated_and_unknown_ones_are_left_alone():
    assert legal_name("ГРИНДЕКС РУС ООО") == "ООО «ГРИНДЕКС РУС»"
    assert legal_name("ООО «Ромашка»") == "ООО «Ромашка»"
    assert legal_name("АО Ромашка") == "АО «Ромашка»"
    assert legal_name("Лукин Евгений Витальевич ИП") == "ИП Лукин Евгений Витальевич"
    assert legal_name("ПУГАЧЕВ ДЕНИС ДМИТРИЕВИЧ ИНДИВИДУАЛЬНЫЙ ПРЕДПРИНИМАТЕЛЬ") == "ИП ПУГАЧЕВ ДЕНИС ДМИТРИЕВИЧ"
    assert legal_name("КОЛТАЧ СОЛЮШНС") == "КОЛТАЧ СОЛЮШНС" and legal_name("") == "" and legal_name(None) == ""


def test_table_is_grouped_by_brand_with_extras_after_placements(db, stub_plan):
    m = _model(db)
    groups = m["table"]["groups"]
    assert [g["brand"] for g in groups] == ["АО Альфа / Бета", "ООО Гамма"]
    assert [r["position"] for r in groups[0]["rows"]] == ["еФарм", "Sales-Lift", "Комплект"]   # размещения, затем допы


def test_vat_is_charged_on_top_per_row_and_sums_agree(db, stub_plan):
    m = _model(db)
    rate = m["vat_rate"]
    t = m["table"]["totals"]
    assert t["net"] == 160000.0 and t["vat"] == round(160000 * rate / 100, 2)
    assert t["gross"] == round(t["net"] + t["vat"], 2) and m["amount"] == t["gross"] and m["vat"] == t["vat"]
    assert m["consistency"]["ok"] is True
    first = m["table"]["groups"][0]["rows"][0]
    assert first["gross"] == round(first["amount"] + first["vat"], 2)         # итог строки = цена + НДС строки


def test_bonus_row_stays_in_the_table_without_a_price(db, stub_plan):
    bonus = [r for g in _model(db)["table"]["groups"] for r in g["rows"] if r["position"] == "Sales-Lift"][0]
    assert bonus["bonus"] is True and bonus["amount"] is None and bonus["gross"] is None


def test_text_blocks_get_the_values_and_keep_zones_and_numbers(db, stub_plan):
    m = _model(db)
    p1 = next(b for b in m["blocks"] if b.get("id") == "p1")
    assert p1["num"] == "1." and p1["zone"] == "acc"
    assert "{" not in p1["text"] and "АО Альфа / Бета, ООО Гамма" in p1["text"]
    cost = next(b for b in m["blocks"] if b.get("id") == "p11")
    assert cost["num"] == "1.1." and cost["zone"] == "law" and m["values"]["сумма"] in cost["text"]
    assert any(p.get("key") == "сумма" for p in cost["parts"])


def test_empty_substitution_is_named_with_where_to_fill(db, stub_plan, monkeypatch):
    monkeypatch.setattr(AS, "_advertisers", lambda db, ids: "")
    blocks = [dict(b) for b in SAMPLE]
    blocks[3] = {**blocks[3], "text": "Рекламодатель {рекламодатель}, бренд {бренд}."}
    miss = _model(db, blocks)["missing"]
    assert any("рекламодатель" in m["text"] and "карточка сделки" in m["where"] for m in miss)


def test_missing_executor_or_customer_details_are_listed(db, stub_plan):
    m = _model(db)
    for who in (m["executor"], m["customer"]):
        assert who["legal_name"] == legal_name(who["name"])


def test_no_template_is_a_conflict(db):
    with pytest.raises(S.AnnexTplError) as e:
        AS.assemble(db, _contract(db), None, period_from=date(2026, 11, 1), period_to=date(2026, 11, 30))
    assert e.value.status == 409


@pytest.fixture
def no_leftovers():
    s = SessionLocal()
    high = s.query(func.max(SalesAnnex.id)).scalar() or 0
    s.close()
    yield
    s = SessionLocal()
    s.query(SalesAnnex).filter(SalesAnnex.id > high).delete(synchronize_session=False)
    s.commit()
    s.close()


def test_confirm_refuses_an_incomplete_document_and_burns_no_number(db, no_leftovers):
    """Подтверждение не занимает номер, пока документ неполон: бумагу с пустым местом подписывают не глядя."""
    c = _contract(db)
    actor = SimpleNamespace(id=None, name="тест", role=SimpleNamespace(key="admin", is_master=True))
    draft = A.create_annex(A.AnnexIn(contract_id=c.id, period_from=date(2026, 6, 1), period_to=date(2026, 6, 30),
                                     total_amount=1000), db, actor)
    assert draft["template_version_id"]                                      # версия запомнена при создании
    with pytest.raises(HTTPException) as e:
        A.confirm_annex(draft["id"], A.ConfirmIn(), db, actor)
    assert e.value.status_code == 409 and "неполон" in e.value.detail
    assert db.query(SalesAnnex).get(draft["id"]).no is None


def test_freeze_stores_the_whole_document_and_the_version(db, monkeypatch):
    c = _contract(db)
    ver = S.current(db, S.resolve_for_contract(db, c)["template"].id)
    model = {"amount": 100.0, "date": date(2026, 5, 31), "missing": [], "consistency": {"ok": True, "details": []},
             "template": {"version_id": ver.id}, "blocks": [{"id": "p1", "text": "Текст"}]}
    monkeypatch.setattr(A, "tpl_assemble", lambda *a, **k: dict(model))
    monkeypatch.setattr(A, "_annex_deals", lambda db, aid: [])
    a = SimpleNamespace(id=1, period_from=date(2026, 6, 1), period_to=date(2026, 6, 30), total_amount=100.0, date=date(2026, 5, 31), blocks=None)
    frozen = A._freeze_for_confirm(db, a, c, 5)
    assert frozen["template"]["version_id"] == ver.id and frozen["date"] == "2026-05-31"      # даты приведены к JSON при заморозке
    monkeypatch.setattr(A, "tpl_assemble", lambda *a, **k: {**model, "missing": [{"text": "не заполнено: бренд", "where": "сделка"}]})
    with pytest.raises(HTTPException) as e:
        A._freeze_for_confirm(db, a, c, 5)
    assert e.value.status_code == 409 and "не заполнено: бренд" in e.value.detail


def test_old_export_takes_clause_one_from_the_template_and_drops_the_stale_requirement(db, stub_plan):
    """Экран и PDF/DOCX строятся из старого `annex.build`: «не задан шаблон формулировки услуги» там — устаревшее требование
    (шаблон по плательщику заменён конструктором), а пункт 1 пуст. Мост берёт текст из шаблона и снимает требование."""
    from app.annex_tpl import document as D
    c = _contract(db)
    annex = SimpleNamespace(blocks=None, no=None, date=None, period_from=date(2026, 11, 1), period_to=date(2026, 11, 30), total_amount=1000.0)
    doc = {"body": "", "missing": [D.OLD_NO_TEMPLATE, "заказчик: ИНН"]}
    out = D.bridge_old_doc(db, annex, c, doc, [1, 2])
    assert D.OLD_NO_TEMPLATE not in out["missing"] and "заказчик: ИНН" in out["missing"]
    assert out["body"] and "{" not in out["body"]
    frozen = SimpleNamespace(blocks={"blocks": [{"id": "x", "sys": "head"}, {"id": "p1", "text": "Замороженный пункт 1."}], "missing": [],
                                     "edits": {}, "closing_basis": {"text": "Основание."}}, template_version_id=None)
    out2 = D.bridge_old_doc(db, frozen, c, {"body": "", "missing": [D.OLD_NO_TEMPLATE]}, [])
    assert out2["body"] == "Замороженный пункт 1." and out2["missing"] == []


def test_bonus_row_has_dashes_in_every_money_column_of_the_word_file():
    """Бонус: цена за единицу, стоимость, НДС и итог — прочерки; пустых ячеек в таблице не остаётся (замечание владельца 14.10.2026)."""
    import io

    from docx import Document

    from app.sales import annex_docx
    rows = [
        {"network": "SIMB-AD", "position": "еФарм", "unit_price": 345.0, "amount": 735010.77, "vat": 161702.37, "gross": 896713.14, "bonus": False},
        {"network": "SIMB-AD", "position": "Sales-Lift", "model": "Бонус", "unit_price": 150000.0, "amount": None, "vat": None, "gross": None, "bonus": True},
    ]
    doc = {"number": "Приложение № 1", "contract": {"number": "Т-1", "date": date(2026, 1, 1)}, "date": date(2026, 9, 30), "period_from": date(2026, 10, 1),
           "period_to": date(2026, 10, 31), "executor": {"name": "Мы"}, "customer": {"name": "Они"}, "body": "Текст.", "rows": rows, "vat_rate": 22,
           "amount_words": "x", "vat_words": "y"}
    table = Document(io.BytesIO(annex_docx.build_docx(doc))).tables[0]
    cells = [c.text.strip() for c in table.rows[2].cells]            # строка 0 — шапка, 1 — еФарм, 2 — Sales-Lift
    assert cells[9:13] == ["—", "—", "—", "—"], cells
    assert [c.text.strip() for c in table.rows[1].cells][9] == "345,00"
