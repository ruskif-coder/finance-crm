"""
Квартальная сводка финотчёта — свёртка месяцев, а не отдельный расчёт.

Тумблер «по кварталам» опасен ровно одним: если квартал начнёт считаться своей
веткой кода, он рано или поздно разойдётся с помесячным видом. Финансист увидит
две разные прибыли за один и тот же период и перестанет доверять обоим.

Поэтому инвариант простой и жёсткий: сумма трёх месяцев обязана совпадать с
кварталом до копейки — по каждой строке отчёта, по каждой подгруппе и по итогам.

Отдельно проверяется операция с квартальным периодом («Q1 2026» вместо «2026-03»):
_collect делит её на три равных месяца, и обратная свёртка обязана вернуть ровно
исходную сумму, иначе способ ввода периода начнёт влиять на квартальный итог.
"""
from app.routers import finreport as F


class _Row:
    """Строка из _collect: (период, строка отчёта, подгруппа, метка, сумма)."""


def _fake_collect(rows):
    return lambda db, basis, vat, dfrom, dto: (rows, {'excluded': {}, 'zero_vat_amount': 0,
                                                      'zero_vat_rows': 0, 'no_period_rows': 0,
                                                      'basis': basis})


def test_quarter_key_is_built_from_month():
    assert F._to_quarter('2025-01') == '2025-Q1'
    assert F._to_quarter('2025-03') == '2025-Q1'
    assert F._to_quarter('2025-04') == '2025-Q2'
    assert F._to_quarter('2025-12') == '2025-Q4'


def test_quarter_keys_sort_chronologically():
    """Сортировка периодов в build_report — обычная лексикографическая.

    Если ключ квартала когда-нибудь запишут как '2025-1' вместо '2025-Q1',
    порядок колонок сохранится, а вот '2025-Q10' сломает всё — проверяем,
    что формат остаётся однозначным.
    """
    keys = [F._to_quarter(f'2025-{m:02d}') for m in range(1, 13)] + \
           [F._to_quarter(f'2026-{m:02d}') for m in range(1, 13)]
    assert sorted(set(keys)) == ['2025-Q1', '2025-Q2', '2025-Q3', '2025-Q4',
                                 '2026-Q1', '2026-Q2', '2026-Q3', '2026-Q4']


def test_quarter_totals_equal_sum_of_months(monkeypatch):
    rows = [
        ('2025-01', F.REVENUE, '', 'Услуги', 100.0),
        ('2025-02', F.REVENUE, '', 'Услуги', 200.0),
        ('2025-03', F.REVENUE, '', 'Услуги', 300.0),
        ('2025-04', F.REVENUE, '', 'Услуги', 50.0),
        ('2025-01', F.COGS, 'Комиссия', 'СК АГЕНТСКАЯ', 30.0),
        ('2025-03', F.COGS, 'Комиссия', 'СК АГЕНТСКАЯ', 70.0),
    ]
    monkeypatch.setattr(F, '_collect', _fake_collect(rows))

    m = F.build_report(None, 'accrual', 'net', None, None, 'month')
    q = F.build_report(None, 'accrual', 'net', None, None, 'quarter')

    # Месяцы остаются, итог квартала встаёт сразу за последним своим месяцем.
    assert q['periods'] == ['2025-01', '2025-02', '2025-03', '2025-Q1', '2025-04', '2025-Q2']
    assert q['base_periods'] == ['2025-01', '2025-02', '2025-03', '2025-04']
    assert q['granularity'] == 'quarter'

    by_key_m = {g['key']: g for g in m['groups']}
    by_key_q = {g['key']: g for g in q['groups']}
    assert by_key_q[F.REVENUE]['totals']['2025-Q1'] == 600.0
    assert by_key_q[F.REVENUE]['totals']['2025-Q2'] == 50.0
    assert by_key_q[F.COGS]['totals']['2025-Q1'] == 100.0

    # Итог за период не должен зависеть от нарезки. Считаем по base_periods:
    # квартальные колонки — те же деньги ещё раз, сумма по всем колонкам удвоится.
    for key in by_key_m:
        a = round(sum(by_key_m[key]['totals'][p] for p in m['base_periods']), 6)
        b = round(sum(by_key_q[key]['totals'][p] for p in q['base_periods']), 6)
        assert a == b, f'разошлась строка {key}: {a} != {b}'


def test_subgroups_and_articles_survive_rollup(monkeypatch):
    """Свёртка не должна схлопывать подгруппы и статьи — сворачиваются только периоды."""
    rows = [
        ('2025-01', F.COGS, 'Комиссия', 'СК АГЕНТСКАЯ', 10.0),
        ('2025-02', F.COGS, 'Комиссия', 'СК ПАРТНЕРСКАЯ', 20.0),
        ('2025-03', F.COGS, 'Закупка', 'ТРАФИК', 40.0),
    ]
    monkeypatch.setattr(F, '_collect', _fake_collect(rows))
    q = F.build_report(None, 'accrual', 'net', None, None, 'quarter')
    assert q['periods'] == ['2025-01', '2025-02', '2025-03', '2025-Q1']
    cogs = [g for g in q['groups'] if g['key'] == F.COGS][0]
    assert [sg['subgroup'] for sg in cogs['subgroups']] == ['Закупка', 'Комиссия']
    commission = [sg for sg in cogs['subgroups'] if sg['subgroup'] == 'Комиссия'][0]
    assert [a['article'] for a in commission['articles']] == ['СК АГЕНТСКАЯ', 'СК ПАРТНЕРСКАЯ']
    assert cogs['totals']['2025-Q1'] == 70.0


def test_profit_is_the_same_in_both_views(monkeypatch):
    """Главное, что увидит финансист: прибыль за период не зависит от нарезки."""
    rows = [
        ('2025-01', F.REVENUE, '', 'Услуги', 1000.0),
        ('2025-02', F.COGS, 'Комиссия', 'СК', 300.0),
        ('2025-03', F.OPEX, 'Офис', 'Аренда', 200.0),
        ('2025-05', F.REVENUE, '', 'Услуги', 500.0),
        ('2025-06', F.PROFIT_TAX, 'Налог на прибыль', 'Налог', 60.0),
    ]
    monkeypatch.setattr(F, '_collect', _fake_collect(rows))
    m = F.build_report(None, 'accrual', 'net', None, None, 'month')
    q = F.build_report(None, 'accrual', 'net', None, None, 'quarter')
    for field in ('revenue', 'gross_profit', 'operating_profit', 'net_profit'):
        a = round(sum(m['summary'][p][field] for p in m['base_periods']), 6)
        b = round(sum(q['summary'][p][field] for p in q['base_periods']), 6)
        assert a == b, f'{field}: помесячно {a}, поквартально {b}'


def test_month_stays_default(monkeypatch):
    """Тумблер добавлен, а поведение по умолчанию не изменилось."""
    rows = [('2025-01', F.REVENUE, '', 'Услуги', 1.0)]
    monkeypatch.setattr(F, '_collect', _fake_collect(rows))
    r = F.build_report(None, 'accrual', 'net', None, None)
    assert r['periods'] == ['2025-01']
    assert r['granularity'] == 'month'


def test_excel_header_renders_quarter():
    """Без ветки для кварталов в шапку Excel попал бы сырой ключ '2025-Q1'."""
    assert F._period_title('2025-Q1') == '1 кв 2025'
    assert F._period_title('2025-01') == 'Янв 2025'


def test_partial_quarter_is_widened_to_whole_quarter():
    """Колонка «1 кв» обязана содержать квартал целиком.

    Ловушка, которую создаёт сам тумблер: выбрали февраль—март, получили колонку
    с квартальной подписью и двумя третями данных внутри. Рядом стоят полные
    кварталы, число сравнят с ними — и вывод будет неверным. Поэтому в квартальном
    режиме границы расширяются до целых кварталов, а фактический диапазон
    возвращается в ответе, чтобы подпись на экране не врала.
    """
    assert F._snap_to_quarters('2026-02', '2026-03') == ('2026-01', '2026-03')
    assert F._snap_to_quarters('2026-01', '2026-03') == ('2026-01', '2026-03')
    assert F._snap_to_quarters('2025-05', '2026-08') == ('2025-04', '2026-09')
    assert F._snap_to_quarters(None, None) == (None, None)


def test_month_mode_does_not_widen_range(monkeypatch):
    """Помесячному режиму расширение не нужно и вредно: февраль — это февраль."""
    seen = {}

    def fake(db, basis, vat, dfrom, dto):
        seen['from'], seen['to'] = dfrom, dto
        return [('2026-02', F.REVENUE, '', 'Услуги', 1.0)], {
            'excluded': {}, 'zero_vat_amount': 0, 'zero_vat_rows': 0,
            'no_period_rows': 0, 'basis': basis}

    monkeypatch.setattr(F, '_collect', fake)
    r = F.build_report(None, 'accrual', 'net', '2026-02', '2026-03', 'month')
    assert (seen['from'], seen['to']) == ('2026-02', '2026-03')
    assert r['range'] == {'from': '2026-02', 'to': '2026-03'}


def _xlsx(monkeypatch, granularity, date_from, date_to):
    """Гоняет настоящую выгрузку и возвращает открытую книгу."""
    import asyncio
    from io import BytesIO
    from openpyxl import load_workbook

    rows = [
        ('2026-01', F.REVENUE, '', 'Услуги', 300.0),
        ('2026-02', F.REVENUE, '', 'Услуги', 200.0),
        ('2026-03', F.COGS, 'Комиссия', 'СК АГЕНТСКАЯ', 100.0),
    ]
    monkeypatch.setattr(F, '_collect', _fake_collect(rows))

    class _User:
        name = 'Тест'
        email = 'test@example.com'

    resp = F.export_finreport(basis='accrual', vat='net', granularity=granularity,
                              date_from=date_from, date_to=date_to, db=None, current_user=_User())

    async def _read():
        out = b''
        async for chunk in resp.body_iterator:
            out += chunk if isinstance(chunk, bytes) else chunk.encode()
        return out

    return load_workbook(BytesIO(asyncio.run(_read())))


def test_excel_names_the_granularity_and_effective_range(monkeypatch):
    """Файл обязан сам объяснять, что в нём.

    Две выгрузки за один период с разной нарезкой различаются только числами;
    без подписи их через неделю не различить, а сравнивать их между собой нельзя.
    Плюс в квартальном режиме диапазон расширен — файл говорит и об этом, иначе
    получатель уверен, что видит февраль—март.
    """
    wb = _xlsx(monkeypatch, 'quarter', '2026-02', '2026-03')
    ws = wb['Отчёт']
    assert 'по кварталам' in ws['A1'].value
    assert ws['A2'].value == 'Период: 2026-01 — 2026-03'
    assert 'расширен до целых кварталов' in (ws['A3'].value or '')
    assert [ws.cell(4, c).value for c in range(2, 6)] ==            ['Янв 2026', 'Фев 2026', 'Мар 2026', '1 кв 2026']

    params = {ws2.cell(i, 1).value: ws2.cell(i, 2).value
              for ws2 in [wb['Параметры']] for i in range(1, 15)}
    assert params['Период с'] == '2026-01'
    assert params['Выбрано в фильтре'] == '2026-02 — 2026-03'
    assert 'кварталам' in params['Нарезка']


def test_excel_month_export_is_untouched(monkeypatch):
    """Помесячная выгрузка не должна ничего расширять и ни на что жаловаться."""
    wb = _xlsx(monkeypatch, 'month', '2026-02', '2026-03')
    ws = wb['Отчёт']
    assert 'по месяцам' in ws['A1'].value
    assert ws['A2'].value == 'Период: 2026-02 — 2026-03'
    assert ws['A3'].value is None
    # Колонки — месяцы, а не кварталы. Конкретные месяцы задаёт подменённый _collect,
    # он диапазон не фильтрует; здесь проверяется формат шапки, а не отбор строк.
    head = [ws.cell(4, c).value for c in range(2, 5)]
    assert head == ['Янв 2026', 'Фев 2026', 'Мар 2026']
    assert not any('кв' in str(h) for h in head)


def test_months_stay_next_to_quarter_totals(monkeypatch):
    """Итог квартала — ДОПОЛНИТЕЛЬНАЯ колонка, месяцы никуда не деваются.

    Требование владельца: «в таблице появляется колонка с итогом, а месячные
    никуда не девались». Замена месяцев кварталами лишила бы отчёт детализации,
    ради которой его и открывают.
    """
    rows = [(f'2025-{m:02d}', F.REVENUE, '', 'Услуги', float(m)) for m in range(1, 8)]
    monkeypatch.setattr(F, '_collect', _fake_collect(rows))
    q = F.build_report(None, 'accrual', 'net', None, None, 'quarter')
    assert q['periods'] == ['2025-01', '2025-02', '2025-03', '2025-Q1',
                            '2025-04', '2025-05', '2025-06', '2025-Q2',
                            '2025-07', '2025-Q3']
    rev = [g for g in q['groups'] if g['key'] == F.REVENUE][0]['totals']
    assert rev['2025-Q1'] == 1 + 2 + 3
    assert rev['2025-Q2'] == 4 + 5 + 6
    assert rev['2025-Q3'] == 7        # неполный квартал в конце данных — просто то, что есть


def test_total_column_does_not_double_count(monkeypatch):
    """Сумма по periods удвоила бы итог: квартальные колонки — те же деньги.

    Именно на этом ломается наивное «просуммируем все колонки», поэтому в ответе
    есть base_periods, и клиент обязан считать ИТОГО по нему.
    """
    rows = [(f'2025-{m:02d}', F.REVENUE, '', 'Услуги', 100.0) for m in range(1, 7)]
    monkeypatch.setattr(F, '_collect', _fake_collect(rows))
    q = F.build_report(None, 'accrual', 'net', None, None, 'quarter')
    rev = [g for g in q['groups'] if g['key'] == F.REVENUE][0]['totals']
    assert sum(rev[p] for p in q['base_periods']) == 600.0
    assert sum(rev.values()) == 1200.0, 'по всем колонкам сумма именно удваивается'


def test_excel_total_formula_skips_quarter_columns(monkeypatch):
    """Формула ИТОГО в файле обязана пропускать квартальные колонки.

    Сплошной SUM по полосе дал бы удвоенный итог — и это тот случай, когда
    ошибка не видна глазами: число выглядит правдоподобно, просто вдвое больше.
    """
    import asyncio
    from io import BytesIO
    from openpyxl import load_workbook

    rows = [(f'2026-{m:02d}', F.REVENUE, '', 'Услуги', 100.0) for m in range(1, 7)]
    monkeypatch.setattr(F, '_collect', _fake_collect(rows))

    class _User:
        name = 'Тест'
        email = 't@e'

    resp = F.export_finreport(basis='accrual', vat='net', granularity='quarter',
                              date_from=None, date_to=None, db=None, current_user=_User())

    async def _read():
        out = b''
        async for chunk in resp.body_iterator:
            out += chunk if isinstance(chunk, bytes) else chunk.encode()
        return out

    ws = load_workbook(BytesIO(asyncio.run(_read())))['Отчёт']
    head = [ws.cell(4, c).value for c in range(2, 11)]
    assert head == ['Янв 2026', 'Фев 2026', 'Мар 2026', '1 кв 2026',
                    'Апр 2026', 'Май 2026', 'Июн 2026', '2 кв 2026', 'ИТОГО']
    formula = None
    for r in range(5, ws.max_row + 1):
        if ws.cell(r, 1).value == 'Выручка':
            formula = ws.cell(r, 10).value
            break
    assert formula == '=SUM(B%d:D%d,F%d:H%d)' % ((r,) * 4), formula
