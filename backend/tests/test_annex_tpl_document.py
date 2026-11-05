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


def test_head_and_place_are_editable_and_inherited(db, stub_plan):
    """Владелец 05.11.2026: «заголовок» и «место и дата» правятся в конструкторе ДС (мастер аккаунт и админ) — в этом ДС и во всех
    последующих ДС договора (постоянные ключи, наследование как у основания закрывающих)."""
    m = _model(db)
    assert m["head"]["edited"] is False and "{номер_дс}" in m["head"]["template"]
    assert m["place"]["template"] == AS.PLACE_DEFAULT
    assert AS.validate_edit(SAMPLE, AS.HEAD_KEY, "Дополнительное соглашение {номер_дс}\nк Договору № {договор_номер}") is None
    assert AS.validate_edit(SAMPLE, AS.PLACE_KEY, "г. Санкт-Петербург | {дата_дс_полностью}") is None

    edited = AS.assemble(db, _contract(db), _version(), period_from=date(2026, 11, 1), period_to=date(2026, 11, 30), deal_ids=[1, 2], no=7,
                         edits={AS.PLACE_KEY: "г. Санкт-Петербург | {дата_дс_полностью}"})
    assert edited["place"]["edited"] and edited["place"]["text"].startswith("г. Санкт-Петербург | «")
    assert edited["edits"][AS.PLACE_KEY], "правка замораживается — следующий ДС наследует её"

    later = AS.assemble(db, _contract(db), _version(), period_from=date(2026, 12, 1), period_to=date(2026, 12, 31), deal_ids=[1, 2], no=8,
                        defaults={AS.HEAD_KEY: {"text": "ДС {номер_дс}\nк договору {договор_номер}", "from": "ДС № 7"}})
    assert later["head"]["inherited_from"] == "ДС № 7" and later["head"]["text"].startswith("ДС №8")
    assert later["edits"][AS.HEAD_KEY], "унаследованная правка тоже уходит дальше по цепочке"


def test_word_file_prints_the_edited_head_and_place():
    import io

    from docx import Document

    from app.sales import annex_docx
    doc = {"number": "Приложение № 1", "contract": {"number": "Т-1", "date": date(2026, 1, 1)}, "date": date(2026, 9, 30),
           "period_from": date(2026, 10, 1), "period_to": date(2026, 10, 31), "executor": {"name": "Мы"}, "customer": {"name": "Они"},
           "body": "Текст.", "rows": [], "vat_rate": 22, "amount_words": "x", "vat_words": "y",
           "head_text": "Дополнительное соглашение №1\nк Договору оказания услуг № Т-1", "place_text": "г. Казань | «30» сентября 2026 г."}
    paras = [p.text for p in Document(io.BytesIO(annex_docx.build_docx(doc))).paragraphs][:4]
    assert paras[0] == "Дополнительное соглашение №1" and paras[1] == "к Договору оказания услуг № Т-1"
    assert paras[2] == "г. Казань\t«30» сентября 2026 г."


def test_head_edit_needs_the_master_deals_approve_right(db, monkeypatch):
    """Править заголовок и место — право «Мастер-сделки · согласование» (мастер аккаунт и админ); у прочих пунктов правило прежнее."""
    from fastapi import HTTPException
    a = db.query(SalesAnnex).filter(SalesAnnex.no.is_(None)).order_by(SalesAnnex.id.desc()).first()
    if a is None:
        pytest.skip("нужен черновик ДС")
    monkeypatch.setattr(A, "_may_change_rk", lambda db_, u: False)
    user = SimpleNamespace(id=None, name="тест", role=SimpleNamespace(key="role_8"), role_id=None)
    monkeypatch.setattr(A, "_annex", lambda db_, aid, u: a)
    with pytest.raises(HTTPException) as e:
        A.edit_block(a.id, A.EditIn(key=AS.HEAD_KEY, text="Заголовок {номер_дс}"), db=db, user=user)
    assert e.value.status_code == 403


def test_head_and_place_text_lives_in_the_template_too(db, stub_plan):
    """Владелец 05.11.2026: заголовок и «место и дата» правятся и в шаблоне (как преамбула) — это текст по умолчанию для всех ДС
    по шаблону; правка в карточке ДС — поверх него. Без текста в шаблоне и без правок файл печатает как раньше."""
    blocks = [dict(b, text="Соглашение {номер_дс}\nк договору {договор_номер}") if b.get("sys") == "head" else dict(b) for b in SAMPLE]
    m = AS.assemble(db, _contract(db), _version(blocks), period_from=date(2026, 11, 1), period_to=date(2026, 11, 30), deal_ids=[1, 2], no=7)
    assert m["head"]["custom"] and m["head"]["text"].startswith("Соглашение №7") and not m["head"]["edited"]
    assert not m["place"]["custom"], "место без текста в шаблоне — печатается как раньше"
    own = AS.assemble(db, _contract(db), _version(blocks), period_from=date(2026, 11, 1), period_to=date(2026, 11, 30), deal_ids=[1, 2], no=7,
                      edits={AS.HEAD_KEY: "Своё {номер_дс}"})
    assert own["head"]["text"] == "Своё №7", "правка в карточке ДС — поверх текста шаблона"


def test_template_check_validates_head_and_place_text():
    from app.annex_tpl.check import check
    blocks = [dict(b, text="г. Москва | {нет_такого}") if b.get("sys") == "place" else dict(b) for b in SAMPLE]
    assert any("нет_такого" in i["text"] for i in check(blocks))


def test_changing_head_text_in_a_template_needs_the_approve_right(monkeypatch):
    from fastapi import HTTPException
    from app.annex_tpl import rights
    old = [dict(b) for b in SAMPLE]
    new = [dict(b, text="Соглашение {номер_дс}") if b.get("sys") == "head" else dict(b) for b in SAMPLE]
    monkeypatch.setattr(rights, "may_edit_head", lambda db, u: False)
    with pytest.raises(HTTPException) as e:
        rights.assert_head_place_unchanged_or_allowed(None, None, old, new)
    assert e.value.status_code == 403
    rights.assert_head_place_unchanged_or_allowed(None, None, old, [dict(b) for b in SAMPLE])     # без изменений — можно
