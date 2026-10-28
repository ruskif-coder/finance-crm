# -*- coding: utf-8 -*-
"""«Юр запросы» (контур Финансы): заявки аккаунтов юристу по пунктам ДС после таблицы МП. Логика — пакет `app/legal`.

Подать заявку — право правки приложений (`annexes.edit`), это делает аккаунт с экрана ДС. Видеть список и закрывать заявки —
право `legal_requests` (роли «Юрист» и, с 28.10.2026, «Мастер аккаунт»)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.annex_tpl import document as tpl_doc
from app.annex_tpl.check import numbering
from app.audit import log_action
from app.database import get_db
from app.notify import legal as N
from app.legal import service as S
from app.legal.models import OPEN, LegalRequest
from app.models import Contract, User
from app.permissions import require_permission
from app.sales.models import SalesAnnex

router = APIRouter()

VIEW = require_permission("legal_requests", "view")
EDIT = require_permission("legal_requests", "edit")
ANNEX_VIEW = require_permission("annexes", "view")
ANNEX_EDIT = require_permission("annexes", "edit")


def _raise(e: S.LegalError):
    raise HTTPException(e.status, e.message)


def _req(db: Session, rid: int) -> LegalRequest:
    r = db.query(LegalRequest).filter(LegalRequest.id == rid).first()
    if not r:
        raise HTTPException(404, "Заявка не найдена")
    return r


def _rebuild_annex_of(db: Session, r: LegalRequest) -> Optional[str]:
    """«Сделано» пересобирает подтверждённое ДС заявки на новой версии шаблона (владелец 14.10.2026: «не пересоздался автоматически»).
    Черновик пересобирать не нужно — он и так собирается по текущей версии. Не собралось (неполон документ, ушло в 1С) — заявка всё равно
    закрывается: правка юриста в шаблоне уже есть, а пересоздать можно кнопкой; причина — в ответе и журнале."""
    from app.routers import annexes as A          # роутер ДС импортирует пакет `legal` — здесь лениво, чтобы не замкнуть импорт
    a = db.query(SalesAnnex).filter(SalesAnnex.id == r.annex_id).first()
    if not a or a.no is None or not tpl_doc.is_frozen(a):
        return None
    if A._sent_to_onec(a):
        return "ДС уже ушло в 1С — не пересоздано"
    try:
        A.rebuild_frozen(db, a, db.query(Contract).filter(Contract.id == a.contract_id).first())
    except HTTPException as e:
        return f"ДС не пересоздано: {e.detail}"
    return f"{a.number} пересоздано на новом шаблоне"


def _contract_no(db: Session, r: LegalRequest) -> Optional[str]:
    c = db.query(Contract).filter(Contract.id == r.contract_id).first()
    return c.contract_number if c else None


def _blocks_of(db: Session, contract, annex=None) -> list:
    version, _ = tpl_doc.resolve(db, contract, annex)
    return version.blocks if version else []


def _block_label(blocks: list, block_id: Optional[str]) -> str:
    if not block_id:
        return "новый пункт"
    num = numbering(blocks)
    b = next((x for x in blocks if x.get("id") == block_id), None)
    return f"Пункт {num.get(block_id, '')} {b.get('title') or ''}".strip() if b else f"пункт {block_id} (нет в текущем шаблоне)"


def _out(db: Session, rows: list) -> list:
    users = {u.id: u.name for u in db.query(User).filter(User.id.in_(
        {x for r in rows for x in (r.created_by, r.taken_by, r.closed_by) if x})).all()} if rows else {}
    contracts = {c.id: c for c in db.query(Contract).filter(Contract.id.in_({r.contract_id for r in rows})).all()} if rows else {}
    annexes = {a.id: a for a in db.query(SalesAnnex).filter(SalesAnnex.id.in_({r.annex_id for r in rows})).all()} if rows else {}
    blocks = {r.id: _blocks_of(db, contracts[r.contract_id], annexes.get(r.annex_id)) for r in rows if r.contract_id in contracts}
    # Шаблон, по которому собирается ДС заявки: «Шаблон ДС» из заявки открывает именно его (у договора их несколько, 27.10.2026).
    picked = {r.id: tpl_doc.pick(db, contracts[r.contract_id], annexes.get(r.annex_id))["template"] for r in rows if r.contract_id in contracts}
    out = []
    for r in rows:
        c, a = contracts.get(r.contract_id), annexes.get(r.annex_id)
        out.append({
            "id": r.id, "status": r.status, "text": r.text, "answer": r.answer, "block_id": r.block_id,
            "block": _block_label(blocks.get(r.id, []), r.block_id),
            "annex_id": r.annex_id, "annex_number": (a.number if a else None) or f"черновик #{r.annex_id}",
            "period_from": a.period_from if a else None, "period_to": a.period_to if a else None,
            "contract_id": r.contract_id, "contract_number": c.contract_number if c else None,
            "counterparty": c.counterparty_name if c else None,
            "contract_format": getattr(c, "cooperation_format", None) if c else None,
            "created_by": users.get(r.created_by), "created_at": r.created_at,
            "taken_by": users.get(r.taken_by), "taken_at": r.taken_at,
            "closed_by": users.get(r.closed_by), "closed_at": r.closed_at,
            "result_version_id": r.result_version_id,
            "template_id": picked[r.id].id if picked.get(r.id) else None,
        })
    return out


@router.get("")
def list_requests(status: str = "open", db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Список для юриста: `open` — открытые и в работе (по умолчанию), `all` — все, новые сверху."""
    q = db.query(LegalRequest)
    if status == "open":
        q = q.filter(LegalRequest.status.in_(OPEN))
    return _out(db, q.order_by(LegalRequest.id.desc()).limit(500).all())


@router.get("/annex/{annex_id}")
def of_annex(annex_id: int, db: Session = Depends(get_db), user: User = Depends(ANNEX_VIEW)):
    """Заявки одного ДС — для экрана приложения: что открыто и что ответил юрист."""
    from app.sales.scope import annex_in_scope
    a = db.query(SalesAnnex).filter(SalesAnnex.id == annex_id).first()
    if not a:
        raise HTTPException(404, "Приложение не найдено")
    annex_in_scope(db, user, a)                     # переписка по чужому ДС не читается (аудит 21.10.2026)
    return _out(db, db.query(LegalRequest).filter(LegalRequest.annex_id == annex_id).order_by(LegalRequest.id.desc()).all())


class CreateIn(BaseModel):
    annex_id: int
    block_id: Optional[str] = None
    text: str


@router.post("", status_code=201)
def create(payload: CreateIn, db: Session = Depends(get_db), user: User = Depends(ANNEX_EDIT)):
    a = db.query(SalesAnnex).filter(SalesAnnex.id == payload.annex_id).first()
    if not a:
        raise HTTPException(404, "Приложение не найдено")
    from app.sales.scope import annex_in_scope
    annex_in_scope(db, user, a)                     # заявкой блокируется выпуск ДС — только по своему (аудит 21.10.2026)
    c = db.query(Contract).filter(Contract.id == a.contract_id).first()
    try:
        r = S.create(db, a, _blocks_of(db, c, a), payload.block_id, payload.text, user)
    except S.LegalError as e:
        _raise(e)
    db.commit()
    log_action(db, user, "legal_request_create", "contract", c.id, f"#{r.id} по ДС #{a.id}: {r.text[:200]}")
    N.new(db, r, c.contract_number, user)
    db.commit()
    return _out(db, [r])[0]


class AnswerIn(BaseModel):
    answer: Optional[str] = None


@router.post("/{rid}/take")
def take(rid: int, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    r = _req(db, rid)
    try:
        S.take(r, user)
    except S.LegalError as e:
        _raise(e)
    db.commit()
    log_action(db, user, "legal_request_take", "contract", r.contract_id, f"#{r.id}")
    N.taken(db, r, _contract_no(db, r), user)
    db.commit()
    return _out(db, [r])[0]


@router.post("/{rid}/done")
def done(rid: int, payload: AnswerIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    r = _req(db, rid)
    try:
        S.done(db, r, user, payload.answer)
    except S.LegalError as e:
        _raise(e)
    rebuilt = _rebuild_annex_of(db, r)
    db.commit()
    log_action(db, user, "legal_request_done", "contract", r.contract_id, f"#{r.id}: версия шаблона {r.result_version_id}" + (f"; {rebuilt}" if rebuilt else ""))
    N.closed(db, r, _contract_no(db, r), user)
    db.commit()
    return {**_out(db, [r])[0], "rebuilt": rebuilt}


@router.post("/{rid}/reject")
def reject(rid: int, payload: AnswerIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    r = _req(db, rid)
    try:
        S.reject(r, user, payload.answer)
    except S.LegalError as e:
        _raise(e)
    db.commit()
    log_action(db, user, "legal_request_reject", "contract", r.contract_id, f"#{r.id}: {r.answer[:200]}")
    N.closed(db, r, _contract_no(db, r), user)
    db.commit()
    return _out(db, [r])[0]
