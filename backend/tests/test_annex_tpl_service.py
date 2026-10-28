# -*- coding: utf-8 -*-
"""Шаблоны ДС: базовые с форматами, версии, откат, кастомный под договор, «базовый изменился» (спринт 1, 13–14.10.2026).

Все записи — внутри транзакции и откатываются в конце: тест не оставляет на стенде ни договоров, ни версий, а настоящий базовый
шаблон владельца не получает лишних версий — урок 05.10.2026, «тесты не едят данные стенда». Тесты правят шаблон ОТНОСИТЕЛЬНО
текущего (настоящего, если он заведён), поэтому не зависят от его текста.
"""
import copy
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.annex_tpl import service as S
from app.annex_tpl.models import AnnexTplFormat, AnnexTplTemplate, AnnexTplVersion
from app.database import SessionLocal
from app.models import Contract

SAMPLE = [
    {"id": "head", "sys": "head", "title": "Заголовок"},
    {"id": "place", "sys": "place", "title": "Место и дата"},
    {"id": "pre", "sys": "pre", "title": "Преамбула"},
    {"id": "p1", "title": "Предмет", "req": 1, "pin": 1, "text": "Услуги для бренда {бренд} в период {период_с} — {период_по}."},
    {"id": "mp", "sys": "table", "title": "Таблица МП"},
    {"id": "p11", "title": "Стоимость", "sub": 1, "req": 1, "pin": 1, "money": 1, "text": "Стоимость {сумма}, НДС {ндс_сумма}."},
    {"id": "p2", "title": "Претензии", "text": "Претензии направляются письменно."},
    {"id": "sign", "sys": "sign", "title": "Подписи"},
]
USER = SimpleNamespace(id=None, name="тест")
FMT = "Клиент"


def leak_counts(s) -> tuple:
    """Сколько строк в таблицах шаблонов и в журнале по ним: тест обязан оставить столько же, сколько нашёл."""
    return tuple(s.execute(text(q)).scalar() for q in (
        "select count(*) from annex_tpl_templates", "select count(*) from annex_tpl_versions",
        "select count(*) from annex_tpl_formats", "select count(*) from audit_log where action like 'annex_tpl%'"))


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


def _edit(blocks, text_):
    out = copy.deepcopy(blocks)
    target = next(b for b in out if not b.get("sys") and not b.get("pin"))
    target["text"] = text_
    return out


def _base(db, fmt=FMT):
    """Базовый шаблон формата: настоящий, если назначен, иначе образец — в обоих случаях всё откатится."""
    base = S.base_for_format(db, fmt)
    if base is None:
        S.create_base(db, "ТЕСТ образец", SAMPLE, None, "тест", [fmt])
        base = S.base_for_format(db, fmt)
    return base


def _contract(db, fmt=FMT):
    c = Contract(contract_number="ТЕСТ-ШАБЛОН", counterparty_name="тест", cooperation_format=fmt)
    db.add(c)
    db.flush()
    return c


def test_save_creates_next_version_and_changes(db):
    base = _base(db)
    v0 = S.current(db, base.id)
    v1 = S.save_version(db, base.id, _edit(v0.blocks, "Совсем иная редакция пункта."), USER)
    assert v1.version == v0.version + 1
    assert any(c[0] == "~" for c in v1.changes)
    assert S.current(db, base.id).id == v1.id


def test_invalid_template_is_not_saved(db):
    base = _base(db)
    cur = S.current(db, base.id)
    with pytest.raises(S.AnnexTplError) as e:
        S.save_version(db, base.id, _edit(cur.blocks, "{нет_такой}"), USER)
    assert e.value.status == 422 and e.value.issues
    assert S.current(db, base.id).id == cur.id          # версия не добавилась


def test_identical_text_is_not_a_new_version(db):
    base = _base(db)
    with pytest.raises(S.AnnexTplError) as e:
        S.save_version(db, base.id, S.current(db, base.id).blocks, USER)
    assert e.value.status == 400


def test_pinned_block_cannot_be_dropped(db):
    base = _base(db)
    cur = S.current(db, base.id)
    pinned = next((b["id"] for b in cur.blocks if b.get("pin")), None)
    assert pinned, "в базовом шаблоне должен быть закреплённый пункт"
    with pytest.raises(S.AnnexTplError) as e:
        S.save_version(db, base.id, [b for b in cur.blocks if b["id"] != pinned], USER)
    assert e.value.status == 422


def test_restore_makes_a_new_version_and_keeps_history(db):
    base = _base(db)
    v0 = S.current(db, base.id)
    v1 = S.save_version(db, base.id, _edit(v0.blocks, "Правка для отката номер один."), USER)
    v2 = S.restore(db, base.id, v0.version, USER)
    assert v2.version == v1.version + 1 and v2.restored_from == v0.version
    assert v2.blocks == v0.blocks
    assert S.version_of(db, base.id, v1.version) is not None        # история цела
    with pytest.raises(S.AnnexTplError):
        S.restore(db, base.id, v2.version, USER)                    # текущую откатывать нельзя


def test_create_base_variant_and_move_formats(db):
    """Новый вариант договора — новый шаблон; форматы переключаются на него без миграции."""
    one = _base(db)
    v = S.create_base(db, "ТЕСТ агентский вариант", S.current(db, one.id).blocks, None, "тест", ["Агентство КЛ"])
    variant = db.query(AnnexTplTemplate).filter_by(id=v.template_id).one()
    assert S.base_for_format(db, "Агентство КЛ").id == variant.id
    assert S.base_for_format(db, FMT).id == one.id                  # остальные форматы не тронуты
    S.set_formats(db, one.id, ["Агентство КЛ", FMT])                # формат переходит назад
    assert S.base_for_format(db, "Агентство КЛ").id == one.id
    assert S.formats_of(db, variant.id) == []
    with pytest.raises(S.AnnexTplError) as e:
        S.create_base(db, "тест АГЕНТСКИЙ вариант", SAMPLE, None, "тест")   # название без учёта регистра
    assert e.value.status == 409
    with pytest.raises(S.AnnexTplError):
        S.create_base(db, "   ", SAMPLE, None, "тест")


def test_formats_only_for_base(db):
    c = _contract(db)
    S.fork_custom(db, c, USER, title="Шаблон договора", main=True)
    with pytest.raises(S.AnnexTplError) as e:
        S.set_formats(db, S.custom_of(db, c.id).id, ["Клиент"])
    assert e.value.status == 400


def test_fork_custom_copies_base_and_remembers_it(db):
    base = _base(db)
    bcur = S.current(db, base.id)
    c = _contract(db)
    v = S.fork_custom(db, c, USER, title="Шаблон договора", main=True)
    tpl = S.custom_of(db, c.id)
    assert tpl.scope == "custom" and tpl.base_template_id == base.id and v.version == 1
    assert v.blocks == bcur.blocks and v.base_version == bcur.version
    assert S.base_state(db, tpl)["changed"] is False
    with pytest.raises(S.AnnexTplError) as e:
        S.fork_custom(db, c, USER, title="Шаблон договора", main=True)
    assert e.value.status == 409


def test_fork_needs_a_known_format(db):
    _base(db)
    with pytest.raises(S.AnnexTplError) as e:
        S.fork_custom(db, _contract(db, fmt=None), USER, title="Шаблон договора", main=True)
    assert e.value.status == 400 and "Формат сотрудничества" in e.value.message
    with pytest.raises(S.AnnexTplError) as e2:
        S.fork_custom(db, _contract(db, fmt="Формат без шаблона"), USER, title="Шаблон договора", main=True)
    assert e2.value.status == 409 and "не задан базовый шаблон" in e2.value.message


def test_base_changed_then_keep_own_or_adopt(db):
    base = _base(db)
    c = _contract(db)
    S.fork_custom(db, c, USER, title="Шаблон договора", main=True)
    tpl = S.custom_of(db, c.id)
    own_before = S.current(db, tpl.id)

    S.save_version(db, base.id, _edit(S.current(db, base.id).blocks, "Новая редакция базы для кастомных."), USER)
    st = S.base_state(db, tpl)
    assert st["changed"] is True and st["now"] > st["known"]
    assert any(ch[0] == "~" for ch in S.base_changes(db, tpl))
    assert S.current(db, tpl.id).blocks == own_before.blocks        # текст кастомного база не трогает

    kept = S.keep_own(db, tpl.id, USER)                              # «оставить свой»
    assert kept.blocks == own_before.blocks and kept.version == own_before.version + 1
    assert S.base_state(db, tpl)["changed"] is False
    with pytest.raises(S.AnnexTplError):
        S.keep_own(db, tpl.id, USER)                                 # база не менялась

    S.save_version(db, base.id, _edit(S.current(db, base.id).blocks, "Ещё одна редакция базы."), USER)
    assert S.base_state(db, tpl)["changed"] is True
    adopted = S.save_version(db, tpl.id, S.current(db, base.id).blocks, USER, adopt_base=True)   # «перенять базу»
    assert adopted.base_version == S.current(db, base.id).version
    assert S.base_state(db, tpl)["changed"] is False


def test_resolve_for_contract(db):
    base = _base(db)
    assert S.resolve_for_contract(db, _contract(db, fmt=None))["source"] == "none"
    assert "не задан базовый шаблон" in S.resolve_for_contract(db, _contract(db, fmt="Формат без шаблона"))["reason"]
    assert S.resolve_for_contract(db, _contract(db, fmt=FMT))["template"].id == base.id
    own = _contract(db, fmt=FMT)
    S.fork_custom(db, own, USER, title="Шаблон договора", main=True)
    r = S.resolve_for_contract(db, own)
    assert r["source"] == "custom" and r["template"].contract_id == own.id


def test_versions_cannot_be_updated(db):
    base = _base(db)
    v = S.current(db, base.id)
    db.flush()
    with pytest.raises(Exception) as e:
        db.execute(text("UPDATE annex_tpl_versions SET author_name = 'подмена' WHERE id = :i"), {"i": v.id})
    assert "не правятся" in str(e.value)


def test_seed_is_repeatable(db):
    first = S.seed_base(db, "ТЕСТ посев", SAMPLE, "тест", ["Подрядчик"])
    again = S.seed_base(db, "ТЕСТ посев", SAMPLE, "тест", ["Подрядчик"])
    assert first.id == again.id
    assert db.query(AnnexTplTemplate).filter(AnnexTplTemplate.title == "ТЕСТ посев").count() == 1
    assert db.query(AnnexTplVersion).filter_by(template_id=first.template_id).count() == 1
    assert db.query(AnnexTplFormat).filter_by(template_id=first.template_id).count() == 1
