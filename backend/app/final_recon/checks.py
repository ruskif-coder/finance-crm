# -*- coding: utf-8 -*-
"""Проверки перехода стадий для контура аккаунта (спринт 4). Регистрируются в общем реестре `sales/stage_checks` из пакета —
в реестре только импорт этого модуля."""
from sqlalchemy import text

from app.sales.stage_checks import Ctx, Result, _not_yet, _ok, register

RECON_STAGE = "Итоговая сверка"
DO_PHASE = "Документооборот (ДО)"


@register("account_finished", "Сделка завершена аккаунтом",
          "В контуре аккаунта РК нет: сделку в документооборот ведёт аккаунт — кнопкой «Завершить» и через «Итоговую сверку»")
def _account_finished(c: Ctx) -> Result:
    """Пара к «РК завершена трафиком» для контура аккаунта (владелец 14.10.2026). Выполнено, если сделка сейчас на «Итоговой сверке»
    или уже в документообороте (движение внутри ДО), либо когда-либо проходила «Итоговую сверку»."""
    row = c.db.execute(text("""
        SELECT st.name, ph.name FROM sales_stages st LEFT JOIN sales_stage_phases ph ON ph.id = st.phase_id
         WHERE st.id = :s"""), {"s": c.deal.our_stage_id}).first()
    if row and (row[0] == RECON_STAGE or row[1] == DO_PHASE):
        return _ok()
    passed = c.db.execute(text("""
        SELECT 1 FROM sales_deal_stage_history h JOIN sales_stages st ON st.id = h.to_stage_id
         WHERE h.deal_id = :d AND st.name = :n LIMIT 1"""), {"d": c.deal.id, "n": RECON_STAGE}).first()
    return _ok() if passed else _not_yet("сделка не прошла «Итоговую сверку» — нажмите «Завершить» на «В размещении»")
