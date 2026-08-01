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
from app.models import User, Counterparty
from app.routers.auth import get_current_user
from app.permissions import require_permission
from app.audit import log_action
from app.sales.models import (SalesService, SalesServiceGroup, SalesAdvertiser,
                              SalesBrand, SalesPriceListItem, SalesAgency,
                              SalesPipeline, SalesDeal, SalesPipelineStage,
                              SalesBitrixStageMap,
                              SalesAgencyCounterparty, SalesAdvertiserCounterparty)
from app.sales.normalize import normalize_name, normalize_inn
from app.sales.stages import STAGE_CATALOG, STAGE_BY_KEY
import logging

router = APIRouter()
logger = logging.getLogger("finance")

# Права per-ресурс: рекламодатели/бренды/услуги/прайс → dir_advertisers;
# агентства → dir_agencies; воронки перенесены в «Настройки» → settings.
ADV_VIEW = require_permission("dir_advertisers", "view")
ADV_EDIT = require_permission("dir_advertisers", "edit")
ADV_DELETE = require_permission("dir_advertisers", "delete")
AG_VIEW = require_permission("dir_agencies", "view")
AG_EDIT = require_permission("dir_agencies", "edit")
AG_DELETE = require_permission("dir_agencies", "delete")
SET_VIEW = require_permission("settings", "view")
SET_EDIT = require_permission("settings", "edit")
SET_DELETE = require_permission("settings", "edit")   # у «Настроек» нет отдельного delete


# ============================== Pydantic ==============================

class ServiceIn(BaseModel):
    name: str
    group: Optional[str] = None
    note: Optional[str] = None


class ServiceGroupIn(BaseModel):
    name: str


class AdvertiserIn(BaseModel):
    short_name: Optional[str] = None
    name_en: Optional[str] = None
    name_ru: Optional[str] = None
    website: Optional[str] = None
    counterparty_id: Optional[int] = None
    inn: Optional[str] = None
    note: Optional[str] = None


def _advertiser_key_name(data: "AdvertiserIn") -> str:
    """Каноничный ключ (уникальное поле name) — короткое имя, иначе первое
    заполненное из ENG/РУС. Хоть одно название обязательно."""
    for v in (data.short_name, data.name_en, data.name_ru):
        if (v or "").strip():
            return v.strip()
    return ""


class CounterpartyLink(BaseModel):
    counterparty_id: int


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
                         current_user: User = Depends(ADV_EDIT)):
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
                   current_user: User = Depends(ADV_EDIT)):
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
                   current_user: User = Depends(ADV_EDIT)):
    svc = _require(db, SalesService, service_id, "Услуга")
    name = _clean_name(data.name)
    _reject_duplicate(db, SalesService, name, exclude_id=service_id)
    svc.name, svc.group, svc.note = name, data.group, data.note
    db.commit()
    log_action(db, current_user, "update_sales_service", "sales_service", svc.id, name)
    return {"message": "Услуга обновлена"}


@router.delete("/services/{service_id}")
def deactivate_service(service_id: int, db: Session = Depends(get_db),
                       current_user: User = Depends(ADV_DELETE)):
    """Мягкое удаление: запись скрывается из выпадающих списков, но остаётся в БД,
    чтобы исторические сделки не потеряли ссылку."""
    svc = _require(db, SalesService, service_id, "Услуга")
    svc.is_active = False
    db.commit()
    log_action(db, current_user, "deactivate_sales_service", "sales_service", svc.id, svc.name)
    return {"message": "Услуга скрыта из справочника"}


class UseIn(BaseModel):
    on: bool


@router.put("/services/{service_id}/use")
def set_service_use(service_id: int, data: UseIn, db: Session = Depends(get_db),
                    current_user: User = Depends(SET_EDIT)):
    """Галочка «использовать» — включает/выключает услугу (is_active)."""
    svc = _require(db, SalesService, service_id, "Услуга")
    svc.is_active = data.on
    db.commit()
    log_action(db, current_user, "set_service_use", "sales_service", svc.id,
               f"{svc.name}: {'использовать' if data.on else 'не использовать'}")
    return {"message": "Сохранено", "is_active": svc.is_active}


@router.post("/services/refresh")
def refresh_services(db: Session = Depends(get_db), current_user: User = Depends(SET_EDIT)):
    """Синхронизация услуг с Битриксом («Продукты Simb-ad», СП 1050): добавляет новые
    (матч по нормализованному имени), существующие не трогает."""
    from app.sales.bitrix.transport import list_bitrix_services
    try:
        items = list_bitrix_services()
    except Exception as e:
        logger.error("directories: Битрикс недоступен: %s", e)
        raise HTTPException(status_code=502, detail="Битрикс недоступен (детали в логе сервера)")
    existing = {normalize_name(s.name) for s in db.query(SalesService).all()}
    added = 0
    max_order = db.query(func.max(SalesService.sort_order)).scalar() or 0
    for it in items:
        title = (it.get("title") or "").strip()
        if not title or normalize_name(title) in existing:
            continue
        max_order += 1
        db.add(SalesService(name=title, is_active=True, sort_order=max_order))
        existing.add(normalize_name(title))
        added += 1
    db.commit()
    log_action(db, current_user, "refresh_services", "sales_service", 0,
               f"добавлено из Битрикса: {added}")
    return {"added": added, "bitrix_total": len(items)}


# ========================== Рекламодатели ==========================

@router.get("/producers")
def list_advertisers(only_active: bool = True, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    q = db.query(SalesAdvertiser)
    if only_active:
        q = q.filter(SalesAdvertiser.is_active.is_(True))
    rows = q.order_by(func.coalesce(SalesAdvertiser.short_name, SalesAdvertiser.name)).all()

    # Бренды подтягиваются одним запросом и раскладываются по рекламодателям:
    # запрос на каждого дал бы 167 обращений к БД на одну отрисовку списка.
    brands = db.query(SalesBrand).filter(SalesBrand.is_active.is_(True)).order_by(SalesBrand.name).all()
    by_adv = {}
    for b in brands:
        by_adv.setdefault(b.advertiser_id, []).append({"id": b.id, "name": b.name})

    # Число сделок на рекламодателя — одним GROUP BY, не запросом на каждого
    deal_counts = dict(db.query(SalesDeal.advertiser_id, func.count(SalesDeal.id))
                       .group_by(SalesDeal.advertiser_id).all())

    # Юрлица рекламодателей (прямые договора) — одним запросом
    cp_names = dict(db.query(Counterparty.id, Counterparty.name).all())
    adv_cps = {}
    for lk in db.query(SalesAdvertiserCounterparty).all():
        adv_cps.setdefault(lk.advertiser_id, []).append(
            {"counterparty_id": lk.counterparty_id, "name": cp_names.get(lk.counterparty_id)})

    return {"items": [{"id": a.id, "name": a.name, "bx_id": a.bx_id,
                       "short_name": a.short_name or a.name,
                       "name_en": a.name_en, "name_ru": a.name_ru, "website": a.website,
                       "inn": a.inn, "counterparty_id": a.counterparty_id,
                       "exclude_from_revenue": a.exclude_from_revenue,
                       "is_active": a.is_active,
                       "deals": deal_counts.get(a.id, 0),
                       "brands": by_adv.get(a.id, []),
                       "counterparties": adv_cps.get(a.id, [])} for a in rows]}


@router.post("/producers")
def create_advertiser(data: AdvertiserIn, db: Session = Depends(get_db),
                      current_user: User = Depends(ADV_EDIT)):
    name = _clean_name(_advertiser_key_name(data))
    _reject_duplicate(db, SalesAdvertiser, name)
    # ИНН нормализуется на входе: из Битрикса он приходит как float ("1673005251.0"),
    # и в справочник должен попасть уже в каноническом виде.
    adv = SalesAdvertiser(
        name=name,
        short_name=(data.short_name or None),
        name_en=(data.name_en or None),
        name_ru=(data.name_ru or None),
        website=(data.website or None),
        counterparty_id=data.counterparty_id,
        inn=normalize_inn(data.inn),
        note=data.note,
    )
    db.add(adv)
    db.commit()
    db.refresh(adv)
    log_action(db, current_user, "create_sales_advertiser", "sales_advertiser", adv.id, name)
    return {"id": adv.id, "message": "Рекламодатель создан"}


@router.put("/producers/{advertiser_id}")
def update_advertiser(advertiser_id: int, data: AdvertiserIn, db: Session = Depends(get_db),
                      current_user: User = Depends(ADV_EDIT)):
    adv = _require(db, SalesAdvertiser, advertiser_id, "Рекламодатель")
    # Каноничный ключ = короткое имя / первое заполненное. Если ничего не прислано —
    # оставляем прежнее (правка website не должна обнулять имя и падать 400).
    name = _advertiser_key_name(data) or adv.name
    dup = (db.query(SalesAdvertiser)
           .filter(func.lower(func.trim(SalesAdvertiser.name)) == normalize_name(name),
                   SalesAdvertiser.id != advertiser_id).first())
    if dup:
        raise HTTPException(status_code=400,
            detail=f"«{dup.name}» уже есть. Если нужно объединить — перенесите бренды "
                   f"на него (⇄) или слейте дубли, а не переименовывайте.")
    adv.name = name
    adv.short_name = data.short_name or None
    adv.name_en = data.name_en or None
    adv.name_ru = data.name_ru or None
    adv.website = data.website or None
    adv.counterparty_id = data.counterparty_id
    adv.inn = normalize_inn(data.inn)
    adv.note = data.note
    db.commit()
    log_action(db, current_user, "update_sales_advertiser", "sales_advertiser", adv.id, name)
    return {"message": "Рекламодатель обновлён"}


@router.delete("/producers/{advertiser_id}")
def deactivate_advertiser(advertiser_id: int, db: Session = Depends(get_db),
                          current_user: User = Depends(ADV_DELETE)):
    adv = _require(db, SalesAdvertiser, advertiser_id, "Рекламодатель")
    adv.is_active = False
    db.commit()
    log_action(db, current_user, "deactivate_sales_advertiser", "sales_advertiser", adv.id, adv.name)
    return {"message": "Рекламодатель скрыт из справочника"}


@router.post("/producers/{advertiser_id}/counterparties")
def attach_producer_counterparty(advertiser_id: int, data: CounterpartyLink,
                                  db: Session = Depends(get_db),
                                  current_user: User = Depends(ADV_EDIT)):
    """Прикрепляет юрлицо к рекламодателю (прямой договор). Несколько допустимо."""
    _require(db, SalesAdvertiser, advertiser_id, "Рекламодатель")
    cp = db.query(Counterparty).filter(Counterparty.id == data.counterparty_id).first()
    if not cp:
        raise HTTPException(status_code=404, detail="Контрагент не найден")
    exists = (db.query(SalesAdvertiserCounterparty)
              .filter(SalesAdvertiserCounterparty.advertiser_id == advertiser_id,
                      SalesAdvertiserCounterparty.counterparty_id == data.counterparty_id).first())
    if exists:
        raise HTTPException(status_code=400, detail=f"«{cp.name}» уже прикреплён")
    db.add(SalesAdvertiserCounterparty(advertiser_id=advertiser_id,
                                        counterparty_id=data.counterparty_id))
    db.commit()
    log_action(db, current_user, "attach_producer_cp", "sales_advertiser", advertiser_id, cp.name)
    return {"message": f"«{cp.name}» прикреплён"}


@router.delete("/producers/{advertiser_id}/counterparties/{counterparty_id}")
def detach_producer_counterparty(advertiser_id: int, counterparty_id: int,
                                  db: Session = Depends(get_db),
                                  current_user: User = Depends(ADV_EDIT)):
    lk = (db.query(SalesAdvertiserCounterparty)
          .filter(SalesAdvertiserCounterparty.advertiser_id == advertiser_id,
                  SalesAdvertiserCounterparty.counterparty_id == counterparty_id).first())
    if not lk:
        raise HTTPException(status_code=404, detail="Связь не найдена")
    db.delete(lk)
    db.commit()
    log_action(db, current_user, "detach_producer_cp", "sales_advertiser", advertiser_id,
               str(counterparty_id))
    return {"message": "Юрлицо откреплено"}


# ============================== Воронки ==============================

class PipelineTrack(BaseModel):
    is_tracked: bool


class PipelineRename(BaseModel):
    name: str


@router.get("/pipelines")
def list_pipelines(db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    """Воронки с числом сделок. Открыт любому авторизованному —
    используется в фильтрах реестра."""
    counts = dict(db.query(SalesDeal.pipeline, func.count(SalesDeal.id))
                  .group_by(SalesDeal.pipeline).all())
    rows = db.query(SalesPipeline).order_by(SalesPipeline.sort_order, SalesPipeline.name).all()
    return {"items": [{"id": p.id, "name": p.name, "is_tracked": p.is_tracked,
                       "is_active": p.is_active,
                       "deals": counts.get(p.name, 0)} for p in rows]}


@router.get("/pipelines/{pipeline_id}/stages")
def pipeline_stages(pipeline_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    """Стадии воронки — для раскрывающегося списка в справочнике.
    Число сделок на стадии считается по фактическим данным (bitrix_stage)."""
    p = _require(db, SalesPipeline, pipeline_id, "Воронка")
    counts = dict(db.query(SalesDeal.bitrix_stage, func.count(SalesDeal.id))
                  .filter(SalesDeal.pipeline == p.name)
                  .group_by(SalesDeal.bitrix_stage).all())
    # Текущая привязка к светофору 2/2/2 — из карты стадий по имени.
    # Ключ совпадает с джойном реестра (pipeline+bitrix_stage по именам).
    maps = {m.bitrix_stage: m for m in
            db.query(SalesBitrixStageMap).filter(SalesBitrixStageMap.pipeline == p.name).all()}
    rows = (db.query(SalesPipelineStage)
            .filter(SalesPipelineStage.pipeline_id == pipeline_id)
            .order_by(SalesPipelineStage.sort_order).all())
    items = []
    for s in rows:
        m = maps.get(s.name)
        items.append({"id": s.id, "status_id": s.status_id, "name": s.name,
                      "deals": counts.get(s.name, 0),
                      "stage_key": m.stage_key if m else None,
                      "money_layer": m.money_layer if m else None})
    return {"items": items, "bitrix_category_id": p.bitrix_category_id,
            "catalog": STAGE_CATALOG}


@router.put("/pipelines/{pipeline_id}/tracked")
def set_pipeline_tracked(pipeline_id: int, data: PipelineTrack,
                         db: Session = Depends(get_db),
                         current_user: User = Depends(SET_EDIT)):
    """Включает/выключает парсинг воронки. Данные не трогает — только флаг.
    При выключении синхронизация перестаёт грузить сделки этой воронки."""
    p = _require(db, SalesPipeline, pipeline_id, "Воронка")
    p.is_tracked = data.is_tracked
    db.commit()
    log_action(db, current_user, "set_pipeline_tracked", "sales_pipeline", p.id,
               f"{p.name}: {'парсить' if data.is_tracked else 'не парсить'}")
    return {"message": "Сохранено", "is_tracked": p.is_tracked}


def _cascade_pipeline_rename(db: Session, old: str, new: str) -> tuple[int, int]:
    """Имя воронки — денормализованный ключ в sales_deals.pipeline и
    sales_bitrix_stage_map.pipeline. Справочник (sales_pipelines) — единственный источник
    имени; при переименовании каскадно обновляем обе таблицы, чтобы связь по имени не рвалась
    (счётчики, money-layer джойн, удаление по имени). Обе стороны джойна меняются синхронно,
    поэтому денежные расчёты не меняются — только подпись воронки.
    → (сколько сделок, сколько строк карты стадий обновлено)."""
    if not old or old == new:
        return (0, 0)
    d = (db.query(SalesDeal).filter(SalesDeal.pipeline == old)
         .update({SalesDeal.pipeline: new}, synchronize_session=False))
    m = (db.query(SalesBitrixStageMap).filter(SalesBitrixStageMap.pipeline == old)
         .update({SalesBitrixStageMap.pipeline: new}, synchronize_session=False))
    return (d, m)


def _cascade_stage_rename(db: Session, pipeline_name: str, old: str, new: str) -> tuple[int, int]:
    """Имя стадии — денормализованный ключ (в паре с воронкой) в sales_deals.bitrix_stage
    и sales_bitrix_stage_map.bitrix_stage. Money-layer джойн витрины идёт по ИМЕНАМ
    (pipeline+bitrix_stage), поэтому переименование стадии в Битриксе обязано каскадно
    менять обе таблицы — иначе новые сделки с новым именем стадии не находят раскладку
    и уходят в «Без группы». → (сколько сделок, сколько строк карты обновлено)."""
    if not old or old == new:
        return (0, 0)
    d = (db.query(SalesDeal)
         .filter(SalesDeal.pipeline == pipeline_name, SalesDeal.bitrix_stage == old)
         .update({SalesDeal.bitrix_stage: new}, synchronize_session=False))
    # Коллизия: если пара (pipeline, new) в карте уже есть, переименование старой
    # строки нарушило бы UNIQUE(pipeline,bitrix_stage) и уронило бы весь refresh.
    # Пропускаем — сделки уже переименованы в new и найдут раскладку по существующей
    # строке; старая (pipeline, old) остаётся осиротевшей (безвредно, без сделок).
    clash = (db.query(SalesBitrixStageMap)
             .filter(SalesBitrixStageMap.pipeline == pipeline_name,
                     SalesBitrixStageMap.bitrix_stage == new).first())
    if clash:
        m = 0
    else:
        m = (db.query(SalesBitrixStageMap)
             .filter(SalesBitrixStageMap.pipeline == pipeline_name, SalesBitrixStageMap.bitrix_stage == old)
             .update({SalesBitrixStageMap.bitrix_stage: new}, synchronize_session=False))
    return (d, m)


@router.put("/pipelines/{pipeline_id}/name")
def rename_pipeline(pipeline_id: int, data: PipelineRename,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(SET_EDIT)):
    """Ручное переименование воронки. Нужно для категории 0 (дефолтной): её настоящее
    имя VibeCode API не отдаёт, поэтому оно правится только здесь. refresh это имя не трогает.
    Каскадно переносит имя на сделки и карту стадий."""
    p = _require(db, SalesPipeline, pipeline_id, "Воронка")
    new_name = (data.name or "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Название не может быть пустым")
    clash = (db.query(SalesPipeline)
             .filter(SalesPipeline.name == new_name, SalesPipeline.id != p.id).first())
    if clash:
        raise HTTPException(status_code=409, detail=f"Воронка «{new_name}» уже существует")
    old = p.name
    p.name = new_name
    deals_n, maps_n = _cascade_pipeline_rename(db, old, new_name)
    db.commit()
    log_action(db, current_user, "rename_pipeline", "sales_pipeline", p.id,
               f"{old} → {new_name} (сделок {deals_n}, карт стадий {maps_n})")
    return {"message": "Сохранено", "name": p.name, "deals_updated": deals_n}


@router.post("/pipelines/refresh")
def refresh_pipelines(db: Session = Depends(get_db), current_user: User = Depends(SET_EDIT)):
    """Синхронизация воронок/стадий с Битриксом. Новые воронки заводятся ВЫКЛЮЧЕННЫМИ
    (is_tracked=False) — чтобы синхрон сделок их не тянул, пока не решим. Стадии добавляются/
    переименовываются по имени. Данные (сделки) не трогает."""
    from app.sales.bitrix.transport import list_bitrix_pipelines, list_bitrix_stages
    try:
        cats = list_bitrix_pipelines()
    except Exception as e:
        logger.error("directories: Битрикс недоступен: %s", e)
        raise HTTPException(status_code=502, detail="Битрикс недоступен (детали в логе сервера)")
    added_p, added_s, renamed_s, renamed_p = 0, 0, 0, 0
    used_names = {p.name for p in db.query(SalesPipeline).all()}
    for c in cats:
        cid = c["id"]
        p = db.query(SalesPipeline).filter(SalesPipeline.bitrix_category_id == cid).first()
        if not p:
            name = c["name"] or f"Воронка {cid}"
            if name in used_names:
                name = f"{name} ({cid})"
            used_names.add(name)
            p = SalesPipeline(name=name, bitrix_category_id=cid, is_tracked=False, is_active=True)
            db.add(p)
            db.flush()
            added_p += 1
        elif cid == 0:
            # Категория 0 (дефолтная): её настоящее имя API не отдаёт (подставляем
            # заглушку). Не затираем — имя задаётся только вручную через /name.
            pass
        else:
            new_name = c["name"] or f"Воронка {cid}"
            if new_name != p.name:
                # не даём переименованием создать дубликат имени другой воронки
                if new_name in used_names:
                    new_name = f"{new_name} ({cid})"
                if new_name != p.name:
                    used_names.discard(p.name)
                    used_names.add(new_name)
                    _cascade_pipeline_rename(db, p.name, new_name)
                    p.name = new_name
                    renamed_p += 1
        try:
            stages = list_bitrix_stages(cid)
        except Exception:
            stages = []
        for order, s in enumerate(stages):
            sid = s["status_id"]
            st = (db.query(SalesPipelineStage)
                  .filter(SalesPipelineStage.bitrix_category_id == cid,
                          SalesPipelineStage.status_id == sid).first())
            if not st:
                db.add(SalesPipelineStage(pipeline_id=p.id, bitrix_category_id=cid,
                                          status_id=sid, name=s["name"], sort_order=order))
                added_s += 1
            elif st.name != s["name"]:
                # каскад: карта слоёв и сделки хранят имя стадии денормализованно
                _cascade_stage_rename(db, p.name, st.name, s["name"])
                st.name = s["name"]
                renamed_s += 1
    db.commit()
    log_action(db, current_user, "refresh_pipelines", "sales_pipeline", 0,
               f"воронок +{added_p} (переим. {renamed_p}), стадий +{added_s}, переименовано стадий {renamed_s}")
    return {"pipelines_added": added_p, "pipelines_renamed": renamed_p,
            "stages_added": added_s, "stages_renamed": renamed_s}


class StageMapping(BaseModel):
    stage_key: Optional[str] = None   # None => снять привязку стадии со светофора


@router.put("/pipelines/{pipeline_id}/stages/{stage_id}/mapping")
def set_stage_mapping(pipeline_id: int, stage_id: int, data: StageMapping,
                      db: Session = Depends(get_db),
                      current_user: User = Depends(SET_EDIT)):
    """Привязывает стадию воронки к позиции светофора 2/2/2 (или снимает привязку).

    Из выбранной позиции (stage_key) выводится слой денег — так и StageBar, и
    P&L смотрят на одно значение. Карта ключуется по ИМЕНАМ (воронка, стадия),
    как и джойн реестра, поэтому привязка сразу влияет на витрину."""
    p = _require(db, SalesPipeline, pipeline_id, "Воронка")
    s = (db.query(SalesPipelineStage)
         .filter(SalesPipelineStage.id == stage_id,
                 SalesPipelineStage.pipeline_id == pipeline_id).first())
    if s is None:
        raise HTTPException(status_code=404, detail="Стадия не найдена")

    existing = (db.query(SalesBitrixStageMap)
                .filter(SalesBitrixStageMap.pipeline == p.name,
                        SalesBitrixStageMap.bitrix_stage == s.name).first())

    if data.stage_key is None:
        if existing:
            db.delete(existing)
            db.commit()
        log_action(db, current_user, "unmap_stage", "sales_stage", stage_id,
                   f"{p.name} / {s.name}: привязка снята")
        return {"message": "Привязка снята", "stage_key": None, "money_layer": None}

    cat = STAGE_BY_KEY.get(data.stage_key)
    if cat is None:
        raise HTTPException(status_code=400, detail="Неизвестная позиция светофора")
    if existing is None:
        existing = SalesBitrixStageMap(pipeline=p.name, bitrix_stage=s.name)
        db.add(existing)
    existing.stage_key = cat["key"]
    existing.money_layer = cat["money_layer"]
    existing.is_active = True
    db.commit()
    log_action(db, current_user, "map_stage", "sales_stage", stage_id,
               f"{p.name} / {s.name} → {cat['label']} ({cat['money_layer']})")
    return {"message": "Сохранено", "stage_key": cat["key"], "money_layer": cat["money_layer"]}


@router.delete("/pipelines/{pipeline_id}")
def delete_pipeline(pipeline_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(SET_DELETE)):
    """ФИЗИЧЕСКИ удаляет воронку вместе со всеми её сделками, их сырьём
    и строками маппинга. Необратимо. Отклоняет удаление, если по сделкам
    воронки есть ручные правки или разнесения — их потеря молча недопустима."""
    p = _require(db, SalesPipeline, pipeline_id, "Воронка")

    deal_ids = [d.id for d in db.query(SalesDeal.id).filter(SalesDeal.pipeline == p.name).all()]
    if deal_ids:
        from app.sales.models import SalesDealFieldOverride, SalesDealAnnexAllocation
        blocked = (db.query(func.count(SalesDealFieldOverride.id))
                   .filter(SalesDealFieldOverride.deal_id.in_(deal_ids)).scalar() or 0)
        blocked += (db.query(func.count(SalesDealAnnexAllocation.id))
                    .filter(SalesDealAnnexAllocation.deal_id.in_(deal_ids)).scalar() or 0)
        if blocked:
            raise HTTPException(status_code=400,
                detail=f"Нельзя удалить: по сделкам воронки есть {blocked} ручных правок "
                       f"или разнесений. Сначала разберите их.")

    bitrix_ids = [d.bitrix_id for d in
                  db.query(SalesDeal.bitrix_id).filter(SalesDeal.pipeline == p.name).all()]

    from app.sales.models import SalesBitrixRaw, SalesBitrixStageMap
    if bitrix_ids:
        db.query(SalesBitrixRaw).filter(SalesBitrixRaw.entity == "deal",
                                        SalesBitrixRaw.bitrix_id.in_(bitrix_ids)
                                        ).delete(synchronize_session=False)
    db.query(SalesDeal).filter(SalesDeal.pipeline == p.name).delete(synchronize_session=False)
    db.query(SalesBitrixStageMap).filter(SalesBitrixStageMap.pipeline == p.name
                                         ).delete(synchronize_session=False)
    db.delete(p)
    db.commit()
    log_action(db, current_user, "delete_sales_pipeline", "sales_pipeline", pipeline_id,
               f"{p.name}: удалено сделок {len(deal_ids)}")
    return {"message": f"Воронка «{p.name}» удалена вместе с {len(deal_ids)} сделками"}


# ============================ Агентства ============================

class AgencyIn(BaseModel):
    short_name: Optional[str] = None
    name_en: Optional[str] = None
    name_ru: Optional[str] = None
    holding: Optional[str] = None
    note: Optional[str] = None


def _agency_name(data: "AgencyIn") -> str:
    """Уникальный ключ агентства. Одно из названий обязательно."""
    for v in (data.short_name, data.name_en, data.name_ru):
        if (v or "").strip():
            return v.strip()
    raise HTTPException(status_code=400, detail="Заполните хотя бы одно название")


@router.get("/agencies")
def list_agencies(only_active: bool = True, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    q = db.query(SalesAgency)
    if only_active:
        q = q.filter(SalesAgency.is_active.is_(True))
    rows = q.order_by(SalesAgency.holding.nullslast(),
                      func.coalesce(SalesAgency.short_name, SalesAgency.name)).all()

    cp = dict(db.query(Counterparty.id, Counterparty.name).all())
    links = {}
    for lk in db.query(SalesAgencyCounterparty).all():
        links.setdefault(lk.agency_id, []).append(
            {"counterparty_id": lk.counterparty_id, "name": cp.get(lk.counterparty_id)})

    # Число сделок на агентство — одним GROUP BY
    deal_counts = dict(db.query(SalesDeal.agency_id, func.count(SalesDeal.id))
                       .group_by(SalesDeal.agency_id).all())

    return {"items": [{"id": a.id, "bx_id": a.bx_id,
                       "short_name": a.short_name or a.name,
                       "name_en": a.name_en, "name_ru": a.name_ru,
                       # Исходное полное имя из Битрикса — для опознания, когда
                       # ENG/РУС ещё не размечены. Не теряем то, что было.
                       "full_name": a.name,
                       "holding": a.holding, "is_active": a.is_active, "note": a.note,
                       "deals": deal_counts.get(a.id, 0), "sk_percent": a.sk_percent,
                       "counterparties": links.get(a.id, [])} for a in rows]}


class SkIn(BaseModel):
    sk_percent: float


@router.put("/agencies/{agency_id}/sk")
def set_agency_sk(agency_id: int, data: SkIn, db: Session = Depends(get_db),
                  current_user: User = Depends(AG_EDIT)):
    """Базовый СК агентства (%). Правится по клику в справочнике."""
    a = _require(db, SalesAgency, agency_id, "Агентство")
    if data.sk_percent < 0 or data.sk_percent > 100:
        raise HTTPException(status_code=400, detail="СК должен быть 0–100%")
    a.sk_percent = data.sk_percent
    db.commit()
    log_action(db, current_user, "set_agency_sk", "sales_agency", a.id, f"{a.name}: СК {data.sk_percent}%")
    return {"message": "Сохранено", "sk_percent": a.sk_percent}


@router.post("/agencies")
def create_agency(data: AgencyIn, db: Session = Depends(get_db),
                  current_user: User = Depends(AG_EDIT)):
    name = _agency_name(data)
    _reject_duplicate(db, SalesAgency, name)
    agency = SalesAgency(name=name, short_name=data.short_name or name,
                         name_en=data.name_en or None, name_ru=data.name_ru or None,
                         holding=data.holding or None, note=data.note)
    db.add(agency)
    db.commit()
    db.refresh(agency)
    log_action(db, current_user, "create_sales_agency", "sales_agency", agency.id, name)
    return {"id": agency.id, "message": "Агентство создано"}


@router.put("/agencies/{agency_id}")
def update_agency(agency_id: int, data: AgencyIn, db: Session = Depends(get_db),
                  current_user: User = Depends(AG_EDIT)):
    agency = _require(db, SalesAgency, agency_id, "Агентство")
    _agency_name(data)  # проверка, что хоть одно имя есть
    agency.short_name = data.short_name or None
    agency.name_en = data.name_en or None
    agency.name_ru = data.name_ru or None
    agency.holding = data.holding or None
    agency.note = data.note
    db.commit()
    log_action(db, current_user, "update_sales_agency", "sales_agency", agency.id, agency.name)
    return {"message": "Агентство обновлено"}


@router.post("/agencies/{agency_id}/counterparties")
def attach_counterparty(agency_id: int, data: CounterpartyLink,
                        db: Session = Depends(get_db), current_user: User = Depends(AG_EDIT)):
    """Прикрепляет юрлицо (контрагента) к агентству. Их может быть несколько."""
    _require(db, SalesAgency, agency_id, "Агентство")
    cp = db.query(Counterparty).filter(Counterparty.id == data.counterparty_id).first()
    if not cp:
        raise HTTPException(status_code=404, detail="Контрагент не найден")
    exists = (db.query(SalesAgencyCounterparty)
              .filter(SalesAgencyCounterparty.agency_id == agency_id,
                      SalesAgencyCounterparty.counterparty_id == data.counterparty_id).first())
    if exists:
        raise HTTPException(status_code=400, detail=f"«{cp.name}» уже прикреплён")
    db.add(SalesAgencyCounterparty(agency_id=agency_id, counterparty_id=data.counterparty_id))
    db.commit()
    log_action(db, current_user, "attach_agency_cp", "sales_agency", agency_id, cp.name)
    return {"message": f"«{cp.name}» прикреплён"}


@router.delete("/agencies/{agency_id}/counterparties/{counterparty_id}")
def detach_counterparty(agency_id: int, counterparty_id: int,
                        db: Session = Depends(get_db), current_user: User = Depends(AG_EDIT)):
    lk = (db.query(SalesAgencyCounterparty)
          .filter(SalesAgencyCounterparty.agency_id == agency_id,
                  SalesAgencyCounterparty.counterparty_id == counterparty_id).first())
    if not lk:
        raise HTTPException(status_code=404, detail="Связь не найдена")
    db.delete(lk)
    db.commit()
    log_action(db, current_user, "detach_agency_cp", "sales_agency", agency_id, str(counterparty_id))
    return {"message": "Юрлицо откреплено"}


@router.delete("/agencies/{agency_id}")
def deactivate_agency(agency_id: int, db: Session = Depends(get_db),
                      current_user: User = Depends(AG_DELETE)):
    agency = _require(db, SalesAgency, agency_id, "Агентство")
    agency.is_active = False
    db.commit()
    log_action(db, current_user, "deactivate_sales_agency", "sales_agency", agency.id, agency.name)
    return {"message": "Агентство скрыто из справочника"}


# ==================== Слияние дублей рекламодателей ====================

class MergeIn(BaseModel):
    source_id: int   # кого вливаем (исчезнет)


@router.get("/producers/duplicates")
def advertiser_duplicates(db: Session = Depends(get_db),
                          current_user: User = Depends(ADV_VIEW)):
    """Предлагает пары возможных дублей рекламодателей по совпадению
    русского или латинского ядра имени. Только предложение — слияние
    подтверждает человек, автоматически не склеиваем."""
    import re

    def cores(a):
        out = set()
        for v in (a.name, a.name_en, a.name_ru):
            if not v:
                continue
            for part in re.split(r"[(/,]", v):
                lat = re.sub(r"[^a-z0-9]", "", part.lower())
                rus = re.sub(r"[^а-я0-9]", "", part.lower())
                if len(lat) >= 4:
                    out.add(("lat", lat))
                if len(rus) >= 4:
                    out.add(("rus", rus))
        return out

    advs = db.query(SalesAdvertiser).all()
    brand_counts = dict(db.query(SalesBrand.advertiser_id, func.count(SalesBrand.id))
                        .group_by(SalesBrand.advertiser_id).all())
    adv_cores = [(a, cores(a)) for a in advs]

    def related(ca, cb):
        """Совпадение ядер: равенство или префикс (одно — начало другого),
        в пределах одного алфавита. Префикс ловит «биннофарм» ⊂ «биннофармгрупп»."""
        for alpha, x in ca:
            for beta, y in cb:
                if alpha != beta:
                    continue
                if x == y:
                    return x
                short, long = (x, y) if len(x) <= len(y) else (y, x)
                if len(short) >= 5 and long.startswith(short):
                    return short
        return None

    seen_pairs = set()
    pairs = []
    for i in range(len(adv_cores)):
        a, ca = adv_cores[i]
        for j in range(i + 1, len(adv_cores)):
            b, cb = adv_cores[j]
            m = related(ca, cb)
            if not m:
                continue
            key = (a.id, b.id)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            keep, drop = (a, b) if brand_counts.get(a.id, 0) >= brand_counts.get(b.id, 0) else (b, a)
            pairs.append({
                "keep": {"id": keep.id, "name": keep.name, "brands": brand_counts.get(keep.id, 0)},
                "drop": {"id": drop.id, "name": drop.name, "brands": brand_counts.get(drop.id, 0)},
                "matched_on": m,
            })
    pairs.sort(key=lambda p: -(p["keep"]["brands"] + p["drop"]["brands"]))
    return {"pairs": pairs}


@router.post("/producers/{target_id}/merge")
def merge_advertiser(target_id: int, data: MergeIn, db: Session = Depends(get_db),
                     current_user: User = Depends(ADV_EDIT)):
    """Вливает source в target: бренды переносятся (дубли по имени схлопываются),
    сделки и ручные правки переуказываются на target, source удаляется."""
    if data.source_id == target_id:
        raise HTTPException(status_code=400, detail="Нельзя слить рекламодателя с самим собой")
    target = _require(db, SalesAdvertiser, target_id, "Рекламодатель (цель)")
    source = _require(db, SalesAdvertiser, data.source_id, "Рекламодатель (источник)")

    # Всё через bulk-UPDATE по id, без ORM-мутаций: если двигать бренды присвоением
    # атрибута, relationship SalesAdvertiser.brands при удалении источника обнулит
    # им advertiser_id (NOT NULL → падение). Bulk-запросы этого не задевают.
    dropped_name = source.name
    tgt_brands = {normalize_name(b.name): b.id for b in
                  db.query(SalesBrand).filter(SalesBrand.advertiser_id == target_id).all()}
    moved_brands = 0
    for b in db.query(SalesBrand).filter(SalesBrand.advertiser_id == data.source_id).all():
        twin_id = tgt_brands.get(normalize_name(b.name))
        if twin_id:
            # бренд-дубль: сделки перецепляем на бренд target, дубль удаляем
            db.query(SalesDeal).filter(SalesDeal.brand_id == b.id).update(
                {SalesDeal.brand_id: twin_id}, synchronize_session=False)
            db.query(SalesBrand).filter(SalesBrand.id == b.id).delete(synchronize_session=False)
        else:
            db.query(SalesBrand).filter(SalesBrand.id == b.id).update(
                {SalesBrand.advertiser_id: target_id}, synchronize_session=False)
            tgt_brands[normalize_name(b.name)] = b.id
            moved_brands += 1

    from app.sales.models import SalesDealFieldOverride
    deals_moved = (db.query(SalesDeal).filter(SalesDeal.advertiser_id == data.source_id)
                   .update({SalesDeal.advertiser_id: target_id}, synchronize_session=False))
    db.query(SalesDealFieldOverride).filter(
        SalesDealFieldOverride.field_name == "advertiser_id",
        SalesDealFieldOverride.value_int == data.source_id).update(
        {SalesDealFieldOverride.value_int: target_id}, synchronize_session=False)

    # Перенос связей с Битриксом: компании source переезжают на target (bx_id уникален
    # по kind, коллизий нет). Мастер наследуется, если у target не задан.
    from app.sales.models import SalesBitrixLink
    db.query(SalesBitrixLink).filter(
        SalesBitrixLink.kind == "advertisers", SalesBitrixLink.our_id == data.source_id).update(
        {SalesBitrixLink.our_id: target_id}, synchronize_session=False)
    if not target.bx_master and source.bx_master:
        target.bx_master = source.bx_master
    db.flush()
    _tgt_links = [lk.bx_id for lk in db.query(SalesBitrixLink).filter(
        SalesBitrixLink.kind == "advertisers", SalesBitrixLink.our_id == target_id)
        .order_by(SalesBitrixLink.id).all()]
    if _tgt_links:
        target.bx_id = _tgt_links[0]

    db.query(SalesAdvertiser).filter(SalesAdvertiser.id == data.source_id).delete(
        synchronize_session=False)
    db.commit()
    log_action(db, current_user, "merge_advertiser", "sales_advertiser", target_id,
               f"влит «{dropped_name}»: брендов +{moved_brands}, сделок {deals_moved}")
    return {"message": f"«{dropped_name}» влит в «{target.name}»: "
                       f"брендов перенесено {moved_brands}, сделок {deals_moved}"}


@router.post("/agencies/{target_id}/merge")
def merge_agency(target_id: int, data: MergeIn, db: Session = Depends(get_db),
                 current_user: User = Depends(AG_EDIT)):
    """Вливает source-агентство в target: юрлица переносятся (дубли связи схлопываются),
    сделки и ручные правки переуказываются на target, source удаляется."""
    if data.source_id == target_id:
        raise HTTPException(status_code=400, detail="Нельзя слить агентство с самим собой")
    target = _require(db, SalesAgency, target_id, "Агентство (цель)")
    source = _require(db, SalesAgency, data.source_id, "Агентство (источник)")
    dropped_name = source.name

    tgt_cp = {lk.counterparty_id for lk in db.query(SalesAgencyCounterparty)
              .filter(SalesAgencyCounterparty.agency_id == target_id).all()}
    moved_legals = 0
    for lk in db.query(SalesAgencyCounterparty).filter(SalesAgencyCounterparty.agency_id == data.source_id).all():
        if lk.counterparty_id in tgt_cp:
            db.query(SalesAgencyCounterparty).filter(SalesAgencyCounterparty.id == lk.id).delete(synchronize_session=False)
        else:
            db.query(SalesAgencyCounterparty).filter(SalesAgencyCounterparty.id == lk.id).update(
                {SalesAgencyCounterparty.agency_id: target_id}, synchronize_session=False)
            tgt_cp.add(lk.counterparty_id); moved_legals += 1

    from app.sales.models import SalesDealFieldOverride
    deals_moved = (db.query(SalesDeal).filter(SalesDeal.agency_id == data.source_id)
                   .update({SalesDeal.agency_id: target_id}, synchronize_session=False))
    db.query(SalesDealFieldOverride).filter(
        SalesDealFieldOverride.field_name == "agency_id",
        SalesDealFieldOverride.value_int == data.source_id).update(
        {SalesDealFieldOverride.value_int: target_id}, synchronize_session=False)

    # Перенос связей с Битриксом: компании source переезжают на target (bx_id уникален
    # по kind, коллизий нет). Мастер наследуется, если у target не задан.
    from app.sales.models import SalesBitrixLink
    db.query(SalesBitrixLink).filter(
        SalesBitrixLink.kind == "agencies", SalesBitrixLink.our_id == data.source_id).update(
        {SalesBitrixLink.our_id: target_id}, synchronize_session=False)
    if not target.bx_master and source.bx_master:
        target.bx_master = source.bx_master
    db.flush()
    _tgt_links = [lk.bx_id for lk in db.query(SalesBitrixLink).filter(
        SalesBitrixLink.kind == "agencies", SalesBitrixLink.our_id == target_id)
        .order_by(SalesBitrixLink.id).all()]
    if _tgt_links:
        target.bx_id = _tgt_links[0]

    db.query(SalesAgency).filter(SalesAgency.id == data.source_id).delete(synchronize_session=False)
    db.commit()
    log_action(db, current_user, "merge_agency", "sales_agency", target_id,
               f"влит «{dropped_name}»: юрлиц +{moved_legals}, сделок {deals_moved}")
    return {"message": f"«{dropped_name}» влит в «{target.name}»: "
                       f"юрлиц перенесено {moved_legals}, сделок {deals_moved}"}


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
                 current_user: User = Depends(require_permission("sales_registry", "edit"))):
    # Добавление бренда — по праву «редактирование» в разделе Продажи (sales_registry),
    # тому же, что и правка сделки (решение 2026-07-27). Отдельного права на справочник
    # не требуем: бренды заводят из реестра сделок.
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


class BrandsMove(BaseModel):
    brand_ids: list[int]
    advertiser_id: int   # куда переносим пачку


class BrandsMerge(BaseModel):
    keep_id: int          # бренд, который остаётся
    drop_ids: list[int]   # бренды-дубли, вливаемые в keep


@router.post("/brands/move")
def move_brands(data: BrandsMove, db: Session = Depends(get_db),
                current_user: User = Depends(ADV_EDIT)):
    """Переносит пачку брендов к одному рекламодателю. Если у цели уже есть
    бренд с таким именем — сделки перецепляем на существующий, дубль удаляем,
    иначе просто меняем advertiser_id."""
    _require(db, SalesAdvertiser, data.advertiser_id, "Рекламодатель")
    tgt_brands = {normalize_name(b.name): b.id for b in
                  db.query(SalesBrand).filter(SalesBrand.advertiser_id == data.advertiser_id).all()}
    moved = 0; merged = 0
    for b in db.query(SalesBrand).filter(SalesBrand.id.in_(data.brand_ids)).all():
        if b.advertiser_id == data.advertiser_id:
            continue
        twin_id = tgt_brands.get(normalize_name(b.name))
        if twin_id:
            db.query(SalesDeal).filter(SalesDeal.brand_id == b.id).update(
                {SalesDeal.brand_id: twin_id}, synchronize_session=False)
            db.query(SalesBrand).filter(SalesBrand.id == b.id).delete(synchronize_session=False)
            merged += 1
        else:
            db.query(SalesBrand).filter(SalesBrand.id == b.id).update(
                {SalesBrand.advertiser_id: data.advertiser_id}, synchronize_session=False)
            tgt_brands[normalize_name(b.name)] = b.id
            moved += 1
    db.commit()
    log_action(db, current_user, "move_brands", "sales_advertiser", data.advertiser_id,
               f"перенесено {moved}, схлопнуто дублей {merged}")
    return {"message": f"Перенесено брендов: {moved}" + (f", схлопнуто дублей: {merged}" if merged else "")}


@router.post("/brands/merge")
def merge_brands(data: BrandsMerge, db: Session = Depends(get_db),
                 current_user: User = Depends(ADV_EDIT)):
    """Схлопывает дубли: сделки со всех drop-брендов перецепляет на keep,
    сами drop-бренды удаляет. Для склейки «вольтарен»/«Вольтарен» и т.п."""
    keep = _require(db, SalesBrand, data.keep_id, "Бренд (остаётся)")
    freed = 0
    for bid in data.drop_ids:
        if bid == data.keep_id:
            continue
        moved = (db.query(SalesDeal).filter(SalesDeal.brand_id == bid)
                 .update({SalesDeal.brand_id: data.keep_id}, synchronize_session=False))
        freed += moved
        db.query(SalesBrand).filter(SalesBrand.id == bid).delete(synchronize_session=False)
    db.commit()
    log_action(db, current_user, "merge_brands", "sales_brand", data.keep_id,
               f"в «{keep.name}» влито {len(data.drop_ids)}, сделок {freed}")
    return {"message": f"Схлопнуто в «{keep.name}»: {len(data.drop_ids)} брендов, сделок {freed}"}


@router.get("/brands/duplicates")
def brand_duplicates(db: Session = Depends(get_db), current_user: User = Depends(ADV_VIEW)):
    """Группы брендов с одинаковым нормализованным именем у одного рекламодателя —
    кандидаты на схлопывание («вольтарен» + «Вольтарен»)."""
    rows = db.query(SalesBrand).all()
    groups = {}
    for b in rows:
        groups.setdefault((b.advertiser_id, normalize_name(b.name)), []).append(b)
    adv = dict(db.query(SalesAdvertiser.id, SalesAdvertiser.name).all())
    out = []
    for (adv_id, _key), brands in groups.items():
        if len(brands) > 1:
            out.append({
                "advertiser_id": adv_id,
                "advertiser": adv.get(adv_id),
                "brands": [{"id": b.id, "name": b.name} for b in brands],
            })
    return {"groups": out}


@router.delete("/brands/{brand_id}/hard")
def delete_brand_hard(brand_id: int, db: Session = Depends(get_db),
                      current_user: User = Depends(ADV_DELETE)):
    """Физически удаляет бренд — для мусорных записей (склеенные списки,
    дубли регистра). Сделки, ссылавшиеся на него, теряют ссылку (brand_id=NULL),
    а не блокируют удаление: мусорный бренд не должен цепляться за данные."""
    brand = _require(db, SalesBrand, brand_id, "Бренд")
    freed = (db.query(SalesDeal).filter(SalesDeal.brand_id == brand_id)
             .update({SalesDeal.brand_id: None}, synchronize_session=False))
    name = brand.name
    db.delete(brand)
    db.commit()
    log_action(db, current_user, "delete_brand_hard", "sales_brand", brand_id,
               f"{name}: освобождено сделок {freed}")
    return {"message": f"Бренд «{name}» удалён (сделок освобождено: {freed})"}


@router.put("/brands/{brand_id}")
def update_brand(brand_id: int, data: BrandIn, db: Session = Depends(get_db),
                 current_user: User = Depends(ADV_EDIT)):
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
                     current_user: User = Depends(ADV_DELETE)):
    brand = _require(db, SalesBrand, brand_id, "Бренд")
    brand.is_active = False
    db.commit()
    log_action(db, current_user, "deactivate_sales_brand", "sales_brand", brand.id, brand.name)
    return {"message": "Бренд скрыт из справочника"}


# ============================== Прайс ==============================

@router.get("/price-list")
def list_price(service_id: Optional[int] = None, only_active: bool = True,
               db: Session = Depends(get_db),
               current_user: User = Depends(ADV_VIEW)):
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
                 current_user: User = Depends(ADV_EDIT)):
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
                 current_user: User = Depends(ADV_EDIT)):
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
                     current_user: User = Depends(ADV_DELETE)):
    item = _require(db, SalesPriceListItem, item_id, "Позиция прайса")
    item.is_active = False
    db.commit()
    log_action(db, current_user, "deactivate_sales_price", "sales_price_list", item.id, str(item.price))
    return {"message": "Позиция прайса скрыта"}
