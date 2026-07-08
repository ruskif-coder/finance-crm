from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import get_db
from app.routers.auth import get_current_user
from app.models import User, Operation
from app.permissions import require_permission
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

BANKS = ['АльфаБанк', 'ОПТ Банк', 'Совкомбанк', 'Наличные']

class BankBalanceUpdate(BaseModel):
    bank: str
    opening_balance: float

class CompanyRequisitesUpdate(BaseModel):
    bank: str
    company_name: Optional[str] = None
    inn: Optional[str] = None
    kpp: Optional[str] = None
    rs: Optional[str] = None
    bik: Optional[str] = None
    bank_full_name: Optional[str] = None
    bank_city: Optional[str] = None
    ks: Optional[str] = None

@router.get("/bank-balances")
def get_bank_balances(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("settings_balances", "view"))
):
    # Стартовые остатки + реквизиты компании
    rows = db.execute(text("""
        SELECT bank, opening_balance,
               company_name, inn, kpp, rs, bik, bank_full_name, bank_city, ks
        FROM bank_balances ORDER BY bank
    """)).fetchall()
    opening = {r.bank: r.opening_balance for r in rows}

    # Обороты из операций
    ops = db.query(
        Operation.bank,
        func.sum(Operation.income).label("income"),
        func.sum(Operation.expense).label("expense"),
    ).filter(Operation.status == 'ОПЛАЧЕНО').group_by(Operation.bank).all()

    turnover = {r.bank: {'income': r.income or 0, 'expense': r.expense or 0} for r in ops}

    # Реквизиты компании по банкам
    req_map = {r.bank: r for r in rows}

    result = []
    total_balance = 0
    for bank in BANKS:
        ob = opening.get(bank, 0)
        inc = turnover.get(bank, {}).get('income', 0)
        exp = turnover.get(bank, {}).get('expense', 0)
        balance = ob + inc - exp
        total_balance += balance
        rq = req_map.get(bank)
        result.append({
            'bank': bank,
            'opening_balance': ob,
            'total_income': inc,
            'total_expense': exp,
            'balance': balance,
            # реквизиты нашей компании для этого банка (используются в экспорте платёжек)
            'company_name': rq.company_name if rq else None,
            'inn': rq.inn if rq else None,
            'kpp': rq.kpp if rq else None,
            'rs': rq.rs if rq else None,
            'bik': rq.bik if rq else None,
            'bank_full_name': rq.bank_full_name if rq else None,
            'bank_city': rq.bank_city if rq else None,
            'ks': rq.ks if rq else None,
        })

    return {'banks': result, 'total_balance': total_balance}

@router.post("/bank-balances")
def update_bank_balance(
    data: BankBalanceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("settings_balances", "edit"))
):
    db.execute(text(
        "UPDATE bank_balances SET opening_balance = :balance, updated_at = NOW() WHERE bank = :bank"
    ), {'balance': data.opening_balance, 'bank': data.bank})
    db.commit()
    return {"message": "Остаток обновлён"}


@router.put("/company-requisites")
def update_company_requisites(
    data: CompanyRequisitesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("settings_balances", "edit"))
):
    """Сохраняет реквизиты компании-плательщика для выбранного банка.
    Эти данные используются при экспорте платёжных поручений в Альфа-Банк."""
    if data.bank not in BANKS:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Неизвестный банк: {data.bank}")

    db.execute(text("""
        UPDATE bank_balances
        SET company_name  = :company_name,
            inn           = :inn,
            kpp           = :kpp,
            rs            = :rs,
            bik           = :bik,
            bank_full_name = :bank_full_name,
            bank_city     = :bank_city,
            ks            = :ks
        WHERE bank = :bank
    """), {
        'company_name':   (data.company_name  or '').strip() or None,
        'inn':            (data.inn           or '').strip() or None,
        'kpp':            (data.kpp           or '').strip() or None,
        'rs':             (data.rs            or '').strip() or None,
        'bik':            (data.bik           or '').strip() or None,
        'bank_full_name': (data.bank_full_name or '').strip() or None,
        'bank_city':      (data.bank_city     or '').strip() or None,
        'ks':             (data.ks            or '').strip() or None,
        'bank':           data.bank,
    })
    db.commit()
    return {"message": "Реквизиты компании сохранены"}
