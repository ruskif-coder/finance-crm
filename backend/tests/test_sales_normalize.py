r"""
Тесты нормализации значений из выгрузок/API Битрикс24.

Главный случай — ИНН приходит как float ("1673005251.0"). Наивная очистка
регуляркой \D даёт "16730052510" (лишний ноль) и молча нулевой матчинг
с counterparties. Проверено на реальном файле выгрузки, см.
docs/INTEGRATION_SPEC.md раздел 7.
"""
from app.sales.normalize import normalize_inn, normalize_name


def test_float_string_inn_drops_decimal_tail():
    assert normalize_inn("1673005251.0") == "1673005251"


def test_float_string_inn_is_not_stripped_by_naive_regex():
    # Регрессия: re.sub(r"\D", "", "1673005251.0") == "16730052510" — 11 цифр, мусор
    assert normalize_inn("1673005251.0") != "16730052510"


def test_real_float_type_inn():
    assert normalize_inn(1673005251.0) == "1673005251"


def test_plain_string_inn_unchanged():
    assert normalize_inn("7707083893") == "7707083893"


def test_twelve_digit_individual_inn():
    assert normalize_inn("500100732259") == "500100732259"


def test_inn_with_spaces_and_dashes():
    assert normalize_inn(" 7707-083-893 ") == "7707083893"


def test_scientific_notation_inn():
    assert normalize_inn("5.00100732259e+11") == "500100732259"


def test_wrong_length_rejected():
    assert normalize_inn("12345") is None


def test_empty_and_none_rejected():
    assert normalize_inn("") is None
    assert normalize_inn(None) is None
    assert normalize_inn("   ") is None


def test_non_numeric_rejected():
    assert normalize_inn("нет данных") is None


def test_normalize_name_collapses_spaces_and_case():
    assert normalize_name("  IN-APP  ") == "in-app"
    assert normalize_name("in  app") == "in app"


def test_normalize_name_handles_none():
    assert normalize_name(None) == ""
