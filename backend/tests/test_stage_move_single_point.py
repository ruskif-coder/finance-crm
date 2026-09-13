# -*- coding: utf-8 -*-
"""Прибор-храповик: стадию сделки пишет ОДНА точка.

## Зачем

`our_stage_id` писали три человеческих пути — диалог движения, массовая правка в реестре
и поштучная инлайн-правка, — и требования проверял один из них. Владелец 13.09.2026:
«через админ доступ к реестру сделок мы всё равно двигаем сделки в обход правил». Гейт,
который обходится штатным экраном, — декорация.

Здесь не проверка поведения, а проверка ФОРМЫ КОДА: присваивание `our_stage_id` вне
`app/sales/stage_move.py` запрещено. Иначе четвёртый путь, написанный завтра, проедет
мимо и требований, и записи в историю — молча, ничего не уронив.

Это тот же узор, что у `test_stat_sources`: там запрос к таблице обязан упоминать
источник, здесь запись стадии обязана идти через общую точку.
"""
import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parent.parent / "app"

FIELD = "our_stage_id"

# Единственный файл, которому МОЖНО присваивать стадию.
OWNER = "sales/stage_move.py"

# Исключения — пара (файл, функция), а не файл целиком. Файловый список однажды уже
# пропустил настоящий переход: `media_plans.py` был разрешён ради рождения сделки из
# плана, и под тем же разрешением проехал `_advance_deal_on_link`, который стадию именно
# ДВИГАЕТ.
#
# Две законные породы: рождение сделки (стадия — начальное значение, проверять нечего)
# и разовый засев пустых стадий при старте.
ALLOWED = {
    ("routers/media_plans.py", "create_deal_from_plan"),
    ("routers/sales_dashboard.py", "create_deal"),
    ("routers/year_plan.py", "_make_deal"),
    ("routers/launch_prep.py", "prolong"),
    ("sales/bitrix/deal_import.py", "upsert_deals"),
    ("main.py", "backfill_deal_our_stage"),
}


def _assignments() -> dict:
    """Где `что-то.our_stage_id = …` встречается присваиванием атрибута.

    Ключ — пара (файл, функция). Смотрим именно на присваивание: чтение
    (`d.our_stage_id`) в запросах и сравнениях законно и встречается десятками.
    """
    out: dict = {}
    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(APP).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if not isinstance(node, ast.Assign):
                    continue
                for tgt in node.targets:
                    if isinstance(tgt, ast.Attribute) and tgt.attr == FIELD:
                        out.setdefault((rel, fn.name), []).append(node.lineno)
    return out


def test_only_one_module_assigns_the_stage():
    """Присваивать `our_stage_id` может только общая точка перевода.

    Исключение — конструкторы новых сделок: там это не переход, а начальное значение.
    """
    found = _assignments()
    offenders = {k: lines for k, lines in found.items()
                 if k[0] != OWNER and k not in ALLOWED}
    assert not offenders, (
        "стадия пишется мимо app/sales/stage_move.py: " + str(offenders) +
        " — требования и запись истории этот путь обойдёт молча")


def test_the_owner_module_is_actually_the_owner():
    """Храповик бесполезен, если сама общая точка перестала писать стадию."""
    assert any(k[0] == OWNER for k in _assignments()), (
        f"{OWNER} больше не присваивает {FIELD} — прибор сторожит пустоту")


def test_every_human_path_goes_through_the_move_module():
    """Оба человеческих пути обязаны звать общую точку по имени.

    Путей ДВА: диалог `/deals/{id}/move` и массовая правка. Третьего — инлайн-правки
    стадии в реестре — не существует: `DealPatch` поле `our_stage_id` никогда не
    объявлял, Pydantic его отбрасывал, и «третий тихий путь» жил только в комментарии
    (найдено прогоном 13.09.2026). Понадобится третий — объявить поле И провести через
    `stage_move`, тогда и это число вырастет.

    Проверяем вызов, а не импорт: импорт мог остаться от прошлой правки, а вот
    `stage_move.apply_move(...)` означает, что путь действительно через неё идёт.
    """
    src = (APP / "routers" / "sales_dashboard.py").read_text(encoding="utf-8")
    assert src.count("stage_move.apply_move(") >= 2, (
        "в sales_dashboard меньше двух вызовов apply_move — значит диалог или массовая "
        "правка снова пишет стадию сам")
    assert "stage_move.plan_move(" in src


def test_bulk_edit_does_not_push_the_stage_in_the_mass_update():
    """Массовая правка не должна тащить стадию в общий UPDATE.

    Иначе переведутся и те, кого требования не пустили: поштучная проверка окажется
    декорацией поверх одного общего запроса.
    """
    src = (APP / "routers" / "sales_dashboard.py").read_text(encoding="utf-8")
    assert "updates.pop(SalesDeal.our_stage_id, None)" in src, (
        "стадия осталась в общем массовом UPDATE — пропущенные сделки уедут вместе со "
        "всеми")

def test_bulk_allows_going_back_on_purpose():
    """Массовая правка НЕ проверяет «движение назад» — и это решение, а не пропуск.

    Диалог отдаёт 403 немастеру на `plan.is_back`; массовая правка этот признак не
    смотрит. Проверка безопасности 13.09.2026 подняла расхождение как обход права —
    владелец ответил, что допущение сознательное: массовая правка это инструмент разбора
    накопленного, а не движение по конвейеру, и требовать на неё мастера значит сделать
    разбор невозможным для тех, кто им занимается.

    Прибор стоит, чтобы решение не было отменено молча: «починка» асимметрии уронит этот
    тест, и человек прочитает, почему она такая.

    Что при этом обязано остаться: область видимости и проверка требований цели.
    """
    src = (APP / "routers" / "sales_dashboard.py").read_text(encoding="utf-8")
    bulk = src[src.index("def bulk_update_deals"):src.index("def brand_suggestions")]

    # Ищем ИСПОЛНЯЕМЫЕ строки, а не любое упоминание: объяснение рядом законно
    # называет признак, и первая редакция этого теста споткнулась о собственный
    # комментарий.
    code = [x for x in bulk.splitlines() if not x.lstrip().startswith("#")]
    assert not any("plan.is_back" in x for x in code), (
        "в массовой правке появилась проверка движения назад — если это намеренно, "
        "снимите этот тест вместе с комментарием в коде; если нет, см. комментарий")
    assert "СОЗНАТЕЛЬНО" in bulk, (
        "исчезло объяснение, почему массовая правка не гейтит движение назад — без него "
        "следующая проверка безопасности поднимет это снова как дыру")
    # А вот эти два ограничения снимать нельзя.
    assert "_scope_deal_ids" in src
    assert "plan.blockers" in bulk
