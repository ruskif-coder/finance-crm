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
# Новый код транспорта импортируем из пакета напрямую (bitrix_api — реэкспорт для старых мест).
from app.sales.bitrix.transport import vibecode_delete, vibecode_post

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


def _bx_deal_count(cid: str, refresh: bool = False) -> int:
    """Сколько сделок висит на компании Битрикса.

    refresh=True обязателен перед удалением компании: кэш живёт 5 минут, а решение
    «сделок ноль, можно удалять» на устаревшем счётчике необратимо.

    ГРАБЛЯ (измерено 2026-08-23): `meta.total` приходит ТОЛЬКО когда выборка пуста.
    Как только сделки есть, вместо него отдаётся `hasMore`/`nextAfterId`, и прежнее
    `meta.total or 0` возвращало НОЛЬ для любой непустой компании — то есть защита
    «удаляем только пустые» пропускала вообще всё. Поэтому отсутствие total значит
    «сделки есть», и считать их надо перебором.
    """
    now = time.time()
    hit = _DEAL_COUNT_CACHE.get(cid)
    if hit and not refresh and now - hit[0] < _TTL:
        return hit[1]
    d = vibecode_get("/deals", {"filter[companyId]": cid, "limit": 1})
    total = (d.get("meta") or {}).get("total")
    if total is None:
        total = len(list_deal_ids_for_company(cid))
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
    return _do_consolidate(db, _kind_or_400(kind), kind, data, current_user)


def _do_consolidate(db: Session, model, kind: str, data: ConsolidateIn, current_user):
    """Тело склейки. Вынесено из эндпоинта, чтобы пакетный прогон выполнял ровно
    ту же последовательность, а не свою копию логики."""
    import json
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


# ─── Шаг 2 склейки: удаление ретайрнутых компаний ───────────────────────────
# Склейка (выше) сделки перебрасывает, но лишние компании не удаляет — переименовывает
# в «XXX_старое имя». Это намеренная точка остановки: Битрикс без транзакций и без
# корзины, удаление необратимо, а ошибку в выборе главной компании видно только после
# того, как посмотришь на результат. Удаление вынесено отдельным шагом, чтобы между
# «склеили» и «удалили» существовал момент, когда всё ещё можно поправить.
RETIRED_PREFIX = "XXX_"


def _retired_candidates(kind: str, with_counts: bool = True) -> list[dict]:
    """Компании Битрикса, помеченные к удалению склейкой.

    Отбираем ТОЛЬКО по префиксу: удалять можно лишь то, что мы сами пометили.
    Компания без префикса — либо не проходила склейку, либо кто-то её переименовал
    обратно вручную; в обоих случаях это не наш объект для удаления.
    """
    out = []
    for c in _fetch_companies(kind):
        title = c.get("title") or ""
        if not title.startswith(RETIRED_PREFIX):
            continue
        row = {"bx_id": str(c["id"]), "title": title}
        if with_counts:
            # Считаем заново, а не из кэша: между склейкой и удалением сделку могли
            # привязать руками, и тогда удалять компанию нельзя.
            try:
                row["deal_count"] = _bx_deal_count(str(c["id"]), refresh=True)
            except Exception:
                row["deal_count"] = None   # неизвестно — значит не удаляем
        out.append(row)
    return out


@router.get("/{kind}/retired")
def retired_preview(kind: str, _=Depends(_can_view)):
    """Что будет удалено. Читает Битрикс, ничего не меняет."""
    _kind_or_400(kind)
    items = _retired_candidates(kind)
    return {
        "items": items,
        "deletable": [x for x in items if x.get("deal_count") == 0],
        "blocked": [x for x in items if x.get("deal_count") != 0],
    }


@router.post("/{kind}/retired/delete")
def retired_delete(kind: str, db: Session = Depends(get_db), current_user=Depends(_can_edit)):
    """ЗАПИСЬ В ПРОД-БИТРИКС, НЕОБРАТИМАЯ. Удаляет компании с префиксом XXX_,
    у которых ноль сделок. Компанию, на которой сделки есть, пропускает и называет —
    молча пропустить нельзя, иначе оператор решит, что всё удалилось.

    Перед удалением каждой компании счётчик сделок перезапрашивается: между
    предпросмотром и нажатием кнопки сделку могли привязать заново.
    """
    import json
    _kind_or_400(kind)
    items = _retired_candidates(kind)

    os.makedirs(CONSOLIDATE_BACKUP_DIR, exist_ok=True)
    backup = {"ts": time.time(), "kind": kind, "action": "delete_retired", "items": items}
    backup_path = f"{CONSOLIDATE_BACKUP_DIR}/bx_delete_{int(backup['ts'])}_{kind}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, indent=2)
    # Дубль в лог: имена и id удалённых компаний — единственное, что от них останется.
    logger.info("delete_retired backup %s: %s", backup_path, json.dumps(backup, ensure_ascii=False))

    deleted, skipped = [], []
    for it in items:
        if it.get("deal_count") != 0:
            skipped.append({**it, "reason": "на компании есть сделки"
                            if it.get("deal_count") else "не удалось посчитать сделки"})
            continue
        try:
            vibecode_delete(f"/companies/{int(it['bx_id'])}")
            deleted.append(it)
        except Exception as e:
            logger.error("delete_retired: %s «%s» не удалена: %s", it["bx_id"], it["title"], e)
            skipped.append({**it, "reason": "Битрикс отклонил удаление"})

    for it in deleted:
        _DEAL_COUNT_CACHE.pop(it["bx_id"], None)
    _CACHE.pop(kind, None)   # список компаний изменился — кэш недействителен

    log_action(db, current_user, "bx_delete_retired", kind, None,
               details=f"удалено {len(deleted)}, пропущено {len(skipped)}; бэкап {backup_path}")
    return {"deleted": deleted, "skipped": skipped, "backup": backup_path}


# ─── Создание нашей записи в Битриксе ────────────────────────────────────────

class CreateInBitrixIn(BaseModel):
    our_id: int


def _created_id(res: dict) -> str:
    """id созданной сущности из ответа VibeCode.

    Ответ обёрнут: {"success": true, "data": {...}} — id на верхнем уровне НЕТ.
    Читать `res["id"]` напрямую нельзя: компания создастся, id не найдётся, и
    оператор получит 502 «Битрикс не вернул id» при уже созданной компании.
    Непустой ответ без обёртки тоже поддерживаем — на случай смены формата.
    """
    if not isinstance(res, dict):
        return ""
    body = res.get("data") or res
    if not isinstance(body, dict):
        return ""
    return str(body.get("id") or body.get("ID") or "")


@router.post("/{kind}/create-in-bitrix")
def create_in_bitrix(kind: str, data: CreateInBitrixIn, db: Session = Depends(get_db),
                     current_user=Depends(_can_edit)):
    """Заводит компанию в Битриксе по нашей записи и сразу связывает их.

    Имя — тот же стандарт, что и при переименовании (Short | ENG | Рус | Холдинг),
    иначе созданная запись сразу разойдётся с остальными.
    """
    return _do_create(db, _kind_or_400(kind), kind, data, current_user)


def _do_create(db: Session, model, kind: str, data: CreateInBitrixIn, current_user):
    """Тело создания. Вынесено ради пакетного прогона — см. _do_consolidate."""
    r, row, links = _record_and_links(db, model, kind, data.our_id)
    if links:
        raise HTTPException(status_code=400, detail="Запись уже связана с компанией Битрикса")

    title = standard_name(row)
    # Поле типа называется typeId — тем же именем компании и читаются
    # (filter[typeId] в list_bitrix_companies). При «companyType» Битрикс запрос
    # принимает, но компания заводится БЕЗ типа и пропадает из экрана сверки.
    created = vibecode_post("/companies", {"title": title, "typeId": TYPE_ID[kind]})
    bx_id = _created_id(created)
    if not bx_id:
        # Компания, возможно, создалась, но id не вернулся — связать не можем, а
        # повтор наплодит дубли. Поэтому не «ok», а явная ошибка с просьбой проверить.
        raise HTTPException(status_code=502,
                            detail=f"Битрикс не вернул id созданной компании «{title}». "
                                   f"Проверьте в Битриксе вручную, не создалась ли она, "
                                   f"прежде чем повторять.")

    db.add(SalesBitrixLink(kind=kind, our_id=data.our_id, bx_id=bx_id))
    db.flush()
    _sync_primary(db, model, kind, data.our_id)
    db.commit()
    _CACHE.pop(kind, None)
    log_action(db, current_user, "bx_create_company", kind, data.our_id,
               details=f"создана компания {bx_id} «{title}»")
    return {"bx_id": bx_id, "title": title}


# ─── Переименование под наш стандарт (без склейки) ───────────────────────────

class RenameIn(BaseModel):
    our_id: int


@router.post("/{kind}/rename-to-standard")
def rename_to_standard(kind: str, data: RenameIn, db: Session = Depends(get_db),
                       current_user=Depends(_can_edit)):
    """Приводит имена связанных компаний Битрикса к нашему стандарту.

    Склейка делает это попутно, но требует ≥2 компаний. Агентству с единственной
    привязкой переименование было недоступно вовсе — а таких большинство.
    """
    return _do_rename(db, _kind_or_400(kind), kind, data, current_user)


def _do_rename(db: Session, model, kind: str, data: RenameIn, current_user):
    """Тело переименования. Вынесено ради пакетного прогона — см. _do_consolidate."""
    _r, row, links = _record_and_links(db, model, kind, data.our_id)
    if not links:
        raise HTTPException(status_code=400, detail="Запись не связана с Битриксом")
    std = standard_name(row)
    titles = {c["id"]: c.get("title") or "" for c in _fetch_companies(kind)}

    renamed, unchanged = [], []
    for bx in links:
        if titles.get(bx) == std:
            unchanged.append({"bx_id": bx, "title": std})
            continue
        vibecode_patch(f"/companies/{int(bx)}", {"title": std})
        renamed.append({"bx_id": bx, "was": titles.get(bx, ""), "now": std})
    if renamed:
        _CACHE.pop(kind, None)
        log_action(db, current_user, "bx_rename", kind, data.our_id,
                   details=f"переименовано {len(renamed)} → «{std}»")
    return {"renamed": renamed, "unchanged": unchanged, "standard": std}


# ─── Пакетный прогон по выбранным записям ────────────────────────────────────
# Одна кнопка вместо трёх на каждую запись: 16 склеек + 62 переименования + 6
# созданий вручную — это 84 нажатия, каждое со своим окном. Удаление в пакет
# намеренно НЕ входит: оно необратимо и остаётся осознанным отдельным шагом.

class SyncItemIn(BaseModel):
    our_id: int
    primary_bx_id: Optional[str] = None


class SyncIn(BaseModel):
    items: list[SyncItemIn]


def _sync_plan(db: Session, model, kind: str, items: list[SyncItemIn]) -> list[dict]:
    """Что произойдёт с каждой выбранной записью. Только читает.

    Главная компания берётся ТОЛЬКО из явного выбора звёздочкой. Порядок привязок
    в базе не задан (`_links_by_our` читает без order_by), поэтому «первая» — это
    произвольная: у Roki она указывает на компанию с нулём сделок, и пакетный
    прогон молча увёз бы туда все сделки. Без выбора запись пропускается.
    """
    titles = {c["id"]: c.get("title") or "" for c in _fetch_companies(kind)}
    plan = []
    for it in items:
        r = db.query(model).filter(model.id == it.our_id).first()
        if r is None:
            plan.append({"our_id": it.our_id, "name": f"#{it.our_id}",
                         "action": "skip", "reason": "запись не найдена"})
            continue
        _r, row, links = _record_and_links(db, model, kind, it.our_id)
        name = r.short_name or r.name
        std = standard_name(row)
        if not links:
            plan.append({"our_id": it.our_id, "name": name, "action": "create", "now": std})
        elif len(links) == 1:
            cur = titles.get(links[0], "")
            if cur.strip() == std.strip():
                plan.append({"our_id": it.our_id, "name": name, "action": "nothing",
                             "reason": "имя уже по стандарту"})
            else:
                plan.append({"our_id": it.our_id, "name": name, "action": "rename",
                             "bx_id": links[0], "was": cur, "now": std})
        elif not it.primary_bx_id:
            plan.append({"our_id": it.our_id, "name": name, "action": "skip",
                         "reason": f"компаний {len(links)}, главная не выбрана звёздочкой"})
        elif it.primary_bx_id not in links:
            plan.append({"our_id": it.our_id, "name": name, "action": "skip",
                         "reason": "выбранная главная не привязана к этой записи"})
        else:
            primary, redundant = _consolidate_plan(kind, row, links, it.primary_bx_id,
                                                   with_counts=True)
            plan.append({"our_id": it.our_id, "name": name, "action": "consolidate",
                         "primary": primary, "redundant": redundant, "now": std,
                         "deals_to_move": sum((x["deal_count"] or 0) for x in redundant)})
    return plan


@router.post("/{kind}/sync/preview")
def sync_preview(kind: str, data: SyncIn, db: Session = Depends(get_db), _=Depends(_can_edit)):
    """Что будет сделано с выбранными записями. Читает Битрикс, ничего не меняет."""
    model = _kind_or_400(kind)
    plan = _sync_plan(db, model, kind, data.items)
    counts: dict[str, int] = {}
    for p in plan:
        counts[p["action"]] = counts.get(p["action"], 0) + 1
    return {"plan": plan, "counts": counts,
            "deals_to_move": sum(p.get("deals_to_move", 0) for p in plan)}


@router.post("/{kind}/sync")
def sync_run(kind: str, data: SyncIn, db: Session = Depends(get_db),
             current_user=Depends(_can_edit)):
    """ЗАПИСЬ В ПРОД-БИТРИКС по всем выбранным записям.

    Сбой на одной записи НЕ останавливает остальные: иначе половина выбранного
    осталась бы необработанной, а оператор увидел бы только текст ошибки и не знал,
    докуда дошло. Каждая запись отчитывается отдельно — сделано или почему нет.
    """
    model = _kind_or_400(kind)
    plan = {p["our_id"]: p for p in _sync_plan(db, model, kind, data.items)}
    done, failed, skipped = [], [], []
    for it in data.items:
        p = plan.get(it.our_id)
        if p is None:
            continue
        if p["action"] in ("skip", "nothing"):
            skipped.append({"our_id": it.our_id, "name": p["name"],
                            "reason": p.get("reason", "")})
            continue
        try:
            if p["action"] == "consolidate":
                res = _do_consolidate(db, model, kind,
                                      ConsolidateIn(our_id=it.our_id,
                                                    primary_bx_id=it.primary_bx_id),
                                      current_user)
                detail = (f"переброшено сделок {res['moved_deals']}, "
                          f"помечено XXX_ {res['retired']}, имя «{res['rename_to']}»")
            elif p["action"] == "rename":
                res = _do_rename(db, model, kind, RenameIn(our_id=it.our_id), current_user)
                detail = f"переименовано {len(res['renamed'])} → «{res['standard']}»"
            else:
                res = _do_create(db, model, kind,
                                 CreateInBitrixIn(our_id=it.our_id), current_user)
                detail = f"создана компания {res['bx_id']} «{res['title']}»"
            done.append({"our_id": it.our_id, "name": p["name"],
                         "action": p["action"], "detail": detail})
        except HTTPException as e:
            db.rollback()
            failed.append({"our_id": it.our_id, "name": p["name"],
                           "error": str(e.detail)[:400]})
        except Exception as e:
            db.rollback()
            logger.error("sync_run %s our_id=%s: %s", kind, it.our_id, e)
            failed.append({"our_id": it.our_id, "name": p["name"], "error": repr(e)[:200]})
    log_action(db, current_user, "bx_sync_batch", kind, None,
               details=(f"выбрано {len(data.items)}: сделано {len(done)}, "
                        f"пропущено {len(skipped)}, ошибок {len(failed)}"))
    return {"done": done, "skipped": skipped, "failed": failed}


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
