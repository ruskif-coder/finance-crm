from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text, case
from app.database import get_db
from app.models import Operation, Article, User
from app.permissions import require_permission, require_any_permission
from app.audit import log_action
from pydantic import BaseModel
from typing import Optional, List
from app import timez

router = APIRouter()

BANKS_ORDER = ['АльфаБанк', 'ОПТ Банк', 'Совкомбанк', 'Наличные']

QUARTER_MONTHS = {
    'Q1': ['01', '02', '03'],
    'Q2': ['04', '05', '06'],
    'Q3': ['07', '08', '09'],
    'Q4': ['10', '11', '12'],
}

def expand_quarter_rows(rows):
    """Разбивает квартальные периоды на 3 месяца равными долями"""
    import re
    expanded = []
    for r in rows:
        p = r.period or ''
        match = re.match(r'^(Q[1-4])\s+(\d{4})$', p)
        if match:
            q, year = match.group(1), match.group(2)
            months = QUARTER_MONTHS.get(q, [])
            for m in months:
                expanded.append({
                    'period': f'{year}-{m}',
                    'bank': r.bank,
                    'total_income': (r.total_income or 0) / 3,
                    'total_expense': (r.total_expense or 0) / 3,
                    'income_count': (getattr(r, 'income_count', 0) or 0) / 3,
                    'expense_count': (getattr(r, 'expense_count', 0) or 0) / 3,
                })
        else:
            expanded.append({
                'period': p,
                'bank': r.bank,
                'total_income': r.total_income or 0,
                'total_expense': r.total_expense or 0,
                'income_count': getattr(r, 'income_count', 0) or 0,
                'expense_count': getattr(r, 'expense_count', 0) or 0,
            })
    return expanded


def _expand_quarter_rows_dict(rows):
    """То же что expand_quarter_rows, но принимает dict-строки (уже имеют все поля)."""
    import re
    expanded = []
    for r in rows:
        p = r.get('period') or ''
        match = re.match(r'^(Q[1-4])\s+(\d{4})$', p)
        if match:
            q, year = match.group(1), match.group(2)
            months = QUARTER_MONTHS.get(q, [])
            for m in months:
                expanded.append({**r, 'period': f'{year}-{m}',
                    'total_income': r['total_income'] / 3,
                    'total_expense': r['total_expense'] / 3,
                    'income_count': r.get('income_count', 0) / 3,
                    'expense_count': r.get('expense_count', 0) / 3,
                })
        else:
            expanded.append(r)
    return expanded



@router.get("/dds")
def get_dds(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    bank: Optional[str] = None,
    group_by: Optional[str] = 'period',
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("dashboard", "view"))
):
    # Выбираем группировку: по периоду или по дате операции
    if group_by == 'date':
        group_col = func.to_char(Operation.date, 'YYYY-MM')
    else:
        group_col = Operation.period

    query = db.query(
        group_col.label("period"),
        Operation.bank,
        func.sum(Operation.income).label("total_income"),
        func.sum(Operation.expense).label("total_expense"),
        func.sum(case((Operation.income > 0, 1), else_=0)).label("income_count"),
        func.sum(case((Operation.expense > 0, 1), else_=0)).label("expense_count"),
    )
    # По дате — только фактически оплаченные операции (кассовый взгляд: реальное движение денег).
    # По периоду — все операции периода, включая план (начислительный взгляд: что отнесено к периоду
    # независимо от факта оплаты). Статусов в системе три: ОПЛАЧЕНО, ПЛАН ПОСТУПЛЕНИЙ, ПЛАН ОПЛАТ.
    if group_by == 'date':
        query = query.filter(Operation.status == 'ОПЛАЧЕНО').filter(Operation.date.isnot(None))
    else:
        query = query.filter(Operation.period.isnot(None))
    query = query.group_by(group_col, Operation.bank).order_by(group_col)

    # Фильтр по диапазону дат:
    #  - group_by='date'   — по to_char(date) в SQL (date всегда YYYY-MM-DD);
    #  - group_by='period' — НЕ здесь: период хранится как 'Q1 2026', и SQL-сравнение
    #    было бы лексическим ('Q…' > '2…'), молча отбрасывая квартальные строки.
    #    Для периода фильтруем ПОСЛЕ разворачивания кварталов в месяцы (см. ниже) —
    #    так же, как в /pl и /plan-fact.
    if date_from and group_by == 'date':
        query = query.filter(func.to_char(Operation.date, 'YYYY-MM') >= date_from)
    if date_to and group_by == 'date':
        query = query.filter(func.to_char(Operation.date, 'YYYY-MM') <= date_to)
    if bank:
        query = query.filter(Operation.bank == bank)

    rows = query.all()

    # Стартовые остатки
    opening_rows = db.execute(text("SELECT bank, opening_balance FROM bank_balances")).fetchall()
    opening = {r.bank: r.opening_balance for r in opening_rows}
    total_opening = sum(opening.values())

    # Разбиваем кварталы на месяцы при группировке по периоду
    if group_by == 'period':
        expanded_rows = expand_quarter_rows(rows)
    else:
        expanded_rows = [{'period': r.period, 'bank': r.bank,
            'total_income': r.total_income or 0, 'total_expense': r.total_expense or 0,
            'income_count': r.income_count or 0, 'expense_count': r.expense_count or 0,
        } for r in rows]

    # Фильтр по диапазону для group_by='period' — на развёрнутых месяцах (YYYY-MM),
    # где лексическое сравнение корректно (см. комментарий к SQL-фильтру выше).
    if group_by == 'period' and (date_from or date_to):
        expanded_rows = [r for r in expanded_rows
                         if (not date_from or (r['period'] or '') >= date_from)
                         and (not date_to or (r['period'] or '') <= date_to)]

    periods = {}
    banks = set()
    for r in expanded_rows:
        p = r['period'] or 'Без периода'
        b = r['bank'] or 'Не указан'
        banks.add(b)
        if p not in periods:
            periods[p] = {'period': p, 'total_income': 0, 'total_expense': 0, 'net': 0, 'income_count': 0, 'expense_count': 0, 'by_bank': {}}
        periods[p]['total_income'] += r['total_income']
        periods[p]['total_expense'] += r['total_expense']
        periods[p]['income_count'] += r.get('income_count', 0)
        periods[p]['expense_count'] += r.get('expense_count', 0)
        periods[p]['net'] = periods[p]['total_income'] - periods[p]['total_expense']
        if b not in periods[p]['by_bank']:
            periods[p]['by_bank'][b] = {'income': 0, 'expense': 0, 'net': 0}
        periods[p]['by_bank'][b]['income'] += r['total_income']
        periods[p]['by_bank'][b]['expense'] += r['total_expense']
        periods[p]['by_bank'][b]['net'] = periods[p]['by_bank'][b]['income'] - periods[p]['by_bank'][b]['expense']

    # Накопительный остаток с учётом стартовых
    cumulative = total_opening
    result = []
    for p in sorted(periods.keys()):
        row = periods[p]
        cumulative += row['net']
        row['cumulative'] = cumulative
        ic = row.get('income_count') or 0
        ec = row.get('expense_count') or 0
        row['avg_income'] = round(row['total_income'] / ic) if ic else 0
        row['avg_expense'] = round(row['total_expense'] / ec) if ec else 0
        result.append(row)

    return {'periods': result, 'banks': sorted(list(banks))}

@router.get("/dds/summary")
def get_dds_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("dashboard", "view"))
):
    total_income = db.query(func.sum(Operation.income)).filter(Operation.status == 'ОПЛАЧЕНО').scalar() or 0
    total_expense = db.query(func.sum(Operation.expense)).filter(Operation.status == 'ОПЛАЧЕНО').scalar() or 0
    plan_income_row = db.query(func.sum(Operation.income), func.count(Operation.id)).filter(Operation.status == 'ПЛАН ПОСТУПЛЕНИЙ').first()
    plan_income, income_count = (plan_income_row[0] or 0), (plan_income_row[1] or 0)
    plan_expense_row = db.query(func.sum(Operation.expense), func.count(Operation.id)).filter(Operation.status == 'ПЛАН ОПЛАТ').first()
    plan_expense, expense_count = (plan_expense_row[0] or 0), (plan_expense_row[1] or 0)

    # Обороты по банкам
    by_bank_rows = db.query(
        Operation.bank,
        func.sum(Operation.income).label("income"),
        func.sum(Operation.expense).label("expense"),
    ).filter(Operation.status == 'ОПЛАЧЕНО')\
     .group_by(Operation.bank).all()
    turnover = {r.bank: {'income': r.income or 0, 'expense': r.expense or 0} for r in by_bank_rows}

    # Стартовые остатки
    opening_rows = db.execute(text("SELECT bank, opening_balance FROM bank_balances")).fetchall()
    opening = {r.bank: r.opening_balance for r in opening_rows}

    # Собираем карточки в нужном порядке
    by_bank = []
    total_balance = 0
    for bank in BANKS_ORDER:
        ob = opening.get(bank, 0)
        inc = turnover.get(bank, {}).get('income', 0)
        exp = turnover.get(bank, {}).get('expense', 0)
        balance = ob + inc - exp
        total_balance += balance
        by_bank.append({
            'bank': bank,
            'opening_balance': ob,
            'income': inc,
            'expense': exp,
            'balance': balance,
        })

    # Остаток долга по займам: получено минус возвращено по статьям с разметкой
    # «Займ — тело». Считается по ВСЕМ статусам сразу — и по факту, и по планам.
    # Смысл именно такой: плашка показывает долг, закрытие которого ещё не заведено
    # в план. Как только возврат запланирован, цифра обнуляется и плашка исчезает —
    # то есть она предупреждает ровно о том, о чём должна: прогнозный баланс держит
    # заёмные деньги, а их возврата в планах нет.
    # Период не фильтруется: долг — величина на момент, а не за отрезок. Заём,
    # взятый до выбранного периода и не возвращённый, обязан быть виден.
    loan_row = db.query(func.sum(Operation.income), func.sum(Operation.expense))        .join(Article, Article.id == Operation.article_id)        .filter(Article.pl_line == 'loan_body').first()
    loan_debt = (loan_row[0] or 0) - (loan_row[1] or 0)

    return {
        'total_income': total_income,
        'total_expense': total_expense,
        'net': total_income - total_expense,
        # Отрицательное значение означало бы, что вернули больше, чем брали, —
        # это ошибка разметки, а не отрицательный долг. Наружу отдаём только долг.
        'loan_debt': loan_debt if loan_debt > 0 else 0,
        'loan_overpaid': -loan_debt if loan_debt < 0 else 0,
        'plan_income': plan_income,
        'plan_expense': plan_expense,
        'income_count': income_count,
        'expense_count': expense_count,
        'total_balance': total_balance,
        'by_bank': by_bank,
    }

# Порядок групп в P&L
UNMAPPED_GROUP = 'ТРЕБУЕТ РАЗМЕТКИ'

# Порядок разделов отчёта. Раньше этот же список решал и что вообще попадёт в P&L:
# группа статьи сравнивалась с ним напрямую, поэтому группы, которых здесь не было
# («Сотрудники» и «Офис» — 100,6 млн расходов), молча выпадали из отчёта. Теперь
# раздел вычисляется из Article.pl_line (см. PL_LINE_TO_GROUP), а список задаёт
# только порядок вывода, и любая статья гарантированно попадает в один из разделов.
PL_GROUPS_ORDER = ['ВЫРУЧКА', 'СЕБЕСТОИМОСТЬ', 'ОПЕРАЦИОННЫЕ', 'МАРКЕТИНГ',
                   UNMAPPED_GROUP, 'НАЛОГИ', 'НЕ В P&L']

# Строка отчёта из справочника → раздел этого (кассового) отчёта. Отображение
# полное: у него нет варианта «не нашлось», иначе деньги снова начнут исчезать.
# Финансовые и прочие расходы отдельных разделов здесь не имеют — в этом отчёте
# они всегда были частью операционных; развёрнутые строки есть в /finreport.
PL_LINE_TO_GROUP = {
    'revenue': 'ВЫРУЧКА',
    'cogs': 'СЕБЕСТОИМОСТЬ',
    'opex': 'ОПЕРАЦИОННЫЕ',
    'finance': 'ОПЕРАЦИОННЫЕ',
    'other': 'ОПЕРАЦИОННЫЕ',
    'marketing': 'МАРКЕТИНГ',
    'profit_tax': 'НАЛОГИ',
    'tax_other': 'НАЛОГИ',
    'excluded': 'НЕ В P&L',
}


TRANSIT_LABEL = 'ТРАНЗИТ (разница списания и поступления)'


def _is_transit(article: Optional[str]) -> bool:
    return 'транзит' in (article or '').lower()


def _collapse_transit(data: dict) -> None:
    """Сворачивает транзит до разницы «списано − поступило». Меняет data на месте.

    Транзит — деньги, проходящие через компанию насквозь: сам оборот не доход и не
    расход. Показанный полным оборотом (78,8 млн прихода против 88,1 расхода) он
    раздувал обе стороны отчёта. Реальный расход здесь — только разница, наценка на
    проходящих деньгах. Так же считает /finreport, поэтому отчёты не расходятся.

    Разница считается по каждому периоду отдельно и может выйти отрицательной —
    в месяце, где поступило больше, чем списано. Это не ошибка и не повод обнулять:
    иначе годовая сумма перестанет быть суммой месяцев.
    """
    for group in data.values():
        for sg_name, subgroup in group.items():
            for article in [a for a in subgroup if _is_transit(a)]:
                periods = subgroup.pop(article)
                dst = subgroup.setdefault(TRANSIT_LABEL, {})
                for p, v in periods.items():
                    cell = dst.setdefault(p, {'income': 0, 'expense': 0})
                    cell['expense'] += v['expense'] - v['income']


def _pl_group(pl_line: Optional[str], article_group: Optional[str]) -> str:
    """Раздел отчёта для статьи.

    `by_description` — статьи, где одна проводка содержит несколько назначений
    (единый налоговый платёж; кредиты, где вместе тело и проценты). Разложить их
    здесь нечем: строки сгруппированы по статье и периоду, текст платежа уже
    потерян. Поэтому для них — и только для них — берём группу из справочника,
    как было раньше. Разложение по назначению делает /finreport.
    """
    if pl_line == 'by_description':
        return article_group or UNMAPPED_GROUP
    return PL_LINE_TO_GROUP.get(pl_line or '', UNMAPPED_GROUP)

@router.get("/pl")
def get_pl(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("pl", "view"))
):
    import re

    query = db.query(
        Operation.period,
        Article.name.label("article"),
        Article.group.label("group"),
        Article.subgroup.label("subgroup"),
        Article.type.label("type"),
        Article.pl_line.label("pl_line"),
        func.sum(Operation.income).label("total_income"),
        func.sum(Operation.expense).label("total_expense"),
    ).outerjoin(Article, Operation.article_id == Article.id)\
     .filter(Operation.status == 'ОПЛАЧЕНО')\
     .group_by(Operation.period, Article.name, Article.group, Article.subgroup,
               Article.type, Article.pl_line)

    rows = query.all()

    # Нормализуем периоды (кварталы → месяцы)
    normalized = []
    for r in rows:
        p = r.period or ''
        # Раздел берём из разметки статьи, а не из её группы: группа отвечает за вид
        # справочника, разметка — за отчёт (одна группа собирает статьи с разной
        # судьбой, см. PL_LINE_TO_GROUP).
        grp = _pl_group(r.pl_line, r.group)
        match = re.match(r'^(Q[1-4])\s+(\d{4})$', p)
        if match:
            q, year = match.group(1), match.group(2)
            months = QUARTER_MONTHS.get(q, [])
            for m in months:
                normalized.append({
                    'period': f'{year}-{m}',
                    'article': r.article or 'Без статьи',
                    'group': grp,
                    'subgroup': r.subgroup or '',
                    'type': r.type,
                    'total_income': (r.total_income or 0) / 3,
                    'total_expense': (r.total_expense or 0) / 3,
                })
        else:
            normalized.append({
                'period': p,
                'article': r.article or 'Без статьи',
                'group': grp,
                'subgroup': r.subgroup or '',
                'type': r.type,
                'total_income': r.total_income or 0,
                'total_expense': r.total_expense or 0,
            })

    # Фильтруем по диапазону дат ПОСЛЕ нормализации кварталов
    if date_from:
        normalized = [r for r in normalized if r['period'] >= date_from]
    if date_to:
        normalized = [r for r in normalized if r['period'] <= date_to]

    # Собираем периоды и данные
    periods_set = sorted(set(r['period'] for r in normalized if r['period']))
    
    # Данные: {group: {subgroup: {article: {period: {income, expense}}}}}
    data = {}
    for r in normalized:
        g = r['group']
        sg = r.get('subgroup') or ''
        a = r['article']
        p = r['period']
        if g not in data:
            data[g] = {}
        if sg not in data[g]:
            data[g][sg] = {}
        if a not in data[g][sg]:
            data[g][sg][a] = {}
        if p not in data[g][sg][a]:
            data[g][sg][a][p] = {'income': 0, 'expense': 0}
        data[g][sg][a][p]['income'] += r['total_income']
        data[g][sg][a][p]['expense'] += r['total_expense']

    _collapse_transit(data)

    # Формируем структуру для фронтенда
    result_groups = []
    # Якоря итоговых строк P&L: рендерим их всегда (даже пустыми), иначе на фронте
    # пропадает подытог (ВАЛОВАЯ/EBITDA/ЧИСТАЯ), привязанный к наличию группы.
    ANCHOR_GROUPS = ("СЕБЕСТОИМОСТЬ", "МАРКЕТИНГ", "НАЛОГИ")
    for group in PL_GROUPS_ORDER:
        if group == 'НЕ В P&L':
            continue
        if group not in data and group not in ANCHOR_GROUPS:
            continue
        subgroups_list = []
        group_totals = {p: {'income': 0, 'expense': 0} for p in periods_set}

        for subgroup, articles_data in sorted(data.get(group, {}).items()):
            articles_list = []
            subgroup_totals = {p: {'income': 0, 'expense': 0} for p in periods_set}

            for article, periods_data in sorted(articles_data.items()):
                article_row = {'article': article, 'periods': {}}
                for p in periods_set:
                    inc = periods_data.get(p, {}).get('income', 0)
                    exp = periods_data.get(p, {}).get('expense', 0)
                    article_row['periods'][p] = {'income': inc, 'expense': exp}
                    subgroup_totals[p]['income'] += inc
                    subgroup_totals[p]['expense'] += exp
                    group_totals[p]['income'] += inc
                    group_totals[p]['expense'] += exp
                articles_list.append(article_row)

            subgroups_list.append({
                'subgroup': subgroup,
                'articles': articles_list,
                'totals': subgroup_totals,
            })

        result_groups.append({
            'group': group,
            'subgroups': subgroups_list,
            'totals': group_totals,
        })

    # Вспомогательная функция для суммирования по группе с новой структурой {subgroup: {article: {period: ...}}}
    def group_sum(group_name, field, period):
        total = 0
        for sg_data in data.get(group_name, {}).values():
            for art_data in sg_data.values():
                total += art_data.get(period, {}).get(field, 0)
        return total

    # Считаем итоговые метрики по периодам
    summary = {}
    for p in periods_set:
        revenue  = group_sum('ВЫРУЧКА',       'income',  p)
        cogs     = group_sum('СЕБЕСТОИМОСТЬ',  'expense', p)
        opex     = group_sum('ОПЕРАЦИОННЫЕ',   'expense', p)
        marketing= group_sum('МАРКЕТИНГ',      'expense', p)
        taxes    = group_sum('НАЛОГИ',         'expense', p)
        # Неразмеченное вычитается наравне с остальным: строка в отчёте — сигнал
        # «проставьте разметку», а не повод не считать эти деньги расходом.
        unmapped = group_sum(UNMAPPED_GROUP,   'expense', p)
        gross_profit = revenue - cogs
        ebitda       = gross_profit - opex - marketing
        net_profit   = ebitda - taxes - unmapped
        summary[p] = {
            'revenue':       revenue,
            'cogs':          cogs,
            'gross_profit':  gross_profit,
            'gross_margin':  round(gross_profit / revenue * 100, 1) if revenue else 0,
            'opex':          opex,
            'marketing':     marketing,
            'ebitda':        ebitda,
            'ebitda_margin': round(ebitda / revenue * 100, 1) if revenue else 0,
            'taxes':         taxes,
            'net_profit':    net_profit,
            'net_margin':    round(net_profit / revenue * 100, 1) if revenue else 0,
        }

    return {
        'periods': periods_set,
        'groups': result_groups,
        'summary': summary,
    }

PLAN_STATUS_INCOME = 'ПЛАН ПОСТУПЛЕНИЙ'
PLAN_STATUS_EXPENSE = 'ПЛАН ОПЛАТ'
FACT_STATUS = 'ОПЛАЧЕНО'

@router.get("/plan-fact")
def get_plan_fact(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("planfact", "view"))
):
    import re

    query = db.query(
        Operation.period,
        Article.name.label("article"),
        Article.group.label("group"),
        Article.subgroup.label("subgroup"),
        Operation.status,
        Article.pl_line.label("pl_line"),
        func.sum(Operation.income).label("total_income"),
        func.sum(Operation.expense).label("total_expense"),
    ).outerjoin(Article, Operation.article_id == Article.id)\
     .group_by(Operation.period, Article.name, Article.group, Article.subgroup,
               Article.pl_line, Operation.status)

    rows = query.all()

    # Нормализуем периоды (кварталы → месяцы), как в /pl
    normalized = []
    for r in rows:
        p = r.period or ''
        # Раздел — из разметки статьи, как в /pl: иначе группы, которых нет в
        # PL_GROUPS_ORDER, снова тихо выпадут из отчёта.
        grp = _pl_group(r.pl_line, r.group)
        match = re.match(r'^(Q[1-4])\s+(\d{4})$', p)
        if match:
            q, year = match.group(1), match.group(2)
            months = QUARTER_MONTHS.get(q, [])
            for m in months:
                normalized.append({
                    'period': f'{year}-{m}',
                    'article': r.article or 'Без статьи', 'group': grp, 'subgroup': r.subgroup or '',
                    'status': r.status,
                    'income': (r.total_income or 0) / 3,
                    'expense': (r.total_expense or 0) / 3,
                })
        else:
            normalized.append({
                'period': p,
                'article': r.article or 'Без статьи', 'group': grp, 'subgroup': r.subgroup or '',
                'status': r.status,
                'income': r.total_income or 0,
                'expense': r.total_expense or 0,
            })

    # Фильтруем по диапазону дат ПОСЛЕ нормализации кварталов
    if date_from:
        normalized = [r for r in normalized if r['period'] >= date_from]
    if date_to:
        normalized = [r for r in normalized if r['period'] <= date_to]

    periods_set = sorted(set(r['period'] for r in normalized if r['period']))

    # Тренд по месяцам: доходная сторона = группа ВЫРУЧКА, расходная = все остальные группы
    trend_acc = {p: {'plan_income': 0, 'fact_income': 0, 'plan_expense': 0, 'fact_expense': 0} for p in periods_set}
    for r in normalized:
        p = r['period']
        if not p:
            continue
        if r['group'] == 'ВЫРУЧКА':
            if r['status'] == PLAN_STATUS_INCOME:
                trend_acc[p]['plan_income'] += r['income']
            elif r['status'] == FACT_STATUS:
                trend_acc[p]['fact_income'] += r['income']
        else:
            if r['status'] == PLAN_STATUS_EXPENSE:
                trend_acc[p]['plan_expense'] += r['expense']
            elif r['status'] == FACT_STATUS:
                trend_acc[p]['fact_expense'] += r['expense']

    trend = []
    for p in periods_set:
        t = trend_acc[p]
        trend.append({
            'period': p,
            'plan_income': t['plan_income'], 'fact_income': t['fact_income'],
            'pct_income': round(t['fact_income'] / t['plan_income'] * 100, 1) if t['plan_income'] else None,
            'plan_expense': t['plan_expense'], 'fact_expense': t['fact_expense'],
            'pct_expense': round(t['fact_expense'] / t['plan_expense'] * 100, 1) if t['plan_expense'] else None,
        })

    # Группа → подгруппа → статья, суммарно за весь выбранный диапазон
    data = {}
    for r in normalized:
        g, sg, a = r['group'], r.get('subgroup') or '', r['article']
        is_income_group = g == 'ВЫРУЧКА'
        value_field = 'income' if is_income_group else 'expense'
        plan_status = PLAN_STATUS_INCOME if is_income_group else PLAN_STATUS_EXPENSE

        if g not in data:
            data[g] = {}
        if sg not in data[g]:
            data[g][sg] = {}
        if a not in data[g][sg]:
            data[g][sg][a] = {'plan': 0, 'fact': 0}

        if r['status'] == plan_status:
            data[g][sg][a]['plan'] += r[value_field]
        elif r['status'] == FACT_STATUS:
            data[g][sg][a]['fact'] += r[value_field]

    def make_row(plan, fact):
        diff = fact - plan
        pct = round(fact / plan * 100, 1) if plan else None
        return {'plan': plan, 'fact': fact, 'diff': diff, 'pct': pct}

    result_groups = []
    for group in PL_GROUPS_ORDER:
        if group not in data or group == 'НЕ В P&L':
            continue
        is_income_group = group == 'ВЫРУЧКА'
        subgroups_list = []
        group_plan, group_fact = 0, 0

        for subgroup, articles_data in sorted(data[group].items()):
            articles_list = []
            sub_plan, sub_fact = 0, 0
            for article, vals in sorted(articles_data.items()):
                articles_list.append({'article': article, **make_row(vals['plan'], vals['fact'])})
                sub_plan += vals['plan']
                sub_fact += vals['fact']
            subgroups_list.append({
                'subgroup': subgroup,
                'articles': articles_list,
                'totals': make_row(sub_plan, sub_fact),
            })
            group_plan += sub_plan
            group_fact += sub_fact

        result_groups.append({
            'group': group,
            'is_income': is_income_group,
            'subgroups': subgroups_list,
            'totals': make_row(group_plan, group_fact),
        })

    # Сводка по компании
    revenue_totals = next((g['totals'] for g in result_groups if g['group'] == 'ВЫРУЧКА'), {'plan': 0, 'fact': 0, 'diff': 0, 'pct': None})
    expense_groups = [g['totals'] for g in result_groups if g['group'] != 'ВЫРУЧКА']
    plan_expense_total = sum(g['plan'] for g in expense_groups)
    fact_expense_total = sum(g['fact'] for g in expense_groups)

    summary = {
        'plan_income': revenue_totals['plan'], 'fact_income': revenue_totals['fact'],
        'diff_income': revenue_totals['diff'], 'pct_income': revenue_totals['pct'],
        'plan_expense': plan_expense_total, 'fact_expense': fact_expense_total,
        'diff_expense': fact_expense_total - plan_expense_total,
        'pct_expense': round(fact_expense_total / plan_expense_total * 100, 1) if plan_expense_total else None,
        'plan_net': revenue_totals['plan'] - plan_expense_total,
        'fact_net': revenue_totals['fact'] - fact_expense_total,
    }

    return {
        'periods': periods_set,
        'trend': trend,
        'groups': result_groups,
        'summary': summary,
    }

@router.get("/balance")
def get_balance(
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("balance", "view"))
):
    query = db.query(
        Operation.bank,
        func.sum(Operation.income).label("total_income"),
        func.sum(Operation.expense).label("total_expense"),
    ).filter(Operation.status == 'ОПЛАЧЕНО')\
     .group_by(Operation.bank)

    if date_to:
        query = query.filter(Operation.period <= date_to)

    results = query.all()
    turnover = {r.bank: {'income': r.total_income or 0, 'expense': r.total_expense or 0} for r in results}

    opening_rows = db.execute(text("SELECT bank, opening_balance FROM bank_balances")).fetchall()
    opening = {r.bank: r.opening_balance for r in opening_rows}

    banks = []
    total_balance = 0
    for bank in BANKS_ORDER:
        ob = opening.get(bank, 0)
        inc = turnover.get(bank, {}).get('income', 0)
        exp = turnover.get(bank, {}).get('expense', 0)
        balance = ob + inc - exp
        total_balance += balance
        banks.append({
            "bank": bank,
            "opening_balance": ob,
            "total_income": inc,
            "total_expense": exp,
            "balance": balance,
        })

    return {
        "banks": banks,
        "total_balance": total_balance,
    }


@router.get("/balance/full")
def get_balance_full(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("balance", "view"))
):
    # 1. Остатки по банкам (стартовые + обороты)
    turnover_rows = db.query(
        Operation.bank,
        func.sum(Operation.income).label("income"),
        func.sum(Operation.expense).label("expense"),
    ).filter(Operation.status == 'ОПЛАЧЕНО').group_by(Operation.bank).all()
    turnover = {r.bank: {'income': r.income or 0, 'expense': r.expense or 0} for r in turnover_rows}

    opening_rows = db.execute(text("SELECT bank, opening_balance FROM bank_balances")).fetchall()
    opening = {r.bank: r.opening_balance for r in opening_rows}

    banks = []
    total_cash = 0
    for bank in BANKS_ORDER:
        ob = opening.get(bank, 0)
        inc = turnover.get(bank, {}).get('income', 0)
        exp = turnover.get(bank, {}).get('expense', 0)
        balance = ob + inc - exp
        total_cash += balance
        banks.append({'bank': bank, 'opening_balance': ob, 'income': inc, 'expense': exp, 'balance': balance})

    # 2. Дебиторская задолженность — план поступлений (нам должны заплатить)
    from app.models import Counterparty

    def build_debt_rows(status, amount_field):
        ops = db.query(Operation).filter(Operation.status == status)\
            .filter(getattr(Operation, amount_field) > 0).all()

        grouped = {}
        for op in ops:
            key = (op.counterparty_id, op.article_id, op.period)
            grouped.setdefault(key, []).append(op)

        counterparty_cache = {c.id: c.name for c in db.query(Counterparty).all()}
        article_cache = {a.id: a.name for a in db.query(Article).all()}

        rows = []
        total = 0
        for (counterparty_id, article_id, period), group_ops in grouped.items():
            amount = sum(getattr(op, amount_field) or 0 for op in group_ops)
            total += amount
            rows.append({
                'counterparty': counterparty_cache.get(counterparty_id, '—'),
                'counterparty_id': counterparty_id,
                'article': article_cache.get(article_id, '—'),
                'article_id': article_id,
                'period': period,
                'amount': amount,
                'operations': [
                    {
                        'id': op.id,
                        'amount': getattr(op, amount_field) or 0,
                        'ds_num': op.ds_num,
                        'invoice': op.invoice,
                        'invoice_date': op.invoice_date.isoformat() if op.invoice_date else None,
                    }
                    for op in sorted(group_ops, key=lambda o: o.date or o.id)
                ],
            })
        return rows, total

    receivables, total_receivables = build_debt_rows('ПЛАН ПОСТУПЛЕНИЙ', 'income')

    # 3. Кредиторская задолженность — план оплат (мы должны заплатить)
    payables, total_payables = build_debt_rows('ПЛАН ОПЛАТ', 'expense')

    total_assets = total_cash + total_receivables
    net_assets = total_assets - total_payables

    return {
        'banks': banks,
        'total_cash': total_cash,
        'receivables': sorted(receivables, key=lambda x: x['period'] or ''),
        'total_receivables': total_receivables,
        'payables': sorted(payables, key=lambda x: x['period'] or ''),
        'total_payables': total_payables,
        'total_assets': total_assets,
        'net_assets': net_assets,
    }

def _period_bounds(period):
    """Возвращает (start_date, end_date) периода ('YYYY-MM' или 'Qn YYYY'), либо (None, None)."""
    import re, calendar
    from datetime import date as date_cls

    if not period:
        return None, None
    p = period.strip()

    m = re.match(r'^(\d{4})-(\d{2})$', p)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        last_day = calendar.monthrange(year, month)[1]
        return date_cls(year, month, 1), date_cls(year, month, last_day)

    m = re.match(r'^Q([1-4])\s+(\d{4})$', p)
    if m:
        q, year = int(m.group(1)), int(m.group(2))
        start_month = (q - 1) * 3 + 1
        end_month = start_month + 2
        last_day = calendar.monthrange(year, end_month)[1]
        return date_cls(year, start_month, 1), date_cls(year, end_month, last_day)

    return None, None


GRACE_DAYS = 30          # буфер после срока оплаты, в течение которого долг считается "текущим", а не просроченным
DEFAULT_TERM_DAYS = 60   # стандартный срок отсрочки для контрагентов без явно заданного term_days
# Раньше отсрочка для двух контрагентов была захардкожена здесь по ИНН (90/120 дн.) — теперь это
# редактируемое поле Counterparty.term_days в реестре контрагентов (/settings → Контрагенты).
# Значения 90/120 были перенесены в БД миграцией migrate_add_term_days.sql.


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


def _compute_debt_grouped(db: Session, status: str, amount_field: str, group_by: str):
    """Общая логика дебиторки/кредиторки: операции со статусом `status` (где `amount_field` > 0),
    сгруппированные либо по контрагенту (group_by='counterparty'), либо по статье (group_by='article'),
    с разбивкой по статусу долга (просрочено/текущая задолженность/план) относительно срока оплаты =
    период + отсрочка контрагента + буфер GRACE_DAYS. Срок отсрочки всегда берётся по контрагенту
    операции независимо от того, по какому полю идёт группировка."""
    from app.models import Counterparty
    from datetime import date as date_cls

    today = date_cls.today()

    ops = db.query(Operation).filter(Operation.status == status)\
        .filter(getattr(Operation, amount_field) > 0).all()

    counterparty_cache = {c.id: c for c in db.query(Counterparty).all()}
    article_cache = {a.id: a.name for a in db.query(Article).all()}

    by_group = {}
    aging_summary = {
        'overdue': {'amount': 0, 'count': 0},
        'current': {'amount': 0, 'count': 0},
        'future':  {'amount': 0, 'count': 0},
        'unknown': {'amount': 0, 'count': 0},
    }

    for op in ops:
        cp = counterparty_cache.get(op.counterparty_id)
        term_days = _term_days_for_counterparty(cp)
        due_date = _due_date(op.period, term_days)
        bucket = _aging_bucket(due_date, today)
        amount = getattr(op, amount_field) or 0

        aging_summary[bucket]['amount'] += amount
        aging_summary[bucket]['count'] += 1

        key = op.counterparty_id if group_by == 'counterparty' else op.article_id
        if key not in by_group:
            if group_by == 'counterparty':
                by_group[key] = {
                    'counterparty_id': key,
                    'counterparty': cp.name if cp else '—',
                    'inn': cp.inn if cp else None,
                    'contract_number': cp.contract_number if cp else None,
                    'contract_date': cp.contract_date if cp else None,
                    'note': cp.note if cp else None,
                    'term_days': term_days,
                    'amount': 0,
                    'op_count': 0,
                    'aging': {'overdue': 0, 'current': 0, 'future': 0, 'unknown': 0},
                    'operations': [],
                }
            else:
                by_group[key] = {
                    'article_id': key,
                    'article': article_cache.get(key, '—'),
                    'amount': 0,
                    'op_count': 0,
                    'aging': {'overdue': 0, 'current': 0, 'future': 0, 'unknown': 0},
                    'operations': [],
                }

        row = by_group[key]
        row['amount'] += amount
        row['op_count'] += 1
        row['aging'][bucket] += amount
        op_detail = {
            'id': op.id,
            'date': op.date,
            'period': op.period,
            'amount': amount,
            'ds_num': op.ds_num,
            'invoice': op.invoice,
            'invoice_date': op.invoice_date,
            'due_date': due_date,
            'aging_bucket': bucket,
        }
        if group_by == 'counterparty':
            op_detail['article'] = article_cache.get(op.article_id, '—')
            op_detail['article_id'] = op.article_id
        else:
            op_detail['counterparty'] = cp.name if cp else '—'
            op_detail['counterparty_id'] = op.counterparty_id
        row['operations'].append(op_detail)

    rows = list(by_group.values())
    for r in rows:
        r['operations'].sort(key=lambda o: (o['date'] or date_cls.min, o['id']))
    rows.sort(key=lambda r: r['amount'], reverse=True)

    total_amount = sum(r['amount'] for r in rows)

    return {
        'as_of': today,
        'summary': {
            'total_amount': total_amount,
            'group_count': len(rows),
            'operation_count': len(ops),
        },
        'aging_summary': aging_summary,
        'rows': rows,
    }


def _compute_receivables(db: Session):
    """Дебиторская задолженность = 'ПЛАН ПОСТУПЛЕНИЙ' (income > 0), сгруппированная по контрагенту."""
    data = _compute_debt_grouped(db, 'ПЛАН ПОСТУПЛЕНИЙ', 'income', 'counterparty')
    data['summary']['counterparty_count'] = data['summary'].pop('group_count')
    return data


def _compute_payables(db: Session):
    """Кредиторская задолженность = 'ПЛАН ОПЛАТ' (expense > 0), сгруппированная по статье."""
    data = _compute_debt_grouped(db, 'ПЛАН ОПЛАТ', 'expense', 'article')
    data['summary']['article_count'] = data['summary'].pop('group_count')
    return data


@router.get("/receivables")
def get_receivables(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("receivables", "view"))
):
    return _compute_receivables(db)


@router.get("/balance/receivables")
def get_balance_receivables(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("balance", "view"))
):
    return _compute_receivables(db)


@router.get("/balance/payables")
def get_balance_payables(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("balance", "view"))
):
    return _compute_payables(db)


class CounterpartyNoteUpdate(BaseModel):
    note: Optional[str] = None


@router.patch("/receivables/{counterparty_id}/note")
def update_counterparty_note(
    counterparty_id: int,
    data: CounterpartyNoteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("receivables", "edit"))
):
    from app.models import Counterparty
    counterparty = db.query(Counterparty).filter(Counterparty.id == counterparty_id).first()
    if not counterparty:
        raise HTTPException(status_code=404, detail="Контрагент не найден")
    counterparty.note = (data.note or "").strip() or None
    db.commit()
    log_action(db, current_user, "update_counterparty_note", entity_type="counterparty", entity_id=counterparty_id,
               details=f"note={counterparty.note or '—'}")
    return {"message": "Примечание сохранено"}


@router.get("/receivables/export")
def export_receivables(
    counterparty: List[str] = Query(default=[]),
    article: List[str] = Query(default=[]),
    period: List[str] = Query(default=[]),
    overdue_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("receivables", "view"))
):
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from fastapi.responses import StreamingResponse

    AGING_LABELS = {'overdue': 'Просрочено', 'current': 'Текущая задолженность', 'future': 'План', 'unknown': 'Без периода'}

    data = _compute_receivables(db)

    # Применяем те же фильтры, что и в клиентском UI
    rows = data['rows']
    if counterparty:
        rows = [r for r in rows if r['counterparty'] in counterparty]

    filtered_rows = []
    for r in rows:
        ops = list(r['operations'])
        if overdue_only:
            ops = [o for o in ops if o['aging_bucket'] in ('overdue', 'current')]
        if article:
            ops = [o for o in ops if o['article'] in article]
        if period:
            ops = [o for o in ops if o['period'] in period]
        if ops:
            filtered_rows.append({**r, 'operations': ops})

    total_amount = sum(o['amount'] for r in filtered_rows for o in r['operations'])

    wb = Workbook()
    ws = wb.active
    ws.title = "Дебиторка"

    columns = [
        ('Контрагент', 30), ('ИНН', 14), ('№ договора', 16), ('Дата договора', 14), ('Отсрочка, дн.', 12),
        ('Статья', 24), ('Период', 12), ('Срок оплаты', 14), ('Возраст', 18), ('Дата операции', 14),
        ('Сумма', 14), ('№ ДС', 14), ('Счёт', 14), ('Счёт от дата', 14),
    ]
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='2563EB', end_color='2563EB', fill_type='solid')
    for col_idx, (title, width) in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=col_idx, value=title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = width
    ws.freeze_panes = "A2"

    date_cols = (4, 8, 10, 14)
    row_idx = 2
    for r in filtered_rows:
        for op in r['operations']:
            values = [
                r['counterparty'], r['inn'], r['contract_number'], r['contract_date'], r['term_days'],
                op['article'], op['period'], op['due_date'], AGING_LABELS.get(op['aging_bucket'], op['aging_bucket']),
                op['date'], op['amount'], op['ds_num'], op['invoice'], op['invoice_date'],
            ]
            for col_idx, value in enumerate(values, start=1):
                ws.cell(row=row_idx, column=col_idx, value=value)
            for dc in date_cols:
                ws.cell(row=row_idx, column=dc).number_format = 'DD.MM.YYYY'
            row_idx += 1

    if row_idx > 2:
        total_row = row_idx
        ws.cell(row=total_row, column=10, value='Итого:').font = Font(bold=True)
        sum_cell = ws.cell(row=total_row, column=11, value=total_amount)
        sum_cell.font = Font(bold=True)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"debitorka_{timez.msk_now().strftime('%Y%m%d_%H%M')}.xlsx"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)


@router.get("/periods")
def get_periods(
    db: Session = Depends(get_db),
    # Фронт этот эндпоинт не зовёт ни с одного экрана (проверено 2026-08-23):
    # /finance/operations берёт периоды из /operations/periods. Оставлен на случай
    # внешних потребителей, но закрыт правами отчётов, а не фактом входа.
    current_user: User = Depends(require_any_permission(
        ("dashboard", "pl", "planfact", "balance", "finreport"), "view"))
):
    results = db.query(Operation.period)\
        .filter(Operation.period.isnot(None))\
        .distinct()\
        .order_by(Operation.period)\
        .all()
    return [r.period for r in results]
