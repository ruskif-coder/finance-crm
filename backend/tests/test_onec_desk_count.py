# -*- coding: utf-8 -*-
"""Счётчик «Закрывающих документов» в меню (19.11.2026): число заявок во вкладке «Заявки на документы».

Сломает: счётчик посчитан своим правилом, а не тем, что показывает экран, — бухгалтер видит в меню «3», а во вкладке 2
(архивные пакеты, вернувшиеся аккаунту или уже внесённые комплекты попали в число)."""
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.onec_desk import board as B
from app.onec_desk.service import DONE, OPEN
from app.routers import onec_desk as R


def _shown(s) -> int:
    return sum(1 for r in B.board(s)["requests"] if r["status"] == "wait")


def test_menu_count_equals_wait_tab_of_the_board():
    """Внесённый комплект стенда на время транзакции снова «ждёт» — без этого на пустой очереди сравнивались бы два нуля."""
    s = SessionLocal()
    try:
        kid = s.execute(text("SELECT id FROM master_deal_upds WHERE onec_state = :d ORDER BY id LIMIT 1"), {"d": DONE}).scalar()
        if kid is not None:
            s.execute(text("UPDATE master_deal_upds SET onec_state = NULL WHERE id = :k"), {"k": kid})
            s.execute(text("UPDATE master_deals SET status = :o WHERE id = (SELECT master_deal_id FROM master_deal_upds WHERE id = :k)"),
                      {"o": sorted(OPEN)[0], "k": kid})
            s.flush()
            assert _shown(s) >= 1
        assert R.desk_count(db=s, user=None) == {"waiting": _shown(s)}
    finally:
        s.rollback()
        s.close()
