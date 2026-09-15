# -*- coding: utf-8 -*-
"""«Скрыть архив» в реестре прячет ЛЮБОЙ терминальный исход.

Правило владельца 15.09.2026: терминальные стадии — это архив, и в выдаче сделок их
быть не должно.

Что было. Признаком архива служил `stage_key = 'archive'`, а у «Сделка не случилась» и
«Сделка сорвалась» ключа нет вовсе — условие пропускало их через ветку `IS NULL`, и при
включённом «скрыть архив» сорванные сделки оставались в списке. Замер на стенде:
569 сделок архива пряталось, 3 сорванные — нет.

Обратный край тут важнее самого правила: сделка БЕЗ нашей стадии (`our_stage_id IS NULL`)
обязана остаться видимой. Это «требует разбора» — её как раз и надо найти, а не спрятать.
На стенде таких 48, и лёгкая ошибка в условии (`SalesStage.stage_key.is_(None)` вместо
`SalesStage.id.is_(None)`) утащила бы их в архив вместе с сорванными.
"""
from app.database import SessionLocal
from app.notify import models as _n  # noqa: F401
from app.ord import models as _o     # noqa: F401
from app.models import User
from app.sales.models import SalesDeal, SalesStage
from app.routers.sales_dashboard import deals_registry


def _registry(db, user, **kw):
    kw.setdefault("limit", 500)
    kw.setdefault("offset", 0)
    return deals_registry(db=db, current_user=user, **kw)


def test_hidden_archive_leaves_no_terminal_deal():
    db = SessionLocal()
    try:
        user = (db.query(User).join(User.role)
                .filter(User.is_active == 1).order_by(User.id).first())
        terminal = {s.id: s.name for s in db.query(SalesStage)
                    .filter((SalesStage.is_terminal.is_(True))
                            | (SalesStage.is_lost.is_(True))).all()}
        if not terminal:
            return                       # каталог без терминальных стадий — проверять нечего
        items = _registry(db, user, hide_archive=True)["items"]
        ids = [i["id"] for i in items]
        if not ids:
            return
        left = [d.code or d.id for d in db.query(SalesDeal).filter(SalesDeal.id.in_(ids)).all()
                if d.our_stage_id in terminal]
        assert not left, f"в выдаче остались терминальные сделки: {left[:5]}"
    finally:
        db.close()


def test_exactly_the_terminal_deals_are_hidden_and_nothing_else():
    """Прячется РОВНО столько, сколько терминальных — ни одной лишней.

    Здесь ловится обратная ошибка: условие, написанное через `stage_key IS NULL` вместо
    `stage_id IS NULL`, утащило бы в архив ещё и сделки БЕЗ нашей стадии. А это
    «требует разбора» — их как раз надо найти, а не спрятать; на стенде таких 48.
    """
    db = SessionLocal()
    try:
        user = (db.query(User).join(User.role)
                .filter(User.is_active == 1).order_by(User.id).first())
        all_cnt = _registry(db, user, hide_archive=False, limit=1)["total"]
        left_cnt = _registry(db, user, hide_archive=True, limit=1)["total"]
        terminal_cnt = (db.query(SalesDeal)
                        .join(SalesStage, SalesStage.id == SalesDeal.our_stage_id)
                        .filter((SalesStage.is_terminal.is_(True))
                                | (SalesStage.is_lost.is_(True))).count())
        assert all_cnt - left_cnt == terminal_cnt, (
            f"спрятано {all_cnt - left_cnt} при {terminal_cnt} терминальных — "
            f"под нож попало что-то ещё")
    finally:
        db.close()
