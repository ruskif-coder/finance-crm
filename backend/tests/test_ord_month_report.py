# -*- coding: utf-8 -*-
"""Отчёт ОРД за месяц (владелец 11.11.2026, образец «пример по выгрузке.xlsx»): строка — сделка × площадка × ЕРИД; «Сумма на
площадку» — доля сделки в УПД с НДС, разложенная по площадкам пропорционально показам; несколько ЕРИД на площадке — делим
по факту DSP по креативу; импорт хранит только отличия от расчёта. Ожидаемое — руками."""
from datetime import date

import pytest

from app.ord import month_report as MR
from app.ord import month_report_xlsx as MX


def test_split_int_keeps_the_total_and_gives_remainder_to_largest_fraction():
    # 10 показов на веса 1:1:1 → 3,33 каждому; остаток 1 — первому по дробной части (все равны → первый)
    assert MR.split_int(10, [1, 1, 1]) == [4, 3, 3]
    assert MR.split_int(100, [3, 1]) == [75, 25]
    assert MR.split_int(7, [0, 0]) is None


def test_erid_split_by_dsp_creative_fact_merges_same_erid():
    # площадка 1000 показов / 10 кликов; креативы: ЕРИД A 300 + ЕРИД A 100 + ЕРИД B 400 → A 50 %, B 50 %
    out = MR.erid_split(1000, 10, [("A", 300), ("A", 100), ("B", 400)])
    assert out == [("A", 500, 5), ("B", 500, 5)]


def test_erid_split_without_creative_fact_returns_none():
    assert MR.erid_split(1000, 10, []) is None
    assert MR.erid_split(1000, 10, [("A", 0)]) is None


def test_amount_is_spread_by_shows_and_sums_to_the_kopeck():
    # пример владельца: бюджет 30 500 на площадки по показам 10 000 / 20 000 / 30 000 → 5 083,33 / 10 166,67 / 15 250,00
    assert MR.spread_amount(30500.0, [10000, 20000, 30000]) == [5083.33, 10166.67, 15250.0]
    assert MR.spread_amount(100.0, [0, 0]) == [100.0, 0.0], "нет факта — вся сумма первой строке, ничего не теряется"


def test_deal_shares_of_a_kit_follow_its_lines_and_sum_to_the_budget():
    lines = [{"deal_id": 1, "gross": 600.0}, {"deal_id": 2, "gross": 300.0}, {"deal_id": 1, "gross": 100.0}]
    # бюджет из 1С 1 000,01 → сделка 1 — 70 %, сделка 2 — 30 %, копейка — последней
    assert MR.deal_shares(1000.01, lines) == {1: 700.01, 2: 300.0}


def test_addons_do_not_go_to_ord_only_placement_share_counts():
    """Владелец 11.11.2026: «допы не идут в орд». УПД 1 000 (размещение 800 + доп 200), из 1С пришло 1 000,02 →
    доли строк по бюджету: 800,02 и 200,00; в ОРД у сделки только размещение — 800,02."""
    lines = [{"deal_id": 1, "gross": 800.0, "kind": "размещение"}, {"deal_id": 1, "gross": 200.0, "kind": "доп"}]
    assert MR.deal_shares(1000.02, lines) == {1: 800.02}
    assert MR.deal_shares(200.0, [{"deal_id": 1, "gross": 200.0, "kind": "доп"}]) == {}, "УПД одних допов в ОРД не идёт"


def _row(code="AAA111", domain="a.ru", erid="E1", shows=100, clicks=1, amount=50.0):
    return {"deal_code": code, "deal_id": 7, "deal_title": "Т", "master_code": "M-0001", "upd_no": "204",
            "upd_date": date(2026, 10, 31), "upd_gross": 100.0, "deal_gross": 100.0, "domain": domain, "publisher_id": 3,
            "shows": shows, "clicks": clicks, "erid": erid, "amount": amount, "note": ""}


def test_overrides_edit_remove_and_add():
    rows = [_row(domain="a.ru"), _row(domain="b.ru")]
    ovs = [{"kind": "правка", "deal_code": "AAA111", "domain": "a.ru", "erid": "E1", "shows": 90, "clicks": None,
            "amount": None, "upd_no": None, "upd_date": None, "upd_gross": None, "deal_id": 7, "publisher_id": 3},
           {"kind": "убрана", "deal_code": "AAA111", "domain": "b.ru", "erid": "E1"},
           {"kind": "добавлена", "deal_code": "AAA111", "domain": "c.ru", "erid": "E9", "shows": 5, "clicks": 0, "amount": 1.5,
            "upd_no": "204", "upd_date": date(2026, 10, 31), "upd_gross": 100.0, "deal_id": 7, "publisher_id": None}]
    out = MR.apply_overrides(rows, ovs)
    assert [(r["domain"], r["shows"], r["clicks"], r["edited"]) for r in out] == [("a.ru", 90, 1, True), ("c.ru", 5, 0, True)]
    assert rows[0]["shows"] == 100, "расчёт не меняется на месте"


def test_diff_keeps_only_changes():
    calc = [_row(domain="a.ru"), _row(domain="b.ru")]
    file = [{**_row(domain="a.ru"), "amount": 49.99, "shows": 100},       # сумма поправлена, показы те же
            {**_row(domain="c.ru", erid="E9", shows=5, amount=1.0)}]     # новой строки нет в расчёте; b.ru убрана
    ovs = MR.diff(calc, file)
    assert sorted((o["kind"], o["domain"]) for o in ovs) == [("добавлена", "c.ru"), ("правка", "a.ru"), ("убрана", "b.ru")]
    edit = next(o for o in ovs if o["kind"] == "правка")
    assert edit["amount"] == 49.99 and edit["shows"] is None, "непоправленное поле — пусто"


def test_diff_of_unchanged_file_is_empty():
    calc = [_row(domain="a.ru")]
    assert MR.diff(calc, [dict(calc[0])]) == []


def test_diff_refuses_duplicate_keys_in_the_file():
    calc = [_row()]
    with pytest.raises(MR.ReportError):
        MR.diff(calc, [_row(), _row()])


def test_xlsx_round_trip_keeps_values():
    rows = [_row(domain="120на80.рф", amount=7131.93), _row(domain="a.ru", erid="E1, E2", shows=0, amount=0.0)]
    data = MX.to_xlsx(rows, date(2026, 10, 1))
    back = MX.parse_xlsx(data)
    assert [(r["deal_code"], r["domain"], r["shows"], r["clicks"], r["erid"], r["amount"], r["upd_no"], r["upd_gross"])
            for r in back] == [("AAA111", "120на80.рф", 100, 1, "E1", 7131.93, "204", 100.0),
                               ("AAA111", "a.ru", 0, 1, "E1, E2", 0.0, "204", 100.0)]
    assert back[0]["upd_date"] == date(2026, 10, 31)


def test_xlsx_without_required_columns_is_refused():
    import io
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.append(["что-то", "другое"])
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(MR.ReportError):
        MX.parse_xlsx(buf.getvalue())


def test_stand_month_rows_sum_to_each_deal_share_in_its_upd():
    """Инвариант на данных стенда: строки сделки в одном УПД в сумме — её доля размещения (до копейки)."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        months = [r[0] for r in db.execute(__import__("sqlalchemy").text(
            "SELECT DISTINCT period FROM master_deals m JOIN master_deal_upds k ON k.master_deal_id = m.id"))]
        if not months:
            pytest.skip("на стенде нет комплектов УПД")
        y, mo = (int(x) for x in sorted(months)[-1].split("-"))
        rows = MR.compute(db, date(y, mo, 1))
        acc = {}
        for r in rows:
            a = acc.setdefault((r["master_code"], r["kit_no"], r["deal_code"]), [r["deal_gross"], 0.0])
            a[1] += r["amount"]
        assert all(abs(g - s) < 0.005 for g, s in acc.values()), [k for k, (g, s) in acc.items() if abs(g - s) >= 0.005]
    finally:
        db.rollback()
        db.close()


def test_import_of_a_file_without_rows_is_refused_not_wiping_the_month():
    """Ревью 11.11.2026: шапка без строк превращала весь расчёт в «убрана» — отчёт месяца пустел. Пустой файл — отказ."""
    from app.ord import month_report_store as ST
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        with pytest.raises(MR.ReportError):
            ST.import_file(db, date(2026, 10, 1), [], None, "пусто.xlsx")
    finally:
        db.rollback()
        db.close()


def _sheet(rows):
    import io
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.append([t for _k, t, _w in MX.COLS])
    for r in rows:
        wb.active.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cells(**kw):
    base = {"deal_code": "AAA111", "domain": "a.ru", "erid": "E1", "shows": 1, "clicks": 0, "amount": 1.0}
    base.update(kw)
    return [base.get(k) for k, _t, _w in MX.COLS]


@pytest.mark.parametrize("bad", [{"deal_code": "X" * 17}, {"upd_no": "9" * 41}, {"erid": "E" * 256},
                                 {"amount": "inf"}, {"shows": "1e30"}, {"amount": "nan"}])
def test_values_the_table_cannot_hold_are_refused_with_a_row_number(bad):
    """Ревью 11.11.2026: длинный ID РК / № УПД / ЕРИД и бесконечность падали 500 на записи. Должен быть понятный отказ."""
    with pytest.raises(MR.ReportError, match="Строка 2"):
        MX.parse_xlsx(_sheet([_cells(**bad)]))


def test_ties_in_shows_keep_a_stable_order_by_placement():
    """Ревью 11.11.2026: при равных показах порядок строк плавал, а остаток копейки идёт последней строке — повторная
    загрузка нетронутого файла давала «правку». Порядок площадок сделки — показы, затем id размещения."""
    import inspect
    src = inspect.getsource(MR._placements)
    assert "sum(s.shows) DESC, p.id" in src
    assert "ORDER BY" in inspect.getsource(MR._snapshot)


def test_blank_cell_means_not_edited_not_a_phantom_edit():
    """Ревью 11.11.2026: пустая ячейка суммы / № УПД / даты считалась «правкой», а писала пусто — счётчик правок врал.
    Пустое = «не правили» (так и записано в миграции); показы и клики пустыми не бывают — пусто там читается как 0."""
    calc = [_row(domain="a.ru")]
    blank = {**_row(domain="a.ru"), "amount": None, "upd_no": None, "upd_date": None, "upd_gross": None}
    assert MR.diff(calc, [blank]) == []


def test_fallback_without_annex_lines_keeps_addons_out_of_ord():
    """Ревью 11.11.2026: комплект без строк ДС делил ВЕСЬ бюджет между сделками поровну — допы уходили в ОРД.
    Без строк ДС доли берутся из строк пакета (размещение и допы раздельно): УПД 1 000 = размещение 800 + доп 200 → 800."""
    lines = MR.fallback_lines([{"deal_id": 1, "kind": "base", "net": 800.0}, {"deal_id": 1, "kind": "extra", "net": 200.0}])
    assert MR.deal_shares(1000.0, lines) == {1: 800.0}


def test_snapshot_row_goes_away_with_its_creative():
    """Ревью 11.11.2026: при ON DELETE SET NULL удаление второго креатива площадки за месяц упиралось в уникальность
    (месяц, размещение, креатив) с NULLS NOT DISTINCT — две строки с пустым креативом. Строка снимка без креатива смысла
    не имеет: удаляется вместе с ним."""
    from sqlalchemy import text
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        rule = db.execute(text("""SELECT rc.delete_rule FROM information_schema.referential_constraints rc
                                   JOIN information_schema.key_column_usage k ON k.constraint_name = rc.constraint_name
                                  WHERE k.table_name = 'ord_erid_month_stat' AND k.column_name = 'creative_id'""")).scalar()
        assert rule == "CASCADE"
    finally:
        db.close()


def test_deal_in_second_kit_does_not_report_its_shows_twice():
    """Владелец 11.11.2026: сделка в двух УПД месяца (на данных не встречается — страховка) — показы один раз, в первом
    комплекте; во втором — её доля суммы одной строкой без показов; обе с пометкой «проверить». Поломка, которую ловит:
    площадки сделки повторены под вторым комплектом — показы в ОРД вдвое."""
    places = [{"placement_id": 1, "publisher_id": 3, "domain": "a.ru", "shows": 1000, "clicks": 4, "deal_id": 7}]
    deal = {"id": 7, "code": "AAA111", "title": "Т"}
    head = {"master_code": "M-0001", "upd_no": "204", "upd_date": None, "upd_gross": 300.0, "kit_no": 2}
    rows = MR.deal_rows_again(deal, head, 300.0)
    assert [(r["domain"], r["shows"], r["clicks"], r["amount"]) for r in rows] == [("", 0, 0, 300.0)]
    assert MR.TWO_UPD in rows[0]["note"]
    assert places  # первый комплект строит строки площадок обычным путём
