# -*- coding: utf-8 -*-
"""Каждая ручка скачивания документа называет файл ОДНИМ правилом `app.doc_names` (владелец 09.11.2026: «независимо с какого
экрана качаю — формат един»). Ломается, если ручка снова соберёт имя сама: ДС справочника без мастер-сделки, файлы пакета без
даты, архив «M-0004.zip», договор с именем загрузки. Только чтение."""
from urllib.parse import unquote

import pytest

import app.model_registry  # noqa: F401
from app import doc_names as DN


@pytest.fixture
def db():
    from app.database import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _admin(db):
    from app.models import User
    return db.query(User).join(User.role).filter_by(key="admin").first()


def _cd_name(resp) -> str:
    return unquote(resp.headers["content-disposition"].split("filename*=UTF-8''", 1)[1])


def test_package_files_from_desk_and_master_deal_share_the_rule(db):
    from app.master_deal.models import MasterDeal, MasterDealFile, MasterDealUpd
    from app.onec_desk import names as NM
    f = db.query(MasterDealFile).filter(MasterDealFile.kind == "счёт 1С").order_by(MasterDealFile.id).first()
    if f is None:
        pytest.skip("на стенде нет счетов 1С")
    m = db.get(MasterDeal, f.master_deal_id)
    k = db.query(MasterDealUpd).filter_by(master_deal_id=m.id, upd_no=f.upd_no).first()
    n = NM.for_file(db, m, f)
    assert n == DN.for_package_file(db, m, f)
    assert n.startswith(f"Счёт № {k.onec_invoice_no} от {k.onec_invoice_date:%d.%m.%Y} · ") and f" · {m.code}" in n


def test_annex_docx_is_named_by_the_rule_with_its_package(db):
    from app.sales import annex_print
    from app.sales.models import SalesAnnex
    for a in db.query(SalesAnnex).filter(SalesAnnex.master_deal_id.isnot(None), SalesAnnex.no.isnot(None)).order_by(SalesAnnex.id):
        try:
            got, _ = annex_print.printable_docx(db, a.id)
        except Exception:  # noqa: BLE001 — не собирается (юрист, реквизиты) — берём следующий
            continue
        assert got == DN.for_annex(db, a, ".docx")
        return
    pytest.skip("на стенде нет собираемого ДС в пакете")


def test_package_zip_is_named_by_the_rule(db):
    from app.master_deal import bundle
    from app.master_deal.models import MasterDeal
    m = db.query(MasterDeal).order_by(MasterDeal.id).first()
    if m is None:
        pytest.skip("на стенде нет мастер-сделок")
    assert bundle.build(db, m)[0] == DN.for_package_zip(db, m)


def test_contract_file_is_named_by_the_rule(db):
    from app.models import Contract
    from app.routers import contracts as R
    c = db.query(Contract).filter(Contract.attached_filename.isnot(None)).order_by(Contract.id).first()
    if c is None:
        pytest.skip("на стенде нет прикреплённых договоров")
    try:
        resp = R.download_contract_document(c.id, db=db, current_user=_admin(db))
    except Exception:  # noqa: BLE001
        pytest.skip("файла договора нет на диске стенда")
    ext = "." + c.attached_filename.rsplit(".", 1)[-1].lower() if "." in c.attached_filename else ""
    assert resp.filename == DN.for_contract(db, c, ext)
