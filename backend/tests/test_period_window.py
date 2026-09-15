# -*- coding: utf-8 -*-
"""Период сделки — ФИНАНСОВЫЙ месяц, и отбор с сортировкой идут по нему.

Правило владельца 15.09.2026: «период сортируется не по датам старта и финиша, а по
указанному финансовому периоду», и то же самое для отбора.

Что было. Отбор считал ПЕРЕСЕЧЕНИЕ дат размещения с окном и отвечал на другой вопрос —
«какие кампании в эти месяцы крутились». Отсюда «работает криво»: в марте—мае
показывались сделки с периодом «2026-01» (размещение длинное, задевает март), а сделка
с периодом «2026-07» из июля пропадала, если у неё испорчен конец — таких 32, вплоть до
года разницы со стартом. Сортировка по той же причине шла по дате старта, и сделки
одного периода расходились по дню начала, хотя в столбце у них написано одно и то же.

Финансовый период материализован как первое число месяца в `period_from` (см.
`_period_bounds`, правку «Периода» в реестре и рождение сделки из плана). Дата окончания
в нём не участвует — значит и испортить его нечем.
"""
from datetime import date

from app.database import SessionLocal
from app.notify import models as _n  # noqa: F401
from app.ord import models as _o     # noqa: F401
from app.sales.models import SalesDeal
from app.sales.periods import end_is_stale, month_key
from app.routers.sales_dashboard import _base_query


def _window(db, date_from, date_to):
    q = _base_query(db, date_from, date_to, None, None, None, None, None)
    return [d for d, _layer, _key in q.all()]


def test_the_window_selects_by_the_financial_period():
    """В окне только сделки, чей ПЕРИОД в него попадает — ни одной лишней."""
    db = SessionLocal()
    try:
        for a, b in (("2026-03", "2026-05"), ("2026-07", "2026-07"), ("2027-01", "2027-12")):
            for d in _window(db, a, b):
                assert d.period_from is not None
                assert a <= month_key(d.period_from) <= b, (
                    f"сделка {d.code or d.id} с периодом {month_key(d.period_from)} "
                    f"попала в окно {a}..{b}")
    finally:
        db.close()


def test_a_broken_end_date_cannot_hide_a_deal_from_its_own_period():
    """Конец раньше старта больше не участвует в отборе вовсе."""
    db = SessionLocal()
    try:
        broken = (db.query(SalesDeal)
                  .filter(SalesDeal.period_from.isnot(None),
                          SalesDeal.period_to.isnot(None),
                          SalesDeal.period_to < SalesDeal.period_from)
                  .order_by(SalesDeal.id).all())
        if not broken:
            return              # данные вычищены — проверять нечего, и это хороший исход
        for d in broken[:10]:
            key = month_key(d.period_from)
            assert d.id in {x.id for x in _window(db, key, key)}, (
                f"сделка {d.code or d.id}: период {key}, конец {d.period_to} — "
                f"выпала из своего же периода")
    finally:
        db.close()


def test_the_whole_period_is_taken_month_by_month():
    """Сумма сделок по месяцам окна равна выборке всего окна.

    Отбор по месяцу не должен ни терять сделку, ни считать её дважды — на этом стоит
    сверка сводки с реестром.
    """
    db = SessionLocal()
    try:
        whole = {d.id for d in _window(db, "2026-03", "2026-05")}
        by_month = set()
        for m in ("2026-03", "2026-04", "2026-05"):
            part = {d.id for d in _window(db, m, m)}
            assert not (part & by_month), f"сделка попала в два месяца ({m})"
            by_month |= part
        assert whole == by_month
    finally:
        db.close()


def test_end_is_stale_names_the_impossible_placement():
    assert end_is_stale(date(2026, 7, 1), date(2025, 9, 30)) is True
    assert end_is_stale(date(2026, 7, 1), date(2026, 7, 31)) is False
    assert end_is_stale(date(2026, 7, 1), None) is False     # NULL = месяц старта
    assert end_is_stale(None, date(2026, 7, 31)) is False    # старта нет — судить не о чем


def test_month_key_prints_four_digit_years():
    """«25-12» вместо «0025-12» читается как нормальный год и выглядит как сбой
    сортировки — хотя сортировка идёт по периоду, а не по подписи. Такие даты в базе
    есть: конец РК «0025-12-24» заведён руками."""
    assert month_key(date(25, 12, 24)) == "0025-12"
    assert month_key(date(2026, 3, 1)) == "2026-03"
    assert month_key(None) is None


def test_sorting_is_by_the_period_not_by_the_start_date():
    """Реестр, отсортированный по «Периоду», идёт по месяцам подряд.

    Прибор смотрит на то, что видит человек, — подпись периода в строке, — а не на
    внутреннее выражение сортировки: менялось именно то, что читается с экрана.
    """
    from app.models import User
    from app.routers.sales_dashboard import deals_registry
    db = SessionLocal()
    try:
        user = (db.query(User).join(User.role)
                .filter(User.is_active == 1).order_by(User.id).first())
        for direction in ("asc", "desc"):
            items = deals_registry(db=db, current_user=user, sort="period",
                                   direction=direction, limit=500, offset=0)["items"]
            seen = [i["period"] for i in items if i["period"]]
            ordered = sorted(seen, reverse=(direction == "desc"))
            assert seen == ordered, f"периоды не идут подряд ({direction})"
    finally:
        db.close()


def test_nothing_outranks_the_chosen_column():
    """Служебный признак не смеет стоять в сортировке ВЫШЕ выбранной колонки.

    Жалоба с прода 15.09.2026: список по периоду шёл 2026-10, 2026-09 … и только потом
    2027-09, 2027-05 — то есть распадался на ДВА независимо отсортированных блока, и
    «2027 год оказывался в середине». Первым ключом ORDER BY стоял `local_first`
    («локальные сделки всегда вверху при любой сортировке»), и он делил таблицу надвое.

    Тест выше (`test_sorting_is_by_the_period_not_by_the_start_date`) этого НЕ поймал и
    поймать не мог: на стенде локальных сделок ноль, признак был константой. Поэтому
    проверка здесь — на форме кода, а не на данных: она не зависит от того, что лежит
    в базе именно сегодня.
    """
    import inspect
    from app.routers import sales_dashboard as sd
    src = inspect.getsource(sd.deals_registry)
    ob = src[src.index("q.order_by("):]
    ob = ob[:ob.index(")\n")]
    head = ob[len("q.order_by("):].split(",")[0].strip()
    assert head == "ordering", (
        f"первым ключом сортировки стоит «{head}», а не выбранная колонка — "
        f"таблица распадётся на блоки, и человек прочтёт это как сбой сортировки")
