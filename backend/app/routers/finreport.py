"""Финансовый отчёт — P&L по начислению и по оплате.

Отдельный эндпоинт рядом с /reports/pl. Старый отчёт не трогаем: он остаётся как есть,
пока пользователи не перейдут на новый и не сверят цифры.

Чем отличается от /reports/pl (см. docs/АУДИТ_PL_2026-08-14.md и
docs/ПЛАН_PL_и_БДР_с_выгрузкой.md):

1. Две базы признания. `basis=accrual` — по месяцу оказания услуги (`Operation.period`,
   все операции); `basis=cash` — по месяцу платежа (`Operation.date`, только оплаченные).
   Старый отчёт брал время от начисления, а полноту от оплаты — гибрид, из-за которого
   закрытый месяц продолжал меняться задним числом.
2. НДС. Суммы в базе брутто, поэтому в режиме `vat=net` из каждой строки вычитается
   `vat_fact`, а статьи самого НДС из отчёта исключаются: НДС транзитный, он не доход и
   не расход. Старый отчёт брал брутто и вычитал уплаченный НДС ещё раз.
3. Обе стороны каждой группы. Строка считается как нетто (расход − доход), поэтому
   возвраты и рибейты больше не теряются.
4. Тело займа — не расход. Погашение и получение займа уходят в «вне P&L», в отчёте
   остаются только проценты, отдельной строкой финансовых расходов.
5. Ничего не пропадает молча: всё, что не удалось разметить, видно строкой «требует
   разметки», а не исчезает из расчёта.
"""

import re
from datetime import datetime
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Article, Operation, User
from app.permissions import require_permission
from app.routers.reports import QUARTER_MONTHS

router = APIRouter()

PAID = 'ОПЛАЧЕНО'

# ---------------------------------------------------------------------------
# Строки отчёта
# ---------------------------------------------------------------------------
# key → (заголовок, знак). Знак +1 — строка увеличивает прибыль (выручка),
# −1 — уменьшает. Внутри строки всегда считаем нетто по её собственному знаку,
# поэтому возврат клиенту уменьшает выручку, а рибейт поставщика — себестоимость.
REVENUE = 'revenue'
COGS = 'cogs'
OPEX = 'opex'
MARKETING = 'marketing'
FINANCE = 'finance'
OTHER = 'other'
PROFIT_TAX = 'profit_tax'
VAT_PAID = 'vat_paid'
UNCLASSIFIED = 'unclassified'
EXCLUDED = 'excluded'

LINES = [
    (REVENUE,      'Выручка',                    +1),
    (COGS,         'Себестоимость',              -1),
    (OPEX,         'Операционные расходы',       -1),
    (MARKETING,    'Маркетинг',                  -1),
    (FINANCE,      'Финансовые расходы',         -1),
    (OTHER,        'Прочие расходы',             -1),
    # Строка живёт только в режиме «с НДС»: раз выручка показана брутто, уплаченный
    # налог обязан остаться расходом, иначе прибыль надувается на всю разницу.
    # В режиме «без НДС» НДС исключён с обеих сторон и этой строки нет.
    (VAT_PAID,     'НДС уплаченный',             -1),
    # Раздел налогов: внутри две подстроки — «Налог на прибыль» и «Прочие налоги».
    # Вычитаются после EBITDA, поэтому строка одна, а не две соседние.
    (PROFIT_TAX,   'Налоги',                     -1),
    (UNCLASSIFIED, 'Требует разметки',           -1),
]
LINE_LABEL = {k: label for k, label, _ in LINES}
LINE_SIGN = {k: sign for k, _, sign in LINES}

# Причины исключения из P&L — показываем их в блоке контроля, чтобы деньги
# не «исчезали»: пользователь должен видеть, что именно вынесено и почему.
EX_VAT = 'НДС (транзитный налог)'
EX_LOAN = 'Тело займа (движение по балансу)'
EX_GROUP = 'Статьи вне P&L (транзит, дивиденды, прочее)'

_RE_INTEREST = re.compile(r'процент|%')
_RE_LOAN_BODY = re.compile(r'погашен|возврат|получен|выдач|вкл\b|тело')
_RE_VAT = re.compile(r'ндс')
_RE_PROFIT = re.compile(r'прибыл')
_RE_NDFL = re.compile(r'ндфл')
_RE_INSURANCE = re.compile(r'взнос|страхов')
_RE_PAYROLL = re.compile(r'фот|зарплат|оплата труда')

PAYROLL_SUBGROUP = 'Сотрудники'
TAX_PROFIT_SUBGROUP = 'Налог на прибыль'
TAX_OTHER_SUBGROUP = 'Прочие налоги'

# Значение Article.pl_line → строка отчёта. Заполняется в справочнике Статей,
# заведено миграцией 2026-08-18_article_pl_line.sql. Раньше это отнесение было
# рассыпано по регуляркам ниже и по списку PL_GROUPS_ORDER в reports.py, из-за чего
# отчёт не видел групп, которых не было в коде («Сотрудники», «Офис» — 100,6 млн).
PL_LINE_MAP = {
    'revenue': REVENUE,
    'cogs': COGS,
    'opex': OPEX,
    'marketing': MARKETING,
    'finance': FINANCE,
    'other': OTHER,
    'profit_tax': PROFIT_TAX,
    'tax_other': PROFIT_TAX,   # тот же раздел «Налоги», отдельной подстрокой
    'excluded': EXCLUDED,
}

# Статьи, где назначение платежа определяется только его описанием. Разметить их
# полем нельзя в принципе: в «НАЛОГИ» приходит единый налоговый платёж (внутри сразу
# НДС, прибыль, НДФЛ и взносы), а в «КРЕДИТЫ» — и тело займа, и проценты по нему.
# Помечены в справочнике значением pl_line='by_description'.
BY_DESCRIPTION = 'by_description'


def classify(pl_line: Optional[str], article: Optional[str], subgroup: Optional[str],
             description: Optional[str]):
    """Куда отнести операцию. Возвращает (строка_отчёта, подгруппа, метка_строки).

    Отнесение берётся из справочника (Article.pl_line). Единственное исключение —
    статьи `by_description`, где один платёж содержит несколько назначений сразу.

    Метка — то, что увидит пользователь в разворачивании строки. Для единого
    налогового платежа это не название статьи (она у всех одна — «НАЛОГИ»), а
    распознанное назначение: иначе 8.4 млн выглядят одной безымянной суммой.
    """
    a = (article or '').strip()
    sg = (subgroup or '').strip()
    d = (description or '').lower()
    a_low = a.lower()

    if pl_line == BY_DESCRIPTION:
        # Займы и кредиты: проценты — расход, тело — движение по балансу.
        if 'кредит' in a_low or 'займ' in a_low:
            if _RE_INTEREST.search(d):
                return FINANCE, '', 'Проценты по займам и кредитам'
            if _RE_LOAN_BODY.search(d):
                return EXCLUDED, EX_LOAN, 'Получение и погашение займов'
            return UNCLASSIFIED, '', f'{a} — назначение не распознано'
        # Единый налоговый платёж: статья одна, внутри всё сразу.
        if _RE_VAT.search(d):
            return EXCLUDED, EX_VAT, 'НДС в составе ЕНП'
        if _RE_PROFIT.search(d):
            return PROFIT_TAX, TAX_PROFIT_SUBGROUP, 'Налог на прибыль в составе ЕНП'
        if _RE_NDFL.search(d):
            return OPEX, PAYROLL_SUBGROUP, 'НДФЛ в составе ЕНП'
        if _RE_INSURANCE.search(d):
            return OPEX, PAYROLL_SUBGROUP, 'Страховые взносы в составе ЕНП'
        if _RE_PAYROLL.search(d):
            return OPEX, PAYROLL_SUBGROUP, 'ФОТ в составе ЕНП'
        return UNCLASSIFIED, '', 'ЕНП — назначение не указано'

    line = PL_LINE_MAP.get(pl_line or '')
    if line is None:
        # Статья без разметки (в том числе операция вообще без статьи). Деньги не
        # теряются — они видны отдельной строкой, пока разметку не проставят.
        return UNCLASSIFIED, '', a or 'Без статьи'

    if line == EXCLUDED:
        return EXCLUDED, (EX_VAT if 'ндс' in a_low else EX_GROUP), a or '—'

    if pl_line == 'profit_tax':
        return PROFIT_TAX, TAX_PROFIT_SUBGROUP, a
    if pl_line == 'tax_other':
        return PROFIT_TAX, TAX_OTHER_SUBGROUP, a

    # Транзит — деньги, проходящие через компанию насквозь. Сам оборот в P&L не место,
    # но списание стабильно больше поступления, и эта разница — реальный расход
    # (наценка/комиссия на проходящих деньгах). Считаем именно её: строка нетто по
    # своему знаку даёт ровно «списано − поступило».
    if 'транзит' in a_low:
        return OTHER, '', 'Транзит (разница между списанием и поступлением)'

    return line, sg, a


# ---------------------------------------------------------------------------
# Сбор данных
# ---------------------------------------------------------------------------

def _month_of(value) -> str:
    return value.strftime('%Y-%m') if value else ''


def _collect(db: Session, basis: str, vat: str, date_from: Optional[str], date_to: Optional[str]):
    """Плоский список строк: (период, строка отчёта, подгруппа, метка, нетто-сумма).

    Нетто считается сразу по знаку строки: для выручки доход − расход, для
    расходных строк расход − доход. Возвраты и рибейты за счёт этого не теряются.
    """
    q = db.query(
        Operation.period,
        Operation.date,
        Operation.income,
        Operation.expense,
        Operation.vat_fact,
        Operation.vat_rate,
        Operation.bank,
        Operation.description,
        Article.name.label('article'),
        Article.subgroup.label('subgroup'),
        Article.pl_line.label('pl_line'),
    ).outerjoin(Article, Operation.article_id == Article.id)

    if basis == 'cash':
        q = q.filter(Operation.status == PAID)

    rows = []
    control = {
        'zero_vat_amount': 0.0,
        'zero_vat_rows': 0,
        'no_period_rows': 0,
        'basis': basis,
        'excluded': {},
    }
    net_mode = (vat == 'net')

    for r in q.all():
        income = float(r.income or 0)
        expense = float(r.expense or 0)
        if not income and not expense:
            continue

        # Сначала раскладываем по месяцам и режем по диапазону — и только потом
        # считаем контрольные суммы. Иначе блок контроля показывает всю базу
        # независимо от выбранного периода и выглядит катастрофой на ровном месте.
        if basis == 'cash':
            months = [_month_of(r.date)]
        else:
            p = (r.period or '').strip()
            m = re.match(r'^(Q[1-4])\s+(\d{4})$', p)
            if m:
                # Квартал раскладываем на три месяца равными долями — как в /reports.
                months = [f'{m.group(2)}-{mm}' for mm in QUARTER_MONTHS.get(m.group(1), [])]
            else:
                months = [p]

        empty = [x for x in months if not x]
        months = [x for x in months if x]
        if empty:
            # В режиме «по оплате» это операции без даты платежа (таких заметно
            # больше среди квартальных), в режиме «по начислению» — без периода.
            control['no_period_rows'] += len(empty)
        if not months:
            continue

        kept = [x for x in months
                if not (date_from and x < date_from) and not (date_to and x > date_to)]
        if not kept:
            continue
        # Доля операции, попавшая в выбранный диапазон: у квартала, разрезанного
        # границей периода, в отчёт входит одна или две трети.
        share = len(kept) / len(months)

        line, subgroup, label = classify(r.pl_line, r.article, r.subgroup, r.description)

        # Транзит очищается от НДС так же, как всё остальное, — несимметрично, и это
        # правильно. Механика операции: с расчётного счёта уходит сумма с НДС, а в
        # кассу приходят уже очищенные деньги (банк «Наличные» — только приход, ставка
        # нулевая у всех строк). Поэтому вычитание НДС только со стороны списания —
        # не перекос данных, а отражение сути: разница считается между очищенным
        # списанием и очищенным поступлением.
        if net_mode:
            vat_fact = float(r.vat_fact or 0)
            has_rate = r.vat_rate is not None and float(r.vat_rate) != 0
            if has_rate:
                if income:
                    income -= vat_fact
                if expense:
                    expense -= vat_fact
            else:
                # Ставка 0 — это заполненное значение «не облагается», а не пробел:
                # NULL в vat_rate не встречается ни в одной операции. Поэтому здесь
                # не предупреждение, а справка — сколько прошло необлагаемых сумм.
                control['zero_vat_amount'] += (income + expense) * share
                control['zero_vat_rows'] += 1
        if line == EXCLUDED and subgroup == EX_VAT and not net_mode:
            line, subgroup = VAT_PAID, ''
        amount = (income - expense) if LINE_SIGN.get(line, -1) > 0 else (expense - income)

        if line == EXCLUDED:
            control['excluded'][subgroup] = (control['excluded'].get(subgroup, 0.0)
                                             + abs(income - expense) * share)
            continue

        value = amount / len(months)
        for period in kept:
            rows.append((period, line, subgroup, label, value))

    return rows, control


def build_report(db: Session, basis: str, vat: str, date_from: Optional[str], date_to: Optional[str]):
    rows, control = _collect(db, basis, vat, date_from, date_to)

    periods = sorted({r[0] for r in rows})
    # {line: {subgroup: {label: {period: amount}}}}
    tree: dict = {}
    for period, line, subgroup, label, value in rows:
        tree.setdefault(line, {}).setdefault(subgroup, {}).setdefault(label, {})
        tree[line][subgroup][label][period] = tree[line][subgroup][label].get(period, 0.0) + value

    groups = []
    for key, label, _sign in LINES:
        data = tree.get(key)
        if not data and key in (UNCLASSIFIED, FINANCE, OTHER, VAT_PAID):
            continue  # пустые вспомогательные строки не показываем
        subgroups = []
        totals = {p: 0.0 for p in periods}
        for sg_name in sorted(data or {}):
            articles = []
            sg_totals = {p: 0.0 for p in periods}
            for art_name in sorted(data[sg_name]):
                by_period = {p: data[sg_name][art_name].get(p, 0.0) for p in periods}
                articles.append({'article': art_name, 'periods': by_period})
                for p in periods:
                    sg_totals[p] += by_period[p]
                    totals[p] += by_period[p]
            subgroups.append({'subgroup': sg_name, 'articles': articles, 'totals': sg_totals})
        groups.append({'key': key, 'label': label, 'subgroups': subgroups, 'totals': totals})

    def line_total(key, period):
        return tree_totals.get(key, {}).get(period, 0.0)

    tree_totals = {g['key']: g['totals'] for g in groups}

    summary = {}
    for p in periods:
        revenue = line_total(REVENUE, p)
        cogs = line_total(COGS, p)
        opex = line_total(OPEX, p)
        marketing = line_total(MARKETING, p)
        finance = line_total(FINANCE, p)
        other = line_total(OTHER, p)
        tax = line_total(PROFIT_TAX, p)
        vat_paid = line_total(VAT_PAID, p)
        unclassified = line_total(UNCLASSIFIED, p)
        gross = revenue - cogs
        operating = gross - opex - marketing
        ebt = operating - finance - other - vat_paid - unclassified
        net = ebt - tax
        pct = lambda v: round(v / revenue * 100, 1) if revenue else 0
        summary[p] = {
            'revenue': revenue, 'cogs': cogs, 'gross_profit': gross, 'gross_margin': pct(gross),
            'opex': opex, 'marketing': marketing,
            'operating_profit': operating, 'operating_margin': pct(operating),
            'finance': finance, 'other': other, 'vat_paid': vat_paid,
            'unclassified': unclassified,
            'profit_before_tax': ebt, 'profit_tax': tax,
            'net_profit': net, 'net_margin': pct(net),
        }

    control['excluded'] = [{'reason': k, 'amount': v} for k, v in sorted(control['excluded'].items())]
    control['unclassified_total'] = sum(line_total(UNCLASSIFIED, p) for p in periods)

    return {
        'basis': basis,
        'vat': vat,
        'periods': periods,
        'groups': groups,
        'summary': summary,
        'control': control,
    }


BASIS_LABEL = {'accrual': 'по начислению', 'cash': 'по оплате'}
VAT_LABEL = {'net': 'без НДС', 'gross': 'с НДС'}


@router.get("")
def get_finreport(
    basis: str = Query('accrual', pattern='^(accrual|cash)$'),
    vat: str = Query('net', pattern='^(net|gross)$'),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("finreport", "view")),
):
    return build_report(db, basis, vat, date_from, date_to)


# ---------------------------------------------------------------------------
# Выгрузка в Excel
# ---------------------------------------------------------------------------
# Строим кодом, а не по шаблону-токенизатору как медиаплан: число колонок здесь
# заранее неизвестно, оно зависит от выбранного периода. Итоги пишем настоящими
# формулами Excel — финансист первым делом проверит сходимость.

MONTH_RU = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']


def _period_title(p: str) -> str:
    try:
        y, m = p.split('-')
        return f'{MONTH_RU[int(m) - 1]} {y}'
    except Exception:
        return p


@router.get("/export")
def export_finreport(
    basis: str = Query('accrual', pattern='^(accrual|cash)$'),
    vat: str = Query('net', pattern='^(net|gross)$'),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("finreport", "view")),
):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    rep = build_report(db, basis, vat, date_from, date_to)
    periods = rep['periods']
    summary = rep['summary']

    NUM = '# ##0;[Red](# ##0);—'
    PCT = '0.0"%"'
    thin = Side(style='thin', color='D9D9D9')
    border = Border(bottom=thin)
    head_fill = PatternFill('solid', fgColor='1F3864')
    total_fill = PatternFill('solid', fgColor='DDEBF7')
    sub_fill = PatternFill('solid', fgColor='F2F2F2')

    wb = Workbook()
    ws = wb.active
    ws.title = 'Отчёт'

    ws['A1'] = f"Финансовый отчёт — {BASIS_LABEL[basis]}, {VAT_LABEL[vat]}"
    ws['A1'].font = Font(bold=True, size=14)
    ws['A2'] = f"Период: {date_from or 'с начала'} — {date_to or 'по настоящее время'}"
    ws['A2'].font = Font(size=10, color='808080')

    header_row = 4
    ws.cell(header_row, 1, 'Статья').font = Font(bold=True, color='FFFFFF')
    ws.cell(header_row, 1).fill = head_fill
    for i, p in enumerate(periods):
        c = ws.cell(header_row, 2 + i, _period_title(p))
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = head_fill
        c.alignment = Alignment(horizontal='right')
    total_col = 2 + len(periods)
    c = ws.cell(header_row, total_col, 'ИТОГО')
    c.font = Font(bold=True, color='FFFFFF')
    c.fill = head_fill
    c.alignment = Alignment(horizontal='right')

    row = header_row + 1
    first_col, last_col = get_column_letter(2), get_column_letter(1 + len(periods))

    def write_total_row(label, field, margin_field=None):
        nonlocal row
        ws.cell(row, 1, label).font = Font(bold=True)
        ws.cell(row, 1).fill = total_fill
        for i, p in enumerate(periods):
            cell = ws.cell(row, 2 + i, summary[p][field])
            cell.number_format = NUM
            cell.font = Font(bold=True)
            cell.fill = total_fill
        cell = ws.cell(row, total_col, f'=SUM({first_col}{row}:{last_col}{row})')
        cell.number_format = NUM
        cell.font = Font(bold=True)
        cell.fill = total_fill
        row += 1
        if margin_field:
            ws.cell(row, 1, '   маржа').font = Font(italic=True, color='808080')
            for i, p in enumerate(periods):
                cell = ws.cell(row, 2 + i, summary[p][margin_field])
                cell.number_format = PCT
                cell.font = Font(italic=True, color='808080')
            row += 1

    for g in rep['groups']:
        group_row = row
        ws.cell(row, 1, g['label']).font = Font(bold=True)
        for i, p in enumerate(periods):
            ws.cell(row, 2 + i, g['totals'].get(p, 0)).number_format = NUM
            ws.cell(row, 2 + i).font = Font(bold=True)
        cell = ws.cell(row, total_col, f'=SUM({first_col}{row}:{last_col}{row})')
        cell.number_format = NUM
        cell.font = Font(bold=True)
        row += 1

        detail_start = row
        for sg in g['subgroups']:
            if sg['subgroup']:
                ws.cell(row, 1, '  ' + sg['subgroup']).font = Font(bold=True, size=10)
                ws.cell(row, 1).fill = sub_fill
                for i, p in enumerate(periods):
                    ws.cell(row, 2 + i, sg['totals'].get(p, 0)).number_format = NUM
                    ws.cell(row, 2 + i).fill = sub_fill
                ws.cell(row, total_col, f'=SUM({first_col}{row}:{last_col}{row})').number_format = NUM
                row += 1
            for a in sg['articles']:
                ws.cell(row, 1, '    ' + a['article']).font = Font(size=10)
                ws.cell(row, 1).border = border
                for i, p in enumerate(periods):
                    cell = ws.cell(row, 2 + i, a['periods'].get(p, 0))
                    cell.number_format = NUM
                    cell.border = border
                cell = ws.cell(row, total_col, f'=SUM({first_col}{row}:{last_col}{row})')
                cell.number_format = NUM
                cell.border = border
                row += 1
        # Сворачиваемая детализация: плюсики слева, по умолчанию свёрнуто у крупных групп.
        if row > detail_start:
            for r in range(detail_start, row):
                ws.row_dimensions[r].outlineLevel = 1
                ws.row_dimensions[r].hidden = False

        if g['key'] == COGS:
            write_total_row('ВАЛОВАЯ ПРИБЫЛЬ', 'gross_profit', 'gross_margin')
        elif g['key'] == MARKETING:
            write_total_row('ОПЕРАЦИОННАЯ ПРИБЫЛЬ', 'operating_profit', 'operating_margin')
        elif g['key'] == PROFIT_TAX:
            pass
        _ = group_row

    write_total_row('ПРИБЫЛЬ ДО НАЛОГА', 'profit_before_tax')
    write_total_row('ЧИСТАЯ ПРИБЫЛЬ', 'net_profit', 'net_margin')

    ws.sheet_properties.outlinePr.summaryBelow = False
    ws.column_dimensions['A'].width = 46
    for i in range(len(periods) + 1):
        ws.column_dimensions[get_column_letter(2 + i)].width = 15
    ws.freeze_panes = ws.cell(header_row + 1, 2)

    # --- Свод ---
    ws2 = wb.create_sheet('Свод')
    ws2.cell(1, 1, 'Показатель').font = Font(bold=True)
    for i, p in enumerate(periods):
        ws2.cell(1, 2 + i, _period_title(p)).font = Font(bold=True)
    ws2.cell(1, total_col, 'ИТОГО').font = Font(bold=True)
    svod = [
        ('Выручка', 'revenue'), ('Себестоимость', 'cogs'), ('Валовая прибыль', 'gross_profit'),
        ('Валовая маржа, %', 'gross_margin'), ('Операционные расходы', 'opex'),
        ('Маркетинг', 'marketing'), ('Операционная прибыль', 'operating_profit'),
        ('Операционная маржа, %', 'operating_margin'), ('Финансовые расходы', 'finance'),
        ('Прочие расходы', 'other'), ('Прибыль до налога', 'profit_before_tax'),
        ('Налог на прибыль', 'profit_tax'), ('Чистая прибыль', 'net_profit'),
        ('Чистая маржа, %', 'net_margin'),
    ]
    r2 = 2
    for label, field in svod:
        ws2.cell(r2, 1, label)
        is_pct = field.endswith('margin')
        for i, p in enumerate(periods):
            cell = ws2.cell(r2, 2 + i, summary[p][field])
            cell.number_format = PCT if is_pct else NUM
        if not is_pct:
            ws2.cell(r2, total_col, f'=SUM({first_col}{r2}:{last_col}{r2})').number_format = NUM
        r2 += 1
    ws2.column_dimensions['A'].width = 30
    for i in range(len(periods) + 1):
        ws2.column_dimensions[get_column_letter(2 + i)].width = 15

    # --- Параметры: без этого листа две выгрузки с разными настройками неразличимы ---
    ws3 = wb.create_sheet('Параметры')
    params = [
        ('Отчёт', 'Финансовый отчёт (P&L)'),
        ('База признания', BASIS_LABEL[basis] + (
            ' — по месяцу оказания услуги, все операции' if basis == 'accrual'
            else ' — по месяцу платежа, только оплаченные')),
        ('НДС', VAT_LABEL[vat]),
        ('Период с', date_from or '—'),
        ('Период по', date_to or '—'),
        ('Выгружено', datetime.now().strftime('%d.%m.%Y %H:%M')),
        ('Пользователь', getattr(current_user, 'name', None) or getattr(current_user, 'email', '—')),
    ]
    for i, (k, v) in enumerate(params, start=1):
        ws3.cell(i, 1, k).font = Font(bold=True)
        ws3.cell(i, 2, v)
    ws3.column_dimensions['A'].width = 20
    ws3.column_dimensions['B'].width = 70

    # --- Контроль: лист есть только если есть что показать ---
    ctrl = rep['control']
    ctrl_rows = []
    for ex in ctrl['excluded']:
        ctrl_rows.append(('Вне P&L: ' + ex['reason'], ex['amount']))
    if ctrl.get('unclassified_total'):
        ctrl_rows.append(('Требует разметки', ctrl['unclassified_total']))
    if vat == 'net' and ctrl.get('zero_vat_rows'):
        ctrl_rows.append((f"Необлагаемые суммы, ставка 0 ({ctrl['zero_vat_rows']} операций) — "
                          f"очищать нечего", ctrl['zero_vat_amount']))
    if ctrl.get('no_period_rows'):
        ctrl_rows.append((f"Операций без периода — не попали в отчёт", ctrl['no_period_rows']))
    if ctrl_rows:
        ws4 = wb.create_sheet('Контроль')
        ws4.cell(1, 1, 'Что').font = Font(bold=True)
        ws4.cell(1, 2, 'Сумма').font = Font(bold=True)
        for i, (k, v) in enumerate(ctrl_rows, start=2):
            ws4.cell(i, 1, k)
            ws4.cell(i, 2, v).number_format = NUM
        ws4.column_dimensions['A'].width = 60
        ws4.column_dimensions['B'].width = 18

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    # Имя файла кириллицей: заголовок HTTP допускает только latin-1, поэтому
    # обязателен процент-энкодинг по RFC 5987, иначе starlette падает на .encode.
    from urllib.parse import quote
    name = f"Финотчёт_{BASIS_LABEL[basis].replace(' ', '_')}_{VAT_LABEL[vat].replace(' ', '_')}"
    if date_from or date_to:
        name += f"_{date_from or ''}-{date_to or ''}"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f"attachment; filename=finreport.xlsx; filename*=UTF-8''{quote(name)}.xlsx"},
    )
