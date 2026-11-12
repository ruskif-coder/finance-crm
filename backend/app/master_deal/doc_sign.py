# -*- coding: utf-8 -*-
"""Подпись у каждого документа пакета — ДС и УПД (владелец 02.11.2026, миграция 2026-11-02_start_pack_and_doc_sign.sql).

Клиент может отказать в подписи ОДНОГО документа пакета после всех согласований, поэтому отметка «отправлено» на пакете
не говорит, что с каждым документом. Здесь — единственное место, где меняется `sign_state` документа.

  ДС:  выпущен → согласован → (бумага: подписан у нас) → выставлен → подписан | отклонён → выставлен …
  УПД: пришёл из 1С → (бумага: подписан у нас) → выставлен → подписан | отклонён → выставлен …

«Выпущен» ставит подтверждение ДС (`issued`), не человек. Канал (ЭДО / бумага) берётся из договора при первом шаге наружу и
дальше остаётся за документом: ушедший документ не меняет ветку, если у договора потом поменяли признак. Подпись бумаги —
только со сканом. Отказ — только с причиной; переделка документа после отказа в системе пока не строится (владелец 02.11:
«проблемы будущего»): документ переделывают вне системы и выставляют снова с тем же номером.
До подключения Диадока все отметки ставятся руками (`source='вручную'`); потом их будет ставить ЭДО (`source='ЭДО'`)."""
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

ISSUED, AGREED, OURS, SENT, SIGNED, REJECTED = "выпущен", "согласован", "подписан у нас", "выставлен", "подписан", "отклонён"
DS_STATES = (ISSUED, AGREED, OURS, SENT, SIGNED, REJECTED)
UPD_STATES = (OURS, SENT, SIGNED, REJECTED)
EDO, PAPER = "ЭДО", "бумага"
OUT = (SENT, SIGNED)          # документ у клиента — выставлен или уже подписан


class SignError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def is_annex(doc) -> bool:
    return getattr(doc, "__tablename__", None) == "sales_annexes"


def label(doc) -> str:
    if is_annex(doc):
        return getattr(doc, "number", None) or f"ДС id {doc.id}"
    return f"УПД № {doc.upd_no}"


def _contract_channel(db: Session, doc) -> Optional[str]:
    if is_annex(doc):
        return db.execute(text("SELECT issue_channel FROM contracts WHERE id = :c"), {"c": doc.contract_id}).scalar()
    return db.execute(text("""SELECT c.issue_channel FROM master_deals m JOIN contracts c ON c.id = m.contract_id
                               WHERE m.id = :m"""), {"m": doc.master_deal_id}).scalar()


def _scan_id(db: Session, doc) -> Optional[int]:
    if is_annex(doc):
        return db.execute(text("SELECT id FROM master_deal_files WHERE annex_id = :a"), {"a": doc.id}).scalar()
    return db.execute(text("SELECT id FROM master_deal_files WHERE master_deal_id = :m AND upd_no = :u AND kind = 'скан УПД'"),
                      {"m": doc.master_deal_id, "u": doc.upd_no}).scalar()


def _write_event(db: Session, doc, **kw) -> None:
    from app.master_deal.models import DocSignEvent
    db.add(DocSignEvent(annex_id=doc.id if is_annex(doc) else None, upd_id=None if is_annex(doc) else doc.id, **kw))


def _allowed(doc, channel: Optional[str]) -> tuple:
    """Куда можно из текущего состояния документа. Канал нужен только на развилке после «согласован» / прихода из 1С."""
    st = doc.sign_state
    start = AGREED if is_annex(doc) else None
    first_out = (OURS,) if channel == PAPER else (SENT,)
    nxt = {ISSUED: (AGREED,), OURS: (SENT,), SENT: (SIGNED, REJECTED), REJECTED: (SENT,), SIGNED: ()}
    if st == start:
        return first_out
    return nxt.get(st, ())


def _last_sent(db: Session, doc) -> tuple:
    """(когда, кто) последней отметки «выставлен» — плашка «отправлен · 12.11 15:30» в реестре v3."""
    a, u_ = (doc.id, None) if is_annex(doc) else (None, doc.id)
    r = db.execute(text("""SELECT e.at, coalesce(u.name, u.email) FROM doc_sign_events e LEFT JOIN users u ON u.id = e.by_user
                            WHERE (e.annex_id = :a OR e.upd_id = :u) AND e.state = :s ORDER BY e.id DESC LIMIT 1"""),
                   {"a": a, "u": u_, "s": SENT}).first()
    return (r[0].isoformat(timespec="seconds") if r[0] else None, r[1]) if r else (None, None)


def view(db: Session, doc, channel: Optional[str] = None) -> dict:
    """Для экрана: где документ, каким каналом и куда его можно отметить дальше (подпись бумаги — сканом, не кнопкой)."""
    if is_annex(doc) and doc.no is None:
        return {"state": None, "channel": None, "next": []}
    ch = doc.sign_channel or channel or _contract_channel(db, doc)
    nxt = [s for s in _allowed(doc, ch) if not (s == SIGNED and ch == PAPER)]
    sent_at, sent_by = _last_sent(db, doc) if doc.sign_state in (SENT, SIGNED, REJECTED) else (None, None)
    return {"state": doc.sign_state, "channel": doc.sign_channel or ch, "next": nxt,
            "needs_scan": ch == PAPER and doc.sign_state == SENT, "sent_at": sent_at, "sent_by": sent_by}


def mark(db: Session, doc, state: str, user, *, reason: Optional[str] = None, source: str = "вручную") -> object:
    """Перевести документ в `state`. Отказ — SignError с текстом для человека; документ не меняется."""
    if is_annex(doc) and doc.no is None:
        raise SignError(409, "ДС ещё не подтверждён — отметки подписи ставятся после подтверждения")
    if state not in (DS_STATES if is_annex(doc) else UPD_STATES) or state == ISSUED:
        raise SignError(400, f"У этого документа нет шага «{state}»")
    channel = doc.sign_channel or _contract_channel(db, doc)
    if state in (OURS, SENT) and doc.sign_state in ((AGREED,) if is_annex(doc) else (None,)):
        if not channel:
            raise SignError(409, "У договора не задано «Выставление» — ЭДО или бумага. Проставьте его в реестре договоров")
        if channel == PAPER and state == SENT:
            raise SignError(409, "Бумага уходит клиенту подписанной — сначала «подписан у нас»")
    if state not in _allowed(doc, channel):
        raise SignError(409, f"{label(doc)}: из «{doc.sign_state or 'черновик'}» в «{state}» нельзя")
    reason = (reason or "").strip() or None
    if state == REJECTED and not reason:
        raise SignError(400, "Отказ клиента — с причиной: без неё документ не переделать")
    file_id = None
    if state == SIGNED and channel == PAPER:
        file_id = _scan_id(db, doc)
        if not file_id:
            raise SignError(409, "Бумага подписана — приложите скан подписанного документа")
    if state in (OURS, SENT) and not doc.sign_channel:
        doc.sign_channel = channel
    doc.sign_state = state
    # `reason`: у отказа — причина клиента, у отправки бумаги — трек (что ушло и где искать), остальным не нужен.
    _write_event(db, doc, state=state, channel=doc.sign_channel, source=source, reason=reason if state in (REJECTED, SENT) else None,
                 file_id=file_id, by_user=getattr(user, "id", None))
    return doc


def issued(db: Session, doc, user, *, reason: Optional[str] = None) -> None:
    """ДС подтверждён (или пересобран по факту) — «выпущен»; прежний круг подписи не наследуется: текст другой."""
    doc.sign_state, doc.sign_channel = ISSUED, None
    _write_event(db, doc, state=ISSUED, channel=None, source="вручную", reason=reason, file_id=None,
                 by_user=getattr(user, "id", None))


def unsign(db: Session, doc, user, *, reason: str) -> None:
    """Снять подпись бумаги, когда убрали её скан: документ снова «выставлен» — у клиента, подписанного у нас нет."""
    doc.sign_state = SENT
    _write_event(db, doc, state=SENT, channel=doc.sign_channel, source="вручную", reason=reason, file_id=None,
                 by_user=getattr(user, "id", None))


UNSENT = "отправка снята"      # событие, не состояние документа: отметку «выставлен» поставили по ошибке


def unsend(db: Session, doc, user) -> None:
    """Снять ошибочную отметку отправки (реестр v3, 12.11.2026): документ возвращается на шаг, с которого уходил клиенту, —
    бумага к «подписан у нас», ЭДО-ДС к «согласован», ЭДО-УПД — к «пришёл из 1С» (пусто). Подписанный и отклонённый не трогаем:
    это ответ клиента, а не наша ошибка."""
    if doc.sign_state != SENT:
        raise SignError(409, f"{label(doc)}: отменить можно только отметку «выставлен», сейчас — «{doc.sign_state or 'не отправлен'}»")
    doc.sign_state = OURS if doc.sign_channel == PAPER else (AGREED if is_annex(doc) else None)
    _write_event(db, doc, state=UNSENT, channel=doc.sign_channel, source="вручную", reason=None, file_id=None,
                 by_user=getattr(user, "id", None))


def is_signed(doc) -> bool:
    return getattr(doc, "sign_state", None) == SIGNED


def at_client(doc) -> bool:
    """Документ уже ушёл клиенту (выставлен, отклонён, подписан у нас и в пути) — пересобирать его нельзя."""
    return getattr(doc, "sign_state", None) in (OURS, SENT, REJECTED)


def summary(docs: list) -> dict:
    states = [getattr(d, "sign_state", None) for d in docs]
    n = len(states)
    sent = sum(1 for s in states if s in OUT)
    signed = sum(1 for s in states if s == SIGNED)
    return {"total": n, "sent": sent, "signed": signed, "rejected": sum(1 for s in states if s == REJECTED),
            "all_sent": bool(n) and sent == n, "all_signed": bool(n) and signed == n}


def pack_docs(db: Session, m) -> list:
    """Документы пакета, которые уходят клиенту: подтверждённые ДС и все комплекты УПД."""
    from app.master_deal.models import MasterDealUpd
    from app.sales.models import SalesAnnex
    ds = (db.query(SalesAnnex).filter(SalesAnnex.master_deal_id == m.id, SalesAnnex.no.isnot(None))
          .order_by(SalesAnnex.sub_no.isnot(None), SalesAnnex.sub_no, SalesAnnex.id).all())
    upd = db.query(MasterDealUpd).filter(MasterDealUpd.master_deal_id == m.id).order_by(MasterDealUpd.upd_no).all()
    return ds + upd


def history(db: Session, doc) -> list:
    a, u_ = (doc.id, None) if is_annex(doc) else (None, doc.id)
    rows = db.execute(text("""SELECT e.state, e.channel, e.source, e.reason, e.at, coalesce(u.name, u.email) AS who
                               FROM doc_sign_events e LEFT JOIN users u ON u.id = e.by_user
                              WHERE e.annex_id = :a OR e.upd_id = :u ORDER BY e.id"""), {"a": a, "u": u_}).mappings().all()
    return [{**r, "at": r["at"].isoformat(timespec="seconds") if r["at"] else None} for r in rows]
