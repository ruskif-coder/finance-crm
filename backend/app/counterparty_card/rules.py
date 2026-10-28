# -*- coding: utf-8 -*-
"""Правила карточки контрагента v2 (хендофф «контрикZ», 28.10.2026). Чистые функции: данные приходят словарями."""
from datetime import date
from typing import List, Optional

from app.contract_card.readiness import term_check, end_date

PLAN_WORD = {"ПЛАН ОПЛАТ": "План оплат", "ПЛАН ПОСТУПЛЕНИЙ": "План поступлений"}


def kind_of(income: float, expense: float) -> Optional[str]:
    """Тип по обороту: только приход — income, только расход — expense, оба — mixed; оборота нет — None."""
    if income and expense:
        return "mixed"
    return "income" if income else "expense" if expense else None


def _ru(d) -> str:
    s = str(d or "")[:10]
    return f"{s[8:10]}.{s[5:7]}.{s[0:4]}" if len(s) == 10 else s


def plan_reason(plans: List[dict]) -> Optional[str]:
    """Строка под сальдо: самая свежая плановая операция (статья, период, счёт, банк) и сколько ещё в плане.
    `plans` — плановые операции, самая свежая первой."""
    if not plans:
        return None
    p = plans[0]
    text = f"{PLAN_WORD.get(p['status'], p['status'])} {p.get('article') or 'без статьи'}"
    if p.get("period"):
        text += f" за {p['period']}"
    if p.get("invoice"):
        text += f", счёт № {p['invoice']}" + (f" от {_ru(p['invoice_date'])}" if p.get("invoice_date") else "")
    text += f" — банк {p.get('bank') or 'не указан'}"
    if len(plans) > 1:
        text += f"; и ещё {len(plans) - 1} в плане"
    return text


def no_contract_warning(contracts: List[dict], last_op_date: Optional[date], on: date) -> Optional[str]:
    """Операции идут после окончания ВСЕХ договоров контрагента (и ни один не продлевается) — жёлтая плашка. Без договоров — None:
    пустой блок договоров и так виден."""
    if not contracts or last_op_date is None:
        return None
    ends = []
    for k in contracts:
        if term_check(k.get("end_date_text"), k.get("prolongation"), last_op_date)["ok"]:
            return None
        end = end_date(k.get("end_date_text"))
        if end:
            ends.append(end)
    if not ends:
        return None
    last_end = max(ends)
    return (f"Договор истёк {last_end:%d.%m.%Y}, пролонгация не задана — операции {last_op_date.year} года идут без действующего договора"
            if len(contracts) == 1 else
            f"Все договоры истекли (последний — {last_end:%d.%m.%Y}), а операции {last_op_date.year} года идут без действующего договора")
