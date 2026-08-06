"""Медиапланы: генератор + реестр (промежуточный контур аккаунта, пока без записи в
Битрикс/deal.amount). Хранение — 3 версии на group_id (старейшая удаляется). Каждое
«на согласование» = новая версия. Файлы (Excel/PDF) генерируются по запросу."""
import os
from datetime import date
from io import BytesIO

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List

from app.database import get_db
from app.routers.auth import get_current_user
from app.permissions import require_permission
from app.audit import log_action
from app.models import User, Counterparty, RolePermission
from app.sales.models import (SalesMediaPlan, SalesMediaPlanRow, SalesMediaPlanExtra,
                              SalesAdvertiser, SalesBrand, SalesAgency, SalesGeo)

router = APIRouter()
VAT = 0.22
KEEP_VERSIONS = 3
MP_EDIT = require_permission("media_plans_editor", "edit")   # создание/правка МП
MP_REG_VIEW = require_permission("media_plans", "view")       # реестр + выгрузка
MP_REG_EDIT = require_permission("media_plans", "edit")       # удаление из реестра
MP_ED_VIEW = require_permission("media_plans_editor", "view")  # открыть в конструкторе


def _mp_own_only(db: Session, user: User, section: str) -> bool:
    """True → роль видит только свои МП (deals_scope='own'). Admin/all → False."""
    if user.role.key == "admin":
        return False
    row = db.query(RolePermission).filter(RolePermission.role_id == user.role_id,
                                          RolePermission.section == section).first()
    return bool(row) and (row.deals_scope or "all") == "own"


def _plan_owned(p, user) -> bool:
    """«Свой» МП: пользователь его создал либо назначен ответственным (продавец/аккаунт/
    трафик). Ответственные хранят id пользователя (см. роль-based модель)."""
    uid = user.id
    return (p.created_by == uid or p.sales_rep_id == uid
            or p.account_manager_id == uid or p.traffic_manager_id == uid)


def _guard_owned(db, plan, user, section):
    """403, если роль 'own' и МП не принадлежит пользователю."""
    if _mp_own_only(db, user, section) and not _plan_owned(plan, user):
        raise HTTPException(status_code=403, detail="Доступ только к своим медиапланам")


class MpRowIn(BaseModel):
    position: Optional[str] = None
    format: Optional[str] = None
    model: Optional[str] = None
    inventory: Optional[str] = None   # 'web' / 'app' / 'cross'
    volume: Optional[float] = 0
    unit_price: Optional[float] = 0
    discount: Optional[float] = 0
    forecast: Optional[dict] = None


class MpExtraIn(BaseModel):
    name: Optional[str] = None
    period: Optional[str] = None
    mode: Optional[str] = None
    price: Optional[float] = 0
    total: Optional[float] = 0


class MpIn(BaseModel):
    group_id: Optional[int] = None      # если задан — добавляем версию к существующему МП
    status: Optional[str] = "draft"     # draft/review/approved/rejected/archived
    title: Optional[str] = None
    advertiser_id: Optional[int] = None
    brand_id: Optional[int] = None
    agency_id: Optional[int] = None
    payer_counterparty_id: Optional[int] = None
    period: Optional[str] = None
    geo_id: Optional[int] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    targeting: Optional[dict] = None
    goals: Optional[dict] = None
    sales_rep_id: Optional[int] = None
    account_manager_id: Optional[int] = None
    traffic_manager_id: Optional[int] = None
    deal_id: Optional[int] = None
    rows: List[MpRowIn] = []
    extras: List[MpExtraIn] = []


def _row_net(r):
    if not (r.position and r.volume and r.unit_price):
        return 0
    # Формула зависит от модели: CPM — за 1000, иначе кол-во×цена (Fix/CPC).
    div = 1000 if (getattr(r, "model", None) or "") == "CPM" else 1
    return round((r.volume or 0) * (r.unit_price or 0) * (1 - (r.discount or 0)) / div)


def _xlsx_safe(v):
    """Защита от formula/CSV-injection: значения, начинающиеся с = + - @, Excel исполняет
    как формулу/DDE. Экранируем ведущей кавычкой (для внешнего клиента, открывающего файл)."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return "'" + v
    return v


def _amounts(rows, extras):
    place = sum(_row_net(r) for r in rows)
    extra = sum((e.total or 0) for e in extras)
    net = place + extra
    return net, round(net * (1 + VAT))


def _apply_fields(p, data: MpIn):
    for f in ("status", "title", "advertiser_id", "brand_id", "agency_id", "payer_counterparty_id",
              "period", "geo_id", "date_from", "date_to", "targeting", "goals",
              "sales_rep_id", "account_manager_id", "traffic_manager_id", "deal_id"):
        setattr(p, f, getattr(data, f))
    net, gross = _amounts(data.rows, data.extras)
    p.amount_net, p.amount_gross = net, gross


def _write_children(db, plan_id, data: MpIn):
    db.query(SalesMediaPlanRow).filter(SalesMediaPlanRow.plan_id == plan_id).delete()
    db.query(SalesMediaPlanExtra).filter(SalesMediaPlanExtra.plan_id == plan_id).delete()
    for i, r in enumerate(data.rows):
        db.add(SalesMediaPlanRow(plan_id=plan_id, sort_order=i, position=r.position, format=r.format,
                                 model=r.model, inventory=r.inventory, volume=r.volume, unit_price=r.unit_price,
                                 discount=r.discount, forecast=r.forecast or {}))
    for i, e in enumerate(data.extras):
        db.add(SalesMediaPlanExtra(plan_id=plan_id, sort_order=i, name=e.name, period=e.period,
                                   mode=e.mode, price=e.price, total=e.total))


def _enforce_cap(db, group_id):
    versions = (db.query(SalesMediaPlan).filter(SalesMediaPlan.group_id == group_id)
                .order_by(SalesMediaPlan.version.desc()).all())
    for old in versions[KEEP_VERSIONS:]:
        db.delete(old)   # каскад удалит строки/доп. услуги


@router.post("")
def create_media_plan(data: MpIn, db: Session = Depends(get_db), current_user: User = Depends(MP_EDIT)):
    """Новый МП или новая версия существующего (если задан group_id). Держим 3 версии."""
    if data.group_id:
        # Добавляем версию к существующей группе — проверяем own-scope против неё (F1),
        # иначе own-роль могла бы дописать версию в чужой МП и выбить чужие версии по cap.
        existing = (db.query(SalesMediaPlan).filter(SalesMediaPlan.group_id == data.group_id)
                    .order_by(SalesMediaPlan.version.desc()).first())
        if not existing:
            raise HTTPException(status_code=404, detail="Группа медиаплана не найдена")
        _guard_owned(db, existing, current_user, "media_plans_editor")
        version = (existing.version or 0) + 1
    else:
        version = 1
    p = SalesMediaPlan(group_id=data.group_id, version=version, created_by=current_user.id if current_user else None)
    _apply_fields(p, data)
    db.add(p)
    db.flush()
    if not p.group_id:
        p.group_id = p.id
    _write_children(db, p.id, data)
    _enforce_cap(db, p.group_id)
    db.commit()
    db.refresh(p)
    log_action(db, current_user, "create_media_plan", "media_plan", p.id, f"{p.title} v{p.version}")
    return {"id": p.id, "group_id": p.group_id, "version": p.version, "status": p.status}


@router.put("/{plan_id}")
def update_media_plan(plan_id: int, data: MpIn, db: Session = Depends(get_db), current_user: User = Depends(MP_EDIT)):
    p = db.query(SalesMediaPlan).filter(SalesMediaPlan.id == plan_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Медиаплан не найден")
    _guard_owned(db, p, current_user, "media_plans_editor")
    # Отправленную/согласованную версию нельзя перетирать черновиком (иначе теряется
    # «версия неизменна»): правки идут только новой версией «на согласование».
    if p.status in ("review", "approved", "archived"):
        raise HTTPException(status_code=409, detail="Нельзя править отправленную/согласованную версию — создайте новую версию «на согласование»")
    _apply_fields(p, data)
    _write_children(db, p.id, data)
    db.commit()
    log_action(db, current_user, "update_media_plan", "media_plan", p.id, f"{p.title} v{p.version}")
    return {"id": p.id, "group_id": p.group_id, "version": p.version, "status": p.status}


class MpPatch(BaseModel):
    """Частичная правка МП из реестра (без строк размещения). Только присланные поля."""
    title: Optional[str] = None
    agency_id: Optional[int] = None
    advertiser_id: Optional[int] = None
    brand_id: Optional[int] = None
    period: Optional[str] = None
    sales_rep_id: Optional[int] = None
    account_manager_id: Optional[int] = None
    payer_counterparty_id: Optional[int] = None


@router.patch("/{plan_id}")
def patch_media_plan(plan_id: int, data: MpPatch, db: Session = Depends(get_db),
                     current_user: User = Depends(MP_REG_EDIT)):
    """Инлайн-правка поля из реестра (клик по ячейке). Строки/суммы не трогаются."""
    p = db.query(SalesMediaPlan).filter(SalesMediaPlan.id == plan_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Медиаплан не найден")
    _guard_owned(db, p, current_user, "media_plans")
    fields = data.dict(exclude_unset=True)   # только явно присланные (в т.ч. null для сброса)
    for k, v in fields.items():
        setattr(p, k, v)
    db.commit()
    log_action(db, current_user, "patch_media_plan", "media_plan", p.id, ", ".join(fields.keys()))
    return {"ok": True}


def _names(db):
    adv = dict(db.query(SalesAdvertiser.id, SalesAdvertiser.short_name).all())
    advf = dict(db.query(SalesAdvertiser.id, SalesAdvertiser.name).all())
    return {
        "adv": {k: (v or advf.get(k)) for k, v in adv.items()},
        "brand": dict(db.query(SalesBrand.id, SalesBrand.name).all()),
        "agency": dict(db.query(SalesAgency.id, SalesAgency.short_name).all()),
        "user": dict(db.query(User.id, User.name).all()),   # ответственные = пользователи
        "geo": dict(db.query(SalesGeo.id, SalesGeo.name).all()),
        "cp": dict(db.query(Counterparty.id, Counterparty.name).all()),
    }


@router.get("")
def list_media_plans(db: Session = Depends(get_db), current_user: User = Depends(MP_REG_VIEW)):
    """Реестр: последняя версия каждого МП (по group_id). Роль 'own' — только свои."""
    own_only = _mp_own_only(db, current_user, "media_plans")
    rows = db.query(SalesMediaPlan).order_by(SalesMediaPlan.group_id, SalesMediaPlan.version.desc()).all()
    latest = {}
    for p in rows:
        if p.group_id not in latest:
            latest[p.group_id] = p
    if own_only:
        latest = {gid: p for gid, p in latest.items() if _plan_owned(p, current_user)}
    n = _names(db)
    items = [{
        "id": p.id, "group_id": p.group_id, "version": p.version, "status": p.status,
        "title": p.title,
        "advertiser_id": p.advertiser_id, "advertiser": n["adv"].get(p.advertiser_id),
        "brand_id": p.brand_id, "brand": n["brand"].get(p.brand_id),
        "agency_id": p.agency_id, "agency": n["agency"].get(p.agency_id),
        "period": p.period,
        "amount_net": p.amount_net, "amount_gross": p.amount_gross,
        "sales_rep_id": p.sales_rep_id, "sales_rep": n["user"].get(p.sales_rep_id),
        "account_manager_id": p.account_manager_id, "account_manager": n["user"].get(p.account_manager_id),
        "payer_counterparty_id": p.payer_counterparty_id, "payer": n["cp"].get(p.payer_counterparty_id),
        "updated_at": p.updated_at, "deal_id": p.deal_id,
    } for p in sorted(latest.values(), key=lambda x: (x.updated_at or x.created_at or 0), reverse=True)]
    return {"items": items}


def _plan_full(db, p, n):
    rows = db.query(SalesMediaPlanRow).filter(SalesMediaPlanRow.plan_id == p.id).order_by(SalesMediaPlanRow.sort_order).all()
    extras = db.query(SalesMediaPlanExtra).filter(SalesMediaPlanExtra.plan_id == p.id).order_by(SalesMediaPlanExtra.sort_order).all()
    return {
        "id": p.id, "group_id": p.group_id, "version": p.version, "status": p.status, "title": p.title,
        "advertiser_id": p.advertiser_id, "brand_id": p.brand_id, "agency_id": p.agency_id,
        "payer_counterparty_id": p.payer_counterparty_id, "period": p.period, "geo_id": p.geo_id,
        "date_from": p.date_from, "date_to": p.date_to, "targeting": p.targeting or {}, "goals": p.goals or {},
        "sales_rep_id": p.sales_rep_id, "account_manager_id": p.account_manager_id, "traffic_manager_id": p.traffic_manager_id,
        "amount_net": p.amount_net, "amount_gross": p.amount_gross, "deal_id": p.deal_id,
        "created_at": p.created_at, "updated_at": p.updated_at,
        "advertiser": n["adv"].get(p.advertiser_id), "brand": n["brand"].get(p.brand_id), "agency": n["agency"].get(p.agency_id),
        "payer": n["cp"].get(p.payer_counterparty_id), "geo": n["geo"].get(p.geo_id),
        "rows": [{"position": r.position, "format": r.format, "model": r.model, "inventory": r.inventory,
                  "volume": r.volume, "unit_price": r.unit_price, "discount": r.discount, "forecast": r.forecast or {}} for r in rows],
        "extras": [{"name": e.name, "period": e.period, "mode": e.mode, "price": e.price, "total": e.total} for e in extras],
    }


@router.get("/{plan_id}")
def get_media_plan(plan_id: int, db: Session = Depends(get_db), current_user: User = Depends(MP_ED_VIEW)):
    p = db.query(SalesMediaPlan).filter(SalesMediaPlan.id == plan_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Медиаплан не найден")
    _guard_owned(db, p, current_user, "media_plans_editor")
    return _plan_full(db, p, _names(db))


@router.get("/{plan_id}/pdf-data")
def pdf_data(plan_id: int, db: Session = Depends(get_db), current_user: User = Depends(MP_REG_VIEW)):
    """Данные для печатного PDF. Гейт как у выгрузки (media_plans:view) — доступно и из
    реестра, и из конструктора; own-scope по разделу реестра."""
    p = db.query(SalesMediaPlan).filter(SalesMediaPlan.id == plan_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Медиаплан не найден")
    _guard_owned(db, p, current_user, "media_plans")
    return _plan_full(db, p, _names(db))


PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "http://pdf:3001")


@router.get("/{plan_id}/pdf")
def pdf_file(plan_id: int, db: Session = Depends(get_db), current_user: User = Depends(MP_REG_VIEW)):
    """Нативный (текстовый) PDF: данные плана уходят в headless-Chromium сайдкар, который
    рендерит нашу же страницу и печатает её. Доступ проверяется здесь — сайдкар без гейта."""
    p = db.query(SalesMediaPlan).filter(SalesMediaPlan.id == plan_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Медиаплан не найден")
    _guard_owned(db, p, current_user, "media_plans")
    payload = jsonable_encoder({"plan": _plan_full(db, p, _names(db))})
    try:
        r = httpx.post(f"{PDF_SERVICE_URL}/render", json=payload, timeout=60.0)
        r.raise_for_status()
    except Exception:
        raise HTTPException(status_code=502, detail="Сервис генерации PDF недоступен")
    fname = f"MP_{plan_id}_v{p.version}.pdf"
    return StreamingResponse(BytesIO(r.content), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/{plan_id}/versions")
def plan_versions(plan_id: int, db: Session = Depends(get_db), current_user: User = Depends(MP_ED_VIEW)):
    p = db.query(SalesMediaPlan).filter(SalesMediaPlan.id == plan_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Медиаплан не найден")
    _guard_owned(db, p, current_user, "media_plans_editor")
    vs = (db.query(SalesMediaPlan).filter(SalesMediaPlan.group_id == p.group_id)
          .order_by(SalesMediaPlan.version.desc()).all())
    return {"items": [{"id": v.id, "version": v.version, "status": v.status,
                       "amount_gross": v.amount_gross, "updated_at": v.updated_at} for v in vs]}


@router.delete("/{plan_id}")
def delete_media_plan(plan_id: int, whole_group: bool = False, db: Session = Depends(get_db), current_user: User = Depends(MP_REG_EDIT)):
    p = db.query(SalesMediaPlan).filter(SalesMediaPlan.id == plan_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Медиаплан не найден")
    _guard_owned(db, p, current_user, "media_plans")
    if whole_group:
        db.query(SalesMediaPlan).filter(SalesMediaPlan.group_id == p.group_id).delete()
    else:
        db.delete(p)
    db.commit()
    log_action(db, current_user, "delete_media_plan", "media_plan", plan_id, "весь МП" if whole_group else "версия")
    return {"message": "Удалено"}


@router.get("/{plan_id}/export.xlsx")
def export_xlsx(plan_id: int, db: Session = Depends(get_db), current_user: User = Depends(MP_REG_VIEW)):
    p = db.query(SalesMediaPlan).filter(SalesMediaPlan.id == plan_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Медиаплан не найден")
    _guard_owned(db, p, current_user, "media_plans")
    full = _plan_full(db, p, _names(db))
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Медиаплан"
    bold = Font(bold=True)
    hdr = Font(bold=True, color="FFFFFF")
    fill = PatternFill("solid", fgColor="4F6CE6")
    right = Alignment(horizontal="right")
    ws["A1"] = _xlsx_safe(full.get("title") or "Медиаплан")
    ws["A1"].font = Font(bold=True, size=14)
    meta = " · ".join([x for x in [full.get("advertiser"), full.get("brand"), full.get("agency"), full.get("period")] if x])
    ws["A2"] = _xlsx_safe(meta)
    r = 4
    ws.cell(r, 1, "Размещение").font = bold
    r += 1
    inv_label = {"web": "Web", "app": "IN-App", "cross": "Кросс-девайс"}
    cols = ["Позиция", "Формат", "Инвентарь", "Модель", "Объём", "Цена/ед.", "Скидка %", "Бюджет до НДС", "Бюджет с НДС"]
    for c, name in enumerate(cols, 1):
        cell = ws.cell(r, c, name)
        cell.font = hdr
        cell.fill = fill
    r += 1
    for row in full["rows"]:
        net = _row_net(MpRowIn(**{k: row.get(k) for k in ("position", "format", "model", "volume", "unit_price", "discount")}))
        ws.cell(r, 1, _xlsx_safe(row.get("position")))
        ws.cell(r, 2, _xlsx_safe(row.get("format")))
        ws.cell(r, 3, inv_label.get(row.get("inventory") or "cross", "Кросс-девайс"))
        ws.cell(r, 4, _xlsx_safe(row.get("model")))
        ws.cell(r, 5, row.get("volume"))
        ws.cell(r, 6, row.get("unit_price"))
        ws.cell(r, 7, round((row.get("discount") or 0) * 100))
        ws.cell(r, 8, net)
        ws.cell(r, 9, round(net * (1 + VAT)))
        r += 1
    r += 1
    if full["extras"]:
        ws.cell(r, 1, "Доп. услуги").font = bold
        r += 1
        for e in full["extras"]:
            ws.cell(r, 1, _xlsx_safe(e.get("name")))
            ws.cell(r, 2, _xlsx_safe(e.get("period")))
            ws.cell(r, 3, _xlsx_safe(e.get("mode")))
            ws.cell(r, 8, e.get("total"))
            r += 1
        r += 1
    ws.cell(r, 1, "Итого с НДС").font = bold
    ws.cell(r, 8, p.amount_gross).font = bold
    for i, w in enumerate([34, 16, 13, 10, 14, 12, 10, 16, 16], 1):
        ws.column_dimensions[chr(64 + i)].width = w
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"MP_{plan_id}_v{p.version}.xlsx"
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})
