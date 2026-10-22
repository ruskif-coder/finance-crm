# -*- coding: utf-8 -*-
"""Шаблоны ДС: базовые именованные (с форматами договоров, которые они обслуживают) и кастомные под договор (спринт 1, 13–14.10.2026).
Роутер тонкий: вся логика — в `app/annex_tpl`. Права — секция `annex_templates` (view / create / edit), кто правит — галочки в «Ролях»."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.annex_tpl import service as S
from app.annex_tpl.check import check, numbering, zone_at
from app.annex_tpl.formats import KNOWN_FORMATS
from app.annex_tpl.models import AnnexTplFormat, AnnexTplTemplate, AnnexTplVersion
from app.annex_tpl.subs import listing
from app.audit import log_action
from app.database import get_db
from app.models import Contract, User
from app.permissions import require_permission

router = APIRouter()
VIEW = require_permission("annex_templates", "view")
CREATE = require_permission("annex_templates", "create")
EDIT = require_permission("annex_templates", "edit")


class BlocksIn(BaseModel):
    blocks: List[dict]
    adopt_base: bool = False


class RestoreIn(BaseModel):
    version: int


class ForkIn(BaseModel):
    contract_id: int


class BaseIn(BaseModel):
    title: str
    copy_from: Optional[int] = None       # скопировать текущие блоки этого шаблона
    blocks: Optional[List[dict]] = None   # или передать блоки явно
    formats: List[str] = []


class FormatsIn(BaseModel):
    formats: List[str]


def _fail(e: S.AnnexTplError):
    raise HTTPException(e.status, {"message": e.message, "issues": e.issues} if e.issues else e.message)


def _label(db: Session, t: AnnexTplTemplate) -> str:
    if t.scope == "base":
        return f"шаблон «{t.title}»"
    base = db.query(AnnexTplTemplate).filter_by(id=t.base_template_id).first()
    return f"кастомный шаблон договора {t.contract_id} (база «{base.title if base else '?'}»)"


def _row(db: Session, t: AnnexTplTemplate, with_blocks: bool = False) -> dict:
    cur = S.current(db, t.id)
    base = db.query(AnnexTplTemplate).filter_by(id=t.base_template_id).first() if t.base_template_id else None
    out = {"id": t.id, "scope": t.scope, "title": t.title or (base.title if base else None),
           "base_template_id": t.base_template_id, "contract_id": t.contract_id,
           "formats": S.formats_of(db, t.id) if t.scope == "base" else [],
           "version": cur.version if cur else None, "base_version": cur.base_version if cur else None,
           "updated_at": cur.created_at if cur else None, "author": cur.author_name if cur else None,
           "base": S.base_state(db, t)}
    if with_blocks and cur:
        out["blocks"] = cur.blocks
        out["numbers"] = numbering(cur.blocks)
        out["zones"] = {b["id"]: zone_at(cur.blocks, i) for i, b in enumerate(cur.blocks) if not b.get("sys")}
    return out


def _version(v: AnnexTplVersion, with_blocks: bool = False) -> dict:
    out = {"id": v.id, "version": v.version, "changes": v.changes, "base_version": v.base_version,
           "restored_from": v.restored_from, "author": v.author_name, "created_at": v.created_at}
    if with_blocks:
        out["blocks"] = v.blocks
    return out


def _template(db: Session, template_id: int) -> AnnexTplTemplate:
    t = db.query(AnnexTplTemplate).filter_by(id=template_id).first()
    if not t:
        raise HTTPException(404, "Шаблон не найден")
    return t


@router.get("")
def list_templates(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Базовые шаблоны и кастомные под договор — одним списком, текущие версии."""
    rows = db.query(AnnexTplTemplate).order_by(AnnexTplTemplate.scope, AnnexTplTemplate.id).all()
    return {"items": [_row(db, t) for t in rows]}


@router.get("/subs")
def subs(user: User = Depends(VIEW)):
    """Справочник подстановок — один источник для редактора."""
    return {"items": listing()}


@router.get("/formats")
def formats(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Какой базовый шаблон обслуживает какой формат сотрудничества; `known` — форматы, которые предлагает экран."""
    mapping = {r.format: r.template_id for r in db.query(AnnexTplFormat).all()}
    return {"known": list(KNOWN_FORMATS), "map": mapping}


@router.post("/check")
def check_blocks(payload: BlocksIn, user: User = Depends(VIEW)):
    """Та же проверка, что при сохранении; ничего не пишет."""
    return {"issues": check(payload.blocks)}


@router.post("/base", status_code=201)
def create_base(payload: BaseIn, db: Session = Depends(get_db), user: User = Depends(CREATE)):
    """Новый базовый шаблон — вариант договора. Блоки — копия существующего шаблона или переданные явно."""
    blocks = payload.blocks
    if payload.copy_from is not None:
        src = S.current(db, _template(db, payload.copy_from).id)
        blocks = src.blocks if src else None
    if not blocks:
        raise HTTPException(400, "Нужен шаблон-источник (copy_from) или блоки")
    try:
        v = S.create_base(db, payload.title, blocks, user.id, user.name or "—", payload.formats)
        db.commit()
    except S.AnnexTplError as e:
        db.rollback()
        _fail(e)
    t = _template(db, v.template_id)
    log_action(db, user, "annex_tpl_base_create", "annex_template", t.id,
               f"{_label(db, t)}; форматы: {', '.join(S.formats_of(db, t.id)) or '—'}")
    return _row(db, t, with_blocks=True)


@router.get("/for-contract/{contract_id}")
def for_contract(contract_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Шаблон, прикреплённый к договору: кастомный, иначе базовый его формата, иначе причина, почему нет."""
    c = db.query(Contract).filter_by(id=contract_id).first()
    if not c:
        raise HTTPException(404, "Договор не найден")
    r = S.resolve_for_contract(db, c)
    t = r["template"]
    return {"source": r["source"], "reason": r["reason"], "format": c.cooperation_format,
            "template": _row(db, t, with_blocks=True) if t else None,
            "base_changes": S.base_changes(db, t) if t and t.scope == "custom" else []}


@router.post("/custom", status_code=201)
def fork(payload: ForkIn, db: Session = Depends(get_db), user: User = Depends(CREATE)):
    c = db.query(Contract).filter_by(id=payload.contract_id).first()
    if not c:
        raise HTTPException(404, "Договор не найден")
    try:
        v = S.fork_custom(db, c, user)
        db.commit()
    except S.AnnexTplError as e:
        db.rollback()
        _fail(e)
    t = _template(db, v.template_id)
    log_action(db, user, "annex_tpl_fork", "annex_template", t.id,
               f"договор {c.contract_number or c.id}: {_label(db, t)}, база v{v.base_version}")
    return _row(db, t, with_blocks=True)


@router.get("/behind")
def behind(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Договоры, у которых кастомный шаблон ДС отстал от базового: юристу — решить «оставить свой» или «перенять базу»."""
    rows = S.customs_behind(db)
    contracts = {c.id: c for c in db.query(Contract).filter(Contract.id.in_({r["contract_id"] for r in rows})).all()} if rows else {}
    return [{**r, "contract_number": getattr(contracts.get(r["contract_id"]), "contract_number", None),
             "counterparty": getattr(contracts.get(r["contract_id"]), "counterparty_name", None),
             "format": getattr(contracts.get(r["contract_id"]), "cooperation_format", None)} for r in rows]


@router.get("/{template_id}")
def one(template_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    t = _template(db, template_id)
    out = _row(db, t, with_blocks=True)
    out["base_changes"] = S.base_changes(db, t) if t.scope == "custom" else []
    return out


@router.put("/{template_id}/formats")
def set_formats(template_id: int, payload: FormatsIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Какие форматы сотрудничества обслуживает базовый шаблон. Формат, занятый другим шаблоном, переходит к этому."""
    try:
        done = S.set_formats(db, template_id, payload.formats)
        db.commit()
    except S.AnnexTplError as e:
        db.rollback()
        _fail(e)
    t = _template(db, template_id)
    log_action(db, user, "annex_tpl_formats", "annex_template", t.id, f"{_label(db, t)}: форматы — {', '.join(done) or 'нет'}")
    return {"id": t.id, "formats": done}


@router.get("/{template_id}/versions")
def versions(template_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    _template(db, template_id)
    rows = (db.query(AnnexTplVersion).filter_by(template_id=template_id)
            .order_by(AnnexTplVersion.version.desc()).all())
    return {"items": [_version(v) for v in rows]}


@router.get("/{template_id}/versions/{version}")
def one_version(template_id: int, version: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    v = S.version_of(db, template_id, version)
    if not v:
        raise HTTPException(404, "Версия не найдена")
    return _version(v, with_blocks=True)


@router.post("/{template_id}/versions", status_code=201)
def save(template_id: int, payload: BlocksIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Сохранить новую версию. Не прошла проверку — 422 со списком ошибок, в базу ничего не попадает."""
    try:
        v = S.save_version(db, template_id, payload.blocks, user, payload.adopt_base)
        db.commit()
    except S.AnnexTplError as e:
        db.rollback()
        _fail(e)
    t = _template(db, template_id)
    log_action(db, user, "annex_tpl_save", "annex_template", t.id,
               f"{_label(db, t)}: версия v{v.version}" + (" (база принята)" if payload.adopt_base else ""))
    if t.scope == "base":
        behind_n = len(S.customs_behind(db, t.id))
        if behind_n:
            from app.notify import legal as legal_notify
            legal_notify.base_changed(db, _label(db, t), v.version, behind_n, user)
            db.commit()
    return _version(v)


@router.post("/{template_id}/restore", status_code=201)
def restore(template_id: int, payload: RestoreIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    try:
        v = S.restore(db, template_id, payload.version, user)
        db.commit()
    except S.AnnexTplError as e:
        db.rollback()
        _fail(e)
    t = _template(db, template_id)
    log_action(db, user, "annex_tpl_restore", "annex_template", t.id,
               f"{_label(db, t)}: v{payload.version} → новая версия v{v.version}")
    return _version(v)


@router.post("/{template_id}/keep-own", status_code=201)
def keep_own(template_id: int, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """«Оставить свой»: принять новую версию базы без изменения текста — появляется версия без правок."""
    try:
        v = S.keep_own(db, template_id, user)
        db.commit()
    except S.AnnexTplError as e:
        db.rollback()
        _fail(e)
    t = _template(db, template_id)
    log_action(db, user, "annex_tpl_keep", "annex_template", t.id, f"{_label(db, t)}: принята база v{v.base_version}")
    return _version(v)
