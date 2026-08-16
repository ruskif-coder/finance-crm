"""
Тесты классификации финансового отчёта (app/routers/finreport.py).

Здесь проверяется именно то, ради чего отчёт заведён отдельно от /reports/pl
(см. docs/АУДИТ_PL_2026-08-14.md): НДС не должен участвовать дважды, тело займа
не расход, налоги разложены по назначению платежа, а всё нераспознанное обязано
быть видимым, а не молча исчезать.
"""
from app.routers.finreport import (
    COGS,
    EXCLUDED,
    EX_LOAN,
    EX_VAT,
    FINANCE,
    MARKETING,
    OPEX,
    PAYROLL_SUBGROUP,
    PROFIT_TAX,
    REVENUE,
    UNCLASSIFIED,
    classify,
)


# ---- обычные группы проходят как есть ----

def test_revenue_group():
    line, sg, label = classify('ВЫРУЧКА', 'Реклама', 'Медийка', None)
    assert line == REVENUE
    assert sg == 'Медийка'
    assert label == 'Реклама'


def test_cogs_and_marketing():
    assert classify('СЕБЕСТОИМОСТЬ', 'Закупка', '', None)[0] == COGS
    assert classify('МАРКЕТИНГ', 'Реклама себя', '', None)[0] == MARKETING


def test_group_excluded_from_pl():
    # ТРАНЗИТ здесь не подходит как пример: он в этой же группе, но его разница
    # между списанием и поступлением как раз попадает в расходы (см. ниже).
    line, reason, _ = classify('НЕ В P&L', 'ПРОЧЕЕ', '', None)
    assert line == EXCLUDED


# ---- НДС: транзит, в P&L не место ----

def test_vat_article_excluded():
    line, reason, _ = classify('НАЛОГИ', 'НАЛОГИ | НДС', '', None)
    assert line == EXCLUDED
    assert reason == EX_VAT


def test_vat_inside_single_tax_payment_excluded():
    line, reason, _ = classify('НАЛОГИ', 'НАЛОГИ', '',
                               'Единый налоговый платеж (НДС за 3 квартал 2024)')
    assert line == EXCLUDED
    assert reason == EX_VAT


# ---- Займы: проценты — расход, тело — движение по балансу ----

def test_loan_principal_is_not_an_expense():
    line, reason, _ = classify('ОПЕРАЦИОННЫЕ', 'КРЕДИТЫ', '', 'ПОГАШЕНИЕ займа')
    assert line == EXCLUDED
    assert reason == EX_LOAN


def test_loan_receipt_also_excluded():
    # Симметрия обязательна: если убрать только возврат, приход раздует доходы.
    line, reason, _ = classify('ОПЕРАЦИОННЫЕ', 'КРЕДИТЫ', '', 'возврат ВКЛ')
    assert line == EXCLUDED
    assert reason == EX_LOAN


def test_loan_interest_is_finance_cost():
    assert classify('ОПЕРАЦИОННЫЕ', 'КРЕДИТЫ', '', 'проценты по займу')[0] == FINANCE
    assert classify('ОПЕРАЦИОННЫЕ', 'КРЕДИТЫ', '', '% ЗА КЕШ ДЕН ЗА 4 МЕСЯЦА')[0] == FINANCE


def test_loan_without_description_is_visible_not_dropped():
    line, _, label = classify('ОПЕРАЦИОННЫЕ', 'КРЕДИТЫ', '', None)
    assert line == UNCLASSIFIED
    assert 'не распознано' in label


# ---- Единый налоговый платёж разбирается по назначению ----

def test_profit_tax_from_description():
    assert classify('НАЛОГИ', 'НАЛОГИ', '',
                    'Единый налоговый платеж (налог на прибыль)')[0] == PROFIT_TAX


def test_ndfl_and_insurance_go_to_payroll():
    line, sg, _ = classify('НАЛОГИ', 'НАЛОГИ', '', 'Единый налоговый платеж (НДФЛ)')
    assert (line, sg) == (OPEX, PAYROLL_SUBGROUP)
    line, sg, _ = classify('НАЛОГИ', 'НАЛОГИ', '',
                           'Единый налоговый платеж (страховые взносы)')
    assert (line, sg) == (OPEX, PAYROLL_SUBGROUP)


def test_ndfl_article_goes_to_payroll():
    line, sg, _ = classify('ОПЕРАЦИОННЫЕ', 'НАЛОГИ | НДФЛ', 'Сотрудники', None)
    assert (line, sg) == (OPEX, PAYROLL_SUBGROUP)


def test_unmarked_single_tax_payment_is_visible():
    line, _, label = classify('НАЛОГИ', 'НАЛОГИ', '', None)
    assert line == UNCLASSIFIED
    assert 'ЕНП' in label


# ---- ничего не теряется ----

def test_operation_without_article_is_visible():
    line, _, label = classify(None, None, None, None)
    assert line == UNCLASSIFIED
    assert label == 'Без статьи'


# ---- Транзит: сам оборот не в P&L, но разница — расход ----

def test_transit_goes_to_other_expenses():
    from app.routers.finreport import OTHER
    line, _, label = classify('НЕ В P&L', 'ТРАНЗИТ', '', None)
    assert line == OTHER
    assert 'разница' in label


def test_dividends_stay_out_of_pl():
    # Дивиденды — распределение прибыли, а не расход: в P&L им места нет.
    line, reason, _ = classify('НЕ В P&L', 'ДИВИДЕНТЫ', '', None)
    assert line == EXCLUDED
