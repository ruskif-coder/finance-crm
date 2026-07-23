"""
Справочники дашборда продаж: услуги, рекламодатели, бренды, прайс.

Паттерны повторяют routers/articles.py, чтобы код читался однородно с остальным
проектом: APIRouter без префикса (он задаётся в main.py), Pydantic-модели рядом
с эндпойнтами, русские тексты ошибок, проверка дублей через func.lower().

Удаление — мягкое, через is_active = FALSE (решение заказчика 2026-07-23).
Причина: при физическом удалении с проверкой ссылок использованную запись
всё равно удалить нельзя, и справочник замусоривается без возможности скрыть
запись из выпадающих списков.

Маршруты без параметра объявлены ДО маршрутов с {id} — иначе, например,
/services/registry перехватывается как service_id.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import date

from app.database import get_db
from app.models import User
from app.routers.auth import get_current_user
from app.permissions import require_permission
from app.audit import log_action
from app.sales.models import (SalesService, SalesServiceGroup, SalesAdvertiser,
                              SalesBrand, SalesPriceListItem)
from app.sales.normalize import normalize_name, normalize_inn

router = APIRouter()

_VIEW = require_permission("sales_directories", "view")
_EDIT = require_permission("sales_directories", "edit")
_DELETE = require_permission("sales_directories", "delete")


# ============================== Pydantic ==============================

class ServiceIn(BaseModel):
    name: str
    group: Optional[str] = None
    note: Optional[str] = None


class ServiceGroupIn(BaseModel):
    name: str


class AdvertiserIn(BaseModel):
    name: str
    counterparty_id: Optional[int] = None
    inn: Optional[str] = None
    exclude_from_revenue: bool = False
    note: Optional[str] = None


class BrandIn(BaseModel):
    name: str
    advertiser_id: int


class PriceIn(BaseModel):
    service_id: int
    price: float
    currency: str = "RUB"
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    unit: Optional[str] = None
    note: Optional[str] = None


def _require(db: Session, model, obj_id: int, what: str):
    obj = db.query(model).filter(model.id == obj_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail=f"{what} не найден(а)")
    return obj


def _reject_duplicate(db: Session, model, name: str, exclude_id: int | None = None,
                      extra_filter=None):
    """Дубль ищется по нормализованному имени, а не по точному совпадению:
    в исходных данных одна и та же услуга пишется как "web", "in-app",
    "inapp", "in app". Без этого справочник обрастает вариантами написания."""
    key = normalize_name(name)
    q = db.query(model).filter(func.lower(func.trim(model.name)) == key)
    if exclude_id is not None:
        q = q.filter(model.id != exclude_id)
    if extra_filter is not None:
        q = q.filter(extra_filter)
    dup = q.first()
    if dup:
        raise HTTPException(status_code=400, detail=f"«{dup.name}» уже есть в справочнике")


def _clean_name(raw: str) -> str:
    name = (raw or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название не может быть пустым")
    return name


# ============================== Услуги ==============================

@router.get("/services")
def list_services(only_active: bool = True, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    """Открыт любому авторизованному — используется в выпадающих списках."""
    q = db.query(SalesService)
    if only_active:
        q = q.filter(SalesService.is_active.is_(True))
    rows = q.order_by(SalesService.sort_order, SalesService.name).all()
    return {"items": [{"id": s.id, "name": s.name, "group": s.group,
                       "is_active": s.is_active} for s in rows]}


@router.get("/services/groups")
def list_service_groups(db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    rows = db.query(SalesServiceGroup).order_by(SalesServiceGroup.sort_order,
                                                SalesServiceGroup.name).all()
    return {"items": [{"id": g.id, "name": g.name, "sort_order": g.sort_order} for g in rows]}


@router.post("/services/groups")
def create_service_group(data: ServiceGroupIn, db: Session = Depends(get_db),
                         current_user: User = Depends(_EDIT)):
    name = _clean_name(data.name)
    _reject_duplicate(db, SalesServiceGroup, name)
    max_order = db.query(func.max(SalesServiceGroup.sort_order)).scalar() or 0
    group = SalesServiceGroup(name=name, sort_order=max_order + 1)
    db.add(group)
    db.commit()
    db.refresh(group)
    log_action(db, current_user, "create_sales_service_group", "sales_service_group", group.id, name)
    return {"id": group.id, "message": "Группа создана"}


@router.post("/services")
def create_service(data: ServiceIn, db: Session = Depends(get_db),
                   current_user: User = Depends(_EDIT)):
    name = _clean_name(data.name)
    _reject_duplicate(db, SalesService, name)
    max_order = db.query(func.max(SalesService.sort_order)).scalar() or 0
    svc = SalesService(name=name, group=data.group, note=data.note, sort_order=max_order + 1)
    db.add(svc)
    db.commit()
    db.refresh(svc)
    log_action(db, current_user, "create_sales_service", "sales_service", svc.id, name)
    return {"id": svc.id, "message": "Услуга создана"}


@router.put("/services/{service_id}")
def update_service(service_id: int, data: ServiceIn, db: Session = Depends(get_db),
                   current_user: User = Depends(_EDIT)):
    svc = _require(db, SalesService, service_id, "Услуга")
    name = _clean_name(data.name)
    _reject_duplicate(db, SalesService, name, exclude_id=service_id)
    svc.name, svc.group, svc.note = name, data.group, data.note
    db.commit()
    log_action(db, current_user, "update_sales_service", "sales_service", svc.id, name)
    return {"message": "Услуга обновлена"}


@router.delete("/services/{service_id}")
def deactivate_service(service_id: int, db: Session = Depends(get_db),
                       current_user: User = Depends(_DELETE)):
    """Мягкое удаление: запись скрывается из выпадающих списков, но остаётся в БД,
    чтобы исторические сделки не потеряли ссылку."""
    svc = _require(db, SalesService, service_id, "Услуга")
    svc.is_active = False
    db.commit()
    log_action(db, current_user, "deactivate_sales_service", "sales_service", svc.id, svc.name)
    return {"message": "Услуга скрыта из справочника"}


# ========================== Рекламодатели ==========================

@router.get("/advertisers")
def list_advertisers(only_active: bool = True, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    q = db.query(SalesAdvertiser)
    if only_active:
        q = q.filter(SalesAdvertiser.is_active.is_(True))
    rows = q.order_by(SalesAdvertiser.name).all()
    return {"items": [{"id": a.id, "name": a.name, "inn": a.inn,
                       "counterparty_id": a.counterparty_id,
                       "exclude_from_revenue": a.exclude_from_revenue,
                       "is_active": a.is_active} for a in rows]}


@router.post("/advertisers")
def create_advertiser(data: AdvertiserIn, db: Session = Depends(get_db),
                      current_user: User = Depends(_EDIT)):
    name = _clean_name(data.name)
    _reject_duplicate(db, SalesAdvertiser, name)
    # ИНН нормализуется на входе: из Битрикса он приходит как float ("1673005251.0"),
    # и в справочник должен попасть уже в каноническом виде.
    adv = SalesAdvertiser(
        name=name,
        counterparty_id=data.counterparty_id,
        inn=normalize_inn(data.inn),
        exclude_from_revenue=data.exclude_from_revenue,
        note=data.note,
    )
    db.add(adv)
    db.commit()
    db.refresh(adv)
    log_action(db, current_user, "create_sales_advertiser", "sales_advertiser", adv.id, name)
    return {"id": adv.id, "message": "Рекламодатель создан"}


@router.put("/advertisers/{advertiser_id}")
def update_advertiser(advertiser_id: int, data: AdvertiserIn, db: Session = Depends(get_db),
                      current_user: User = Depends(_EDIT)):
    adv = _require(db, SalesAdvertiser, advertiser_id, "Рекламодатель")
    name = _clean_name(data.name)
    _reject_duplicate(db, SalesAdvertiser, name, exclude_id=advertiser_id)
    adv.name = name
    adv.counterparty_id = data.counterparty_id
    adv.inn = normalize_inn(data.inn)
    adv.exclude_from_revenue = data.exclude_from_revenue
    adv.note = data.note
    db.commit()
    log_action(db, current_user, "update_sales_advertiser", "sales_advertiser", adv.id, name)
    return {"message": "Рекламодатель обновлён"}


@router.delete("/advertisers/{advertiser_id}")
def deactivate_advertiser(advertiser_id: int, db: Session = Depends(get_db),
                          current_user: User = Depends(_DELETE)):
    adv = _require(db, SalesAdvertiser, advertiser_id, "Рекламодатель")
    adv.is_active = False
    db.commit()
    log_action(db, current_user, "deactivate_sales_advertiser", "sales_advertiser", adv.id, adv.name)
    return {"message": "Рекламодатель скрыт из справочника"}


# ============================== Бренды ==============================

@router.get("/brands")
def list_brands(advertiser_id: Optional[int] = None, only_active: bool = True,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    q = db.query(SalesBrand)
    if advertiser_id is not None:
        q = q.filter(SalesBrand.advertiser_id == advertiser_id)
    if only_active:
        q = q.filter(SalesBrand.is_active.is_(True))
    rows = q.order_by(SalesBrand.name).all()
    return {"items": [{"id": b.id, "name": b.name, "advertiser_id": b.advertiser_id,
                       "is_active": b.is_active} for b in rows]}


@router.post("/brands")
def create_brand(data: BrandIn, db: Session = Depends(get_db),
                 current_user: User = Depends(_EDIT)):
    name = _clean_name(data.name)
    _require(db, SalesAdvertiser, data.advertiser_id, "Рекламодатель")
    # Уникальность бренда — в пределах рекламодателя: одноимённые бренды
    # у разных рекламодателей допустимы.
    _reject_duplicate(db, SalesBrand, name,
                      extra_filter=(SalesBrand.advertiser_id == data.advertiser_id))
    brand = SalesBrand(name=name, advertiser_id=data.advertiser_id)
    db.add(brand)
    db.commit()
    db.refresh(brand)
    log_action(db, current_user, "create_sales_brand", "sales_brand", brand.id, name)
    return {"id": brand.id, "message": "Бренд создан"}


@router.put("/brands/{brand_id}")
def update_brand(brand_id: int, data: BrandIn, db: Session = Depends(get_db),
                 current_user: User = Depends(_EDIT)):
    brand = _require(db, SalesBrand, brand_id, "Бренд")
    name = _clean_name(data.name)
    _require(db, SalesAdvertiser, data.advertiser_id, "Рекламодатель")
    _reject_duplicate(db, SalesBrand, name, exclude_id=brand_id,
                      extra_filter=(SalesBrand.advertiser_id == data.advertiser_id))
    brand.name, brand.advertiser_id = name, data.advertiser_id
    db.commit()
    log_action(db, current_user, "update_sales_brand", "sales_brand", brand.id, name)
    return {"message": "Бренд обновлён"}


@router.delete("/brands/{brand_id}")
def deactivate_brand(brand_id: int, db: Session = Depends(get_db),
                     current_user: User = Depends(_DELETE)):
    brand = _require(db, SalesBrand, brand_id, "Бренд")
    brand.is_active = False
    db.commit()
    log_action(db, current_user, "deactivate_sales_brand", "sales_brand", brand.id, brand.name)
    return {"message": "Бренд скрыт из справочника"}


# ============================== Прайс ==============================

@router.get("/price-list")
def list_price(service_id: Optional[int] = None, only_active: bool = True,
               db: Session = Depends(get_db),
               current_user: User = Depends(_VIEW)):
    q = db.query(SalesPriceListItem)
    if service_id is not None:
        q = q.filter(SalesPriceListItem.service_id == service_id)
    if only_active:
        q = q.filter(SalesPriceListItem.is_active.is_(True))
    rows = q.order_by(SalesPriceListItem.service_id, SalesPriceListItem.valid_from).all()
    return {"items": [{"id": p.id, "service_id": p.service_id, "price": p.price,
                       "currency": p.currency, "valid_from": p.valid_from,
                       "valid_to": p.valid_to, "unit": p.unit,
                       "is_active": p.is_active} for p in rows]}


@router.post("/price-list")
def create_price(data: PriceIn, db: Session = Depends(get_db),
                 current_user: User = Depends(_EDIT)):
    _require(db, SalesService, data.service_id, "Услуга")
    if data.valid_from and data.valid_to and data.valid_to < data.valid_from:
        raise HTTPException(status_code=400, detail="Дата окончания раньше даты начала")
    item = SalesPriceListItem(**data.dict())
    db.add(item)
    db.commit()
    db.refresh(item)
    log_action(db, current_user, "create_sales_price", "sales_price_list", item.id, str(data.price))
    return {"id": item.id, "message": "Позиция прайса создана"}


@router.put("/price-list/{item_id}")
def update_price(item_id: int, data: PriceIn, db: Session = Depends(get_db),
                 current_user: User = Depends(_EDIT)):
    item = _require(db, SalesPriceListItem, item_id, "Позиция прайса")
    _require(db, SalesService, data.service_id, "Услуга")
    if data.valid_from and data.valid_to and data.valid_to < data.valid_from:
        raise HTTPException(status_code=400, detail="Дата окончания раньше даты начала")
    for field, value in data.dict().items():
        setattr(item, field, value)
    db.commit()
    log_action(db, current_user, "update_sales_price", "sales_price_list", item.id, str(data.price))
    return {"message": "Позиция прайса обновлена"}


@router.delete("/price-list/{item_id}")
def deactivate_price(item_id: int, db: Session = Depends(get_db),
                     current_user: User = Depends(_DELETE)):
    item = _require(db, SalesPriceListItem, item_id, "Позиция прайса")
    item.is_active = False
    db.commit()
    log_action(db, current_user, "deactivate_sales_price", "sales_price_list", item.id, str(item.price))
    return {"message": "Позиция прайса скрыта"}
