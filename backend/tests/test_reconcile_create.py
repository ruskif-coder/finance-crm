"""Заведение компании в Битриксе: две ошибки, найденные живой проверкой 2026-08-23.

Кнопка «завести в Битриксе» ни разу не запускалась с момента выкладки (v2.4.5,
19.08), и обе ошибки дожили именно потому, что на неё не было ни одного теста.
Проверка на выброшенной компании (bx 2756, создана и удалена) показала:

1. поле типа называется `typeId`; при `companyType` Битрикс запрос принимает,
   но компания заводится БЕЗ типа и не попадает в `filter[typeId]=SUPPLIER`,
   то есть исчезает из экрана сверки;
2. ответ обёрнут в `{"success": ..., "data": {...}}`, id на верхнем уровне нет.
"""
from pathlib import Path

import app.routers.sales_reconcile as rec
from app.sales.bitrix import transport


def test_created_id_reads_wrapped_response():
    """Реальный ответ VibeCode на POST: обёртка success/data."""
    assert rec._created_id({"success": True, "data": {"id": 2756}}) == "2756"


def test_created_id_survives_unwrapped_and_upper_case():
    assert rec._created_id({"id": 7}) == "7"
    assert rec._created_id({"success": True, "data": {"ID": 9}}) == "9"


def test_created_id_returns_empty_when_no_id():
    """Пустая строка — сигнал «связать не можем», роутер отвечает 502.
    Молча вернуть None нельзя: повтор наплодит дубли компаний."""
    assert rec._created_id({"success": True, "data": {}}) == ""
    assert rec._created_id({}) == ""
    assert rec._created_id(None) == ""


def test_company_created_with_same_type_field_as_read():
    """Создаём и читаем компании одним и тем же именем поля.

    Рассинхрон этих двух мест не ловится ничем: Битрикс принимает запрос,
    ошибки нет, а компания просто не появляется в списке.
    """
    src = Path(rec.__file__).read_text(encoding="utf-8")
    reader = Path(transport.__file__).read_text(encoding="utf-8")
    assert '"filter[typeId]"' in reader, "читатель компаний сменил имя поля"
    assert '"typeId": TYPE_ID[kind]' in src, "создание компании должно слать typeId"
    # именно как ключ запроса (в кавычках) — в комментариях это слово упоминается
    assert '"companyType"' not in src, "companyType Битрикс принимает, но тип не ставит"
