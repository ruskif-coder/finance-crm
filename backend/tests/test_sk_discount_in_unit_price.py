# -*- coding: utf-8 -*-
"""Скидка СК «в счёт» — через цену единицы, а не строкой «Скидка СК» (владелец 11.11.2026, после разговора с бухгалтером:
«скидка в счёт идёт за счёт уменьшения цены единицы закупки; у себя фиксируем, что пакет со скидкой в счёт, в ДС пункт убираем»).

Поломка, которую ловят: строка с минусом в ДС, которую заявка бухгалтеру пропускает (`document.upd_rows`), — бухгалтер выставил
M-0032…35 на суммы без скидки (M-0035: 610 610 вместо 330 950,62). Ожидаемое — руками."""
from app.master_deal import layout as LY


def _base(net, unit_price, deal_id=1, code="AAA111", pct=30.0, model="CPM", volume=None):
    return {"deal_id": deal_id, "deal": code, "brand": "Бренд", "service": "Услуга", "sk_pct": pct, "kind": "base",
            "model": model, "volume": volume, "unit_price": unit_price, "net": net}


def _extra(net, deal_id=1, code="AAA111", pct=30.0):
    return {"deal_id": deal_id, "deal": code, "brand": "Бренд", "service": "Услуга", "sk_pct": pct, "kind": "extra",
            "model": "Фикс", "volume": None, "unit_price": net, "net": net}


def test_discount_lowers_the_placement_row_and_its_unit_price_no_minus_row():
    out = LY._fold_discounts([_base(100000.0, 200.0, volume=500000), _extra(20000.0)])
    assert [r["kind"] for r in out] == ["base", "extra"], "строки «Скидка СК» нет"
    assert out[0]["net"] == 70000.0
    assert out[0]["unit_price"] == 140.0
    assert out[0]["volume"] == 500000, "объём закупки не меняется — меняется цена"
    assert out[1]["net"] == 20000.0 and out[1]["unit_price"] == 20000.0, "допы СК не облагаются"


def test_m0035_by_hand():
    out = LY._fold_discounts([_base(500500.0, 350.0, pct=45.8, volume=1430000)])
    assert out[0]["net"] == 271271.0
    assert out[0]["unit_price"] == 189.7


def test_several_placement_rows_sum_exactly_to_base_minus_discount():
    out = LY._fold_discounts([_base(60000.0, 100.0), _base(40000.01, 100.0)])
    # 100 000,01 − скидка 30 % (30 000,00) = 70 000,01 — та же сумма «к закрытию», что давала строка с минусом
    assert round(sum(r["net"] for r in out), 2) == 70000.01
    assert out[0]["net"] == 42000.0


def test_row_sum_has_no_float_tail_it_goes_into_the_document():
    # M-0033: 500 010 − 45,8 % (229 004,58) = 271 005,42; во float разность даёт 271005.42000000004
    out = LY._fold_discounts([_base(500010.0, 280.0, pct=45.8)])
    assert repr(out[0]["net"]) == "271005.42"


def test_without_discount_rows_are_untouched():
    rows = [_base(100000.0, 200.0, pct=0.0)]
    assert LY._fold_discounts(rows) == rows


def test_input_rows_are_not_mutated():
    rows = [_base(100000.0, 200.0)]
    LY._fold_discounts(rows)
    assert rows[0]["net"] == 100000.0 and rows[0]["unit_price"] == 200.0


def test_package_note_names_deals_with_discount_in_bill():
    rows = [_base(100000.0, 200.0), _base(5000.0, 10.0, deal_id=2, code="BBB222", pct=0.0)]
    assert LY.sk_in_invoice(rows) == [{"deal": "AAA111", "pct": 30.0}]


def test_ds_document_row_carries_the_discounted_unit_price_not_the_mp_one():
    from app.master_deal import to_annex as TA
    src = {"position": "Баннер", "unit_price": 200.0, "volume": 500000, "model": "CPM"}
    r = {**_base(70000.0, 140.0, volume=500000), "src": src}
    ds = {"groups": [{"brand": "Бренд", "service": "Услуга", "_src": [r]}]}
    row = TA._snapshot(ds)[0]
    assert row["unit_price"] == 140.0 and row["amount"] == 70000.0


def test_every_kit_request_to_the_accountant_sums_to_the_kit():
    """Инвариант стенда: заявка бухгалтеру (строки УПД) = сумма комплекта ±1 ₽ — иначе «Внести» откажет, как на M-0035."""
    from app.database import SessionLocal
    from app.master_deal.models import MasterDeal, MasterDealUpd
    from app.onec_desk import board as BD
    db = SessionLocal()
    try:
        bad = []
        for k in db.query(MasterDealUpd).all():
            r = BD.request_for(db, db.get(MasterDeal, k.master_deal_id), k)
            if r is not None and abs(BD._expected(r)["gross"] - float(k.gross or 0)) > 1.0:
                bad.append((k.id, BD._expected(r)["gross"], float(k.gross or 0)))
        assert not bad, bad
    finally:
        db.rollback()
        db.close()


def _sk_env(monkeypatch):
    from types import SimpleNamespace
    from app.final_recon import sk as SK
    from app.onec_desk import board as BD
    deals = {1: SimpleNamespace(id=1, code="AAA111"), 2: SimpleNamespace(id=2, code="BBB222")}
    modes = {1: ("скидка в счёт", 45.8), 2: ("постоплата", 10.0)}
    monkeypatch.setattr(SK, "of_deal", lambda db, d: {"mode": modes[d.id][0], "percent": modes[d.id][1]})
    monkeypatch.setattr(BD, "_deal_ids", lambda db_, m: [1, 2])
    return BD, SimpleNamespace(get=lambda model, i: deals[i]), SimpleNamespace(id=35)


def test_request_to_the_accountant_names_deals_with_discount_in_bill(monkeypatch):
    """Плашка «документы со скидкой в счёт» у бухгалтера — только для сведения: суммы заявки уже со скидкой."""
    BD, db, m = _sk_env(monkeypatch)
    lines = [{"deal_id": 1, "kind": "размещение"}, {"deal_id": 2, "kind": "размещение"}]
    assert BD.kit_sk_note(db, m, None, lines) == [{"deal": "AAA111", "pct": 45.8}]


def test_note_is_per_kit_a_kit_of_other_deals_or_addons_only_has_none(monkeypatch):
    BD, db, m = _sk_env(monkeypatch)
    assert BD.kit_sk_note(db, m, None, [{"deal_id": 2, "kind": "размещение"}]) == []
    assert BD.kit_sk_note(db, m, None, [{"deal_id": 1, "kind": "доп"}]) == [], "ДС допов скидкой не облагается"


def test_old_annex_with_minus_row_gets_no_already_discounted_note(monkeypatch):
    """ДС, выпущенный по старому правилу (строка «Скидка СК»): заявка скидку не видит — сказать «уже в цене» было бы враньём."""
    from types import SimpleNamespace
    BD, db, m = _sk_env(monkeypatch)
    old = SimpleNamespace(rows=[{"kind": "base", "deal_id": 1}, {"kind": "discount", "deal_id": 1}])
    assert BD.kit_sk_note(db, m, old, [{"deal_id": 1, "kind": "размещение"}]) == []


def test_fold_spreads_from_mp_amounts_like_the_closing_does():
    """Сверка раскладывает суммы МП сразу на «базу − скидку»; раскладка — тоже от сумм МП (src), а не от уже
    разложенных строк: двойное масштабирование сдвигало копейку между строками и НДС по строкам (ревью 11.11.2026)."""
    from app.final_recon import money as M
    mp = [81227.04, 3722.51, 3264.68]                 # подобрано перебором: здесь двойное масштабирование расходится
    scaled = M.scale_to(mp, 67987.26)
    rows = [{**_base(n, 100.0, pct=7.0), "src": {"amount": a}} for n, a in zip(scaled, mp)]
    out = LY._fold_discounts(rows)
    assert [r["net"] for r in out] == [58220.03, 2668.13, 2339.99]
