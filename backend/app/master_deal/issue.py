# -*- coding: utf-8 -*-
"""Выставление пакета — сводка по документам (владелец 02.11.2026; до того — отметки на пакете целиком, 19.10.2026).

Клиент может отказать в подписи одного документа пакета после всех согласований, поэтому статус подписи — у КАЖДОГО ДС и
УПД (`doc_sign`), а пакет его только сводит:
  «выставление» → «ждём оплату» — сам, когда выставлены все документы (`sync`); руками — при том же условии;
  архив — когда подписаны все; у бумаги между ними по-прежнему «Оплачено» → «ждём сканы»;
  отклонённый документ держит пакет и называет себя в «что нужно сейчас».
Скан — к КАЖДОМУ бумажному документу (19.10.2026: «скан к документу, ибо надо понимать, что есть что»); приложенный скан
ушедшей клиенту бумаги и есть отметка «подписан». Срок до красного у неподписанных — `company_settings.master_scans_due_days`
(по умолчанию 30) от последней выставленной отметки."""
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.master_deal import doc_sign as DS

SCAN_DS, SCAN_UPD = "скан ДС", "скан УПД"
SCAN_KINDS = (SCAN_DS, SCAN_UPD)      # в master_deal_files рядом лежат и файлы из 1С (05.11.2026) — сканы только этими видами
SCAN_EXTS = (".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff")      # один файл — один документ: без архивов
DUE_DEFAULT = 30      # владелец 19.10.2026


def due_days(db: Session) -> int:
    v = db.execute(text("SELECT value FROM company_settings WHERE key = 'master_scans_due_days'")).scalar()
    try:
        return max(int(v), 1)
    except (TypeError, ValueError):
        return DUE_DEFAULT


def scan_ext_ok(filename: str) -> bool:
    return (filename or "").lower().endswith(SCAN_EXTS)


def docs(db: Session, m) -> list:
    """Документы пакета, уходящие клиенту: подтверждённые ДС и комплекты УПД."""
    return DS.pack_docs(db, m)


def doc_label(d) -> str:
    return DS.label(d)


def labels_of(db: Session, m, pick) -> list:
    """Подписи документов пакета, отобранных `pick(doc)` — номер ДС тем словом, что в документе."""
    from app.master_deal import to_annex as TA
    numbers = {x["id"]: x["number"] for x in TA.annexes_of(db, m)} if db is not None else {}
    out = []
    for d in docs(db, m):
        if pick(d):
            out.append(numbers.get(d.id) if (DS.is_annex(d) and numbers.get(d.id)) else doc_label(d))
    return out


def state(db: Session, m) -> dict:
    return DS.summary(docs(db, m))


def not_sent(db: Session, m) -> list:
    return labels_of(db, m, lambda d: d.sign_state not in DS.OUT)


def unsigned(db: Session, m) -> list:
    return labels_of(db, m, lambda d: d.sign_state != DS.SIGNED)


def rejected(db: Session, m) -> list:
    return labels_of(db, m, lambda d: d.sign_state == DS.REJECTED)


def last_sent_at(db: Session, m) -> Optional[datetime]:
    """Когда документы пакета последний раз уходили клиенту — от этого считается срок ожидания подписанных."""
    return db.execute(text("""
        SELECT max(e.at) FROM doc_sign_events e
          LEFT JOIN sales_annexes a ON a.id = e.annex_id
          LEFT JOIN master_deal_upds u ON u.id = e.upd_id
         WHERE e.state = 'выставлен' AND (a.master_deal_id = :m OR u.master_deal_id = :m)"""), {"m": m.id}).scalar()


def closed_at(db: Session, m) -> Optional[datetime]:
    """Когда документы пакета закрыты — последний из «подписан», если подписаны все; иначе None."""
    if not state(db, m)["all_signed"]:
        return None
    return db.execute(text("""
        SELECT max(e.at) FROM doc_sign_events e
          LEFT JOIN sales_annexes a ON a.id = e.annex_id
          LEFT JOIN master_deal_upds u ON u.id = e.upd_id
         WHERE e.state = 'подписан' AND (a.master_deal_id = :m OR u.master_deal_id = :m)"""), {"m": m.id}).scalar()


def sync(db: Session, m) -> bool:
    """После отметки документа: все выставлены — пакет из «выставления» уходит в «ждём оплату». True — статус сменился."""
    from app.master_deal.status import ISSUE, WAIT_PAY
    if m.status != ISSUE or not state(db, m)["all_sent"]:
        return False
    m.status, m.updated_at = WAIT_PAY, datetime.utcnow()
    return True


def required_scans(db: Session, m) -> list:
    """Документы пакета, к которым можно приложить скан: каждый ДС (по annex_id) и каждый комплект УПД (по upd_no)."""
    from app.master_deal import to_annex as TA
    numbers = {x["id"]: x["number"] for x in TA.annexes_of(db, m)}
    out = []
    for d in docs(db, m):
        if DS.is_annex(d):
            out.append({"kind": SCAN_DS, "annex_id": d.id, "upd_no": None, "label": numbers.get(d.id) or doc_label(d), "doc": d})
        else:
            out.append({"kind": SCAN_UPD, "annex_id": None, "upd_no": d.upd_no, "label": doc_label(d), "doc": d})
    return out


def find_doc(db: Session, m, annex_id: Optional[int], upd_no: Optional[int]):
    """Документ пакета по ссылке экрана: один ДС (annex_id) или один УПД (upd_no). Чужой или черновик — None."""
    if (annex_id is None) == (upd_no is None):
        return None
    for d in docs(db, m):
        if (DS.is_annex(d) and d.id == annex_id) or (not DS.is_annex(d) and d.upd_no == upd_no):
            return d
    return None


def mark_doc(db: Session, m, doc, state: str, user, reason: Optional[str] = None) -> bool:
    """Отметка подписи документа пакета. УПД — только когда комплекты пришли из 1С («выставление» и дальше): раньше их нет.
    Возвращает True, если пакет от этого сменил статус (все выставлены → «ждём оплату»)."""
    from app.master_deal.status import ISSUE, WAIT_PAY, WAIT_SCANS
    if not DS.is_annex(doc) and m.status not in (ISSUE, WAIT_PAY, WAIT_SCANS):
        raise DS.SignError(409, "УПД выставляют клиенту после получения документов из 1С — на «выставлении»")
    DS.mark(db, doc, state, user, reason=reason)
    db.flush()
    return sync(db, m)
