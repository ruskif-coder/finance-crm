# -*- coding: utf-8 -*-
"""Сборка приложения: номер, дата, стороны, подстановки.

Три правила, каждое из которых ошибается молча и вылезает у клиента на подписании:
нумерация внутри договора со стартом от выданных вне системы, дата как последний день
предыдущего месяца и полнота реквизитов.
"""
from datetime import date
from types import SimpleNamespace

import pytest

import app.launch_prep.models  # noqa: F401
import app.ord.models          # noqa: F401
from app.database import SessionLocal
from app.models import Contract, Counterparty
from app.sales import annex
from app.sales.models import AnnexTemplate, SalesAnnex


@pytest.fixture
def db():
    d = SessionLocal()
    yield d
    d.rollback()
    d.close()


# ── дата ─────────────────────────────────────────────────────────────────────

def test_date_is_the_last_day_of_the_previous_month():
    """Правило владельца 05.09.2026. Февраль и январь — там, где ошибаются."""
    assert annex.annex_date(date(2026, 6, 1)) == date(2026, 5, 31)
    assert annex.annex_date(date(2026, 6, 17)) == date(2026, 5, 31)   # день внутри месяца не важен
    assert annex.annex_date(date(2026, 1, 1)) == date(2025, 12, 31)   # переход через год
    assert annex.annex_date(date(2026, 3, 1)) == date(2026, 2, 28)
    assert annex.annex_date(date(2024, 3, 1)) == date(2024, 2, 29)    # високосный


# ── номер ────────────────────────────────────────────────────────────────────

def test_next_number_starts_from_what_was_issued_outside(db):
    """У «Уайт Бокс Медиа» приложения дошли до 73 вне системы. Первое наше обязано быть
    74-м, а не первым: иначе клиент получит номер, который у него уже есть."""
    c = db.query(Contract).order_by(Contract.id).first()
    if not c:
        pytest.skip('нужен хотя бы один договор')
    was = c.annex_start_no
    try:
        c.annex_start_no = 73
        db.flush()
        assert annex.next_no(db, c) == 74
        c.annex_start_no = None
        db.flush()
        assert annex.next_no(db, c) == 1
    finally:
        c.annex_start_no = was
        db.rollback()


def test_our_own_numbers_win_when_they_are_higher(db):
    """Стартовый ставят один раз, дальше считают наши. Взять только старт означало бы
    выдавать один и тот же номер каждому следующему приложению."""
    c = db.query(Contract).order_by(Contract.id).first()
    if not c:
        pytest.skip('нужен хотя бы один договор')
    try:
        c.annex_start_no = 10
        db.add(SalesAnnex(contract_id=c.id, no=12, number="Приложение № 12"))
        db.flush()
        assert annex.next_no(db, c) == 13
    finally:
        db.rollback()


def test_number_hint_ignores_garbage_from_old_operations(db):
    """В `operations.ds_num` лежит свободный текст, и среди чисел есть мусор — у одного
    контрагента «590425». Подсказка обязана его отсекать, иначе следующий номер уедет
    в шестизначные."""
    assert annex.HINT_MAX < 590425
    c = (db.query(Contract).filter(Contract.counterparty_id.isnot(None))
         .order_by(Contract.id).first())
    if not c:
        pytest.skip('нужен договор с контрагентом')
    hint = annex.no_hint(db, c)
    assert hint is None or hint <= annex.HINT_MAX


# ── стороны ──────────────────────────────────────────────────────────────────

def test_missing_requisites_are_named_not_silently_blank(db):
    """Документ с пустым местом на месте директора подпишут не глядя. Поэтому недостающее
    перечисляется поимённо, а не оставляется пустой строкой."""
    empty = Counterparty(name="Пустой контрагент")
    out = annex.party(empty)
    assert set(out["missing"]) == {"ИНН", "ФИО подписанта", "должность подписанта",
                                   "основание полномочий"}
    assert annex.party(None)["missing"]


def test_signature_form_is_surname_with_initials():
    """В подписи документа стоит «Макаров Д.С.», а не полное ФИО."""
    assert annex.short_fio("Макаров Денис Сергеевич") == "Макаров Д.С."
    assert annex.short_fio("Кинчиков Павел Сергеевич") == "Кинчиков П.С."
    assert annex.short_fio("Иванов") == "Иванов"
    assert annex.short_fio("") is None


# ── шаблон и сборка ──────────────────────────────────────────────────────────

def test_payer_template_wins_over_the_default(db):
    """Шаблон привязан к ПЛАТЕЛЬЩИКУ: подписывает и платит он, у него и свои формулировки."""
    payer = db.query(Counterparty).filter(Counterparty.is_own_company.is_(False)).first()
    if not payer:
        pytest.skip('нужен контрагент')
    try:
        own = AnnexTemplate(payer_id=payer.id, name="Свой", body="СВОЙ {бренд}")
        db.add(own)
        db.flush()
        assert annex.pick_template(db, payer.id).id == own.id
        # У чужого плательщика — типовой, если он заведён.
        other = annex.pick_template(db, None)
        assert other is None or other.payer_id is None
    finally:
        db.rollback()


def test_unknown_placeholder_stays_visible():
    """Незакрытая подстановка остаётся текстом: видимая дыра лучше молча пустого места —
    человек заметит её при проверке."""
    tpl = SimpleNamespace(body="Бренд {бренд}, а тут {неизвестно}")
    out = annex.render_body(tpl, {"бренд": "Мезим"})
    assert out == "Бренд Мезим, а тут {неизвестно}"


def test_build_reproduces_the_sample_document(db):
    """Числа из живого образца «Приложение № 68»: 732 000 при ставке 22 % дают НДС
    ровно 132 000, и обе суммы прописью совпадают с подписанным документом."""
    c = (db.query(Contract).filter(Contract.counterparty_id.isnot(None))
         .order_by(Contract.id).first())
    if not c:
        pytest.skip('нужен договор с контрагентом')
    d = annex.build(db, c, period_from=date(2026, 6, 1), period_to=date(2026, 6, 30),
                    amount=732000, brand="Мезим / Mezym")
    assert d["date"] == date(2026, 5, 31)
    assert d["vat"] == 132000.0
    assert d["amount_words"].endswith("(Семьсот тридцать две тысячи) рублей 00 копеек")
    assert d["vat_words"].endswith("(Сто тридцать две тысячи) рублей 00 копеек")
    assert d["number"] == f"Приложение № {d['no']}"
    # Сборка НИЧЕГО не пишет: номер занимается только при подтверждении.
    assert db.query(SalesAnnex).filter(SalesAnnex.contract_id == c.id).count() == 0


# ── бренд ────────────────────────────────────────────────────────────────────

def test_brand_is_taken_from_the_deals_when_not_passed(db):
    """До 05.09.2026 в документе стояло «материалов бренда: «»» — `build` звали без
    `brand`, и подстановка молча схлопывалась в пустые кавычки. Пустое место в
    подписанном документе замечает клиент, а не мы."""
    from app.sales.models import SalesDeal
    d = (db.query(SalesDeal).filter(SalesDeal.advertiser_id.isnot(None))
         .order_by(SalesDeal.id).first())
    if not d:
        pytest.skip('нужна сделка с рекламодателем')
    assert annex.deal_brand(db, [d.id])
    assert annex.deal_brand(db, []) is None


def test_brand_and_advertiser_are_written_as_a_pair_without_repeating(db):
    """Рекламодатель и бренд идут парой через « / », как в образце. У половины
    рекламодателей бренд назван так же — тогда пара схлопывается, иначе в документе
    стояло бы «Ромашка / Ромашка»."""
    from sqlalchemy import text as sa_text
    row = db.execute(sa_text("""
        SELECT d.id, COALESCE(NULLIF(btrim(a.short_name), ''), a.name) AS adv, b.name AS brand
          FROM sales_deals d
          JOIN sales_advertisers a ON a.id = d.advertiser_id
          JOIN sales_brands b ON b.id = d.brand_id
         WHERE lower(btrim(a.short_name)) <> lower(btrim(b.name))
         ORDER BY d.id LIMIT 1
    """)).mappings().first()
    if not row:
        pytest.skip('нужна сделка, где бренд и рекламодатель названы по-разному')
    assert annex.deal_brand(db, [row["id"]]) == f'{row["adv"]} / {row["brand"]}'
    same = db.execute(sa_text("""
        SELECT d.id FROM sales_deals d
          JOIN sales_advertisers a ON a.id = d.advertiser_id
          JOIN sales_brands b ON b.id = d.brand_id
         WHERE lower(btrim(a.short_name)) = lower(btrim(b.name))
         ORDER BY d.id LIMIT 1
    """)).mappings().first()
    if same:
        assert ' / ' not in (annex.deal_brand(db, [same["id"]]) or '')


def test_brand_reaches_the_document_text(db):
    """Проверяется не контекст, а сам текст: подстановка могла не дойти до шаблона."""
    from app.sales.models import SalesDeal
    c = (db.query(Contract).filter(Contract.counterparty_id.isnot(None))
         .order_by(Contract.id).first())
    d = (db.query(SalesDeal).filter(SalesDeal.advertiser_id.isnot(None))
         .order_by(SalesDeal.id).first())
    if not c or not d:
        pytest.skip('нужны договор с контрагентом и сделка с рекламодателем')
    out = annex.build(db, c, period_from=date(2026, 6, 1), period_to=date(2026, 6, 30),
                      amount=732000, deal_ids=[d.id])
    assert out["brand"]
    if out["body"]:
        assert out["brand"] in out["body"], 'бренд не дошёл до текста формулировки'
    assert 'бренд/рекламодатель' not in out["missing"]


# ── поля документа из справочника услуг ──────────────────────────────────────

def test_position_text_and_rotation_come_from_the_service_directory(db):
    """Решение владельца 05.09.2026: текстовка позиции и тип ротации задаются у УСЛУГИ.
    Одна услуга продаётся одинаково, и держать этот абзац в каждой строке медиаплана
    значило бы переписывать его при каждой сборке.

    Проверяется не колонка в базе, а то, что значение доходит до строки документа: между
    услугой и строкой плана стоит соединение по имени, и оно уже расходилось."""
    from sqlalchemy import text as sa_text
    from app.sales.models import SalesService
    row = db.execute(sa_text("""
        SELECT mp.deal_id, r.position
          FROM sales_media_plan_rows r
          JOIN sales_media_plans mp ON mp.id = r.plan_id
          JOIN sales_services s ON lower(btrim(s.name)) = lower(btrim(r.position))
         WHERE mp.status <> 'rejected'
         ORDER BY mp.deal_id LIMIT 1
    """)).mappings().first()
    if not row:
        pytest.skip('нужна строка медиаплана, чья услуга есть в справочнике')
    svc = db.query(SalesService).filter(SalesService.name == row["position"]).first()
    was = (svc.doc_position, svc.rotation_type)
    try:
        svc.doc_position = "Описание позиции для документа"
        svc.rotation_type = "Динамика"
        db.flush()
        out = [r for r in annex.plan_rows(db, [row["deal_id"]])
               if r["position"] == row["position"]]
        assert out and out[0]["doc_position"] == "Описание позиции для документа"
        assert out[0]["rotation"] == "Динамика"
        # Незаполненное отдаётся пустым, а не выдумывается: пустая ячейка видна при
        # вычитке, придуманная формулировка — нет.
        svc.doc_position, svc.rotation_type = None, None
        db.flush()
        out = [r for r in annex.plan_rows(db, [row["deal_id"]])
               if r["position"] == row["position"]]
        assert out[0]["doc_position"] is None and out[0]["rotation"] is None
    finally:
        svc.doc_position, svc.rotation_type = was
        db.rollback()


def test_rotation_type_is_a_closed_list(db):
    """Свободный текст дал бы «Динамика», «динамика» и «динамическая» в одной колонке
    документа."""
    from fastapi import HTTPException
    from app.routers.sales_directories import ROTATION_TYPES, _set_service_fields
    from types import SimpleNamespace
    assert ROTATION_TYPES == ("Динамика", "Статика")
    svc = SimpleNamespace()
    data = SimpleNamespace(color=None, placement_type=None, calc_form=None,
                           separate_price=False, unit_price=None, unit_price_web=None,
                           unit_price_app=None, constants=None, revenue_article_id=None,
                           doc_position=None, rotation_type="динамическая")
    with pytest.raises(HTTPException) as e:
        _set_service_fields(svc, data)
    assert e.value.status_code == 400


# ── НДС: две разные формулы ──────────────────────────────────────────────────

def test_row_vat_is_charged_while_document_vat_is_extracted(db):
    """Две операции с НДС, которые легко спутать, и разница — 22/100 против 22/122.

    · Строка медиаплана хранит стоимость БЕЗ налога (объём × цена ÷ 1000 со скидкой),
      значит налог НАЧИСЛЯЕТСЯ: 500 000,20 × 22 % = 110 000,04, с НДС 610 000,24.
    · Сумма приложения в тексте — С налогом, значит налог ИЗВЛЕКАЕТСЯ: из 610 000,24
      выходит 110 000,04, а не 22 % сверху.

    06.09.2026 в строках стояло извлечение вместо начисления: НДС выходил 90 163,97, и
    таблица переставала сходиться с суммой сделки при верных данных. Проверять надо обе
    формулы разом — по отдельности каждая выглядит правильной.
    """
    c = (db.query(Contract).filter(Contract.counterparty_id.isnot(None))
         .order_by(Contract.id).first())
    if not c:
        pytest.skip('нужен договор с контрагентом')
    net, rate = 500000.20, 22
    assert round(net * rate / 100, 2) == 110000.04        # начисление на строку
    assert annex.vat_of(610000.24, rate) == 110000.04     # извлечение из суммы с НДС
    assert annex.vat_of(net, rate) != round(net * rate / 100, 2), \
        'формулы обязаны различаться — иначе их и правда можно путать'


def test_plan_total_equals_the_sum_of_row_gross(db):
    """Сумма приложения — по МЕДИАПЛАНУ (владелец 06.09.2026). Значит она равна сумме
    строк с НДС, а не берётся из сделки: иначе в тексте одно число, в таблице другое,
    и это видит подписант."""
    from app.sales.models import SalesDeal
    c = (db.query(Contract).filter(Contract.counterparty_id.isnot(None))
         .order_by(Contract.id).first())
    d = (db.query(SalesDeal).join(
            __import__("app.sales.models", fromlist=["SalesMediaPlan"]).SalesMediaPlan,
            __import__("app.sales.models", fromlist=["SalesMediaPlan"]).SalesMediaPlan.deal_id == SalesDeal.id)
         .order_by(SalesDeal.id).first())
    if not c or not d:
        pytest.skip('нужны договор и сделка с медиапланом')
    out = annex.build(db, c, period_from=date(2026, 6, 1), period_to=date(2026, 6, 30),
                      amount=1, deal_ids=[d.id])
    if not out["rows"]:
        pytest.skip('у сделки нет строк медиаплана')
    assert out["plan_total"] == round(sum(r["gross"] or 0 for r in out["rows"]), 2)
    for r in out["rows"]:
        if r["amount"]:
            assert round(r["amount"] + r["vat"], 2) == r["gross"], 'строка не сходится сама с собой'


def test_amount_that_disagrees_with_the_plan_is_named(db):
    """Приложение выпускается на этапе сборки, когда план зафиксирован, — расхождению
    взяться неоткуда. Если оно всё же есть, план правили после сборки, и печатать нельзя:
    в тексте одна сумма, в таблице другая."""
    from app.sales.models import SalesDeal, SalesMediaPlan
    c = (db.query(Contract).filter(Contract.counterparty_id.isnot(None))
         .order_by(Contract.id).first())
    d = (db.query(SalesDeal).join(SalesMediaPlan, SalesMediaPlan.deal_id == SalesDeal.id)
         .order_by(SalesDeal.id).first())
    if not c or not d:
        pytest.skip('нужны договор и сделка с медиапланом')
    out = annex.build(db, c, period_from=date(2026, 6, 1), period_to=date(2026, 6, 30),
                      amount=1, deal_ids=[d.id])
    if out["plan_total"] is None:
        pytest.skip('у сделки нет строк медиаплана')
    assert any("медиаплан" in m for m in out["missing"]), 'расхождение обязано быть названо'
    ok = annex.build(db, c, period_from=date(2026, 6, 1), period_to=date(2026, 6, 30),
                     amount=out["plan_total"], deal_ids=[d.id])
    assert not any("медиаплан" in m for m in ok["missing"])


def test_document_vat_equals_the_sum_of_row_vat(db):
    """Ревью 06.09.2026: при 2+ строках ИТОГО НДС в таблице расходился с НДС в пункте 1.1
    на копейку — таблица складывала построчные round(net×22/100), а текст извлекал налог
    из общей суммы. Обе цифры печатаются в ОДНОМ подписанном документе.

    Проверяется само отношение, а не конкретные числа: НДС документа обязан быть суммой
    построчных, когда строки есть.
    """
    from app.sales.models import SalesDeal, SalesMediaPlan
    c = (db.query(Contract).filter(Contract.counterparty_id.isnot(None))
         .order_by(Contract.id).first())
    d = (db.query(SalesDeal).join(SalesMediaPlan, SalesMediaPlan.deal_id == SalesDeal.id)
         .order_by(SalesDeal.id).first())
    if not c or not d:
        pytest.skip('нужны договор и сделка с медиапланом')
    out = annex.build(db, c, period_from=date(2026, 6, 1), period_to=date(2026, 6, 30),
                      amount=1, deal_ids=[d.id])
    if not out["rows"]:
        pytest.skip('у сделки нет строк медиаплана')
    assert out["vat"] == round(sum(r["vat"] or 0 for r in out["rows"]), 2)
    # И без строк формула прежняя: извлечение из суммы с НДС.
    plain = annex.build(db, c, period_from=date(2026, 6, 1), period_to=date(2026, 6, 30),
                        amount=732000)
    assert plain["vat"] == annex.vat_of(732000, plain["vat_rate"])


def test_rounding_does_not_split_the_totals_on_many_rows(db):
    """Копеечное расхождение вылезает только на нескольких строках, поэтому проверяем
    арифметику напрямую: сумма построчных НДС и извлечение из общей суммы РАСХОДЯТСЯ, и
    документ обязан печатать первое."""
    rate, nets = 22, [500000.20, 333333.37, 111111.11]
    by_rows = round(sum(round(n * rate / 100, 2) for n in nets), 2)
    gross = round(sum(round(n * (100 + rate) / 100, 2) for n in nets), 2)
    assert by_rows != annex.vat_of(gross, rate), \
        'если формулы совпали — тест устарел, но правило остаётся: печатаем сумму строк'
