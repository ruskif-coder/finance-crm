"""
Тесты классификации финансового отчёта (app/routers/finreport.py).

Здесь проверяется именно то, ради чего отчёт заведён отдельно от /reports/pl
(см. docs/АУДИТ_PL_2026-08-14.md): НДС не должен участвовать дважды, тело займа
не расход, налоги разложены по назначению платежа, а всё нераспознанное обязано
быть видимым, а не молча исчезать.

С 2026-08-18 отнесение статьи к строке отчёта берётся из справочника
(Article.pl_line, миграция 2026-08-18_article_pl_line.sql), а не из регулярок по
названию статьи. Поэтому первый аргумент classify — разметка, а не группа.
"""
from app.routers.finreport import (
    COGS,
    EXCLUDED,
    EX_LOAN,
    EX_VAT,
    FINANCE,
    MARKETING,
    OPEX,
    OTHER,
    PAYROLL_SUBGROUP,
    PROFIT_TAX,
    REVENUE,
    TAX_OTHER_SUBGROUP,
    TAX_PROFIT_SUBGROUP,
    UNCLASSIFIED,
    classify,
)


# ---- разметка справочника определяет строку ----

def test_revenue_line():
    line, sg, label = classify('revenue', 'Реклама', 'Медийка', None)
    assert line == REVENUE
    assert sg == 'Медийка'
    assert label == 'Реклама'


def test_cogs_and_marketing():
    assert classify('cogs', 'Закупка', '', None)[0] == COGS
    assert classify('marketing', 'Реклама себя', '', None)[0] == MARKETING


def test_payroll_is_operating_expense():
    """Ровно тот случай, ради которого всё затевалось.

    Раньше ФОТ попадал в операционные только потому, что его название ловила
    регулярка, а АВАНС и ПРЕМИЯ — те же деньги тех же людей — не ловились и
    висели в «Требует разметки». Теперь решает разметка, а не написание.
    """
    for name in ('ФОТ', 'АВАНС', 'ПРЕМИЯ', 'БОНУСЫ'):
        line, sg, _ = classify('opex', name, 'Сотрудники', None)
        assert (line, sg) == (OPEX, 'Сотрудники'), name


def test_unknown_group_no_longer_disappears():
    """Группы, которой нет ни в одном списке в коде, достаточно разметки.

    До правки /reports/pl сверял группу со списком PL_GROUPS_ORDER, и группы
    «Сотрудники» и «Офис» — 100,6 млн расходов — просто не выводились.
    """
    assert classify('opex', 'Аренда', 'Офис', None)[0] == OPEX


# ---- налоги: один раздел, две подстроки ----

def test_profit_and_other_taxes_share_one_section():
    line, sg, _ = classify('profit_tax', 'НАЛОГИ | Прибыль', '', None)
    assert (line, sg) == (PROFIT_TAX, TAX_PROFIT_SUBGROUP)
    line, sg, _ = classify('tax_other', 'НАЛОГИ | Пени', '', None)
    assert (line, sg) == (PROFIT_TAX, TAX_OTHER_SUBGROUP)


# ---- НДС: транзит, в P&L не место ----

def test_vat_article_excluded():
    line, reason, _ = classify('excluded', 'НАЛОГИ | НДС', '', None)
    assert line == EXCLUDED
    assert reason == EX_VAT


def test_vat_inside_single_tax_payment_excluded():
    line, reason, _ = classify('by_description', 'НАЛОГИ', '',
                               'Единый налоговый платеж (НДС за 3 квартал 2024)')
    assert line == EXCLUDED
    assert reason == EX_VAT


# ---- Займы: проценты — расход, тело — движение по балансу ----

def test_loan_principal_is_not_an_expense():
    line, reason, _ = classify('by_description', 'КРЕДИТЫ', '', 'ПОГАШЕНИЕ займа')
    assert line == EXCLUDED
    assert reason == EX_LOAN


def test_loan_receipt_also_excluded():
    # Симметрия обязательна: если убрать только возврат, приход раздует доходы.
    line, reason, _ = classify('by_description', 'КРЕДИТЫ', '', 'возврат ВКЛ')
    assert line == EXCLUDED
    assert reason == EX_LOAN


def test_loan_interest_is_finance_cost():
    assert classify('by_description', 'КРЕДИТЫ', '', 'проценты по займу')[0] == FINANCE
    assert classify('by_description', 'КРЕДИТЫ', '', '% ЗА КЕШ ДЕН ЗА 4 МЕСЯЦА')[0] == FINANCE


def test_loan_without_description_is_visible_not_dropped():
    line, _, label = classify('by_description', 'КРЕДИТЫ', '', None)
    assert line == UNCLASSIFIED
    assert 'не распознано' in label


# ---- Единый налоговый платёж разбирается по назначению ----

def test_profit_tax_from_description():
    line, sg, _ = classify('by_description', 'НАЛОГИ', '',
                           'Единый налоговый платеж (налог на прибыль)')
    assert (line, sg) == (PROFIT_TAX, TAX_PROFIT_SUBGROUP)


def test_ndfl_and_insurance_go_to_payroll():
    line, sg, _ = classify('by_description', 'НАЛОГИ', '', 'Единый налоговый платеж (НДФЛ)')
    assert (line, sg) == (OPEX, PAYROLL_SUBGROUP)
    line, sg, _ = classify('by_description', 'НАЛОГИ', '',
                           'Единый налоговый платеж (страховые взносы)')
    assert (line, sg) == (OPEX, PAYROLL_SUBGROUP)


def test_unmarked_single_tax_payment_is_visible():
    line, _, label = classify('by_description', 'НАЛОГИ', '', None)
    assert line == UNCLASSIFIED
    assert 'ЕНП' in label


# ---- ничего не теряется ----

def test_operation_without_article_is_visible():
    line, _, label = classify(None, None, None, None)
    assert line == UNCLASSIFIED
    assert label == 'Без статьи'


def test_article_without_markup_is_visible():
    """Новая статья, которую ещё не разметили, обязана быть видна.

    Это штатный сценарий: статью заводят в справочнике раньше, чем решают, куда
    её относить. Деньги по ней должны попасть в «Требует разметки», а не пропасть.
    """
    line, _, label = classify(None, 'Новая услуга', '', None)
    assert line == UNCLASSIFIED
    assert label == 'Новая услуга'


def test_unknown_markup_value_does_not_silently_vanish():
    # Опечатка в значении разметки — тоже повод показать деньги, а не потерять.
    assert classify('чтототакое', 'Статья', '', None)[0] == UNCLASSIFIED


# ---- Транзит: сам оборот не в P&L, но разница — расход ----

def test_transit_goes_to_other_expenses():
    line, _, label = classify('other', 'ТРАНЗИТ', '', None)
    assert line == OTHER
    assert 'разница' in label


def test_dividends_stay_out_of_pl():
    # Дивиденды — распределение прибыли, а не расход: в P&L им места нет.
    line, reason, _ = classify('excluded', 'ДИВИДЕНТЫ', '', None)
    assert line == EXCLUDED


# ---- отчёт обязан сходиться с оборотом ----

def test_every_line_key_is_known():
    """Каждое значение разметки должно вести в существующую строку отчёта.

    Опечатка в PL_LINE_MAP раньше означала бы тихую потерю денег: строка
    с неизвестным ключом не попала бы ни в один раздел и ни в один итог.
    """
    from app.routers.finreport import LINE_LABEL, PL_LINE_MAP
    for value, line in PL_LINE_MAP.items():
        assert line in LINE_LABEL or line == EXCLUDED, value
