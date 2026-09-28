"""Строка очереди аккаунта по стадии — «Что сделать» (макет «акки 3», владелец 28.09.2026).

Три обещания:

1. Проверки в строке — ТЕ ЖЕ функции, что на карточке и в диалоге движения
   (`stage_checks.REGISTRY`). Очередь подкладывает им окружение, загруженное пачкой;
   ответ обязан совпасть с поштучным расчётом до последнего поля.
2. Пачка не растёт с числом сделок: очередь на 600 строк не должна делать 600 запросов.
3. Что показывает строка каждой стадии и куда ведёт её кнопка — чистая функция,
   проверяется без базы.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy import text as text_

import app.main  # noqa: F401 — все модели в реестре SQLAlchemy
from app.database import SessionLocal, engine
from app.sales import queue_state as qs
from app.sales.stage_checks import REGISTRY, Ctx, Result, OK, NOT_YET, UNKNOWN
from app.sales.urgency import Verdict

TODAY = date(2026, 10, 1)


# ─────────────────────── 1–2. пачка против поштучного ───────────────────────

@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _open_deals(db):
    from app.sales.models import SalesDeal, SalesStage
    return (db.query(SalesDeal).join(SalesStage, SalesStage.id == SalesDeal.our_stage_id)
            .filter(SalesStage.is_terminal.is_(False), SalesStage.is_lost.is_(False))
            .order_by(SalesDeal.id).all())


def _same(a: Result, b: Result) -> bool:
    return (a.state, a.detail, tuple(a.blockers)) == (b.state, b.detail, tuple(b.blockers))


def _deals_with_environment(db):
    """Открытые сделки плюс ВСЕ, у кого есть комплекты, РК, приложения или файлы.

    Одних открытых мало: на стенде пары «комплект × площадка» лежат у закрытых сделок,
    и сравнение по открытым ничего бы не сравнило — подмена пар пустым списком прошла
    бы незамеченной (так и вышло при проверке теста нарочной поломкой)."""
    from app.sales.models import SalesDeal
    extra = {i for (i,) in db.execute(text_("""
        SELECT deal_id FROM launch_prep_creative_set
        UNION SELECT deal_id FROM ad_campaign
        UNION SELECT deal_id FROM sales_deal_annex_allocation
        UNION SELECT deal_id FROM sales_deal_files""")).all()}
    open_ = _open_deals(db)
    more = (db.query(SalesDeal).filter(SalesDeal.id.in_(extra - {d.id for d in open_}))
            .order_by(SalesDeal.id).all()) if extra else []
    return open_ + more


def test_batch_checks_equal_per_deal(db):
    deals = _deals_with_environment(db)
    if not deals:
        pytest.skip("на стенде нет сделок")
    ctxs = qs.load(db, deals, TODAY).ctxs
    diff = []
    for d in deals:
        for key in qs.CHECK_KEYS:
            got, want = REGISTRY[key].fn(ctxs[d.id]), REGISTRY[key].fn(Ctx(db, d))
            if not _same(got, want):
                diff.append((d.code, key, got, want))
    assert not diff, f"пачка разошлась с карточкой: {diff[:5]}"


def test_batch_annex_equal_per_deal(db):
    """Приложений на стенде нет — заводим своё в транзакции, которая откатывается."""
    from app.models import Contract
    from app.sales.models import SalesAnnex, SalesDealAnnexAllocation
    deals = _open_deals(db)
    contract = db.query(Contract).order_by(Contract.id).first()
    if not deals or not contract:
        pytest.skip("нет сделки или договора")
    d = deals[0]
    a = SalesAnnex(contract_id=contract.id, no=7, number="Приложение № 7", total_amount=100)
    b = SalesAnnex(contract_id=contract.id, no=8, total_amount=200)   # номер не напечатан
    db.add_all([a, b])
    db.flush()
    db.add_all([SalesDealAnnexAllocation(deal_id=d.id, annex_id=a.id, amount=100),
                SalesDealAnnexAllocation(deal_id=d.id, annex_id=b.id, amount=200)])
    db.flush()
    batch = qs.load(db, [d], TODAY)
    for key in ("annex_generated", "signatory_filled"):
        assert _same(REGISTRY[key].fn(batch.ctxs[d.id]), REGISTRY[key].fn(Ctx(db, d))), key
    # Номер — последнего приложения (без печатного номера — по порядковому), сумма — по всем.
    assert batch.annex[d.id] == ("№ 8", 300)


def _count_queries(db, fn):
    n = [0]

    def hook(*_a, **_k):
        n[0] += 1
    event.listen(engine, "before_cursor_execute", hook)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", hook)
    return n[0]


def test_query_count_does_not_grow_with_deals(db):
    deals = _open_deals(db)
    if len(deals) < 20:
        pytest.skip("мало сделок для замера")
    # Половина против всех, а не три против всех: у трёх сделок может не быть комплектов
    # или РК, и тогда часть запросов пропускается — разница была бы не ростом, а пропуском.
    verdicts = {d.id: Verdict("normal") for d in deals}
    half = deals[: len(deals) // 2]
    few = _count_queries(db, lambda: qs.build(db, half, verdicts, TODAY))
    many = _count_queries(db, lambda: qs.build(db, deals, verdicts, TODAY))
    assert many <= few + 2, f"запросов на {len(half)} сделок {few}, на {len(deals)} — {many}"
    assert many <= 30, f"{many} запросов на очередь — где-то запрос на строку"


# ─────────────────────────── 3. строка по стадии ───────────────────────────

def bundle(slot, **kw) -> "qs.Bundle":
    base = dict(slot=slot, code="K7Q2MD", stage_days=4, start_in=10, end_in=40,
                verdict=Verdict("soon"), has_mp=True, amount=1_250_000, gross=1_525_000,
                checks={}, required=set())
    base.update(kw)
    return qs.Bundle(**base)


def chips(st):
    return [(e["type"], e.get("v") or e.get("k")) for e in st["state"]]


def test_mp_prep_without_plan_collects_plan():
    st = qs.row_state(bundle("mp_prep", has_mp=False, verdict=Verdict("overdue"), start_in=4))
    assert st["action"]["do"] == "mp" and st["action"]["label"] == "Собрать МП"
    assert {"type": "alert", "tone": "bad", "v": "МП нет"} in st["state"]
    assert {"type": "fact", "k": "старт", "v": "через 4 дн."} in st["state"]


def test_start_without_dates_is_a_warning():
    st = qs.row_state(bundle("mp_prep", has_mp=False, start_in=None, end_in=None))
    assert {"type": "alert", "tone": "warn", "v": "даты не заданы"} in st["state"]


def test_mp_sent_shows_days_at_client_and_sum():
    st = qs.row_state(bundle("mp_sent", stage_days=6))
    assert {"type": "fact", "k": "у клиента", "v": "6 дн."} in st["state"]
    assert {"type": "fact", "k": "МП", "v": "1 250 000 ₽"} in st["state"]
    assert st["action"] == {"label": "Бронь", "do": "move",
                            "hint": "Клиент согласовал медиаплан — перевести в «Бронь»"}


def _checks(**states):
    return {k: Result(v, "") for k, v in states.items()}


def test_booking_first_missing_requirement_is_the_button():
    st = qs.row_state(bundle("booking", checks=_checks(
        payer_set=OK, final_contract=NOT_YET, realization_pipeline=NOT_YET),
        required={"payer_set", "final_contract", "realization_pipeline"}))
    assert st["action"]["label"] == "Договор ОРД"
    assert st["action"]["do"] == "link" and st["action"]["url"] == "/sales/deals/K7Q2MD#ord"
    got = [(e["v"], e["ok"]) for e in st["state"] if e["type"] == "check"]
    assert got == [("Плательщик", True), ("Договор ОРД", False), ("Воронка", False)]


def test_booking_all_done_confirms():
    st = qs.row_state(bundle("booking", checks=_checks(
        payer_set=OK, final_contract=OK, realization_pipeline=OK),
        required={"payer_set", "final_contract", "realization_pipeline"}))
    assert st["action"]["label"] == "Подтвердить" and st["action"]["do"] == "confirm"


def test_not_required_check_is_grey_and_not_the_button():
    st = qs.row_state(bundle("booking", checks=_checks(
        payer_set=OK, final_contract=NOT_YET, realization_pipeline=OK),
        required={"payer_set", "realization_pipeline"}))
    ord_chip = next(e for e in st["state"] if e.get("v") == "Договор ОРД")
    assert ord_chip["optional"] is True
    assert st["action"]["do"] == "confirm", "необязательное не должно запирать кнопку"


def test_unknown_check_is_not_drawn():
    """«Проверить нечем» — не ✗: иначе ЭДО без интеграции горело бы у каждой сделки."""
    st = qs.row_state(bundle("booking", checks={"payer_set": Result(UNKNOWN, "нет связи")},
                             required={"payer_set"}))
    assert not [e for e in st["state"] if e["type"] == "check"]


def test_prep_creatives_progress_and_erid_waiting():
    st = qs.row_state(bundle("prep", creatives=(2, 5), sets=1, erids=[], kktu=True,
                             erid_share=20,
                             checks=_checks(campaign_ready=NOT_YET),
                             required={"campaign_ready"}))
    assert {"type": "progress", "k": "креативы", "x": 2, "y": 5} in st["state"]
    assert {"type": "fact", "k": "ЕРИД", "v": "ждёт 20 %"} in st["state"]
    assert {"type": "check", "v": "РК в DSP", "ok": False, "optional": False} in st["state"]
    assert st["action"]["label"] == "Креативы" and st["action"]["do"] == "prep"


def test_prep_no_kktu_asks_for_it():
    st = qs.row_state(bundle("prep", creatives=(4, 4), sets=1, erids=[], kktu=False,
                             erid_share=20, checks=_checks(campaign_ready=OK),
                             required={"campaign_ready"}))
    assert {"type": "alert", "tone": "warn", "v": "ЕРИД: нет ККТУ"} in st["state"]
    assert st["action"]["label"] == "ККТУ"
    assert st["action"]["url"] == "/directory/advertisers"


def test_prep_all_ready_goes_live():
    st = qs.row_state(bundle("prep", creatives=(6, 6), sets=1, erids=["2SDnQHT6RU"], kktu=True,
                             erid_share=20, checks=_checks(campaign_ready=OK),
                             required={"campaign_ready"}))
    assert {"type": "fact", "k": "ЕРИД", "v": "2SDnQHT6RU"} in st["state"]
    assert st["action"]["label"] == "В размещение" and st["action"]["do"] == "move"


def test_live_lag_has_no_button():
    st = qs.row_state(bundle("live", verdict=Verdict("overdue", "Отставание", "", "delivery_lag"),
                             delivery={"done_pct": 31.0, "closed_pace": 0.4, "fact_shows": 100,
                                       "placements": 5, "placements_on": 4}))
    assert st["action"] is None and st["note"] == "ведёт трафик"
    assert {"type": "progress", "k": "открутка", "x": 31, "y": 100, "unit": "%"} in st["state"]
    assert {"type": "alert", "tone": "bad", "v": "отставание 22,5 %"} in st["state"]
    assert {"type": "fact", "k": "площадок", "v": "4 / 5"} in st["state"]


def test_live_flight_over_is_not_lag_chip():
    """Последний день флайта: срочность молчит — и чип обязан молчать (ревью 28.09.2026)."""
    st = qs.row_state(bundle("live", verdict=Verdict("normal"),
                             delivery={"done_pct": 80.0, "closed_pace": 1.0, "flight_over": True,
                                       "fact_shows": 800, "placements": 2, "placements_on": 2}))
    assert not [e for e in st["state"] if e["type"] == "alert"]


def test_live_without_statistics_says_so():
    st = qs.row_state(bundle("live", delivery={"done_pct": None, "fact_shows": None,
                                               "placements": 3, "placements_on": 0}))
    assert {"type": "fact", "k": "открутка", "v": "статистики нет"} in st["state"]


def test_recon_estimate_to_close_is_at_plan_price():
    st = qs.row_state(bundle("recon", checks=_checks(fact_collected=OK),
                             delivery={"done_pct": 93.0, "fact_shows": 930, "plan_show": 1000,
                                       "plan_budget": 1_000_000}))
    assert {"type": "check", "v": "Факт собран", "ok": True, "optional": True} in st["state"]
    assert {"type": "fact", "k": "расхождение", "v": "−7 %"} in st["state"]
    assert {"type": "fact", "k": "к закрытию ≈", "v": "930 000 ₽"} in st["state"]
    assert st["action"]["label"] == "В ДО"


def test_closing_report_is_always_optional_and_docs_open_the_row():
    st = qs.row_state(bundle("closing", checks=_checks(
        invoice_issued=OK, upd_issued=NOT_YET, report_attached=NOT_YET),
        required={"invoice_issued", "upd_issued", "report_attached"}))
    rep = next(e for e in st["state"] if e.get("v") == "Отчёт")
    assert rep["optional"] is True
    assert st["action"] == {"label": "Документы", "do": "expand",
                            "hint": "Приложите документы в раскрытой строке"}


def test_pay_overdue_leads_to_receivables_and_floats_up():
    st = qs.row_state(bundle("pay", pay_due=TODAY - timedelta(days=12), today=TODAY,
                             verdict=Verdict("normal")))
    assert {"type": "alert", "tone": "warn", "v": "срок прошёл 12 дн."} in st["state"]
    assert st["action"]["label"] == "Дебиторка"
    assert st["tail"] is False, "просроченная оплата всплывает в рабочую часть"


def test_pay_in_time_is_tail_and_calm_is_not_tail():
    st = qs.row_state(bundle("pay", pay_due=TODAY + timedelta(days=20), today=TODAY,
                             verdict=Verdict("normal")))
    assert st["tail"] is True and st["calm"] is False and st["action"] is None
    st2 = qs.row_state(bundle("mp_sent", verdict=Verdict("normal")))
    assert st2["calm"] is True and st2["tail"] is False


def test_unmapped_stage_is_sorted_out():
    st = qs.row_state(bundle("unmapped", verdict=Verdict("today")))
    assert st["action"]["label"] == "Разобрать" and st["action"]["do"] == "move"
    assert st["state"][0]["tone"] == "bad"


def test_unknown_slot_falls_back_to_reason():
    st = qs.row_state(bundle(None, verdict=Verdict("soon", "На стадии 9 дн. (норма 5)", "Двинуть",
                                                   "stage_stuck")))
    assert st["state"] == [{"type": "fact", "k": "", "v": "На стадии 9 дн. (норма 5)"}]
    assert st["action"]["do"] == "move"
