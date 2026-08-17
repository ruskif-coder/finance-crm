"""Группы прав должны совпадать с контурами меню, а ключи — не меняться никогда.

Ключ права — это то, чем в базе записан доступ конкретного человека. Переименование
ключа молча отнимает доступ у всех, у кого он был: строка в role_permissions
перестаёт совпадать. Поэтому список ключей зафиксирован здесь дословно.
"""
from app.permissions import SECTIONS

CONTOURS = {"Финансы", "Продажи", "Аккаунты", "Справочники", "Ядро"}

EXPECTED_KEYS = {
    "dashboard", "pl", "balance", "planfact", "receivables",
    # Добавлен 2026-08-17: у «Фин. отчёта» появилось своё право (был на pl).
    "finreport",
    "sales_dashboard", "sales_registry", "sales_analytics", "year_plan",
    # Добавлен 2026-08-17 вместе с дашбордом аккаунта (очередь «Что делать»).
    "accounts_dashboard",
    "media_plans", "media_plans_editor",
    "operations", "import",
    "counterparties", "contracts", "dir_advertisers", "dir_agencies", "bx_reconcile",
    "settings_balances", "settings_articles", "settings_pipelines",
    "settings_services", "settings_field_audit", "settings_audit",
    # Добавлен 2026-08-16 вместе с разделом «Бэклог отладки» (routers/backlog.py).
    "settings_backlog",
}


def test_groups_are_contours():
    """Сравнение строгое, а не «подмножество»: иначе тест останется зелёным, когда
    все права схлопнутся в один контур — а такая раскладка бессмысленна, хотя
    формально ничего лишнего в ней нет."""
    groups = {s["group"] for s in SECTIONS}
    assert groups == CONTOURS, (
        f"Лишние группы: {groups - CONTOURS}; опустевшие контуры: {CONTOURS - groups}"
    )


def test_permission_keys_unchanged():
    keys = {s["key"] for s in SECTIONS}
    assert keys == EXPECTED_KEYS, (
        f"Пропали: {EXPECTED_KEYS - keys}; появились: {keys - EXPECTED_KEYS}"
    )


def test_every_section_has_view():
    for s in SECTIONS:
        assert "view" in s["actions"], f"У раздела {s['key']} нет действия view"
