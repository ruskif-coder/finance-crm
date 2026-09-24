"""
Раздел кассового P&L (/reports/pl) выводится из разметки статьи.

Ради чего тест: до 2026-08-18 раздел брался из Article.group и сверялся со списком
PL_GROUPS_ORDER. Группы, которой не было в списке, для отчёта не существовало —
«Сотрудники» (93,5 млн) и «Офис» (7,0 млн) не попадали в P&L, и ошибки при этом
не возникало. Любая новая группа в справочнике воспроизвела бы ту же тихую потерю.
"""
from app.routers.reports import (
    PL_GROUPS_ORDER,
    PL_LINE_TO_GROUP,
    TRANSIT_LABEL,
    UNMAPPED_GROUP,
    _collapse_transit,
    _pl_group,
)


def test_every_markup_value_lands_in_a_rendered_section():
    """Отображение обязано быть полным: у него нет варианта «не нашлось»."""
    for value, group in PL_LINE_TO_GROUP.items():
        assert group in PL_GROUPS_ORDER, value


def test_payroll_and_office_reach_the_report():
    assert _pl_group('opex', 'Сотрудники') == 'ОПЕРАЦИОННЫЕ'
    assert _pl_group('opex', 'Офис') == 'ОПЕРАЦИОННЫЕ'


def test_unknown_group_no_longer_decides_anything():
    # Группа справочника может быть какой угодно новой — раздел решает разметка.
    assert _pl_group('marketing', 'Придуманная завтра группа') == 'МАРКЕТИНГ'


def test_unmarked_article_is_visible_not_lost():
    assert _pl_group(None, 'ОПЕРАЦИОННЫЕ') == UNMAPPED_GROUP
    assert _pl_group('опечатка', None) == UNMAPPED_GROUP


def test_unmapped_section_is_rendered():
    # Иначе неразмеченное снова исчезнет — теперь уже по другой причине.
    assert UNMAPPED_GROUP in PL_GROUPS_ORDER


def test_taxes_share_one_section():
    assert _pl_group('profit_tax', None) == 'НАЛОГИ'
    assert _pl_group('tax_other', None) == 'НАЛОГИ'


# ---- транзит: в отчёт попадает только разница ----

def test_transit_is_collapsed_to_the_difference():
    """Полный оборот транзита раздувал обе стороны отчёта на десятки миллионов.

    Сквозные деньги не доход и не расход; расход здесь — только разница между
    списанием и поступлением. Так же считает /finreport, иначе отчёты разойдутся.
    """
    data = {'ОПЕРАЦИОННЫЕ': {'': {'ТРАНЗИТ': {'2026-01': {'income': 100, 'expense': 130}}}}}
    _collapse_transit(data)
    row = data['ОПЕРАЦИОННЫЕ']['']
    assert 'ТРАНЗИТ' not in row
    assert row[TRANSIT_LABEL]['2026-01'] == {'income': 0, 'expense': 30}


def test_transit_difference_may_be_negative():
    # В месяце, где поступило больше, чем списано. Обнулять нельзя: иначе годовая
    # сумма перестанет быть суммой месяцев.
    data = {'ОПЕРАЦИОННЫЕ': {'': {'ТРАНЗИТ': {'2026-02': {'income': 200, 'expense': 50}}}}}
    _collapse_transit(data)
    assert data['ОПЕРАЦИОННЫЕ'][''][TRANSIT_LABEL]['2026-02']['expense'] == -150


def test_collapse_leaves_other_articles_alone():
    data = {'ОПЕРАЦИОННЫЕ': {'': {'ФОТ': {'2026-01': {'income': 0, 'expense': 500}}}}}
    _collapse_transit(data)
    assert data['ОПЕРАЦИОННЫЕ']['']['ФОТ']['2026-01']['expense'] == 500


def test_by_description_falls_back_to_directory_group():
    """ЕНП и кредиты здесь разложить нечем — текст платежа уже потерян в группировке."""
    assert _pl_group('by_description', 'НАЛОГИ') == 'НАЛОГИ'
    assert _pl_group('by_description', 'ОПЕРАЦИОННЫЕ') == 'ОПЕРАЦИОННЫЕ'


# ---- тело займа — вне P&L во всех отчётах (аудит 23.09.2026, 2.M4) ----

def test_loan_body_is_outside_pl():
    """Финотчёт исключал тело займа, а /pl и /plan-fact отправляли его в «Требует
    разметки»: погашение вычиталось из прибыли, получение не было видно."""
    assert _pl_group('loan_body', 'КРЕДИТЫ') == 'НЕ В P&L'


def test_every_markup_the_directory_offers_has_a_section():
    """Ратчет: значение, которое можно выбрать в справочнике статей, обязано иметь
    раздел здесь. `loan_body` было выбираемым и не имело — отсюда 2.M4."""
    from app.routers.articles import PL_LINE_VALUES
    missing = PL_LINE_VALUES - set(PL_LINE_TO_GROUP) - {'by_description'}
    assert not missing, f"разметка без раздела в /pl: {missing}"
