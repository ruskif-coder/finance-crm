# -*- coding: utf-8 -*-
"""Вид документа по договору («Приложение» / «ДС»): выбирается ОДИН раз — при первой сборке ДС, вместе со стартовым
номером, — и дальше меняется только администратором (владелец 31.10.2026: «фиксировать в базе — правки только для меня»;
администратор в системе один, это владелец).

Правило одно на все места, откуда вид можно поменять: панель сборки мастер-сделки, тумблер в карточке договора, правка
договора. Иначе запрет в одном месте обходился бы через другое.

Тесты не коммитят: `commit` подменён на `flush` (`log_action` коммитит сам), фикстура откатывает. Стенд — копия прода.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.annex_tpl import doc_kind as DK

ADMIN = SimpleNamespace(role=SimpleNamespace(key="admin"))
ACCOUNT = SimpleNamespace(role=SimpleNamespace(key="role_8"))


# ── само правило ─────────────────────────────────────────────────────────────

def test_first_choice_is_open_to_whoever_assembles():
    """Пока вид не выбран, его фиксирует тот, кто собирает ДС, — это и есть первичный выбор."""
    c = SimpleNamespace(annex_word=None)
    assert DK.assign(c, "дс", ACCOUNT) == "дс" and c.annex_word == "дс"


def test_once_chosen_only_admin_changes_it():
    c = SimpleNamespace(annex_word="дс")
    with pytest.raises(PermissionError):
        DK.assign(c, "приложение", ACCOUNT)
    assert c.annex_word == "дс", "запрет не должен успевать менять значение"
    with pytest.raises(PermissionError):
        DK.assign(c, None, ACCOUNT)        # сбросить — тоже изменение
    assert DK.assign(c, "приложение", ADMIN) == "приложение"


def test_repeating_the_same_choice_is_not_a_change():
    """Тот же вид ещё раз — не изменение: сохранение панели со стартовым номером не должно падать у аккаунта."""
    c = SimpleNamespace(annex_word="дс")
    assert DK.assign(c, "дс", ACCOUNT) == "дс"


def test_unknown_word_is_refused_by_word():
    with pytest.raises(ValueError):
        DK.assign(SimpleNamespace(annex_word=None), "доп", ADMIN)


# ── правило действует во всех местах ─────────────────────────────────────────

@pytest.fixture
def rw(db, monkeypatch):
    monkeypatch.setattr(db, "commit", db.flush)
    return db


def _non_admin(db):
    from app.models import Role, User
    u = (db.query(User).join(Role, Role.id == User.role_id)
         .filter(Role.key != "admin", User.is_active == 1).order_by(User.id).first())
    if u is None:
        pytest.skip("на стенде нет активной учётки не-админа")
    return u


def test_contract_update_cannot_bypass_the_lock(rw):
    """Правка договора — тот же запрет: иначе тумблер в карточке обходил бы панель сборки."""
    from app.models import Contract
    from app.routers.contracts import ContractCreate, update_contract
    db = rw
    c = db.query(Contract).order_by(Contract.id).first()
    c.annex_word = "дс"
    db.flush()
    with pytest.raises(HTTPException) as e:
        update_contract(c.id, ContractCreate(annex_word="приложение"), db=db, current_user=_non_admin(db))
    assert e.value.status_code == 403
    db.expire_all()
    assert db.get(Contract, c.id).annex_word == "дс"


def test_first_assembly_fixes_the_kind_together_with_the_start_number(rw, monkeypatch):
    """Панель сборки мастер-сделки сохраняет вид той же кнопкой, что стартовый номер."""
    from app.master_deal.models import MasterDeal
    from app.models import Contract
    from app.routers.master_deals import StartNoIn, master_start_no
    db = rw
    # Стартовый номер у M-0001 уже закреплён (ДС пакета созданы → 409), а мастер-сделка на стенде одна. Здесь
    # проверяется не нумерация (у неё свои тесты), а то, что вид сохраняется ТЕМ ЖЕ запросом, — поэтому
    # `set_start_no` подменяется пустышкой. Без подмены тест уходил в пропуск, и главный путь оставался непроверенным.
    from app.master_deal import package as PK
    monkeypatch.setattr(PK, "set_start_no", lambda *a, **k: None)
    m = db.query(MasterDeal).order_by(MasterDeal.id).first()
    if m is None:
        pytest.skip("на стенде нет мастер-сделок")
    db.get(Contract, m.contract_id).annex_word = None
    db.flush()
    from app.models import User
    admin = db.query(User).join(User.role).filter_by(key="admin").first()
    no = (m.start_no or 0) + 1000                       # заведомо свободный номер, всё равно откатится
    master_start_no(m.code, StartNoIn(no=no, annex_word="приложение"), db=db, user=admin)
    db.expire_all()
    assert db.get(Contract, m.contract_id).annex_word == "приложение"


def test_panel_and_registry_know_the_contracts_kind(rw):
    """Панель сборки и реестр шаблонов показывают вид договора — данные для обоих приходят с сервера."""
    from app.master_deal.models import MasterDeal
    from app.models import Contract, User
    from app.routers.annex_templates import list_templates
    db = rw
    admin = db.query(User).join(User.role).filter_by(key="admin").first()
    custom = next((r for r in list_templates(db=db, user=admin)["items"] if r["scope"] == "custom"), None)
    if custom:
        db.get(Contract, custom["contract_id"]).annex_word = "дс"
        db.flush()
        r = next(x for x in list_templates(db=db, user=admin)["items"] if x["id"] == custom["id"])
        assert r["contract"]["annex_word"] == "дс"
    m = db.query(MasterDeal).order_by(MasterDeal.id).first()
    if m is None:
        return
    # Панель берёт договор из карточки мастер-сделки — ровно так, как её собирает ручка `GET /master-deals/{code}`.
    from app.master_deal import view as VW
    from app.routers.master_deals import _scope_all
    out = VW.card(db, m, admin, _scope_all(db, m, admin))
    assert "annex_word" in (out["contract"] or {}), "панель сборки не узнает вид договора"


# ── пересохранение шаблона: вид выбирается, если ещё не выбран (владелец 31.10.2026) ──

def _changed_blocks(db, t):
    """Текущие блоки шаблона с одним изменённым пунктом. Без изменения сервер отказывает «Изменений нет» — так и
    пересохраняют на деле: правят текст (например, слово документа на `{вид_документа}`)."""
    import copy
    from app.annex_tpl import service as S
    blocks = copy.deepcopy(S.current(db, t.id).blocks)
    b = next(x for x in blocks if not x.get("sys") and (x.get("text") or "").strip())
    b["text"] = b["text"].rstrip() + " Проверка пересохранения."
    return blocks


def _custom_template(db):
    from app.annex_tpl.models import AnnexTplTemplate
    t = db.query(AnnexTplTemplate).filter(AnnexTplTemplate.scope == "custom").order_by(AnnexTplTemplate.id).first()
    if t is None:
        pytest.skip("на стенде нет шаблонов договоров")
    return t


def test_template_detail_tells_whether_the_kind_is_chosen(rw):
    """Окно шаблона знает, выбран ли вид у договора, — чтобы спросить при пересохранении, только если не выбран."""
    from app.models import Contract, User
    from app.routers.annex_templates import one
    db = rw
    t = _custom_template(db)
    db.get(Contract, t.contract_id).annex_word = None
    db.flush()
    admin = db.query(User).join(User.role).filter_by(key="admin").first()
    assert "contract_annex_word" in one(t.id, db=db, user=admin)
    assert one(t.id, db=db, user=admin)["contract_annex_word"] is None


def test_resave_fixes_the_kind_when_not_yet_chosen(rw):
    """Пересохранение шаблона договора, у которого вид не выбран, — фиксирует вид тем же запросом."""
    from app.models import Contract
    from app.routers.annex_templates import BlocksIn, save
    db = rw
    t = _custom_template(db)
    db.get(Contract, t.contract_id).annex_word = None
    db.flush()
    save(t.id, BlocksIn(blocks=_changed_blocks(db, t), annex_word="дс"), db=db, user=_non_admin(db))
    db.expire_all()
    assert db.get(Contract, t.contract_id).annex_word == "дс", "вид не зафиксирован при пересохранении"


def test_resave_cannot_change_an_already_chosen_kind_without_admin(rw):
    """Тот же запрет, что везде: выбранный вид пересохранение шаблона не меняет у не-админа."""
    from app.models import Contract
    from app.routers.annex_templates import BlocksIn, save
    db = rw
    t = _custom_template(db)
    db.get(Contract, t.contract_id).annex_word = "дс"
    db.flush()
    with pytest.raises(HTTPException) as e:
        save(t.id, BlocksIn(blocks=_changed_blocks(db, t), annex_word="приложение"), db=db, user=_non_admin(db))
    assert e.value.status_code == 403
