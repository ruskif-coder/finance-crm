"""Группы прав должны совпадать с контурами меню, а ключи — не меняться никогда.

Ключ права — это то, чем в базе записан доступ конкретного человека. Переименование
ключа молча отнимает доступ у всех, у кого он был: строка в role_permissions
перестаёт совпадать. Поэтому список ключей зафиксирован здесь дословно.
"""
from app.permissions import SECTIONS

CONTOURS = {"Финансы", "Продажи", "Аккаунты", "Паблишеры", "Траффики",
            "Справочники", "Ядро"}

EXPECTED_KEYS = {
    "dashboard", "pl", "balance", "planfact", "receivables",
    # Добавлен 2026-08-17: у «Фин. отчёта» появилось своё право (был на pl).
    "finreport",
    "sales_dashboard", "sales_registry", "sales_analytics", "year_plan",
    # Добавлен 2026-08-17 вместе с дашбордом аккаунта (очередь «Что делать»).
    "accounts_dashboard",
    # Добавлены 2026-08-25 вместе с обвязкой ОРД. `ord` — зеркало справочников,
    # `ord_submit` отделён потому, что запись в ЕРИР необратима: маркер, ушедший
    # в реестр, не отменяется нажатием «отмена».
    "ord", "ord_submit",
    # Добавлен 2026-08-26 вместе с модулем креативов (сбор запуска). Выпуск ЕРИД остался
    # под `ord_submit`: за одним правом — одна необратимость.
    "creatives",
    "media_plans", "media_plans_editor",
    "operations", "import",
    "counterparties", "contracts", "dir_advertisers", "dir_agencies", "dir_publishers",
    # Добавлен 2026-08-20: экран «Заполнение» отделён от реестра площадок (только view).
    "dir_publishers_bulk",
    # Добавлен 2026-08-28 вместе с контуром кабинета паблишера: учётки внешних лиц.
    "dir_publishers_cabinets",
    "bx_reconcile",
    # Добавлен 2026-08-28 вместе с контуром «Траффики»: очередь проверки материала.
    "traffic_queue",
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


def test_registry_and_usage_match():
    """Реестр секций и то, чем реально закрыты ручки, — одно и то же множество.

    Две молчаливые ошибки ловятся здесь и больше нигде:

    · **опечатка в имени секции.** `require_permission("creativs", …)` не падает: секция
      просто не находится в `role_permissions`, и ручка отказывает ВСЕМ, кроме админа.
      Со стороны это выглядит как «у меня нет прав», а не как ошибка в коде — и чинят
      это раздачей прав на несуществующую секцию;

    · **осиротевшая секция.** Ключ остался в реестре, а последняя ручка, которой он
      закрывал, переименована или удалена. В конструкторе ролей появляется галочка,
      которая ничего не открывает, — и однажды кто-то на неё положится.

    Читается через метку `_perm_sections` на замыкании: снаружи зависимость неотличима
    от любой другой, и обойти ручки было бы нечем.
    """
    from fastapi.routing import APIRoute

    import app.main as main_module

    def walk(dep, acc):
        for sub in dep.dependencies:
            if sub.call is not None:
                acc.append(sub.call)
            walk(sub, acc)

    used = set()
    for route in main_module.app.routes:
        if not isinstance(route, APIRoute):
            continue
        found = []
        walk(route.dependant, found)
        for call in found:
            used.update(getattr(call, '_perm_sections', ()) or ())

    registered = {s['key'] for s in SECTIONS}
    assert not (used - registered), (
        f"ручки закрыты несуществующими секциями: {sorted(used - registered)} — "
        "такая ручка отказывает всем, кроме админа, и выглядит как нехватка прав"
    )
    assert not (registered - used), (
        f"секции есть в реестре, но ничего не закрывают: {sorted(registered - used)} — "
        "в конструкторе ролей появляется галочка, которая ничего не открывает"
    )
