# -*- coding: utf-8 -*-
"""Правила строки денег действуют на ВСЕХ четырёх входах, а не только на форме.

ЗАЧЕМ. 11.09.2026 в проект завели `_assert_operation_valid` — серверную проверку того,
что интерфейс требовал и раньше: известный статус, не «доход и расход сразу», статья и
период на месте. Смысл был назван так: «у API нет второго набора правил, есть один».

В тот же день выяснилось, что набора всё-таки два. Проверка стояла на `create_operation`
и `update_operation` — то есть на пути «человек заполнил форму». Мимо неё шли:

  · `POST /operations/import`        — строит `Operation(...)` напрямую;
  · `POST /operations/import/apply`  — то же, плюс правит существующие строки;
  · `PUT  /operations/bulk`          — `setattr` в цикле.

Именно эти три кладут в базу СОТНИ строк за раз. Строгим оказался редкий путь, дырявым —
массовый; заметить это глазами нельзя, потому что каждая ручка по отдельности выглядит
аккуратно написанной.

Тест держит два свойства: правило одно на всех входах, и импорт не встаёт НАПОЛОВИНУ.
Второе важнее первого. Частичный импорт денег — худший исход: часть строк в базе, человек
видит «ошибка» и запускает файл заново, получая дубли по уже вставленному.
"""
import pytest
from fastapi import HTTPException

from app.routers import operations as ops


class _Op:
    """Строка журнала настолько, насколько её видят правила."""

    def __init__(self, **kw):
        self.id = kw.pop("id", 1)
        self.status = kw.pop("status", "ОПЛАЧЕНО")
        self.income = kw.pop("income", 100.0)
        self.expense = kw.pop("expense", 0.0)
        self.article_id = kw.pop("article_id", 7)
        self.period = kw.pop("period", "2026-09")
        assert not kw, kw


class _FakeDb:
    def __init__(self):
        self.rolled_back = False

    def rollback(self):
        self.rolled_back = True


# ── сами правила ─────────────────────────────────────────────────────────────

def test_good_row_passes():
    assert ops._operation_problem(_Op()) is None


@pytest.mark.parametrize("kw, expect", [
    ({"status": "ЧТО-ТО"},                  "статус"),
    ({"income": 100.0, "expense": 50.0},    "одновременно"),
    ({"article_id": None},                  "статья"),
    ({"period": "   "},                     "период"),
    ({"period": None},                      "период"),
])
def test_bad_rows_are_named(kw, expect):
    problem = ops._operation_problem(_Op(**kw))
    assert problem and expect.lower() in problem.lower(), problem


def test_assert_raises_400_with_the_same_text():
    """Одиночный вход отказывает сразу — и тем же объяснением, а не своим."""
    op = _Op(article_id=None)
    with pytest.raises(HTTPException) as e:
        ops._assert_operation_valid(op)
    assert e.value.status_code == 400
    assert e.value.detail == ops._operation_problem(op)


# ── импорт: всё или ничего ───────────────────────────────────────────────────

def test_import_with_no_problems_writes():
    db = _FakeDb()
    ops._assert_import_rows_valid(db, [])       # не должно ни бросить, ни откатить
    assert db.rolled_back is False


def test_import_rolls_back_on_a_single_bad_row():
    """Одна негодная строка отменяет ВЕСЬ файл. Именно откат, а не пропуск строки:
    человек должен получить либо целый импорт, либо нетронутую базу."""
    db = _FakeDb()
    with pytest.raises(HTTPException) as e:
        ops._assert_import_rows_valid(db, ["строка 3: Не выбрана статья."])
    assert db.rolled_back is True
    assert e.value.status_code == 400
    assert "Ничего не записано" in e.value.detail
    assert "строка 3" in e.value.detail, "номер строки обязан доехать до человека"


def test_import_message_names_the_scale_but_not_every_row():
    """Тысяча строк в ответе — стена текста, по которой ничего не найти. Показываем
    первые несколько и ОБЩЕЕ ЧИСЛО: характер ошибки виден, масштаб назван."""
    db = _FakeDb()
    many = [f"строка {i}: Не указан период." for i in range(1, 51)]
    with pytest.raises(HTTPException) as e:
        ops._assert_import_rows_valid(db, many)
    detail = e.value.detail
    assert "50 негодных строк" in detail
    assert detail.count("строка ") <= ops._IMPORT_PROBLEMS_SHOWN + 1
    assert f"и ещё {50 - ops._IMPORT_PROBLEMS_SHOWN}" in detail


# ── правило одно на всех входах ──────────────────────────────────────────────

def test_every_write_path_checks_the_invariants():
    """Гейт от возврата дефекта: каждая ручка, которая пишет строку денег, обязана
    спросить правила. Проверяем по ИСХОДНИКУ — потому что обойти их снова легче всего
    новым путём записи, а не правкой старого.
    """
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(ops))
    checkers = {"_operation_problem", "_assert_operation_valid"}
    # Ручки, пишущие строку журнала денег. Имена, а не маршруты: маршрут переименуют,
    # функция останется.
    writers = ["create_operation", "update_operation", "bulk_update_operations",
               "import_excel", "import_apply"]
    by_name = {n.name: n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    missing = []
    for w in writers:
        fn = by_name.get(w)
        if fn is None:
            missing.append(f"{w} — функции с таким именем больше нет, поправьте список")
            continue
        called = {getattr(c.func, "id", None) or getattr(c.func, "attr", None)
                  for c in ast.walk(fn) if isinstance(c, ast.Call)}
        if not (called & checkers):
            missing.append(f"{w} пишет операцию, не спросив правила")
    assert not missing, "; ".join(missing)
