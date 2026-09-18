# -*- coding: utf-8 -*-
"""Решение по пикселю: «надо / не надо» — и отдельно «решали ли вообще».

Булев флаг знал два состояния, а их три. «Не надо» и «ещё не решали» выглядели
одинаково: блок «Доп. параметры РК» стоял свёрнутым с подписью «пиксель не заказан»,
хотя решения не принимал никто. Умолчание колонки читалось как выбор человека.

Согласовано с владельцем 18.09.2026: отдельная колонка `weborama_pixel_decided_at`,
существующий флаг не трогаем — 948 живых сделок автоматически читаются как «не выбрано».
"""
import inspect

from sqlalchemy import text

from app import models as _core  # noqa: F401
from app.sales import models as _sales  # noqa: F401


def _db():
    from app.database import SessionLocal
    return SessionLocal()


def test_the_column_exists_and_starts_empty():
    """Пусто = «не решали». Существующие сделки переписывать не пришлось."""
    db = _db()
    try:
        col = db.execute(text(
            "SELECT is_nullable FROM information_schema.columns "
            " WHERE table_name = 'sales_deals' "
            "   AND column_name = 'weborama_pixel_decided_at'")).scalar()
        assert col == "YES", "колонки нет или она обязательная"
    finally:
        db.close()


def test_the_flag_itself_is_untouched():
    """Смысл старого поля не изменился: `weborama_pixel = false` по-прежнему означает
    «пиксель не заказан», а не «не решали». Иначе пришлось бы искать глазами каждый
    запрос, который на него смотрит."""
    db = _db()
    try:
        row = db.execute(text(
            "SELECT is_nullable, column_default FROM information_schema.columns "
            " WHERE table_name = 'sales_deals' AND column_name = 'weborama_pixel'"
        )).mappings().first()
        assert row["is_nullable"] == "NO" and "false" in (row["column_default"] or "")
    finally:
        db.close()


def test_a_repeated_choice_still_counts_as_a_choice():
    """«Не нужен» по сделке, где флаг и так false, не меняет ни одного поля — но это
    РЕШЕНИЕ. Без отметки блок остался бы развёрнутым навсегда, а нажатие выглядело бы
    проигнорированным."""
    from app.routers import sales_dashboard as sd

    src = inspect.getsource(sd.save_deal_campaign_extra)
    i_mark = src.index("weborama_pixel_decided_at = ")
    i_exit = src.index("if was == want and not setup_changed")
    assert i_mark < i_exit, "отметка о выборе обязана стоять ДО раннего выхода"


def test_the_screen_is_told_whether_the_choice_was_made():
    """Экран не считает это сам: поле приходит с сервера, как и всё остальное состояние
    сделки. Вычисляй он его по `weborama_pixel`, третье состояние снова исчезло бы."""
    from app.routers import sales_dashboard as sd

    assert '"weborama_pixel_decided"' in inspect.getsource(sd)
