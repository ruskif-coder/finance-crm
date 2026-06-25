from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, case
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Counterparty, Operation, Article, User
from app.routers.auth import get_current_user
from app.permissions import require_permission
from app.audit import log_action
from app.routers.reports import DEFAULT_TERM_DAYS
from pydantic import BaseModel
from typing import Optional, List
from datetime import date

router = APIRouter()

class CounterpartyCreate(BaseModel):
    name: str
    vat_rate: float = 0

VALID_STATUSES = {"действующий", "виртуальный"}

class CounterpartyRegistryUpdate(BaseModel):
    name: str
    inn: Optional[str] = None
    status: str
    contract_number: Optional[str] = None
    contract_date: Optional[date] = None
    term_days: Optional[int] = None

class CounterpartyBulkUpdate(BaseModel):
    ids: List[int]
    status: Optional[str] = None
    group_override: Optional[str] = None

@router.get("/")
def get_counterparties(
    skip: int = 0,
    limit: int = 200,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Counterparty)
    if search:
        query = query.filter(Counterparty.name.ilike(f"%{search}%"))
    total = query.count()
    items = query.offset(skip).limit(limit).all()
    return {
        "total": total,
        "items": [{"id": c.id, "name": c.name, "vat_rate": c.vat_rate} for c in items]
    }

@router.post("/")
def create_counterparty(
    data: CounterpartyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    existing = db.query(Counterparty).filter(Counterparty.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Контрагент уже существует")
    counterparty = Counterparty(**data.dict())
    db.add(counterparty)
    db.commit()
    db.refresh(counterparty)
    return {"id": counterparty.id, "message": "Контрагент создан"}

@router.put("/{counterparty_id}")
def update_counterparty(
    counterparty_id: int,
    data: CounterpartyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    counterparty = db.query(Counterparty).filter(Counterparty.id == counterparty_id).first()
    if not counterparty:
        raise HTTPException(status_code=404, detail="Контрагент не найден")
    counterparty.name = data.name
    counterparty.vat_rate = data.vat_rate
    db.commit()
    return {"message": "Контрагент обновлён"}

@router.delete("/{counterparty_id}")
def delete_counterparty(
    counterparty_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("counterparties", "delete"))
):
    counterparty = db.query(Counterparty).filter(Counterparty.id == counterparty_id).first()
    if not counterparty:
        raise HTTPException(status_code=404, detail="Контрагент не найден")
    name = counterparty.name
    db.delete(counterparty)
    db.commit()
    log_action(db, current_user, "delete_counterparty", entity_type="counterparty", entity_id=counterparty_id,
               details=f"Удалён контрагент: {name}")
    return {"message": "Контрагент удалён"}


# ===================== Реестр контрагентов (Настройки → Справочники) =====================
# Отдельные эндпоинты — не трогают /(list)/create/update/delete выше, которые используются
# выпадающим списком на /operations и должны остаться доступны всем с правом на "operations".

@router.get("/registry")
def get_counterparties_registry(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("counterparties", "view"))
):
    # Основной агрегат по контрагенту. Условные суммы (case) считаются прямо в БД —
    # это безопасно (не размножает строки), в отличие от джойна со статьями ниже.
    rows = (
        db.query(
            Counterparty.id,
            Counterparty.name,
            Counterparty.inn,
            Counterparty.status,
            Counterparty.group_override,
            Counterparty.contract_number,
            Counterparty.contract_date,
            Counterparty.term_days,
            func.count(Operation.id).label("op_count"),
            # Поступления/выплаты по факту (статус "ОПЛАЧЕНО")
            func.coalesce(func.sum(case((Operation.status == 'ОПЛАЧЕНО', Operation.income), else_=0)), 0).label("income_paid"),
            func.coalesce(func.sum(case((Operation.status == 'ОПЛАЧЕНО', Operation.expense), else_=0)), 0).label("expense_paid"),
            # Дебиторка (план поступлений) / кредиторка (план оплат)
            func.coalesce(func.sum(case((Operation.status == 'ПЛАН ПОСТУПЛЕНИЙ', Operation.income), else_=0)), 0).label("receivable"),
            func.coalesce(func.sum(case((Operation.status == 'ПЛАН ОПЛАТ', Operation.expense), else_=0)), 0).label("payable"),
            # Суммы по всем операциям независимо от статуса — для определения роли (заказчик/поставщик/смешенный)
            func.coalesce(func.sum(Operation.income), 0).label("total_income_all"),
            func.coalesce(func.sum(Operation.expense), 0).label("total_expense_all"),
            func.max(Operation.date).label("last_op_date"),
        )
        .outerjoin(Operation, Operation.counterparty_id == Counterparty.id)
        .group_by(Counterparty.id, Counterparty.name, Counterparty.inn, Counterparty.status, Counterparty.group_override,
                  Counterparty.contract_number, Counterparty.contract_date, Counterparty.term_days)
        .order_by(Counterparty.name)
        .all()
    )

    # Группа (колонка): если у контрагента вручную задан group_override — показываем его,
    # иначе — самая частая КОНКРЕТНАЯ статья среди операций контрагента, без группировки
    # по категории — например, для «Ай-Гуру ООО» это будет «Реализация», а не группа статьи.
    # Отдельный запрос — джойн со статьями в основном агрегате размножил бы строки и испортил суммы.
    article_rows = (
        db.query(Operation.counterparty_id, Article.name, func.count(Operation.id).label("cnt"))
        .join(Article, Article.id == Operation.article_id)
        .filter(Operation.counterparty_id.isnot(None))
        .group_by(Operation.counterparty_id, Article.name)
        .all()
    )
    top_article = {}
    for cid, article_name, cnt in article_rows:
        best = top_article.get(cid)
        if best is None or cnt > best[1]:
            top_article[cid] = (article_name, cnt)

    def classify(total_income, total_expense):
        has_income = (total_income or 0) > 0
        has_expense = (total_expense or 0) > 0
        if has_income and has_expense:
            return "смешенный"
        if has_expense:
            return "поставщик"
        if has_income:
            return "заказчик"
        return None

    return {
        "items": [
            {
                "id": r.id,
                "name": r.name,
                "inn": r.inn,
                "contract_number": r.contract_number,
                "contract_date": r.contract_date.isoformat() if r.contract_date else None,
                "term_days": r.term_days,
                "term_days_effective": r.term_days if r.term_days is not None else DEFAULT_TERM_DAYS,
                "term_days_is_default": r.term_days is None,
                "status": r.status,
                "relation": classify(r.total_income_all, r.total_expense_all),
                "group": r.group_override or top_article.get(r.id, (None, 0))[0],
                "group_is_override": bool(r.group_override),
                "op_count": r.op_count,
                "receivable": float(r.receivable or 0),
                "payable": float(r.payable or 0),
                "income_paid": float(r.income_paid or 0),
                "expense_paid": float(r.expense_paid or 0),
                "diff": float(r.income_paid or 0) - float(r.expense_paid or 0),
                "last_op_date": r.last_op_date.isoformat() if r.last_op_date else None,
            }
            for r in rows
        ]
    }


@router.patch("/bulk")
def bulk_update_counterparties(
    payload: CounterpartyBulkUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("counterparties", "edit"))
):
    """Массовое изменение Вида и/или Группы у списка контрагентов одним запросом —
    по аналогии с PATCH /operations/bulk. Меняются только явно переданные поля
    (exclude_unset), остальные поля затронутых контрагентов не трогаются."""
    if not payload.ids:
        raise HTTPException(status_code=400, detail="Не указаны id контрагентов")

    fields = payload.dict(exclude={"ids"}, exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="Не указаны поля для изменения")

    if "status" in fields and fields["status"] not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Статус должен быть «действующий» или «виртуальный»")

    # Пустая строка для group_override = сбросить вручную заданную группу и вернуться
    # к автоматическому вычислению самой частой статьи.
    if "group_override" in fields and fields["group_override"] == "":
        fields["group_override"] = None

    counterparties = db.query(Counterparty).filter(Counterparty.id.in_(payload.ids)).all()
    if not counterparties:
        raise HTTPException(status_code=404, detail="Контрагенты не найдены")

    for cp in counterparties:
        for key, value in fields.items():
            setattr(cp, key, value)
    db.commit()

    changed_desc = ", ".join(f"{k}={v}" for k, v in fields.items())
    log_action(db, current_user, "bulk_update_counterparty", entity_type="counterparty", entity_id=None,
               details=f"ids={payload.ids}; {changed_desc}")

    return {"message": f"Обновлено {len(counterparties)} контрагентов", "updated": len(counterparties)}


@router.put("/{counterparty_id}/registry")
def update_counterparty_registry(
    counterparty_id: int,
    data: CounterpartyRegistryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("counterparties", "edit"))
):
    counterparty = db.query(Counterparty).filter(Counterparty.id == counterparty_id).first()
    if not counterparty:
        raise HTTPException(status_code=404, detail="Контрагент не найден")

    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название не может быть пустым")
    if data.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Статус должен быть «действующий» или «виртуальный»")
    if data.term_days is not None and data.term_days < 0:
        raise HTTPException(status_code=400, detail="Отсрочка не может быть отрицательной")

    if name != counterparty.name:
        dup = db.query(Counterparty).filter(Counterparty.name == name, Counterparty.id != counterparty_id).first()
        if dup:
            raise HTTPException(
                status_code=400,
                detail=f"Контрагент с названием «{name}» уже существует (ID {dup.id}) — объединение дублей через этот реестр пока не поддерживается"
            )

    changes = []
    if name != counterparty.name:
        changes.append(f"название: {counterparty.name} → {name}")
    new_inn = (data.inn or "").strip() or None
    if new_inn != counterparty.inn:
        changes.append(f"ИНН: {counterparty.inn or '—'} → {new_inn or '—'}")
    if data.status != counterparty.status:
        changes.append(f"статус: {counterparty.status} → {data.status}")
    if data.contract_number != counterparty.contract_number:
        changes.append(f"№ договора: {counterparty.contract_number or '—'} → {data.contract_number or '—'}")
    if data.contract_date != counterparty.contract_date:
        changes.append(f"дата договора: {counterparty.contract_date or '—'} → {data.contract_date or '—'}")
    if data.term_days != counterparty.term_days:
        changes.append(f"отсрочка: {counterparty.term_days if counterparty.term_days is not None else f'{DEFAULT_TERM_DAYS} (по умолч.)'} → {data.term_days if data.term_days is not None else f'{DEFAULT_TERM_DAYS} (по умолч.)'}")

    counterparty.name = name
    counterparty.inn = new_inn
    counterparty.status = data.status
    counterparty.contract_number = (data.contract_number or "").strip() or None
    counterparty.contract_date = data.contract_date
    counterparty.term_days = data.term_days
    db.commit()

    if changes:
        log_action(db, current_user, "update_counterparty", entity_type="counterparty", entity_id=counterparty.id,
                   details="; ".join(changes))

    return {"message": "Контрагент обновлён"}