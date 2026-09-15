# -*- coding: utf-8 -*-
"""Гео на карточке сделки — настоящее, из шапки её медиаплана.

Жалоба владельца 15.09.2026: «гео не тянется с МП в сделку, массовые жалобы». Тянуть
было НЕКУДА — своего поля гео у сделки нет вовсе, — а на карточке стояла строка
`['Гео', '—']` с зашитым прочерком: она рисовалась всегда, чем бы ни был заполнен план.

Данные при этом были на месте и нигде не терялись: замер того же дня — 35 привязанных
планов из 36 с заполненным гео, и в документе ДС оно печаталось верно (`app/sales/annex.py`
читает его тем же джойном). То есть «не тянется» относилось ровно к одному экрану.

Колонку сделке не заводили намеренно: гео задаётся в плане, оттуда же его берёт документ,
и второе хранилище того же значения разъехалось бы с первым. Карточка читает его через
общий контекст строки (`app/sales/row_context.py`) — там же, где живут цвет услуги и
поверхность, которые уже однажды разъезжались между реестром, очередью и карточкой.
"""
import inspect

from app.sales.row_context import RowContext, load_row_context


def test_the_card_returns_the_geo():
    from app.routers import sales_dashboard as sd
    src = inspect.getsource(sd.get_deal)
    assert '"geo": _card_ctx.geo(deal.id)' in src, "карточка не отдаёт гео"


def test_geo_lives_in_the_shared_row_context():
    """Считать гео по месту нельзя: витрин у строки сделки три, и они уже расходились."""
    assert hasattr(RowContext, "geo")


def test_geo_reaches_the_card_on_real_data():
    """На живых данных: у сделки с планом, где гео заполнено, карточка его показывает."""
    from app.database import SessionLocal
    from app.notify import models as _n   # noqa: F401
    from app.ord import models as _o      # noqa: F401
    from app.sales.models import SalesMediaPlan
    db = SessionLocal()
    try:
        pair = (db.query(SalesMediaPlan.deal_id, SalesMediaPlan.geo_id)
                .filter(SalesMediaPlan.deal_id.isnot(None),
                        SalesMediaPlan.geo_id.isnot(None))
                .order_by(SalesMediaPlan.deal_id).first())
        if not pair:
            return                        # на стенде нет пары план↔сделка с гео
        ctx = load_row_context(db, [pair.deal_id])
        assert ctx.geo(pair.deal_id), "гео плана не доехало до контекста карточки"
    finally:
        db.close()
