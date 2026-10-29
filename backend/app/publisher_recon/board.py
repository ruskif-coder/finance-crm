# -*- coding: utf-8 -*-
"""Чтение сверок: статусы месяца, детализация площадки, сводная за год.

Факт — `publisher_placement_v` (миграция 2026-10-26): из неё же читает кабинет площадки (`pub.campaign_v1`),
поэтому «наши показы» у менеджера и у площадки — одно число, а не два расчёта одной формулы.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

# Сверки начинаются с октября 2026 (владелец 26.10.2026): раньше месяцы закрывались без них, и звать сверять
# всё лето было бы неправдой. Месяц раньше старта — «без сверки», в сводной только наши данные.
START = "2026-10"

WAIT, READY, OUT, ANSWER, DONE = "ждёт закрытия", "готово", "ожидает", "есть ответ", "согласовано"
ORDER = {ANSWER: 0, "late": 1, OUT: 2, READY: 3, WAIT: 4, DONE: 5}
AGREED = "согласовано"
DONE_STATUS = "завершён"        # статус строки витрины у окончившегося размещения
REFUSED = "отказ"


def period_ok(period: str) -> bool:
    try:
        datetime.strptime(period or "", "%Y-%m")
        return True
    except ValueError:
        return False


def status_of(total: int, done: int, req: Optional[dict], today: date) -> tuple:
    """(статус, просрочено). Чистая функция — проверяется таблицей случаев.

    Пока сверку не отправили, статус считается из размещений: «готово», когда окончены ВСЕ размещения площадки
    за месяц (владелец 12.10.2026). После отправки — по переписке: последнее несистемное сообщение площадки =
    «есть ответ» (ход наш), иначе «ожидает»; просрочено — ожидаем дольше срока."""
    if req is None:
        return (READY if total and done >= total else WAIT), False
    if req.get("verdict") == AGREED:
        return DONE, False
    if req.get("last_side") == "площадка":
        return ANSWER, False
    due = req.get("due_at")
    return OUT, bool(due and due < today)


def _placements(db: Session, period: str, publisher_id: Optional[int] = None) -> List[dict]:
    rows = db.execute(text("""
        SELECT v.placement_id, v.publisher_id, v.site, v.brand, v.service, v.surface, v.date_from, v.date_to,
               v.plan, v.fact, v.cpm, v.erid, v.status
          FROM publisher_placement_v v
         WHERE to_char(v.date_from, 'YYYY-MM') = :p
           -- архивное = снятое нами (правило 16.09.2026) — в сверку не идёт; витрина отдаёт его с отметкой (29.10.2026)
           AND v.archived_at IS NULL
           -- «отказ» без показов — не размещение; с показами (успела открутить до отказа) — оплачивается, в сверке
           AND (v.status <> :refused OR v.fact > 0)
           AND (CAST(:pub AS integer) IS NULL OR v.publisher_id = :pub)
         ORDER BY v.fact DESC, v.placement_id"""),
        {"p": period, "refused": REFUSED, "pub": publisher_id}).mappings().all()
    return [dict(r) for r in rows]


def _requests(db: Session, period: str) -> Dict[int, dict]:
    rows = db.execute(text("""
        SELECT r.id, r.publisher_id, r.asked_at, r.due_at, r.verdict, r.decided_at, r.decided_by, r.sent_by,
               rc.our_volume, rc.their_volume, rc.agreed_volume, rc.cpm AS agreed_cpm,
               (SELECT m.side FROM publisher_request_message m WHERE m.request_id = r.id AND m.side <> 'система'
                 ORDER BY m.id DESC LIMIT 1) AS last_side,
               (SELECT count(*) FROM publisher_request_message m
                 WHERE m.request_id = r.id AND m.side <> 'система') AS messages,
               (SELECT count(*) FROM publisher_request_message m WHERE m.request_id = r.id AND m.side = 'площадка'
                   AND m.created_at > COALESCE(r.our_seen_at, '-infinity'::timestamp)) AS unread,
               (SELECT array_agg(l.target_id ORDER BY l.target_id) FROM publisher_recon_line l
                 WHERE l.request_id = r.id) AS line_targets,
               pb.domain AS site, pb.cpm_contract AS cpm
          FROM publisher_request r LEFT JOIN publisher_recon rc ON rc.request_id = r.id
          JOIN sales_publishers pb ON pb.id = r.publisher_id
         WHERE r.kind = 'сверка' AND r.period = :p"""), {"p": period}).mappings().all()
    return {r["publisher_id"]: dict(r) for r in rows}


def _amount(shows, cpm) -> Optional[float]:
    return round(shows * float(cpm) / 1000, 2) if shows is not None and cpm else None


def month_rows(db: Session, period: str, today: Optional[date] = None) -> List[dict]:
    """Строки экрана менеджера за месяц: площадка × месяц, наши и площадки показы, статус, переписка."""
    return assemble(period, _placements(db, period), _requests(db, period), today or date.today())


def assemble(period: str, placements: List[dict], reqs: Dict[int, dict], today: date) -> List[dict]:
    """Сборка строк из размещений месяца и сверок. Чистая функция — сценарии проверяются таблицей случаев.

    Правила (26.10.2026):
      · размещение окончено — «завершён»; «отказ» с показами тоже окончено (открутила до отказа — платим);
      · сверка, у площадки которой за месяц не осталось размещений (сделку перенесли, удалили), не исчезает:
        строка остаётся со статусом по переписке и пометкой `orphan`;
      · согласованная сверка, у которой после итога поменялся наш факт или состав размещений, помечается
        `changed`: итог без возврата, но менеджер должен это видеть."""
    by_pub: Dict[int, dict] = {}
    for p in placements:
        a = by_pub.setdefault(p["publisher_id"], {"site": p["site"], "total": 0, "done": 0, "fact": 0,
                                                  "cpm": p["cpm"], "targets": []})
        a["total"] += 1
        a["done"] += p["status"] in (DONE_STATUS, REFUSED)
        a["fact"] += int(p["fact"] or 0)
        a["targets"].append(p["placement_id"])
    for pid, req in reqs.items():
        by_pub.setdefault(pid, {"site": req.get("site"), "total": 0, "done": 0, "fact": 0, "cpm": req.get("cpm"),
                                "targets": [], "orphan": True})
    out = []
    for pid, a in by_pub.items():
        req = reqs.get(pid)
        st, late = status_of(a["total"], a["done"], req, today)
        agreed = st == DONE
        ours = int(req["our_volume"]) if agreed and req.get("our_volume") is not None else a["fact"]
        cpm = req["agreed_cpm"] if agreed and req.get("agreed_cpm") is not None else a["cpm"]
        theirs = req.get("their_volume") if req else None
        changed = bool(agreed and (a["fact"] != ours
                                   or sorted(a["targets"]) != sorted(req.get("line_targets") or [])))
        out.append({
            "publisher_id": pid, "site": a["site"], "period": period,
            "total": a["total"], "done": a["done"], "ours": ours, "theirs": theirs,
            "delta": (theirs - ours) if theirs is not None else None,
            "agreed": req["agreed_volume"] if agreed else None,
            "cpm": float(cpm) if cpm else None,
            # После итога — деньги от согласованной цифры, как в «Сводной» (ревью 26.10.2026)
            "amount": _amount(req["agreed_volume"] if agreed and req.get("agreed_volume") is not None else ours, cpm),
            "status": st, "late": late, "due_at": req["due_at"].isoformat() if req and req.get("due_at") else None,
            "messages": int(req.get("messages") or 0) if req else 0, "new": bool(req and req.get("unread")),
            "request_id": req["id"] if req else None,
            "decided_at": req["decided_at"].isoformat() if req and req.get("decided_at") else None,
            "decided_by": req.get("decided_by") if req else None,
            "orphan": bool(a.get("orphan")),
            # после итога: что сейчас — для пометки «изменилось после согласования»
            "changed": changed, "fact_now": a["fact"],
        })
    out.sort(key=lambda r: (ORDER["late" if r["late"] else r["status"]], -(r["amount"] or 0), r["site"] or ""))
    return out


def months_between(start: str, end: str) -> List[str]:
    y, m = map(int, start.split("-"))
    out = []
    while f"{y:04d}-{m:02d}" <= end:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def unagreed_before(db: Session, period: str, today: Optional[date] = None) -> List[dict]:
    """Прошлые месяцы (с октября 2026) с несогласованными сверками — для жёлтой строки на текущем месяце."""
    out = []
    prev = [m for m in months_between(START, period) if m < period]
    for m in prev:
        n = sum(1 for r in month_rows(db, m, today) if r["status"] != DONE)
        if n:
            out.append({"period": m, "count": n})
    return out


def board(db: Session, period: str, today: Optional[date] = None) -> dict:
    today = today or date.today()
    return {"period": period, "start": START, "active": period >= START,
            "rows": month_rows(db, period, today) if period >= START else [],
            "past": unagreed_before(db, period, today)}


def detail(db: Session, publisher_id: int, period: str, today: Optional[date] = None) -> Optional[dict]:
    """Модалка: строка площадки, кампании месяца, переписка с вложениями."""
    row = next((r for r in month_rows(db, period, today) if r["publisher_id"] == publisher_id), None)
    if row is None:
        return None
    places = _placements(db, period, publisher_id)
    colors = _service_colors(db, [p["placement_id"] for p in places])
    camps = [{**{k: p[k] for k in ("placement_id", "brand", "service", "surface", "erid", "status")},
              "service_color": colors.get(p["placement_id"]),
              "date_from": p["date_from"].isoformat() if p["date_from"] else None,
              "date_to": p["date_to"].isoformat() if p["date_to"] else None,
              "plan": int(p["plan"] or 0), "fact": int(p["fact"] or 0), "amount": _amount(int(p["fact"] or 0), p["cpm"])}
             for p in places]
    return {"row": row, "campaigns": camps,
            "thread": thread(db, row["request_id"]) if row["request_id"] else []}


def _service_colors(db: Session, target_ids: List[int]) -> Dict[int, Optional[str]]:
    """Цвет услуги сделки из справочника услуг — маркер в таблице кампаний (дизайн 26.10)."""
    if not target_ids:
        return {}
    return {r[0]: r[1] for r in db.execute(text("""
        SELECT t.id, s.color FROM launch_prep_target t JOIN sales_deals d ON d.id = t.deal_id
          LEFT JOIN sales_services s ON s.id = COALESCE(d.service_id, (SELECT x.id FROM sales_services x WHERE x.name = d.product)) WHERE t.id = ANY(:ids)"""), {"ids": target_ids})}


def thread(db: Session, request_id: int) -> List[dict]:
    msgs = db.execute(text("""
        SELECT id, side, author_name, body, volume, created_at FROM publisher_request_message
         WHERE request_id = :r ORDER BY id"""), {"r": request_id}).mappings().all()
    files: Dict[int, list] = {}
    for f in db.execute(text("""
            SELECT f.id, f.message_id, f.original_name, f.size_bytes FROM publisher_request_file f
              JOIN publisher_request_message m ON m.id = f.message_id WHERE m.request_id = :r ORDER BY f.id"""),
            {"r": request_id}).mappings().all():
        files.setdefault(f["message_id"], []).append({"id": f["id"], "name": f["original_name"],
                                                       "size_bytes": f["size_bytes"]})
    # Момент в UTC: экран переводит в Москву сам (`lib/dates`), двойной перевод сдвинул бы на 3 часа.
    return [{**dict(m), "created_at": m["created_at"].isoformat(), "files": files.get(m["id"], [])} for m in msgs]


def summary(db: Session, year: int, today: Optional[date] = None) -> dict:
    """Сводная: площадки × месяцы года; значение — итог сверки, до согласования — наши данные (дизайн 26.10)."""
    today = today or date.today()
    cur = today.strftime("%Y-%m")
    months = [f"{year:04d}-{m:02d}" for m in range(1, 13) if f"{year:04d}-{m:02d}" <= cur]
    pubs: Dict[int, dict] = {}
    for m in months:
        if m >= START:
            rows = month_rows(db, m, today)
        else:
            rows = [{"publisher_id": pid, "site": a["site"], "ours": a["fact"], "agreed": None, "theirs": None,
                     "cpm": a["cpm"], "status": None, "total": a["total"]}
                    for pid, a in _plain_month(db, m).items()]
        for r in rows:
            p = pubs.setdefault(r["publisher_id"], {"publisher_id": r["publisher_id"], "site": r["site"], "cells": {}})
            value = r["agreed"] if r.get("agreed") is not None else r["ours"]
            p["cells"][m] = {"shows": value, "amount": _amount(value, r["cpm"]), "status": r["status"],
                             "ours": r["ours"], "theirs": r.get("theirs"), "total": r.get("total"),
                             "no_cpm": not r["cpm"]}
    # Пустые месяцы в начале года не рисуем: размещения в системе есть не с января (на проде — с конца лета).
    used = [m for m in months if any(m in p["cells"] for p in pubs.values())]
    months = months[months.index(used[0]):] if used else []
    return {"year": year, "months": months, "start": START,
            "rows": sorted(pubs.values(), key=lambda p: -sum((c["amount"] or 0) for c in p["cells"].values()))}


def _plain_month(db: Session, period: str) -> Dict[int, dict]:
    out: Dict[int, dict] = {}
    for p in _placements(db, period):
        a = out.setdefault(p["publisher_id"], {"site": p["site"], "fact": 0, "cpm": p["cpm"], "total": 0})
        a["fact"] += int(p["fact"] or 0)
        a["total"] += 1
    return out


def target_facts(db: Session, publisher_id: int, period: str) -> Dict[int, int]:
    """Наш факт по размещениям площадки за месяц — основа разнесения итога."""
    return {p["placement_id"]: int(p["fact"] or 0) for p in _placements(db, period, publisher_id)}
