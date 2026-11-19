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


def avg_pay_days(rows):
    """Среднее время оплаты по контрагенту (владелец 18.11.2026): от 1-го числа месяца после периода операции до даты
    фактической оплаты, простое среднее по всем оплаченным операциям. Считается на лету — новая оплата меняет число сразу.

    rows — [(counterparty_id, period, paid_date)]. Оплата раньше начала следующего периода (предоплата) даёт минус —
    так и остаётся: это правда о контрагенте, а не ошибка. Строки без периода или даты пропускаются.
    Возвращает {counterparty_id: (среднее в днях, округлённое; число оплат)}.
    """
    from datetime import timedelta
    acc = {}
    for cp_id, period, paid in rows:
        if cp_id is None or paid is None:
            continue
        _, end = _period_bounds(period)
        if not end:
            continue
        s = acc.setdefault(cp_id, [0, 0])
        s[0] += (paid - (end + timedelta(days=1))).days
        s[1] += 1
    return {cp: (round(t / n), n) for cp, (t, n) in acc.items()}


def next_period_start(period):
    """1-е число месяца после периода (для квартала — после квартала): точка отсчёта «расчётного дня» и времени оплаты."""
    from datetime import timedelta
    _, end = _period_bounds(period)
    return end + timedelta(days=1) if end else None


def avg_pay_days_db(db):
    """avg_pay_days по всем оплаченным операциям базы — одна точка для реестра контрагентов, дебиторки и экрана «Деньги»."""
    from app.models import Operation
    rows = db.query(Operation.counterparty_id, Operation.period, Operation.date).filter(
        Operation.status == 'ОПЛАЧЕНО', Operation.counterparty_id.isnot(None), Operation.date.isnot(None)).all()
    return avg_pay_days(rows)


def docs_of_operations(db, op_ids):
    """Документы наших операций для дебиторки (владелец 18.11.2026: «глаз» у счёта и у ДС/ПР): операция, рождённая мостом
    мастер-сделки, знает свой комплект УПД → ДС и PDF счёта 1С. {op_id: {kit_id, inv_pdf_id, annex_id, annex_external}}.
    Ручные операции (номер ДС текстом) документов в системе не имеют — их в ответе нет."""
    from sqlalchemy import text
    if not op_ids:
        return {}
    rows = db.execute(text("""
        SELECT o.id AS op_id, k.id AS kit_id, k.annex_id, a.origin,
               (SELECT f.id FROM master_deal_files f WHERE f.master_deal_id = k.master_deal_id AND f.upd_no = k.upd_no
                  AND f.kind = 'счёт 1С' ORDER BY f.id DESC LIMIT 1) AS inv_pdf_id
          FROM operations o JOIN master_deal_upds k ON k.id = o.master_deal_upd_id
          LEFT JOIN sales_annexes a ON a.id = k.annex_id
         WHERE o.id = ANY(:ids)"""), {"ids": list(op_ids)}).mappings().all()
    from app.sales.annex_external import ORIGIN
    return {r["op_id"]: {"kit_id": r["kit_id"], "inv_pdf_id": r["inv_pdf_id"], "annex_id": r["annex_id"],
                         "annex_external": r["origin"] == ORIGIN} for r in rows}


def managers_of_counterparties(db, cp_ids):
    """Ответственный по контрагенту для дебиторки (хендофф 19.11.2026: «ответственный под названием»). Своего поля у контрагента
    нет — берём аккаунта последней сделки, где контрагент платит (плательщик сделки, иначе её контрагент). {cp_id: имя}."""
    from sqlalchemy import text
    if not cp_ids:
        return {}
    rows = db.execute(text("""
        SELECT DISTINCT ON (coalesce(d.payer_counterparty_id, d.counterparty_id))
               coalesce(d.payer_counterparty_id, d.counterparty_id) AS cp, r.name
          FROM sales_deals d JOIN sales_reps r ON r.id = d.account_manager_id
         WHERE coalesce(d.payer_counterparty_id, d.counterparty_id) = ANY(:ids)
         ORDER BY coalesce(d.payer_counterparty_id, d.counterparty_id), d.id DESC"""), {"ids": list(cp_ids)}).fetchall()
    return {r.cp: r.name for r in rows}
