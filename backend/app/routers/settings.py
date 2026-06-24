from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import get_db
from app.routers.auth import get_current_user
from app.models import User, Operation
from app.permissions import require_permission
from sqlalchemy import func
from pydantic import BaseModel

router = APIRouter()

BANKS = ['АльфаБанк', 'ОПТ Банк', 'Совкомбанк', 'Наличные']

class BankBalanceUpdate(BaseModel):
    bank: str
    opening_balance: float

@router.get("/bank-balances")
def get_bank_balances(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("settings_balances", "view"))
):
    # Стартовые остатки
    rows = db.execute(text("SELECT bank, opening_balance FROM bank_balances ORDER BY bank")).fetchall()
    opening = {r.bank: r.opening_balance for r in rows}

    # Обороты из операций
    ops = db.query(
        Operation.bank,
        func.sum(Operation.income).label("income"),
        func.sum(Operation.expense).label("expense"),
    ).filter(Operation.status == 'ОПЛАЧЕНО').group_by(Operation.bank).all()

    turnover = {r.bank: {'income': r.income or 0, 'expense': r.expense or 0} for r in ops}

    result = []
    total_balance = 0
    for bank in BANKS:
        ob = opening.get(bank, 0)
        inc = turnover.get(bank, {}).get('income', 0)
        exp = turnover.get(bank, {}).get('expense', 0)
        balance = ob + inc - exp
        total_balance += balance
        result.append({
            'bank': bank,
            'opening_balance': ob,
            'total_income': inc,
            'total_expense': exp,
            'balance': balance,
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
