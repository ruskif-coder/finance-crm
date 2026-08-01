"""Синхронизация одной сделки из Битрикса (через VibeCode).

Читает живой payload сделки, обновляет наши поля и скачивает файлы (МП, договор)
в персистентный том /app/uploads. Идемпотентно: повторный вызов обновляет только
изменившееся, а неопознанные поля НЕ затирает (защита от порчи ручных правок).

Коды полей — в VibeCode-нотации (camelCase), см. «Сверку полей» / DEAL_FIELD_MAP.
"""
import os
import re
import logging
from datetime import datetime, date

import httpx
from sqlalchemy.orm import Session

from app.sales.bitrix.transport import vibecode_get
from app.sales.models import SalesDeal, SalesRep, SalesAdvertiser, SalesBrand, SalesDealFile

logger = logging.getLogger("sales.deal_sync")

UPLOADS_ROOT = "/app/uploads"
FILES_SUBDIR = "deal_files"

# ── коды полей Битрикса ──────────────────────────────────────────
F_AMOUNT_NET = "ufCrm_1690138678699"   # сумма до НДС ("500000|RUB")
F_SALE_MGR = "ufCrm_1761319635"        # employee — продавец (Sale manager)
F_KEY_ACC = "ufCrm_1723638961"         # employee — аккаунт (Key account)
F_ADVERTISER = "ufCrm_1761214459"      # crm/лид — рекламодатель (непоследовательное)
F_BRAND = "ufCrm_64BD76BC5BC45"        # текст — бренд
F_PERIOD_FROM = "ufCrm_1723639172"     # дата — Старт РК
F_MP = "ufCrm_1690138838403"           # file — МП
F_CONTRACT = "ufCrm_1690897647759"     # file — Договор и приложения


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _money(v):
    if not v:
        return None
    return _num(str(v).split("|")[0].strip())


def _parse_date(v):
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _first(v):
    """crm/employee/file-поле бывает списком или скаляром."""
    if isinstance(v, list):
        return v[0] if v else None
    return v


# ── резолв связей ────────────────────────────────────────────────
_user_cache = {}


def _resolve_user_name(uid):
    uid = str(uid)
    if uid in _user_cache:
        return _user_cache[uid]
    nm = None
    try:
        r = vibecode_get(f"/users/{uid}", {})
        d = (r.get("data") if isinstance(r, dict) else None) or {}
        nm = ((d.get("name") or "") + " " + (d.get("lastName") or d.get("last_name") or "")).strip() or d.get("title")
    except Exception as e:
        logger.warning("resolve user %s: %s", uid, e)
    _user_cache[uid] = nm
    return nm


def _resolve_rep_id(db, uid):
    """Bitrix user id → наш SalesRep. Сначала по bitrix_user_id, иначе по имени
    (и кэшируем связь в bitrix_user_id для будущих прогонов)."""
    if not uid:
        return None, None
    rep = db.query(SalesRep).filter(SalesRep.bitrix_user_id == str(uid)).first()
    if rep:
        return rep.id, None
    name = _resolve_user_name(uid)
    if not name:
        return None, f"пользователь bx#{uid} не опознан"
    rep = db.query(SalesRep).filter(SalesRep.name == name).first()
    if rep:
        if not rep.bitrix_user_id:
            rep.bitrix_user_id = str(uid)
        return rep.id, None
    return None, f"сейлз «{name}» (bx#{uid}) не найден в справочнике"


def _resolve_advertiser_id(db, crm_val):
    """ufCrm_1761214459 (crm/лид) → наш SalesAdvertiser по имени. Поле
    непоследовательное — ставим только при уверенном совпадении."""
    ent = _first(crm_val)
    if not ent:
        return None, None
    ent = str(ent).split("_")[-1]  # 'L_2055' -> '2055'
    title = None
    for path in (f"/leads/{ent}", f"/companies/{ent}"):
        try:
            r = vibecode_get(path, {})
            d = (r.get("data") if isinstance(r, dict) else None) or {}
            title = d.get("title") or d.get("name")
            if title:
                break
        except Exception:
            continue
    if not title:
        return None, f"рекламодатель bx#{ent} не резолвится"
    adv = (db.query(SalesAdvertiser)
           .filter((SalesAdvertiser.name == title) | (SalesAdvertiser.short_name == title)).first())
    if adv:
        return adv.id, None
    head = re.split(r"[ (]", title.strip())[0]
    if len(head) >= 3:
        cand = (db.query(SalesAdvertiser)
                .filter((SalesAdvertiser.name.ilike(head + "%")) | (SalesAdvertiser.short_name.ilike(head + "%"))).all())
        if len(cand) == 1:
            return cand[0].id, None
    return None, f"рекламодатель «{title}» не сопоставлен — проверьте вручную"


def _resolve_brand_id(db, text, advertiser_id):
    if not text:
        return None, None
    q = db.query(SalesBrand).filter(SalesBrand.name == text)
    if advertiser_id:
        q = q.filter(SalesBrand.advertiser_id == advertiser_id)
    cand = q.all()
    if len(cand) == 1:
        return cand[0].id, None
    if not cand:
        return None, f"бренд «{text}» не найден в справочнике"
    return None, f"бренд «{text}» неоднозначен ({len(cand)})"


def _download_file(db, deal, field_val, kind):
    """Скачивает файл по urlMachine (со встроенным токеном) в персистентный том."""
    item = _first(field_val)
    if not isinstance(item, dict):
        return None, None
    url = item.get("urlMachine") or item.get("url")
    fid = str(item.get("id") or "")
    if not url:
        return None, f"нет urlMachine у файла ({kind})"
    existing = (db.query(SalesDealFile)
                .filter(SalesDealFile.deal_id == deal.id, SalesDealFile.kind == kind).first())
    if existing and existing.bitrix_file_id == fid and os.path.exists(os.path.join(UPLOADS_ROOT, existing.path)):
        return existing, None  # тот же файл уже скачан
    try:
        r = httpx.get(url, timeout=120, follow_redirects=True)
        r.raise_for_status()
    except Exception as e:
        return None, f"скачивание {kind} не удалось: {repr(e)[:80]}"
    cd = r.headers.get("content-disposition", "")
    m = re.search(r'filename="([^"]+)"', cd)
    fname = m.group(1) if m else f"{kind}_{fid}"
    subdir = os.path.join(UPLOADS_ROOT, FILES_SUBDIR, str(deal.id))
    os.makedirs(subdir, exist_ok=True)
    safe = re.sub(r"[^\w.\-]+", "_", fname)
    abspath = os.path.join(subdir, safe)
    with open(abspath, "wb") as f:
        f.write(r.content)
    rel = os.path.relpath(abspath, UPLOADS_ROOT)
    if existing:
        existing.bitrix_file_id = fid
        existing.filename = fname
        existing.path = rel
        existing.size = len(r.content)
        existing.content_type = r.headers.get("content-type")
        existing.synced_at = datetime.utcnow()
        rec = existing
    else:
        rec = SalesDealFile(deal_id=deal.id, kind=kind, bitrix_file_id=fid, filename=fname,
                            path=rel, size=len(r.content), content_type=r.headers.get("content-type"))
        db.add(rec)
    return rec, None


def sync_deal_from_bitrix(db: Session, deal: SalesDeal, download_files: bool = True) -> dict:
    """Живая сделка из Битрикса → наши поля + файлы. Идемпотентно, неопознанное
    НЕ затирает. Возвращает отчёт: changes / files / warnings."""
    if (deal.bitrix_id or "").startswith("local-"):
        raise ValueError("Локальная сделка ещё не в Битриксе")
    r = vibecode_get(f"/deals/{deal.bitrix_id}", {})
    d = (r.get("data") if isinstance(r, dict) else None) or {}
    changes = {}
    issues = []  # [{field, message}] — поля, требующие внимания (для подсветки + попапа)

    def setf(field, val):
        if val is None:
            return
        old = getattr(deal, field)
        if old != val:
            changes[field] = {"old": str(old) if old is not None else None, "new": str(val)}
            setattr(deal, field, val)

    def issue(field, w):
        if w:
            issues.append({"field": field, "message": w})

    setf("amount_with_vat", _num(d.get("amount")))       # стандартное opportunity — с НДС
    setf("amount", _money(d.get(F_AMOUNT_NET)))          # до НДС
    setf("period_from", _parse_date(d.get(F_PERIOD_FROM)))

    rid, w = _resolve_rep_id(db, _first(d.get(F_SALE_MGR)))
    setf("sales_rep_id", rid)
    issue("sales_rep", w)
    aid, w = _resolve_rep_id(db, _first(d.get(F_KEY_ACC)))
    setf("account_manager_id", aid)
    issue("account_manager", w)
    adv_id, w = _resolve_advertiser_id(db, d.get(F_ADVERTISER))
    setf("advertiser_id", adv_id)
    issue("advertiser", w)
    br_id, w = _resolve_brand_id(db, d.get(F_BRAND), deal.advertiser_id)
    setf("brand_id", br_id)
    issue("brand", w)

    files = []
    if download_files:
        for field, kind in ((F_MP, "mp"), (F_CONTRACT, "contract")):
            val = d.get(field)
            if not val:
                continue
            rec, w = _download_file(db, deal, val, kind)
            if rec:
                files.append({"kind": kind, "filename": rec.filename, "size": rec.size, "id": rec.id})
            issue(kind, w)

    # ── Светофор ──
    # red  — Битрикс расходится с нашими справочниками (что-то не сматчилось);
    # blue — у нас есть ручные правки (данные полнее / не выгружены в Битрикс);
    # green — всё сошлось. red важнее blue.
    from app.sales.models import SalesDealFieldOverride
    has_overrides = (db.query(SalesDealFieldOverride)
                     .filter(SalesDealFieldOverride.deal_id == deal.id).count() > 0)
    deal.sync_status = "red" if issues else ("blue" if has_overrides else "green")
    deal.sync_checked_at = datetime.utcnow()
    # Отчёт сохраняем в сделке — чтобы клик по светофору показал детали без нового запроса.
    deal.sync_report = {"issues": issues, "changes": list(changes.keys()),
                        "checked_at": deal.sync_checked_at.isoformat()}

    db.commit()
    warnings = [i["message"] for i in issues]
    return {"changes": changes, "files": files, "warnings": warnings, "issues": issues,
            "status": deal.sync_status, "bitrix_id": deal.bitrix_id}
