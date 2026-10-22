# -*- coding: utf-8 -*-
"""ДС мастер-сделки печатается без сверки с медиапланом (строки — снимок сверки), но с проверкой своей таблицы (21.10.2026)."""
from types import SimpleNamespace

from app.annex_tpl import document as D


def test_master_doc_drops_mp_mismatch_and_keeps_own_consistency():
    class Q:
        def filter(self, *a):
            return self

        def order_by(self, *a):
            return self

        def all(self):
            return []
    db = SimpleNamespace(query=lambda *a: Q())
    doc = {"missing": ["сумма приложения 162 354.18 не сходится с медиапланом 933 313.14", "заказчик: подписант"]}
    model = {"table": {"groups": []}, "amount": 1, "vat": 0, "number": "ДС № 2",
             "consistency": {"ok": False, "details": ["итог без НДС плюс НДС не равен итогу с НДС"]}}
    out = D._master_doc(db, SimpleNamespace(id=1, rows=[]), None, doc, model)
    assert out["missing"] == ["заказчик: подписант", "итог без НДС плюс НДС не равен итогу с НДС"]


def test_docx_footer_has_only_master_code_and_black_borders():
    """Колонтитул — только код пакета (владелец 21.10.2026: «убери „мастер сделка“, оставь только номер»); рамки таблицы чёрные."""
    import io
    import re
    import zipfile
    from datetime import date

    from app.sales import annex_docx
    d = {"number": "ДС № 2", "date": date(2026, 10, 1), "contract": {"number": "1", "date": date(2024, 1, 1)},
         "customer": {}, "executor": {}, "rows": [], "amount": 0, "vat": 0, "vat_rate": 22, "master_code": "M-1167"}
    z = zipfile.ZipFile(io.BytesIO(annex_docx.build_docx(d)))
    foot = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", z.read("word/footer1.xml").decode()))
    assert foot == "M-1167"
    assert annex_docx.BORDER == "000000"


def test_pdf_request_carries_master_code_as_footer(db, monkeypatch):
    """Код уходит сервису печати полем `footer` — колонтитулом принтера на каждом листе, в поле страницы."""
    import pytest
    from app.master_deal.models import MasterDeal
    from app.models import User
    from app.routers import annexes as AX
    from app.sales.models import SalesAnnex
    a = db.query(SalesAnnex).join(MasterDeal, MasterDeal.id == SalesAnnex.master_deal_id).filter(SalesAnnex.rows.isnot(None)).first()
    if a is None:
        pytest.skip("на стенде нет ДС мастер-сделки")
    sent = {}

    class R:
        content = b"%PDF"

        def raise_for_status(self):
            return None
    monkeypatch.setattr(AX.httpx, "post", lambda url, json, timeout: sent.update(json) or R())
    user = db.query(User).filter(User.role.has(key="admin")).first()
    AX.annex_pdf(a.id, db, user)
    assert sent["footer"] == db.get(MasterDeal, a.master_deal_id).code
