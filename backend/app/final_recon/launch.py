# -*- coding: utf-8 -*-
"""Кнопки аккаунта для контура аккаунта (владелец 14.10.2026): «Запустить» — «Готовятся к старту» → «В размещении», «Завершить» —
«В размещении» → «Итоговая сверка». Переход тем же путём, что диалог движения (`stage_move`): требования стадии, история, уведомления."""
from typing import Optional

from app.final_recon import flow
from app.sales import stage_move
from app.sales import stage_slots as SS
from app.sales.catalog import Catalog

ACTIONS = {
    "launch": (SS.PREP, SS.LIVE, "Запуск в контуре аккаунта"),
    "finish": (SS.LIVE, SS.RECON, "Завершение в контуре аккаунта"),
}


class LaunchError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _by_name(cat: Catalog, name: str):
    return next((s for s in cat.by_id.values() if s.name == name), None)


def available(db, deal, cat: Optional[Catalog] = None) -> Optional[str]:
    """Какая кнопка сейчас у сделки: `launch` / `finish` / None (полный цикл или стадия не та)."""
    if not flow.has_account_buttons(db, deal):
        return None
    cat = cat or Catalog(db)
    cur = cat.by_id.get(deal.our_stage_id)
    return next((k for k, (src, _, _) in ACTIONS.items() if cur and cur.name == src), None)


PRIO_SELF_LAUNCH = ("У приоритезации сделка переходит «В размещении» сама — при запуске первой согласованной площадки "
                    "с ЕРИД (блок «Приоритезация», «Запустить»)")


def button(db, deal, cat: Optional[Catalog] = None) -> Optional[str]:
    """Кнопка шапки сделки (владелец 16.11.2026): у приоритезации «Запустить» нет — оно давало проскочить ожидание согласования
    площадок; сделку переводит запуск первой площадки (`prio.launch._deal_goes_live`, ему нужен `available`). «Завершить» — есть."""
    return None if self_launch(db, deal, cat) else available(db, deal, cat)


def self_launch(db, deal, cat: Optional[Catalog] = None) -> bool:
    """Приоритезация на стадии старта: переход «В размещении» делает запуск первой площадки — шапке нечего предлагать."""
    return available(db, deal, cat) == "launch" and flow.of_deal(db, deal) == flow.PRIO


def run_button(db, deal, action: str, user) -> dict:
    """Нажатие кнопки шапки — то же правило, что её показ (`button`): прямой запрос мимо экрана не переведёт приоритезацию."""
    if action == "launch" and flow.of_deal(db, deal) == flow.PRIO:
        raise LaunchError(409, PRIO_SELF_LAUNCH)
    return run(db, deal, action, user)


def run(db, deal, action: str, user) -> dict:
    if action not in ACTIONS:
        raise LaunchError(400, "Неизвестное действие")
    if not flow.has_account_buttons(db, deal):
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
