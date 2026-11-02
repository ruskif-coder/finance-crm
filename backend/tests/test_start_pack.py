# -*- coding: utf-8 -*-
"""ДС на старте через конструктор закрытия (владелец 02.11.2026).

«Создать» в карточке сделки вело в черновик старого конструктора: ДС на одну сделку, на ПОСЛЕДНИЙ договор плательщика, без
раскладки. Теперь кнопка заводит мастер-сделку `issued_at_start`: одна сделка, без объединения, раскладка по МП, конструктор
без сверки, ДС — первичный; «Подтвердить ДС» → «ждём закрытия»; на итоговой сверке «Отправить в ДО» возвращает этот же пакет
в черновик, и он закрывается по факту: ДС не ушёл клиенту — пересобирается с тем же номером; ушёл и не подписан — закрытие
стоит; подписан — комплекты УПД по факту к нему.

Поломки, которые ловит набор: старт на последний договор плательщика вместо доходного; старт до «Сборки» или после
итоговой сверки; чужая сделка присоединяется к стартовому пакету; раскладка старта ждёт факта/сверки; ДС старта «по факту»;
стартовый пакет считается закрытым; пересобирается ДС, уже выставленный клиенту; «Вернуть в раскладку» на старте отказывает.
Транзакция откатывается; уведомления подменены."""
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.annex_tpl import document as tpl_doc
from app.final_recon import closing as CL
from app.master_deal import doc_sign as DSG
from app.master_deal import layout as LY
from app.master_deal import package as PK
from app.master_deal import service as MS
from app.master_deal import start as SP
from app.master_deal import status as ST
from app.master_deal import to_annex as TA


@pytest.fixture
def env(monkeypatch):
    import app.notify.bus as bus
    from app.routers import annexes as AX
    monkeypatch.setattr(bus, "emit", lambda *a, **k: None)
    real = AX.tpl_assemble

    def complete(*a, **k):                  # полнота реквизитов договора стенда здесь не проверяется — её держат свои тесты
        return {**real(*a, **k), "missing": []}
    monkeypatch.setattr(AX, "tpl_assemble", complete)
    from app.database import SessionLocal
    from app.models import Contract, User
    from app.sales.models import SalesDeal
    db = SessionLocal()
    ids = [i for (i,) in db.execute(text("""
        SELECT d.id FROM sales_deals d
          JOIN sales_media_plans mp ON mp.deal_id = d.id AND mp.status <> 'rejected'
          JOIN sales_media_plan_rows r ON r.plan_id = mp.id AND r.unit_price > 0 AND r.volume > 0
         WHERE d.period_from IS NOT NULL AND NOT EXISTS (SELECT 1 FROM master_deal_items i WHERE i.deal_id = d.id)
           AND NOT EXISTS (SELECT 1 FROM ad_campaign c WHERE c.deal_id = d.id)
         GROUP BY d.id ORDER BY d.id DESC LIMIT 2""")).fetchall()]
    if len(ids) < 2:
        pytest.skip("на стенде нет двух сделок с медиапланом вне пакетов")
    contract = next((c for c in db.query(Contract).order_by(Contract.id) if tpl_doc.resolve(db, c)[0] is not None), None)
    if contract is None:
        pytest.skip("на стенде нет договора с шаблоном ДС")
    assembly = db.execute(text("SELECT id FROM sales_stages WHERE stage_key = 'launch_prep' ORDER BY id LIMIT 1")).scalar()
    deals = [db.get(SalesDeal, i) for i in ids]
    for d in deals:
        d.our_stage_id, d.ord_final_contract_id = assembly, contract.id
        d.period_from = deals[0].period_from
    db.flush()
    admin = db.query(User).filter(User.is_active == 1).filter(User.role.has(key="admin")).first()
    try:
        yield db, deals, admin, contract
    finally:
        db.rollback()
        db.close()


def _stage(db, name):
    return db.execute(text("SELECT id FROM sales_stages WHERE name = :n"), {"n": name}).scalar()


def _start_with_ds(db, d, u):
    m = SP.start(db, d, u)
    PK.set_start_no(db, m, max((x["no"] for x in PK.issued(db, m.contract_id)), default=0), u)
    made = TA.create(db, m, u)
    return m, made


def _confirm(db, m, u):
    from app.routers import annexes as AX
    from app.sales.models import SalesAnnex
    for a in db.query(SalesAnnex).filter(SalesAnnex.master_deal_id == m.id, SalesAnnex.no.is_(None)).order_by(SalesAnnex.sub_no.isnot(None)):
        AX.confirm_one(db, a, AX.ConfirmIn(), u)
        db.flush()
    TA.after_confirm(db, m)
    db.flush()


def test_start_takes_income_contract_one_deal_and_is_idempotent(env):
    db, deals, u, c = env
    m = SP.start(db, deals[0], u)
    assert m.issued_at_start and m.contract_id == c.id and m.status == ST.DRAFT
    assert [d.id for d in TA._deals(db, m)] == [deals[0].id]
    assert SP.start(db, deals[0], u).id == m.id, "повторное «Создать» ведёт в тот же пакет"


@pytest.mark.parametrize("stage,word", [("МП Отправлено", "Сборк"), ("Итоговая сверка", "Отправить в ДО")])
def test_start_only_from_assembly_until_final_recon(env, stage, word):
    db, deals, u, _ = env
    deals[0].our_stage_id = _stage(db, stage)
    db.flush()
    with pytest.raises(MS.MasterError) as e:
        SP.start(db, deals[0], u)
    assert word in e.value.message


def test_start_needs_income_contract(env):
    db, deals, u, _ = env
    deals[0].ord_final_contract_id = None
    db.flush()
    with pytest.raises(MS.MasterError) as e:
        SP.start(db, deals[0], u)
    assert "доходный договор" in e.value.message


def test_nobody_joins_a_start_pack(env):
    db, deals, u, _ = env
    m = SP.start(db, deals[0], u)
    assert m.id not in {x["id"] for x in MS.candidates(db, deals[1])}
    with pytest.raises(MS.MasterError):
        PK.add_deal(db, m, deals[1], u)
    with pytest.raises(MS.MasterError):
        MS.attach(db, deals[1], m, u)


def test_start_layout_is_by_media_plan_without_recon(env):
    db, deals, u, _ = env
    m = SP.start(db, deals[0], u)
    st = CL.compute(db, deals[0])
    assert st["confirmed"] is False, "сверки нет — старт её не ждёт"
    lay = LY.layout(db, m)
    plan = st["amounts"]["plan"] + st["paid_extras_net"]
    assert lay["total_net"] == pytest.approx(plan, abs=0.05), "раскладка старта — по МП"
    assert TA.ready(db, m) == ["не задан номер ДС"]


def test_start_ds_is_primary_and_pack_waits_for_closing(env):
    db, deals, u, _ = env
    from app.sales.models import SalesAnnex
    m, made = _start_with_ds(db, deals[0], u)
    assert m.status == ST.AGREE and made
    for x in made:
        assert db.get(SalesAnnex, x["id"]).issue_kind == "primary"
    from app.master_deal.models import MasterDealUpd
    assert not db.query(MasterDealUpd).filter_by(master_deal_id=m.id).count(), "на старте УПД нет — они по факту, на закрытии"
    _confirm(db, m, u)
    assert m.status == ST.WAIT_CLOSE
    for x in made:
        assert db.get(SalesAnnex, x["id"]).sign_state == "выпущен"


def test_revert_at_start_removes_the_draft(env):
    db, deals, u, _ = env
    from app.sales.models import SalesAnnex
    m, made = _start_with_ds(db, deals[0], u)
    assert TA.revert(db, m) == len(made)
    assert m.status == ST.DRAFT and not db.query(SalesAnnex).filter_by(master_deal_id=m.id).count()


def _to_closing(db, d, u):
    d.our_stage_id = _stage(db, "Итоговая сверка")
    db.flush()
    CL.set_mode(db, d, "plan", None, None, privileged=True)
    CL.confirm(db, d, True, None)
    return MS.send(db, d, u, target="new")


def test_send_to_do_returns_the_same_pack_to_draft(env):
    db, deals, u, _ = env
    m, _made = _start_with_ds(db, deals[0], u)
    _confirm(db, m, u)
    out = _to_closing(db, deals[0], u)
    assert out["master"]["id"] == m.id and m.status == ST.DRAFT
    assert not SP.in_start_phase(db, m)


def test_closing_rebuilds_primary_not_yet_at_client_with_the_same_number(env):
    db, deals, u, _ = env
    from app.sales.models import SalesAnnex
    m, made = _start_with_ds(db, deals[0], u)
    _confirm(db, m, u)
    main = db.get(SalesAnnex, made[0]["id"])
    no = main.no
    DSG.mark(db, main, "согласован", u)
    _to_closing(db, deals[0], u)
    again = TA.create(db, m, u)
    assert again[0]["id"] == main.id and main.no == no
    assert main.sign_state == "выпущен", "пересобранный текст — новый круг согласования"


def test_closing_stops_when_primary_is_at_client_unsigned(env):
    db, deals, u, _ = env
    from app.sales.models import SalesAnnex
    m, made = _start_with_ds(db, deals[0], u)
    _confirm(db, m, u)
    main = db.get(SalesAnnex, made[0]["id"])
    main.sign_state, main.sign_channel = "выставлен", "ЭДО"
    _to_closing(db, deals[0], u)
    with pytest.raises(MS.MasterError) as e:
        TA.create(db, m, u)
    assert "у клиента" in e.value.message


def test_closing_on_signed_primary_attaches_upds(env):
    db, deals, u, _ = env
    from app.master_deal.models import MasterDealUpd
    from app.sales.models import SalesAnnex
    m, made = _start_with_ds(db, deals[0], u)
    _confirm(db, m, u)
    main = db.get(SalesAnnex, made[0]["id"])
    main.sign_state, main.sign_channel = "подписан", "ЭДО"
    _to_closing(db, deals[0], u)
    out = TA.create(db, m, u)
    assert out[0]["kind"] == "primary_signed"
    assert db.query(MasterDealUpd).filter_by(master_deal_id=m.id, annex_id=main.id).count() >= 1


def test_confirming_the_ds_on_its_own_page_moves_the_pack_too(env):
    """«Подтвердить номер» на странице ДС, а не «Подтвердить ДС пакета» в карточке: пакет всё равно уходит дальше, когда
    подтверждены все его ДС. До 02.11.2026 он оставался в «согласовании» навсегда — дальше вела только кнопка пакета."""
    db, deals, u, _ = env
    from app.routers import annexes as AX
    from app.sales.models import SalesAnnex
    m, made = _start_with_ds(db, deals[0], u)
    a = db.get(SalesAnnex, made[0]["id"])
    AX.confirm_one(db, a, AX.ConfirmIn(), u)
    db.flush()
    assert TA.after_confirm(db, m) is True and m.status == ST.WAIT_CLOSE
    assert TA.after_confirm(db, m) is False, "второй раз — ничего"


def test_closing_on_signed_primary_moves_the_pack_to_wait_1c(env):
    """Подписанный первичный ДС на закрытии не пересобирается — подтверждать нечего, и «Подтвердить ДС пакета» отвечает
    «неподтверждённых нет». Поломка: пакет остаётся в «согласовании» навсегда (системный статус руками не сдвинуть)."""
    db, deals, u, _ = env
    from app.sales.models import SalesAnnex
    m, made = _start_with_ds(db, deals[0], u)
    _confirm(db, m, u)
    main = db.get(SalesAnnex, made[0]["id"])
    main.sign_state, main.sign_channel = "подписан", "ЭДО"
    _to_closing(db, deals[0], u)
    TA.create(db, m, u)
    assert m.status == ST.WAIT_1C


def test_start_is_one_ds_even_when_addons_go_separately(env, monkeypatch):
    """Владелец 02.11.2026: на старте одна сделка — один ДС. Настройка «допы отдельным ДС» на старте дала бы два первичных,
    и закрытие упало бы на «разные первичные ДС». Поломка: на старте раскладка делит ДС."""
    db, deals, u, _ = env
    m = SP.start(db, deals[0], u)
    common = {"deal_id": deals[0].id, "deal": deals[0].code, "brand": "Б", "service": "С", "sk_pct": 0.0}
    monkeypatch.setattr(LY, "lines", lambda db_, m_: [{**common, "id": "b:1:0", "kind": "base", "net": 100.0},
                                                      {**common, "id": "e:1:0", "kind": "extra", "net": 50.0}])
    assert len(LY.layout(db, m, {"addons_separate": True})["ds"]) == 1
