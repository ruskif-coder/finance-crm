"""Медиапланы: генератор + реестр (промежуточный контур аккаунта, пока без записи в
Битрикс/deal.amount). Хранение — 3 версии на group_id (старейшая удаляется). Каждое
«на согласование» = новая версия. Файлы (Excel/PDF) генерируются по запросу."""
import json
import os
from datetime import date
from io import BytesIO

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional, List

from app.database import get_db
from app.routers.auth import get_current_user
from app.permissions import require_permission, ACTION_FIELDS
from app.audit import log_action
from app.notify import emit
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
    # Отметки конструктора: «проверено» по блокам (размещения + прогноз) и
    # необязательный комментарий о причинах изменений при отправке на согласование.
    # Оба — только для журнала: в самой версии МП не хранятся, проставляются заново
    # при каждом сохранении (это чек-лист перед сохранением, а не свойство плана).
    verified: Optional[bool] = None
    change_note: Optional[str] = None


def _is_cpm(model) -> bool:
    """Модель закупки — CPM? Сравнение регистронезависимое и с обрезкой пробелов:
    справочник услуг заполняется руками, и «cpm» вместо «CPM» дало бы объём×цену
    вместо объём/1000×цены — ошибку в тысячу раз, причём молча."""
    return (model or "").strip().upper() == "CPM"


def _row_net(r):
    if not (r.position and r.volume and r.unit_price):
        return 0
    # Формула зависит от модели: CPM — за 1000, иначе кол-во×цена (Fix/CPC).
    div = 1000 if _is_cpm(getattr(r, "model", None)) else 1
    return round((r.volume or 0) * (r.unit_price or 0) * (1 - (r.discount or 0)) / div)


def _fc_metrics(row, net):
    """Прогнозные показатели строки — та же формула, что в конструкторе/PDF (чтобы Excel бился).
    Вход в forecast: freq, ctr(%), cr(%), price, sov(%). Остальное — производное от net/объёма."""
    f = row.get("forecast") or {}
    def pn(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return 0.0
    freq = pn(f.get("freq"))
    ctr_pct, cr_pct, sov_pct = pn(f.get("ctr")), pn(f.get("cr")), pn(f.get("sov"))
    price = pn(f.get("price"))
    imp = row.get("volume") or 0
    reach = imp / freq if freq > 0 else 0
    clicks = imp * ctr_pct / 100
    checks = clicks * cr_pct / 100
    revenue = checks * price
    gross = round(net * (1 + VAT))
    return {
        "freq": freq or None, "reach": reach or None, "imp": imp or None,
        "ctr": ctr_pct or None, "clicks": clicks or None,
        "cpm": (net / imp * 1000) if imp > 0 else None,
        "cpc": (net / clicks) if clicks > 0 else None,
        "cpu": (net / reach) if reach > 0 else None,
        "cr": cr_pct or None, "checks": checks or None,
        "cpo": (net / checks) if checks > 0 else None,
        "price": price or None, "revenue": revenue or None,
        "roi": ((revenue - gross) / gross) if gross > 0 and revenue else None,
        "sov": sov_pct or None,
    }


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


# Сигнатура содержимого МП (шапка + строки + доп.услуги) — для change-detection: новую
# версию создаём только если контент реально изменился. Числа приводим к float (иначе
# int/float-шум из ORM даёт ложное «изменение»); даты — к YYYY-MM-DD.
_SIG_HEAD = ("title", "advertiser_id", "brand_id", "agency_id", "payer_counterparty_id",
             "period", "geo_id", "sales_rep_id", "account_manager_id", "traffic_manager_id")


def _norm(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 6)
    if isinstance(v, dict):
        return {str(k): _norm(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_norm(x) for x in v]
    return v


def _dstr(x):
    if not x:
        return None
    return x.isoformat()[:10] if hasattr(x, "isoformat") else str(x)[:10]


def _content_sig(fields, rows, extras):
    head = {k: getattr(fields, k, None) for k in _SIG_HEAD}
    head["date_from"] = _dstr(getattr(fields, "date_from", None))
    head["date_to"] = _dstr(getattr(fields, "date_to", None))
    head["targeting"] = getattr(fields, "targeting", None) or {}
    head["goals"] = getattr(fields, "goals", None) or {}
    rowd = [{"position": getattr(r, "position", None), "format": getattr(r, "format", None),
             "model": getattr(r, "model", None), "inventory": getattr(r, "inventory", None),
             "volume": getattr(r, "volume", None), "unit_price": getattr(r, "unit_price", None),
             "discount": getattr(r, "discount", None), "forecast": getattr(r, "forecast", None) or {}} for r in rows]
    exd = [{"name": getattr(e, "name", None), "period": getattr(e, "period", None), "mode": getattr(e, "mode", None),
            "price": getattr(e, "price", None), "total": getattr(e, "total", None)} for e in extras]
    return json.dumps(_norm({"h": head, "r": rowd, "e": exd}), sort_keys=True, ensure_ascii=False)


def _plan_content_sig(db, plan):
    rows = db.query(SalesMediaPlanRow).filter(SalesMediaPlanRow.plan_id == plan.id).order_by(SalesMediaPlanRow.sort_order).all()
    extras = db.query(SalesMediaPlanExtra).filter(SalesMediaPlanExtra.plan_id == plan.id).order_by(SalesMediaPlanExtra.sort_order).all()
    return _content_sig(plan, rows, extras)


class LinkDealIn(BaseModel):
    deal_id: Optional[int] = None   # None → отвязать


@router.get("/deals-lookup")
def deals_lookup(q: str = "", sort: str = "id", direction: str = "desc",
                 db: Session = Depends(get_db), current_user: User = Depends(MP_ED_VIEW)):
    """Табличный поиск сделок для привязки МП: поиск по всем полям, сортировка, статус
    «есть ли МП». Только сделки ДО «Брони» включительно (МП привязывают до реализации).
    Доступ по праву конструктора МП (без прав продаж). Объявлен ДО /{plan_id}."""
    from app.sales.models import (SalesDeal, SalesAdvertiser, SalesBrand, SalesAgency,
                                  SalesRep, SalesStage, SalesMediaPlan)
    from app.sales.catalog import Catalog
    from sqlalchemy import or_
    from sqlalchemy.orm import aliased

    cat = Catalog(db)
    # стадии до «Бронь» включительно (по основной цепочке)
    allowed_ids = None
    bron = next((s for s in cat.stages if s.name.strip().lower() == "бронь"), None)
    if bron and bron.id in cat.flow:
        allowed_ids = set(cat.flow[:cat.flow.index(bron.id) + 1])

    adv = aliased(SalesAdvertiser); br = aliased(SalesBrand); ag = aliased(SalesAgency)
    rep = aliased(SalesRep); acc = aliased(SalesRep); st = aliased(SalesStage)
    qy = (db.query(SalesDeal, adv, br, ag, rep, acc, st)
          .outerjoin(adv, adv.id == SalesDeal.advertiser_id)
          .outerjoin(br, br.id == SalesDeal.brand_id)
          .outerjoin(ag, ag.id == SalesDeal.agency_id)
          .outerjoin(rep, rep.id == SalesDeal.sales_rep_id)
          .outerjoin(acc, acc.id == SalesDeal.account_manager_id)
          .outerjoin(st, st.id == SalesDeal.our_stage_id))
    if allowed_ids is not None:
        qy = qy.filter(or_(SalesDeal.our_stage_id.in_(allowed_ids), SalesDeal.our_stage_id.is_(None)))

    qs = (q or "").strip()
    if qs:
        like = f"%{qs}%"
        qy = qy.filter(or_(
            SalesDeal.title.ilike(like), SalesDeal.bitrix_id.ilike(like),
            adv.name.ilike(like), adv.short_name.ilike(like), br.name.ilike(like),
            ag.name.ilike(like), ag.short_name.ilike(like), rep.name.ilike(like), acc.name.ilike(like)))

    sortmap = {"id": SalesDeal.id, "bitrix_id": SalesDeal.bitrix_id, "title": SalesDeal.title,
               "advertiser": adv.name, "brand": br.name, "agency": ag.short_name,
               "sales_rep": rep.name, "account_manager": acc.name,
               "period": SalesDeal.period_from, "amount": SalesDeal.amount, "our_stage": st.sort_order}
    col = sortmap.get(sort, SalesDeal.id)
    qy = qy.order_by(col.desc() if direction == "desc" else col.asc())
    rows = qy.limit(300).all()

    deal_ids = [r[0].id for r in rows]
    mp_deals = set()
    if deal_ids:
        for (did,) in (db.query(SalesMediaPlan.deal_id)
                       .filter(SalesMediaPlan.deal_id.in_(deal_ids)).distinct()):
            mp_deals.add(did)

    items = [{
        "id": d.id, "bitrix_id": d.bitrix_id, "title": d.title,
        "advertiser": (adv_r.short_name or adv_r.name) if adv_r else None,
        "brand": br_r.name if br_r else None,
        "agency": (ag_r.short_name or ag_r.name) if ag_r else None,
        "sales_rep": rep_r.name if rep_r else None,
        "account_manager": acc_r.name if acc_r else None,
        "period": d.period_from.strftime("%Y-%m") if d.period_from else None,
        "amount": d.amount,
        "our_stage": st_r.name if st_r else None,
        "has_mp": d.id in mp_deals,
    } for d, adv_r, br_r, ag_r, rep_r, acc_r, st_r in rows]
    return {"items": items}


@router.post("/{plan_id}/link-deal")
def link_deal(plan_id: int, data: LinkDealIn, db: Session = Depends(get_db),
              current_user: User = Depends(MP_EDIT)):
    """Привязать/отвязать сделку. Пишем во ВСЕ версии группы — связь переживает
    версионирование (новые версии при «на согласование» наследуют её)."""
    p = db.query(SalesMediaPlan).filter(SalesMediaPlan.id == plan_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Медиаплан не найден")
    _guard_owned(db, p, current_user, "media_plans_editor")
    if data.deal_id is not None:
        from app.sales.models import SalesDeal
        if not db.query(SalesDeal).filter(SalesDeal.id == data.deal_id).first():
            raise HTTPException(status_code=400, detail="Сделка не найдена")
    for pl in db.query(SalesMediaPlan).filter(SalesMediaPlan.group_id == p.group_id).all():
        pl.deal_id = data.deal_id
    db.commit()
    log_action(db, current_user, "link_deal_media_plan", "media_plan", p.id, f"deal_id={data.deal_id}")
    return {"message": "Сделка привязана" if data.deal_id else "Привязка снята", "deal_id": data.deal_id}


class DealBriefIn(BaseModel):
    brief: Optional[str] = None


@router.get("/{plan_id}/deal-brief")
def mp_get_deal_brief(plan_id: int, refresh: int = 0, db: Session = Depends(get_db),
                      current_user: User = Depends(MP_ED_VIEW)):
    """Бриф связанной сделки для конструктора МП (по праву МП, без прав продаж).
    Ленивая подгрузка из Битрикса (поле ufCrm_1761318500) + кэш, как в реестре сделок."""
    p = db.query(SalesMediaPlan).filter(SalesMediaPlan.id == plan_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Медиаплан не найден")
    _guard_owned(db, p, current_user, "media_plans_editor")
    from app.sales.models import SalesDeal
    from app.routers.sales_dashboard import BRIEF_FIELD, _deal_is_local
    from datetime import datetime as _dt
    deal = db.query(SalesDeal).filter(SalesDeal.id == p.deal_id).first() if p.deal_id else None
    if not deal:
        return {"has_deal": False, "deal_id": None, "brief": "", "is_local": None, "synced_at": None}
    if (deal.brief is None or refresh) and not _deal_is_local(deal):
        from app.sales.bitrix.transport import vibecode_get
        try:
            r = vibecode_get(f"/deals/{deal.bitrix_id}", {})
            d = (r.get("data") if isinstance(r, dict) else None) or {}
            deal.brief = d.get(BRIEF_FIELD) or ""
            deal.brief_synced_at = _dt.utcnow()
            db.commit()
        except Exception:
            if deal.brief is None:
                raise HTTPException(status_code=502, detail="Битрикс недоступен")
    return {"has_deal": True, "deal_id": deal.id, "brief": deal.brief or "",
            "is_local": _deal_is_local(deal),
            "synced_at": deal.brief_synced_at.isoformat() if deal.brief_synced_at else None}


@router.put("/{plan_id}/deal-brief")
def mp_save_deal_brief(plan_id: int, data: DealBriefIn, db: Session = Depends(get_db),
                       current_user: User = Depends(MP_EDIT)):
    """Сохранение брифа связанной сделки (двусторонняя запись в Битрикс для не-локальных)."""
    p = db.query(SalesMediaPlan).filter(SalesMediaPlan.id == plan_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Медиаплан не найден")
    _guard_owned(db, p, current_user, "media_plans_editor")
    if not p.deal_id:
        raise HTTPException(status_code=400, detail="Медиаплан не привязан к сделке")
    from app.sales.models import SalesDeal
    from app.routers.sales_dashboard import BRIEF_FIELD, _deal_is_local
    from datetime import datetime as _dt
    deal = db.query(SalesDeal).filter(SalesDeal.id == p.deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    text_val = data.brief or ""
    pushed = False
    if not _deal_is_local(deal):
        from app.sales.bitrix.transport import vibecode_patch
        try:
            vibecode_patch(f"/deals/{deal.bitrix_id}", {BRIEF_FIELD: text_val})
            pushed = True
        except Exception:
            raise HTTPException(status_code=502, detail="Битрикс отклонил запись брифа")
    deal.brief = text_val
    deal.brief_synced_at = _dt.utcnow()
    db.commit()
    log_action(db, current_user, "save_deal_brief_mp", "media_plan", p.id, f"бриф {len(text_val)} симв.")
    return {"brief": deal.brief, "pushed_to_bitrix": pushed, "is_local": _deal_is_local(deal)}


def _prefill_rows(db, deal):
    """Строка размещения для нового МП из сделки — собирается так же, как в конвейере
    годового плана (_build_mp): услуга ищется в справочнике по названию, дальше её
    тариф решает всё. Объём = сумма ÷ цену × (CPM → 1000), чтобы бюджет строки сошёлся
    с суммой сделки копейка в копейку.

    Услуги нет в справочнике (свободный текст в сделке) → отдаём Fix-строку
    «объём 1 × сумма»: бюджет всё равно верный, а объём проставят руками."""
    from app.sales.models import SalesService
    name = (deal.product or "").strip()
    amt = float(deal.amount or 0)
    if not name:
        return []
    svc = (db.query(SalesService)
           .filter(func.lower(SalesService.name) == name.lower()).first())
    if not svc:
        return [{"position": name, "format": None, "model": "Fix", "inventory": None,
                 "volume": 1, "unit_price": amt, "discount": 0, "forecast": {}}]
    # inventory строго по прайсу услуги: раздельный → web (дефолт), иначе кросс-девайс
    if svc.separate_price:
        inv, price = "web", svc.unit_price_web
    else:
        inv, price = "cross", svc.unit_price
    volume = (amt / price * (1000 if _is_cpm(svc.calc_form) else 1)) if price and price > 0 else 1
    return [{
        "position": svc.name, "format": svc.placement_type, "model": svc.calc_form,
        "inventory": inv, "volume": volume, "unit_price": price or amt,
        "discount": 0, "forecast": {},
    }]


@router.get("/deal-prefill/{deal_id}")
def mp_deal_prefill(deal_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(MP_ED_VIEW)):
    """Данные сделки для префилла нового МП (создание МП из карточки сделки): реквизиты
    брифа + free-text бриф. Доступ по праву конструктора МП."""
    from app.sales.models import SalesDeal
    from app.routers.sales_dashboard import BRIEF_FIELD, _deal_is_local, _assert_deal_in_scope
    from datetime import datetime as _dt
    from app.sales.models import SalesRep
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    # Область видимости сделок — та же, что в реестре: право конструктора МП открывает
    # конструктор, а не чужие сделки. Здесь читается бриф, то есть содержание сделки.
    _assert_deal_in_scope(db, current_user, deal)
    # Ответственные МП = id ПОЛЬЗОВАТЕЛЕЙ; у сделки — id SalesRep (Битрикс) → user_id
    def _rep_user(rid):
        if not rid:
            return None
        r = db.query(SalesRep.user_id).filter(SalesRep.id == rid).first()
        return r[0] if r else None
    if deal.brief is None and not _deal_is_local(deal):
        from app.sales.bitrix.transport import vibecode_get
        try:
            r = vibecode_get(f"/deals/{deal.bitrix_id}", {})
            d = (r.get("data") if isinstance(r, dict) else None) or {}
            deal.brief = d.get(BRIEF_FIELD) or ""
            deal.brief_synced_at = _dt.utcnow()
            db.commit()
        except Exception:
            pass
    return {
        "deal_id": deal.id, "title": deal.title,
        "advertiser_id": deal.advertiser_id, "brand_id": deal.brand_id,
        "agency_id": deal.agency_id, "payer_counterparty_id": deal.payer_counterparty_id,
        "period": deal.period_from.strftime("%Y-%m") if deal.period_from else None,
        "product": deal.product,   # услуга сделки → первая строка МП
        "amount": deal.amount,     # сумма сделки (без НДС) → сумма первой строки МП
        "rows": _prefill_rows(db, deal),   # готовая строка размещения (как в конвейере)
        "sales_rep_id": _rep_user(deal.sales_rep_id),         # user id (для owners МП)
        "account_manager_id": _rep_user(deal.account_manager_id),
        "brief": deal.brief or "", "is_local": _deal_is_local(deal),
    }


def _advance_deal_after_verify(db, current_user, p):
    """Сделка, рождённая конвейером годового плана, приходит на ПЕРВУЮ стадию
    («МП Подготовка») — её МП собран автоматом и ещё никем не смотрен. В интерфейсе
    такая сделка светится жёлтым: «есть МП, но он не завизирован».

    Аккаунт открывает МП, жмёт обе отметки «Проверено» и сохраняет — вот здесь
    сделка и уходит на следующую стадию, а жёлтый гаснет. Двигаем только с первой
    стадии: если сделка уже дальше, повторное сохранение МП её не откатывает и не
    перепрыгивает вперёд."""
    if not p.deal_id:
        return
    from app.sales.models import SalesDeal
    from app.sales.catalog import Catalog
    deal = db.query(SalesDeal).filter(SalesDeal.id == p.deal_id).first()
    if not deal:
        return
    cat = Catalog(db)
    first = cat.first()
    if not first or deal.our_stage_id != first.id:
        return
    nxt = cat.next_of(first.id)
    if not nxt:
        return
    from app.sales.models import SalesDealStageHistory
    deal.our_stage_id = nxt.id
    # История стадий пишется и здесь: это второе место в системе, которое двигает
    # сделку (первое — /deals/{id}/move). Без этой записи «сколько сделка стоит на
    # стадии» считалось бы от неизвестной даты, а автор перехода терялся.
    db.add(SalesDealStageHistory(deal_id=deal.id, from_stage_id=first.id,
                                 to_stage_id=nxt.id, user_id=current_user.id,
                                 reason="медиаплан проверен и сохранён"))
    db.flush()
    log_action(db, current_user, "move_deal", "sales_deal", deal.id,
               f"{first.name} → {nxt.name} (медиаплан проверен и сохранён)")


def _log_verify_note(db, current_user, p, data):
    """Журнал конструктора: отметка «МП проверен» и комментарий к изменениям.
    Пишем отдельными записями, чтобы их было видно в истории сделки/МП."""
    if getattr(data, "verified", None):
        log_action(db, current_user, "verify_media_plan", "media_plan", p.id,
                   f"МП проверен · {p.title} v{p.version}")
        _advance_deal_after_verify(db, current_user, p)
    note = (getattr(data, "change_note", None) or "").strip()
    if note:
        log_action(db, current_user, "media_plan_change_note", "media_plan", p.id,
                   f"причина изменений: {note[:500]}")


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
        # Новую версию создаём ТОЛЬКО при изменении содержимого. Если контент совпал с
        # последней версией — версию не плодим, лишь при необходимости меняем статус
        # (напр. черновик → «на согласование»).
        if (existing.status in ("draft", "review")
                and _content_sig(data, data.rows, data.extras) == _plan_content_sig(db, existing)):
            if data.status and existing.status != data.status:
                existing.status = data.status
                db.flush()
                log_action(db, current_user, "submit_media_plan", "media_plan", existing.id,
                           f"{existing.title} v{existing.version} → {existing.status} (без изменений содержимого)")
                _log_verify_note(db, current_user, existing, data)
                if existing.status == "review":
                    _notify_submit(db, existing, current_user)
                db.commit()
            return {"id": existing.id, "group_id": existing.group_id, "version": existing.version,
                    "status": existing.status, "unchanged": True}
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
    db.flush()
    log_action(db, current_user, "create_media_plan", "media_plan", p.id, f"{p.title} v{p.version}")
    _log_verify_note(db, current_user, p, data)
    if p.status == "review":
        _notify_submit(db, p, current_user)
    db.commit()
    db.refresh(p)
    return {"id": p.id, "group_id": p.group_id, "version": p.version, "status": p.status}


@router.put("/{plan_id}")
def update_media_plan(plan_id: int, data: MpIn, db: Session = Depends(get_db), current_user: User = Depends(MP_EDIT)):
    p = db.query(SalesMediaPlan).filter(SalesMediaPlan.id == plan_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Медиаплан не найден")
    _guard_owned(db, p, current_user, "media_plans_editor")
    # Отправленную/согласованную версию нельзя перетирать черновиком (иначе теряется
    # «версия неизменна»): правки идут только новой версией «на согласование».
    if p.status in ("review", "approved", "rejected", "archived"):
        raise HTTPException(status_code=409, detail="Нельзя править отправленную/согласованную/отклонённую версию — создайте новую версию «на согласование»")
    _apply_fields(p, data)
    _write_children(db, p.id, data)
    log_action(db, current_user, "update_media_plan", "media_plan", p.id, f"{p.title} v{p.version}")
    _log_verify_note(db, current_user, p, data)
    db.commit()
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


# ── Статус-воркфлоу ──────────────────────────────────────────────────────────
# draft→review (submit, через create); review→approved/rejected/draft(recall);
# approved/rejected→archived. approve/reject/archive — право media_plans:approve.
_MP_TRANSITIONS = {
    "review": {"approved", "rejected", "draft"},
    "approved": {"archived"},
    "rejected": {"archived"},
}


def _has_perm(db, user, section, action):
    if user.role and user.role.key == "admin":
        return True
    row = db.query(RolePermission).filter(RolePermission.role_id == user.role_id,
                                          RolePermission.section == section).first()
    return bool(row) and bool(getattr(row, ACTION_FIELDS.get(action, "can_view"), 0))


def _notify_submit(db, p, actor):
    emit(db, "mp_submit", entity_type="media_plan", entity_id=p.id,
         link=f"/accounts/mp/{p.id}", actor=actor, ctx={"media_plan": p},
         title=f"Новый МП на согласование: {p.title or ('#' + str(p.id))}")


def _notify_status(db, p, frm, to, actor):
    name = p.title or ("#" + str(p.id))
    titles = {"approved": f"МП согласован: {name}", "rejected": f"МП отклонён: {name}",
              "archived": f"МП в архиве: {name}", "draft": f"МП отозван из согласования: {name}"}
    title = titles.get(to)
    if not title:
        return
    # вид события — свой на каждый переход: от него зависят получатели, тон и кнопка.
    # Кому слать, объявлено в реестре (app/notify/registry.py): recall → согласующим,
    # остальные переходы → автору и ответственным по плану.
    event_key = {"approved": "mp_approved", "rejected": "mp_rejected",
                 "archived": "mp_archived", "draft": "mp_recalled"}.get(to)
    if not event_key:
        return
    body = p.reject_reason if to == "rejected" else None
    emit(db, event_key, title=title, body=body, link=f"/accounts/mp/{p.id}",
         entity_type="media_plan", entity_id=p.id, actor=actor, ctx={"media_plan": p})


class MpStatusIn(BaseModel):
    to: str
    comment: Optional[str] = None


@router.post("/{plan_id}/status")
def change_status(plan_id: int, data: MpStatusIn, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    """Переход по стейт-машине. approve/reject/archive — право media_plans:approve
    (само-согласование разрешено); recall review→draft — автор (media_plans_editor)."""
    p = db.query(SalesMediaPlan).filter(SalesMediaPlan.id == plan_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Медиаплан не найден")
    frm, to = p.status, data.to
    if to not in _MP_TRANSITIONS.get(frm, set()):
        raise HTTPException(status_code=409, detail=f"Недопустимый переход: {frm} → {to}")
    if frm == "review" and to == "draft":            # recall — автор отзывает свою заявку
        _guard_owned(db, p, current_user, "media_plans_editor")
    elif not _has_perm(db, current_user, "media_plans", "approve"):
        raise HTTPException(status_code=403, detail="Недостаточно прав для согласования")
    if to == "rejected":
        reason = (data.comment or "").strip()
        if not reason:
            raise HTTPException(status_code=400, detail="Укажите причину отклонения")
        p.reject_reason = reason
    p.status = to
    if to in ("approved", "rejected"):
        p.decided_by = current_user.id
        p.decided_at = func.now()
    db.flush()
    log_action(db, current_user, f"mp_status_{to}", "media_plan", p.id,
               f"{frm}→{to}" + (f": {p.reject_reason}" if to == "rejected" else ""))
    _notify_status(db, p, frm, to, current_user)
    db.commit()
    return {"id": p.id, "status": p.status, "reject_reason": p.reject_reason}


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


def _deal_code(db, deal_id):
    """Наш 6-значный код сделки (см. deal-code) — в интерфейсе показываем его,
    а не внутренний id и не bitrix_id."""
    if not deal_id:
        return None
    from app.sales.models import SalesDeal
    row = db.query(SalesDeal.code).filter(SalesDeal.id == deal_id).first()
    return row[0] if row else None


def _year_plan_of_deal(db, deal_id):
    """Материнский годовой план сделки, к которой прикреплён МП (или None).
    Тот же контракт, что в раскрытии сделки: deal → строка плана → пакет."""
    if not deal_id:
        return None
    from app.sales.models import SalesYearPlanLine, SalesYearPlan, SalesDeal
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if not deal or not deal.year_plan_line_id:
        return None
    ln = db.query(SalesYearPlanLine).filter(SalesYearPlanLine.id == deal.year_plan_line_id).first()
    if not ln:
        return None
    pl = db.query(SalesYearPlan).filter(SalesYearPlan.id == ln.plan_id).first() if ln.plan_id else None
    # Комментарий рекламодателя из формы плана (brief.adv_comment): своя строка,
    # иначе любая соседняя того же плана.
    comment = ((ln.brief or {}).get("adv_comment") or "").strip()
    if not comment and ln.plan_id:
        for sl in db.query(SalesYearPlanLine).filter(SalesYearPlanLine.plan_id == ln.plan_id).all():
            c = ((sl.brief or {}).get("adv_comment") or "").strip()
            if c:
                comment = c
                break
    return {
        "line_id": ln.id, "plan_id": ln.plan_id,
        "title": (pl.title if pl else None),
        "comment": comment or None,
        "year": (pl.year if pl else ln.year),
        "rep_id": (pl.sales_rep_id if pl else ln.sales_rep_id),
        "month": deal.plan_month,
        "deal_code": deal.code,
    }


def _plan_full(db, p, n):
    rows = db.query(SalesMediaPlanRow).filter(SalesMediaPlanRow.plan_id == p.id).order_by(SalesMediaPlanRow.sort_order).all()
    extras = db.query(SalesMediaPlanExtra).filter(SalesMediaPlanExtra.plan_id == p.id).order_by(SalesMediaPlanExtra.sort_order).all()
    return {
        "year_plan": _year_plan_of_deal(db, p.deal_id),
        "id": p.id, "group_id": p.group_id, "version": p.version, "status": p.status, "title": p.title,
        "advertiser_id": p.advertiser_id, "brand_id": p.brand_id, "agency_id": p.agency_id,
        "payer_counterparty_id": p.payer_counterparty_id, "period": p.period, "geo_id": p.geo_id,
        "date_from": p.date_from, "date_to": p.date_to, "targeting": p.targeting or {}, "goals": p.goals or {},
        "sales_rep_id": p.sales_rep_id, "account_manager_id": p.account_manager_id, "traffic_manager_id": p.traffic_manager_id,
        "amount_net": p.amount_net, "amount_gross": p.amount_gross, "deal_id": p.deal_id,
        # наш код сделки — для ссылки «← Сделка XXXXXX» в конструкторе (bitrix_id/внутренний
        # id в интерфейсе не показываем, см. deal-code)
        "deal_code": _deal_code(db, p.deal_id),
        "created_at": p.created_at, "updated_at": p.updated_at,
        "reject_reason": p.reject_reason, "decided_by": p.decided_by, "decided_at": p.decided_at,
        "decided_by_name": n["user"].get(p.decided_by),
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


# Формат листа «МП» — 1-в-1 с эталонным Excel клиента (ДЕНИС МП_Simb-ad).
_MP_BLUE = "FF7299E8"      # заливка шапок таблиц
_MP_INV = {"web": "WEB", "app": "IN-APP", "cross": "Кросс-девайс"}
_MP_UNIT = {"CPM": "Показов", "CPC": "Кликов"}   # ед. измерения объёма по модели
# Примечания и бонус-сноска — из эталонного МП (юротдел согласовал текст).
_MP_NOTES = [
    '1. В случае размещения по модели CPM (единица закупки — "1000 показов"), гарантированными показателями являются количество показов и стоимость закупки за 1000 показов, все остальные показатели являются прогнозными.',
    '2. Плановые показатели прогнозных значений основываются на данных и опыте Команды. Фактические показатели (результаты) рекламной кампании могут измениться как в меньшую, так и в большую сторону. Команда несет ответственность только за ключевые параметры закупки: количество кликов и стоимость за клик (для модели CPC) и кол-во показов и стоимость за 1000 показов (для модели CPM). Команда не дает 100% гарантии достижения прогнозируемых результатов рекламной кампании, указанных в данном медиаплане.',
    '3. Дедлайн предоставления согласованных креативных материалов под все форматы — не менее чем за 2 рабочих дня до старта рекламной кампании. В случае нарушения сроков предоставления исполнитель не может гарантировать своевременный старт рекламной кампании.',
    '4. Медиаплан актуален в течение 14 календарных дней с даты составления.',
    '5. В случае, если после согласования медиаплана и старта РК будут внесены изменения в ключевые KPI и модель закупки медиа-инвентаря, данный медиаплан подлежит перерасчету и согласованию повторно.',
    '6. KPI по CTR подтверждается при условии закупки по CPM и наличии всех форматов из медиаплана. Иначе прогнозные показатели должны быть обновлены.',
]
_MP_BONUS = ('*Бонусом при условии: от 500 000 рублей до НДС на бренд в месяц при первом размещении бренда '
             'или при размещении от 1,5М рублей до НДС в месяц на бренд.')


def _mp_targeting_text(targeting):
    """{группа: [значения]} → 'группа: v1, v2; …' для блока ЦА."""
    if not isinstance(targeting, dict):
        return ""
    parts = []
    for g, vals in targeting.items():
        vals = vals if isinstance(vals, list) else [vals]
        vals = [str(v) for v in vals if v not in (None, "")]
        if vals:
            parts.append(f"{g}: {', '.join(vals)}")
    return "; ".join(parts)


def _wb_programmatic(full, p):
    """Фолбэк: собрать книгу с нуля (если шаблон mp_template.xlsx недоступен)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    wb = Workbook()
    ws = wb.active
    ws.title = "МП"
    ws.sheet_view.showGridLines = False

    F10 = Font(name="Calibri", size=10)
    F10B = Font(name="Calibri", size=10, bold=True)
    HDR = Font(name="Calibri", size=10, bold=True, color="FFFFFFFF")     # белый на синем
    FILL = PatternFill("solid", fgColor=_MP_BLUE)
    thin = Side(style="thin", color="FFBFBFBF")
    BORD = Border(left=thin, right=thin, top=thin, bottom=thin)
    CTR = Alignment(horizontal="center", vertical="center", wrap_text=True)
    LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
    RIGHT = Alignment(horizontal="right", vertical="center")
    MONEY, MONEY0, INT, PCT2, ROI = "#,##0.00", "#,##0", "#,##0", "0.00", "0%"

    def put(r, c, v=None, font=F10, fill=None, align=None, border=None, numfmt=None):
        cell = ws.cell(r, c)
        if v is not None:
            cell.value = _xlsx_safe(v) if isinstance(v, str) else v
        cell.font = font
        if fill:
            cell.fill = fill
        cell.alignment = align or LEFT
        if border:
            cell.border = border
        if numfmt:
            cell.number_format = numfmt
        return cell

    def hdrcell(r, c, v):
        return put(r, c, v, font=HDR, fill=FILL, align=CTR, border=BORD)

    def span(rng, font=HDR, fill=FILL, align=CTR, border=BORD):
        """Стилизуем каждую ячейку диапазона (для видимой заливки под merge), затем merge."""
        cells = ws[rng]
        for row in cells:
            for cell in row:
                cell.font = font
                if fill:
                    cell.fill = fill
                cell.alignment = align
                if border:
                    cell.border = border
        ws.merge_cells(rng)
        return ws[rng.split(":")[0]]

    # ── Шапка: реквизиты (лево) + Итого (право) ─────────────────────────────
    span("B2:C4", font=Font(name="Calibri", size=16, bold=True, color="FF2F5496"),
         fill=None, align=Alignment(horizontal="left", vertical="center"), border=None).value = "SIMB-AD"
    reqs = [("Агентство", full.get("agency")), ("Рекламодатель", full.get("advertiser")),
            ("Бренд", full.get("brand")), ("Название РК", full.get("title")),
            ("Период размещения", full.get("period")),
            ("Дата", (full.get("created_at").strftime("%d.%m.%Y") if full.get("created_at") else date.today().strftime("%d.%m.%Y")))]
    for i, (label, val) in enumerate(reqs):
        rr = 6 + i
        put(rr, 2, label, font=F10B)
        put(rr, 3, val or "—")
    # Таргетинг (B12:B13) + гео (C12) + ЦА (C13)
    span("B12:B13", font=F10B, fill=None, align=Alignment(horizontal="left", vertical="center"), border=None).value = "Таргетинг"
    span("C12:H12", font=F10, fill=None, align=LEFT, border=None).value = full.get("geo") or "—"
    ca = _mp_targeting_text(full.get("targeting"))
    span("C13:H13", font=F10, fill=None, align=LEFT, border=None).value = f"ЦА: {ca}" if ca else "ЦА: —"
    # Итого-блок
    span("E6:H6", font=F10B, fill=None, align=Alignment(horizontal="center", vertical="center"), border=None).value = "Итого"
    net_total, gross_total = full.get("amount_net") or 0, full.get("amount_gross") or 0
    tot = [("Стоимость до НДС", net_total), ("НДС", round(gross_total - net_total)), ("Стоимость с НДС", gross_total)]
    for i, (label, val) in enumerate(tot):
        rr = 7 + i
        span(f"E{rr}:F{rr}", font=F10B, fill=None, align=Alignment(horizontal="left", vertical="center"), border=None).value = label
        span(f"G{rr}:H{rr}", font=F10B, fill=None, align=RIGHT, border=None)
        put(rr, 7, val, font=F10B, align=RIGHT, numfmt=MONEY)

    # ── Таблица размещений: двухстрочная шапка (15–16) ──────────────────────
    H1 = 15
    base_cols = [("B", "Место размещения"), ("C", "Позиция"), ("D", "Гео"), ("E", "Формат"),
                 ("F", "Девайс"), ("G", "Тип ротации (для медийных форматов)"), ("H", "Модель закупки"),
                 ("K", "Период"), ("L", "Сезонный коэффициент"), ("M", "Стоимость за единицу закупки"),
                 ("N", "Стоимость без скидки"), ("O", "Скидка,%"), ("P", "Скидка,руб"),
                 ("Q", "Итоговая стоимость размещения до НДС"), ("R", "НДС 22%"),
                 ("S", "Итоговая стоимость размещения с НДС")]
    for col, name in base_cols:
        span(f"{col}{H1}:{col}{H1+1}").value = name
    span(f"I{H1}:J{H1+1}").value = "Объем размещения"       # I=число, J=ед. изм.
    span(f"T{H1}:AH{H1}").value = "Прогнозные показатели"
    fc_heads = ["Частота\n(max)", "Охват", "Показы", "CTR, %", "Клики", "CPM", "CPC", "CPU",
                "CR,%", "CR, кол-во чеков", "CPО", "Цена", "Доход", "ROI", "SOV,%"]
    for i, name in enumerate(fc_heads):        # T(20)…AH(34)
        hdrcell(H1 + 1, 20 + i, name)

    # ── Строки размещений ───────────────────────────────────────────────────
    r = H1 + 2
    agg = {"vol": 0, "n": 0, "p": 0, "q": 0, "r": 0, "s": 0, "rev": 0}
    for row in full["rows"]:
        net = _row_net(MpRowIn(**{k: row.get(k) for k in ("position", "format", "model", "volume", "unit_price", "discount")}))
        model = row.get("model") or ""
        div = 1000 if _is_cpm(model) else 1
        vol, unit, disc = row.get("volume") or 0, row.get("unit_price") or 0, row.get("discount") or 0
        n_noded = round(vol * unit / div) if (vol and unit) else 0     # до скидки
        disc_rub = n_noded - net
        gross = round(net * (1 + VAT))
        m = _fc_metrics(row, net)
        put(r, 2, "SIMB-AD", align=LEFT, border=BORD)
        put(r, 3, row.get("position"), align=LEFT, border=BORD)
        put(r, 4, full.get("geo") or "—", align=CTR, border=BORD)
        put(r, 5, row.get("format"), align=CTR, border=BORD)
        put(r, 6, _MP_INV.get(row.get("inventory") or "cross", "Кросс-девайс"), align=CTR, border=BORD)
        put(r, 7, "Динамика", align=CTR, border=BORD)
        put(r, 8, model, align=CTR, border=BORD)
        put(r, 9, vol, align=RIGHT, border=BORD, numfmt=INT)
        put(r, 10, _MP_UNIT.get((model or "").strip().upper(), "—"), align=CTR, border=BORD)
        put(r, 11, row.get("period") or full.get("period"), align=CTR, border=BORD)
        put(r, 12, 1, align=CTR, border=BORD, numfmt=INT)
        put(r, 13, unit, align=RIGHT, border=BORD, numfmt=MONEY)
        put(r, 14, n_noded, align=RIGHT, border=BORD, numfmt=MONEY)
        put(r, 15, round(disc * 100), align=CTR, border=BORD, numfmt=INT)
        put(r, 16, disc_rub, align=RIGHT, border=BORD, numfmt=MONEY)
        put(r, 17, net, align=RIGHT, border=BORD, numfmt=MONEY)
        put(r, 18, round(net * VAT), align=RIGHT, border=BORD, numfmt=MONEY)
        put(r, 19, gross, align=RIGHT, border=BORD, numfmt=MONEY)
        # прогноз T…AH
        fc_vals = [(m["freq"], INT), (m["reach"], INT), (m["imp"], INT), (m["ctr"], PCT2),
                   (m["clicks"], INT), (m["cpm"], MONEY0), (m["cpc"], MONEY0), (m["cpu"], MONEY),
                   (m["cr"], PCT2), (m["checks"], INT), (m["cpo"], MONEY0), (m["price"], MONEY0),
                   (m["revenue"], MONEY0), (m["roi"], ROI), (m["sov"], PCT2)]
        for i, (val, nf) in enumerate(fc_vals):
            put(r, 20 + i, val, align=RIGHT if nf != PCT2 else CTR, border=BORD, numfmt=nf)
        agg["vol"] += vol; agg["n"] += n_noded; agg["p"] += disc_rub
        agg["q"] += net; agg["r"] += round(net * VAT); agg["s"] += gross
        agg["rev"] += m["revenue"] or 0
        r += 1
    # ИТОГО по размещениям
    put(r, 2, "ИТОГО:", font=F10B, align=LEFT, border=BORD)
    for c in (3, 4, 5, 6, 7, 8, 10, 11, 12, 13):
        put(r, c, border=BORD)
    put(r, 9, agg["vol"], font=F10B, align=RIGHT, border=BORD, numfmt=INT)
    put(r, 14, agg["n"], font=F10B, align=RIGHT, border=BORD, numfmt=MONEY)
    put(r, 15, "", border=BORD)
    put(r, 16, agg["p"], font=F10B, align=RIGHT, border=BORD, numfmt=MONEY)
    put(r, 17, agg["q"], font=F10B, align=RIGHT, border=BORD, numfmt=MONEY)
    put(r, 18, agg["r"], font=F10B, align=RIGHT, border=BORD, numfmt=MONEY)
    put(r, 19, agg["s"], font=F10B, align=RIGHT, border=BORD, numfmt=MONEY)
    put(r, 32, agg["rev"], font=F10B, align=RIGHT, border=BORD, numfmt=MONEY0)   # AF Доход
    r += 2

    # ── Дополнительные услуги ───────────────────────────────────────────────
    if full["extras"]:
        put(r, 2, "ДОПОЛНИТЕЛЬНЫЕ УСЛУГИ:", font=F10B, align=LEFT)
        r += 1
        for col, name in [("B", "Место размещения"), ("C", "Позиция"), ("K", "Период"),
                          ("L", "Сезонный коэффициент"), ("M", "Стоимость за единицу закупки"),
                          ("N", "Стоимость без скидки"), ("O", "Скидка,%"), ("P", "Скидка,руб"),
                          ("Q", "Итоговая стоимость размещения до НДС"), ("R", "НДС 22%"),
                          ("S", "Итоговая стоимость размещения с НДС")]:
            col_i = {"B": 2, "C": 3, "K": 11, "L": 12, "M": 13, "N": 14, "O": 15, "P": 16, "Q": 17, "R": 18, "S": 19}[col]
            hdrcell(r, col_i, name)
        span(f"I{r}:J{r}").value = "Объем размещения"
        r += 1
        ex = {"n": 0, "p": 0, "q": 0, "r": 0, "s": 0}
        for e in full["extras"]:
            price = e.get("price") or 0
            total = e.get("total") or 0
            disc_rub = round(price - total)
            r_vat = round(total * VAT)
            put(r, 2, "SIMB-AD", align=LEFT, border=BORD)
            put(r, 3, e.get("name"), align=LEFT, border=BORD)
            put(r, 9, 1, align=RIGHT, border=BORD, numfmt=INT)
            put(r, 10, "—", align=CTR, border=BORD)
            put(r, 11, e.get("period") or "—", align=CTR, border=BORD)
            put(r, 12, 1, align=CTR, border=BORD, numfmt=INT)
            put(r, 13, price, align=RIGHT, border=BORD, numfmt=MONEY)
            put(r, 14, price, align=RIGHT, border=BORD, numfmt=MONEY)
            put(r, 15, round((disc_rub / price * 100) if price else 0), align=CTR, border=BORD, numfmt=INT)
            put(r, 16, disc_rub, align=RIGHT, border=BORD, numfmt=MONEY)
            put(r, 17, total, align=RIGHT, border=BORD, numfmt=MONEY)
            put(r, 18, r_vat, align=RIGHT, border=BORD, numfmt=MONEY)
            put(r, 19, round(total + r_vat), align=RIGHT, border=BORD, numfmt=MONEY)
            for c in (4, 5, 6, 7, 8):
                put(r, c, border=BORD)
            ex["n"] += price; ex["p"] += disc_rub; ex["q"] += total
            ex["r"] += r_vat; ex["s"] += round(total + r_vat)
            r += 1
        put(r, 2, "ИТОГО:", font=F10B, align=LEFT, border=BORD)
        for c in (3, 9, 10, 11, 12, 13):
            put(r, c, border=BORD)
        put(r, 14, ex["n"], font=F10B, align=RIGHT, border=BORD, numfmt=MONEY)
        put(r, 16, ex["p"], font=F10B, align=RIGHT, border=BORD, numfmt=MONEY)
        put(r, 17, ex["q"], font=F10B, align=RIGHT, border=BORD, numfmt=MONEY)
        put(r, 18, ex["r"], font=F10B, align=RIGHT, border=BORD, numfmt=MONEY)
        put(r, 19, ex["s"], font=F10B, align=RIGHT, border=BORD, numfmt=MONEY)
        r += 1
        put(r, 2, _MP_BONUS, font=Font(name="Calibri", size=9, italic=True), align=LEFT)
        span(f"B{r}:S{r}", font=Font(name="Calibri", size=9, italic=True), fill=None, align=LEFT, border=None)
        r += 1
    r += 1

    # ── Примечания ──────────────────────────────────────────────────────────
    put(r, 2, "ПРИМЕЧАНИЯ:", font=F10B, align=LEFT)
    r += 1
    for note in _MP_NOTES:
        ws.merge_cells(f"B{r}:S{r}")
        put(r, 2, note, font=Font(name="Calibri", size=9), align=LEFT)
        ws.row_dimensions[r].height = 30
        r += 1

    # ── Ширины колонок (из эталона) ─────────────────────────────────────────
    widths = {"A": 3, "B": 24.3, "C": 45.8, "D": 8, "E": 14, "F": 12, "G": 15, "H": 13,
              "I": 12, "J": 10, "K": 11, "L": 12.4, "M": 15, "N": 13, "O": 9, "P": 12,
              "Q": 15, "R": 12, "S": 15, "T": 9.1, "U": 11, "V": 11, "W": 8, "X": 10,
              "Y": 9.1, "Z": 9, "AA": 9, "AB": 8, "AC": 10.8, "AD": 9.9, "AE": 9,
              "AF": 12.8, "AG": 9.9, "AH": 8}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    ws.row_dimensions[H1].height = 40
    ws.row_dimensions[H1 + 1].height = 28
    return wb


# ── Рендер по пользовательскому шаблону (mp_template.xlsx) ────────────────────
# Шаблон правит аккаунт в Excel; мы лишь подставляем значения в токены {{...}} и
# клонируем строки-образцы размещения ({{r.*}}) и доп.услуги ({{e.*}}) под факт.
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "mp_template.xlsx")
LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "mp_logo.png")


def _insert_logo(ws, coord):
    """Вставить логотип (mp_logo.png) в ячейку-якорь coord (маркер {{logo}}), масштабируя под
    объединённую область. openpyxl теряет встроенные картинки при round-trip, поэтому лого
    добавляем на бэкенде каждый рендер. Без Pillow/файла — молча пропускаем."""
    if not coord:
        return
    path = os.path.abspath(LOGO_PATH)
    if not os.path.exists(path):
        return
    try:
        from openpyxl.drawing.image import Image as XLImage
        from openpyxl.utils import get_column_letter, coordinate_to_tuple
        img = XLImage(path)               # требует Pillow
    except Exception:
        return
    row0, col0 = coordinate_to_tuple(coord)
    box = next(((mr.min_row, mr.max_row, mr.min_col, mr.max_col) for mr in ws.merged_cells.ranges
                if mr.min_row <= row0 <= mr.max_row and mr.min_col <= col0 <= mr.max_col),
               (row0, row0, col0, col0))
    r1, r2, c1, c2 = box
    bw = sum((ws.column_dimensions[get_column_letter(c)].width or 8.43) * 7 + 5 for c in range(c1, c2 + 1))
    bh = sum((ws.row_dimensions[r].height or 15) * 4 / 3 for r in range(r1, r2 + 1))
    if img.width and img.height:
        ratio = min(bw / img.width, bh / img.height) * 0.92   # небольшой внутренний отступ
        img.width, img.height = int(img.width * ratio), int(img.height * ratio)
    ws.add_image(img, get_column_letter(c1) + str(r1))


def _row_ctx(row, full):
    net = _row_net(MpRowIn(**{k: row.get(k) for k in ("position", "format", "model", "volume", "unit_price", "discount")}))
    model = row.get("model") or ""
    div = 1000 if _is_cpm(model) else 1
    vol, unit, disc = row.get("volume") or 0, row.get("unit_price") or 0, row.get("discount") or 0
    n_nodisc = round(vol * unit / div) if (vol and unit) else 0
    m = _fc_metrics(row, net)
    return {
        "r.place": "SIMB-AD", "r.position": row.get("position"), "r.geo": full.get("geo") or "—",
        "r.format": row.get("format"), "r.device": _MP_INV.get(row.get("inventory") or "cross", "Кросс-девайс"),
        "r.rotation": "Динамика", "r.model": model, "r.volume": vol,
        "r.unit_name": _MP_UNIT.get((model or "").strip().upper(), "—"),
        # Период строки, если он у неё свой: на листе «Годовой МП» строки разных
        # месяцев лежат вперемешку, и период шапки (год) их бы не различал.
        "r.period": row.get("period") or full.get("period"), "r.season": 1,
        "r.unit_price": unit, "r.net_nodisc": n_nodisc, "r.disc_pct": round(disc * 100),
        "r.disc_rub": n_nodisc - net, "r.net": net, "r.vat": round(net * VAT), "r.gross": round(net * (1 + VAT)),
        "r.freq": m["freq"], "r.reach": m["reach"], "r.imp": m["imp"], "r.ctr": m["ctr"],
        "r.clicks": m["clicks"], "r.cpm": m["cpm"], "r.cpc": m["cpc"], "r.cpu": m["cpu"],
        "r.cr": m["cr"], "r.checks": m["checks"], "r.cpo": m["cpo"], "r.price": m["price"],
        "r.revenue": m["revenue"], "r.roi": m["roi"], "r.sov": m["sov"],
        "_net": net, "_n_nodisc": n_nodisc, "_disc_rub": n_nodisc - net, "_revenue": m["revenue"] or 0,
    }


def _extra_ctx(e):
    price, total = e.get("price") or 0, e.get("total") or 0
    disc_rub = round(price - total)
    vat = round(total * VAT)
    return {
        "e.place": "SIMB-AD", "e.name": e.get("name"), "e.volume": 1, "e.unit_name": "—",
        "e.period": e.get("period") or "—", "e.season": 1, "e.unit_price": price,
        "e.net_nodisc": price, "e.disc_pct": round((disc_rub / price * 100) if price else 0),
        "e.disc_rub": disc_rub, "e.total": total, "e.vat": vat, "e.gross": round(total + vat),
        "_price": price, "_total": total, "_disc_rub": disc_rub, "_vat": vat, "_gross": round(total + vat),
    }


def _sub_cell(cell, mapping):
    """Подстановка токенов в ячейку. Точный одиночный токен → нативный тип (число/строка/None,
    формат числа берётся из шаблона). Токен внутри текста → строковая замена."""
    import re
    v = cell.value
    if not isinstance(v, str) or "{{" not in v:
        return
    m = re.fullmatch(r"\s*\{\{([\w.]+)\}\}\s*", v)
    if m and m.group(1) in mapping:
        cell.value = mapping[m.group(1)]
        return
    cell.value = re.sub(r"\{\{([\w.]+)\}\}",
                        lambda mm: ("" if mapping.get(mm.group(1)) is None else str(mapping.get(mm.group(1), mm.group(0)))), v)


def _find_token_row(ws, prefix):
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and prefix in cell.value:
                return cell.row
    return None


def _clone_below(ws, src, count):
    """Вставить count копий строки src сразу под ней (стиль+высота+токены), сдвинув merge ниже."""
    from copy import copy
    if count <= 0:
        return
    moved = []
    for mr in list(ws.merged_cells.ranges):
        if mr.min_row > src:
            moved.append((mr.min_row, mr.max_row, mr.min_col, mr.max_col))
            ws.unmerge_cells(str(mr))
    ws.insert_rows(src + 1, count)
    for r1, r2, c1, c2 in moved:
        ws.merge_cells(start_row=r1 + count, end_row=r2 + count, start_column=c1, end_column=c2)
    maxc = ws.max_column
    for k in range(1, count + 1):
        ws.row_dimensions[src + k].height = ws.row_dimensions[src].height
        for c in range(1, maxc + 1):
            s, d = ws.cell(src, c), ws.cell(src + k, c)
            d.value = s.value
            d.font = copy(s.font)
            d.fill = copy(s.fill)
            d.border = copy(s.border)
            d.alignment = copy(s.alignment)
            d.number_format = s.number_format


def _token_cols(ws, row, prefix):
    """{field: буква_колонки} для токенов {{prefix.field}} в строке row."""
    import re
    pat = re.compile(r"\{\{" + re.escape(prefix) + r"\.(\w+)\}\}")
    cols = {}
    for cell in ws[row]:
        if isinstance(cell.value, str):
            m = pat.fullmatch(cell.value.strip())
            if m:
                cols[m.group(1)] = cell.column_letter
    return cols


def _find_token_cell(ws, name):
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and cell.value.strip() == "{{" + name + "}}":
                return cell.coordinate
    return None


def _tg_join(full, key):
    t = full.get("targeting") or {}
    vals = t.get(key) or []
    vals = [str(v) for v in (vals if isinstance(vals, list) else [vals]) if v not in (None, "")]
    return ", ".join(vals) if vals else "—"


def _row_formula_ctx(row, full, C, R):
    """Значения строки размещения: входные — числами (редактируемые), производные — Excel-формулами
    (НДС/итоги/прогноз пересчитываются в файле). Формулы ссылаются на колонки C[field] строки R."""
    def n(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None
    model = row.get("model") or ""
    disc = row.get("discount") or 0
    fc = row.get("forecast") or {}
    v = str(VAT)
    ctx = {
        "r.place": "SIMB-AD", "r.position": row.get("position"), "r.geo": full.get("geo") or "—",
        "r.format": row.get("format"), "r.device": _MP_INV.get(row.get("inventory") or "cross", "Кросс-девайс"),
        "r.rotation": "Динамика", "r.model": model, "r.volume": row.get("volume") or 0,
        "r.unit_name": _MP_UNIT.get((model or "").strip().upper(), "—"),
        # Период строки, если он у неё свой: на листе «Годовой МП» строки разных
        # месяцев лежат вперемешку, и период шапки (год) их бы не различал.
        "r.period": row.get("period") or full.get("period"), "r.season": 1,
        "r.unit_price": row.get("unit_price") or 0, "r.disc_pct": round(disc * 100),
        "r.freq": n(fc.get("freq")), "r.ctr": n(fc.get("ctr")), "r.cr": n(fc.get("cr")),
        "r.price": n(fc.get("price")), "r.sov": n(fc.get("sov")),
        # производные — формулы (KeyError → фолбэк на числа в вызывающем коде)
        "r.net_nodisc": f'=IF({C["model"]}{R}="CPM",{C["volume"]}{R}*{C["unit_price"]}{R}/1000,{C["volume"]}{R}*{C["unit_price"]}{R})',
        "r.disc_rub": f'={C["net_nodisc"]}{R}*{C["disc_pct"]}{R}/100',
        "r.net": f'={C["net_nodisc"]}{R}-{C["disc_rub"]}{R}',
        "r.vat": f'={C["net"]}{R}*{v}',
        "r.gross": f'={C["net"]}{R}+{C["vat"]}{R}',
        "r.imp": f'={C["volume"]}{R}',
        "r.reach": f'=IF({C["freq"]}{R}>0,{C["imp"]}{R}/{C["freq"]}{R},"")',
        "r.clicks": f'={C["imp"]}{R}*{C["ctr"]}{R}/100',
        "r.cpm": f'=IF({C["imp"]}{R}>0,{C["net"]}{R}/{C["imp"]}{R}*1000,"")',
        "r.cpc": f'=IF({C["clicks"]}{R}>0,{C["net"]}{R}/{C["clicks"]}{R},"")',
        "r.cpu": f'=IF(AND({C["freq"]}{R}>0,{C["imp"]}{R}>0),{C["net"]}{R}*{C["freq"]}{R}/{C["imp"]}{R},"")',
        "r.checks": f'={C["clicks"]}{R}*{C["cr"]}{R}/100',
        "r.cpo": f'=IF({C["checks"]}{R}>0,{C["net"]}{R}/{C["checks"]}{R},"")',
        "r.revenue": f'={C["checks"]}{R}*{C["price"]}{R}',
        "r.roi": f'=IF(AND({C["gross"]}{R}>0,{C["revenue"]}{R}>0),({C["revenue"]}{R}-{C["gross"]}{R})/{C["gross"]}{R},"")',
    }
    return ctx


def _extra_formula_ctx(e, C, R):
    price, total = e.get("price") or 0, e.get("total") or 0
    disc_pct = round((1 - total / price) * 100) if price else 0
    v = str(VAT)
    return {
        "e.place": "SIMB-AD", "e.name": e.get("name"), "e.volume": 1, "e.unit_name": "—",
        "e.period": e.get("period") or "—", "e.season": 1, "e.unit_price": price, "e.disc_pct": disc_pct,
        "e.net_nodisc": f'={C["unit_price"]}{R}',
        "e.disc_rub": f'={C["net_nodisc"]}{R}*{C["disc_pct"]}{R}/100',
        "e.total": f'={C["net_nodisc"]}{R}-{C["disc_rub"]}{R}',
        "e.vat": f'={C["total"]}{R}*{v}',
        "e.gross": f'={C["total"]}{R}+{C["vat"]}{R}',
    }


def _fill_block(ws, src, prefix, items, ctx_fn, fallback_fn):
    """Клонировать строку-образец src под len(items), заполнить каждую (формулы/значения).

    Элемент вида {"_band": "Название"} — не размещение, а полоса-разделитель (годовая
    выгрузка отбивает ею бренды). Элемент {"_subtotal": "Название"} — строка подытога,
    её формулы проставляет вызывающий код (он знает границы своих групп). Токены такой
    строки гасятся, а сама строка попадает в список служебных для оформления.

    Возвращает (первая_строка, последняя_строка, {field: колонка}, [(строка, элемент)]).
    Служебные строки числовых значений не несут, поэтому =СУММ по диапазону блока их не
    видит — но подытог, заполненный позже, УЖЕ виден: см. `sum_rows` в render_mp_sheet."""
    maxc = ws.max_column
    cols = _token_cols(ws, src, prefix)
    n = len(items)
    if n == 0:
        for c in range(1, maxc + 1):
            _sub_cell(ws.cell(src, c), {})   # пусто — гасим токены образца
        return src, src, cols, []
    if n > 1:
        _clone_below(ws, src, n - 1)
    specials = []
    for i, it in enumerate(items):
        R = src + i
        if isinstance(it, dict) and (it.get("_band") or it.get("_subtotal")):
            for c in range(1, maxc + 1):
                _sub_cell(ws.cell(R, c), {})
            specials.append((R, it))
            continue
        try:
            ctx = ctx_fn(it, cols, R)
        except KeyError:
            ctx = fallback_fn(it)            # нет нужной колонки в шаблоне → числа
        for c in range(1, maxc + 1):
            _sub_cell(ws.cell(R, c), ctx)
    return src, src + n - 1, cols, specials


# Полоса-разделитель бренда на месячном листе годовой выгрузки: цвета из макета
# сводной (navy-tint-200 / navy-700), чтобы месячные листы читались одной семьёй.
BAND_FILL, BAND_TEXT = "DFE4F0", "14265E"


def _style_bands(ws, bands, cols):
    """Оформить строки-полосы: объединить по ширине блока, подписать бренд."""
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import column_index_from_string
    if not bands or not cols:
        return
    idx = [column_index_from_string(c) for c in cols.values()]
    c1, c2 = min(idx), max(idx)
    for r, text in bands:
        # В строке-образце шаблона уже есть свои объединения (название позиции растянуто
        # на несколько колонок), и они клонируются вместе с ней. Наложить поверх ещё одно
        # нельзя: пересекающиеся объединения Excel считает повреждением файла и «чинит»
        # его, выкидывая их при открытии. Снимаем прежние по этой строке.
        for mr in list(ws.merged_cells.ranges):
            if mr.min_row <= r <= mr.max_row and not (mr.max_col < c1 or mr.min_col > c2):
                ws.unmerge_cells(str(mr))
        ws.merge_cells(start_row=r, end_row=r, start_column=c1, end_column=c2)
        cell = ws.cell(r, c1)
        cell.value = text
        cell.font = Font(name="Arial", size=10, bold=True, color=BAND_TEXT)
        cell.fill = PatternFill("solid", fgColor=BAND_FILL)
        cell.alignment = Alignment(horizontal="left", vertical="center")


def subtotal_formulas(cols, tcol, ranges):
    """Формулы строки-подытога: {колонка: =СУММ по своим строкам}.

    Пишутся в ячейки НАПРЯМУЮ, а не через _sub_cell: служебная строка приходит из
    _fill_block с уже погашенными токенами, подставлять в неё нечего.

    `ranges` — список диапазонов (a, b) либо одиночных номеров строк. Одиночные нужны
    верхним уровням: подытог бренда суммирует строки-подытоги месяцев, а не данные,
    иначе месяц и его итог сложились бы дважды."""
    parts = [x if isinstance(x, (tuple, list)) else (x, x) for x in ranges]
    out = {}
    for f, tc in tcol.items():
        col = cols.get(f, tc)
        out[col] = "=SUM(" + ",".join(
            f"{col}{a}:{col}{b}" if a != b else f"{col}{a}" for a, b in parts) + ")"
    return out


def render_mp_sheet(ws, full, rows=None, extras=None, row_hook=None):
    """Заполнить ОДИН лист-шаблон МП данными плана.

    Вынесено из _render_from_template, чтобы годовая выгрузка могла отрендерить этим же
    кодом двенадцать месячных листов в одной книге: месячный лист годовой выгрузки —
    это тот же МП, только строки собраны по всем брендам и отбиты полосами.
    rows/extras можно передать явно (полосы = элементы {"_band": ...}).
    row_hook(ws, cols, tcol, first, last, specials) вызывается после заливки блока
    размещений — им лист «Годовой МП» проставляет свои подытоги. Если хук вернул список
    строк, ИТОГО суммирует ИХ, а не весь диапазон: иначе подытоги, попавшие внутрь
    диапазона, удвоили бы годовую сумму."""
    rows = full["rows"] if rows is None else rows
    extras = full["extras"] if extras is None else extras

    net_cell = _find_token_cell(ws, "total_net")
    gross_cell = _find_token_cell(ws, "total_gross")

    # Размещения + строка ИТОГО (t.*) = СУММ по колонкам.
    src_r = _find_token_row(ws, "{{r.")
    t_map = {}
    if src_r:
        tcol = _token_cols(ws, src_r + 1, "t")   # колонки итоговой строки (до сдвига)
        first, last, rcol, specials = _fill_block(ws, src_r,
                                                  "r", rows,
                                                  lambda it, C, R: _row_formula_ctx(it, full, C, R),
                                                  lambda it: _row_ctx(it, full))
        _style_bands(ws, [(R, it["_band"]) for R, it in specials if it.get("_band")], rcol)
        sum_rows = row_hook(ws, rcol, tcol, first, last, specials) if row_hook else None
        tot_row = last + 1
        if sum_rows:
            tctx = {f"t.{f}": "=SUM(" + ",".join(f"{rcol.get(f, col)}{r}" for r in sum_rows) + ")"
                    for f, col in tcol.items()}
        else:
            tctx = {f"t.{f}": f"=SUM({rcol.get(f, col)}{first}:{rcol.get(f, col)}{last})" for f, col in tcol.items()}
        for c in range(1, ws.max_column + 1):
            _sub_cell(ws.cell(tot_row, c), tctx)
        t_map = {"net": f'{rcol.get("net", "Q")}{tot_row}', "gross": f'{rcol.get("gross", "S")}{tot_row}'}

    # Доп.услуги + строка ИТОГО (te.*) — образец ищем заново (строки сдвинулись).
    src_e = _find_token_row(ws, "{{e.")
    te_map = {}
    if src_e:
        tecol = _token_cols(ws, src_e + 1, "te")
        efirst, elast, ecol, especials = _fill_block(ws, src_e,
                                                     "e", extras,
                                                     lambda it, C, R: _extra_formula_ctx(it, C, R),
                                                     lambda it: _extra_ctx(it))
        _style_bands(ws, [(R, it["_band"]) for R, it in especials if it.get("_band")], ecol)
        etot_row = elast + 1
        tectx = {f"te.{f}": f"=SUM({ecol.get(f, col)}{efirst}:{ecol.get(f, col)}{elast})" for f, col in tecol.items()}
        for c in range(1, ws.max_column + 1):
            _sub_cell(ws.cell(etot_row, c), tectx)
        te_map = {"total": f'{ecol.get("total", "Q")}{etot_row}', "gross": f'{ecol.get("gross", "S")}{etot_row}'}

    # Итого-блок = формулы (размещения + доп.услуги).
    net_f = "=" + t_map.get("net", "0") + (("+" + te_map["total"]) if (te_map and extras) else "")
    gross_f = "=" + t_map.get("gross", "0") + (("+" + te_map["gross"]) if (te_map and extras) else "")
    vat_f = f"={gross_cell}-{net_cell}" if (net_cell and gross_cell) else 0

    adv, brand, agency = full.get("advertiser"), full.get("brand"), full.get("agency")

    def d(x):
        return x.strftime("%d.%m.%Y") if hasattr(x, "strftime") else (str(x) if x else "")

    created = d(full.get("created_at")) or date.today().strftime("%d.%m.%Y")
    ca = _mp_targeting_text(full.get("targeting"))
    g = {
        "agency": agency or "—", "advertiser": adv or "—", "brand": brand or "—",
        "title": full.get("title") or "—", "period": full.get("period") or "—",
        "date": created, "date_from": d(full.get("date_from")) or "—", "date_to": d(full.get("date_to")) or "—",
        "mp_title": f"Медиаплан · {adv or '—'}" + (f" | {brand}" if brand else ""),
        # В конце подзаголовка — код сделки, к которой прикреплён МП, через вертикальный
        # разделитель: по выгрузке видно, к какой сделке она относится. Нет привязки — нет хвоста.
        "mp_subtitle": (f"SIMB-AD · {agency or adv or '—'} · от {created} · МП актуален 14 дней"
                        + (f" | {full['deal_code']}" if full.get("deal_code") else "")),
        "geo": full.get("geo") or "—", "ca": ca or "—",
        "tg_geo": full.get("geo") or "—", "tg_audience": _tg_join(full, "audience"),
        "tg_buys": _tg_join(full, "buys"), "tg_interests": _tg_join(full, "interests"),
        "tg_behavior": _tg_join(full, "behavior"), "tg_competitors": _tg_join(full, "competitors"),
        "total_net": net_f, "total_gross": gross_f, "total_vat": vat_f,
    }
    g.update(full.get("head_override") or {})   # годовая выгрузка правит шапку (бренд, подзаголовок)
    logo_coord = _find_token_cell(ws, "logo")   # до подстановки: {{logo}} очистится в проходе ниже
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and "{{" in cell.value:
                _sub_cell(cell, g)
    _insert_logo(ws, logo_coord)
    return ws


def _render_from_template(full, p, path):
    from openpyxl import load_workbook
    wb = load_workbook(path)
    ws = wb["МП"] if "МП" in wb.sheetnames else wb.active
    render_mp_sheet(ws, full)
    try:
        wb.calculation.fullCalcOnLoad = True   # Excel пересчитает формулы при открытии
    except Exception:
        pass
    return wb


@router.get("/{plan_id}/export.xlsx")
def export_xlsx(plan_id: int, db: Session = Depends(get_db), current_user: User = Depends(MP_REG_VIEW)):
    p = db.query(SalesMediaPlan).filter(SalesMediaPlan.id == plan_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Медиаплан не найден")
    _guard_owned(db, p, current_user, "media_plans")
    full = _plan_full(db, p, _names(db))
    tpl = os.path.abspath(TEMPLATE_PATH)
    wb = _render_from_template(full, p, tpl) if os.path.exists(tpl) else _wb_programmatic(full, p)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"MP_{plan_id}_v{p.version}.xlsx"
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})
