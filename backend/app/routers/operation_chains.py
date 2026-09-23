# -*- coding: utf-8 -*-
"""Частичная оплата, цепочка и принудительное удаление материнской операции.

Монтируется под тот же префикс `/api/operations`, что и реестр операций: адреса для
экрана единые, а код цепочки не раздувает `operations.py` (он и без того на две тысячи
строк). Правила — в `app/operation_chains.py`, решение владельца — 23.09.2026.
"""
from datetime import date as _Date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import operation_chains as chains
from app.audit import log_action
from app.database import get_db
from app.models import Operation, User
from app.passwords import verify_password
from app.permissions import require_permission

router = APIRouter()


def confirm_password(db: Session, user: User, password: Optional[str]) -> None:
    """Пароль своей учётки — для удаления цепочки (одной материнской или целиком).

    Попытки — общим счётчиком со входом: иначе с чужим токеном пароль учётки подбирался
    бы здесь, в обход блокировки `/login` (ревью 23.09.2026). Пять неверных подряд — та
    же блокировка на 15 минут, что и у входа."""
    from app.routers.auth import (_check_login_lockout, _clear_login_attempts, _norm_email,
                                  _register_failed_login)
    email = _norm_email(user.email)
    _check_login_lockout(db, email)
    if not verify_password(password or "", user.hashed_password):
        _register_failed_login(db, email)
        raise HTTPException(status_code=403, detail="Неверный пароль")
    _clear_login_attempts(db, email)


def _load(db: Session, op_id: int, lock: bool = False) -> Operation:
    q = db.query(Operation).filter(Operation.id == op_id)
    op = (q.with_for_update() if lock else q).first()
    if not op:
        raise HTTPException(status_code=404, detail="Операция не найдена")
    return op


def _vat(op) -> None:
    from app.routers.operations import compute_vat_fact
    op.vat_fact = compute_vat_fact(op.income, op.expense, op.vat_rate)


class PartialPaymentIn(BaseModel):
    amount: float
    # Имя поля `date` — через алиас типа: без него аннотация затеняет сама себя (тот же
    # случай разобран у OperationCreate в operations.py).
    date: _Date
    bank: Optional[str] = None


@router.post("/{op_id}/partial-payment")
def partial_payment(op_id: int, body: PartialPaymentIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_permission("operations", "edit")),
                    _creates: User = Depends(require_permission("operations", "create"))):
    """Закрыть часть плановой операции ОДНИМ действием.

    Полученная сумма становится отдельной оплаченной операцией со ссылкой на материнскую,
    у материнской остаётся план на остаток. Раньше это делали руками — копия и правка
    двух сумм, — и ошибка в одной из них была неотличима от настоящего долга.

    Оплата ровно на остаток закрывает саму материнскую: новой части не заводим, иначе
    в цепочке висела бы материнская с нулём — строка, которая ничего не значит.

    Права — ОБА: правка (меняется материнская) и создание (заводится часть). С одним
    «правка» роль без права создавать заводила операции этой кнопкой (ревью 23.09.2026).
    Строка материнской читается под блокировкой: два одновременных запроса иначе видели
    один остаток и делили его дважды — сумма договора росла.
    """
    from app.routers.operations import _assert_operation_valid

    op = _load(db, op_id, lock=True)
    if op.status not in chains.PLAN_STATUSES:
        raise HTTPException(status_code=400,
                            detail="Частичная оплата — только у плановой операции")
    s = chains.side(op)
    if not s:
        raise HTTPException(status_code=400, detail="У операции нет суммы — делить нечего")
    remaining = chains.amount(op)
    amt = round(float(body.amount or 0), 2)
    if amt <= 0:
        raise HTTPException(status_code=400, detail="Сумма оплаты должна быть больше нуля")
    if amt > remaining:
        raise HTTPException(status_code=400,
                            detail=f"Сумма оплаты больше остатка ({remaining:,.2f})".replace(",", " "))
    bank = (body.bank or op.bank or "").strip()
    if not bank:
        raise HTTPException(status_code=400,
                            detail="Укажите банк оплаты: без банка операция выпадет из остатков")

    if amt == remaining:
        op.status, op.date, op.bank = chains.PAID, body.date, bank
        _assert_operation_valid(op)
        db.commit()
        log_action(db, current_user, "partial_payment_operation", entity_type="operation",
                   entity_id=op.id, details=f"остаток {amt} оплачен, цепочка закрыта")
        return {"closed": True, "part_id": None, "remaining": 0}

    part = Operation(
        date=body.date, status=chains.PAID, bank=bank, income=0.0, expense=0.0,
        period=op.period, vat_rate=op.vat_rate, article_id=op.article_id,
        counterparty_id=op.counterparty_id, ds_num=op.ds_num, invoice=op.invoice,
        invoice_date=op.invoice_date, description=op.description,
        document_link=op.document_link, own_company_id=op.own_company_id,
        parent_operation_id=chains.root_id(op), created_by=current_user.id)
    setattr(part, s, amt)
    setattr(op, s, round(remaining - amt, 2))
    _vat(part)
    _vat(op)
    _assert_operation_valid(part)
    _assert_operation_valid(op)
    db.add(part)
    db.commit()
    log_action(db, current_user, "partial_payment_operation", entity_type="operation",
               entity_id=op.id,
               details=f"часть #{part.id} оплачена на {amt}, остаток {getattr(op, s)}")
    return {"closed": False, "part_id": part.id, "remaining": getattr(op, s)}


def _chain_row(op) -> dict:
    return {"id": op.id, "date": op.date, "status": op.status, "bank": op.bank,
            "amount": chains.amount(op)}


@router.get("/{op_id}/chain")
def get_chain(op_id: int, db: Session = Depends(get_db),
              current_user: User = Depends(require_permission("operations", "view"))):
    """Цепочка, в которую входит операция: материнская, её части и итог по договору.

    Спросить можно с любого звена. Сумма договора не хранится — она считается здесь из
    самих операций и потому не расходится с ними.
    """
    op = _load(db, op_id)
    root = _load(db, chains.root_id(op))
    parts = (db.query(Operation).filter(Operation.parent_operation_id == root.id)
             .order_by(Operation.date, Operation.id).all())
    members = [root] + parts
    total = round(sum(chains.amount(m) for m in members), 2)
    paid = round(sum(chains.amount(m) for m in members if m.status == chains.PAID), 2)
    return {"root": _chain_row(root), "parts": [_chain_row(p) for p in parts],
            "total": total, "paid": paid, "remaining": round(total - paid, 2)}


@router.post("/{op_id}/unlink-parent")
def unlink_parent(op_id: int, db: Session = Depends(get_db),
                  current_user: User = Depends(require_permission("operations", "edit"))):
    """Сделать часть самостоятельной — если её связали по ошибке."""
    op = _load(db, op_id)
    was = op.parent_operation_id
    if not was:
        return {"message": "Операция и так самостоятельная"}
    op.parent_operation_id = None
    db.commit()
    log_action(db, current_user, "unlink_operation_parent", entity_type="operation",
               entity_id=op.id, details=f"отвязана от материнской #{was}")
    return {"message": "Операция отвязана"}


class ForceDeleteIn(BaseModel):
    password: str


@router.post("/{op_id}/force-delete")
def force_delete(op_id: int, body: ForceDeleteIn, db: Session = Depends(get_db),
                 current_user: User = Depends(require_permission("operations", "delete"))):
    """Удалить материнскую операцию вместе со связью — только с паролем.

    Пароль проверяется ЗДЕСЬ, а не отдельным запросом перед удалением: проверка на
    стороне экрана обходится прямым вызовом ручки. Части не удаляются — база снимает с
    них ссылку (ON DELETE SET NULL), и они остаются самостоятельными операциями:
    полученные деньги не должны исчезать вместе с планом.
    """
    confirm_password(db, current_user, body.password)
    op = _load(db, op_id)
    part_ids = [r.id for r in db.query(Operation.id)
                .filter(Operation.parent_operation_id == op.id).all()]
    details = (f"{op.status}, доход {op.income}, расход {op.expense}, банк {op.bank}; "
               f"части стали самостоятельными: {part_ids}")
    db.delete(op)
    db.commit()
    log_action(db, current_user, "force_delete_operation", entity_type="operation",
               entity_id=op_id, details=details)
    return {"message": "Операция удалена", "detached_parts": part_ids}
