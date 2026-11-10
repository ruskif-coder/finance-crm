# -*- coding: utf-8 -*-
"""Имя выгрузки пакета для 1С (xlsx): «M-0019 · АПР ЕВРАЗИЯ ООО · 2026-10 · для 1С.xlsx». Документы пакета (ДС, счёт, УПД, XML,
сканы) называются общим правилом `app.doc_names` (владелец 09.11.2026) — `for_file` отдаёт туда."""
import re
from typing import Optional

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
    from app.doc_names import disposition as _d
    return _d(name, ascii_fallback)


def for_file(db: Session, m, f) -> str:
    """Файл пакета — общим правилом имени документа (`app.doc_names`, владелец 09.11.2026: «формат един»)."""
    from app.doc_names import for_package_file
    return for_package_file(db, m, f)
