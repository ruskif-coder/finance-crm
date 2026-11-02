# -*- coding: utf-8 -*-
"""Сводка плана оплат (хендофф «План оплат · виджеты сводки», 02.11.2026).

Ожидаемые числа — литералы, посчитанные руками по строкам макета (они же строки стенда). Поломки, которые ловят тесты:
заглушка «ПЛАН» попала в топ или в дубли; хвосты прошлого года считаются по году операции, а не по периоду; «уже
списано?» не находит проведённую операцию; пин с нулём остаётся на экране; кредит считается лимитом, а не свободным
остатком; знак «не хватает» задваивается.
"""
from datetime import date

from app.pay_plan_summary import money, summarize


def _r(i, s, period, art, cp_id, cp, bank=None, inv=None, d=None):
    return {"id": i, "sum": s, "bank": bank, "period": period, "article": art, "counterparty_id": cp_id,
            "counterparty": cp, "invoice": inv, "date": d}


ROWS = [
    _r(1, 5272746.61, "Q4 2025", "СК АГЕНТСКАЯ", 10, "МЕГАБАЙТ ООО"),
    _r(2, 4000000, "2025-04", "АПТЕКА", 11, "РИГЛА ООО"),
    _r(3, 2160080.06, "Q3 2026", "СК АГЕНТСКАЯ", 12, "УАЙТ БОКС МЕДИА ООО", inv="8003"),
    _r(4, 1393140, "2026-08", "СК АГЕНТСКАЯ", 99, "ПЛАН"),
    _r(5, 1049993.28, "Q3 2025", "СК АГЕНТСКАЯ", 13, "МБР ООО"),
    _r(6, 782208, "Q4 2025", "СК АГЕНТСКАЯ", 13, "МБР ООО"),
    _r(7, 565000, "2026-07", "СК АГЕНТСКАЯ", 99, "ПЛАН"),
    _r(8, 300231.63, "Q1 2026", "БОНУСЫ", 14, "ПРОГРАММАТИК МЕДИА ООО", bank="Наличные", d=date(2026, 11, 5)),
    _r(9, 14000, "2026-08", "IT", 15, "1-Й НОСОРОГ ООО", inv="8"),
]
DONE = [{"counterparty_id": 12, "sum": 2160080.06, "date": date(2026, 10, 24), "bank": "АльфаБанк"},
        {"counterparty_id": 10, "sum": 1.0, "date": date(2026, 10, 1), "bank": "ОПТ Банк"}]


def test_total_count_and_counterparties_without_the_stub():
    s = summarize(ROWS, DONE, 2026)
    assert round(s["total"], 2) == 15537399.58
    assert s["count"] == 9
    assert s["counterparties"] == 6          # МЕГАБАЙТ, РИГЛА, УАЙТ БОКС, МБР, ПРОГРАММАТИК, НОСОРОГ — без «ПЛАН»


def test_last_year_tails_are_read_from_the_period():
    ages = {a["key"]: a for a in summarize(ROWS, DONE, 2026)["ages"]}
    assert round(ages["old"]["sum"], 2) == 11104947.89          # 5272746.61 + 4000000 + 1049993.28 + 782208
    assert ages["old"]["label"] == "хвосты 2025 года" and sorted(ages["old"]["ids"]) == [1, 2, 5, 6]
    assert ages["cur"]["label"] == "2026 год" and round(ages["cur"]["sum"], 2) == 4432451.69


def test_articles_by_sum_with_share_and_count():
    arts = summarize(ROWS, DONE, 2026)["articles"]
    assert [a["name"] for a in arts] == ["СК АГЕНТСКАЯ", "АПТЕКА", "БОНУСЫ", "IT"]
    assert arts[0]["count"] == 6 and arts[0]["pct"] == 72       # 11 223 167,95 / 15 537 399,58
    assert sorted(arts[0]["ids"]) == [1, 3, 4, 5, 6, 7]


def test_top_recipients_skip_the_stub_and_list_periods():
    top = summarize(ROWS, DONE, 2026)["top"]
    assert [t["name"] for t in top] == ["МЕГАБАЙТ ООО", "РИГЛА ООО", "УАЙТ БОКС МЕДИА ООО", "МБР ООО",
                                        "ПРОГРАММАТИК МЕДИА ООО"]
    mbr = top[3]
    assert mbr["count"] == 2 and mbr["periods"] == ["Q3 2025", "Q4 2025"] and round(mbr["sum"], 2) == 1832201.28


def test_duplicate_tags():
    tags = summarize(ROWS, DONE, 2026)["tags"]
    assert tags[3]["kind"] == "done" and "24.10.26" in tags[3]["text"] and "АльфаБанк" in tags[3]["text"]
    assert tags[5]["kind"] == "twin" and tags[6]["kind"] == "twin"
    assert 4 not in tags and 7 not in tags, "заглушка «ПЛАН» в повторы не попадает"
    assert 1 not in tags, "другая сумма у того же контрагента — не дубль"


def test_pins_hide_zero_and_count_out_of_all():
    pins = {p["key"]: p for p in summarize(ROWS, DONE, 2026)["pins"]}
    assert pins["dup"]["count"] == 3
    assert pins["nodate"]["count"] == 8
    assert pins["nobank"]["count"] == 8
    assert pins["noinv"]["count"] == 7
    assert pins["stub"]["count"] == 2 and sorted(pins["stub"]["ids"]) == [4, 7]
    assert sorted(summarize(ROWS, DONE, 2026)["stub_ids"]) == [4, 7]
    clean = summarize([_r(1, 10, "2026-10", "IT", 1, "А", bank="АльфаБанк", inv="1", d=date(2026, 11, 3))], [], 2026)
    assert clean["pins"] == []


def test_money_counts_free_credit_and_gaps_without_a_sign():
    banks = [{"bank": "АльфаБанк", "balance": 6840000}, {"bank": "ОПТ Банк", "balance": 2120000},
             {"bank": "Совкомбанк", "balance": 410000}, {"bank": "Наличные", "balance": 180000}]
    lines = [{"bank": "АльфаБанк", "limit_amount": 10000000, "used_amount": 3500000}]
    m = money(banks, lines, total=19272810)
    assert m["banks"] == 9370000 and m["bank_count"] == 3 and m["cash"] == 180000
    assert m["credit"] == {"free": 6500000, "limit": 10000000, "banks": ["АльфаБанк"]}
    assert m["own"] == {"short": True, "value": 9722810}
    assert m["with_credit"] == {"short": True, "value": 3222810}


def test_money_without_credit_lines_has_no_credit_comparison():
    m = money([{"bank": "АльфаБанк", "balance": 100}, {"bank": "Наличные", "balance": 0}], [], total=40)
    assert m["credit"] is None and m["with_credit"] is None
    assert m["own"] == {"short": False, "value": 60}


def test_balances_are_shown_only_with_the_balance_right():
    """Поломка: остатки банков уходят тому, у кого нет «Баланс: просмотр»."""
    from types import SimpleNamespace

    from app.database import SessionLocal
    from app import pay_plan_summary as pps
    db = SessionLocal()
    try:
        admin = SimpleNamespace(id=-1, role=SimpleNamespace(key="admin"), role_id=None)
        nobody = SimpleNamespace(id=-2, role=SimpleNamespace(key="__нет__"), role_id=-999)
        assert pps.load(db, admin)["money"] is not None
        got = pps.load(db, nobody)
        assert got["money"] is None and "total" in got
    finally:
        db.close()
