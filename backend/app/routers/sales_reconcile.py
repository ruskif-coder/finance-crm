import time
import os
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app.audit import log_action, require_admin
from app.permissions import require_permission

# Сверка гейтится правом bx_reconcile: чтение — view, любые записи (link/unlink/
# master/import/flag/auto/consolidate) — edit. import-deals остаётся admin-only
# (это глобальный импорт сделок, не операция справочника).
_can_view = require_permission("bx_reconcile", "view")
_can_edit = require_permission("bx_reconcile", "edit")
from app.sales.models import SalesAgency, SalesAdvertiser, SalesBitrixLink, SalesDeal
from app.sales.reconcile import build_buckets, plan_auto_link, standard_name, TYPE_ID
from app.bitrix_api import (list_bitrix_companies, vibecode_get, vibecode_patch,
                            list_deal_ids_for_company, all_deal_company_ids)

router = APIRouter()
logger = logging.getLogger("finance")

# Бэкап консолидации — на примонтированный том (переживает пересоздание контейнера).
CONSOLIDATE_BACKUP_DIR = "/app/uploads/bx_consolidate"

MODEL_BY_KIND = {"agencies": SalesAgency, "advertisers": SalesAdvertiser}
_CACHE: dict[str, tuple[float, list]] = {}
_DEAL_COUNT_CACHE: dict[str, tuple[float, int]] = {}
_DEAL_MAP: dict = {"ts": 0.0, "counts": {}}   # companyId -> кол-во сделок (общий, кэш)
_TTL = 300.0
_MAP_TTL = 1800.0   # карта сделок живёт 30 мин (меняется редко), сброс — refresh=1


def _kind_or_400(kind: str):
    if kind not in MODEL_BY_KIND:
        raise HTTPException(status_code=400, detail="Неизвестный тип справочника")
    return MODEL_BY_KIND[kind]


def _fetch_companies(kind: str, refresh: bool = False) -> list:
    now = time.time()
    hit = _CACHE.get(kind)
    if hit and not refresh and now - hit[0] < _TTL:
        return hit[1]
    companies = list_bitrix_companies(TYPE_ID[kind])
    _CACHE[kind] = (now, companies)
    return companies


def _links_by_our(db: Session, kind: str) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for lk in db.query(SalesBitrixLink).filter(SalesBitrixLink.kind == kind).all():
        out.setdefault(lk.our_id, []).append(lk.bx_id)
    return out


def _our_deal_counts(db: Session, model) -> dict[int, int]:
    fk = SalesDeal.agency_id if model is SalesAgency else SalesDeal.advertiser_id
    rows = db.query(fk, func.count(SalesDeal.id)).group_by(fk).all()
    return {k: v for k, v in rows if k is not None}


def _bx_deal_count(cid: str) -> int:
    now = time.time()
    hit = _DEAL_COUNT_CACHE.get(cid)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    d = vibecode_get("/deals", {"filter[companyId]": cid, "limit": 1})
    total = (d.get("meta") or {}).get("total") or 0
    _DEAL_COUNT_CACHE[cid] = (now, total)
    return total


def _deal_counts_map(refresh: bool = False) -> dict[str, int]:
    """companyId -> кол-во сделок для ВСЕХ компаний одним проходом (кэш TTL). Общий для
    агентств и рекламодателей — сделки покрывают оба."""
    now = time.time()
    if _DEAL_MAP["counts"] and not refresh and now - _DEAL_MAP["ts"] < _MAP_TTL:
        return _DEAL_MAP["counts"]
    from collections import Counter
    counts = dict(Counter(all_deal_company_ids()))
    _DEAL_MAP["ts"] = now
    _DEAL_MAP["counts"] = counts
    return counts


def _our_rows(db: Session, model, kind: str) -> list[dict]:
    links = _links_by_our(db, kind)
    counts = _our_deal_counts(db, model)
    rows = db.query(model).filter(model.is_active == True).all()  # noqa: E712
    return [{
        "id": r.id, "name": r.name, "short_name": r.short_name,
        "name_en": r.name_en, "name_ru": r.name_ru,
        "holding": getattr(r, "holding", None), "deal_count": counts.get(r.id, 0),
        "bx_ids": links.get(r.id, []), "bx_master": r.bx_master,
    } for r in rows]


def _sync_primary(db: Session, model, kind: str, our_id: int):
    """Зеркалит первую связь в record.bx_id (для колонки BX_ID в справочниках).
    Если связей не осталось — очищает bx_id и bx_master."""
    row = db.query(model).filter(model.id == our_id).first()
    if not row:
        return
    remaining = [lk.bx_id for lk in db.query(SalesBitrixLink)
                 .filter(SalesBitrixLink.kind == kind, SalesBitrixLink.our_id == our_id)
                 .order_by(SalesBitrixLink.id).all()]
    row.bx_id = remaining[0] if remaining else None
    if not remaining:
        row.bx_master = None


@router.get("/{kind}")
def get_reconcile(kind: str, refresh: int = Query(0),
                  db: Session = Depends(get_db), _=Depends(_can_view)):
    model = _kind_or_400(kind)
    try:
        companies = _fetch_companies(kind, refresh=bool(refresh))
    except Exception as e:
        logger.error("reconcile: Битрикс недоступен: %s", e)
        raise HTTPException(status_code=502, detail="Битрикс недоступен (детали в логе сервера)")
    # Счётчики сделок Битрикса НЕ строим здесь (медленно) — их тянет отдельный
    # эндпойнт /{kind}/deal-counts, чтобы страница открывалась мгновенно.
    return build_buckets(_our_rows(db, model, kind), companies)


@router.post("/import-deals")
def import_deals(commit: int = Query(0), db: Session = Depends(get_db),
                 current_user=Depends(require_admin)):
    """Инкрементальный импорт новых сделок из Битрикса (id > нашего максимума).
    commit=0 — dry-run (предпросмотр), commit=1 — запись. Только отслеживаемые воронки."""
    from app.sales.bitrix.deal_import import import_new_deals
    try:
        report = import_new_deals(db, commit=bool(commit))
    except Exception as e:
        logger.error("reconcile import: %s", e)
        raise HTTPException(status_code=502, detail="Импорт не удался (детали в логе сервера)")
    if commit and report["inserted"]:
        log_action(db, current_user, "bx_import_deals", "deals", 0,
                   details=f"импортировано {report['inserted']} сделок (id>{report['anchor_bitrix_id']}); "
                           f"пропущено вне воронок {report['skipped_untracked']}")
    return report


@router.get("/{kind}/deal-counts")
def deal_counts(kind: str, refresh: int = Query(0), _=Depends(_can_view)):
    """Карта {bx_id: кол-во сделок в Битриксе} — грузится фронтом отдельно, после букетов."""
    _kind_or_400(kind)
    try:
        return {"counts": _deal_counts_map(refresh=bool(refresh))}
    except Exception as e:
        logger.error("reconcile: Битрикс недоступен: %s", e)
        raise HTTPException(status_code=502, detail="Битрикс недоступен (детали в логе сервера)")


class LinkIn(BaseModel):
    our_id: int
    bx_id: str
    master: str = "ours"


@router.post("/{kind}/link")
def link(kind: str, data: LinkIn, db: Session = Depends(get_db),
         current_user=Depends(_can_edit)):
    model = _kind_or_400(kind)
    row = db.query(model).filter(model.id == data.our_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    existing = db.query(SalesBitrixLink).filter(
        SalesBitrixLink.kind == kind, SalesBitrixLink.bx_id == data.bx_id).first()
    if existing:
        if existing.our_id == data.our_id:
            return {"ok": True}  # уже привязано к этой же записи — идемпотентно
        other = db.query(model).filter(model.id == existing.our_id).first()
        raise HTTPException(status_code=409,
                            detail=f"Компания уже привязана к «{other.name if other else existing.our_id}»")
    db.add(SalesBitrixLink(kind=kind, our_id=data.our_id, bx_id=data.bx_id))
    row.bx_master = data.master if data.master in ("ours", "bitrix") else "ours"
    db.flush()
    _sync_primary(db, model, kind, data.our_id)
    db.commit()
    log_action(db, current_user, "bx_link", kind, data.our_id,
               details=f"{row.name} ↔ bx {data.bx_id} (master={row.bx_master})")
    return {"ok": True}


class UnlinkIn(BaseModel):
    our_id: int
    bx_id: Optional[str] = None  # None → отвязать все компании записи


@router.post("/{kind}/unlink")
def unlink(kind: str, data: UnlinkIn, db: Session = Depends(get_db),
           current_user=Depends(_can_edit)):
    model = _kind_or_400(kind)
    row = db.query(model).filter(model.id == data.our_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    q = db.query(SalesBitrixLink).filter(
        SalesBitrixLink.kind == kind, SalesBitrixLink.our_id == data.our_id)
    if data.bx_id:
        q = q.filter(SalesBitrixLink.bx_id == data.bx_id)
    q.delete(synchronize_session=False)
    db.flush()
    _sync_primary(db, model, kind, data.our_id)
    db.commit()
    log_action(db, current_user, "bx_unlink", kind, data.our_id,
               details=f"{row.name}: {'bx ' + data.bx_id if data.bx_id else 'все связи'}")
    return {"ok": True}


class SetMasterIn(BaseModel):
    our_id: int
    master: str


@router.post("/{kind}/set-master")
def set_master(kind: str, data: SetMasterIn, db: Session = Depends(get_db),
               current_user=Depends(_can_edit)):
    model = _kind_or_400(kind)
    row = db.query(model).filter(model.id == data.our_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    row.bx_master = data.master if data.master in ("ours", "bitrix") else "ours"
    db.commit()
    log_action(db, current_user, "bx_set_master", kind, data.our_id,
               details=f"{row.name}: master={row.bx_master}")
    return {"ok": True}


class ImportIn(BaseModel):
    bx_id: str


@router.post("/{kind}/import")
def import_company(kind: str, data: ImportIn, db: Session = Depends(get_db),
                   current_user=Depends(_can_edit)):
    model = _kind_or_400(kind)
    if db.query(SalesBitrixLink).filter(
            SalesBitrixLink.kind == kind, SalesBitrixLink.bx_id == data.bx_id).first():
        raise HTTPException(status_code=409, detail="Эта компания уже привязана")
    companies = _fetch_companies(kind)
    comp = next((c for c in companies if str(c["id"]) == data.bx_id), None)
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена в Битриксе")
    title = (comp.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="У компании пустое название")
    if db.query(model).filter(model.name == title).first():
        raise HTTPException(status_code=409,
                            detail=f"Запись «{title}» уже есть — свяжите её, а не импортируйте")
    row = model(name=title, short_name=title, bx_id=data.bx_id, bx_master="ours", is_active=True)
    db.add(row)
    db.flush()
    db.add(SalesBitrixLink(kind=kind, our_id=row.id, bx_id=data.bx_id))
    db.commit()
    db.refresh(row)
    log_action(db, current_user, "bx_import", kind, row.id, details=f"{title} ← bx {data.bx_id}")
    return {"ok": True, "id": row.id}


class FlagIn(BaseModel):
    our_id: int
    on: bool = True


@router.post("/{kind}/flag-create")
def flag_create(kind: str, data: FlagIn, db: Session = Depends(get_db),
                current_user=Depends(_can_edit)):
    model = _kind_or_400(kind)
    row = db.query(model).filter(model.id == data.our_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    if db.query(SalesBitrixLink).filter(
            SalesBitrixLink.kind == kind, SalesBitrixLink.our_id == data.our_id).first():
        raise HTTPException(status_code=400, detail="Запись уже связана с Битриксом")
    row.bx_master = "ours" if data.on else None
    db.commit()
    log_action(db, current_user, "bx_flag_create", kind, data.our_id,
               details=f"{row.name}: {'помечена' if data.on else 'снята метка'}")
    return {"ok": True}


def _record_and_links(db: Session, model, kind: str, our_id: int):
    r = db.query(model).filter(model.id == our_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    links = [lk.bx_id for lk in db.query(SalesBitrixLink)
             .filter(SalesBitrixLink.kind == kind, SalesBitrixLink.our_id == our_id)
             .order_by(SalesBitrixLink.id).all()]
    row = {"id": r.id, "name": r.name, "short_name": r.short_name, "name_en": r.name_en,
           "name_ru": r.name_ru, "holding": getattr(r, "holding", None)}
    return r, row, links


class ConsolidateIn(BaseModel):
    our_id: int
    primary_bx_id: str


def _consolidate_plan(kind: str, row: dict, links: list, primary_bx_id: str, with_counts: bool):
    if primary_bx_id not in links:
        raise HTTPException(status_code=400, detail="Главная компания не среди привязок записи")
    if len(links) < 2:
        raise HTTPException(status_code=400, detail="Для склейки нужно ≥2 привязанных компаний")
    companies = _fetch_companies(kind)
    titles = {c["id"]: c["title"] for c in companies}
    std = standard_name(row)

    def cnt(cid):
        if not with_counts:
            return None
        try:
            return _bx_deal_count(cid)
        except Exception:
            return None

    primary = {"bx_id": primary_bx_id, "title": titles.get(primary_bx_id, ""),
               "deal_count": cnt(primary_bx_id), "rename_to": std}
    redundant = []
    for b in links:
        if b == primary_bx_id:
            continue
        t = titles.get(b, "") or ""
        redundant.append({"bx_id": b, "title": t, "deal_count": cnt(b),
                          "rename_to": t if t.startswith("XXX_") else "XXX_" + t})
    return primary, redundant


@router.post("/{kind}/consolidate/preview")
def consolidate_preview(kind: str, data: ConsolidateIn, db: Session = Depends(get_db),
                        _=Depends(_can_edit)):
    model = _kind_or_400(kind)
    _r, row, links = _record_and_links(db, model, kind, data.our_id)
    primary, redundant = _consolidate_plan(kind, row, links, data.primary_bx_id, with_counts=True)
    return {"primary": primary, "redundant": redundant,
            "total_deals_to_move": sum((x["deal_count"] or 0) for x in redundant)}


@router.post("/{kind}/consolidate")
def consolidate(kind: str, data: ConsolidateIn, db: Session = Depends(get_db),
                current_user=Depends(_can_edit)):
    """ЗАПИСЬ В ПРОД-БИТРИКС. Перебрасывает сделки редундантных компаний на главную,
    переименовывает главную под наш стандарт, редундантные → XXX_старое имя (НЕ удаляет).
    Перед записью пишет бэкап на персистентный том И в лог; при сбое на середине
    сообщает, что уже выполнено (откат по бэкапу вручную — Битрикс без транзакций)."""
    import json
    model = _kind_or_400(kind)
    _r, row, links = _record_and_links(db, model, kind, data.our_id)
    primary, redundant = _consolidate_plan(kind, row, links, data.primary_bx_id, with_counts=False)
    std = primary["rename_to"]

    # Бэкап: id всех перебрасываемых сделок + старые названия компаний.
    backup = {"ts": time.time(), "kind": kind, "our_id": data.our_id,
              "primary": data.primary_bx_id, "primary_old_title": primary["title"],
              "primary_new_title": std, "redundant": []}
    deal_map = {}
    for red in redundant:
        ids = list_deal_ids_for_company(red["bx_id"])
        deal_map[red["bx_id"]] = ids
        backup["redundant"].append({"bx_id": red["bx_id"], "old_title": red["title"],
                                    "new_title": red["rename_to"], "deal_ids": ids})
    os.makedirs(CONSOLIDATE_BACKUP_DIR, exist_ok=True)
    backup_path = f"{CONSOLIDATE_BACKUP_DIR}/bx_consolidate_{int(backup['ts'])}_{data.our_id}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, indent=2)
    # дублируем бэкап в лог — переживёт даже потерю файла (для ручного отката)
    logger.info("consolidate backup %s: %s", backup_path, json.dumps(backup, ensure_ascii=False))

    # Битрикс без транзакций — фиксируем прогресс, чтобы при сбое на середине
    # оператор знал, что уже применено, и мог откатить по бэкапу.
    done = {"moved": 0, "primary_renamed": False, "redundant_renamed": []}
    try:
        # id приводим к int и в путь (не только в тело) — путь к внешнему API
        # не должен собираться из непроверенной строки.
        primary_id = int(data.primary_bx_id)
        # 1) переброс сделок → главная
        for red in redundant:
            for did in deal_map[red["bx_id"]]:
                vibecode_patch(f"/deals/{int(did)}", {"companyId": primary_id})
                done["moved"] += 1
        # 2) главную → наш стандарт
        vibecode_patch(f"/companies/{primary_id}", {"title": std})
        done["primary_renamed"] = True
        # 3) редундантные → XXX_старое имя (не удаляем)
        for red in redundant:
            vibecode_patch(f"/companies/{int(red['bx_id'])}", {"title": red["rename_to"]})
            done["redundant_renamed"].append(red["bx_id"])
    except Exception as e:
        logger.error("consolidate: частичный сбой Битрикса, выполнено=%s, бэкап=%s: %s",
                     done, backup_path, e)
        raise HTTPException(status_code=502,
            detail=(f"Битрикс отклонил на середине: переброшено {done['moved']} сделок, "
                    f"главная переименована: {done['primary_renamed']}, ретайр: {len(done['redundant_renamed'])}. "
                    f"Локально ничего не тронуто. Бэкап для ручного отката: {backup_path}. "
                    f"Детали ошибки — в логе сервера."))
    moved = done["moved"]

    # у нас оставляем связь только с главной
    db.query(SalesBitrixLink).filter(
        SalesBitrixLink.kind == kind, SalesBitrixLink.our_id == data.our_id,
        SalesBitrixLink.bx_id != data.primary_bx_id).delete(synchronize_session=False)
    db.flush()
    _sync_primary(db, model, kind, data.our_id)
    db.commit()
    _DEAL_COUNT_CACHE.pop(data.primary_bx_id, None)
    for red in redundant:
        _DEAL_COUNT_CACHE.pop(red["bx_id"], None)
    log_action(db, current_user, "bx_consolidate", kind, data.our_id,
               details=f"главная {data.primary_bx_id} «{std}»; переброшено {moved} сделок; "
                       f"ретайр {len(redundant)}; бэкап {backup_path}")
    return {"moved_deals": moved, "primary": data.primary_bx_id, "rename_to": std,
            "retired": len(redundant), "backup": backup_path}


class AutoLinkIn(BaseModel):
    threshold: float = 0.8
    master: str = "ours"


@router.post("/{kind}/auto-link")
def auto_link(kind: str, data: AutoLinkIn, db: Session = Depends(get_db),
              current_user=Depends(_can_edit)):
    model = _kind_or_400(kind)
    try:
        companies = _fetch_companies(kind)
    except Exception as e:
        logger.error("reconcile: Битрикс недоступен: %s", e)
        raise HTTPException(status_code=502, detail="Битрикс недоступен (детали в логе сервера)")
    buckets = build_buckets(_our_rows(db, model, kind), companies)
    taken = {c["bx_id"] for l in buckets["linked"] for c in l["companies"]}
    master = data.master if data.master in ("ours", "bitrix") else "ours"
    plan = plan_auto_link(buckets["candidates"], data.threshold, taken)
    for item in plan["to_link"]:
        db.add(SalesBitrixLink(kind=kind, our_id=item["our_id"], bx_id=item["bx_id"]))
        row = db.query(model).filter(model.id == item["our_id"]).first()
        if row:
            row.bx_master = master
    db.flush()
    for item in plan["to_link"]:
        _sync_primary(db, model, kind, item["our_id"])
    db.commit()
    log_action(db, current_user, "bx_auto_link", kind, 0,
               details=f"связано {len(plan['to_link'])}, пропущено {len(plan['skipped'])} (порог {data.threshold})")
    return {"linked": len(plan["to_link"]), "skipped": len(plan["skipped"])}
