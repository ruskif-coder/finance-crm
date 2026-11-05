# -*- coding: utf-8 -*-
"""Имя скачиваемого файла пакета (владелец 05.11.2026: «файлы при скачивании должны нести данные мастер-сделки и контрагентов
и периода»): «M-0019 · АПР ЕВРАЗИЯ ООО · 2026-10 · УПД № 1 · Счёт № 1247.pdf». Одна функция на все скачивания пакета —
файлы из 1С, ДС, сканы, выгрузку; экран имя не придумывает (правило 13.09.2026, `lib/download`)."""
import re
from typing import Optional
from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.orm import Session

_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
MAX_PART = 60


def safe(s: Optional[str]) -> str:
    """Часть имени без знаков, которые не примет Windows; пробелы схлопнуты."""
    return re.sub(r"\s+", " ", _BAD.sub(" ", s or "")).strip()[:MAX_PART].strip()


def parties(db: Session, m) -> str:
    """Контрагент доходного договора и, если платит другой, — плательщик через «→»."""
    r = db.execute(text("""SELECT b.name, p.name FROM master_deals m JOIN contracts c ON c.id = m.contract_id
                             LEFT JOIN counterparties b ON b.id = c.counterparty_id
                             LEFT JOIN counterparties p ON p.id = m.payer_counterparty_id AND p.id IS DISTINCT FROM c.counterparty_id
                            WHERE m.id = :m"""), {"m": m.id}).first()
    if r is None:
        return ""
    return " → ".join(safe(x) for x in r if x)


def file_name(db: Session, m, label: str, ext: str, upd_no: Optional[int] = None) -> str:
    parts = [m.code, parties(db, m), m.period, f"УПД № {upd_no}" if upd_no else None, safe(label)]
    return " · ".join(p for p in parts if p) + ext


def disposition(name: str, ascii_fallback: str) -> str:
    """Content-Disposition с кириллицей: ASCII-запасное имя и `filename*` в UTF-8 (RFC 5987), как у ДС."""
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(name)}"


def for_file(db: Session, m, f) -> str:
    """Имя файла пакета по его виду: скан ДС / скан УПД / счёт, УПД и XML из 1С — с номерами документов."""
    import os
    from app.master_deal.models import MasterDealUpd
    ext = os.path.splitext(f.filename or "")[1].lower() or ".pdf"
    if f.annex_id:
        num = db.execute(text("SELECT number FROM sales_annexes WHERE id = :a"), {"a": f.annex_id}).scalar()
        return file_name(db, m, f"{num or 'ДС'} · скан подписанного", ext)
    k = db.query(MasterDealUpd).filter_by(master_deal_id=m.id, upd_no=f.upd_no).first()
    label = {"счёт 1С": f"Счёт № {k.onec_invoice_no}" if k is not None and k.onec_invoice_no else "Счёт",
             "УПД 1С": f"УПД 1С № {k.onec_upd_no}" if k is not None and k.onec_upd_no else "УПД 1С",
             "УПД 1С xml": f"УПД 1С № {k.onec_upd_no} · ЭДО" if k is not None and k.onec_upd_no else "УПД 1С · ЭДО",
             }.get(f.kind, "скан подписанного")
    return file_name(db, m, label, ext, upd_no=f.upd_no)
