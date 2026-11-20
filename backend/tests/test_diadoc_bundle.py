# -*- coding: utf-8 -*-
"""Архив «Скачать для Диадока» (реестр v3, 12.11.2026; владелец: класть то, что есть, недостающее — в «не вошло.txt»).
Поломка, которую ловит: комплект без PDF счёта, PDF УПД или XML УПД из 1С молча выпадает из архива, и в Диадок уходит неполный
пакет; сканы (подписанная бумага) попадают в архив для ЭДО."""
from app.master_deal import bundle


def test_missing_1c_files_are_named_per_kit():
    kits = [{"upd_no": 1, "upd_doc_no": "1247"}, {"upd_no": 2, "upd_doc_no": None}]
    files = {1: {"invoice": {"id": 5}, "upd": {"id": 6}, "xml": {"id": 7}}, 2: {"upd": {"id": 8}}}
    assert bundle.missing_onec(kits, files) == ["Комплект 2: нет счёта (pdf) и XML УПД из 1С"]


def test_kit_with_nothing_from_1c():
    assert bundle.missing_onec([{"upd_no": 3, "upd_doc_no": None}], {}) == ["Комплект 3: нет счёта (pdf), УПД (pdf) и XML УПД из 1С"]


def test_diadoc_bundle_takes_1c_files_not_scans():
    assert bundle.diadoc_kinds() == {"счёт 1С", "УПД 1С", "УПД 1С xml"}


def test_diadoc_bundle_takes_the_external_ds_file():
    """ДС, подписанный вне системы, — файл клиента в слоте «скан ДС» (владелец 12.11.2026: «они мне так же нужны в рамках архива
    с доками»). Обычный скан подписанной бумаги в архив для ЭДО по-прежнему не идёт."""
    from types import SimpleNamespace as NS
    ext = {7}
    assert bundle.diadoc_file(NS(kind="скан ДС", annex_id=7), ext) is True
    assert bundle.diadoc_file(NS(kind="скан ДС", annex_id=8), ext) is False
    assert bundle.diadoc_file(NS(kind="скан УПД", annex_id=None), ext) is False
    assert bundle.diadoc_file(NS(kind="счёт 1С", annex_id=None), ext) is True


def test_ds_button_downloads_the_client_file_for_an_external_ds():
    """Кнопка «ДС pdf» вела на сборку нашего docx, а у внешнего ДС она запрещена — скачать было нельзя."""
    from types import SimpleNamespace as NS
    from app.master_deal import docs
    assert docs.doc_url(NS(id=5, origin="загружен"), has_file=True) == "/annexes/5/external-file"
    assert docs.doc_url(NS(id=6, origin=None)) == "/annexes/6/docx"
    # владелец 12.11.2026: внешний ДС — либо ссылка на Диадок («уже в ЭДО»), либо файл; без файла кнопки скачать нет
    assert docs.doc_url(NS(id=7, origin="загружен"), has_file=False) is None


def test_pack_docs_keep_sign_and_links():
    """12.11.2026: правка ссылки на Диадок унесла поле `sign` в комментарий — у всех ДС в карточке стало «не выпущен».
    Каждый ДС пакета отдаёт и подпись, и кнопку документа, и ссылку ЭДО."""
    from app.database import SessionLocal
    from app.master_deal import docs
    from app.master_deal.models import MasterDeal
    import app.model_registry  # noqa: F401
    db = SessionLocal()
    try:
        m = db.query(MasterDeal).join(MasterDeal.__table__.metadata.tables["sales_annexes"],
                                      MasterDeal.__table__.c.id == MasterDeal.__table__.metadata.tables["sales_annexes"].c.master_deal_id).first()
        if m is None:
            import pytest
            pytest.skip("нет пакетов с ДС")
        for d in docs.build(db, m)["ds"]:
            assert {"sign", "doc_url", "edo_link"} <= set(d), d.keys()
    finally:
        db.close()


# ── бумага: «Скачать для печати» (владелец 20.11.2026: «для мастер-сделок на бумаге тоже нужно скачать архив, как для ЭДО») ──

def test_paper_bundle_takes_printable_1c_files_only():
    """На бумагу печатают PDF счёта и УПД; XML УПД и сканы подписанной бумаги в архив для печати не идут."""
    from types import SimpleNamespace as NS
    assert bundle.pack_file(NS(kind="счёт 1С", annex_id=None), set(), "paper") is True
    assert bundle.pack_file(NS(kind="УПД 1С", annex_id=None), set(), "paper") is True
    assert bundle.pack_file(NS(kind="УПД 1С xml", annex_id=None), set(), "paper") is False
    assert bundle.pack_file(NS(kind="скан УПД", annex_id=None), set(), "paper") is False
    assert bundle.pack_file(NS(kind="скан ДС", annex_id=7), {7}, "paper") is True, "ДС, подписанный вне системы, — сам документ"
    assert bundle.pack_file(NS(kind="УПД 1С xml", annex_id=None), set(), "diadoc") is True


def test_paper_bundle_names_missing_pdfs_without_asking_for_xml():
    kits = [{"upd_no": 1}, {"upd_no": 2}]
    files = {1: {"invoice": {"id": 5}, "upd": {"id": 6}}, 2: {"upd": {"id": 8}}}
    assert bundle.missing_onec(kits, files, "paper") == ["Комплект 2: нет счёта (pdf) из 1С"]
    assert bundle.missing_onec(kits, files) == ["Комплект 1: нет XML УПД из 1С", "Комплект 2: нет счёта (pdf) и XML УПД из 1С"]


def test_paper_bundle_has_ds_both_as_docx_and_pdf(monkeypatch):
    """Владелец 20.11.2026: в архиве для печати ДС — PDF «дублем», docx оставить. Сайдкар печати лёг — docx на месте, PDF
    назван в «не вошло.txt». В архиве для Диадока PDF ДС нет."""
    import io
    import zipfile
    from fastapi import HTTPException
    import app.model_registry  # noqa: F401
    from sqlalchemy import text
    from app.database import SessionLocal
    from app.master_deal.models import MasterDeal
    db = SessionLocal()
    try:
        mid = db.execute(text("""SELECT m.id FROM master_deals m JOIN sales_annexes a ON a.master_deal_id = m.id
                                  WHERE a.origin IS DISTINCT FROM 'загружен' ORDER BY m.id LIMIT 1""")).scalar()
        if mid is None:
            import pytest
            pytest.skip("нет пакетов с ДС")
        m = db.get(MasterDeal, mid)
        monkeypatch.setattr(bundle, "_annex_docx", lambda db_, aid: ("x.docx", b"DOCX"))
        monkeypatch.setattr(bundle, "_annex_pdf", lambda db_, aid: ("x.pdf", b"%PDF"))

        def names(**kw):
            z = zipfile.ZipFile(io.BytesIO(bundle.build(db, m, **kw)[1]))
            return z, [n for n in z.namelist() if z.read(n) in (b"DOCX", b"%PDF")]
        _, paper = names(paper=True)
        assert sum(n.endswith(".docx") for n in paper) >= 1
        assert sum(n.endswith(".pdf") for n in paper) == sum(n.endswith(".docx") for n in paper), paper
        _, edo = names(diadoc=True)
        assert not any(n.endswith(".pdf") for n in edo), "в Диадок ДС уходит docx, как и было"

        def down(db_, aid):
            raise HTTPException(502, "Сервис генерации PDF недоступен")
        monkeypatch.setattr(bundle, "_annex_pdf", down)
        z, paper = names(paper=True)
        assert any(n.endswith(".docx") for n in paper) and not any(n.endswith(".pdf") for n in paper)
        assert "Сервис генерации PDF недоступен" in z.read("не вошло.txt").decode()
    finally:
        db.rollback()
        db.close()
