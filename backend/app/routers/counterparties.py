from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, case
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Counterparty, CounterpartyBankAccount, Operation, Article, Contract, User
from app.routers.auth import get_current_user
from app.permissions import require_permission
from app.audit import log_action
from app.routers.reports import DEFAULT_TERM_DAYS
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter()

class CounterpartyCreate(BaseModel):
    name: str
    vat_rate: float = 0

VALID_STATUSES = {"действующий", "виртуальный"}

class CounterpartyRegistryUpdate(BaseModel):
    name: str
    inn: Optional[str] = None
    status: str
    term_days: Optional[int] = None
    is_own_company: Optional[bool] = None  # только admin меняет через реестр
    # contract_number/contract_date УБРАНЫ (см. models.py): дублировали 1:N таблицу
    # Contract как ложное 1:1 поле. Источник правды теперь Contract.counterparty_id —
    # см. contracts_count в GET /registry ниже.

class CounterpartyBulkUpdate(BaseModel):
    ids: List[int]
    status: Optional[str] = None
    group_override: Optional[str] = None

class CounterpartyBulkDelete(BaseModel):
    ids: List[int]
    password: str

class BankAccountData(BaseModel):
    bank_name: Optional[str] = None
    bank_city: Optional[str] = None
    rs: Optional[str] = None
    ks: Optional[str] = None
    bik: Optional[str] = None

class CounterpartyRequisitesUpdate(BaseModel):
    kpp: Optional[str] = None
    ogrn: Optional[str] = None
    okpo: Optional[str] = None
    address: Optional[str] = None
    address_fact: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    edo_id: Optional[str] = None
    director_name: Optional[str] = None
    note: Optional[str] = None
    bank_accounts: List[BankAccountData] = []

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
        "items": [{"id": c.id, "name": c.name, "vat_rate": c.vat_rate, "status": c.status} for c in items]
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

@router.delete("/bulk")
def bulk_delete_counterparties(
    payload: CounterpartyBulkDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("counterparties", "delete"))
):
    """Массовое удаление контрагентов с подтверждением паролем администратора.
    Отклоняет удаление, если у любого из контрагентов есть связанные операции."""
    from app.routers.auth import verify_password
    if not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(status_code=403, detail="Неверный пароль")
    if not payload.ids:
        raise HTTPException(status_code=400, detail="Не указаны id контрагентов")

    cps = db.query(Counterparty).filter(Counterparty.id.in_(payload.ids)).all()
    if not cps:
        raise HTTPException(status_code=404, detail="Контрагенты не найдены")

    # Запрещаем удаление «своих компаний»
    own = [cp.name for cp in cps if cp.is_own_company]
    if own:
        raise HTTPException(status_code=400,
                            detail=f"Нельзя удалить свои организации: {'; '.join(own)}")

    # Проверяем наличие связанных операций — при их наличии удаление запрещено:
    # FK Operation.counterparty_id не даст сделать это на уровне БД, но лучше
    # дать понятное сообщение заранее, чем поймать IntegrityError.
    blocked = []
    for cp in cps:
        op_count = db.query(func.count(Operation.id)).filter(Operation.counterparty_id == cp.id).scalar() or 0
        if op_count:
            blocked.append(f"«{cp.name}» ({op_count} оп.)")
    if blocked:
        raise HTTPException(
            status_code=400,
            detail=f"Нельзя удалить: у следующих контрагентов есть операции — {'; '.join(blocked)}"
        )

    names = [cp.name for cp in cps]
    for cp in cps:
        db.delete(cp)
    db.commit()

    log_action(db, current_user, "bulk_delete_counterparty", entity_type="counterparty", entity_id=None,
               details=f"Удалено {len(names)} контрагентов: {'; '.join(names)}")
    return {"message": f"Удалено {len(names)} контрагентов"}


@router.delete("/{counterparty_id}")
def delete_counterparty(
    counterparty_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("counterparties", "delete"))
):
    counterparty = db.query(Counterparty).filter(Counterparty.id == counterparty_id).first()
    if not counterparty:
        raise HTTPException(status_code=404, detail="Контрагент не найден")
    if counterparty.is_own_company:
        raise HTTPException(status_code=400, detail="Нельзя удалить свою организацию")
    name = counterparty.name
    db.delete(counterparty)
    db.commit()
    log_action(db, current_user, "delete_counterparty", entity_type="counterparty", entity_id=counterparty_id,
               details=f"Удалён контрагент: {name}")
    return {"message": "Контрагент удалён"}


# ===================== Реестр контрагентов (Настройки → Справочники) =====================
# Отдельные эндпоинты — не трогают /(list)/create/update/delete выше, которые используются
# выпадающим списком на /operations и должны остаться доступны всем с правом на "operations".


@router.get("/own")
def get_own_companies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Список своих юрлиц (is_own_company=True) с банковскими счетами.
    Используется в дропдаунах: остатки по банку, платёжные поручения, договоры.
    Доступен всем аутентифицированным пользователям (не только admin)."""
    cps = (
        db.query(Counterparty)
        .filter(Counterparty.is_own_company == True)
        .order_by(Counterparty.name)
        .all()
    )
    return [
        {
            "id": cp.id,
            "name": cp.name,
            "inn": cp.inn,
            "kpp": cp.kpp,
            "ogrn": cp.ogrn,
            "address": cp.address,
            "bank_accounts": [
                {
                    "id": ba.id,
                    "bank_name": ba.bank_name,
                    "bank_city": ba.bank_city,
                    "rs": ba.rs,
                    "ks": ba.ks,
                    "bik": ba.bik,
                }
                for ba in cp.bank_accounts
            ],
        }
        for cp in cps
    ]


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
            Counterparty.term_days,
            Counterparty.is_own_company,
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
                  Counterparty.term_days, Counterparty.is_own_company)
        .order_by(Counterparty.name)
        .all()
    )

    # Кол-во привязанных договоров (Contract.counterparty_id) — отдельный запрос, как и
    # top_article ниже, чтобы джойн с Contract не размножил строки основного агрегата.
    contract_count_rows = (
        db.query(Contract.counterparty_id, func.count(Contract.id))
        .filter(Contract.counterparty_id.isnot(None))
        .group_by(Contract.counterparty_id)
        .all()
    )
    contracts_count_by_cp = {cid: cnt for cid, cnt in contract_count_rows}

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
                "contracts_count": contracts_count_by_cp.get(r.id, 0),
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
                "is_own_company": bool(r.is_own_company),
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
    if data.term_days != counterparty.term_days:
        changes.append(f"отсрочка: {counterparty.term_days if counterparty.term_days is not None else f'{DEFAULT_TERM_DAYS} (по умолч.)'} → {data.term_days if data.term_days is not None else f'{DEFAULT_TERM_DAYS} (по умолч.)'}")

    counterparty.name = name
    counterparty.inn = new_inn
    counterparty.status = data.status
    # contract_number/contract_date намеренно НЕ трогаются (см. CounterpartyRegistryUpdate
    # выше) — старые значения остаются как историческая заморозка, не перезаписываются в None.
    counterparty.term_days = data.term_days
    if data.is_own_company is not None:
        if not data.is_own_company and counterparty.is_own_company:
            changes.append("is_own_company: Наша → нет")
        elif data.is_own_company and not counterparty.is_own_company:
            changes.append("is_own_company: нет → Наша")
        counterparty.is_own_company = data.is_own_company
    db.commit()

    if changes:
        log_action(db, current_user, "update_counterparty", entity_type="counterparty", entity_id=counterparty.id,
                   details="; ".join(changes))

    return {"message": "Контрагент обновлён"}


# ===================== Карточка контрагента =====================

@router.get("/{counterparty_id}/card")
def get_counterparty_card(
    counterparty_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("counterparties", "view"))
):
    """Полные данные для карточки контрагента: реквизиты, банковские счета,
    договора, агрегаты по операциям."""
    cp = db.query(Counterparty).filter(Counterparty.id == counterparty_id).first()
    if not cp:
        raise HTTPException(status_code=404, detail="Контрагент не найден")

    # Агрегаты по операциям
    stats = (
        db.query(
            func.count(Operation.id).label("op_count"),
            func.coalesce(func.sum(
                case((Operation.status == 'ОПЛАЧЕНО', Operation.income), else_=0)
            ), 0).label("income_paid"),
            func.coalesce(func.sum(
                case((Operation.status == 'ОПЛАЧЕНО', Operation.expense), else_=0)
            ), 0).label("expense_paid"),
            func.coalesce(func.sum(
                case((Operation.status == 'ПЛАН ПОСТУПЛЕНИЙ', Operation.income), else_=0)
            ), 0).label("receivable"),
            func.coalesce(func.sum(
                case((Operation.status == 'ПЛАН ОПЛАТ', Operation.expense), else_=0)
            ), 0).label("payable"),
            func.max(Operation.date).label("last_op_date"),
        )
        .filter(Operation.counterparty_id == counterparty_id)
        .first()
    )

    contracts = (
        db.query(Contract)
        .filter(Contract.counterparty_id == counterparty_id)
        .order_by(Contract.contract_date.desc().nullslast())
        .all()
    )

    bank_accounts = (
        db.query(CounterpartyBankAccount)
        .filter(CounterpartyBankAccount.counterparty_id == counterparty_id)
        .order_by(CounterpartyBankAccount.sort_order)
        .all()
    )

    return {
        "id": cp.id,
        "name": cp.name,
        "inn": cp.inn,
        "kpp": cp.kpp,
        "ogrn": cp.ogrn,
        "okpo": cp.okpo,
        "address": cp.address,
        "address_fact": cp.address_fact,
        "phone": cp.phone,
        "email": cp.email,
        "edo_id": cp.edo_id,
        "director_name": cp.director_name,
        "website": cp.website,
        "note": cp.note,
        "status": cp.status,
        "vat_rate": cp.vat_rate,
        "term_days": cp.term_days,
        "bank_accounts": [
            {
                "id": b.id,
                "bank_name": b.bank_name,
                "bank_city": b.bank_city,
                "rs": b.rs,
                "ks": b.ks,
                "bik": b.bik,
                "sort_order": b.sort_order,
            }
            for b in bank_accounts
        ],
        "contracts": [
            {
                "id": c.id,
                "contract_number": c.contract_number,
                "contract_date": c.contract_date.isoformat() if c.contract_date else None,
                "cooperation_format": c.cooperation_format,
                "prolongation": c.prolongation,
                "payment_term_days": c.payment_term_days,
                "payment_term_condition": c.payment_term_condition,
                "end_date_text": c.end_date_text,
                "note": c.note,
                "document_link": c.document_link,
                "attached_filename": c.attached_filename,
            }
            for c in contracts
        ],
        "stats": {
            "op_count": stats.op_count or 0,
            "income_paid": float(stats.income_paid or 0),
            "expense_paid": float(stats.expense_paid or 0),
            "receivable": float(stats.receivable or 0),
            "payable": float(stats.payable or 0),
            "saldo": float(stats.receivable or 0) - float(stats.payable or 0),
            "last_op_date": stats.last_op_date.isoformat() if stats.last_op_date else None,
        },
    }


@router.get("/{counterparty_id}/analytics")
def get_counterparty_analytics(
    counterparty_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("counterparties", "view"))
):
    """Аналитика для карточки контрагента: оборот по месяцам, топ статей,
    разбивка по статусам операций, средний чек."""
    from sqlalchemy import text

    cp = db.query(Counterparty).filter(Counterparty.id == counterparty_id).first()
    if not cp:
        raise HTTPException(status_code=404, detail="Контрагент не найден")

    # Оборот по месяцам — только YYYY-MM периоды, весь доступный период
    monthly = db.execute(text("""
        SELECT period,
               COALESCE(SUM(income),  0) AS income,
               COALESCE(SUM(expense), 0) AS expense
        FROM operations
        WHERE counterparty_id = :cid
          AND period ~ '^[0-9]{4}-[0-9]{2}$'
        GROUP BY period
        ORDER BY period
    """), {"cid": counterparty_id}).fetchall()

    # Топ-5 статей по суммарному обороту
    top_articles = db.execute(text("""
        SELECT a.name AS article,
               COALESCE(SUM(o.income),  0) AS income,
               COALESCE(SUM(o.expense), 0) AS expense
        FROM operations o
        JOIN articles a ON a.id = o.article_id
        WHERE o.counterparty_id = :cid
        GROUP BY a.name
        ORDER BY (COALESCE(SUM(o.income), 0) + COALESCE(SUM(o.expense), 0)) DESC
        LIMIT 5
    """), {"cid": counterparty_id}).fetchall()

    # Разбивка по статусам операций
    by_status = db.execute(text("""
        SELECT status,
               COUNT(*)               AS cnt,
               COALESCE(SUM(income),  0) AS income,
               COALESCE(SUM(expense), 0) AS expense
        FROM operations
        WHERE counterparty_id = :cid
        GROUP BY status
    """), {"cid": counterparty_id}).fetchall()

    # Средний чек (только ненулевые значения)
    avg_row = db.execute(text("""
        SELECT AVG(NULLIF(income,  0)) AS avg_income,
               AVG(NULLIF(expense, 0)) AS avg_expense
        FROM operations
        WHERE counterparty_id = :cid
    """), {"cid": counterparty_id}).fetchone()

    return {
        "monthly": [
            {"period": r.period, "income": float(r.income), "expense": float(r.expense)}
            for r in monthly
        ],
        "top_articles": [
            {"article": r.article, "income": float(r.income), "expense": float(r.expense)}
            for r in top_articles
        ],
        "by_status": [
            {"status": r.status, "cnt": r.cnt,
             "income": float(r.income), "expense": float(r.expense)}
            for r in by_status
        ],
        "avg_income":  float(avg_row.avg_income  or 0) if avg_row and avg_row.avg_income  else 0,
        "avg_expense": float(avg_row.avg_expense or 0) if avg_row and avg_row.avg_expense else 0,
    }


@router.put("/{counterparty_id}/requisites")
def update_counterparty_requisites(
    counterparty_id: int,
    data: CounterpartyRequisitesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("counterparties", "edit"))
):
    """Сохранение реквизитов контрагента (реквизитные поля + банковские счета).
    Банковские счета перезаписываются целиком — старые удаляются, новые вставляются."""
    cp = db.query(Counterparty).filter(Counterparty.id == counterparty_id).first()
    if not cp:
        raise HTTPException(status_code=404, detail="Контрагент не найден")

    def _s(v): return (v or '').strip() or None

    cp.kpp           = _s(data.kpp)
    cp.ogrn          = _s(data.ogrn)
    cp.okpo          = _s(data.okpo)
    cp.address       = _s(data.address)
    cp.address_fact  = _s(data.address_fact)
    cp.phone         = _s(data.phone)
    cp.email         = _s(data.email)
    cp.edo_id        = _s(data.edo_id)
    cp.director_name = _s(data.director_name)
    cp.website       = _s(data.website)
    cp.note          = _s(data.note)

    # Перезаписываем банковские счета
    db.query(CounterpartyBankAccount).filter(
        CounterpartyBankAccount.counterparty_id == counterparty_id
    ).delete()
    for i, ba in enumerate(data.bank_accounts):
        db.add(CounterpartyBankAccount(
            counterparty_id=counterparty_id,
            bank_name=_s(ba.bank_name),
            bank_city=_s(ba.bank_city),
            rs=_s(ba.rs),
            ks=_s(ba.ks),
            bik=_s(ba.bik),
            sort_order=i,
        ))

    db.commit()
    log_action(db, current_user, "update_counterparty_requisites",
               entity_type="counterparty", entity_id=cp.id,
               details=f"Обновлены реквизиты: «{cp.name}»")
    return {"message": "Реквизиты обновлены"}


# ===================== Справочник БИК ЦБ РФ =====================

@router.get("/bic/{bik}")
def lookup_bic(
    bik: str,
    current_user: User = Depends(get_current_user)
):
    """Запрашивает справочник ЦБ РФ по БИК и возвращает наименование банка,
    город, корреспондентский счёт. Используется для автозаполнения реквизитов."""
    import httpx
    import xml.etree.ElementTree as ET

    bik = bik.strip()
    if not bik.isdigit() or len(bik) != 9:
        raise HTTPException(status_code=400, detail="БИК должен состоять из 9 цифр")

    # Источник 1: bik-info.ru — полные реквизиты (КС, город, наименование), без API-ключа
    bank_name = ""
    bank_city = ""
    ks = ""
    try:
        url1 = f"https://bik-info.ru/api.html?BIK={bik}&TYPE=json"
        r1 = httpx.get(url1, timeout=6.0)
        if r1.status_code == 200:
            d = r1.json()
            bank_name = (d.get("namep") or d.get("name") or "").strip()
            bank_city = (d.get("city") or "").strip().title()
            ks        = (d.get("ks")   or "").strip()
    except Exception:
        pass  # падаем на резервный источник

    # Источник 2: ЦБ РФ (резерв) — только наименование банка
    if not bank_name:
        try:
            import xml.etree.ElementTree as ET
            url2 = f"https://www.cbr.ru/scripts/XML_bic.asp?BIC={bik}"
            r2 = httpx.get(url2, timeout=5.0)
            r2.raise_for_status()
            root = ET.fromstring(r2.content)
            row  = root.find(".//Record") or root.find(".//BICRow")
            if row is not None:
                def _t(p, *tags):
                    for t in tags:
                        el = p.find(t)
                        if el is not None and el.text:
                            return el.text.strip()
                    return ""
                bank_name = _t(row, "ShortName", "NameP") or row.get("NameP", "") or row.get("ShortName", "")
        except Exception:
            pass

    if not bank_name:
        raise HTTPException(status_code=404, detail="БИК не найден")

    return {"bik": bik, "bank_name": bank_name, "bank_city": bank_city, "ks": ks}


# ===================== Операции контрагента =====================

@router.get("/{counterparty_id}/operations")
def get_counterparty_operations(
    counterparty_id: int,
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    sort_col: Optional[str] = "date",
    sort_dir: Optional[str] = "desc",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Операции контрагента. Доступно при наличии operations.view ИЛИ counterparties.view_operations."""
    from app.permissions import get_permissions_for_user
    perms = get_permissions_for_user(db, current_user)
    if not (perms.get("operations", {}).get("view") or perms.get("counterparties", {}).get("view_operations")):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    cp = db.query(Counterparty).filter(Counterparty.id == counterparty_id).first()
    if not cp:
        raise HTTPException(status_code=404, detail="Контрагент не найден")

    query = (
        db.query(Operation)
        .outerjoin(Article, Operation.article_id == Article.id)
        .filter(Operation.counterparty_id == counterparty_id)
    )
    if status:
        query = query.filter(Operation.status == status)

    total = query.count()

    sort_map = {
        "date": Operation.date, "status": Operation.status,
        "income": Operation.income, "expense": Operation.expense,
        "period": Operation.period, "article": Article.name,
    }
    sc = sort_map.get(sort_col, Operation.date)
    query = query.order_by(sc.asc().nulls_first() if sort_dir == "asc" else sc.desc().nulls_first())
    ops = query.offset(skip).limit(limit).all()

    from app.routers.reports import _due_date, _aging_bucket, _term_days_for_counterparty
    from datetime import date as date_type
    today = date_type.today()

    def _recv_status(op):
        if op.status != "ПЛАН ПОСТУПЛЕНИЙ" or not op.income or op.income <= 0:
            return None
        term = _term_days_for_counterparty(cp)
        due = _due_date(op.period, term)
        return _aging_bucket(due, today)

    return {
        "total": total,
        "items": [
            {
                "id": op.id,
                "date": op.date,
                "status": op.status,
                "income": float(op.income or 0),
                "expense": float(op.expense or 0),
                "bank": op.bank,
                "period": op.period,
                "article": op.article.name if op.article else None,
                "article_id": op.article_id,
                "ds_num": op.ds_num,
                "invoice": op.invoice,
                "invoice_date": str(op.invoice_date) if op.invoice_date else None,
                "receivable_status": _recv_status(op),
            }
            for op in ops
        ],
    }