"""
Справочник паблишеров (площадок).

Таблицы созданы миграцией backend/migrations/2026-08-19_publishers.sql.

Грань записи — площадка (сайт), а не поверхность: юрлицо, договор, чат и контакты у
сайта одни, а фигма, статус интеграции и покрытие мест — свои у веба и приложения.
Поэтому поверхности вынесены в отдельную таблицу, а услуги привязаны к паре
«площадка + поверхность»: у услуг с раздельным прайсом web и app — разные тарифы.

Паттерны те же, что в sales_directories.py: APIRouter без префикса, Pydantic рядом
с эндпойнтом, русские тексты ошибок, мягкое удаление через is_active.

Маршруты без параметра объявлены ДО маршрутов с {publisher_id}.
"""
import os
import re
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, case, and_
from sqlalchemy.orm import Session, selectinload
from pydantic import BaseModel
from typing import Optional, List

from app.database import get_db
from app.models import User, Counterparty, Contract, Operation, Article
from app.permissions import require_any_permission
from app.audit import log_action
from app.sales.models import (SalesPublisher, SalesPublisherKind, SalesPublisherSurface,
                              SalesPublisherService, SalesPublisherCounterparty,
                              SalesPublisherContract, SalesPublisherContact, SalesService,
                              PUBLISHER_STATUSES, SURFACE_STATUSES, SURFACE_KINDS,
                              PUBLISHER_DEAL_TYPES, SELF_PROMO_VALUES,
                              SalesPublisherSurfacePlatform, SalesPublisherTraffic, SalesContactPosition,
                              SalesPublisherDocument, SalesDocumentType,
                              PUBLISHER_CONTRACT_ROLES, PLATFORM_KINDS, TRAFFIC_SCOPES,
                              normalize_domain)

router = APIRouter()

# Медиакиты рядом с документами договоров, в том же volume (./uploads:/app/uploads).
UPLOADS_DIR = "/app/uploads/publishers"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                      ".jpg", ".jpeg", ".png", ".zip"}

# Эндпоинты общие для карточки и экрана «Заполнение», поэтому пропускаем по ЛЮБОМУ
# из двух прав. Так сотрудника можно посадить на одно «Заполнение»: правит пачкой,
# а карточка ему открыта только на чтение (это разделение экранов, не защита данных —
# на уровне API оба права дают одни и те же действия).
# Экраны, работающие с одними и теми же эндпоинтами площадки: карточка, «Заполнение» и
# — с 28.08.2026 — настройка кабинетов. Контактные лица заводятся и там: доступ выдаётся
# КОНТАКТУ, и человек, настраивающий кабинет, обязан иметь возможность его завести, не
# уходя на другой экран и не прося чужого права.
PUB_SECTIONS = ("dir_publishers", "dir_publishers_bulk", "dir_publishers_cabinets")
PUB_VIEW = require_any_permission(PUB_SECTIONS, "view")
PUB_EDIT = require_any_permission(PUB_SECTIONS, "edit")


def _require(db: Session, publisher_id: int) -> SalesPublisher:
    p = db.query(SalesPublisher).filter(SalesPublisher.id == publisher_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Площадка не найдена")
    return p


# Префикс имени файла на диске. Вид сущности обязателен: медиакит площадки №7,
# документ договора №7 и документ площадки №7 раньше давали одно и то же имя
# «7_dogovor.pdf» в общем каталоге и молча затирали друг друга.
def _stored_prefix(kind: str, owner_id: int) -> str:
    return f"{kind}{owner_id}_"


def _original_name(owner_id, stored, kind: str = ""):
    """Пользователю показывается то имя, которое он загружал, без служебного префикса.
    Старые файлы лежат с префиксом из одного id — их тоже разбираем."""
    if not stored:
        return None
    for prefix in ([_stored_prefix(kind, owner_id)] if kind else []) + [f"{owner_id}_"]:
        if stored.startswith(prefix):
            return stored[len(prefix):]
    return stored


async def _save_upload(file: UploadFile, owner_id: int, kind: str = "") -> str:
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    original = file.filename or "file"
    ext = os.path.splitext(original)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415,
                            detail=f"Недопустимый тип файла. Разрешены: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413,
                            detail=f"Файл слишком большой (максимум {MAX_UPLOAD_BYTES // 1024 // 1024} МБ)")
    safe = re.sub(r"[^\w.\-]", "_", original)
    stored = f"{_stored_prefix(kind, owner_id)}{safe}"
    with open(os.path.join(UPLOADS_DIR, stored), "wb") as fh:
        fh.write(content)
    return stored


def _clean_code(db: Session, value, current_id: int = None):
    """Постоянный код площадки: верхний регистр, латиница и цифры, до 8 знаков.

    Из него собирается код пары «креатив × площадка» (`HCLA6E-MKS-01`), который уезжает
    в DSP и обратно уже не переименовывается. Отсюда три ограничения:

      · **дефис запрещён** — он разделитель в коде пары, и `MK-S` разъехал бы разбор;
      · **только латиница** — код читают в чужих системах, кириллица там ломается;
      · **уникальность проверяется здесь**, а не только индексом: иначе пользователь
        получит 500 вместо внятного «код занят такой-то площадкой».
    """
    if value is None:
        return None
    code = str(value).strip().upper()
    if not code:
        return None
    if not re.fullmatch(r"[A-Z0-9]{2,8}", code):
        raise HTTPException(status_code=400,
                            detail="Код площадки: 2–8 знаков, латиница и цифры, без дефисов")
    q = db.query(SalesPublisher).filter(SalesPublisher.code == code)
    if current_id is not None:
        q = q.filter(SalesPublisher.id != current_id)
    twin = q.first()
    if twin:
        raise HTTPException(status_code=400,
                            detail=f"Код «{code}» уже занят площадкой «{twin.name}»")
    return code


def _check(value, allowed, label):
    """Значения перечислений сравниваются буквально, поэтому опечатка должна падать
    здесь, а не всплывать позже пустым фильтром в реестре."""
    if value not in (None, "") and value not in allowed:
        raise HTTPException(status_code=400, detail=f"{label}: недопустимое значение «{value}»")
    return value or None


# ============================== Pydantic ==============================

class PublisherIn(BaseModel):
    name: Optional[str] = None
    domain: str
    code: Optional[str] = None
    kind: Optional[str] = None
    status: Optional[str] = None
    network: Optional[str] = None
    deal_type: Optional[str] = None
    intermediary_counterparty_id: Optional[int] = None
    is_exclusive: Optional[bool] = None
    has_dsp: Optional[bool] = None
    # is_priority намеренно отсутствует: приоритезация — услуга каталога, колонка
    # заморожена. Приём поля означал бы вторую правду о том же.
    self_promo: Optional[str] = None
    self_promo_note: Optional[str] = None
    cpm_contract: Optional[float] = None
    basket_note: Optional[str] = None
    note: Optional[str] = None
    chat_title: Optional[str] = None
    chat_url: Optional[str] = None
    chat_url_max: Optional[str] = None
    messenger_note: Optional[str] = None


class SurfaceIn(BaseModel):
    figma_url: Optional[str] = None
    integration_status: Optional[str] = None
    we_work: Optional[bool] = None
    coverage_percent: Optional[float] = None
    note: Optional[str] = None


class ServiceToggleIn(BaseModel):
    surface_kind: str
    service_id: int
    is_active: bool = True


class LinkIn(BaseModel):
    counterparty_id: int


class ContractLinkIn(BaseModel):
    # Либо ссылка в реестр, либо просто номер: договоров площадок в реестре
    # «Договора» по большей части нет, а номер известен и должен быть виден.
    contract_id: Optional[int] = None
    number_raw: Optional[str] = None
    role: Optional[str] = "с площадкой"


class ContactIn(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    telegram: Optional[str] = None
    max_url: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    is_primary: Optional[bool] = False
    note: Optional[str] = None


class KindIn(BaseModel):
    name: str


# ============================== Справочные списки ==============================

@router.get("/meta")
def meta(db: Session = Depends(get_db), current_user: User = Depends(PUB_VIEW)):
    """Всё, что нужно форме заведения и фильтрам реестра, одним запросом."""
    kinds = db.query(SalesPublisherKind).order_by(SalesPublisherKind.sort_order,
                                                  SalesPublisherKind.name).all()
    # Сети не отдельный справочник: список собирается из уже введённого, как виды.
    networks = [n for (n,) in db.query(SalesPublisher.network)
                .filter(SalesPublisher.network.isnot(None))
                .distinct().order_by(SalesPublisher.network).all()]
    services = (db.query(SalesService).filter(SalesService.is_active.is_(True))
                .order_by(SalesService.sort_order, SalesService.name).all())
    svc_counts = dict(db.query(SalesPublisherService.service_id,
                               func.count(func.distinct(SalesPublisherService.publisher_id)))
                      .group_by(SalesPublisherService.service_id).all())
    return {"statuses": PUBLISHER_STATUSES,
            "surface_statuses": SURFACE_STATUSES,
            "surface_kinds": SURFACE_KINDS,
            "platform_kinds": PLATFORM_KINDS,
            "traffic_scopes": TRAFFIC_SCOPES,
            "deal_types": PUBLISHER_DEAL_TYPES,
            "self_promo": SELF_PROMO_VALUES,
            "contract_roles": PUBLISHER_CONTRACT_ROLES,
            "kinds": [{"id": k.id, "name": k.name} for k in kinds],
            "doc_types": [{"id": x.id, "name": x.name} for x in
                          db.query(SalesDocumentType)
                          .order_by(SalesDocumentType.sort_order, SalesDocumentType.name).all()],
            "positions": [{"id": x.id, "name": x.name} for x in
                          db.query(SalesContactPosition)
                          .order_by(SalesContactPosition.sort_order,
                                    SalesContactPosition.name).all()],
            "networks": networks,
            # Счётчик рядом с услугой в фильтре: сколько площадок её поддерживают.
            # Одним агрегатом, а не запросом на услугу.
            "services": [{"id": s.id, "name": s.name, "group": s.group,
                          "separate_price": s.separate_price, "color": s.color,
                          "publishers": svc_counts.get(s.id, 0)}
                         for s in services]}


def _add_catalog_value(db, model, name, action, entity, current_user, label):
    """Пополнение накопительного каталога: виды паблишеров, должности контактов, типы
    документов. Логика у всех одна — отличаются только таблица и подпись, поэтому она
    живёт в одном месте: правка (обрезка пробелов, регистр) должна доходить до всех
    сразу, а не до того каталога, о котором вспомнили."""
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail=f"{label} не может быть пустым")
    exists = db.query(model).filter(func.lower(model.name) == name.lower()).first()
    if exists:
        return {"id": exists.id, "name": exists.name, "message": f"{label} уже есть"}
    row = model(name=name, sort_order=999)
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, current_user, action, entity, row.id, name)
    return {"id": row.id, "name": row.name, "message": f"{label} добавлен"}


@router.post("/kinds")
def add_kind(data: KindIn, db: Session = Depends(get_db), current_user: User = Depends(PUB_EDIT)):
    """Новый вид паблишера. Заводится из карточки — отдельного раздела нет намеренно."""
    return _add_catalog_value(db, SalesPublisherKind, data.name, "create_publisher_kind",
                              "sales_publisher_kind", current_user, "Вид паблишера")


@router.post("/positions")
def add_position(data: KindIn, db: Session = Depends(get_db),
                 current_user: User = Depends(PUB_EDIT)):
    """Должность контактного лица. Каталог общий на все площадки."""
    return _add_catalog_value(db, SalesContactPosition, data.name, "create_contact_position",
                              "sales_contact_position", current_user, "Должность")


@router.post("/doc-types")
def add_doc_type(data: KindIn, db: Session = Depends(get_db),
                 current_user: User = Depends(PUB_EDIT)):
    """Тип документа площадки: медиакит, ТТ на баннеры, доп. инструкции."""
    return _add_catalog_value(db, SalesDocumentType, data.name, "create_document_type",
                              "sales_document_type", current_user, "Тип документа")


@router.get("/contracts-by-counterparty")
def contracts_by_counterparty(counterparty_id: int, db: Session = Depends(get_db),
                              current_user: User = Depends(PUB_VIEW)):
    """Договоры выбранного юрлица — чтобы при правке площадки номер выбирался из
    реестра, а не вводился руками. Отдаётся вид и номер, как в карточке контрагента."""
    rows = (db.query(Contract).filter(Contract.counterparty_id == counterparty_id)
            .order_by(Contract.contract_date.desc().nullslast(), Contract.id.desc()).all())
    return {"items": [{"id": c.id, "number": c.contract_number,
                       "date": c.contract_date.isoformat() if c.contract_date else None,
                       "kind": c.cooperation_format or c.marketing_name,
                       "counterparty": c.counterparty_name} for c in rows]}


# ============================== Реестр ==============================

@router.get("")
def list_publishers(status: Optional[str] = None,
                    kind: Optional[str] = None, network: Optional[str] = None,
                    q: Optional[str] = None, service_id: Optional[List[int]] = Query(None),
                    db: Session = Depends(get_db), current_user: User = Depends(PUB_VIEW)):
    # Архив — это статус площадки, отдельного признака «скрыта» нет: колонка is_active
    # заморожена, и фильтровать по ней значило бы иметь два способа спрятать запись.
    query = db.query(SalesPublisher)
    if status:
        query = query.filter(SalesPublisher.status == status)
    if kind:
        query = query.filter(SalesPublisher.kind == kind)
    if network:
        query = query.filter(SalesPublisher.network == network)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.filter(or_(func.lower(SalesPublisher.name).like(like),
                                 SalesPublisher.domain.like(like)))
    if service_id:
        # Площадка попадает в выборку, если поддерживает ЛЮБУЮ из выбранных услуг:
        # фильтр отвечает на «кто это умеет», а не «у кого ровно этот набор».
        query = query.filter(SalesPublisher.id.in_(
            db.query(SalesPublisherService.publisher_id)
            .filter(SalesPublisherService.service_id.in_(service_id))))
    rows = query.order_by(SalesPublisher.name).all()
    ids = [p.id for p in rows]

    surfaces, supported, contracts, service_list = {}, {}, {}, {}
    if ids:
        for s in (db.query(SalesPublisherSurface)
                  .options(selectinload(SalesPublisherSurface.platforms))
                  .filter(SalesPublisherSurface.publisher_id.in_(ids)).all()):
            surfaces.setdefault(s.publisher_id, {})[s.kind] = {
                "figma_url": s.figma_url, "integration_status": s.integration_status,
                "we_work": s.we_work, "coverage_percent": s.coverage_percent, "note": s.note,
                # Платформы нужны прямо в строке: в реестре Android и iOS показаны
                # отдельными метками, потому что подключаются они врозь.
                "platforms": {pl.kind: {"integration_status": pl.integration_status,
                                        "is_active": pl.is_active}
                              for pl in s.platforms}}
        # Сами услуги в строку: реестр показывает их плашками, чтобы за составом не
        # приходилось открывать сводку. Имена берём одним запросом, не по строке.
        svc_names = dict(db.query(SalesService.id, SalesService.name).all())
        for r in (db.query(SalesPublisherService)
                  .filter(SalesPublisherService.publisher_id.in_(ids),
                          SalesPublisherService.is_active.is_(True)).all()):
            bag = service_list.setdefault(r.publisher_id, {})
            item = bag.setdefault(r.service_id, {"service_id": r.service_id,
                                                 "name": svc_names.get(r.service_id),
                                                 "surfaces": []})
            item["surfaces"].append(r.surface_kind)

        # Счётчик считает то же, что карточка: услуги на поверхностях, с которыми мы
        # РАБОТАЕМ. Одна услуга, отмеченная и в вебе, и в аппе, — одна услуга. Считать
        # здесь все отмеченные значило бы показывать в реестре и в карточке разные
        # числа под одной подписью.
        for pid, bag in service_list.items():
            working = {k for k, sf in surfaces.get(pid, {}).items() if sf["we_work"]}
            supported[pid] = len([1 for item in bag.values()
                                  if working & set(item["surfaces"])])
        # Договоры прямо в строку: номер и юрлицо нужны в реестре, а не только в карточке.
        # Тянем только те договоры и юрлица, что реально встретились в выборке: раньше
        # на каждый показ списка поднимались все договоры и все контрагенты базы.
        links = (db.query(SalesPublisherContract)
                 .filter(SalesPublisherContract.publisher_id.in_(ids)).all())
        contract_ids = {lk.contract_id for lk in links if lk.contract_id}
        c_rows = ({c.id: c for c in db.query(Contract)
                   .filter(Contract.id.in_(contract_ids)).all()} if contract_ids else {})
        cp_ids = {c.counterparty_id for c in c_rows.values() if c.counterparty_id}
        cp_names = (dict(db.query(Counterparty.id, Counterparty.name)
                         .filter(Counterparty.id.in_(cp_ids)).all()) if cp_ids else {})
        for lk in links:
            c = c_rows.get(lk.contract_id) if lk.contract_id else None
            contracts.setdefault(lk.publisher_id, []).append(
                {"contract_id": lk.contract_id, "role": lk.role,
                 "number": (c.contract_number if c else None) or lk.number_raw,
                 "counterparty": (c.counterparty_name if c else None)
                                 or (cp_names.get(c.counterparty_id) if c else None),
                 "linked": bool(c)})

    return {"items": [{"id": p.id, "name": p.name, "domain": p.domain, "code": p.code,
                       "kind": p.kind,
                       "status": p.status, "network": p.network, "deal_type": p.deal_type,
                       "is_exclusive": p.is_exclusive, "has_dsp": p.has_dsp,
                       "our_code": p.our_code, "timezone_offset": p.timezone_offset,
                       "self_promo": p.self_promo,
                       "cpm_contract": p.cpm_contract,
                       "chat_url": p.chat_url, "chat_url_max": p.chat_url_max, "chat_title": p.chat_title,
                       "contracts": contracts.get(p.id, []),
                       "surfaces": surfaces.get(p.id, {}),
                       "services_supported": supported.get(p.id, 0),
                       "services": sorted(service_list.get(p.id, {}).values(),
                                          key=lambda x: x["name"] or ""),
                       } for p in rows]}


@router.post("")
def create_publisher(data: PublisherIn, db: Session = Depends(get_db),
                     current_user: User = Depends(PUB_EDIT)):
    """Форма заведения площадки. Обязателен только домен — он же ключ; название по
    умолчанию равно домену, чтобы запись можно было завести в один шаг и дополнить потом."""
    domain = normalize_domain(data.domain)
    if not domain:
        raise HTTPException(status_code=400, detail="Домен обязателен")
    if db.query(SalesPublisher).filter(SalesPublisher.domain == domain).first():
        raise HTTPException(status_code=400, detail=f"Площадка «{domain}» уже есть в справочнике")
    p = SalesPublisher(
        name=(data.name or "").strip() or domain, domain=domain,
        code=_clean_code(db, data.code),
        kind=(data.kind or "").strip() or None,
        status=_check(data.status, PUBLISHER_STATUSES, "Статус") or "ПЕРЕГОВОРЫ",
        network=(data.network or "").strip() or None,
        deal_type=_check(data.deal_type, PUBLISHER_DEAL_TYPES, "Вид договора"),
        intermediary_counterparty_id=data.intermediary_counterparty_id,
        is_exclusive=bool(data.is_exclusive), has_dsp=bool(data.has_dsp),
        self_promo=_check(data.self_promo, SELF_PROMO_VALUES, "Самореклама"),
        self_promo_note=data.self_promo_note, cpm_contract=data.cpm_contract,
        basket_note=data.basket_note, note=data.note,
        chat_title=data.chat_title, chat_url=data.chat_url,
        chat_url_max=data.chat_url_max, messenger_note=data.messenger_note)
    db.add(p)
    db.commit()
    db.refresh(p)
    log_action(db, current_user, "create_publisher", "sales_publisher", p.id, p.domain)
    return {"id": p.id, "message": "Площадка заведена"}


@router.get("/{publisher_id}")
def get_publisher(publisher_id: int, db: Session = Depends(get_db),
                  current_user: User = Depends(PUB_VIEW)):
    p = _require(db, publisher_id)
    # Имена юрлиц берём только те, что нужны карточке: прикреплённые, посредник и
    # стороны договоров. Раньше поднимался весь реестр контрагентов.
    live_links = [x for x in p.contracts if not x.is_archived]
    contract_ids = {x.contract_id for x in live_links if x.contract_id}
    c_rows = ({c.id: c for c in db.query(Contract)
               .filter(Contract.id.in_(contract_ids)).all()} if contract_ids else {})
    cp_ids = ({lk.counterparty_id for lk in p.counterparties}
              | {c.counterparty_id for c in c_rows.values() if c.counterparty_id})
    if p.intermediary_counterparty_id:
        cp_ids.add(p.intermediary_counterparty_id)
    cp_names = (dict(db.query(Counterparty.id, Counterparty.name)
                     .filter(Counterparty.id.in_(cp_ids)).all()) if cp_ids else {})
    surfaces = {s.kind: {"id": s.id, "figma_url": s.figma_url,
                         "integration_status": s.integration_status,
                         "we_work": s.we_work,
                         "coverage_percent": s.coverage_percent, "note": s.note,
                         # Платформы есть только у приложения; статус APP выводится
                         # как лучший из них, но хранится своим полем.
                         "platforms": {pl.kind: {"id": pl.id,
                                                 "integration_status": pl.integration_status,
                                                 "is_active": pl.is_active, "note": pl.note}
                                       for pl in s.platforms}}
                for s in (db.query(SalesPublisherSurface)
                          .options(selectinload(SalesPublisherSurface.platforms))
                          .filter(SalesPublisherSurface.publisher_id == p.id).all())}
    svc_names = dict(db.query(SalesService.id, SalesService.name).all())
    services = [{"surface_kind": s.surface_kind, "service_id": s.service_id,
                 "service_name": svc_names.get(s.service_id), "is_active": s.is_active,
                 "note": s.note} for s in p.services]
    contracts = []
    for link in live_links:
        c = c_rows.get(link.contract_id) if link.contract_id else None
        contracts.append({"id": link.id, "contract_id": link.contract_id, "role": link.role,
                          # Номер из реестра, если договор найден; иначе тот, что записан
                          # руками — иначе строка выглядела бы пустой.
                          "number": (c.contract_number if c else None) or link.number_raw,
                          "date": c.contract_date.isoformat() if c and c.contract_date else None,
                          "counterparty": (c.counterparty_name if c else None)
                                          or (cp_names.get(c.counterparty_id) if c else None),
                          "linked": bool(c),
                          "document_source": link.document_source,
                          "document_url": link.document_url,
                          "document_filename": _original_name(link.id, link.document_filename, "con")})
    # Показывается последний замер по каждому показателю: в карточке нужна текущая
    # картина, история живёт в самой таблице замеров.
    traffic = {}
    for t in sorted(p.traffic, key=lambda x: x.measured_at):
        traffic[t.scope] = {"value": t.value, "depth": t.depth,
                            "measured_at": t.measured_at.isoformat(), "source": t.source}

    return {"id": p.id, "name": p.name, "domain": p.domain, "code": p.code,
            "kind": p.kind,
            "status": p.status, "network": p.network, "deal_type": p.deal_type,
            "intermediary_counterparty_id": p.intermediary_counterparty_id,
            "intermediary_name": cp_names.get(p.intermediary_counterparty_id),
            "is_exclusive": p.is_exclusive, "has_dsp": p.has_dsp,
            "self_promo": p.self_promo,
            "self_promo_note": p.self_promo_note, "cpm_contract": p.cpm_contract,
            "basket_note": p.basket_note, "note": p.note,
            "chat_title": p.chat_title, "chat_url": p.chat_url,
            "chat_url_max": p.chat_url_max,
            "messenger_note": p.messenger_note,
            "our_code": p.our_code, "shares_data": p.shares_data,
            "timezone_offset": p.timezone_offset,
            "tech_requirements": p.tech_requirements,
            "documents": [{"id": d.id, "doc_type": d.doc_type,
                           "filename": _original_name(d.id, d.filename, "doc"),
                           "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
                           "note": d.note}
                          for d in sorted(p.documents, key=lambda x: x.id)],
            "traffic": traffic,
            "surfaces": surfaces, "services": services, "contracts": contracts,
            "counterparties": [{"counterparty_id": lk.counterparty_id,
                                "name": cp_names.get(lk.counterparty_id)}
                               for lk in p.counterparties],
            "contacts": [{"id": c.id, "name": c.name, "email": c.email,
                          "telegram": c.telegram, "max_url": c.max_url, "phone": c.phone,
                          "role": c.role, "is_primary": c.is_primary, "note": c.note}
                         for c in sorted(p.contacts,
                                         key=lambda x: (not x.is_primary, x.id))]}


class PublisherPatch(BaseModel):
    """Частичная правка: реестр меняет одно поле по клику, а карточка держит заметки,
    корзину и мессенджер, которых в реестре нет. Полный PUT из реестра их бы обнулил."""
    name: Optional[str] = None
    domain: Optional[str] = None
    code: Optional[str] = None
    kind: Optional[str] = None
    status: Optional[str] = None
    network: Optional[str] = None
    deal_type: Optional[str] = None
    cpm_contract: Optional[float] = None
    is_exclusive: Optional[bool] = None
    has_dsp: Optional[bool] = None
    chat_url: Optional[str] = None
    chat_url_max: Optional[str] = None
    chat_title: Optional[str] = None
    self_promo: Optional[str] = None
    self_promo_note: Optional[str] = None
    our_code: Optional[bool] = None
    shares_data: Optional[bool] = None
    timezone_offset: Optional[int] = None
    tech_requirements: Optional[str] = None
    basket_note: Optional[str] = None
    note: Optional[str] = None
    messenger_note: Optional[str] = None
    intermediary_counterparty_id: Optional[int] = None
    # Вложенные сущности приходят целиком и заменяют текущее состояние — карточка
    # присылает то, что видит пользователь на момент «Сохранить».
    surfaces: Optional[dict] = None    # {"web": {exists, we_work, integration_status, ...}}
    services: Optional[List[dict]] = None   # [{surface_kind, service_id}, ...] — весь набор
    traffic: Optional[dict] = None     # {"web": {value, depth}, ...} — замер текущего месяца


def _apply_surfaces(db, publisher_id, payload):
    for kind, body in (payload or {}).items():
        if kind not in SURFACE_KINDS:
            raise HTTPException(status_code=400, detail=f"Неизвестная поверхность «{kind}»")
        row = (db.query(SalesPublisherSurface)
               .filter(SalesPublisherSurface.publisher_id == publisher_id,
                       SalesPublisherSurface.kind == kind).first())
        if not body or body.get("exists") is False:
            # Поверхности нет — вместе с ней уходят отмеченные на ней услуги, иначе
            # в справочнике останутся услуги несуществующего приложения.
            if row:
                (db.query(SalesPublisherService)
                 .filter(SalesPublisherService.publisher_id == publisher_id,
                         SalesPublisherService.surface_kind == kind)
                 .delete(synchronize_session=False))
                db.delete(row)
            continue
        if not row:
            row = SalesPublisherSurface(publisher_id=publisher_id, kind=kind)
            db.add(row)
            db.flush()
        if "integration_status" in body:
            row.integration_status = _check(body["integration_status"], SURFACE_STATUSES,
                                            "Статус интеграции") or "НЕТ"
        if "we_work" in body:
            row.we_work = bool(body["we_work"])
        if "coverage_percent" in body:
            row.coverage_percent = body["coverage_percent"]
        if "figma_url" in body:
            row.figma_url = (body["figma_url"] or "").strip() or None
        if "note" in body:
            row.note = body["note"]

        for pkind, pbody in (body.get("platforms") or {}).items():
            if pkind not in PLATFORM_KINDS:
                raise HTTPException(status_code=400, detail=f"Неизвестная платформа «{pkind}»")
            pl = (db.query(SalesPublisherSurfacePlatform)
                  .filter(SalesPublisherSurfacePlatform.surface_id == row.id,
                          SalesPublisherSurfacePlatform.kind == pkind).first())
            if not pbody or pbody.get("exists") is False:
                if pl:
                    db.delete(pl)
                continue
            if not pl:
                pl = SalesPublisherSurfacePlatform(surface_id=row.id, kind=pkind)
                db.add(pl)
            if "integration_status" in pbody:
                pl.integration_status = _check(pbody["integration_status"], SURFACE_STATUSES,
                                               "Статус интеграции") or "НЕТ"
            if "is_active" in pbody:
                pl.is_active = bool(pbody["is_active"])


def _surface_exists(db, publisher_id, kind) -> bool:
    return bool(db.query(SalesPublisherSurface)
                .filter(SalesPublisherSurface.publisher_id == publisher_id,
                        SalesPublisherSurface.kind == kind).first())


def _apply_services(db, publisher_id, payload):
    """Полная замена набора: карточка присылает все отмеченные пары «услуга +
    поверхность», разбор «что добавили, что сняли» на клиенте только плодил бы ошибки."""
    wanted = {(x.get("surface_kind"), x.get("service_id")) for x in (payload or [])}
    current = {(r.surface_kind, r.service_id): r for r in
               db.query(SalesPublisherService)
               .filter(SalesPublisherService.publisher_id == publisher_id).all()}
    for key, row in current.items():
        if key not in wanted:
            db.delete(row)
    for kind, service_id in wanted:
        if kind not in SURFACE_KINDS or not service_id:
            continue
        if not _surface_exists(db, publisher_id, kind):
            raise HTTPException(status_code=400,
                                detail=f"Поверхность {kind.upper()} не заведена — "
                                       f"услуги на ней отметить нельзя")
        if (kind, service_id) not in current:
            db.add(SalesPublisherService(publisher_id=publisher_id, surface_kind=kind,
                                         service_id=service_id))


def _apply_traffic(db, publisher_id, payload):
    today = datetime.now()
    measured = date(today.year, today.month, 1)
    for scope, body in (payload or {}).items():
        if scope not in TRAFFIC_SCOPES:
            raise HTTPException(status_code=400, detail=f"Неизвестный показатель «{scope}»")
        value = (body or {}).get("value")
        depth = None if scope == "ad_requests" else (body or {}).get("depth")
        row = (db.query(SalesPublisherTraffic)
               .filter(SalesPublisherTraffic.publisher_id == publisher_id,
                       SalesPublisherTraffic.scope == scope,
                       SalesPublisherTraffic.measured_at == measured).first())
        # Пустые значения — это очистка замера, а не «нечего делать»: иначе стёртое
        # в карточке число возвращается после перезагрузки. Замер, которого не было,
        # пустым не заводим — незачем плодить строки с NULL.
        if value is None and depth is None:
            if row:
                db.delete(row)
            continue
        if not row:
            row = SalesPublisherTraffic(publisher_id=publisher_id, scope=scope,
                                        measured_at=measured)
            db.add(row)
        row.value = value
        row.depth = depth
        row.source = "manual"


@router.patch("/{publisher_id}")
def patch_publisher(publisher_id: int, data: PublisherPatch, db: Session = Depends(get_db),
                    current_user: User = Depends(PUB_EDIT)):
    p = _require(db, publisher_id)
    fields = data.dict(exclude_unset=True)
    nested = {key: fields.pop(key) for key in ("surfaces", "services", "traffic")
              if key in fields}
    if "domain" in fields:
        domain = normalize_domain(fields["domain"])
        if not domain:
            raise HTTPException(status_code=400, detail="Домен обязателен")
        if domain != p.domain and db.query(SalesPublisher).filter(
                SalesPublisher.domain == domain, SalesPublisher.id != p.id).first():
            raise HTTPException(status_code=400, detail=f"Площадка «{domain}» уже есть в справочнике")
        fields["domain"] = domain
    if "code" in fields:
        fields["code"] = _clean_code(db, fields["code"], current_id=p.id)
    if "status" in fields:
        _check(fields["status"], PUBLISHER_STATUSES, "Статус")
    if "deal_type" in fields and fields["deal_type"]:
        _check(fields["deal_type"], PUBLISHER_DEAL_TYPES, "Вид договора")
    if "self_promo" in fields and fields["self_promo"]:
        _check(fields["self_promo"], SELF_PROMO_VALUES, "Самореклама")
    # Пустая строка в «сети» и «виде» значит «не задано», а не значение из пробелов:
    # иначе в фильтрах реестра заведётся пустой вариант.
    for key in ("network", "kind", "name"):
        if key in fields:
            fields[key] = (fields[key] or "").strip() or None
    # Домен мог измениться этим же запросом, а поля применяются ниже — берём новый.
    if fields.get("name") is None and "name" in fields:
        fields["name"] = fields.get("domain") or p.domain
    for key, value in fields.items():
        setattr(p, key, value)

    # Вложенные сущности сохраняются в той же транзакции: половина применённых правок
    # хуже, чем ни одной — пользователь увидит смесь старого и нового.
    if "surfaces" in nested:
        _apply_surfaces(db, p.id, nested["surfaces"])
    if "services" in nested:
        _apply_services(db, p.id, nested["services"])
    if "traffic" in nested:
        _apply_traffic(db, p.id, nested["traffic"])

    db.commit()
    log_action(db, current_user, "patch_publisher", "sales_publisher", p.id,
               ", ".join(list(fields.keys()) + list(nested.keys())))
    return {"message": "Сохранено"}


# ============================== Поверхности ==============================

@router.put("/{publisher_id}/surfaces/{kind}")
def upsert_surface(publisher_id: int, kind: str, data: SurfaceIn,
                   db: Session = Depends(get_db), current_user: User = Depends(PUB_EDIT)):
    _require(db, publisher_id)
    if kind not in SURFACE_KINDS:
        raise HTTPException(status_code=400, detail="Поверхность бывает только web или app")
    status = _check(data.integration_status, SURFACE_STATUSES, "Статус интеграции")
    s = (db.query(SalesPublisherSurface)
         .filter(SalesPublisherSurface.publisher_id == publisher_id,
                 SalesPublisherSurface.kind == kind).first())
    if not s:
        s = SalesPublisherSurface(publisher_id=publisher_id, kind=kind)
        db.add(s)
    s.figma_url = data.figma_url or None
    s.integration_status = status or "НЕТ"
    if data.we_work is not None:
        s.we_work = data.we_work
    s.coverage_percent = data.coverage_percent
    s.note = data.note
    db.commit()
    log_action(db, current_user, "set_publisher_surface", "sales_publisher", publisher_id,
               f"{kind}: {s.integration_status}")
    return {"message": "Сохранено"}


@router.delete("/{publisher_id}/surfaces/{kind}")
def delete_surface(publisher_id: int, kind: str, db: Session = Depends(get_db),
                   current_user: User = Depends(PUB_EDIT)):
    """Удаление поверхности означает «её нет» — вместе с ней уходят и её услуги,
    иначе в справочнике остались бы подключённые услуги несуществующего приложения."""
    s = (db.query(SalesPublisherSurface)
         .filter(SalesPublisherSurface.publisher_id == publisher_id,
                 SalesPublisherSurface.kind == kind).first())
    if not s:
        raise HTTPException(status_code=404, detail="Поверхность не заведена")
    db.delete(s)
    (db.query(SalesPublisherService)
     .filter(SalesPublisherService.publisher_id == publisher_id,
             SalesPublisherService.surface_kind == kind).delete(synchronize_session=False))
    db.commit()
    log_action(db, current_user, "delete_publisher_surface", "sales_publisher", publisher_id, kind)
    return {"message": "Поверхность удалена"}


# ============================== Услуги ==============================

@router.put("/{publisher_id}/services")
def toggle_service(publisher_id: int, data: ServiceToggleIn, db: Session = Depends(get_db),
                   current_user: User = Depends(PUB_EDIT)):
    """Галочка активации услуги на поверхности. Снятая галочка удаляет связь, а не
    хранит её выключенной: «услуга не поддерживается» и «услуга не отмечена» — одно и то же."""
    _require(db, publisher_id)
    if data.surface_kind not in SURFACE_KINDS:
        raise HTTPException(status_code=400, detail="Поверхность бывает только web или app")
    svc = db.query(SalesService).filter(SalesService.id == data.service_id).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Услуга не найдена")
    # Услуга живёт на поверхности: отметить её там, где поверхности нет, значит
    # получить состояние, которое сама же карточка показывает как расхождение.
    if data.is_active and not _surface_exists(db, publisher_id, data.surface_kind):
        raise HTTPException(status_code=400,
                            detail=f"Поверхность {data.surface_kind.upper()} не заведена")
    link = (db.query(SalesPublisherService)
            .filter(SalesPublisherService.publisher_id == publisher_id,
                    SalesPublisherService.surface_kind == data.surface_kind,
                    SalesPublisherService.service_id == data.service_id).first())
    if data.is_active and not link:
        db.add(SalesPublisherService(publisher_id=publisher_id,
                                     surface_kind=data.surface_kind,
                                     service_id=data.service_id))
    elif not data.is_active and link:
        db.delete(link)
    db.commit()
    log_action(db, current_user, "set_publisher_service", "sales_publisher", publisher_id,
               f"{data.surface_kind} · {svc.name}: {'да' if data.is_active else 'нет'}")
    return {"message": "Сохранено"}


# ============================== Юрлица и договоры ==============================

@router.post("/{publisher_id}/counterparties")
def attach_counterparty(publisher_id: int, data: LinkIn, db: Session = Depends(get_db),
                        current_user: User = Depends(PUB_EDIT)):
    _require(db, publisher_id)
    cp = db.query(Counterparty).filter(Counterparty.id == data.counterparty_id).first()
    if not cp:
        raise HTTPException(status_code=404, detail="Контрагент не найден")
    if (db.query(SalesPublisherCounterparty)
            .filter(SalesPublisherCounterparty.publisher_id == publisher_id,
                    SalesPublisherCounterparty.counterparty_id == data.counterparty_id).first()):
        raise HTTPException(status_code=400, detail=f"«{cp.name}» уже прикреплён")
    db.add(SalesPublisherCounterparty(publisher_id=publisher_id,
                                      counterparty_id=data.counterparty_id))
    db.commit()
    log_action(db, current_user, "attach_publisher_cp", "sales_publisher", publisher_id, cp.name)
    return {"message": f"«{cp.name}» прикреплён"}


@router.delete("/{publisher_id}/counterparties/{counterparty_id}")
def detach_counterparty(publisher_id: int, counterparty_id: int, db: Session = Depends(get_db),
                        current_user: User = Depends(PUB_EDIT)):
    lk = (db.query(SalesPublisherCounterparty)
          .filter(SalesPublisherCounterparty.publisher_id == publisher_id,
                  SalesPublisherCounterparty.counterparty_id == counterparty_id).first())
    if not lk:
        raise HTTPException(status_code=404, detail="Связь не найдена")
    db.delete(lk)
    db.commit()
    log_action(db, current_user, "detach_publisher_cp", "sales_publisher", publisher_id,
               str(counterparty_id))
    return {"message": "Юрлицо откреплено"}


@router.post("/{publisher_id}/contracts")
def attach_contract(publisher_id: int, data: ContractLinkIn, db: Session = Depends(get_db),
                    current_user: User = Depends(PUB_EDIT)):
    """Договор выбирается только из тех, что прикреплены к юрлицам площадки в реестре
    контрагентов. Свободный ввод номера убран намеренно: набранный руками номер не
    связан ни с чем и через месяц расходится с реестром. Записи, приехавшие номером из
    рабочей таблицы (26 из 47), остаются как есть и помечены ⚠ — их доводят привязкой,
    когда договор появится в реестре.
    """
    _require(db, publisher_id)
    role = _check(data.role, PUBLISHER_CONTRACT_ROLES, "Вид договора") or "с площадкой"

    cp_ids = [lk.counterparty_id for lk in
              db.query(SalesPublisherCounterparty)
              .filter(SalesPublisherCounterparty.publisher_id == publisher_id).all()]
    if not cp_ids:
        raise HTTPException(status_code=400,
                            detail="Сначала прикрепите юрлицо — договор заключается с ним")
    if not data.contract_id:
        raise HTTPException(status_code=400,
                            detail="Договор выбирается из реестра, номер вручную не вводится")

    c = db.query(Contract).filter(Contract.id == data.contract_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Договор не найден")
    # Чужой договор привязать нельзя: он должен принадлежать юрлицу этой площадки.
    if c.counterparty_id not in cp_ids:
        raise HTTPException(status_code=400,
                            detail="Договор принадлежит другому юрлицу — прикрепите его к площадке")
    if (db.query(SalesPublisherContract)
            .filter(SalesPublisherContract.publisher_id == publisher_id,
                    SalesPublisherContract.contract_id == data.contract_id,
                    SalesPublisherContract.role == role).first()):
        raise HTTPException(status_code=400, detail="Договор уже прикреплён")

    db.add(SalesPublisherContract(publisher_id=publisher_id, contract_id=data.contract_id,
                                  number_raw=c.contract_number, role=role))
    db.commit()
    log_action(db, current_user, "attach_publisher_contract", "sales_publisher", publisher_id,
               f"{c.contract_number} ({role})")
    return {"message": "Договор привязан"}


@router.delete("/{publisher_id}/contracts/{link_id}")
def detach_contract(publisher_id: int, link_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(PUB_EDIT)):
    """Удаление по id связи, а не по id договора: у ряда, записанного одним номером,
    договора в реестре нет вовсе."""
    lk = (db.query(SalesPublisherContract)
          .filter(SalesPublisherContract.id == link_id,
                  SalesPublisherContract.publisher_id == publisher_id).first())
    if not lk:
        raise HTTPException(status_code=404, detail="Связь не найдена")
    db.delete(lk)
    db.commit()
    log_action(db, current_user, "detach_publisher_contract", "sales_publisher", publisher_id,
               str(link_id))
    return {"message": "Договор откреплён"}


# ============================== Контакты ==============================

@router.post("/{publisher_id}/contacts")
def add_contact(publisher_id: int, data: ContactIn, db: Session = Depends(get_db),
                current_user: User = Depends(PUB_EDIT)):
    _require(db, publisher_id)
    if not any([data.name, data.email, data.telegram, data.phone]):
        raise HTTPException(status_code=400,
                            detail="Нужно хотя бы имя или один способ связи")
    c = SalesPublisherContact(publisher_id=publisher_id, name=data.name, email=data.email,
                              telegram=data.telegram, max_url=data.max_url, phone=data.phone,
                              role=data.role, is_primary=bool(data.is_primary), note=data.note)
    db.add(c)
    db.commit()
    db.refresh(c)
    log_action(db, current_user, "add_publisher_contact", "sales_publisher", publisher_id,
               data.name or data.email or "")
    return {"id": c.id, "message": "Контакт добавлен"}


@router.put("/{publisher_id}/contacts/{contact_id}")
def update_contact(publisher_id: int, contact_id: int, data: ContactIn,
                   db: Session = Depends(get_db), current_user: User = Depends(PUB_EDIT)):
    c = (db.query(SalesPublisherContact)
         .filter(SalesPublisherContact.id == contact_id,
                 SalesPublisherContact.publisher_id == publisher_id).first())
    if not c:
        raise HTTPException(status_code=404, detail="Контакт не найден")
    # ЧАСТИЧНАЯ правка: присваиваются только присланные поля. Прежняя редакция писала
    # все восемь, поэтому вызов с двумя полями стирал телеграм, телефон и заметку —
    # экран кабинетов правит именно так, по одному-двум полям.
    fields = data.dict(exclude_unset=True)
    for k, v in fields.items():
        setattr(c, k, v)

    # «Главный» у площадки ОДИН: зелёный квадрат на трёх строках ничего не значит.
    # Поэтому назначение снимает пометку с остальных — тем же запросом, а не отдельным
    # действием, иначе между ними существует состояние с двумя главными.
    if fields.get("is_primary"):
        db.query(SalesPublisherContact).filter(
            SalesPublisherContact.publisher_id == publisher_id,
            SalesPublisherContact.id != contact_id).update(
            {"is_primary": False}, synchronize_session=False)
    db.commit()
    log_action(db, current_user, "update_publisher_contact", "sales_publisher", publisher_id,
               data.name or "")
    return {"message": "Сохранено"}


@router.delete("/{publisher_id}/contacts/{contact_id}")
def delete_contact(publisher_id: int, contact_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(PUB_EDIT)):
    c = (db.query(SalesPublisherContact)
         .filter(SalesPublisherContact.id == contact_id,
                 SalesPublisherContact.publisher_id == publisher_id).first())
    if not c:
        raise HTTPException(status_code=404, detail="Контакт не найден")
    # У `cabinet_account.contact_id` стоит ON DELETE SET NULL: удалив контакт с учёткой,
    # мы бы не сломали ничего видимого — учётка осталась бы жить, но с пустым контактом,
    # то есть стала бы неотличима от учётки СЛУЖЕБНОГО кабинета, которую заводят руками.
    # Человек при этом продолжал бы входить. Поэтому порядок обратный: сперва учётка.
    from app.cabinet.models import CabinetAccount
    acc = db.query(CabinetAccount).filter(CabinetAccount.contact_id == c.id).first()
    if acc is not None:
        raise HTTPException(
            status_code=400,
            detail=f"У «{c.name or c.email}» есть учётка в кабинете — "
                   f"сначала уберите доступ, потом контакт")
    db.delete(c)
    db.commit()
    log_action(db, current_user, "delete_publisher_contact", "sales_publisher", publisher_id,
               str(contact_id))
    return {"message": "Контакт удалён"}


# ============================== Платформы приложения ==============================

class PlatformIn(BaseModel):
    integration_status: Optional[str] = None
    is_active: Optional[bool] = None
    note: Optional[str] = None


@router.put("/{publisher_id}/surfaces/app/platforms/{kind}")
def upsert_platform(publisher_id: int, kind: str, data: PlatformIn,
                    db: Session = Depends(get_db), current_user: User = Depends(PUB_EDIT)):
    """Android и iOS живут своими статусами: приложение бывает подключено на одной
    платформе и в подготовке на другой. Платформы существуют только у поверхности app."""
    if kind not in PLATFORM_KINDS:
        raise HTTPException(status_code=400, detail="Платформа бывает только android или ios")
    surface = (db.query(SalesPublisherSurface)
               .filter(SalesPublisherSurface.publisher_id == publisher_id,
                       SalesPublisherSurface.kind == "app").first())
    if not surface:
        raise HTTPException(status_code=400, detail="Сначала заведите поверхность APP")
    status = _check(data.integration_status, SURFACE_STATUSES, "Статус интеграции")
    pl = (db.query(SalesPublisherSurfacePlatform)
          .filter(SalesPublisherSurfacePlatform.surface_id == surface.id,
                  SalesPublisherSurfacePlatform.kind == kind).first())
    if not pl:
        pl = SalesPublisherSurfacePlatform(surface_id=surface.id, kind=kind)
        db.add(pl)
    if status:
        pl.integration_status = status
    if data.is_active is not None:
        pl.is_active = data.is_active
    if data.note is not None:
        pl.note = data.note
    db.commit()
    log_action(db, current_user, "set_publisher_platform", "sales_publisher", publisher_id,
               f"{kind}: {pl.integration_status}")
    return {"message": "Сохранено"}


# ============================== Замеры трафика ==============================

class TrafficIn(BaseModel):
    scope: str
    value: Optional[float] = None
    depth: Optional[float] = None
    measured_at: Optional[str] = None   # «ГГГГ-ММ»; по умолчанию текущий месяц
    source: Optional[str] = "manual"


@router.put("/{publisher_id}/traffic")
def upsert_traffic(publisher_id: int, data: TrafficIn, db: Session = Depends(get_db),
                   current_user: User = Depends(PUB_EDIT)):
    """Трафик — замер на месяц, а не поле карточки. Повторный ввод за тот же месяц
    исправляет замер (решение владельца), поэтому UPSERT, а не INSERT."""
    _require(db, publisher_id)
    if data.scope not in TRAFFIC_SCOPES:
        raise HTTPException(status_code=400, detail=f"Неизвестный показатель «{data.scope}»")
    if data.scope == "ad_requests" and data.depth is not None:
        # У запросов рекламного кода глубины просмотра не существует.
        raise HTTPException(status_code=400, detail="У запросов рекламного кода нет глубины")
    period = (data.measured_at or "").strip()
    if period:
        try:
            measured = date(int(period[:4]), int(period[5:7]), 1)
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail="Месяц замера в формате ГГГГ-ММ")
    else:
        today = datetime.now()
        measured = date(today.year, today.month, 1)

    row = (db.query(SalesPublisherTraffic)
           .filter(SalesPublisherTraffic.publisher_id == publisher_id,
                   SalesPublisherTraffic.scope == data.scope,
                   SalesPublisherTraffic.measured_at == measured).first())
    # Пустое значение — очистка замера, а не замер «ничего». Пустая строка ещё и
    # опаснее отсутствия: карточка показывает ПОСЛЕДНИЙ замер, и NULL за текущий
    # месяц перекрывал бы реальную цифру за прошлый.
    if data.value is None and data.depth is None:
        if row:
            db.delete(row)
        db.commit()
        log_action(db, current_user, "set_publisher_traffic", "sales_publisher", publisher_id,
                   f"{data.scope} {measured:%Y-%m}: очищен")
        return {"message": "Замер очищен", "measured_at": measured.isoformat()}
    if not row:
        row = SalesPublisherTraffic(publisher_id=publisher_id, scope=data.scope,
                                    measured_at=measured)
        db.add(row)
    row.value = data.value
    row.depth = data.depth
    row.source = data.source or "manual"
    db.commit()
    log_action(db, current_user, "set_publisher_traffic", "sales_publisher", publisher_id,
               f"{data.scope} {measured:%Y-%m}: {data.value}")
    return {"message": "Сохранено", "measured_at": measured.isoformat()}


# ============================== Документ договора ==============================

class DocumentIn(BaseModel):
    document_url: str


@router.put("/{publisher_id}/contracts/{link_id}/document-url")
def set_contract_edo(publisher_id: int, link_id: int, data: DocumentIn,
                     db: Session = Depends(get_db), current_user: User = Depends(PUB_EDIT)):
    """Ссылка на ЭДО. Схемы кроме http(s) отклоняются — то же ограничение, что у
    document_link договора: javascript: и data: это XSS, а не адрес документа."""
    lk = (db.query(SalesPublisherContract)
          .filter(SalesPublisherContract.id == link_id,
                  SalesPublisherContract.publisher_id == publisher_id).first())
    if not lk:
        raise HTTPException(status_code=404, detail="Договор не найден")
    url = (data.document_url or "").strip()
    if url and not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400,
                            detail="Ссылка должна начинаться с http:// или https://")
    lk.document_url = url or None
    lk.document_source = "edo" if url else None
    db.commit()
    log_action(db, current_user, "set_publisher_contract_edo", "sales_publisher", publisher_id, url)
    return {"message": "Ссылка сохранена"}


@router.post("/{publisher_id}/contracts/{link_id}/document")
async def upload_contract_document(publisher_id: int, link_id: int, file: UploadFile = File(...),
                                   db: Session = Depends(get_db),
                                   current_user: User = Depends(PUB_EDIT)):
    lk = (db.query(SalesPublisherContract)
          .filter(SalesPublisherContract.id == link_id,
                  SalesPublisherContract.publisher_id == publisher_id).first())
    if not lk:
        raise HTTPException(status_code=404, detail="Договор не найден")
    if lk.document_filename:
        old = os.path.join(UPLOADS_DIR, lk.document_filename)
        if os.path.exists(old):
            os.remove(old)
    stored = await _save_upload(file, link_id, "con")
    lk.document_filename = stored
    lk.document_path = os.path.join(UPLOADS_DIR, stored)
    lk.document_source = "file"
    db.commit()
    log_action(db, current_user, "upload_publisher_contract_doc", "sales_publisher",
               publisher_id, file.filename or "")
    return {"filename": _original_name(link_id, stored, "con"), "message": "Документ прикреплён"}


@router.get("/{publisher_id}/contracts/{link_id}/document")
def download_contract_document(publisher_id: int, link_id: int, db: Session = Depends(get_db),
                               current_user: User = Depends(PUB_VIEW)):
    lk = (db.query(SalesPublisherContract)
          .filter(SalesPublisherContract.id == link_id,
                  SalesPublisherContract.publisher_id == publisher_id).first())
    if not lk or not lk.document_filename:
        raise HTTPException(status_code=404, detail="Документ не приложен")
    path = os.path.join(UPLOADS_DIR, lk.document_filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Файл не найден на сервере")
    return FileResponse(path, filename=_original_name(link_id, lk.document_filename, "con"),
                        media_type="application/octet-stream")


# ============================== Финансы по площадке ==============================

@router.get("/{publisher_id}/finance")
def publisher_finance(publisher_id: int, db: Session = Depends(get_db),
                      current_user: User = Depends(PUB_VIEW)):
    """Операции по юрлицам площадки.

    Про честность цифры: операция привязана к контрагенту, а не к площадке, и одно
    юрлицо стоит за многими площадками (ООО «ДПД Медиа» — за двадцатью). Поэтому вместе
    с суммами отдаётся shared_entities: по каким юрлицам сумма общая и на сколько
    площадок они работают. Без этой пометки карточка одного сайта показывала бы оборот
    двадцати как свой.
    """
    p = _require(db, publisher_id)
    cp_ids = [lk.counterparty_id for lk in p.counterparties]
    if not cp_ids:
        return {"items": [], "kpi": {}, "shared_entities": [], "counterparty_ids": []}

    shared = dict(db.query(SalesPublisherCounterparty.counterparty_id,
                           func.count(func.distinct(SalesPublisherCounterparty.publisher_id)))
                  .filter(SalesPublisherCounterparty.counterparty_id.in_(cp_ids))
                  .group_by(SalesPublisherCounterparty.counterparty_id).all())
    cp_names = dict(db.query(Counterparty.id, Counterparty.name)
                    .filter(Counterparty.id.in_(cp_ids)).all())

    # Сначала оплаченное, планы уходят вниз: в таблице читают факт, а не намерение.
    # Внутри каждой группы — от свежих к старым.
    paid_first = case((func.upper(func.coalesce(Operation.status, "")) == "ОПЛАЧЕНО", 0), else_=1)
    rows = (db.query(Operation).filter(Operation.counterparty_id.in_(cp_ids))
            .order_by(paid_first, Operation.date.desc().nullslast(), Operation.id.desc())
            .limit(500).all())
    articles = dict(db.query(Article.id, Article.name).all())

    # KPI считаются агрегатом по ВСЕМ операциям юрлиц, а не по показанным пятистам:
    # таблица обрезана ради экрана, а сумма выплат обрезанной быть не может — иначе
    # карточка занижает цифру молча, без единого признака усечения.
    # Статусы в базе записаны капсом («ОПЛАЧЕНО», «ПЛАН ОПЛАТ») — сравнение буквальное.
    status_upper = func.upper(func.coalesce(Operation.status, ""))
    agg = (db.query(
                func.coalesce(func.sum(case((status_upper == "ОПЛАЧЕНО",
                                             func.coalesce(Operation.expense, 0)), else_=0)), 0),
                func.coalesce(func.sum(case((status_upper == "ПЛАН ОПЛАТ",
                                             func.coalesce(Operation.expense, 0)), else_=0)), 0),
                func.coalesce(func.sum(case((status_upper == "ОПЛАЧЕНО",
                                             func.coalesce(Operation.income, 0)), else_=0)), 0),
                func.count(case((and_(status_upper == "ОПЛАЧЕНО",
                                      func.coalesce(Operation.expense, 0) != 0), 1), else_=None)))
           .filter(Operation.counterparty_id.in_(cp_ids)).one())
    paid_out, planned_sum, refunds_sum, paid_count = float(agg[0]), float(agg[1]), float(agg[2]), int(agg[3])

    return {
        "counterparty_ids": cp_ids,
        "shared_entities": [{"counterparty_id": cid, "name": cp_names.get(cid),
                             "publishers": cnt} for cid, cnt in shared.items() if cnt > 1],
        # Таблица показывает последние 500 операций, KPI — все.
        "shown": len(rows),
        # refunds — весь приход по операциям юрлиц: возвраты, доплаты и всё, что
        # пришло к нам; в интерфейсе это «Поступления».
        "kpi": {"paid_out": paid_out, "planned": planned_sum, "refunds": refunds_sum,
                "avg_check": (paid_out / paid_count) if paid_count else 0,
                "paid_count": paid_count},
        # У операции нет поля «договор»: связь с договором ведётся номером ДС и счёта,
        # поэтому в таблице показываем их, а не выдуманную колонку.
        "items": [{"id": r.id, "date": r.date.isoformat() if r.date else None,
                   "status": r.status, "counterparty_id": r.counterparty_id,
                   "counterparty": cp_names.get(r.counterparty_id),
                   "ds_num": r.ds_num, "income": r.income, "expense": r.expense,
                   "bank": r.bank, "period": r.period,
                   "article": articles.get(r.article_id),
                   "invoice": r.invoice} for r in rows],
    }


# ============================== Документы площадки ==============================

@router.post("/{publisher_id}/documents")
async def upload_document(publisher_id: int, doc_type: str, file: UploadFile = File(...),
                          db: Session = Depends(get_db), current_user: User = Depends(PUB_EDIT)):
    """Файл площадки с типом. Медиакит — такой же документ, как остальные."""
    _require(db, publisher_id)
    kind = (doc_type or "").strip()
    if not kind:
        raise HTTPException(status_code=400, detail="Выберите тип документа")
    row = SalesPublisherDocument(publisher_id=publisher_id, doc_type=kind, filename="")
    db.add(row)
    db.flush()          # нужен id: он идёт префиксом имени на диске
    stored = await _save_upload(file, row.id, "doc")
    row.filename = stored
    row.path = os.path.join(UPLOADS_DIR, stored)
    row.uploaded_by = current_user.id
    db.commit()
    log_action(db, current_user, "upload_publisher_document", "sales_publisher", publisher_id,
               f"{kind}: {file.filename or ''}")
    return {"id": row.id, "filename": _original_name(row.id, stored, "doc"),
            "message": "Документ загружен"}


@router.get("/{publisher_id}/documents/{doc_id}")
def download_document(publisher_id: int, doc_id: int, db: Session = Depends(get_db),
                      current_user: User = Depends(PUB_VIEW)):
    d = (db.query(SalesPublisherDocument)
         .filter(SalesPublisherDocument.id == doc_id,
                 SalesPublisherDocument.publisher_id == publisher_id).first())
    if not d:
        raise HTTPException(status_code=404, detail="Документ не найден")
    path = os.path.join(UPLOADS_DIR, d.filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Файл не найден на сервере")
    return FileResponse(path, filename=_original_name(d.id, d.filename, "doc"),
                        media_type="application/octet-stream")


@router.delete("/{publisher_id}/documents/{doc_id}")
def delete_document(publisher_id: int, doc_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(PUB_EDIT)):
    d = (db.query(SalesPublisherDocument)
         .filter(SalesPublisherDocument.id == doc_id,
                 SalesPublisherDocument.publisher_id == publisher_id).first())
    if not d:
        raise HTTPException(status_code=404, detail="Документ не найден")
    path = os.path.join(UPLOADS_DIR, d.filename)
    if os.path.exists(path):
        os.remove(path)
    db.delete(d)
    db.commit()
    log_action(db, current_user, "delete_publisher_document", "sales_publisher", publisher_id,
               str(doc_id))
    return {"message": "Документ удалён"}


# ============================== Архив договора ==============================

@router.post("/{publisher_id}/contracts/{link_id}/archive")
def archive_contract(publisher_id: int, link_id: int, restore: bool = False,
                     db: Session = Depends(get_db), current_user: User = Depends(PUB_EDIT)):
    """Договор уходит в архив вместо удаления: по нему шли деньги, и стирать его
    из истории площадки нельзя. Возврат — тем же вызовом с restore=true."""
    lk = (db.query(SalesPublisherContract)
          .filter(SalesPublisherContract.id == link_id,
                  SalesPublisherContract.publisher_id == publisher_id).first())
    if not lk:
        raise HTTPException(status_code=404, detail="Договор не найден")
    lk.is_archived = not restore
    db.commit()
    log_action(db, current_user, "archive_publisher_contract", "sales_publisher", publisher_id,
               f"{lk.number_raw or lk.contract_id}: {'возвращён' if restore else 'в архив'}")
    return {"message": "Договор возвращён" if restore else "Договор убран в архив"}


@router.get("/{publisher_id}/contracts/archived")
def archived_contracts(publisher_id: int, db: Session = Depends(get_db),
                       current_user: User = Depends(PUB_VIEW)):
    rows = (db.query(SalesPublisherContract)
            .filter(SalesPublisherContract.publisher_id == publisher_id,
                    SalesPublisherContract.is_archived.is_(True)).all())
    # Только номера нужных договоров: раньше поднималась вся таблица ради одного-двух.
    ids = {r.contract_id for r in rows if r.contract_id}
    numbers = (dict(db.query(Contract.id, Contract.contract_number)
                    .filter(Contract.id.in_(ids)).all()) if ids else {})
    return {"items": [{"id": r.id, "role": r.role,
                       "number": numbers.get(r.contract_id) or r.number_raw}
                      for r in rows]}
