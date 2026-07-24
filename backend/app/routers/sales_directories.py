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
                              SalesAgencyCounterparty)
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

    return {"items": [{"id": a.id, "name": a.name,
                       "short_name": a.short_name or a.name,
                       "name_en": a.name_en, "name_ru": a.name_ru, "website": a.website,
                       "inn": a.inn, "counterparty_id": a.counterparty_id,
                       "exclude_from_revenue": a.exclude_from_revenue,
                       "is_active": a.is_active,
                       "deals": deal_counts.get(a.id, 0),
                       "brands": by_adv.get(a.id, [])} for a in rows]}


@router.post("/producers")
def create_advertiser(data: AdvertiserIn, db: Session = Depends(get_db),
                      current_user: User = Depends(_EDIT)):
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
                      current_user: User = Depends(_EDIT)):
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
                          current_user: User = Depends(_DELETE)):
    adv = _require(db, SalesAdvertiser, advertiser_id, "Рекламодатель")
    adv.is_active = False
    db.commit()
    log_action(db, current_user, "deactivate_sales_advertiser", "sales_advertiser", adv.id, adv.name)
    return {"message": "Рекламодатель скрыт из справочника"}


# ============================== Воронки ==============================

class PipelineTrack(BaseModel):
    is_tracked: bool


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
    rows = (db.query(SalesPipelineStage)
            .filter(SalesPipelineStage.pipeline_id == pipeline_id)
            .order_by(SalesPipelineStage.sort_order).all())
    return {"items": [{"id": s.id, "status_id": s.status_id, "name": s.name,
                       "deals": counts.get(s.name, 0)} for s in rows],
            "bitrix_category_id": p.bitrix_category_id}


@router.put("/pipelines/{pipeline_id}/tracked")
def set_pipeline_tracked(pipeline_id: int, data: PipelineTrack,
                         db: Session = Depends(get_db),
                         current_user: User = Depends(_EDIT)):
    """Включает/выключает парсинг воронки. Данные не трогает — только флаг.
    При выключении синхронизация перестаёт грузить сделки этой воронки."""
    p = _require(db, SalesPipeline, pipeline_id, "Воронка")
    p.is_tracked = data.is_tracked
    db.commit()
    log_action(db, current_user, "set_pipeline_tracked", "sales_pipeline", p.id,
               f"{p.name}: {'парсить' if data.is_tracked else 'не парсить'}")
    return {"message": "Сохранено", "is_tracked": p.is_tracked}


@router.delete("/pipelines/{pipeline_id}")
def delete_pipeline(pipeline_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(_DELETE)):
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


class CounterpartyLink(BaseModel):
    counterparty_id: int


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

    return {"items": [{"id": a.id,
                       "short_name": a.short_name or a.name,
                       "name_en": a.name_en, "name_ru": a.name_ru,
                       # Исходное полное имя из Битрикса — для опознания, когда
                       # ENG/РУС ещё не размечены. Не теряем то, что было.
                       "full_name": a.name,
                       "holding": a.holding, "is_active": a.is_active, "note": a.note,
                       "counterparties": links.get(a.id, [])} for a in rows]}


@router.post("/agencies")
def create_agency(data: AgencyIn, db: Session = Depends(get_db),
                  current_user: User = Depends(_EDIT)):
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
                  current_user: User = Depends(_EDIT)):
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
                        db: Session = Depends(get_db), current_user: User = Depends(_EDIT)):
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
                        db: Session = Depends(get_db), current_user: User = Depends(_EDIT)):
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
                      current_user: User = Depends(_DELETE)):
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
                          current_user: User = Depends(_VIEW)):
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
                     current_user: User = Depends(_EDIT)):
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

    db.query(SalesAdvertiser).filter(SalesAdvertiser.id == data.source_id).delete(
        synchronize_session=False)
    db.commit()
    log_action(db, current_user, "merge_advertiser", "sales_advertiser", target_id,
               f"влит «{dropped_name}»: брендов +{moved_brands}, сделок {deals_moved}")
    return {"message": f"«{dropped_name}» влит в «{target.name}»: "
                       f"брендов перенесено {moved_brands}, сделок {deals_moved}"}


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


class BrandsMove(BaseModel):
    brand_ids: list[int]
    advertiser_id: int   # куда переносим пачку


class BrandsMerge(BaseModel):
    keep_id: int          # бренд, который остаётся
    drop_ids: list[int]   # бренды-дубли, вливаемые в keep


@router.post("/brands/move")
def move_brands(data: BrandsMove, db: Session = Depends(get_db),
                current_user: User = Depends(_EDIT)):
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
                 current_user: User = Depends(_EDIT)):
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
def brand_duplicates(db: Session = Depends(get_db), current_user: User = Depends(_VIEW)):
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
                      current_user: User = Depends(_DELETE)):
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
