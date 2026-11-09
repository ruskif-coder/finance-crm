# -*- coding: utf-8 -*-
"""«Документы для 1С» (владелец 05.11.2026): моста в 1С к закрытию не будет, бухгалтер сама забирает данные комплекта
(УПД + счёт), выставляет документы в 1С и вносит обратно номера, даты, суммы и PDF.

Поломки, которые ловит набор:
- PDF из 1С лежит в той же таблице, что сканы, и скан УПД «заменяет» его (поиск прежнего файла был по upd_no без вида);
- внесено не всё (нет номера/даты/суммы) — а пакет ушёл дальше;
- сумма 1С расходится больше чем на 1 ₽ без объяснения;
- пакет не уходит в «выставление», когда внесены все комплекты, или уходит, когда внесены не все;
- операция по счёту не родилась или считается от нашей суммы, а не от суммы 1С (вернувшаяся сумма — факт);
- возврат без комментария, возврат уже внесённого, «исправлено» без возврата;
- внесение в пакет, который ещё не дошёл до 1С.
Живой пакет стенда, транзакция откатывается."""
from datetime import date

import pytest

from tests._untouched_kit import untouched_kit
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.master_deal import status as ST


@pytest.fixture
def env(monkeypatch):
    from app.database import SessionLocal
    from app.master_deal.models import MasterDeal
    from app.models import User
    from app.onec_desk import service as SV
    db = SessionLocal()
    k = untouched_kit(db)
    if k is None:
        db.close()
        pytest.skip("на стенде нет комплектов УПД")
    m = db.get(MasterDeal, k.master_deal_id)
    m.status = ST.WAIT_1C
    db.execute(text("UPDATE contracts SET issue_channel = coalesce(issue_channel, 'ЭДО') WHERE id = :c"), {"c": m.contract_id})
    from app.sales.models import SalesAnnex
    a = db.get(SalesAnnex, k.annex_id)
    if a is not None and not a.number:
        a.number = "ДС № 2"
    for f in ("onec_state", "onec_at", "onec_invoice_no", "onec_upd_no", "onec_invoice_date", "onec_upd_date", "onec_net",
              "onec_vat", "onec_gross", "onec_by"):
        setattr(k, f, None)
    db.flush()
    sent = []
    monkeypatch.setattr(SV, "_notify", lambda db_, key, m_, **kw: sent.append(key))
    user = db.query(User).filter(User.is_active == 1).order_by(User.id).first()
    try:
        yield db, m, k, user, sent
    finally:
        db.rollback()
        db.close()


def _full(k, **kw):
    d = {"invoice_no": "1247", "invoice_date": date(2026, 10, 31), "upd_no": "УПД-881", "upd_date": date(2026, 10, 31),
         "net": float(k.net), "vat": float(k.vat), "gross": float(k.gross), "comment": None}
    d.update(kw)
    return d


def _all_kits(db, m):
    from app.master_deal.models import MasterDealUpd
    return db.query(MasterDealUpd).filter(MasterDealUpd.master_deal_id == m.id).order_by(MasterDealUpd.upd_no).all()


# ── файлы 1С и сканы в одной таблице ─────────────────────────────────────────────────────────────

def test_onec_pdf_is_not_a_scan(env):
    """PDF счёта из 1С к тому же upd_no — не скан: подпись по скану его не видит, скан его не заменяет, в «скан» карточки не попадает."""
    db, m, k, user, _ = env
    from app.master_deal import doc_sign as DSG
    from app.master_deal import docs as DC
    from app.master_deal import files as FL
    from app.master_deal.models import MasterDealFile
    db.add(MasterDealFile(master_deal_id=m.id, kind="счёт 1С", upd_no=k.upd_no, filename="счёт.pdf", path="x/счёт.pdf"))
    db.flush()
    assert DSG._scan_id(db, k) is None
    assert FL.scan_of(db, m, None, k.upd_no) is None
    assert DC._files(db, m).get(("u", k.upd_no)) is None


def test_onec_file_replaces_only_its_own_kind(env, tmp_path, monkeypatch):
    db, m, k, user, _ = env
    from app.onec_desk import files as OF
    monkeypatch.setattr(OF, "ROOT", str(tmp_path))
    a = OF.save(db, m, k, user, slot="invoice", filename="счёт.pdf", content=b"%PDF-1")
    OF.save(db, m, k, user, slot="upd", filename="упд.pdf", content=b"%PDF-2")
    b = OF.save(db, m, k, user, slot="invoice", filename="счёт2.pdf", content=b"%PDF-3")
    got = OF.files_of(db, m, k)
    assert got["invoice"]["filename"] == "счёт2.pdf" and got["upd"]["filename"] == "упд.pdf"
    assert a["old_path"] is None and b["old_path"]


def test_onec_file_types(env, tmp_path, monkeypatch):
    db, m, k, user, _ = env
    from app.onec_desk import files as OF
    from app.onec_desk.service import DeskError
    monkeypatch.setattr(OF, "ROOT", str(tmp_path))
    with pytest.raises(DeskError):
        OF.save(db, m, k, user, slot="invoice", filename="счёт.zip", content=b"x")
    with pytest.raises(DeskError):
        OF.save(db, m, k, user, slot="upd", filename="упд.xml", content=b"<x/>")
    OF.save(db, m, k, user, slot="xml", filename="упд.xml", content=b"<x/>")


def test_scan_delete_does_not_touch_onec_file(env):
    db, m, k, user, _ = env
    from app.master_deal import files as FL
    from app.master_deal.models import MasterDealFile
    from app.master_deal.service import MasterError
    f = MasterDealFile(master_deal_id=m.id, kind="УПД 1С", upd_no=k.upd_no, filename="упд.pdf", path="x/упд.pdf")
    db.add(f)
    db.flush()
    with pytest.raises(MasterError):
        FL.delete(db, m, f.id, user)


# ── внесение ─────────────────────────────────────────────────────────────────────────────────────

def test_enter_needs_every_field(env):
    db, m, k, user, _ = env
    from app.onec_desk import service as SV
    for miss in ("invoice_no", "invoice_date", "upd_no", "upd_date", "net", "vat", "gross"):
        with pytest.raises(SV.DeskError) as e:
            SV.enter(db, m, k, _full(k, **{miss: None}), user)
        assert e.value.status == 400
    assert k.onec_state is None and k.onec_at is None


def test_enter_gross_mismatch_over_1_rub_needs_comment(env):
    db, m, k, user, _ = env
    from app.onec_desk import service as SV
    with pytest.raises(SV.DeskError) as e:
        SV.enter(db, m, k, _full(k, net=float(k.net) + 10, gross=float(k.gross) + 10), user)
    assert "1 ₽" in e.value.message
    SV.enter(db, m, k, _full(k, net=float(k.net) + 0.6, gross=float(k.gross) + 0.6), user)       # до 1 ₽ — принимается молча
    assert k.onec_state == "внесён"


def test_enter_net_plus_vat_must_be_gross(env):
    db, m, k, user, _ = env
    from app.onec_desk import service as SV
    with pytest.raises(SV.DeskError):
        SV.enter(db, m, k, _full(k, vat=float(k.vat) + 50), user)


def test_enter_all_kits_moves_package_and_makes_operation_from_onec_sum(env):
    db, m, k, user, sent = env
    from app.onec_desk import service as SV
    kits = _all_kits(db, m)
    for i, x in enumerate(kits):
        assert m.status == ST.WAIT_1C, "пока внесены не все — пакет ждёт 1С"
        SV.enter(db, m, x, _full(x, invoice_no=f"12{i}", net=float(x.net) + 0.5, gross=float(x.gross) + 0.5), user)
    assert m.status == ST.ISSUE
    assert "master_onec_done" in sent
    for x in kits:
        assert x.onec_state == "внесён" and x.onec_at and x.onec_by == user.id
        op = db.execute(text("SELECT income, invoice FROM operations WHERE master_deal_upd_id = :k"), {"k": x.id}).one()
        assert abs(op.income - float(x.onec_gross)) < 0.01, "вернувшаяся из 1С сумма — факт"
    ev = db.execute(text("SELECT kind FROM onec_desk_events WHERE upd_id = :k ORDER BY id"), {"k": k.id}).scalars().all()
    assert ev == ["внесено"]


def test_enter_refused_before_1c(env):
    db, m, k, user, _ = env
    from app.onec_desk import service as SV
    m.status = ST.AGREE
    with pytest.raises(SV.DeskError) as e:
        SV.enter(db, m, k, _full(k), user)
    assert e.value.status == 409


def test_edit_after_entered_is_a_correction(env):
    db, m, k, user, _ = env
    from app.onec_desk import service as SV
    SV.enter(db, m, k, _full(k), user)
    SV.enter(db, m, k, _full(k, invoice_no="1300"), user)
    assert k.onec_invoice_no == "1300"
    ev = db.execute(text("SELECT kind FROM onec_desk_events WHERE upd_id = :k ORDER BY id"), {"k": k.id}).scalars().all()
    assert ev == ["внесено", "правка"]


# ── возврат аккаунту ──────────────────────────────────────────────────────────────────────────────

def test_return_needs_text_and_shows_in_package_todo(env):
    db, m, k, user, sent = env
    from app.onec_desk import service as SV
    with pytest.raises(SV.DeskError):
        SV.give_back(db, m, k, "   ", user)
    SV.give_back(db, m, k, "КПП покупателя не тот", user)
    assert k.onec_state == "возвращён" and "master_onec_returned" in sent
    t = ST.todo(db, m)
    assert t["tone"] == "bad" and "КПП покупателя не тот" in t["text"]


def test_return_of_entered_kit_refused(env):
    db, m, k, user, _ = env
    from app.onec_desk import service as SV
    SV.enter(db, m, k, _full(k), user)
    with pytest.raises(SV.DeskError) as e:
        SV.give_back(db, m, k, "ошибка", user)
    assert e.value.status == 409


def test_fixed_only_after_return(env):
    db, m, k, user, _ = env
    from app.onec_desk import service as SV
    with pytest.raises(SV.DeskError):
        SV.fixed(db, m, k, None, user)
    SV.give_back(db, m, k, "основание без бренда", user)
    SV.fixed(db, m, k, "поправил основание", user)
    assert k.onec_state is None
    ev = db.execute(text("SELECT kind, text FROM onec_desk_events WHERE upd_id = :k ORDER BY id"), {"k": k.id}).all()
    assert [e.kind for e in ev] == ["возврат", "исправлено"] and ev[1].text == "поправил основание"


def test_basis_editable_while_returned(env):
    """Возврат «основание не то» — аккаунт правит основание; после внесения — уже нет (сумма и основание у 1С)."""
    db, m, k, user, _ = env
    from app.master_deal import to_annex as TA
    from app.master_deal.service import MasterError
    from app.onec_desk import service as SV
    SV.give_back(db, m, k, "основание", user)
    TA.set_basis(db, m, k.upd_no, None)
    SV.fixed(db, m, k, None, user)
    SV.enter(db, m, k, _full(k), user)
    with pytest.raises(MasterError):
        TA.set_basis(db, m, k.upd_no, None)


# ── очередь и карточка ────────────────────────────────────────────────────────────────────────────

def test_queue_and_card_carry_what_1c_needs(env):
    db, m, k, user, _ = env
    from app.onec_desk import queue as Q
    rows = Q.queue(db, "wait")
    row = next(r for r in rows if r["kit_id"] == k.id)
    assert row["master"] == m.code and row["state"] is None
    card = Q.card(db, k)
    assert card["buyer"]["inn"] is not None and card["contract"]["number"] is not None
    assert card["annex"]["number"] and card["basis"]
    assert card["lines"] and abs(sum(x["net"] for x in card["lines"]) - float(k.net)) < 1
    assert card["upd_date_suggested"].endswith(("-28", "-29", "-30", "-31"))
    from app.onec_desk import service as SV
    SV.enter(db, m, k, _full(k), user)
    assert all(r["kit_id"] != k.id for r in Q.queue(db, "wait"))
    assert any(r["kit_id"] == k.id for r in Q.queue(db, "done"))


# ── ревью 05.11.2026 ──────────────────────────────────────────────────────────────────────────────

def test_long_number_is_a_400_not_a_500(env):
    db, m, k, user, _ = env
    from app.onec_desk import service as SV
    with pytest.raises(SV.DeskError) as e:
        SV.enter(db, m, k, _full(k, invoice_no="Счёт на оплату № 0000-001247 от 31.10.2026 г. (копия)"), user)
    assert e.value.status == 400 and "40" in e.value.message


@pytest.mark.parametrize("bad", [{"gross": float("nan")},
                                 {"net": -1.0, "vat": 0.0, "gross": -1.0, "comment": "по счёту так"},
                                 {"net": 0.0, "vat": 0.0, "gross": 0.0, "comment": "по счёту так"}])
def test_sums_must_be_real_positive_numbers(env, bad):
    db, m, k, user, _ = env
    from app.onec_desk import service as SV
    with pytest.raises(SV.DeskError):
        SV.enter(db, m, k, _full(k, **bad), user)


def test_operation_vat_is_the_1c_vat(env):
    """Вернувшиеся из 1С суммы — факт (решение 42): НДС операции — НДС из 1С, а не пересчёт от нашей ставки."""
    db, m, k, user, _ = env
    from app.onec_desk import service as SV
    SV.enter(db, m, k, _full(k, net=float(k.net) - 0.3, vat=float(k.vat) + 0.3), user)
    vat = db.execute(text("SELECT vat_fact FROM operations WHERE master_deal_upd_id = :k"), {"k": k.id}).scalar()
    assert abs(vat - float(k.onec_vat)) < 0.005


def test_bridge_failure_is_reported_not_swallowed(env, monkeypatch):
    db, m, k, user, _ = env
    from app.master_deal import bridge as BR
    from app.onec_desk import service as SV
    monkeypatch.setattr(BR, "sync_kit", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("нет статьи")))
    out = SV.enter(db, m, k, _full(k), user)
    assert out["operation_error"] and k.onec_state == "внесён"


def test_all_entered_but_stuck_tells_the_account_and_offers_the_step(env):
    """Канала у договора не было — пакет остался в «ждём 1С»; канал проставили позже — «что нужно сейчас» говорит аккаунту
    перевести пакет, в реестре есть шаг. «бухгалтерия: внесено N из N» — неправда: у бухгалтера дел больше нет."""
    db, m, k, user, sent = env
    from app.onec_desk import service as SV
    db.execute(text("UPDATE contracts SET issue_channel = NULL WHERE id = :c"), {"c": m.contract_id})
    for x in _all_kits(db, m):
        SV.enter(db, m, x, _full(x), user)
    assert m.status == ST.WAIT_1C
    db.execute(text("UPDATE contracts SET issue_channel = 'ЭДО' WHERE id = :c"), {"c": m.contract_id})
    t = ST.todo(db, m)
    assert t["who"] == "аккаунт" and "выставление" in t["text"]
    assert ST.row_step(db, m) == "docs_1c"
    SV.enter(db, m, k, _full(k, invoice_no="999"), user)       # правка — второго «внесены все» нет
    assert sent.count("master_onec_done") == 1


def test_queue_finds_kits_of_packages_moved_on_by_hand(env):
    """Пакет, который до «Документов для 1С» двинули руками дальше «ждём 1С», — его комплекты без ответа 1С тоже в очереди."""
    db, m, k, user, _ = env
    from app.onec_desk import queue as Q
    m.status = ST.ISSUE
    db.flush()
    assert any(r["kit_id"] == k.id for r in Q.queue(db, "wait"))


# ── имя скачиваемого файла (владелец 05.11.2026: «файлы при скачивании должны нести данные мастер-сделки, контрагентов
#    и периода») ─────────────────────────────────────────────────────────────────────────────────────

def test_download_name_carries_master_counterparty_and_period(env):
    db, m, k, user, _ = env
    from app.onec_desk import names as NM
    name = NM.file_name(db, m, "Счёт № 1247", ".pdf", upd_no=k.upd_no)
    buyer = db.execute(text("""SELECT cp.name FROM contracts c JOIN counterparties cp ON cp.id = c.counterparty_id
                                WHERE c.id = :c"""), {"c": m.contract_id}).scalar()
    assert name.startswith(m.code) and m.period in name and name.endswith(".pdf")
    assert f"УПД № {k.upd_no}" in name and "Счёт № 1247" in name
    assert NM.safe(buyer)[:20] in name
    assert not any(ch in name for ch in '/\\:*?"<>|')


def test_download_name_strips_characters_windows_refuses():
    from app.onec_desk import names as NM
    assert NM.safe('ООО "Ромашка/Лютик": *?') == "ООО Ромашка Лютик"


def test_file_of_entered_kit_can_be_replaced_not_removed(env, tmp_path, monkeypatch):
    """Внесённая заявка: файл можно догрузить или заменить, но не убрать — иначе внесённое останется без обязательного документа."""
    db, m, k, user, _ = env
    from app.onec_desk import files as OF
    from app.onec_desk import service as SV
    monkeypatch.setattr(OF, "ROOT", str(tmp_path))
    k.onec_state = SV.DONE
    db.flush()
    f = OF.save(db, m, k, user, slot="upd", filename="упд.pdf", content=b"%PDF-1")
    OF.save(db, m, k, user, slot="upd", filename="упд2.pdf", content=b"%PDF-2")
    new_id = OF.files_of(db, m, k)["upd"]["id"]
    with pytest.raises(SV.DeskError) as e:
        OF.delete(db, m, k, new_id)
    assert e.value.status == 409 and f["id"] != new_id
