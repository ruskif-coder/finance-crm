# -*- coding: utf-8 -*-
"""Выдача экрана «Премодерация» одним ответом — в контракте макета (`sampleData.js` хендоффа).

Фильтры, поиск и группировка — на фронте. Проверки пакета считает сервер (`package_checks`) при заборе
очереди; фронт их показывает, а не пересчитывает. Решения живут у заявок (`premod_decision`), а макет
показывает их у пакета — здесь заявки одного решения сводятся в одно событие.

Чего нет против макета (владелец 08.11.2026): распознанного текста статики, веса, длительности анимации
и снимка PNG при решении — для них нужен браузер без окна, отдельным этапом. Учётки SSP не сопоставлены
с нашими паблишерами (ждём админа трафика), поэтому `places[acc].name` — пусто.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.launch_prep import sandbox
from app.premod import checks as RC
from app.premod import package_checks as PC
from app.premod import service as S
from app.premod.models import APPROVED, PremodAdvertiser, PremodDecision, PremodPackage, PremodRequest

STATUS = {S.PENDING: "wait", S.CHANGED: "changed", S.APPROVED_STATE: "approved", S.DECLINED_STATE: "declined"}
VERDICT_OUT = {APPROVED: "approved", "отклонено": "declined"}
SYNC_EVERY = timedelta(minutes=10)
SYNC_STALE = timedelta(minutes=25)       # два пропущенных прохода крона — уже сбой
FREQUENT_DAYS, FREQUENT_TOP = 30, 4


def iso(dt: Optional[datetime]) -> Optional[str]:
    """Время в базе — UTC без пояса; фронт считает московское сам, ему нужен явный `Z`."""
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


def size_out(size: Optional[str]) -> Optional[str]:
    return size.replace("x", "×") if size else None


def _adv_key(pkg: PremodPackage) -> str:
    return pkg.advertiser_inn or "name:" + (pkg.advertiser_name or "")


def advertisers(db: Session, pkgs: List[PremodPackage], trust: Dict[str, dict]) -> dict:
    rows = {a.inn: a for a in db.query(PremodAdvertiser).all()}
    out = {}
    for p in pkgs:
        key = _adv_key(p)
        row = rows.get(p.advertiser_inn)
        out[key] = {"short": (row.short_name if row and row.short_name else PC.short_name(p.advertiser_name)),
                    "name": p.advertiser_name or "Заказчик не указан", "inn": p.advertiser_inn or "—",
                    "category": row.category if row else None,
                    "trust": trust.get(key, {"same": 0, "total": 0})}
    return out


# Категории, от которых зависит проверка предупреждения; остальные копятся вводом (накопительный список).
BASE_CATEGORIES = (PC.DRUGS, PC.SUPPLEMENTS)


def categories(db: Session) -> List[str]:
    used = {c for (c,) in db.query(PremodAdvertiser.category).filter(PremodAdvertiser.category.isnot(None)).all()}
    return list(BASE_CATEGORIES) + sorted(used - set(BASE_CATEGORIES))


def _events(decisions: List[PremodDecision]) -> List[List[PremodDecision]]:
    """Заявки, решённые одним нажатием, — одно событие (одна транзакция даёт одно время `now()`)."""
    by = defaultdict(list)
    for d in decisions:
        by[(d.decided_at, d.decided_by, d.verdict, d.image_hash)].append(d)
    return sorted(by.values(), key=lambda g: (g[0].decided_at, g[0].id), reverse=True)


def decision_out(group: List[PremodDecision], names: dict, version_of: Dict[str, int]) -> dict:
    d = group[0]
    return {"id": d.id, "verdict": VERDICT_OUT[d.verdict], "request_ids": [x.request_id for x in group],
            "reason_code": d.reason_code, "reason": d.reason_label, "comment": d.comment,
            "by": names.get(d.decided_by) or "—", "at": iso(d.decided_at),
            "version": version_of.get(d.image_hash), "repeat": d.followed_package is True,
            "bulk": bool(d.bulk), "snapshot_png_url": None}


def _host_path(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    parts = urlsplit(url)
    return ((parts.hostname or "") + parts.path).rstrip("/") or None


def request_out(r: PremodRequest) -> dict:
    erid = next((c for c in r.checks or [] if c.get("key") == "erid"), {})
    return {"uuid": r.id, "erid": r.erid or "—", "crid": r.crid,
            "acc": ",".join(str(x) for x in r.ssp_publishers or []) or "—",
            "ssp_status": S.SSP_STATUS.get(r.ssp_status, "—"), "ssp_by": r.ssp_moderated_by,
            "created_at": iso(r.ssp_updated_at or r.fetched_at),
            # Ссылка клика целиком (в ней ЕРИД), посадочная — уже развёрнутая из редиректов. Обе — текстом.
            "landing": r.click_url or r.landing or "", "dest": _host_path(r.landing),
            "err": erid.get("detail", "") if erid.get("state") == PC.BAD else "",
            "link_erid": RC.erid_in_link(r.click_url)}


def _prev(pkg, reqs, by_req, names, version_of) -> Optional[dict]:
    """Прежняя версия креатива: последнее решение у заявок пакета по другому хешу."""
    old = [d for r in reqs for d in by_req.get(r.id, []) if d.image_hash != pkg.image_hash]
    if not old:
        return None
    last = max(old, key=lambda d: (d.decided_at, d.id))
    return {"version": version_of.get(last.image_hash) or pkg.prev_package_id, "decided_by": names.get(last.decided_by),
            "decided_at": iso(last.decided_at), "snapshot_png_url": None,
            "changes": pkg.changes or PC.changes({}, {})}


def package_out(pkg, reqs, by_req, names, version_of) -> dict:
    state = S.state_of(pkg, reqs, by_req)
    current = [d for r in reqs for d in by_req.get(r.id, []) if d.image_hash == pkg.image_hash]
    prior = S.package_prior(by_req, reqs, pkg.image_hash)
    waiting = state in (S.PENDING, S.CHANGED)
    hosts = next((c["short"].split(", ") for c in pkg.checks or [] if c.get("key") == "scripts"
                  and c.get("state") == PC.WARN), [])
    return {
        "id": pkg.id, "advertiser": _adv_key(pkg), "ord_inn": pkg.advertiser_inn,
        "size": size_out(pkg.size), "size_guess": None if pkg.size else "не объявлен", "type": pkg.kind or "прочее",
        "weight_kb": None, "anim_s": None, "scripts": [{"host": h, "known": False} for h in hosts],
        "text": pkg.text, "text_source": "html" if pkg.text else None,
        "snapshot_url": sandbox.public_url(pkg.snapshot_token, "index.html"),
        "status": STATUS[state], "checks": pkg.checks or [],
        "requests": [request_out(r) for r in reqs],
        "decisions": [decision_out(g, names, version_of) for g in _events(current)],
        "same_creative": ({"by": names.get(prior.decided_by), "at": iso(prior.decided_at),
                           "request": next((r.erid for r in reqs if r.id == prior.request_id), "—"),
                           "note": "та же версия креатива"}
                          if waiting and prior is not None and prior.verdict == APPROVED else None),
        "prev": _prev(pkg, reqs, by_req, names, version_of) if state == S.CHANGED else None,
    }


def trust_by_advertiser(pkgs: Dict[int, PremodPackage], by_pkg, by_req) -> Dict[str, dict]:
    """Сколько повторных решений совпало с прежним решением пакета — копится для будущего автоодобрения."""
    out: Dict[str, dict] = defaultdict(lambda: {"same": 0, "total": 0})
    for pid, reqs in by_pkg.items():
        key = _adv_key(pkgs[pid])
        for group in _events([d for r in reqs for d in by_req.get(r.id, [])]):
            if group[0].followed_package is not None:
                out[key]["total"] += 1
                out[key]["same"] += int(group[0].followed_package)
    return out


def reasons_out(tree: List[dict]) -> List[dict]:
    """Дерево причин SSP: невыбираемый пункт — заголовок группы, выбираемые под ним — причины."""
    out: List[dict] = []
    for r in tree or []:
        label = f"{r.get('number', '')} {r.get('title', '')}".strip()
        if not r.get("canSelected"):
            out.append({"group": label, "items": []})
        else:
            if not out:
                out.append({"group": "Причины", "items": []})
            out[-1]["items"].append({"code": r["id"], "label": label})
    return [g for g in out if g["items"]]


def frequent(db: Session, now: datetime) -> List[int]:
    since = now - timedelta(days=FREQUENT_DAYS)
    rows = (db.query(PremodDecision.reason_code).filter(PremodDecision.reason_code.isnot(None),
                                                         PremodDecision.decided_at >= since).all())
    counts: Dict[int, int] = defaultdict(int)
    for (code,) in rows:
        counts[code] += 1
    return [c for c, _ in sorted(counts.items(), key=lambda x: -x[1])[:FREQUENT_TOP]]


def sync_state(reqs: List[PremodRequest], now: datetime) -> dict:
    """Состояние крона по следам в данных: когда последний раз видели очередь SSP."""
    last = max((r.last_seen_at for r in reqs), default=None)
    if last is None:
        return {"ok": False, "last_at": None, "next_at": None, "fetched": 0, "new": 0,
                "error": {"at": iso(now), "retry_at": iso(now + SYNC_EVERY), "message": "очередь SSP ещё не забиралась"}}
    fetched = sum(1 for r in reqs if r.last_seen_at == last)
    new = sum(1 for r in reqs if r.fetched_at and r.fetched_at >= last - SYNC_EVERY)
    stale = now - last > SYNC_STALE
    return {"ok": not stale, "last_at": iso(last), "next_at": iso(last + SYNC_EVERY), "fetched": fetched, "new": new,
            "error": ({"at": iso(now), "retry_at": iso(now + SYNC_EVERY),
                       "message": f"очередь не обновлялась {int((now - last).total_seconds() // 60)} мин"}
                      if stale else None)}


def board(db: Session, can_decide: bool, reason_tree: List[dict], now: Optional[datetime] = None) -> dict:
    now = now or datetime.utcnow()
    pkgs, by_pkg, by_req = S.load(db)
    live = [p for p in pkgs.values() if by_pkg.get(p.id)]
    all_reqs = [r for rs in by_pkg.values() for r in rs]
    names = S.user_names(db, [d.decided_by for ds in by_req.values() for d in ds])
    version_of = {p.image_hash: p.id for p in pkgs.values()}
    accs = {",".join(str(x) for x in r.ssp_publishers or []) or "—" for r in all_reqs}
    return {
        "now": iso(now), "can_decide": can_decide, "sync": sync_state(all_reqs, now),
        "places": {a: {"name": None, "draft": True} for a in sorted(accs)},
        "advertisers": advertisers(db, live, trust_by_advertiser(pkgs, by_pkg, by_req)),
        "reasons": reasons_out(reason_tree), "frequent": frequent(db, now), "categories": categories(db),
        "packages": [package_out(p, by_pkg[p.id], by_req, names, version_of) for p in live],
    }
