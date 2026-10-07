# -*- coding: utf-8 -*-
"""Сроки оплаты и старение дебиторки.

Вынесено из `routers/reports.py` 07.10.2026: этим пользуются и отчёты, и уведомления (`notify/scanner.py`), а крону
слой HTTP не нужен — иначе процесс раздувается (см. tests/test_cron_runs_without_routers.py). Роутер реэкспортирует имена.
"""


def _period_bounds(period):
    """Возвращает (start_date, end_date) периода ('YYYY-MM' или 'Qn YYYY'), либо (None, None)."""
    import re, calendar
    from datetime import date as date_cls
    from app import periods

    if not period:
        return None, None
    p = period.strip()

    m = re.match(r'^(\d{4})-(\d{2})$', p)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        last_day = calendar.monthrange(year, month)[1]
        return date_cls(year, month, 1), date_cls(year, month, last_day)

    parsed = periods.parse_quarter(p)
    if parsed:
        year, q = parsed
        start_month = (q - 1) * 3 + 1
        end_month = start_month + 2
        last_day = calendar.monthrange(year, end_month)[1]
        return date_cls(year, start_month, 1), date_cls(year, end_month, last_day)

    return None, None

GRACE_DAYS = 30          # буфер после срока оплаты, в течение которого долг считается "текущим", а не просроченным

DEFAULT_TERM_DAYS = 60   # стандартный срок отсрочки для контрагентов без явно заданного term_days

def _term_days_for_counterparty(cp):
    """Срок отсрочки в днях для контрагента: явное значение term_days из реестра контрагентов,
    либо стандартный срок (DEFAULT_TERM_DAYS), если оно не задано."""
    if cp is not None and cp.term_days is not None:
        return cp.term_days
    return DEFAULT_TERM_DAYS

def _due_date(period, term_days):
    """Срок оплаты = первый день месяца, следующего за периодом операции, + срок отсрочки контрагента."""
    from datetime import timedelta
    _, end = _period_bounds(period)
    if not end:
        return None
    date_basis = end + timedelta(days=1)
    return date_basis + timedelta(days=term_days)

def _aging_bucket(due_date, today):
    """Возраст долга относительно срока оплаты (с учётом отсрочки контрагента):
    future  — срок оплаты ещё не наступил (план);
    current — срок наступил, просрочка в пределах GRACE_DAYS (текущая задолженность);
    overdue — просрочка больше GRACE_DAYS сверх срока оплаты."""
    if not due_date:
        return 'unknown'
    diff = (today - due_date).days
    if diff < 0:
        return 'future'
    if diff <= GRACE_DAYS:
        return 'current'
    return 'overdue'
