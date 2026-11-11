# -*- coding: utf-8 -*-
"""Отчёт ОРД за месяц (владелец 11.11.2026) — «Аккаунты → ОРД → Отчёты», образец «пример по выгрузке.xlsx».

Строка — сделка × площадка × ЕРИД за месяц мастер-сделки:
- УПД — комплект закрывающих пакета: № и дата из 1С («Закрывающие документы»), бюджет — сумма 1С, до неё — сумма комплекта;
- доля сделки в УПД — по строкам СВОЕЙ УПД (`onec_desk.queue._lines`), в сумме ровно бюджет;
- показы и клики — наш факт площадки за месяц (`ad_campaign_stat`, `fact_sources`), решение 29.10: «наш факт DSP/Adfox»;
- несколько ЕРИД на площадке — делим по факту креативов (снимок `ord_erid_month_stat`, владелец 11.11.2026); снимка нет —
  одна строка со всеми ЕРИД и пометкой;
- «Сумма на площадку» — доля сделки, разложенная по строкам пропорционально показам, до копейки.

Правки из Excel (`ord_report_overrides`) накладываются поверх расчёта: хранятся только отличия (`diff`)."""
import calendar
from collections import Counter
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.final_recon import money as M

EDITABLE = ("shows", "clicks", "amount", "upd_no", "upd_date", "upd_gross")
NO_FACT = "нет факта за месяц"
NOT_SPLIT = "несколько ЕРИД — факт по креативам не снят"
NO_ERID = "нет ЕРИД"
NO_UPD = "УПД из 1С ещё не внесён"


class ReportError(Exception):
    """Ошибка для человека: текст уходит на экран."""


def key(r: dict) -> tuple:
    return ((r.get("deal_code") or "").strip().upper(), (r.get("domain") or "").strip().lower(), (r.get("erid") or "").strip())


# ── чистые расчёты ────────────────────────────────────────────────────────────

split_int = M.split_int          # общий делитель целого по весам (final_recon.money)


def erid_split(shows: int, clicks: int, parts: List[tuple]) -> Optional[List[tuple]]:
    """Факт площадки по ЕРИД пропорционально показам креативов: [(ЕРИД, показы, клики)]; один ЕРИД у нескольких креативов —
    одна строка. Факта креативов нет — None (делить не по чему)."""
    by: Dict[str, float] = {}
    for erid, w in parts:
        if erid:
            by[erid] = by.get(erid, 0) + (w or 0)
    erids = list(by)
    s = split_int(int(shows or 0), [by[e] for e in erids])
    if s is None:
        return None
    c = split_int(int(clicks or 0), [by[e] for e in erids]) or [0] * len(erids)
    return list(zip(erids, s, c))


def spread_amount(gross: float, shows: List[int]) -> List[float]:
    """Сумма сделки по строкам пропорционально показам, в сумме ровно `gross`. Показов нет — всё первой строке."""
    if not shows:
        return []
    if sum(shows) <= 0:
        return [M.r2(gross)] + [0.0] * (len(shows) - 1)
    return M.scale_to(shows, M.r2(gross))


def deal_shares(budget: float, lines: List[dict]) -> Dict[int, float]:
    """Доли сделок в ОРД из бюджета УПД: строки своей УПД (с НДС) масштабируются под бюджет (сумма 1С может отличаться на
    копейки), в долю идёт только размещение — «допы не идут в орд» (владелец 11.11.2026). УПД одних допов — пусто."""
    own = [x for x in lines if x.get("deal_id")]
    scaled = M.scale_to([float(x.get("gross") or 0) for x in own], M.r2(budget)) if own else []
    by: Dict[int, float] = {}
    for x, g in zip(own, scaled):
        if x.get("kind", "размещение") != "доп":
            by[x["deal_id"]] = M.r2(by.get(x["deal_id"], 0.0) + g)
    return by


def apply_overrides(rows: List[dict], ovs: List[dict]) -> List[dict]:
    """Правки поверх расчёта — новые строки, расчёт не меняется. `edited` — строку правили из файла."""
    by = {key(o): o for o in ovs}
    out = []
    for r in rows:
        o = by.get(key(r))
        if o is None:
            out.append({**r, "edited": False})
        elif o["kind"] == "правка":
            out.append({**r, **{f: o[f] for f in EDITABLE if o.get(f) is not None}, "edited": True})
    for o in ovs:
        if o["kind"] == "добавлена":
            out.append({"deal_code": o["deal_code"], "deal_id": o.get("deal_id"), "deal_title": o.get("deal_title") or "",
                        "master_code": o.get("master_code") or "", "deal_gross": None, "domain": o["domain"],
                        "publisher_id": o.get("publisher_id"), "erid": o["erid"], "note": "добавлена из файла", "edited": True,
                        **{f: o.get(f) for f in EDITABLE}})
    return out


def _same(f: str, a, b) -> bool:
    if f in ("amount", "upd_gross"):
        return a is not None and b is not None and abs(float(a) - float(b)) < 0.005
    if f == "upd_no":
        return (str(a or "").strip()) == (str(b or "").strip())
    return a == b


def diff(calc: List[dict], file_rows: List[dict]) -> List[dict]:
    """Отличия файла от расчёта: правка (только изменённые поля), добавлена (строки нет в расчёте), убрана (в файле нет)."""
    seen: Dict[tuple, dict] = {}
    for r in file_rows:
        k = key(r)
        if k in seen:
            raise ReportError(f"В файле строка повторяется: {k[0]} · {k[1] or 'без площадки'} · {k[2] or 'без ЕРИД'}")
        seen[k] = r
    base = {key(r): r for r in calc}
    out = []
    for k, r in seen.items():
        c = base.get(k)
        ident = {"deal_code": r["deal_code"], "domain": r.get("domain") or "", "erid": r.get("erid") or "",
                 "deal_id": (c or {}).get("deal_id"), "publisher_id": (c or {}).get("publisher_id")}
        if c is None:
            out.append({**ident, "kind": "добавлена", **{f: r.get(f) for f in EDITABLE}})
            continue
        # пустая ячейка — «не правили» (миграция: пустое поле правки берётся из расчёта), а не правка в пустоту
        changed = {f: r.get(f) for f in EDITABLE if r.get(f) not in (None, "") and not _same(f, r.get(f), c.get(f))}
        if changed:
            out.append({**ident, "kind": "правка", **{f: changed.get(f) for f in EDITABLE}})
    for k, c in base.items():
        if k not in seen:
            out.append({"deal_code": c["deal_code"], "domain": c.get("domain") or "", "erid": c.get("erid") or "",
                        "deal_id": c.get("deal_id"), "publisher_id": c.get("publisher_id"), "kind": "убрана",
                        **{f: None for f in EDITABLE}})
    return out


# ── расчёт по базе ────────────────────────────────────────────────────────────

def month_bounds(month: date) -> tuple:
    m1 = month.replace(day=1)
    return m1, m1.replace(day=calendar.monthrange(m1.year, m1.month)[1])


def _kits(db: Session, month: date) -> list:
    return db.execute(text("""
        SELECT k.id, k.upd_no AS kit_no, k.annex_id, k.net, k.vat, k.gross, k.onec_upd_no, k.onec_upd_date, k.onec_gross,
               m.id AS master_id, m.code AS master_code
          FROM master_deal_upds k JOIN master_deals m ON m.id = k.master_deal_id
         WHERE m.period = :p ORDER BY m.code, k.upd_no"""), {"p": month.strftime("%Y-%m")}).mappings().all()


def fallback_lines(rows: list) -> list:
    """Строки пакета (`master_deal.layout.lines`) как строки комплекта: размещение и допы раздельно — допы в ОРД не идут.
    Нужны, когда у комплекта нет ДС или её строки без сделок; доли — по сумме без НДС (бюджет всё равно масштабируется)."""
    return [{"deal_id": r["deal_id"], "gross": float(r.get("net") or 0), "kind": "размещение" if r["kind"] == "base" else "доп"}
            for r in rows if r.get("deal_id")]


def _kit_lines(db: Session, k) -> list:
    """Строки своей УПД с deal_id и суммой с НДС; ДС без строк — доля пакета целиком на его сделки поровну по сумме."""
    from app.master_deal.models import MasterDealUpd
    from app.onec_desk import queue as Q
    from app.sales.models import SalesAnnex
    kit = db.get(MasterDealUpd, k["id"])
    a = db.get(SalesAnnex, k["annex_id"]) if k["annex_id"] else None
    rate = float(a.vat_rate) if a is not None and a.vat_rate is not None else 0.0
    lines = Q._lines(db, kit, a, {}, rate) if a is not None else []
    if not any(x.get("deal_id") for x in lines):
        from app.master_deal import layout as L
        from app.master_deal.models import MasterDeal
        lines = fallback_lines(L.lines(db, db.get(MasterDeal, k["master_id"])))
    return lines


def _placements(db: Session, deal_ids: list, d1: date, d2: date) -> list:
    from app.ad.stat_sources import fact_sources
    return db.execute(text("""
        SELECT c.deal_id, p.id AS placement_id, p.publisher_id, sp.domain,
               coalesce(sum(s.shows), 0) AS shows, coalesce(sum(s.clicks), 0) AS clicks
          FROM ad_campaign c JOIN ad_campaign_placement p ON p.campaign_id = c.id
          JOIN sales_publishers sp ON sp.id = p.publisher_id
          JOIN ad_campaign_stat s ON s.placement_id = p.id AND s.source = ANY(:src) AND s.date BETWEEN :a AND :b
         WHERE c.deal_id = ANY(:ids)
         GROUP BY 1, 2, 3, 4 HAVING coalesce(sum(s.shows), 0) > 0
         ORDER BY c.deal_id, sum(s.shows) DESC, p.id"""),
        {"ids": deal_ids or [0], "src": fact_sources(), "a": d1, "b": d2}).mappings().all()


def _creative_erids(db: Session, placement_ids: list) -> Dict[int, list]:
    out: Dict[int, list] = {}
    for pid, erid in db.execute(text("""SELECT placement_id, erid FROM ad_campaign_creative
                                         WHERE placement_id = ANY(:p) AND erid IS NOT NULL AND erid <> '' ORDER BY id"""),
                                {"p": placement_ids or [0]}):
        if erid not in out.setdefault(pid, []):
            out[pid].append(erid)
    return out


def _snapshot(db: Session, month: date, placement_ids: list) -> Dict[int, list]:
    out: Dict[int, list] = {}
    for pid, erid, shows in db.execute(text("""SELECT placement_id, erid, shows FROM ord_erid_month_stat
                                                WHERE month = :m AND placement_id = ANY(:p)
                                                ORDER BY placement_id, creative_id NULLS FIRST, id"""),
                                       {"m": month, "p": placement_ids or [0]}):
        out.setdefault(pid, []).append((erid, int(shows or 0)))
    return out


def _deal_info(db: Session, ids: list) -> Dict[int, dict]:
    return {r["id"]: dict(r) for r in db.execute(text("SELECT id, code, title FROM sales_deals WHERE id = ANY(:i)"),
                                                 {"i": ids or [0]}).mappings()}


def _deal_rows(deal: dict, head: dict, gross: float, places: list, erids: Dict[int, list], snap: Dict[int, list]) -> list:
    rows = []
    for p in places:
        own = erids.get(p["placement_id"], [])
        split = erid_split(p["shows"], p["clicks"], snap.get(p["placement_id"], [])) if len(own) > 1 else None
        if split:
            rows += [{"publisher_id": p["publisher_id"], "domain": p["domain"], "erid": e, "shows": s, "clicks": c, "note": ""}
                     for e, s, c in split]
        else:
            note = NO_ERID if not own else (NOT_SPLIT if len(own) > 1 else "")
            rows.append({"publisher_id": p["publisher_id"], "domain": p["domain"], "erid": ", ".join(own),
                         "shows": int(p["shows"]), "clicks": int(p["clicks"]), "note": note})
    if not rows:
        rows = [{"publisher_id": None, "domain": "", "erid": "", "shows": 0, "clicks": 0, "note": NO_FACT}]
    return [{**r, **head, "deal_id": deal["id"], "deal_code": deal["code"], "deal_title": deal["title"] or "",
             "deal_gross": M.r2(gross), "amount": amt,
             "note": "; ".join(x for x in (r["note"], NO_UPD if head["upd_no"] is None else "") if x)}
            for r, amt in zip(rows, spread_amount(gross, [r["shows"] for r in rows]))]


TWO_UPD = "сделка в двух УПД — проверить"


def deal_rows_again(deal: dict, head: dict, gross: float) -> list:
    """Сделка уже отчитана показами в другом комплекте месяца (владелец 11.11.2026: показы — один раз, в первом): здесь — только
    её доля суммы этой УПД одной строкой без площадки и показов. На данных не встречается: сделка в одной мастер-сделке
    (уникальный ключ), комплекты — по бренду и услуге; страховка на медиаплан со строками разных услуг."""
    return [{"publisher_id": None, "domain": "", "erid": "", "shows": 0, "clicks": 0, **head, "deal_id": deal["id"],
             "deal_code": deal["code"], "deal_title": deal["title"] or "", "deal_gross": M.r2(gross), "amount": M.r2(gross),
             "note": "; ".join(x for x in (TWO_UPD, NO_UPD if head["upd_no"] is None else "") if x)}]


def compute(db: Session, month: date) -> List[dict]:
    """Расчёт месяца без правок."""
    d1, d2 = month_bounds(month)
    out: List[dict] = []
    kits = _kits(db, month)
    shares = {}
    for k in kits:
        budget = float(k["onec_gross"] if k["onec_gross"] is not None else (k["gross"] or 0))
        shares[k["id"]] = (budget, deal_shares(budget, _kit_lines(db, k)))
    deal_ids = sorted({d for _b, s in shares.values() for d in s})
    seen_in = Counter(d for _b, s in shares.values() for d in s)
    twice, done = {d for d, n in seen_in.items() if n > 1}, set()
    info = _deal_info(db, deal_ids)
    places_all = _placements(db, deal_ids, d1, d2)
    pids = [p["placement_id"] for p in places_all]
    erids, snap = _creative_erids(db, pids), _snapshot(db, month, pids)
    for k in kits:
        budget, by_deal = shares[k["id"]]
        head = {"master_code": k["master_code"], "upd_no": k["onec_upd_no"], "upd_date": k["onec_upd_date"],
                "upd_gross": M.r2(budget), "kit_no": k["kit_no"]}
        for deal_id, gross in by_deal.items():
            if deal_id not in info:
                continue
            if deal_id in done:
                out += deal_rows_again(info[deal_id], head, gross)
                continue
            rows = _deal_rows(info[deal_id], head, gross, [p for p in places_all if p["deal_id"] == deal_id], erids, snap)
            if deal_id in twice:
                rows = [{**r, "note": "; ".join(x for x in (TWO_UPD, r["note"]) if x)} for r in rows]
            out += rows
            done.add(deal_id)
    return out

