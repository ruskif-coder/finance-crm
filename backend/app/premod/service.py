# -*- coding: utf-8 -*-
"""Премодерация: состояние пакетов, карточка, решение, счётчик неразобранного.

Решение живёт у ЗАЯВКИ и привязано к версии креатива (`image_hash`): заявка «ждёт», пока у неё нет решения
по текущему хешу своего пакета. Пакет «ждёт», если ждёт хоть одна его заявка; «изменился» — если ждущая
заявка уже решалась, но по другой версии креатива.

Новая заявка к уже решённому пакету не одобряется сама (владелец 07.11.2026: «ждём, пока не накопим
стату») — ей показывается подсказка «такой же одобрен <когда>, <кто>», а в решении пишется
`followed_package`: повторил ли человек прежнее решение пакета.
"""
from collections import defaultdict
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import User
from app.premod import package_checks as PC
from app.premod.models import (APPROVED, DECLINED, VERDICTS, PremodAdvertiser, PremodDecision, PremodPackage,
                               PremodRequest)

PENDING, CHANGED, APPROVED_STATE, DECLINED_STATE = "pending", "changed", "approved", "declined"
SSP_STATUS = {0: "ждёт", 1: "одобрено", 2: "отклонено"}


class DecisionError(ValueError):
    """Решение не принято; текст показывается человеку."""


def load(db: Session, package_ids=None):
    pq = db.query(PremodPackage)
    if package_ids is not None:
        pq = pq.filter(PremodPackage.id.in_(package_ids))
    packages = {p.id: p for p in pq.all()}
    reqs = (db.query(PremodRequest).filter(PremodRequest.package_id.in_(list(packages) or [0]))
            .order_by(PremodRequest.id).all())
    decs = (db.query(PremodDecision).filter(PremodDecision.request_id.in_([r.id for r in reqs] or [0]))
            .order_by(PremodDecision.decided_at, PremodDecision.id).all())
    by_pkg: Dict[int, list] = defaultdict(list)
    for r in reqs:
        by_pkg[r.package_id].append(r)
    by_req: Dict[int, list] = defaultdict(list)
    for d in decs:
        by_req[d.request_id].append(d)
    return packages, by_pkg, by_req


def _current(decisions: list, image_hash: str) -> Optional[PremodDecision]:
    """Последнее решение по ЭТОЙ версии креатива."""
    same = [d for d in decisions if d.image_hash == image_hash]
    return same[-1] if same else None


def package_prior(by_req: dict, reqs: list, image_hash: str) -> Optional[PremodDecision]:
    """Последнее решение по этому креативу у любой заявки пакета — основа подсказки и `followed_package`."""
    pool = [d for r in reqs for d in by_req.get(r.id, []) if d.image_hash == image_hash]
    return max(pool, key=lambda d: (d.decided_at, d.id)) if pool else None


def state_of(pkg: PremodPackage, reqs: list, by_req: dict) -> str:
    waiting = [r for r in reqs if _current(by_req.get(r.id, []), pkg.image_hash) is None]
    if waiting:
        return CHANGED if any(by_req.get(r.id) for r in waiting) else PENDING
    verdicts = {_current(by_req[r.id], pkg.image_hash).verdict for r in reqs}
    return APPROVED_STATE if APPROVED in verdicts else DECLINED_STATE


def waiting_count(db: Session) -> int:
    """Неразобранные пакеты — для индикатора в меню. Один запрос, без загрузки строк."""
    return db.execute(text("""
        SELECT count(DISTINCT p.id) FROM premod_package p
          JOIN premod_request r ON r.package_id = p.id
         WHERE NOT EXISTS (SELECT 1 FROM premod_decision d
                            WHERE d.request_id = r.id AND d.image_hash = p.image_hash)
    """)).scalar() or 0


def user_names(db: Session, ids) -> Dict[int, str]:
    ids = [i for i in set(ids) if i]
    return {u.id: u.name for u in db.query(User).filter(User.id.in_(ids or [0])).all()}


def decide(db: Session, user: User, package_id: int, verdict: str, request_ids: Optional[List[int]] = None,
           reason_code: Optional[int] = None, reason_label: Optional[str] = None,
           comment: Optional[str] = None, bulk: bool = False) -> List[PremodDecision]:
    """Решение по заявкам пакета. Без `request_ids` — по всем ждущим. В SSP не отправляется."""
    if verdict not in VERDICTS:
        raise DecisionError("Решение — «одобрено» или «отклонено»")
    if verdict == DECLINED and not reason_code:
        raise DecisionError("Для отказа выберите причину")
    pkgs, by_pkg, by_req = load(db, [package_id])
    pkg = pkgs.get(package_id)
    if not pkg:
        raise DecisionError("Пакет не найден")
    reqs = by_pkg.get(pkg.id, [])
    if request_ids:
        wanted = set(request_ids)
        chosen = [r for r in reqs if r.id in wanted]
        if len(chosen) != len(wanted):
            raise DecisionError("Заявка не из этого пакета")
    else:
        chosen = [r for r in reqs if _current(by_req.get(r.id, []), pkg.image_hash) is None]
    if not chosen:
        raise DecisionError("В пакете нет заявок, ждущих решения")
    prior = package_prior(by_req, reqs, pkg.image_hash)
    followed = None if prior is None else prior.verdict == verdict
    made = [PremodDecision(request_id=r.id, image_hash=pkg.image_hash, verdict=verdict,
                           reason_code=reason_code if verdict == DECLINED else None,
                           reason_label=(reason_label or None) if verdict == DECLINED else None,
                           comment=(comment or "").strip() or None, decided_by=user.id,
                           followed_package=followed, bulk=bulk)
            for r in chosen]
    db.add_all(made)
    db.flush()
    return made


class NotClean(DecisionError):
    """Среди пакетов массового одобрения есть пакет с нарушением — не одобряем ни одного."""

    def __init__(self, missing: List[int]):
        super().__init__("У пакетов есть нарушения — одобрите их по одному")
        self.missing = missing


def bulk_approve(db: Session, user: User, package_ids: List[int]) -> List[List[PremodDecision]]:
    """«Одобрить чистые»: все ждущие заявки каждого пакета. Сервер сам проверяет, что пакеты чистые."""
    pkgs = {p.id: p for p in db.query(PremodPackage).filter(PremodPackage.id.in_(package_ids or [0])).all()}
    missing = [i for i in package_ids if i not in pkgs or not PC.is_clean(pkgs[i].checks or [])]
    if missing:
        raise NotClean(missing)
    return [decide(db, user, i, APPROVED, bulk=True) for i in package_ids]


def advertiser_of(db: Session, inn: Optional[str], name: Optional[str]) -> dict:
    """Заказчик пакета; новый ИНН заводится в справочник с коротким именем, без категории."""
    row = db.get(PremodAdvertiser, inn) if inn else None
    if inn and row is None:
        row = PremodAdvertiser(inn=inn, short_name=PC.short_name(name))
        db.add(row)
        db.flush()
    return {"inn": inn, "short": row.short_name if row else PC.short_name(name),
            "category": row.category if row else None}


def hosts_of(pkg: PremodPackage) -> list:
    """Внешние скрипты пакета — из его же проверки «Внешние скрипты» (разметку мы не храним)."""
    item = next((c for c in pkg.checks or [] if c.get("key") == "scripts"), None)
    return item["short"].split(", ") if item and item.get("state") == PC.WARN else []


def refresh_checks(db: Session, pkg: PremodPackage, hosts: list) -> None:
    """Проверки пакета сводятся по всем его заявкам и категории заказчика — пересчёт при любой их смене."""
    reqs = db.query(PremodRequest).filter(PremodRequest.package_id == pkg.id).all()
    adv = advertiser_of(db, pkg.advertiser_inn, pkg.advertiser_name)
    pkg.checks = PC.package_checks(pkg.kind, pkg.text, adv, pkg.size, hosts, [r.checks or [] for r in reqs])


class UnknownAdvertiser(DecisionError):
    """ИНН нет в справочнике заказчиков премодерации."""


def set_category(db: Session, inn: str, category: Optional[str]) -> None:
    """Категория заказчика решает, нужно ли предупреждение («лекарства», «БАД»); пустая — снять."""
    row = db.get(PremodAdvertiser, inn)
    if row is None:
        raise UnknownAdvertiser("Такого заказчика в премодерации нет")
    row.category = (category or "").strip() or None
    db.flush()
    for pkg in db.query(PremodPackage).filter(PremodPackage.advertiser_inn == inn).all():
        refresh_checks(db, pkg, hosts_of(pkg))
