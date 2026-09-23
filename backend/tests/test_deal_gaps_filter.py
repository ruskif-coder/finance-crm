# -*- coding: utf-8 -*-
"""Фильтр «Незаполненные» в реестре сделок.

Здесь два разных утверждения, и второе дороже первого.

ПЕРВОЕ — «нет стадии» действительно отбирает сделки без НАШЕЙ стадии. Колонка
«Стадия» в реестре показывает нашу лестницу (`our_stage_id`), а не имя стадии из
Битрикса, и фильтр обязан отвечать на то, что человек видит. Сделка без нашей стадии
не попадает ни в один слой денег и выпадает из всех сводок — то есть это именно та
дыра, ради которой метку и добавили 22.09.2026.

ВТОРОЕ — неизвестный признак даёт ОТКАЗ, а не тишину. До 22.09.2026 чужой ключ молча
выпадал из списка условий, и если он был единственным, условий не оставалось вовсе:
экран показывал ВСЕ сделки, утверждая, что отобрал незаполненные. Со стороны «фильтр
ничего не нашёл» и «фильтр не сработал» выглядят по-разному, а вот «фильтр отобрал
всё» неотличимо от «в реестре просто много строк».

Это же единственный сторож стыка двух деревьев: список меток живёт на фронте
(`GAP_FIELDS` в components/salesTableKit.js), обработчики — здесь. Прочитать JS из
контейнера бэкенда нельзя, поэтому расхождение ловится не сверкой списков, а тем,
что новая метка без обработчика падает на первом же щелчке.
"""
import pytest
from fastapi import HTTPException

from app.database import SessionLocal
from app.routers.sales_dashboard import _apply_extra_filters
from app.sales.models import SalesDeal


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _count(db, gaps):
    return _apply_extra_filters(db.query(SalesDeal), db, False, None, gaps).count()


def test_no_stage_matches_the_plain_query(db):
    """Число фильтра сходится с прямым запросом к базе."""
    direct = db.query(SalesDeal).filter(SalesDeal.our_stage_id.is_(None)).count()
    assert _count(db, ["our_stage_id"]) == direct


def test_no_stage_is_about_our_ladder_not_bitrix(db):
    """Отбираются сделки без НАШЕЙ стадии.

    Отдельная проверка, потому что у сделки есть второе поле стадии —
    `bitrix_stage`, имя из чужой системы. Спутать их легко: обе называются
    «стадия», а заполнены по-разному. Фильтр по чужому полю выглядел бы рабочим и
    отбирал бы не те строки.
    """
    q = _apply_extra_filters(db.query(SalesDeal), db, False, None, ["our_stage_id"])
    rows = q.limit(50).all()
    if not rows:
        pytest.skip("на стенде нет сделок без нашей стадии")
    assert all(d.our_stage_id is None for d in rows)


def test_gaps_add_up_by_or(db):
    """Две метки складываются по ИЛИ, а не по И.

    Человек ищет, что дозаполнить, а не строку, где пусто сразу всё. Подмена ИЛИ на
    И не падает — она возвращает почти пустой список, и это читается как «всё
    заполнено».
    """
    a, b = _count(db, ["our_stage_id"]), _count(db, ["advertiser_id"])
    both = _count(db, ["our_stage_id", "advertiser_id"])
    assert both >= max(a, b)
    assert both <= a + b


def test_unknown_gap_is_refused_loudly(db):
    """Непонятый признак — 400 с его именем, а не молчаливый показ всего."""
    with pytest.raises(HTTPException) as e:
        _count(db, ["стадия_которой_нет"])
    assert e.value.status_code == 400
    assert "стадия_которой_нет" in e.value.detail

    # И в компании с понятным — тоже отказ: иначе одна опечатка в наборе тихо
    # расширила бы выборку, оставшись незамеченной среди верных меток.
    with pytest.raises(HTTPException):
        _count(db, ["our_stage_id", "опечатка"])


def test_known_gaps_still_work(db):
    """Все метки, которые предлагает экран, обработчик знает.

    Список повторён здесь намеренно: он и есть то, что сверяется с фронтом глазами
    при правке. Пропадёт обработчик — тест покраснеет на отказе.
    """
    for g in ("advertiser_id", "brand_id", "agency_id", "sales_rep_id",
              "account_manager_id", "period_from", "payer", "our_stage_id"):
        _count(db, [g])          # не падает — значит признак известен
