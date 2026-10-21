# -*- coding: utf-8 -*-
"""Операции над шаблонами ДС: базовые шаблоны и их форматы, сохранение версии, откат, кастомный под договор, «базовый изменился».

Версии только добавляются. Каждая операция берёт блокировку строки шаблона (`FOR UPDATE`), поэтому две
параллельные правки не получат один номер версии; номер к тому же держит `UNIQUE (template_id, version)`.
Коммит — за вызывающим: ручка коммитит одним куском вместе с записью в журнал.
"""
import copy
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.annex_tpl.check import check, check_transition
from app.annex_tpl.diff import diff
from app.annex_tpl.formats import clean
from app.annex_tpl.models import AnnexTplFormat, AnnexTplTemplate, AnnexTplVersion


class AnnexTplError(Exception):
    def __init__(self, status: int, message: str, issues: Optional[list] = None):
        super().__init__(message)
        self.status, self.message, self.issues = status, message, issues or []


def current(db: Session, template_id: int) -> Optional[AnnexTplVersion]:
    return (db.query(AnnexTplVersion).filter_by(template_id=template_id)
            .order_by(AnnexTplVersion.version.desc()).first())


def version_of(db: Session, template_id: int, version: int) -> Optional[AnnexTplVersion]:
    return db.query(AnnexTplVersion).filter_by(template_id=template_id, version=version).first()


def custom_of(db: Session, contract_id: int) -> Optional[AnnexTplTemplate]:
    return db.query(AnnexTplTemplate).filter_by(scope="custom", contract_id=contract_id).first()


def base_by_title(db: Session, title: str) -> Optional[AnnexTplTemplate]:
    return (db.query(AnnexTplTemplate)
            .filter(AnnexTplTemplate.scope == "base", func.lower(AnnexTplTemplate.title) == (title or "").strip().lower())
            .first())


def base_for_format(db: Session, fmt: Optional[str]) -> Optional[AnnexTplTemplate]:
    """Базовый шаблон, обслуживающий формат сотрудничества договора. Пустой или не заведённый формат — None."""
    f = clean(fmt)
    row = db.query(AnnexTplFormat).filter_by(format=f).first() if f else None
    return db.query(AnnexTplTemplate).filter_by(id=row.template_id).first() if row else None


def formats_of(db: Session, template_id: int) -> list:
    return sorted(r.format for r in db.query(AnnexTplFormat).filter_by(template_id=template_id))


def _lock(db: Session, template_id: int) -> AnnexTplTemplate:
    t = db.query(AnnexTplTemplate).filter_by(id=template_id).with_for_update().first()
    if t is None:
        raise AnnexTplError(404, "Шаблон не найден")
    return t


def _add(db: Session, tpl: AnnexTplTemplate, blocks: list, user_id, user_name: str, *,
         base_version: Optional[int] = None, restored_from: Optional[int] = None,
         changes: Optional[list] = None) -> AnnexTplVersion:
    cur = current(db, tpl.id)
    issues = check(blocks) + check_transition(cur.blocks if cur else None, blocks)
    if issues:
        raise AnnexTplError(422, "Шаблон не прошёл проверку — версия не сохранена", issues)
    if changes is None:
        n = sum(1 for b in blocks if not b.get("sys"))
        changes = diff(cur.blocks, blocks) if cur else [["+", "шаблон создан", f"пунктов: {n}"]]
    row = AnnexTplVersion(
        template_id=tpl.id, version=(cur.version + 1) if cur else 1, blocks=copy.deepcopy(blocks),
        changes=changes, base_version=base_version, restored_from=restored_from,
        author_id=user_id, author_name=user_name)
    db.add(row)
    db.flush()
    return row


# ── базовые шаблоны и их форматы ─────────────────────────────────────────────────────────────

def set_formats(db: Session, template_id: int, formats: Iterable[str]) -> list:
    """Шаблон обслуживает РОВНО эти форматы. Формат, занятый другим шаблоном, переходит к этому;
    формат, которого нет в списке, освобождается (договор с ним остаётся без шаблона, пока формат не назначат)."""
    tpl = _lock(db, template_id)
    if tpl.scope != "base":
        raise AnnexTplError(400, "Форматы назначаются только базовому шаблону")
    want = {clean(f) for f in formats if clean(f)}
    for row in db.query(AnnexTplFormat).filter_by(template_id=tpl.id):
        if row.format not in want:
            db.delete(row)
    for f in want:
        row = db.query(AnnexTplFormat).filter_by(format=f).first()
        if row is None:
            db.add(AnnexTplFormat(format=f, template_id=tpl.id))
        elif row.template_id != tpl.id:
            row.template_id = tpl.id
    db.flush()
    return formats_of(db, tpl.id)


def create_base(db: Session, title: str, blocks: list, user_id, user_name: str, formats: Iterable[str] = ()) -> AnnexTplVersion:
    """Новый базовый шаблон (вариант договора): название уникально; v1 проходит ту же проверку, что любое сохранение."""
    title = (title or "").strip()
    if not title:
        raise AnnexTplError(400, "У шаблона должно быть название")
    if base_by_title(db, title):
        raise AnnexTplError(409, f"Базовый шаблон «{title}» уже есть")
    tpl = AnnexTplTemplate(scope="base", title=title, created_by=user_id)
    db.add(tpl)
    db.flush()
    v = _add(db, tpl, blocks, user_id, user_name)
    set_formats(db, tpl.id, formats)
    return v


def seed_base(db: Session, title: str, blocks: list, author_name: str, formats: Iterable[str] = ()) -> AnnexTplVersion:
    """Заводит базовый шаблон и его v1. Повторный вызов ничего не делает (возвращает текущую версию)."""
    tpl = base_by_title(db, title)
    if tpl:
        return current(db, tpl.id)
    return create_base(db, title, blocks, None, author_name, formats)


# ── версии ───────────────────────────────────────────────────────────────────────────────────

def _base_version(db: Session, tpl: AnnexTplTemplate) -> int:
    cur = current(db, tpl.base_template_id) if tpl.base_template_id else None
    if not cur:
        raise AnnexTplError(409, "У кастомного шаблона нет базового")
    return cur.version


def save_version(db: Session, template_id: int, blocks: list, user, adopt_base: bool = False) -> AnnexTplVersion:
    tpl = _lock(db, template_id)
    cur = current(db, tpl.id)
    if cur is None:
        raise AnnexTplError(409, "У шаблона нет версий")
    bv = cur.base_version
    if tpl.scope == "custom" and adopt_base:
        bv = _base_version(db, tpl)
    elif tpl.scope == "base":
        bv = None
    if blocks == cur.blocks and bv == cur.base_version:
        raise AnnexTplError(400, "Изменений нет — новая версия не нужна")
    changes = diff(cur.blocks, blocks)
    if bv != cur.base_version:
        changes.append(["≡", "базовый шаблон", f"принята версия v{bv}"])
    return _add(db, tpl, blocks, user.id, user.name or "—", base_version=bv, changes=changes)


def restore(db: Session, template_id: int, version: int, user) -> AnnexTplVersion:
    """Откат создаёт НОВУЮ версию с текстом старой; история не стирается."""
    tpl = _lock(db, template_id)
    cur, old = current(db, tpl.id), version_of(db, tpl.id, version)
    if old is None:
        raise AnnexTplError(404, f"Версии v{version} нет")
    if cur and old.version == cur.version:
        raise AnnexTplError(400, "Это текущая версия")
    if cur and old.blocks == cur.blocks:
        raise AnnexTplError(400, f"Текст v{version} совпадает с текущим — откатывать нечего")
    return _add(db, tpl, old.blocks, user.id, user.name or "—",
                base_version=cur.base_version if tpl.scope == "custom" else None,
                restored_from=old.version, changes=diff(cur.blocks, old.blocks))


# ── кастомный под договор ────────────────────────────────────────────────────────────────────

def fork_custom(db: Session, contract, user) -> AnnexTplVersion:
    """Кастомный шаблон под договор: копия ТЕКУЩЕЙ версии базового шаблона его формата, v1; запоминает версию базы."""
    fmt = clean(getattr(contract, "cooperation_format", None))
    if not fmt:
        raise AnnexTplError(400, "У договора не указан «Формат сотрудничества» — шаблон не определён")
    if custom_of(db, contract.id):
        raise AnnexTplError(409, "У договора уже есть кастомный шаблон")
    base = base_for_format(db, fmt)
    bcur = current(db, base.id) if base else None
    if not bcur:
        raise AnnexTplError(409, f"Для формата «{fmt}» не задан базовый шаблон")
    tpl = AnnexTplTemplate(scope="custom", contract_id=contract.id, base_template_id=base.id, created_by=user.id)
    db.add(tpl)
    db.flush()
    return _add(db, tpl, bcur.blocks, user.id, user.name or "—", base_version=bcur.version,
                changes=[["+", "шаблон создан", f"ответвлён от «{base.title}» v{bcur.version}"]])


def keep_own(db: Session, template_id: int, user) -> AnnexTplVersion:
    """«Оставить свой»: текст не меняется, версия базы принимается. Это новая версия (версии не правятся),
    с пометкой `≡` в истории."""
    tpl = _lock(db, template_id)
    if tpl.scope != "custom":
        raise AnnexTplError(400, "Только у кастомного шаблона")
    cur = current(db, tpl.id)
    bv = _base_version(db, tpl)
    if bv == cur.base_version:
        raise AnnexTplError(409, "Базовый шаблон не менялся")
    return _add(db, tpl, cur.blocks, user.id, user.name or "—", base_version=bv,
                changes=[["≡", "базовый шаблон", f"принята версия v{bv}, текст оставлен"]])


def base_state(db: Session, tpl: AnnexTplTemplate) -> Optional[dict]:
    """Для кастомного: изменилась ли база с момента согласования. Для базового — None."""
    if tpl.scope != "custom":
        return None
    cur = current(db, tpl.id)
    bcur = current(db, tpl.base_template_id)
    if not (cur and bcur):
        return {"changed": False, "known": cur.base_version if cur else None, "now": None}
    return {"changed": bcur.version > (cur.base_version or 0), "known": cur.base_version, "now": bcur.version}


def base_changes(db: Session, tpl: AnnexTplTemplate) -> list:
    """Что изменилось в базе между известной шаблону договора версией и текущей."""
    st = base_state(db, tpl)
    if not st or not st["changed"]:
        return []
    known = version_of(db, tpl.base_template_id, st["known"])
    return diff(known.blocks, current(db, tpl.base_template_id).blocks) if known else []


def customs_behind(db: Session, base_template_id: Optional[int] = None) -> list:
    """Кастомные шаблоны договоров, отставшие от своей базы (база сохранена новее, чем версия, с которой согласован кастомный).
    Для «Юр запросов», реестра договоров и уведомления юристам (владелец 14.10.2026)."""
    q = db.query(AnnexTplTemplate).filter(AnnexTplTemplate.scope == "custom")
    if base_template_id:
        q = q.filter(AnnexTplTemplate.base_template_id == base_template_id)
    out = []
    for t in q.order_by(AnnexTplTemplate.id).all():
        st = base_state(db, t)
        if st and st["changed"]:
            out.append({"template_id": t.id, "contract_id": t.contract_id, "known": st["known"], "now": st["now"]})
    return out


def resolve_for_contract(db: Session, contract) -> dict:
    """Какой шаблон прикреплён к договору: свой кастомный, иначе базовый его формата, иначе причина, почему нет."""
    own = custom_of(db, contract.id)
    if own:
        return {"source": "custom", "template": own, "reason": None}
    fmt = clean(getattr(contract, "cooperation_format", None))
    if not fmt:
        return {"source": "none", "template": None,
                "reason": "У договора не указан «Формат сотрудничества» — шаблон не определён, ДС не собирается"}
    base = base_for_format(db, fmt)
    if base is None:
        return {"source": "none", "template": None,
                "reason": f"Для формата «{fmt}» не задан базовый шаблон — ДС не собирается"}
    return {"source": "base", "template": base, "reason": None}
