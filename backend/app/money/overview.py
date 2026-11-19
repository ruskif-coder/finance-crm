# -*- coding: utf-8 -*-
"""Экран «Деньги» (бывшая «Сводка руководителя»), хендофф docs/design_handoff_money_navy.zip, 18.11.2026.

Сервер отдаёт ФАКТЫ: счета и их остатки, открытые плановые операции с ожидаемой датой, привычную задержку клиента,
качество данных, помесячный факт. Календарь на 14 дней, «можно тратить», сценарии «что если» и накопительный прогноз
экран считает сам из этого набора — так «что если» пересчитывается мгновенно, без запроса.

Чего в учёте пока нет (аудит 18.11.2026, docs/Деньги - процессы и учёт.md) и что поэтому НЕ выдумывается здесь:
  · выписок нет — «свежесть» счёта = дата последней оплаченной операции по банку, а не выписки;
  · у плана оплат почти никогда нет даты — такие уходят отдельной строкой `undated_out`, в календарь не попадают;
  · срок поступления — тот же, что в «Операциях» и в дебиторке (`receivables._due_date`), без договора; обычная дата —
    начало следующего периода + среднее время оплаты контрагента (`receivables.avg_pay_days`).
"""
from collections import defaultdict
from datetime import date, timedelta
import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Article, Counterparty, Operation
from app.receivables import _due_date, _term_days_for_counterparty, avg_pay_days_db, next_period_start
from app.banks import BANKS

PAID, PLAN_IN, PLAN_OUT = 'ОПЛАЧЕНО', 'ПЛАН ПОСТУПЛЕНИЙ', 'ПЛАН ОПЛАТ'
BANK_ABBR = {'АльфаБанк': 'АБ', 'ОПТ Банк': 'ОПТ', 'Совкомбанк': 'СВК', 'Наличные': '₽'}
QUALITY_WINDOW_DAYS = 90     # качество данных — по свежим операциям: старый хвост разбирать некому и незачем
LEGAL = re.compile(r'\b(ООО|АО|ПАО|ЗАО|ОАО|ИП|НКО|АНО)\b|["«»“”]', re.I)


def short_name(name):
    """«АЛЬФАРМ ООО» → «АЛЬФАРМ»: в карточках экрана правовая форма — шум, имя и так узнаётся."""
    s = LEGAL.sub(' ', name or '').strip()
    return re.sub(r'\s+', ' ', s) or (name or '—')


def amount_of(op):
    return float(op.income or 0) if (op.income or 0) > 0 else float(op.expense or 0)


def duplicate_pairs(rows):
    """Похоже на дубль: тот же контрагент и сумма, даты в пределах 3 дней. rows — [(id, cp_id, amount, date, root)].

    Части одной цепочки оплат (общий корень) дублями не считаются — это транши, а не повтор."""
    by_key = defaultdict(list)
    for r in rows:
        if r[1] is not None and r[2] and r[3]:
            by_key[(r[1], round(r[2], 2))].append(r)
    hits = set()
    for group in by_key.values():
        group.sort(key=lambda r: r[3])
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if (b[3] - a[3]).days > 3:
                    break
                if a[4] is not None and a[4] == b[4]:
                    continue
                hits.update((a[0], b[0]))
    return hits


def _accounts(db, today):
    opening = {r.bank: float(r.opening_balance or 0) for r in db.execute(text('SELECT bank, opening_balance FROM bank_balances'))}
    since = today - timedelta(days=365)
    agg = db.execute(text(
        "SELECT bank, coalesce(sum(income),0) i, coalesce(sum(expense),0) e, max(date) last, "
        "coalesce(sum(income) filter (where date >= :s),0) i12, coalesce(sum(expense) filter (where date >= :s),0) e12 "
        "FROM operations WHERE status = :paid GROUP BY bank"), {'paid': PAID, 's': since}).fetchall()
    by = {r.bank: r for r in agg}
    out = []
    for bank in BANKS:
        r = by.get(bank)
        out.append({'bank': bank, 'abbr': BANK_ABBR.get(bank, bank[:3].upper()),
                    'balance': opening.get(bank, 0) + (float(r.i) - float(r.e) if r else 0),
                    'last_op': r.last if r else None, 'in12': float(r.i12) if r else 0, 'out12': float(r.e12) if r else 0})
    return out


def _plans(db, today, cps, arts):
    """Открытые плановые операции с ожидаемой датой. Поступление — срок как в «Операциях»; оплата — её дата, если есть."""
    rows = db.query(Operation).filter(Operation.status.in_((PLAN_IN, PLAN_OUT))).all()
    plans, undated = [], {'count': 0, 'sum': 0.0}
    for op in rows:
        cp = cps.get(op.counterparty_id)
        art = arts.get(op.article_id)
        incoming = op.status == PLAN_IN and (op.income or 0) > 0
        if not incoming and not (op.expense or 0) > 0:
            continue
        due = _due_date(op.period, _term_days_for_counterparty(cp)) if incoming else op.date
        if due is None and not incoming:
            undated['count'] += 1
            undated['sum'] += amount_of(op)
            continue
        plans.append({'id': op.id, 'kind': 'in' if incoming else 'out', 'amount': amount_of(op),
                      'cp_id': op.counterparty_id, 'who': short_name(cp.name) if cp else (op.description or '—'),
                      'cat': (art.group if art else None) or 'без статьи', 'article': art.name if art else None,
                      'due': due, 'invoice': op.invoice, 'ds_num': op.ds_num, 'period': op.period})
    return plans, undated


def _quality(db, today):
    since = today - timedelta(days=QUALITY_WINDOW_DAYS)
    ops = db.query(Operation.id, Operation.counterparty_id, Operation.income, Operation.expense, Operation.date,
                   Operation.parent_operation_id, Operation.article_id, Operation.invoice, Operation.document_link,
                   Operation.status).filter(Operation.date >= since).all()

    def row(key, title, picked):
        return {'key': key, 'title': title, 'count': len(picked),
                'sum': round(sum(float(o.income or 0) + float(o.expense or 0) for o in picked), 2)}
    dup_ids = duplicate_pairs([(o.id, o.counterparty_id, float(o.income or 0) + float(o.expense or 0), o.date,
                                o.parent_operation_id or o.id) for o in ops if o.status == PAID])
    return [
        row('no_article', 'Не разнесено по статьям', [o for o in ops if o.article_id is None]),
        row('no_counterparty', 'Без контрагента', [o for o in ops if o.counterparty_id is None]),
        row('no_document', 'Без закрывающего документа',
            [o for o in ops if o.status == PAID and not (o.invoice or '').strip() and not (o.document_link or '').strip()]),
        row('duplicates', 'Похоже на дубль', [o for o in ops if o.id in dup_ids]),
    ]


def _months(db, today, opening_total):
    """Факт по оплаченным по месяцам: 12 последних (включая текущий), остаток на конец месяца."""
    first = date(today.year - 1, today.month, 1)
    before = db.execute(text("SELECT coalesce(sum(income),0) - coalesce(sum(expense),0) FROM operations "
                             "WHERE status = :p AND date < :d"), {'p': PAID, 'd': first}).scalar() or 0
    rows = db.execute(text("SELECT to_char(date, 'YYYY-MM') m, coalesce(sum(income),0) i, coalesce(sum(expense),0) e "
                           "FROM operations WHERE status = :p AND date >= :d GROUP BY 1"), {'p': PAID, 'd': first}).fetchall()
    by = {r.m: (float(r.i), float(r.e)) for r in rows}
    bal = opening_total + float(before)
    out, y, m = [], first.year, first.month
    for _ in range(13):
        key = f'{y}-{m:02d}'
        i, e = by.get(key, (0.0, 0.0))
        bal += i - e
        out.append({'month': key, 'income': i, 'expense': e, 'balance_end': round(bal, 2)})
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def build(db: Session, today: date) -> dict:
    cps = {c.id: c for c in db.query(Counterparty).all()}
    arts = {a.id: a for a in db.query(Article).all()}
    accounts = _accounts(db, today)
    plans, undated = _plans(db, today, cps, arts)
    # «Как платят на деле» (владелец 18.11.2026): обычная дата = 1-е число следующего периода + среднее время оплаты
    # контрагента — то же число, что колонка «Опл.» в реестре и «обычно платят» в дебиторке. Нет истории — по сроку.
    usual = avg_pay_days_db(db)
    for p in plans:
        p['usual'], p['delay'] = None, 0
        avg = usual.get(p['cp_id'], (None, 0))[0] if p['kind'] == 'in' else None
        start = next_period_start(p['period']) if avg is not None else None
        if start is not None:
            p['usual'] = start + timedelta(days=avg)
            p['delay'] = (p['usual'] - p['due']).days
    opening_total = sum(float(r.opening_balance or 0) for r in db.execute(text('SELECT opening_balance FROM bank_balances')))
    return {'today': today, 'accounts': accounts, 'balance_total': round(sum(a['balance'] for a in accounts), 2),
            'plans': plans, 'undated_out': undated, 'quality': _quality(db, today),
            'months': _months(db, today, opening_total)}
