# -*- coding: utf-8 -*-
"""Несколько именованных шаблонов ДС под один договор, основной, память «бренд → шаблон», выбор в ДС (владелец 27.10.2026).

Шаблон по умолчанию для нового ДС: последний выбранный для его бренда → основной шаблон договора → базовый шаблон формата. Бренды ДС
указывают на разные шаблоны — основной. Выбранный руками шаблон главнее любого умолчания. Всё внутри транзакции и откатывается.
"""
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.annex_tpl import service as S
from app.database import SessionLocal
from app.models import Contract

SAMPLE = [
    {"id": "head", "sys": "head", "title": "Заголовок"},
    {"id": "place", "sys": "place", "title": "Место и дата"},
    {"id": "pre", "sys": "pre", "title": "Преамбула"},
    {"id": "p1", "title": "Предмет", "req": 1, "pin": 1, "text": "Услуги для бренда {бренд} в период {период_с} — {период_по}."},
    {"id": "p0", "title": "Порядок", "text": "Порядок оказания — по Договору."},
    {"id": "mp", "sys": "table", "title": "Таблица МП"},
    {"id": "p11", "title": "Стоимость", "sub": 1, "req": 1, "pin": 1, "money": 1, "text": "Стоимость {сумма}, НДС {ндс_сумма}."},
    {"id": "p2", "title": "Претензии", "text": "Претензии направляются письменно."},
    {"id": "sign", "sys": "sign", "title": "Подписи"},
]
USER = SimpleNamespace(id=None, name="тест")
FMT = "ТЕСТ формат именованных"


def leak_counts(s) -> tuple:
    return tuple(s.execute(text(q)).scalar() for q in (
        "select count(*) from annex_tpl_templates", "select count(*) from annex_tpl_versions",
        "select count(*) from annex_tpl_formats", "select count(*) from annex_tpl_brand_memory"))


@pytest.fixture
def db():
    s = SessionLocal()
    before = leak_counts(s)
    try:
        yield s
    finally:
        s.rollback()
        left = leak_counts(s)
        s.close()
        assert left == before, f"тест оставил строки шаблонов ДС на стенде: было {before}, стало {left}"


@pytest.fixture
def base(db):
    S.create_base(db, "ТЕСТ база именованных", SAMPLE, None, "тест", [FMT])
    return S.base_for_format(db, FMT)


def _contract(db, fmt=FMT):
    c = Contract(contract_number="ТЕСТ-ИМЕНА", counterparty_name="тест", cooperation_format=fmt)
    db.add(c)
    db.flush()
    return c


def _brands(db, n):
    """Существующие бренды: память пишется в транзакции теста и откатывается, брендов заводить не нужно."""
    ids = db.execute(text("SELECT id FROM sales_brands ORDER BY id LIMIT :n"), {"n": n}).scalars().all()
    assert len(ids) == n, "на стенде нет брендов"
    return ids


def _named(db, c, title, main=False, source_id=None, blocks=None):
    v = S.fork_custom(db, c, USER, title=title, source_id=source_id, blocks=blocks, main=main)
    return db.get(S.AnnexTplTemplate, v.template_id)


def test_several_named_templates_per_contract(db, base):
    c = _contract(db)
    a = _named(db, c, "Фарма")
    b = _named(db, c, "Ритейл")
    assert {t.id for t in S.customs_of(db, c.id)} == {a.id, b.id}
    assert a.title == "Фарма" and a.base_template_id == base.id and a.is_main is False


def test_name_is_required_and_unique_within_contract(db, base):
    c = _contract(db)
    _named(db, c, "Фарма")
    with pytest.raises(S.AnnexTplError) as e:
        _named(db, c, "  фарма ")
    assert e.value.status == 409 and "Фарма" in e.value.message
    with pytest.raises(S.AnnexTplError) as e2:
        _named(db, c, "   ")
    assert e2.value.status == 400
    assert _named(db, _contract(db), "Фарма").title == "Фарма"      # у другого договора то же имя можно


def test_fork_from_contract_template_copies_its_text(db, base):
    c = _contract(db)
    src = _named(db, c, "Исходный")
    edited = [dict(b, text="Претензии — в течение 5 дней.") if b["id"] == "p2" else b for b in S.current(db, src.id).blocks]
    S.save_version(db, src.id, edited, USER)
    copy = _named(db, c, "Копия", source_id=src.id)
    assert S.current(db, copy.id).blocks == edited
    assert copy.base_template_id == base.id                          # база — та же, что у источника


def test_fork_from_given_blocks(db, base):
    c = _contract(db)
    blocks = [dict(b, text="Порядок — по заявке Заказчика.") if b["id"] == "p0" else b for b in S.current(db, base.id).blocks]
    t = _named(db, c, "Из конструктора", blocks=blocks)
    assert S.current(db, t.id).blocks == blocks


def test_source_of_another_contract_is_refused(db, base):
    other = _named(db, _contract(db), "Чужой")
    with pytest.raises(S.AnnexTplError) as e:
        _named(db, _contract(db), "Мой", source_id=other.id)
    assert e.value.status == 400


def test_main_is_one_per_contract(db, base):
    c = _contract(db)
    a = _named(db, c, "А", main=True)
    b = _named(db, c, "Б")
    S.set_main(db, b.id, True)
    db.refresh(a)
    assert S.main_of(db, c.id).id == b.id and a.is_main is False
    S.set_main(db, b.id, False)
    assert S.main_of(db, c.id) is None
    with pytest.raises(S.AnnexTplError):
        S.set_main(db, base.id, True)                                # базовый основным договора не бывает


def test_rename(db, base):
    c = _contract(db)
    a = _named(db, c, "А")
    _named(db, c, "Б")
    assert S.rename(db, a.id, "  Новое имя ").title == "Новое имя"
    with pytest.raises(S.AnnexTplError) as e:
        S.rename(db, a.id, "б")
    assert e.value.status == 409


def test_default_base_then_main_then_brand_memory(db, base):
    c = _contract(db)
    b1, b2 = _brands(db, 2)
    r = S.resolve_for_contract(db, c, brand_ids=[b1])
    assert r["template"].id == base.id and r["why"] == "format"

    main = _named(db, c, "Основной", main=True)
    r = S.resolve_for_contract(db, c, brand_ids=[b1])
    assert r["template"].id == main.id and r["why"] == "main"

    pharma = _named(db, c, "Фарма")
    S.remember(db, c.id, [b1], pharma.id, None)
    r = S.resolve_for_contract(db, c, brand_ids=[b1])
    assert r["template"].id == pharma.id and r["why"] == "brand"
    assert S.resolve_for_contract(db, c, brand_ids=[b2])["template"].id == main.id     # у другого бренда памяти нет


def test_brands_disagree_main_wins(db, base):
    c = _contract(db)
    b1, b2 = _brands(db, 2)
    main = _named(db, c, "Основной", main=True)
    x, y = _named(db, c, "Икс"), _named(db, c, "Игрек")
    S.remember(db, c.id, [b1], x.id, None)
    S.remember(db, c.id, [b2], y.id, None)
    assert S.resolve_for_contract(db, c, brand_ids=[b1, b2])["template"].id == main.id
    S.remember(db, c.id, [b2], x.id, None)                           # память перезаписывается
    assert S.resolve_for_contract(db, c, brand_ids=[b1, b2])["template"].id == x.id


def test_chosen_wins_over_defaults(db, base):
    c = _contract(db)
    b1, = _brands(db, 1)
    _named(db, c, "Основной", main=True)
    alt = _named(db, c, "Альтернативный")
    r = S.resolve_for_contract(db, c, brand_ids=[b1], chosen_id=alt.id)
    assert r["template"].id == alt.id and r["why"] == "chosen"
    assert S.resolve_for_contract(db, c, chosen_id=base.id)["template"].id == base.id   # базовый формата тоже можно выбрать


def test_chosen_template_of_another_contract_is_refused(db, base):
    foreign = _named(db, _contract(db), "Чужой")
    with pytest.raises(S.AnnexTplError) as e:
        S.resolve_for_contract(db, _contract(db), chosen_id=foreign.id)
    assert e.value.status == 400


def test_templates_for_picker(db, base):
    c = _contract(db)
    main = _named(db, c, "Основной", main=True)
    other = _named(db, c, "Другой")
    ids = [t.id for t in S.choices(db, c)]
    assert ids == [main.id, other.id, base.id]                       # основной первым, базовый формата последним


def test_blocks_from_model_takes_text_on_screen():
    model = [{"id": "p0", "source_text": "Порядок — по заявке {бренд}."}, {"id": "mp", "sys": "table"},
             {"id": "p2", "source_text": "Претензии направляются письменно."}]
    out = S.blocks_from_model(SAMPLE, model)
    assert next(b for b in out if b["id"] == "p0")["text"] == "Порядок — по заявке {бренд}."
    assert next(b for b in out if b["id"] == "p11") == next(b for b in SAMPLE if b["id"] == "p11")
    assert SAMPLE[4]["text"] == "Порядок оказания — по Договору."     # исходник не тронут
