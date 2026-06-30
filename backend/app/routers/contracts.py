from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Contract, Counterparty, User
from app.permissions import require_permission
from app.audit import log_action
from pydantic import BaseModel
from typing import List, Optional
from datetime import date

router = APIRouter()


# ===================== Реестр договоров (Настройки → Справочники) =====================
# Counterparty — единый источник данных для всех полей "контрагент" в системе (см.
# CLAUDE.md). Contract.counterparty_id — FK на Counterparty; при создании договора
# обязателен (см. create_contract), при редактировании может оставаться NULL для
# исторических строк, ещё не сопоставленных с реестром (см.
# link_contracts_to_counterparties.py). Когда counterparty_id указан,
# counterparty_name/inn — это денормализованный снимок, который сервер ВСЕГДА
# перезаписывает из канонической записи Counterparty (см. _resolve_counterparty) —
# клиентский свободный текст в этих полях для привязанных строк игнорируется.
# Для НЕпривязанных строк (counterparty_id is None) counterparty_name/inn остаются
# обычным свободным текстом, как было раньше.

class ContractCreate(BaseModel):
    contract_number: Optional[str] = None
    contract_date: Optional[date] = None
    inn: Optional[str] = None
    counterparty_id: Optional[int] = None
    counterparty_name: Optional[str] = None
    marketing_name: Optional[str] = None
    cooperation_format: Optional[str] = None
    services: Optional[str] = None
    end_date_text: Optional[str] = None
    prolongation: Optional[str] = None
    payment_form: Optional[str] = None
    payment_term_days: Optional[int] = None
    payment_term_condition: Optional[str] = None
    note: Optional[str] = None


# Списки для выпадающих списков на фронте (settings.js) — здесь НЕ валидируются
# строго (Pydantic Literal), чтобы не сломать сохранение старых строк, чьи
# значения cooperation_format/prolongation не входят в текущий список (см.
# CLAUDE.md: то же решение принято для vat_rate/VAT_OPTIONS). Ограничение —
# только на фронте через <select>.
class ContractBulkUpdate(BaseModel):
    ids: List[int]
    cooperation_format: Optional[str] = None
    prolongation: Optional[str] = None
    payment_term_days: Optional[int] = None
    payment_term_condition: Optional[str] = None


def _clean(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = s.strip()
    return s or None


def _resolve_counterparty(db: Session, counterparty_id: Optional[int]) -> Optional[Counterparty]:
    if not counterparty_id:
        return None
    cp = db.query(Counterparty).filter(Counterparty.id == counterparty_id).first()
    if not cp:
        raise HTTPException(status_code=400, detail="Контрагент не найден в реестре контрагентов")
    return cp


def _serialize(c: Contract) -> dict:
    return {
        "id": c.id,
        "contract_number": c.contract_number,
        "contract_date": c.contract_date.isoformat() if c.contract_date else None,
        "inn": c.inn,
        "counterparty_id": c.counterparty_id,
        "counterparty_name": c.counterparty_name,
        "linked": c.counterparty_id is not None,
        "marketing_name": c.marketing_name,
        "cooperation_format": c.cooperation_format,
        "services": c.services,
        "end_date_text": c.end_date_text,
        "prolongation": c.prolongation,
        "payment_form": c.payment_form,
        "payment_term_days": c.payment_term_days,
        "payment_term_condition": c.payment_term_condition,
        "payment_term_legacy": c.payment_term,  # старое текстовое поле — только для справки, не редактируется
        "note": c.note,
    }


@router.get("/registry")
def get_contracts_registry(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contracts", "view"))
):
    items = db.query(Contract).order_by(Contract.contract_date.desc().nullslast(), Contract.id.desc()).all()
    return {"items": [_serialize(c) for c in items]}


@router.patch("/bulk")
def bulk_update_contracts(
    payload: ContractBulkUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contracts", "edit"))
):
    if not payload.ids:
        raise HTTPException(status_code=400, detail="Не выбраны договоры")

    fields = payload.dict(exclude={"ids"}, exclude_unset=True)
    if "cooperation_format" in fields:
        fields["cooperation_format"] = _clean(fields["cooperation_format"])
    if "prolongation" in fields:
        fields["prolongation"] = _clean(fields["prolongation"])
    if "payment_term_condition" in fields:
        fields["payment_term_condition"] = _clean(fields["payment_term_condition"])
    if not fields:
        raise HTTPException(status_code=400, detail="Не указаны поля для изменения")

    contracts = db.query(Contract).filter(Contract.id.in_(payload.ids)).all()
    if not contracts:
        raise HTTPException(status_code=404, detail="Договоры не найдены")

    for c in contracts:
        for key, value in fields.items():
            setattr(c, key, value)
    db.commit()

    labels = {
        "cooperation_format": "формат сотрудничества", "prolongation": "пролонгация",
        "payment_term_days": "срок оплаты, дни", "payment_term_condition": "условие",
    }
    changes_str = "; ".join(f"{labels[k]} → {v or '—'}" for k, v in fields.items())
    ids_str = ", ".join(str(c.id) for c in contracts)
    log_action(db, current_user, "bulk_update_contract", entity_type="contract", entity_id=None,
               details=f"Массовое изменение договоров [{ids_str}]: {changes_str}")
    return {"message": f"Обновлено договоров: {len(contracts)}"}


class ContractBulkDelete(BaseModel):
    ids: List[int]


@router.delete("/bulk")
def bulk_delete_contracts(
    payload: ContractBulkDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contracts", "edit"))
):
    # Массовое удаление — отдельно от точечного DELETE /{id} (которое разрешено любому
    # с правом "edit" на раздел) — здесь дополнительно жёстко требуем роль admin, по
    # запросу пользователя: массовое удаление договоров — это admin-only операция.
    if current_user.role.key != "admin":
        raise HTTPException(status_code=403, detail="Массовое удаление договоров доступно только администратору")
    if not payload.ids:
        raise HTTPException(status_code=400, detail="Не выбраны договоры")

    contracts = db.query(Contract).filter(Contract.id.in_(payload.ids)).all()
    if not contracts:
        raise HTTPException(status_code=404, detail="Договоры не найдены")

    labels_str = "; ".join(f"{c.contract_number or '—'} ({c.counterparty_name or '—'})" for c in contracts)
    ids_str = ", ".join(str(c.id) for c in contracts)
    count = len(contracts)
    for c in contracts:
        db.delete(c)
    db.commit()

    log_action(db, current_user, "bulk_delete_contract", entity_type="contract", entity_id=None,
               details=f"Массовое удаление договоров [{ids_str}]: {labels_str}")
    return {"message": f"Удалено договоров: {count}"}


@router.post("/")
def create_contract(
    data: ContractCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contracts", "edit"))
):
    # Контрагент обязателен при создании НОВОГО договора — единый источник данных
    # (см. CLAUDE.md), никаких новых свободно-текстовых контрагентов через эту форму.
    # Проверка здесь, а не Pydantic-полем Field(...), т.к. ContractCreate общая модель
    # с update_contract, где counterparty_id может оставаться NULL у старых строк.
    if not data.counterparty_id:
        raise HTTPException(status_code=400, detail="Выберите контрагента из реестра контрагентов")
    cp = _resolve_counterparty(db, data.counterparty_id)

    contract = Contract(
        contract_number=_clean(data.contract_number),
        contract_date=data.contract_date,
        inn=cp.inn,
        counterparty_name=cp.name,
        counterparty_id=cp.id,
        marketing_name=_clean(data.marketing_name),
        cooperation_format=_clean(data.cooperation_format),
        services=_clean(data.services),
        end_date_text=_clean(data.end_date_text),
        prolongation=_clean(data.prolongation),
        payment_form=_clean(data.payment_form),
        payment_term_days=data.payment_term_days,
        payment_term_condition=_clean(data.payment_term_condition),
        note=_clean(data.note),
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)

    log_action(db, current_user, "create_contract", entity_type="contract", entity_id=contract.id,
               details=f"Создан договор № {contract.contract_number or '—'} ({contract.counterparty_name or '—'})")
    return {"id": contract.id, "message": "Договор создан"}


@router.put("/{contract_id}")
def update_contract(
    contract_id: int,
    data: ContractCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contracts", "edit"))
):
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Договор не найден")

    # Если counterparty_id передан — контрагент привязан/перепривязан к реестру, и
    # counterparty_name/inn ВСЕГДА берутся из канонической записи Counterparty (клиентский
    # свободный текст в этих двух полях для привязанных строк игнорируется). Если
    # counterparty_id не передан (None) — это правка исторической непривязанной строки,
    # counterparty_name/inn остаются обычным свободным текстом, как раньше.
    if data.counterparty_id:
        cp = _resolve_counterparty(db, data.counterparty_id)
        resolved_name, resolved_inn, resolved_cp_id = cp.name, cp.inn, cp.id
    else:
        resolved_name, resolved_inn, resolved_cp_id = _clean(data.counterparty_name), _clean(data.inn), None

    new_values = {
        "contract_number": _clean(data.contract_number),
        "contract_date": data.contract_date,
        "inn": resolved_inn,
        "counterparty_name": resolved_name,
        "counterparty_id": resolved_cp_id,
        "marketing_name": _clean(data.marketing_name),
        "cooperation_format": _clean(data.cooperation_format),
        "services": _clean(data.services),
        "end_date_text": _clean(data.end_date_text),
        "prolongation": _clean(data.prolongation),
        "payment_form": _clean(data.payment_form),
        "payment_term_days": data.payment_term_days,
        "payment_term_condition": _clean(data.payment_term_condition),
        "note": _clean(data.note),
    }

    changes = []
    labels = {
        "contract_number": "№ договора", "contract_date": "дата договора", "inn": "ИНН",
        "counterparty_name": "контрагент", "counterparty_id": "привязка к реестру",
        "marketing_name": "маркетинговое название",
        "cooperation_format": "формат сотрудничества", "services": "услуги",
        "end_date_text": "дата окончания", "prolongation": "пролонгация",
        "payment_form": "форма оплаты", "payment_term_days": "срок оплаты, дни",
        "payment_term_condition": "условие", "note": "примечание",
    }
    for key, val in new_values.items():
        old = getattr(contract, key)
        if val != old:
            changes.append(f"{labels[key]}: {old or '—'} → {val or '—'}")
            setattr(contract, key, val)

    db.commit()
    if changes:
        log_action(db, current_user, "update_contract", entity_type="contract", entity_id=contract.id,
                   details="; ".join(changes))
    return {"message": "Договор обновлён"}


@router.delete("/{contract_id}")
def delete_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contracts", "edit"))
):
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Договор не найден")
    label = f"{contract.contract_number or '—'} ({contract.counterparty_name or '—'})"
    db.delete(contract)
    db.commit()

    log_action(db, current_user, "delete_contract", entity_type="contract", entity_id=contract_id,
               details=f"Удалён договор {label}")
    return {"message": "Договор удалён"}
