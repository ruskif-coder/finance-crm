# -*- coding: utf-8 -*-
"""Выставление пакета — вилка ЭДО / бумага (владелец 19.10.2026).

ЭДО, пока интеграции нет: одна отметка «отправлено в ЭДО» — документы закрыты, пакет сразу «ждём оплату». Подпись в ЭДО
придёт вместе с интеграцией Диадока; до неё ожидание подписи и отказы были бы ручной работой без пользы («до подключения
избыточно»).
Бумага: «подписано у нас» → «отправлено» (трек по желанию) → «ждём оплату» → «Оплачено» → «ждём сканы» → архив.
Скан — к КАЖДОМУ документу (владелец 19.10.2026: «скан к документу, ибо надо понимать, что есть что»): к каждому ДС пакета и к
каждому УПД. Один файл — один документ, архивы не принимаются. Документы закрыты, когда сканы есть у всех; убрали любой —
снова открыты. Срок до красного в «ждём сканы» — настройка `company_settings.master_scans_due_days` (по умолчанию 30)."""
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.master_deal.status import ISSUE, WAIT_PAY, StatusError, channel_of, is_paper

PAPER, EDO = "бумага", "ЭДО"
SCAN_DS, SCAN_UPD = "скан ДС", "скан УПД"
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


def required_scans(db: Session, m) -> list:
    """Документы пакета, к которым нужен скан: каждый ДС (по annex_id) и каждый комплект УПД (по upd_no)."""
    ds = db.execute(text("""SELECT id, coalesce(number, '') FROM sales_annexes WHERE master_deal_id = :m
                             ORDER BY sub_no IS NOT NULL, sub_no, id"""), {"m": m.id}).all()
    upd = db.execute(text("SELECT upd_no FROM master_deal_upds WHERE master_deal_id = :m ORDER BY upd_no"), {"m": m.id}).all()
    from app.master_deal import to_annex as TA
    numbers = {x["id"]: x["number"] for x in TA.annexes_of(db, m)}
    return ([{"kind": SCAN_DS, "annex_id": a, "upd_no": None, "label": numbers.get(a) or n or f"ДС id {a}"} for a, n in ds]
            + [{"kind": SCAN_UPD, "annex_id": None, "upd_no": u, "label": f"УПД № {u}"} for (u,) in upd])


def _have(db: Session, m) -> set:
    rows = db.execute(text("SELECT annex_id, upd_no FROM master_deal_files WHERE master_deal_id = :m"), {"m": m.id}).all()
    return {("a", a) for a, _ in rows if a is not None} | {("u", u) for _, u in rows if u is not None}


def missing_scans(db: Session, m) -> list:
    have = _have(db, m)
    return [x["label"] for x in required_scans(db, m)
            if (("a", x["annex_id"]) if x["annex_id"] is not None else ("u", x["upd_no"])) not in have]


def _uid(user) -> Optional[int]:
    return getattr(user, "id", None)


def signed_by_us(db: Session, m, user) -> None:
    if m.status != ISSUE:
        raise StatusError(409, "Отметить подпись можно на «выставлении»")
    if channel_of(db, m) != PAPER:
        raise StatusError(409, "Подпись у нас отмечается только для бумаги — у договора ЭДО")
    if m.signed_by_us_at:
        raise StatusError(409, "Уже отмечено: подписано у нас")
    m.signed_by_us_at, m.signed_by_us_by, m.updated_at = datetime.utcnow(), _uid(user), datetime.utcnow()


def sent(db: Session, m, user, track_no: Optional[str]) -> None:
    """Отправлено клиенту → «ждём оплату». ЭДО закрывает документы сразу, бумага ждёт сканов."""
    if m.status != ISSUE:
        raise StatusError(409, "Отметить отправку можно на «выставлении»")
    # Ветку держит подпись у нас: подписали бумагой, а у договора потом поставили ЭДО — пакет остаётся бумажным (аудит 20.10)
    ch = PAPER if m.signed_by_us_at else channel_of(db, m)
    if not ch:
        raise StatusError(409, "У договора не задано «Выставление» — ЭДО или бумага")
    if m.sent_at:
        raise StatusError(409, "Уже отмечено: отправлено")
    if ch == PAPER and not m.signed_by_us_at:
        raise StatusError(409, "Сначала распечатайте и подпишите у нас — отметка «Подписано у нас»")
    now = datetime.utcnow()
    m.sent_at, m.sent_by = now, _uid(user)
    m.track_no = ((track_no or "").strip() or None) if ch == PAPER else None
    if ch == EDO:
        m.docs_closed_at, m.docs_closed_by = now, _uid(user)
    m.status, m.updated_at = WAIT_PAY, now


def scans_changed(db: Session, m, user) -> None:
    """После загрузки или удаления скана: бумажные документы закрыты, когда сканы есть у КАЖДОГО документа пакета."""
    if not is_paper(db, m):
        return
    full = not missing_scans(db, m)
    if full and not m.docs_closed_at:
        m.docs_closed_at, m.docs_closed_by = datetime.utcnow(), _uid(user)
    elif not full and m.docs_closed_at:
        m.docs_closed_at = m.docs_closed_by = None
    m.updated_at = datetime.utcnow()
