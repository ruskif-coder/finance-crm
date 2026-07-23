"""
Тесты маппинга (воронка, стадия Битрикса) → слой денег.

Ключ — пара, а не стадия: в текущем VBA (GetCWValue_Fast в modFillinClearData)
у воронок «Общая», «Pharm», «ДО», «Other» разные названия стадий, ведущие
в один слой. Названия содержат имена сотрудников, поэтому маппинг хранится
данными и сравнивается литерально.
"""
from types import SimpleNamespace
from app.sales.stages import MONEY_LAYERS, build_stage_index, resolve_money_layer


def _row(pipeline, bitrix_stage, money_layer):
    return SimpleNamespace(pipeline=pipeline, bitrix_stage=bitrix_stage, money_layer=money_layer)


ROWS = [
    _row("Общая", "Подготовка МП", "планируемые"),
    _row("Общая", "Медиаплан отправлен", "планируемые"),
    _row("Общая", "Бронь подтверждена", "планируемые"),
    _row("Pharm", "Готовятся к старту (траффик)", "реализуемые"),
    _row("Pharm", "В размещении", "реализуемые"),
    _row("ДО", "Согласование ДС", "фактические"),
    _row("ДО", "Архив", "фактические"),
]


def test_three_money_layers_exactly():
    assert MONEY_LAYERS == ("планируемые", "реализуемые", "фактические")


def test_resolves_known_pair():
    idx = build_stage_index(ROWS)
    assert resolve_money_layer(idx, "Общая", "Подготовка МП") == "планируемые"


def test_same_stage_name_different_pipeline_is_independent():
    rows = ROWS + [_row("Other", "В размещении", "фактические")]
    idx = build_stage_index(rows)
    assert resolve_money_layer(idx, "Pharm", "В размещении") == "реализуемые"
    assert resolve_money_layer(idx, "Other", "В размещении") == "фактические"


def test_unknown_pair_returns_none():
    idx = build_stage_index(ROWS)
    assert resolve_money_layer(idx, "Общая", "Неизвестная стадия") is None
    assert resolve_money_layer(idx, "Неизвестная воронка", "Архив") is None


def test_matching_tolerates_case_and_spacing():
    idx = build_stage_index(ROWS)
    assert resolve_money_layer(idx, "общая", "  подготовка   мп ") == "планируемые"


def test_stage_with_employee_name_matches_literally():
    rows = [_row("ДО", "Закрывающие документы | Мария", "фактические")]
    idx = build_stage_index(rows)
    assert resolve_money_layer(idx, "ДО", "Закрывающие документы | Мария") == "фактические"


def test_none_inputs_return_none():
    idx = build_stage_index(ROWS)
    assert resolve_money_layer(idx, None, "Архив") is None
    assert resolve_money_layer(idx, "ДО", None) is None


def test_empty_index_returns_none():
    assert resolve_money_layer(build_stage_index([]), "Общая", "Архив") is None
