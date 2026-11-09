# -*- coding: utf-8 -*-
"""Забор очереди модерации SSP в нашу базу. Крон раз в 10 минут: `python -m app.premod.sync`.

Разметку тянем только у новых заявок и у тех, что SSP обновил (`updated_at` сдвинулся): иначе каждые
10 минут — сотня запросов ради одного и того же. Изменилась разметка → другой хеш → заявка уходит в
другой пакет и снова ждёт решения (прежние решения остаются в истории — по старому хешу).

В SSP ничего не пишется.
"""
import app.model_registry  # noqa: F401  — крон отдельным процессом (заметка cron-standalone-model-registry)

import logging
import re
import sys
from datetime import datetime
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.launch_prep import sandbox
from app.premod import checks, markup as M, package_checks as PC, service, ssp
from app.premod.models import PremodPackage, PremodRequest

log = logging.getLogger("premod.sync")
UPLOADS_ROOT = "/app/uploads"
_HTML5 = re.compile(r"<canvas\b|createjs|gsap|<video\b", re.I)


def _ts(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "").replace("T", " ")[:19])
    except ValueError:
        return None


def kind_of(html: str) -> str:
    if _HTML5.search(html or ""):
        return "HTML5"
    clean = M.sanitize(html)
    if re.search(r"<img\b", clean, re.I) and not M.external_hosts(clean):
        return "статика"
    return "прочее"


def _package(db: Session, html: str, stash, previous_id: Optional[int]) -> PremodPackage:
    h, kind = M.image_hash(html), kind_of(html)
    text = None if kind == "статика" else M.visible_text(M.sanitize(html))
    pkg = db.query(PremodPackage).filter(PremodPackage.image_hash == h).first()
    if pkg:
        pkg.kind, pkg.text = kind, text   # тот же хеш — та же разметка; обновляем, если правила разбора поменялись
        return pkg
    info = M.ord_info(html) or {}
    token, _ = stash(UPLOADS_ROOT, M.sanitize(html))
    pkg = PremodPackage(image_hash=h, size=M.size(html), kind=kind,
                        advertiser_name=info.get("name") or None, advertiser_inn=info.get("inn") or None,
                        snapshot_token=token, text=text)
    prev = db.get(PremodPackage, previous_id) if previous_id else None
    if prev is not None:   # SSP поменял креатив у заявки, которую мы уже видели
        pkg.prev_package_id = prev.id
        pkg.changes = PC.changes({"size": prev.size, "text": prev.text, "hosts": service.hosts_of(prev)},
                                 {"size": pkg.size, "text": pkg.text, "hosts": M.external_hosts(M.sanitize(html))})
    db.add(pkg)
    db.flush()
    return pkg


def _apply_markup(db: Session, req: PremodRequest, html: str, stash) -> None:
    old_id = req.package_id
    pkg = _package(db, html, stash, old_id)
    req.package_id = pkg.id
    req.click_url = M.click_href(html)
    req.landing = M.landing(html)
    req.checks = checks.run(req.erid, html)
    req.fetched_at = datetime.utcnow()
    db.flush()
    service.refresh_checks(db, pkg, M.external_hosts(M.sanitize(html)))
    old = db.get(PremodPackage, old_id) if old_id and old_id != pkg.id else None
    if old is not None:
        service.refresh_checks(db, old, service.hosts_of(old))


def sync(db: Session, *, fetch_list: Callable = ssp.fetch_list, fetch_markup: Callable = ssp.fetch_markup,
         stash: Callable = sandbox.stash_html, recheck: bool = False) -> dict:
    """Один проход. Возвращает счётчики — для журнала крона и проверки руками.

    `recheck` — забрать разметку у ВСЕХ заявок и пересчитать проверки (правила проверок или категория
    заказчика поменялись). Только чтение у SSP, как и обычный проход.
    """
    stats = {"seen": 0, "new": 0, "refetched": 0, "failed": 0}
    now = datetime.utcnow()
    for item in fetch_list():
        stats["seen"] += 1
        uuid = item.get("uuid")
        if not uuid:
            continue
        req = db.query(PremodRequest).filter(PremodRequest.ssp_uuid == uuid).first()
        updated = _ts(item.get("updated_at"))
        fresh = req is None
        changed = not fresh and updated is not None and updated != req.ssp_updated_at
        if fresh:
            req = PremodRequest(ssp_uuid=uuid)
            db.add(req)
        req.erid, req.crid = item.get("erid"), item.get("crid")
        req.ssp_publishers = [int(p) for p in item.get("publishers") or []]
        req.ssp_status = item.get("status")
        req.ssp_updated_at = updated
        req.ssp_moderated_by = item.get("moderated_by") or None
        req.preview_url = item.get("preview_url")
        req.last_seen_at = now
        if fresh or changed or recheck or req.package_id is None:
            try:
                _apply_markup(db, req, fetch_markup(req.preview_url), stash)
                stats["new" if fresh else "refetched"] += 1
            except (ssp.SspError, sandbox.SandboxError) as e:
                stats["failed"] += 1
                log.warning("премодерация: разметка %s не забрана: %s", uuid, e)
        db.flush()
    db.commit()
    return stats


def main() -> None:
    from app.database import SessionLocal
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    # httpx на INFO пишет каждый запрос с полным адресом кабинета SSP — сотня строк за проход и адрес в логе.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not ssp.configured():
        log.info("премодерация: кабинет SSP не настроен — пропуск")
        return
    db = SessionLocal()
    try:
        log.info("премодерация: %s", sync(db, recheck="--recheck" in sys.argv))
    finally:
        db.close()


if __name__ == "__main__":
    main()
