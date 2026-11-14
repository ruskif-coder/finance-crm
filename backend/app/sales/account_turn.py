# -*- coding: utf-8 -*-
"""«Чей ход» строки дашборда аккаунта v5 — «Мои сделки» (13.11.2026, design_handoff_account_dashboard_v5, функция `todo(d)` эталона).

Ось, которой не было: ваш ход (кнопка у аккаунта) · ждём кого (ход у другого участника) · всё хорошо (ход ни у кого не просрочен).
Считается ПОВЕРХ `queue_state`: его факты и кнопки не меняются, здесь только классификация. Где эталон расходится с нашим, берём
наше (владелец 13.11: «по тому, что у нас уже реализовано, ориентируйся на нас»):
  · у контура аккаунта и приоритезации «Запустить» / «Завершить» — кнопки аккаунта, значит ход его;
  · после «ждём 1С» у аккаунта действий нет — ЭДО, подпись, оплату ведут финансы.

`col` — подколонка песочницы: готовим МП · у клиента · пора напомнить · зависли (пороги эталона: 14 и 45 дней у клиента)."""
from typing import Optional

from app.final_recon import flow as FLOW
from app.sales.urgency import DealFacts, lag_alarm

NUDGE_DAYS = 14          # МП у клиента дольше — пора напомнить (допущение эталона, 13.11.2026)
STUCK_DAYS = 45          # дольше — завис
BOOKING_DAYS = 15        # бронь подтверждают за 15 дней до старта (`urgency.BOOKING_CONFIRM_DAYS`)
ACCOUNT_LAUNCH = (FLOW.ACCOUNT, FLOW.PRIO)   # «Запустить» / «Завершить» — кнопки аккаунта (`flow.has_account_buttons`)
ASSEMBLY_KEYS = {"creatives_accepted", "erid_issued"}   # пункты матрицы, из которых состоит сборка


def external_launch(flow: str, applies) -> bool:
    """Запуск во внешней системе: контур аккаунта, и матрица учёта по услугам не требует от сделки ни креативов, ни ЕРИД
    (владелец 14.11.2026). Одно правило для строки очереди, расхлопа и кнопки «Подтвердить запуск». `applies` None — «всё
    применимо» (сборка руками в тестах)."""
    return flow == FLOW.ACCOUNT and applies is not None and not (applies & ASSEMBLY_KEYS)


def _t(mine: bool, who: Optional[str] = None, good: bool = False, col: Optional[str] = None) -> dict:
    return {"mine": mine, "who": who, "good": good, "col": col}


def _sandbox(b) -> dict:
    if b.slot == "mp_prep":
        return _t(True, col="prep")
    days = b.stage_days or 0
    if days > STUCK_DAYS:
        return _t(True, col="stuck")
    if days >= NUDGE_DAYS:
        return _t(True, col="nudge")
    return _t(False, "клиент", col="client")


def _prep(b) -> dict:
    if b.flow in ACCOUNT_LAUNCH:
        return _t(True)                                  # собирает и запускает сам
    done, total = b.creatives or (0, 0)
    if not b.sets or not total:
        return _t(True)                                  # креативов нет — запуск стоит
    if done < total:
        return _t(False, "площадки")                     # площадки согласуют баннер
    if b.sets and not b.kktu and len(b.erids) < b.sets:
        return _t(True)                                  # ККТУ бренда — ход аккаунта
    return _t(False, "трафик", good=True)                # ЕРИД, РК — у трафика и ОРД


def _live(b) -> dict:
    dl = b.delivery or {}
    own = b.flow in ACCOUNT_LAUNCH
    if dl.get("flight_over"):
        return _t(True) if own else _t(False, "трафик — завершить РК")   # «Завершить» / срок вышел, трафик не закрыл РК
    if lagging(dl):
        # Полный цикл: темп ведёт трафик — ход его, строка красная тревогой (владелец 14.11.2026); свой запуск — у аккаунта.
        return _t(True) if own else _t(False, "трафик — отставание")
    # Внешний запуск (контур аккаунта) — наших площадок нет, крутит внешняя система (владелец 14.11.2026)
    who = {FLOW.ACCOUNT: "внешняя система", FLOW.PRIO: "площадки"}.get(b.flow, "трафик")
    return _t(False, who, good=True)


def lag_of(dl: dict):
    """Отставание открутки за порогом тревоги (`urgency.lag_alarm`) или None; после конца флайта недокрут — итог, не отставание."""
    if not dl or dl.get("flight_over"):
        return None
    return lag_alarm(DealFacts(delivery_done_pct=dl.get("done_pct"), delivery_pace=dl.get("closed_pace")))


def lagging(dl: dict) -> bool:
    return lag_of(dl) is not None


def _recon(b) -> dict:
    r = (b.checks or {}).get("fact_collected")
    if b.flow == "полный цикл" and r is not None and getattr(r, "state", None) == "not_yet":
        return _t(False, "трафик")                       # факт по размещениям снимает трафик (не площадки; «неприменимо» — не ждём)
    return _t(True)                                      # подтвердить сверку, «Отправить в ДО»


def turn(b, action: Optional[dict]) -> dict:
    """{mine, who, good, col} для строки. `action` — кнопка `queue_state` (для стадий, где наша логика уже решила)."""
    s = b.slot
    if s in ("mp_prep", "mp_sent"):
        return _sandbox(b)
    if s == "booking":
        if b.start_in is None or b.start_in <= BOOKING_DAYS:
            return _t(True)
        return _t(False, "срок не подошёл", good=True)
    if s == "prep":
        return _prep(b)
    if s == "live":
        return _live(b)
    if s == "recon":
        return _recon(b)
    if s == "closing":
        return _t(False, "бухгалтер")
    if s in ("edo", "pay"):
        return _t(False, "финансы")
    if s == "ord":
        return _t(False, "ОРД", good=True)
    return _t(bool(action))                              # черновик / согласование ДС, неразобранная стадия
