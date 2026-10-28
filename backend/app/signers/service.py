# -*- coding: utf-8 -*-
"""Подписанты (владелец 28.10.2026): у юрлица их несколько, один — по умолчанию; договор выбирает подписанта каждой стороны из списка
её юрлица (заказчик — контрагент договора, исполнитель — наше юрлицо договора). Нет выбора или выбранный ушёл в архив — подписант
юрлица по умолчанию. Срок доверенности (`valid_until`) проверяется на дату документа: истекла — ДС не подтверждается.

Единственный источник подписанта для документов: колонки `counterparties.director_name/signer_position/signer_basis` заморожены
миграцией `2026-10-28_signers.sql`; старые формы, присылающие эти три поля, правят подписанта по умолчанию (`upsert_default`)."""
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.signers.models import ContractSigner, CounterpartySigner

SIDES = ("заказчик", "исполнитель")
FIELDS = ("director_name", "signer_position", "signer_basis", "valid_until")


class SignerError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _clean(data: dict) -> dict:
    out = {}
    for k in FIELDS:
        if k in data:
            v = data[k]
            out[k] = (" ".join(str(v).split()) or None) if isinstance(v, str) else v
    return out


def list_of(db: Session, cp_id: int, archived: bool = False) -> list:
    q = db.query(CounterpartySigner).filter(CounterpartySigner.counterparty_id == cp_id)
    if not archived:
        q = q.filter(CounterpartySigner.is_archived.is_(False))
    return q.order_by(CounterpartySigner.is_default.desc(), CounterpartySigner.is_archived, CounterpartySigner.id).all()


def default_of(db: Session, cp_id: Optional[int]) -> Optional[CounterpartySigner]:
    if not cp_id:
        return None
    return db.query(CounterpartySigner).filter_by(counterparty_id=cp_id, is_default=True).first()


def _get(db: Session, signer_id: int) -> CounterpartySigner:
    s = db.query(CounterpartySigner).filter_by(id=signer_id).with_for_update().first()
    if s is None:
        raise SignerError(404, "Подписант не найден")
    return s


def _touch(s: CounterpartySigner, user) -> None:
    s.updated_at, s.updated_by = func.now(), getattr(user, "id", None)


def create(db: Session, cp_id: int, data: dict, user) -> CounterpartySigner:
    """Новый подписант юрлица; первый у юрлица становится подписантом по умолчанию."""
    vals = _clean(data)
    if not (vals.get("director_name") or "").strip():
        raise SignerError(400, "Укажите ФИО подписанта")
    first = default_of(db, cp_id) is None
    s = CounterpartySigner(counterparty_id=cp_id, is_default=first, updated_by=getattr(user, "id", None), **vals)
    db.add(s)
    db.flush()
    return s


def update(db: Session, signer_id: int, data: dict, user) -> CounterpartySigner:
    s = _get(db, signer_id)
    for k, v in _clean(data).items():
        setattr(s, k, v)
    if not (s.director_name or "").strip():
        raise SignerError(400, "ФИО подписанта не может быть пустым")
    _touch(s, user)
    db.flush()
    return s


def set_default(db: Session, signer_id: int, user) -> CounterpartySigner:
    s = _get(db, signer_id)
    if s.is_archived:
        raise SignerError(409, "Подписант в архиве — сначала верните его из архива")
    db.query(CounterpartySigner).filter(CounterpartySigner.counterparty_id == s.counterparty_id, CounterpartySigner.id != s.id,
                                        CounterpartySigner.is_default.is_(True)).update({"is_default": False})
    db.flush()                       # иначе частичный уникальный индекс «по умолчанию один» споткнётся о прежнего
    s.is_default = True
    _touch(s, user)
    db.flush()
    return s


def archive(db: Session, signer_id: int, on: bool, user) -> CounterpartySigner:
    s = _get(db, signer_id)
    if on and s.is_default:
        raise SignerError(409, "Это подписант по умолчанию — сначала назначьте по умолчанию другого")
    s.is_archived = bool(on)
    _touch(s, user)
    db.flush()
    return s


def side_counterparty(db: Session, contract, side: str):
    """Юрлицо стороны договора: заказчик — контрагент договора, исполнитель — наше юрлицо (договора или единственное)."""
    if side not in SIDES:
        raise SignerError(400, "Сторона — «заказчик» или «исполнитель»")
    if side == "заказчик":
        return contract.counterparty
    from app import own_company
    return contract.own_company or own_company.sole(db)


def choose(db: Session, contract, side: str, signer_id: Optional[int], user) -> Optional[CounterpartySigner]:
    """Подписант стороны договора; `None` — снова по умолчанию юрлица."""
    cp = side_counterparty(db, contract, side)
    row = db.query(ContractSigner).filter_by(contract_id=contract.id, side=side).first()
    if signer_id is None:
        if row is not None:
            db.delete(row)
            db.flush()
        return None
    s = db.query(CounterpartySigner).filter_by(id=signer_id).first()
    if s is None or cp is None or s.counterparty_id != cp.id:
        raise SignerError(400, f"Этот подписант не относится к юрлицу стороны «{side}»")
    if s.is_archived:
        raise SignerError(409, "Подписант в архиве")
    if row is None:
        db.add(ContractSigner(contract_id=contract.id, side=side, signer_id=s.id, updated_by=getattr(user, "id", None)))
    else:
        row.signer_id, row.updated_at, row.updated_by = s.id, func.now(), getattr(user, "id", None)
    db.flush()
    return s


def for_side(db: Session, contract, side: str) -> tuple:
    """(подписант, откуда: «договор» / «по умолчанию») для стороны договора; подписанта нет — (None, None)."""
    row = db.query(ContractSigner).filter_by(contract_id=contract.id, side=side).first() if contract is not None else None
    if row is not None:
        s = db.query(CounterpartySigner).filter_by(id=row.signer_id).first()
        if s is not None and not s.is_archived:
            return s, "договор"
    cp = side_counterparty(db, contract, side) if contract is not None else None
    d = default_of(db, cp.id) if cp is not None else None
    return (d, "по умолчанию") if d else (None, None)


def upsert_default(db: Session, cp, fields: dict, user) -> Optional[CounterpartySigner]:
    """Для форм, которые присылают три поля подписанта контрагента (реквизиты, мобильная карточка, «Добавить»): правят подписанта
    по умолчанию, а нет его — заводят. Все поля пусты и подписанта нет — ничего не делаем."""
    vals = _clean(fields)
    d = default_of(db, cp.id)
    if d is None:
        if not any(vals.get(k) for k in ("director_name", "signer_position", "signer_basis")):
            return None
        d = CounterpartySigner(counterparty_id=cp.id, is_default=True, updated_by=getattr(user, "id", None))
        db.add(d)
    for k, v in vals.items():
        setattr(d, k, v)
    _touch(d, user)
    db.flush()
    return d


def party_of(db: Session, cp, contract=None, side: Optional[str] = None, on: Optional[date] = None) -> dict:
    """Сторона документа (`sales.annex.party`) с подписантом договора для этой стороны, иначе подписантом юрлица по умолчанию."""
    from app.sales.annex import party
    if contract is not None and side:
        signer, _ = for_side(db, contract, side)
    else:
        signer = default_of(db, getattr(cp, "id", None))
    return party(cp, signer, on)
