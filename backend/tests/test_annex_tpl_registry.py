# -*- coding: utf-8 -*-
"""Реестр шаблонов ДС — вкладка «Справочники → Приложения → Шаблоны» (хендофф «шаблоны дс», 31.10.2026).

Одна строка — один шаблон. Макет требует на строке: юрлицо и ИНН, договор, бренд, сколько пунктов,
сколько ДС собрано по шаблону и когда последний, кто создал и кто правил. Всё это выводится из уже
существующих данных — новой схемы нет.

**Бренд — это память «договор + бренд → шаблон»** (`annex_tpl_brand_memory`, решение владельца 27.10.2026):
та же таблица, по которой сборка подставляет шаблон в следующий ДС бренда. Макет её показывает и
даёт задать явно при создании шаблона. Отдельной колонки «бренд шаблона» не заводим: это было бы
второе мнение о том же и разошлось бы с тем, что реально подставит сборка.

Тесты не коммитят: `commit` подменён на `flush`, и фикстура при закрытии сессии всё откатывает. Стенд
сейчас — копия прода, и шаблоны, созданные тестом, остались бы в живом реестре.
"""
import pytest
from sqlalchemy import text

from app.models import User


@pytest.fixture
def ctx(db, monkeypatch):
    """Договор, у которого можно создать шаблон (есть формат с базовым шаблоном) и есть бренды."""
    monkeypatch.setattr(db, "commit", db.flush)       # ничего не оседает в базе стенда
    row = db.execute(text("""
        SELECT k.id AS contract_id, d.brand_id
          FROM contracts k
          JOIN annex_tpl_formats f ON f.format = k.cooperation_format
          JOIN sales_deals d ON coalesce(d.payer_counterparty_id, d.counterparty_id) = k.counterparty_id
         WHERE k.counterparty_id IS NOT NULL AND d.brand_id IS NOT NULL
         ORDER BY k.id LIMIT 1""")).first()
    if row is None:
        pytest.skip("на стенде нет договора с форматом и брендами — проверить не на чем")
    user = db.query(User).order_by(User.id).first()
    return db, row.contract_id, row.brand_id, user


def _fork(db, user, contract_id, title, brand_id=None):
    from app.routers.annex_templates import ForkIn, fork
    return fork(ForkIn(contract_id=contract_id, title=title, brand_id=brand_id), db=db, user=user)


def _row_of(db, user, template_id):
    from app.routers.annex_templates import list_templates
    return next(r for r in list_templates(db=db, user=user)["items"] if r["id"] == template_id)


def test_registry_row_carries_what_the_design_needs(ctx):
    """Строка реестра несёт всё, что рисует макет, — без похода за данными с экрана."""
    db, contract_id, _brand, user = ctx
    t = _fork(db, user, contract_id, "Проверка реестра 31-10")
    r = _row_of(db, user, t["id"])

    k = db.execute(text("SELECT contract_number FROM contracts WHERE id = :c"), {"c": contract_id}).scalar()
    # Ключами, а не всем словарём: в договоре строки ещё вид документа и последний номер (31.10.2026).
    assert r["contract"]["id"] == contract_id and r["contract"]["no"] == k
    assert r["entity"] and r["entity"]["id"] and r["entity"]["name"] and "inn" in r["entity"]
    assert isinstance(r["items"], int) and r["items"] > 0, "пунктов в шаблоне"
    assert r["ds_count"] == 0 and r["ds_last_at"] is None, "по новому шаблону ДС ещё не собирали"
    assert r["brands"] == [], "без бренда — «все бренды договора»"
    assert r["created_by_name"], "кто создал — именем, а не номером учётки"


def test_a_brand_given_at_creation_lands_in_brand_memory(ctx):
    """Бренд при создании шаблона пишется в ту же память, по которой сборка подставит шаблон.

    Иначе реестр показывал бы привязку, которой сборка не знает, — и следующий ДС бренда ушёл бы
    по другому шаблону.
    """
    db, contract_id, brand_id, user = ctx
    t = _fork(db, user, contract_id, "Проверка бренда 31-10", brand_id=brand_id)
    got = db.execute(text("SELECT template_id FROM annex_tpl_brand_memory "
                          "WHERE contract_id = :c AND brand_id = :b"), {"c": contract_id, "b": brand_id}).scalar()
    assert got == t["id"], "память «договор + бренд → шаблон» не указывает на новый шаблон"
    name = db.execute(text("SELECT name FROM sales_brands WHERE id = :b"), {"b": brand_id}).scalar()
    assert _row_of(db, user, t["id"])["brands"] == [name]


def test_ds_count_and_last_date_come_from_annexes_built_on_the_template(ctx):
    """«ДС по шаблону» и дата последнего — по `sales_annexes.tpl_template_id`."""
    db, contract_id, _brand, user = ctx
    t = _fork(db, user, contract_id, "Проверка счётчика ДС 31-10")
    a = db.execute(text("SELECT id, date FROM sales_annexes WHERE date IS NOT NULL ORDER BY id LIMIT 1")).first()
    if a is None:
        pytest.skip("на стенде нет ни одного ДС")
    db.execute(text("UPDATE sales_annexes SET tpl_template_id = :t WHERE id = :a"), {"t": t["id"], "a": a.id})
    db.flush()
    r = _row_of(db, user, t["id"])
    assert r["ds_count"] == 1
    assert str(r["ds_last_at"])[:10] == a.date.isoformat()


def test_brand_options_are_the_brands_of_the_contracts_payer(ctx):
    """Бренды для выбора в «Новом шаблоне» — бренды сделок плательщика по договору."""
    from app.routers.annex_templates import contract_brands
    db, contract_id, brand_id, user = ctx
    ids = {b["id"] for b in contract_brands(contract_id, db=db, user=user)}
    assert brand_id in ids


def test_registry_shows_the_last_number_the_next_annex_will_follow(ctx):
    """Последний порядковый номер ДС по договору (владелец 31.10.2026) — наибольший из ВСЕХ источников.

    У договора два независимых счётчика: одиночные ДС нумеруются от «ДС с» договора и выданных (`next_no`), а мастер-
    сделка хранит свой `start_no` и в договор его не пишет (`package.set_start_no`). Замер 31.10: у M-0001 в мастер-
    сделке № 44, у договора «ДС с» пусто. Первая редакция брала только `next_no` и показала бы «номеров нет» вместо 44.
    """
    from app.master_deal.models import MasterDeal
    from app.models import Contract
    from app.sales.annex import next_no
    db, contract_id, _brand, user = ctx
    t = _fork(db, user, contract_id, "Проверка номера 31-10")
    c = db.get(Contract, contract_id)
    # мастер-сделка с номером больше договорного — в рамках отката
    m = db.query(MasterDeal).order_by(MasterDeal.id).first()
    if m is None:
        pytest.skip("на стенде нет мастер-сделок")
    big = next_no(db, c) + 500
    was = (m.contract_id, m.start_no)
    m.contract_id, m.start_no = contract_id, big
    db.flush()
    r = _row_of(db, user, t["id"])
    assert r["contract"]["last_no"] == big, "номер мастер-сделки не учтён — реестр разошёлся бы с её панелью"
    assert r["contract"]["last_no_source"] == "в мастер-сделке"
    m.contract_id, m.start_no = was
    db.flush()


def test_a_brand_outside_the_contract_is_refused_with_a_reason(ctx):
    """Бренд, которого нет среди брендов договора (или нет вовсе), — 400 с объяснением, а не 500 на внешнем
    ключе памяти брендов (ревью 31.10.2026). Список допустимых — тот же, что предлагает окно «Новый шаблон»."""
    from fastapi import HTTPException
    db, contract_id, _brand, user = ctx
    missing = (db.execute(text("SELECT coalesce(max(id), 0) + 1000 FROM sales_brands")).scalar())
    with pytest.raises(HTTPException) as e:
        _fork(db, user, contract_id, "Проверка чужого бренда 31-10", brand_id=missing)
    assert e.value.status_code == 400 and "бренд" in str(e.value.detail).lower()
