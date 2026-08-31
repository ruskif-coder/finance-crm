# -*- coding: utf-8 -*-
"""Буквальный адрес не должен перехватываться параметром, объявленным раньше.

FastAPI подбирает маршрут ПО ПОРЯДКУ объявления, а не по точности совпадения. Поэтому
`@router.put("/{cabinet_id}")`, написанный выше `@router.put("/our-contacts")`, забирает
себе и второй адрес: «our-contacts» приезжает в него как номер кабинета, разбор падает,
и снаружи это выглядит как «страница падает при сохранении» — без единой строки в логе
приложения, потому что до кода дело не доходит.

Поймано 30.08.2026 на настройке наших контактов у площадок. Ошибка не видна ни в коде
(обе ручки выглядят правильно), ни в тестах ручек (их зовут напрямую, мимо
маршрутизации), ни в схеме OpenAPI — только в живом запросе.

Прибор проверяет то, что можно проверить механически: **каждый полностью буквальный
адрес обязан доставаться сам себе.** Адреса с параметрами так не проверить — по ним
неоткуда взять подходящее значение, — но именно буквальные и заслоняются.
"""
from starlette.routing import Match

from app.main import app


def _first_match(path: str, method: str):
    """Кто ответит на этот запрос на самом деле — по порядку, как это делает Starlette."""
    scope = {"type": "http", "path": path, "method": method, "root_path": "",
             "headers": [], "query_string": b""}
    for route in app.routes:
        match, _ = route.matches(scope)
        if match is Match.FULL:
            return route
    return None


def test_no_literal_route_is_shadowed():
    shadowed = []
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or set()
        if "{" in path or not path.startswith("/api/"):
            continue
        for method in sorted(methods - {"HEAD", "OPTIONS"}):
            winner = _first_match(path, method)
            if winner is not route:
                shadowed.append(
                    f"{method} {path} → достаётся {getattr(winner, 'path', '?')}")
    assert not shadowed, (
        "адрес перехвачен маршрутом с параметром, объявленным выше:\n  "
        + "\n  ".join(sorted(set(shadowed)))
        + "\nЛечится переносом буквального объявления ВЫШЕ параметрического.")
