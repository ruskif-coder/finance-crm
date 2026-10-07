# -*- coding: utf-8 -*-
"""Ручка записи не должна стоять под правом «просмотр».

Внешний аудит 06.10.2026: `POST /launch-prep/set/{id}/erid/refresh` меняет состояние во внешней
системе, а закрыта правом `creatives/view`. «Просмотр» — самое широкое право (его получают почти
все), и ручка записи под ним доступна тем, кому записывать не положено. Глазами это не
ловится: ручка работает, права «есть». Поэтому прибор: любая ручка POST/PUT/PATCH/DELETE, у
которой ВСЕ проверки права — на «просмотр», должна быть в явном списке с причиной. Новая ручка
записи под «просмотром» роняет сборку, пока её не разобрали глазами.

Сам список — это «предпросмотры, расчёты и выгрузки»: им нужен POST из-за тела запроса, но они
ничего не пишут (это стережётся тоже: в исходнике такой ручки не должно появляться
`db.commit()`/`db.add(`), и две ручки, которые ПИШУТ: «Обновить статус» ЕРИД (оставлена
осознанно, владелец 07.10.2026: пусть будет у всех с правом просмотра; крон делает то же самое
каждые 30 минут; при готовом ЕРИД кнопка блокируется) и выгрузка платёжек в Альфу (двигает
счётчик номеров; найдена этим прибором, решение владельца ещё не принято).

Пары раздела и действия читаются из метки `_perm_pairs`: у `require_any_permission` бывают
смешанные пары (`creatives/edit` или `traffic_queue/edit`), и общего «действия по умолчанию»
для них недостаточно — именно так замер 07.10.2026 сначала принял три ручки под правкой за
ручки под просмотром.
"""
import inspect

import pytest
from fastapi import Depends, FastAPI

from app.main import app
from app.permissions import require_any_permission, require_permission
from tests.route_utils import iter_dependencies

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# (метод, путь) -> почему это допустимо под правом «просмотр»
VIEW_ONLY_WRITES = {
    ("POST", "/api/annexes/export.xlsx"): "выгрузка: POST только из-за тела запроса, ничего не пишет",
    ("POST", "/api/annexes/party/phrase"): "генерация фразы по стороне договора, ничего не пишет",
    ("POST", "/api/diadoc/import/preview"): "предпросмотр импорта: только разбор файла",
    ("POST", "/api/operations/import/preview"): "предпросмотр импорта: только разбор файла",
    ("POST", "/api/operations/export/alfa"):
        "ЗАПИСЬ, ОТКРЫТЫЙ ВОПРОС (найдено прибором 07.10.2026): формирует файл платёжных поручений "
        "и каждый раз двигает счётчик номеров `payment_number_last`, а закрыта правом «просмотр "
        "операций». Без правки право есть только у роли viewer (1 человек), выгрузкой по журналу "
        "копии прода не пользовался никто. РЕШЕНИЕ ВЛАДЕЛЬЦА 07.10.2026: модуль (и Диадок) пока не трогаем, на следующей неделе финблок переделывается целиком.",
    ("POST", "/api/launch-prep/set/{set_id}/erid/refresh"):
        "ЗАПИСЬ осознанно: опрос статуса ЕРИД и объявление готового маркера; то же делает крон "
        "каждые 30 минут (решение владельца 07.10.2026)",
}

# Ручки из списка, про которые проверяется «в исходнике нет записи в базу»
WRITES_ON_PURPOSE = {("POST", "/api/launch-prep/set/{set_id}/erid/refresh"),
                     ("POST", "/api/operations/export/alfa")}
NO_DB_WRITE = {k for k in VIEW_ONLY_WRITES if k not in WRITES_ON_PURPOSE}


def view_only_writes(application):
    """{(метод, путь): функция} — ручки записи, где ВСЕ проверки права — на «просмотр»."""
    found = {}
    for r in application.routes:
        methods = (getattr(r, "methods", None) or set()) & WRITE_METHODS
        if not methods or not hasattr(r, "dependant"):
            continue
        pairs = []
        for d in iter_dependencies(r.dependant):
            pairs.extend(getattr(d.call, "_perm_pairs", ()))
        if pairs and all(action == "view" for _, action in pairs):
            for m in methods:
                found[(m, r.path)] = r.endpoint
    return found


def test_write_routes_under_view_are_exactly_the_known_ones():
    found = view_only_writes(app)
    new = sorted(set(found) - set(VIEW_ONLY_WRITES))
    gone = sorted(set(VIEW_ONLY_WRITES) - set(found))
    assert not new, ("ручка записи под правом «просмотр»: переведи на edit/create/delete или "
                     f"внеси в список с причиной: {new}")
    assert not gone, f"в списке есть ручки, которых под «просмотром» уже нет — убери из списка: {gone}"


@pytest.mark.parametrize("key", sorted(NO_DB_WRITE))
def test_the_read_only_exceptions_really_do_not_write(key):
    src = inspect.getsource(view_only_writes(app)[key])
    assert "db.commit(" not in src and "db.add(" not in src, \
        f"{key}: ручка в списке «ничего не пишет», а в исходнике запись в базу"


# ── сам прибор ────────────────────────────────────────────────────────────────

def _mini(dep):
    a = FastAPI()

    @a.post("/w")
    def w(user=Depends(dep)):
        return {}
    return a


def test_the_instrument_flags_a_write_under_view():
    assert ("POST", "/w") in view_only_writes(_mini(require_permission("contracts", "view")))


def test_the_instrument_passes_a_write_under_edit():
    assert view_only_writes(_mini(require_permission("contracts", "edit"))) == {}


def test_mixed_pairs_with_edit_are_not_flagged():
    """`creatives/edit` ИЛИ `traffic_queue/edit` — это правка, а не просмотр."""
    dep = require_any_permission((("creatives", "edit"), ("traffic_queue", "edit")))
    assert view_only_writes(_mini(dep)) == {}


def test_any_view_only_pairs_are_flagged():
    dep = require_any_permission(("creatives", "traffic_queue"), "view")
    assert ("POST", "/w") in view_only_writes(_mini(dep))
