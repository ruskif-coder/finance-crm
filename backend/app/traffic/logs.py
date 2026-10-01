# -*- coding: utf-8 -*-
"""Логи обмена с DSP и Weborama для админки трафика (владелец 01.10.2026): вкладка «Логи»,
две ленты, каждая строка — сделка + площадка + креатив.

Журналы живут в разных местах и ссылаются на наши объекты по-разному — сводим здесь:

  DSP (`dsp_send_log`, аналитическая база): `local_ref` = `cr<id>` (креатив РК) или номер
      РК; иначе — хеш DSP в `ms_xxhash` или в параметрах запроса (`xxhash`,
      `campaign_xxhash`), по нему ищется креатив или кампания.
  Weborama (`weborama_submissions`, основная база): `kind` + `local_id` — project → сделка,
      campaign → РК, insertion/tag → площадка РК. Креатива у Weborama нет: пиксель
      заводится на площадку.

Токены в журнале DSP уже вырезаны при записи (`dsp.client._redact`); здесь ничего не
раскрывается сверх того, что лежит в журнале.
"""
import json
import re
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

CR_REF = re.compile(r"^cr(\d+)$")
MAX_BODY = 4000      # тело запроса/ответа в ленте — обрезаем: экран, а не архив


def _short(v) -> Optional[str]:
    if v is None:
        return None
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s if len(s) <= MAX_BODY else s[:MAX_BODY] + " …"


def _params(req) -> dict:
    if isinstance(req, str):
        try:
            req = json.loads(req)
        except ValueError:
            return {}
    return (req or {}).get("params") or {} if isinstance(req, dict) else {}


def _creatives(db: Session, ids=(), hashes=()) -> dict:
    """{('id', n) | ('hash', h): {deal, publisher, creative}} одним запросом."""
    if not ids and not hashes:
        return {}
    rows = db.execute(text("""
        SELECT cr.id, upper(coalesce(cr.ms_creative_xxhash, '')) AS h, cr.ms_title AS title, cr.creative_no,
               d.id AS deal_id, d.code, pub.name AS publisher
          FROM ad_campaign_creative cr
          JOIN ad_campaign a ON a.id = cr.campaign_id
          JOIN sales_deals d ON d.id = a.deal_id
          LEFT JOIN ad_campaign_placement pl ON pl.id = cr.placement_id
          LEFT JOIN sales_publishers pub ON pub.id = pl.publisher_id
         WHERE cr.id = ANY(:ids) OR upper(coalesce(cr.ms_creative_xxhash, '')) = ANY(:hs)
    """), {"ids": list(ids) or [0], "hs": [h.upper() for h in hashes] or [""]}).mappings().all()
    out = {}
    for r in rows:
        v = {"deal_id": r["deal_id"], "deal": r["code"], "publisher": r["publisher"],
             "creative": r["title"] or f"креатив №{r['creative_no']}"}
        out[("id", r["id"])] = v
        if r["h"]:
            out[("hash", r["h"])] = v
    return out


def _campaigns(db: Session, ids=(), hashes=()) -> dict:
    if not ids and not hashes:
        return {}
    rows = db.execute(text("""
        SELECT a.id, upper(coalesce(a.ms_campaign_xxhash, '')) AS h, d.id AS deal_id, d.code
          FROM ad_campaign a JOIN sales_deals d ON d.id = a.deal_id
         WHERE a.id = ANY(:ids) OR upper(coalesce(a.ms_campaign_xxhash, '')) = ANY(:hs)
    """), {"ids": list(ids) or [0], "hs": [h.upper() for h in hashes] or [""]}).mappings().all()
    out = {}
    for r in rows:
        v = {"deal_id": r["deal_id"], "deal": r["code"], "publisher": None, "creative": None}
        out[("id", r["id"])] = v
        if r["h"]:
            out[("hash", r["h"])] = v
    return out


def _resolve(r, crs: dict, camps: dict) -> dict:
    """Запись журнала DSP → {deal, publisher, creative}: по `cr<id>`, по хешу креатива или
    кампании в запросе, по номеру РК. Не нашли — пусто, а не ошибка: в журнале есть и
    вызовы без нашей сделки (демо, тесты)."""
    ref = (r["local_ref"] or "").strip()
    p = _params(r["request"])
    m = CR_REF.match(ref)
    hit = crs.get(("id", int(m.group(1)))) if m else None
    for h in (p.get("xxhash"), r["ms_xxhash"]):
        if not hit and isinstance(h, str) and h.strip():
            hit = crs.get(("hash", h.strip().upper())) or camps.get(("hash", h.strip().upper()))
    if not hit and ref.isdigit():
        hit = camps.get(("id", int(ref)))
    if not hit and isinstance(p.get("campaign_xxhash"), str):
        hit = camps.get(("hash", p["campaign_xxhash"].strip().upper()))
    return hit or {}


def dsp_rows(db: Session, limit: int = 200, only_errors: bool = False,
             deal: Optional[str] = None, engine=None, prod_only: bool = True) -> list:
    """Лента DSP, новые сверху. `deal` — код сделки (фильтр после сведения: журнал
    сделок не знает)."""
    if engine is None:
        from app.dsp.db import dsp_engine
        engine = dsp_engine()
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT id, ts, method, entity_type, local_ref, ms_xxhash, ok, error, contour, "
            "request, response FROM dsp_send_log "
            + "WHERE true "
            + ("AND contour = 'prod' " if prod_only else "")
            + ("AND ok IS NOT TRUE " if only_errors else "")
            + "ORDER BY id DESC LIMIT :n"), {"n": limit * (5 if deal else 1)}).mappings().all()

    cr_ids, camp_ids, hashes = set(), set(), set()
    for r in rows:
        ref = (r["local_ref"] or "").strip()
        m = CR_REF.match(ref)
        if m:
            cr_ids.add(int(m.group(1)))
        elif ref.isdigit():
            camp_ids.add(int(ref))
        p = _params(r["request"])
        for h in (r["ms_xxhash"], p.get("xxhash"), p.get("campaign_xxhash")):
            if isinstance(h, str) and h.strip():
                hashes.add(h.strip())
    crs = _creatives(db, cr_ids, hashes)
    camps = _campaigns(db, camp_ids, hashes)

    out = []
    for r in rows:
        ref = (r["local_ref"] or "").strip()
        hit = _resolve(r, crs, camps)
        if deal and (hit.get("deal") or "").upper() != deal.upper():
            continue
        out.append({"id": r["id"], "ts": r["ts"], "method": r["method"],
                    "entity": r["entity_type"], "ref": ref or r["ms_xxhash"],
                    "hash": r["ms_xxhash"], "ok": r["ok"], "error": r["error"],
                    "contour": r["contour"], "deal_id": hit.get("deal_id"),
                    "deal": hit.get("deal"), "publisher": hit.get("publisher"),
                    "creative": hit.get("creative"),
                    "request": _short(r["request"]), "response": _short(r["response"])})
        if len(out) >= limit:
            break
    return out


def wr_rows(db: Session, limit: int = 200, only_errors: bool = False,
            deal: Optional[str] = None) -> list:
    """Лента Weborama, новые сверху. Успех — завершена и без ошибки; «без ответа» —
    вызов ушёл, ответа нет (`finished_at` пуст): такие показываем как ошибку."""
    rows = db.execute(text(f"""
        SELECT w.id, w.started_at AS ts, w.finished_at, w.kind, w.method, w.local_id, w.wcm_id,
               w.http_status, w.error, w.request,
               coalesce(dp.id, dc.id, dl.id) AS deal_id,
               coalesce(dp.code, dc.code, dl.code) AS deal,
               pub.name AS publisher
          FROM weborama_submissions w
          LEFT JOIN sales_deals dp ON w.kind = 'project' AND dp.id = w.local_id
          LEFT JOIN ad_campaign ac ON w.kind = 'campaign' AND ac.id = w.local_id
          LEFT JOIN sales_deals dc ON dc.id = ac.deal_id
          LEFT JOIN ad_campaign_placement pl ON w.kind IN ('insertion', 'tag') AND pl.id = w.local_id
          LEFT JOIN ad_campaign ap ON ap.id = pl.campaign_id
          LEFT JOIN sales_deals dl ON dl.id = ap.deal_id
          LEFT JOIN sales_publishers pub ON pub.id = pl.publisher_id
         WHERE (:deal = '' OR upper(coalesce(dp.code, dc.code, dl.code)) = upper(:deal))
           {"AND (w.error IS NOT NULL OR w.finished_at IS NULL)" if only_errors else ""}
         ORDER BY w.id DESC LIMIT :n
    """), {"n": limit, "deal": deal or ""}).mappings().all()
    return [{"id": r["id"], "ts": r["ts"], "method": r["method"], "entity": r["kind"],
             "ref": r["local_id"], "hash": r["wcm_id"],
             "ok": bool(r["finished_at"]) and not r["error"],
             "error": r["error"] or (None if r["finished_at"] else "вызов ушёл, ответа нет"),
             "http_status": r["http_status"], "deal_id": r["deal_id"], "deal": r["deal"],
             "publisher": r["publisher"], "creative": None,
             "request": _short(r["request"]), "response": None} for r in rows]
