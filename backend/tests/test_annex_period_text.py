"""Период размещения в ТЕКСТЕ ДС — по датам строк, а не по финансовому месяцу (05.11.2026).

Поломка на проде: ДС мастер-сделки SA5JUK — в таблице строки «с 07.11 по 30.11», а в тексте
«с 01.11 по 30.11». Мастер-ДС хранит период документа как весь месяц (`to_annex._bounds`),
и текст брал его. Тест падает, если `{период_с}`/`{период_по}` снова возьмут период документа
при строках с датами.
"""
from datetime import date

from app.annex_tpl.assemble import placement_span

NOV = (date(2026, 11, 1), date(2026, 11, 30))


def test_text_period_is_taken_from_row_dates_not_the_month():
    rows = [{"date_from": date(2026, 11, 7), "date_to": date(2026, 11, 30)},
            {"date_from": date(2026, 11, 10), "date_to": date(2026, 11, 20)}]
    assert placement_span(rows, *NOV) == (date(2026, 11, 7), date(2026, 11, 30))


def test_rows_without_dates_do_not_widen_the_span():
    # строка скидки и доп. услуга дат не имеют — период по размещению
    rows = [{"date_from": date(2026, 10, 1), "date_to": date(2026, 10, 15)},
            {"date_from": None, "date_to": None, "kind": "discount"},
            {"kind": "extra"}]
    assert placement_span(rows, date(2026, 10, 1), date(2026, 10, 31)) == (date(2026, 10, 1), date(2026, 10, 15))


def test_dates_as_strings_are_read_too():
    rows = [{"date_from": "2026-11-07", "date_to": "2026-11-30T00:00:00"}]
    assert placement_span(rows, *NOV) == (date(2026, 11, 7), date(2026, 11, 30))


def test_no_dated_rows_falls_back_to_document_period():
    assert placement_span([], *NOV) == NOV
    assert placement_span([{"kind": "extra"}], *NOV) == NOV


def test_master_annex_default_date_is_rk_start_from_rows():
    # Владелец 05.11.2026: дата ДС мастер-сделки по умолчанию — начало РК из строк, а не 1-е число месяца
    from app.master_deal.to_annex import default_date
    rows = [{"date_from": "2026-11-07", "date_to": "2026-11-30"}, {"kind": "discount", "date_from": None}]
    assert default_date(rows, *NOV) == date(2026, 11, 7)
    assert default_date([], *NOV) == date(2026, 11, 1)
