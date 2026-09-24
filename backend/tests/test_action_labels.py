# -*- coding: utf-8 -*-
"""Прибор-храповик: новое действие не появляется в журнале сырым ключом.

## Зачем

Правило проекта: строка действия, попавшая в `log_action`, получает человеческую подпись
в `ACTION_LABELS`. Без неё экран «Журнал действий» показывает служебный ключ вида
`ord_sync_kktu`, и запись о реальном событии читается как отладочный мусор. Так уже
случилось 12.09.2026 с заливкой ККТУ — чинилось отдельной версией ПОСЛЕ выкладки.

## Почему храповик, а не строгое равенство

Замер 12.09.2026: в коде 237 действий, подписи есть у 44. Требовать подписи у всех —
значит уронить сборку на 193 унаследованных строках и заставить придумывать формулировки
скопом, не разбираясь, что каждая значит. Разовая уборка на 193 пункта делается
осознанно и отдельно, а не под давлением красного теста.

Поэтому здесь ПОТОЛОК: столько-то без подписи допустимо, больше — нет. Новое действие
без подписи роняет тест сразу; подписанное старое опускает потолок, и обратно он уже не
поднимется. Долг виден числом, а не ощущением.
"""
import ast
import pathlib

from app.routers.users import ACTION_LABELS

APP = pathlib.Path(__file__).resolve().parent.parent / "app"

# Замер 12.09.2026 — 193. Долг закрыт 24.09.2026 (владелец: «названия событий почти все
# технические»): подписаны все, потолок — ноль. Новое действие без подписи роняет тест.
CEILING = 0


def _actions_in_code() -> dict:
    """Строки действий, уходящие в `log_action`, и файлы, откуда они уходят.

    Только литералы: собранное из переменной здесь не разобрать, и притворяться, что
    разобрали, хуже, чем честно пропустить.
    """
    out: dict = {}
    for path in sorted(APP.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:                      # pragma: no cover — ловим явно
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "id", "") == "log_action"
                    and len(node.args) >= 3):
                arg = node.args[2]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    out.setdefault(arg.value, set()).add(path.name)
    return out


def test_unlabelled_actions_do_not_grow():
    used = _actions_in_code()
    assert used, "не нашёл ни одного log_action — прибор смотрит не туда"
    missing = sorted(k for k in used if k not in ACTION_LABELS)
    assert len(missing) <= CEILING, (
        "новое действие без подписи в ACTION_LABELS — в журнале оно будет сырым ключом: "
        + ", ".join(f"{k} ({', '.join(sorted(used[k]))})" for k in missing[:10]))


def test_ceiling_is_lowered_when_labels_are_added():
    """Обратный ход храповика: подписали — опустите потолок, иначе он ничего не держит."""
    used = _actions_in_code()
    missing = [k for k in used if k not in ACTION_LABELS]
    assert len(missing) >= CEILING - 20, (
        f"без подписи осталось {len(missing)} при потолке {CEILING} — "
        f"опустите CEILING до {len(missing)}, чтобы прибор снова что-то держал")


def test_targeting_link_action_is_labelled():
    """Точечно: действие, заведённое 12.09.2026 вместе с кнопкой нацеливания."""
    assert ACTION_LABELS.get("targeting_link")
