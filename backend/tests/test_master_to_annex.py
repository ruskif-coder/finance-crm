# -*- coding: utf-8 -*-
"""Раскладка мастер-сделки → черновики ДС (app/master_deal/to_annex.py, владелец 15.10.2026): ДС создаются по раскладке, строки —
снимком (сумма документа = сумме ДС раскладки), распределение по сделкам из строк, комплекты УПД записаны, номер «ДС № N» и
«ДС № N-01», «Вернуть в раскладку» снимает черновики. Транзакция откатывается; уведомления подменены."""
import pytest

import app.model_registry  # noqa: F401
from app.annex_tpl import document as tpl_doc
from app.final_recon import closing as CL
from app.master_deal import layout as LY
from app.master_deal import package as PK
from app.master_deal import service as MS
from app.master_deal import to_annex as TA
from app.master_deal.models import MasterDeal, MasterDealUpd
from tests import test_closing_scenarios as _cs
from tests.test_closing_scenarios import _ready

# Фикстура из сценариев сверки: присваиванием, а не импортом — иначе ruff считает параметр
# `env` у тестов переопределением неиспользованного импорта (F811).
env = _cs.env


def _with_template(db, deals):
    """Договор с шаблоном ДС — без него конструктор не соберёт документ и проверка ничего не докажет."""
    from app.models import Contract
    for c in db.query(Contract).order_by(Contract.id):
        if tpl_doc.resolve(db, c)[0] is not None:
            for d in deals:
                d.ord_final_contract_id = c.id
            db.flush()
            return c
    pytest.skip("на стенде нет договора с шаблоном ДС")


def _package(db, deals, u, settings):
    _with_template(db, deals)
    for d in deals:
        _ready(db, d)
    m = db.get(MasterDeal, MS.send_with(db, deals[0], deals[1:], u, target="new")["master"]["id"])
    PK.save_settings(db, m, settings, u)
    last = max((x["no"] for x in PK.issued(db, m.contract_id)), default=0)
    PK.set_start_no(db, m, last, u)
    return m


@pytest.mark.parametrize("settings", [
    {"addons_separate": True, "bonus_addons": "zero", "ds_by_brand": True, "ds_by_service": True},
    {"addons_separate": False, "bonus_addons": "hide", "ds_by_brand": False, "ds_by_service": False, "upd_by_brand": False},
])
def test_to_annex_creates_ds_matching_layout(env, settings):
    db, deals, u = env
    from app.models import Contract
    from app.sales.models import SalesAnnex, SalesDealAnnexAllocation
    m = _package(db, deals, u, settings)
    c = db.get(Contract, m.contract_id)
    lay = LY.layout(db, m)
    made = TA.create(db, m, u)
    assert m.status == "согласование" and len(made) == len(lay["ds"])
    base = m.start_no + 1
    for ds, x in zip(lay["ds"], made):
        a = db.get(SalesAnnex, x["id"])
        assert a.master_deal_id == m.id and a.kind == ds["kind"] and a.rows
        # Мастер-сделка по умолчанию — доп. соглашение (решение 15.10.2026), и с 31.10.2026 номер
        # печатается полной формой: он стоит в документе, а «ДС» — только на экранах.
        assert x["number"] == (f"Доп. соглашение № {base}-01" if ds["kind"] == "addons" else f"Доп. соглашение № {base}")
        deal_ids = [al.deal_id for al in db.query(SalesDealAnnexAllocation).filter_by(annex_id=a.id)]
        model = tpl_doc.live(db, c, tpl_doc.resolve(db, c)[0], a, deal_ids)
        assert model["number"] == x["number"], "номер в документе — из раскладки"
        assert model["table"]["totals"]["net"] == pytest.approx(ds["net"], abs=0.02), "сумма документа = сумме ДС раскладки"
        assert model["consistency"]["ok"], model["consistency"]["details"]
        assert float(a.total_amount) == pytest.approx(model["amount"], abs=0.01)
        alloc = sum(al.amount for al in db.query(SalesDealAnnexAllocation).filter_by(annex_id=a.id))
        assert alloc == pytest.approx(model["amount"], abs=0.05), "распределение по сделкам = сумме ДС"
    upds = db.query(MasterDealUpd).filter_by(master_deal_id=m.id).order_by(MasterDealUpd.upd_no).all()
    assert [k.upd_no for k in upds] == list(range(1, lay["upd_count"] + 1))
    with pytest.raises(MS.MasterError):                         # повторно — нельзя, пакет уже не на сборке
        TA.create(db, m, u)
    assert TA.revert(db, m) == len(made)                        # вернуть в раскладку
    assert m.status == "черновик" and not db.query(MasterDealUpd).filter_by(master_deal_id=m.id).count()
    assert not db.query(SalesAnnex).filter_by(master_deal_id=m.id).count()


def test_to_annex_refusals(env):
    db, deals, u = env
    _ready(db, deals[0])
    m = db.get(MasterDeal, MS.send(db, deals[0], u, target="new")["master"]["id"])
    with pytest.raises(MS.MasterError) as e:                    # номер не задан
        TA.create(db, m, u)
    assert "номер" in e.value.message
    PK.add_deal(db, m, deals[1], u)                             # несверенная сделка держит пакет
    PK.set_start_no(db, m, max((x["no"] for x in PK.issued(db, m.contract_id)), default=0), u)
    assert CL.compute(db, deals[1])["frozen"] is False
    with pytest.raises(MS.MasterError) as e:
        TA.create(db, m, u)
    assert "сверка" in e.value.message


def test_master_ds_file_prints_snapshot_groups_ds_words_and_upd_basis(env):
    """Выгрузка ДС пакета (DOCX): строки — снимок раскладки, заголовки групп, «Доп. соглашение № N», слово документа —
    «Доп. соглашение» вместо «Приложения» во всех падежах, основания по УПД. До 31.10.2026 здесь было сокращение «ДС»
    в тексте; владелец: «в тексте — Доп. соглашение»."""
    import io
    from docx import Document
    from app.models import Contract
    from app.routers.annexes import _doc
    from app.sales.annex_docx import build_docx
    from app.sales.models import SalesAnnex
    db, deals, u = env
    m = _package(db, deals, u, {"addons_separate": False, "ds_by_brand": True, "ds_by_service": True})
    made = TA.create(db, m, u)
    a = db.get(SalesAnnex, made[0]["id"])
    d = _doc(db, a)
    assert d["is_master"] and d["number"] == made[0]["number"]
    assert any(r.get("group_title") for r in d["rows"]), "заголовки групп в таблице"
    assert "УПД № 1" in d["closing_basis"]
    net = sum(float(r.get("amount") or 0) for r in d["rows"] if not r.get("group_title"))
    assert net == pytest.approx(LY.layout(db, m)["ds"][0]["net"], abs=0.02), "строки файла — снимок раскладки"
    text = "\n".join(p.text for p in Document(io.BytesIO(build_docx(d, with_basis=True))).paragraphs)
    assert made[0]["number"] in text and "настоящему Доп. соглашению" in text
    # Сокращения «ДС» в ТЕКСТЕ документа больше нет — только в интерфейсе. Прибор на возврат к таблице замен.
    for abbr in ("настоящему ДС", "настоящим ДС", "Настоящее ДС", "отдельными ДС", "ДС составлено"):
        assert abbr not in text, abbr
    # Постоянный текст генератора (п. 1.1, 1.2, 3) — «ДС»; пункт 1 — текст шаблона договора, его правит юрист.
    for old in ("настоящему Приложению", "настоящим Приложением", "Настоящее Приложение", "отдельными Приложениями"):
        assert old not in text, old
    assert db.get(Contract, m.contract_id)


def _primary(db, m, deals, u, confirmed_no=None):
    """Первичный ДС «на старте»: на сделки пакета, на план (сумма с запасом), черновик или с номером."""
    from datetime import date
    from app.sales.models import SalesAnnex, SalesDealAnnexAllocation
    total = sum(CL.compute(db, d)["base_plan_net"] for d in deals) * 1.22 * 1.5
    a = SalesAnnex(contract_id=m.contract_id, period_from=date(2026, 10, 1), period_to=date(2026, 10, 31), date=date(2026, 10, 1),
                   total_amount=round(total, 2), status="черновик" if confirmed_no is None else "подтверждён", issue_kind="primary",
                   no=confirmed_no, number=(f"Приложение № {confirmed_no}" if confirmed_no else None),
                   template_version_id=tpl_doc.resolve(db, db.get(__import__("app.models", fromlist=["Contract"]).Contract, m.contract_id))[0].id)
    db.add(a)
    db.flush()
    for d in deals:
        db.add(SalesDealAnnexAllocation(deal_id=d.id, annex_id=a.id, amount=1))
    db.flush()
    return a


def test_unsigned_primary_is_rebuilt_by_fact_keeping_its_number(env):
    """Владелец 16.10: первичный ДС не подписан — важен только номер; этот же ДС пересобирается по факту."""
    from app.sales.models import SalesAnnex
    db, deals, u = env
    m = _package(db, deals, u, {"addons_separate": False})
    m.start_no = None
    p = _primary(db, m, deals, u)
    assert TA.ready(db, m) == [], "с первичным ДС номер раскладки не нужен"
    made = TA.create(db, m, u)
    assert [x["id"] for x in made] == [p.id], "новый ДС не создаётся — пересобран первичный"
    a = db.get(SalesAnnex, p.id)
    assert a.issue_kind == "primary" and a.rows and a.master_deal_id == m.id, "происхождение видно, строки — по факту"
    with pytest.raises(MS.MasterError):                     # пересобранный первичный в раскладку не возвращается
        TA.revert(db, m)


def test_signed_primary_stays_and_upds_close_by_fact(env):
    """Подписан — ДС не трогаем, УПД по факту к нему, расхождение видно; закрыть больше ДС нельзя."""
    from app.master_deal import primary as PR
    from app.master_deal.models import MasterDealUpd
    from app.sales import annex_signed
    db, deals, u = env
    m = _package(db, deals, u, {"addons_separate": False})
    p = _primary(db, m, deals, u, confirmed_no=None)
    total_before = float(p.total_amount)
    orig = annex_signed._from_file
    annex_signed._from_file = lambda db, a: {"signed": True, "at": None}
    try:
        info = PR.info(db, m, LY.layout(db, m)["total_gross"])
        assert info["branch"] == "signed" and info["diff"] < 0
        made = TA.create(db, m, u)
        assert made[0]["kind"] == "primary_signed" and made[0]["id"] == p.id
        assert float(p.total_amount) == total_before and p.rows is None and p.issue_kind == "primary", "подписанный ДС не тронут"
        assert db.query(MasterDealUpd).filter_by(master_deal_id=m.id, annex_id=p.id).count() >= 1
        assert TA.revert(db, m) == 1 and p.master_deal_id is None, "вернуть — только отвязать, ДС остаётся"
        p.total_amount = 1.0                                 # подписан на сумму меньше закрытия
        with pytest.raises(MS.MasterError):
            TA.create(db, m, u)
    finally:
        annex_signed._from_file = orig


def _fill_signer(db, cp, fio, position):
    """Дозаполнить подписанта заказчика по умолчанию (с 28.10.2026 — `counterparty_signers`) в транзакции теста: иначе документ неполон."""
    from app.signers import service as SG
    d = SG.default_of(db, cp.id)
    SG.upsert_default(db, cp, {"director_name": (d and d.director_name) or fio, "signer_position": (d and d.signer_position) or position,
                               "signer_basis": (d and d.signer_basis) or "Устава"}, None)


def test_confirmed_unsigned_primary_keeps_number_and_is_refrozen_by_fact(env):
    from app.sales.models import SalesAnnex
    db, deals, u = env
    m = _package(db, deals, u, {"addons_separate": False})
    free = (db.execute(__import__("sqlalchemy").text("SELECT coalesce(max(no), 0) + 50 FROM sales_annexes WHERE contract_id = :c"),
                       {"c": m.contract_id}).scalar())
    from app.models import Contract
    cp = db.get(Contract, m.contract_id).counterparty    # подписант заказчика — иначе документ неполон и пересборка честно откажет
    cp.inn = cp.inn or "7700000000"
    _fill_signer(db, cp, "Иванов Иван Иванович", "Генеральный директор")
    db.flush()
    p = _primary(db, m, deals, u, confirmed_no=free)
    TA.create(db, m, u)
    a = db.get(SalesAnnex, p.id)
    assert a.no == free, "номер первичного ДС сохраняется"
    assert isinstance(a.blocks, dict) and "blocks" in a.blocks, "подтверждённый — перезаморожен"
    lay_net = LY.layout(db, m)["ds"][0]["net"]
    assert a.blocks["table"]["totals"]["net"] == pytest.approx(lay_net, abs=0.02), "замороженный документ — по факту из раскладки"


def test_confirm_all_ds_of_package_in_one_action(env, monkeypatch):
    """Основной ДС и ДС допов подтверждаются одним действием: номера «ДС № N» и «ДС № N-01», ничего не коммитится (подмена)."""
    from app.routers import master_deals as R
    from app.sales.models import SalesAnnex
    db, deals, u = env
    monkeypatch.setattr(db, "commit", db.flush)
    import app.routers.annexes as AX
    monkeypatch.setattr(AX, "log_action", lambda *a, **k: None)
    monkeypatch.setattr(R, "log_action", lambda *a, **k: None)
    monkeypatch.setattr(db, "rollback", lambda: None)
    from app.models import Contract
    m = _package(db, deals, u, {"addons_separate": True})
    cp = db.get(Contract, m.contract_id).counterparty
    cp.inn = cp.inn or "7700000000"
    _fill_signer(db, cp, "Иванов И.И.", "Директор")
    made = TA.create(db, m, u)
    admin = type("A", (), {"id": None, "name": "тест", "role": type("R", (), {"key": "admin", "is_master": True})()})()
    out = R.master_confirm_ds(m.code, db, admin)
    nums = sorted(db.get(SalesAnnex, x["id"]).number for x in made)
    base = m.start_no + 1
    assert nums == sorted([f"Доп. соглашение № {base}"] + ([f"Доп. соглашение № {base}-01"] if len(made) > 1 else []))
    assert len(out["confirmed"]) == len(made)


def test_upd_basis_is_the_constructor_closing_basis(env):
    """Основание УПД — то же «основание для закрывающих», что в конструкторе ДС (владелец 19.10.2026: «реализовать то, что в конструкторе
    ДС»): шаблон с подстановками, бренд — свой у каждого УПД; свой текст хранится С подстановками и проверяется так же; пусто — снова
    по шаблону; в файле ДС печатается именно оно."""
    from app.routers.annexes import _doc
    from app.sales.models import SalesAnnex
    db, deals, u = env
    m = _package(db, deals, u, {"addons_separate": False, "upd_by_brand": True})
    TA.create(db, m, u)
    ups = TA.upds_of(db, m)
    assert ups and all("согласно Доп. соглашению" in x["basis"] and not x["basis_custom"] for x in ups), ups[0]["basis"]
    assert all("{" in x["basis_template"] and x["values"] for x in ups), "на экран — шаблон и значения, как в конструкторе"
    for x in ups:
        if x["brand"]:
            assert x["values"]["бренд_название"] in x["basis"], "бренд в основании — свой у каждого УПД"
    TA.set_basis(db, m, ups[0]["upd_no"], "Своё основание по {номер_дс}")
    ups2 = TA.upds_of(db, m)
    assert ups2[0]["basis_custom"] and ups2[0]["basis_template"] == "Своё основание по {номер_дс}"
    assert "{" not in ups2[0]["basis"] and ups2[0]["basis"].startswith("Своё основание по "), ups2[0]["basis"]   # {номер_дс} — номер, как в конструкторе
    assert ups2[0]["basis"] in _doc(db, db.get(SalesAnnex, ups[0]["annex_id"]))["closing_basis"]
    with pytest.raises(MS.MasterError):
        TA.set_basis(db, m, ups[0]["upd_no"], "Текст с {нет_такой_подстановки}")
    TA.set_basis(db, m, ups[0]["upd_no"], "  ")
    assert not TA.upds_of(db, m)[0]["basis_custom"]
    with pytest.raises(MS.MasterError):
        TA.set_basis(db, m, 999, "x")


@pytest.mark.parametrize("kinds,start", [
    (["base"], "Размещение рекламных материалов бренда"),
    (["extra", "extra"], "Оказание дополнительных услуг (Sales-Lift) для бренда"),
    (["base", "extra"], "Размещение рекламных материалов и оказание дополнительных услуг (Sales-Lift) бренда"),
])
def test_upd_basis_default_follows_ds_content(kinds, start):
    """Шаблон конструктора, но у ДС допов (n-01) — не «размещение рекламных материалов» (владелец 16.10)."""
    from types import SimpleNamespace

    from app.annex_tpl import document as D
    model = {"values": {"бренд_название": "Милдронат", "услуга": "Sales-Lift", "сеть": "SIMB-AD", "номер_дс": "5-01", "дата_дс_кратко": "01.10.26",
                        "договор_номер": "45/24", "договор_дата_кратко": "01.02.24", "период_с": "01.10.2026", "период_по": "31.10.2026"},
             "closing_basis": {"template": "x", "edited": False, "inherited_from": None}}
    k = SimpleNamespace(brand="Grindeks / Милдронат", basis_text=None)
    out = D.upd_closing(model, k, rows=[{"kind": x} for x in kinds])
    assert out["text"].startswith(start + " «Милдронат»"), out["text"]


def test_upd_basis_takes_ds_level_edit_or_inherited():
    """Основание, поправленное в конструкторе ДС (или унаследованное от прошлого ДС), — основание УПД по умолчанию."""
    from types import SimpleNamespace

    from app.annex_tpl import document as D
    model = {"values": {"бренд_название": "Милдронат", "номер_дс": "5"},
             "closing_basis": {"template": "По {номер_дс} для {бренд_название}", "edited": True, "inherited_from": None}}
    out = D.upd_closing(model, SimpleNamespace(brand="Кудесан", basis_text=None), rows=[{"kind": "base"}])
    assert out["text"] == "По 5 для Кудесан" and not out["edited"]
