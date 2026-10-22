# -*- coding: utf-8 -*-
"""Кнопки аккаунта для контура аккаунта (владелец 14.10.2026): «Запустить» — «Готовятся к старту» → «В размещении», «Завершить» —
«В размещении» → «Итоговая сверка». Переход тем же путём, что диалог движения (`stage_move`): требования стадии, история, уведомления."""
from typing import Optional

from app.final_recon import flow
from app.sales import stage_move
from app.sales.catalog import Catalog

ACTIONS = {
    "launch": ("Готовятся к старту", "В размещении", "Запуск в контуре аккаунта"),
    "finish": ("В размещении", "Итоговая сверка", "Завершение в контуре аккаунта"),
}


class LaunchError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _by_name(cat: Catalog, name: str):
    return next((s for s in cat.by_id.values() if s.name == name), None)


def available(db, deal, cat: Optional[Catalog] = None) -> Optional[str]:
    """Какая кнопка сейчас у сделки: `launch` / `finish` / None (полный цикл или стадия не та)."""
    if not flow.is_account(db, deal):
        return None
    cat = cat or Catalog(db)
    cur = cat.by_id.get(deal.our_stage_id)
    return next((k for k, (src, _, _) in ACTIONS.items() if cur and cur.name == src), None)


def run(db, deal, action: str, user) -> dict:
    if action not in ACTIONS:
        raise LaunchError(400, "Неизвестное действие")
    if not flow.is_account(db, deal):
        raise LaunchError(409, "Сделку полного цикла запускает и завершает трафик")
    src, dst, reason = ACTIONS[action]
    cat = Catalog(db)
    cur = cat.by_id.get(deal.our_stage_id)
    if not cur or cur.name != src:
        raise LaunchError(409, f"Кнопка работает со стадии «{src}», а сделка на «{cur.name if cur else '—'}»")
    target = _by_name(cat, dst)
    if target is None:
        raise LaunchError(500, f"Стадии «{dst}» нет в каталоге")
    plan = stage_move.plan_move(db, deal, target, cat)
    if not stage_move.may_move(plan):
        raise LaunchError(409, stage_move.refusal_text(plan))
    res = stage_move.apply_move(db, deal, target, user, reason=reason, catalog=cat)
    return {"moved": res["moved"], "stage": dst}
