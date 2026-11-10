# -*- coding: utf-8 -*-
"""Имя скачиваемого документа — одно правило на всю систему (владелец 09.11.2026): «вид - номер - дата - контрагент - мастер
сделка - доп инфа если нужна», «независимо с какого экрана качаю — формат един».

    ДС № 12 от 31.10.2026 · АПР ЕВРАЗИЯ ООО · M-0019.pdf
    УПД № 240 от 06.11.2026 · ИЗИ-НЭТ ООО · M-0004 · ЭДО.xml
    Договор № РМ-01-06-26-1 от 01.06.2026 · ООО Ромашка.pdf

Разделитель « · », а не дефис: дефис живёт внутри номеров (`РМ-01-06-26-1`, `M-0004`). Контрагент — тот, кому документ выставлен:
плательщик пакета, а если его нет — сторона договора. Экран имя не придумывает: сервер отдаёт его в `Content-Disposition`,
`lib/download` его берёт (правило 13.09.2026). Чужие файлы без нашего номера (сверки и документы площадок, файлы сделок) — с именем
загрузки, их не трогаем (владелец 09.11.2026). Медиаплан называется своим правилом (`lib/mpDownload.js`)."""
import os
import re
from typing import Optional
from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.orm import Session

SEP = " · "
_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
MAX_PART = 60
MAX_NAME = 110          # символов до расширения: кириллица в UTF-8 — два байта, предел ФС — 255 байт

# Как на экранах (`frontend/lib/annexNumber.js`): «ДС № 68» / «ПР № 68»; полная форма остаётся в самом документе
_SHORT = ((re.compile(r"^\s*(дополнительное|доп\.?)\s*соглашение\s*", re.I), "ДС "), (re.compile(r"^\s*приложение\s*", re.I), "ПР "))


def safe(s: Optional[str]) -> str:
    """Часть имени без знаков, которые не примет Windows; пробелы схлопнуты, длина ограничена."""
    return re.sub(r"\s+", " ", _BAD.sub(" ", s or "")).strip()[:MAX_PART].strip()


def head(word_no: str, d) -> str:
    """«Счёт № 287 от 06.11.2026»; без даты — только вид и номер."""
    return f"{word_no} от {d.strftime('%d.%m.%Y')}" if d else word_no


def name(word_no: str, d, counterparty: Optional[str], master_code: Optional[str], extra: Optional[str] = None,
         ext: str = ".pdf") -> str:
    parts = [safe(head(word_no, d)), safe(counterparty), safe(master_code), safe(extra)]
    return SEP.join(p for p in parts if p)[:MAX_NAME].rstrip(" ·") + ext


def short_annex(number: Optional[str], no: Optional[int] = None) -> str:
    if number:
        for rx, word in _SHORT:
            if rx.search(number):
                return re.sub(r"№\s*", "№ ", word + rx.sub("", number, count=1))
        return number
    return f"ДС № {no}" if no else "ДС без номера"


def disposition(file_name: str, ascii_fallback: str) -> str:
    """Content-Disposition с кириллицей: ASCII-запасное имя и `filename*` в UTF-8 (RFC 5987)."""
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(file_name)}"


def _cp_name(db: Session, cp_id) -> Optional[str]:
    return db.execute(text("SELECT name FROM counterparties WHERE id = :i"), {"i": cp_id}).scalar() if cp_id else None


def package_counterparty(db: Session, m) -> Optional[str]:
    """Кому выставлен документ пакета: плательщик, иначе сторона договора."""
    if m.payer_counterparty_id:
        return _cp_name(db, m.payer_counterparty_id)
    cp = db.execute(text("SELECT counterparty_id FROM contracts WHERE id = :c"), {"c": m.contract_id}).scalar() if m.contract_id else None
    return _cp_name(db, cp)


def for_annex(db: Session, a, ext: str = ".pdf", extra: Optional[str] = None, number: Optional[str] = None) -> str:
    """ДС с любого экрана: справочник, мастер-сделка, «Закрывающие документы», внешний файл, скан. `number` — номер из раскладки
    пакета для черновика, у которого своего номера ещё нет (архив пакета)."""
    from app.master_deal.models import MasterDeal
    m = db.get(MasterDeal, a.master_deal_id) if getattr(a, "master_deal_id", None) else None
    if m is not None:
        cp, code = package_counterparty(db, m), m.code
    else:
        cp, code = _cp_name(db, db.execute(text("SELECT counterparty_id FROM contracts WHERE id = :c"),
                                           {"c": a.contract_id}).scalar()), None
    return name(short_annex(a.number or number, a.no), a.date, cp, code, extra, ext)


def for_package_file(db: Session, m, f) -> str:
    """Файл пакета по виду: скан ДС → как ДС; счёт, УПД, XML из 1С — номером и датой документа 1С; скан УПД — номером УПД."""
    from app.master_deal.models import MasterDealUpd
    from app.sales.models import SalesAnnex
    ext = os.path.splitext(f.filename or "")[1].lower() or ".pdf"
    if f.annex_id:
        a = db.get(SalesAnnex, f.annex_id)
        if a is not None:
            return for_annex(db, a, ext, "скан подписанного")
    k = db.query(MasterDealUpd).filter_by(master_deal_id=m.id, upd_no=f.upd_no).first()
    inv_no, inv_d = (k.onec_invoice_no, k.onec_invoice_date) if k is not None else (None, None)
    upd_no, upd_d = (k.onec_upd_no, k.onec_upd_date) if k is not None else (None, None)
    upd = f"УПД № {upd_no}" if upd_no else (f"УПД № {f.upd_no} в пакете" if f.upd_no else "УПД")
    word, d, extra = {"счёт 1С": (f"Счёт № {inv_no}" if inv_no else "Счёт", inv_d, None),
                      "УПД 1С": (upd, upd_d, None),
                      "УПД 1С xml": (upd, upd_d, "ЭДО")}.get(f.kind, (upd, upd_d, "скан подписанного"))
    return name(word, d, package_counterparty(db, m), m.code, extra, ext)


def for_package_zip(db: Session, m) -> str:
    """Архив пакета: «Пакет M-0004 · ИЗИ-НЭТ ООО · октябрь 2026.zip» — дата документа у пакета нет, есть период."""
    from app.periods import month_label
    return name(f"Пакет {m.code}", None, package_counterparty(db, m), None, month_label(m.period) if m.period else None, ".zip")


def for_contract(db: Session, c, ext: str) -> str:
    """Файл договора: мастер-сделки у договора нет — он не привязан к одному пакету."""
    return name(f"Договор № {c.contract_number}" if c.contract_number else "Договор", c.contract_date,
                _cp_name(db, c.counterparty_id) or c.counterparty_name, None, None, ext)
