# -*- coding: utf-8 -*-
"""Шаблоны ДС: базовые именованные (с форматами договоров, которые они обслуживают) и шаблоны договора (спринт 1, 13–14.10.2026; с 27.10.2026
у договора их несколько, у каждого имя, один может быть основным). Роутер тонкий: вся логика — в `app/annex_tpl`. Права — секция
`annex_templates` (view / create / edit), кто правит — галочки в «Ролях». Выбор шаблона в ДС и «Сохранить как шаблон» из конструктора ДС —
по праву правки приложений (`annexes`, владелец 27.10.2026: «любой с правом правки»)."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.annex_tpl import document as D
from app.annex_tpl import service as S
from app.annex_tpl.check import check, literal_word_notes, numbering, zone_at
from app.annex_tpl.formats import KNOWN_FORMATS
from app.annex_tpl.models import AnnexTplFormat, AnnexTplTemplate, AnnexTplVersion
from app.annex_tpl.subs import listing
from app.audit import log_action
from app.database import get_db
from app.models import Contract, User
from app.permissions import require_permission
from app.sales import annex_print as AP

router = APIRouter()
VIEW = require_permission("annex_templates", "view")
CREATE = require_permission("annex_templates", "create")
EDIT = require_permission("annex_templates", "edit")
ANNEX_EDIT = require_permission("annexes", "edit")


class BlocksIn(BaseModel):
    blocks: List[dict]
    adopt_base: bool = False
    # Вид документа по договору, выбранный при пересохранении шаблона договора (владелец 31.10.2026: «при пересохранении —
    # выбор ДС/Приложение, если ещё не выбрано»). То же правило, что везде (`doc_kind.assign`): первичный выбор — тому,
    # кто сохраняет; выбранный — менять только администратору. Не прислан — вид не трогаем.
    annex_word: Optional[str] = None


class RestoreIn(BaseModel):
    version: int


class ForkIn(BaseModel):
    contract_id: int
    title: str
    source_id: Optional[int] = None       # копия этого шаблона (базового или шаблона договора); пусто — базовый формата договора
    main: bool = False
    annex_id: Optional[int] = None        # заявка юристу из ДС: черновик этого ДС переключается на новый шаблон
    # Бренд, к которому шаблон относится (реестр шаблонов, 31.10.2026). Пишется в память «договор + бренд →
    # шаблон» — ту же, по которой сборка подставит шаблон в следующий ДС бренда. Пусто — все бренды договора.
    brand_id: Optional[int] = None


class TitleIn(BaseModel):
    title: str


class MainIn(BaseModel):
    main: bool


class ChoiceIn(BaseModel):
    template_id: Optional[int] = None     # пусто — шаблон по умолчанию


class SaveAsIn(BaseModel):
    title: str
    main: bool = False


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
    return f"шаблон договора {t.contract_id} «{t.title}» (база «{base.title if base else '?'}»)"


def _row(db: Session, t: AnnexTplTemplate, with_blocks: bool = False) -> dict:
    cur = S.current(db, t.id)
    base = db.query(AnnexTplTemplate).filter_by(id=t.base_template_id).first() if t.base_template_id else None
    out = {"id": t.id, "scope": t.scope, "title": t.title or (base.title if base else None), "is_main": bool(t.is_main),
           "base_title": base.title if base else None, "base_template_id": t.base_template_id, "contract_id": t.contract_id,
           "formats": S.formats_of(db, t.id) if t.scope == "base" else [],
           "version": cur.version if cur else None, "base_version": cur.base_version if cur else None,
           "updated_at": cur.created_at if cur else None, "author": cur.author_name if cur else None,
           "base": S.base_state(db, t),
           # Пункты, где вид документа написан СЛОВОМ, а не `{вид_документа}`: тумблер договора
           # «Приложение / ДС» их не изменит. Число — для вкладки «Шаблоны»: что пересохранить.
           "literal_words": len(literal_word_notes(cur.blocks)) if cur else 0,
           "items": sum(1 for b in (cur.blocks or []) if not b.get("sys")) if cur else 0,
           "created_at": t.created_at}
    if with_blocks and t.contract_id:
        out["contract_annex_word"] = getattr(db.get(Contract, t.contract_id), "annex_word", None)
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
    # Чей шаблон — одним запросом на все договоры, а не по запросу на строку: вкладка
    # «Шаблоны» показывает их все разом (по образцу `/behind`).
    ids = {t.contract_id for t in rows if t.contract_id}
    contracts = {c.id: c for c in db.query(Contract).filter(Contract.id.in_(ids)).all()} if ids else {}
    tids = [t.id for t in rows]
    # Реестр шаблонов (хендофф 31.10.2026): каждое поле — одним запросом на все шаблоны, а не по строке.
    ds = {r.tid: (r.n, r.last) for r in db.execute(sa_text("""
        SELECT tpl_template_id AS tid, count(*) AS n, max(date) AS last FROM sales_annexes
         WHERE tpl_template_id = ANY(:t) GROUP BY 1"""), {"t": tids}).all()} if tids else {}
    # Бренд шаблона — память «договор + бренд → шаблон»: по ней сборка и подставит шаблон в ДС бренда.
    brands: dict = {}
    for r in (db.execute(sa_text("""
        SELECT m.template_id AS tid, b.name FROM annex_tpl_brand_memory m JOIN sales_brands b ON b.id = m.brand_id
         WHERE m.template_id = ANY(:t) ORDER BY b.name"""), {"t": tids}).all() if tids else []):
        brands.setdefault(r.tid, []).append(r.name)
    # Последний порядковый номер ДС по договору (владелец 31.10.2026) — НАИБОЛЬШИЙ из всех источников. У договора два
    # независимых счётчика: одиночные ДС нумеруются от «ДС с» договора и выданных (`sales.annex.next_no`), а мастер-сделка
    # хранит свой `start_no` и в договор его не пишет (`master_deal.package.set_start_no`). Возьми один — и реестр
    # разойдётся с панелью мастер-сделки (замер 31.10: у M-0001 № 44, у договора «ДС с» пусто). Источник — для подсказки.
    from app.master_deal.models import MasterDeal
    from app.sales.models import SalesAnnex
    master = {cid: n for cid, n in db.query(MasterDeal.contract_id, func.max(MasterDeal.start_no))
              .filter(MasterDeal.contract_id.in_(list(contracts)), MasterDeal.start_no.isnot(None))
              .group_by(MasterDeal.contract_id).all()} if contracts else {}
    issued = {cid: n for cid, n in db.query(SalesAnnex.contract_id, func.max(SalesAnnex.no))
              .filter(SalesAnnex.contract_id.in_(list(contracts)), SalesAnnex.no.isnot(None))
              .group_by(SalesAnnex.contract_id).all()} if contracts else {}
    last_no: dict = {}       # договор → (номер, источник); НЕ `last` — так в цикле ниже зовётся дата последнего ДС
    for cid, c in contracts.items():
        src = [("вне системы", c.annex_start_no or 0), ("в системе", issued.get(cid) or 0),
               ("в мастер-сделке", master.get(cid) or 0)]
        name, n = max(src, key=lambda x: x[1])
        last_no[cid] = (n, name if n else None)
    uids = {t.created_by for t in rows if t.created_by}
    names = {u.id: u.name for u in db.query(User).filter(User.id.in_(uids)).all()} if uids else {}
    items = []
    for t in rows:
        r = _row(db, t)
        n, last = ds.get(t.id, (0, None))
        r.update(ds_count=n, ds_last_at=last, brands=brands.get(t.id, []),
                 created_by_name=names.get(t.created_by), contract=None, entity=None)
        if t.contract_id:
            c = contracts.get(t.contract_id)
            cp = getattr(c, "counterparty", None)
            ln, src = last_no.get(t.contract_id, (None, None))
            r["contract"] = {"id": t.contract_id, "no": getattr(c, "contract_number", None),
                             "annex_word": getattr(c, "annex_word", None), "last_no": ln, "last_no_source": src}
            # Юрлицо — из реестра контрагентов; у непривязанной исторической строки договора — его текст.
            r["entity"] = {"id": cp.id, "name": cp.name, "inn": cp.inn} if cp else                 {"id": None, "name": getattr(c, "counterparty_name", None), "inn": getattr(c, "inn", None)}
            r["contract_number"] = getattr(c, "contract_number", None)
            r["format"] = getattr(c, "cooperation_format", None)
        items.append(r)
    return {"items": items}


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


def _contract(db: Session, contract_id: int) -> Contract:
    c = db.query(Contract).filter_by(id=contract_id).first()
    if not c:
        raise HTTPException(404, "Договор не найден")
    return c


@router.get("/for-contract/{contract_id}")
def for_contract(contract_id: int, template_id: Optional[int] = None, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Шаблоны договора: его именованные (основной первым) и базовый формата. Открыт `template_id`, иначе тот, что подставляется по
    умолчанию (основной, иначе базовый формата); шаблона нет вовсе — причина."""
    c = _contract(db, contract_id)
    r = S.resolve_for_contract(db, c)
    t = r["template"]
    if template_id is not None:
        t = next((x for x in S.choices(db, c) if x.id == template_id), None)
        if t is None:
            raise HTTPException(400, "Этот шаблон не относится к договору")
    return {"source": t.scope if t else "none", "reason": r["reason"], "format": c.cooperation_format,
            "templates": [_row(db, x) for x in S.choices(db, c)],
            "template": _row(db, t, with_blocks=True) if t else None,
            "base_changes": S.base_changes(db, t) if t and t.scope == "custom" else []}


@router.post("/custom", status_code=201)
def fork(payload: ForkIn, db: Session = Depends(get_db), user: User = Depends(CREATE)):
    """Новый именованный шаблон договора — копия базового формата или указанного шаблона."""
    c = _contract(db, payload.contract_id)
    if payload.brand_id is not None and payload.brand_id not in {b["id"] for b in _brands_of(db, c)}:
        raise HTTPException(400, "Этот бренд не относится к договору — выберите бренд из списка или «все бренды»")
    try:
        v = S.fork_custom(db, c, user, title=payload.title, source_id=payload.source_id, main=payload.main)
        if payload.brand_id is not None:
            S.remember(db, c.id, [payload.brand_id], v.template_id, getattr(user, "id", None))
        if payload.annex_id is not None:
            a = AP.annex_of(db, payload.annex_id, user)
            if a.contract_id != c.id:
                raise S.AnnexTplError(400, "Приложение не по этому договору")
            a.tpl_template_id = v.template_id
        db.commit()
    except S.AnnexTplError as e:
        db.rollback()
        _fail(e)
    t = _template(db, v.template_id)
    log_action(db, user, "annex_tpl_fork", "annex_template", t.id,
               f"договор {c.contract_number or c.id}: {_label(db, t)}, база v{v.base_version}" + (" · основной" if t.is_main else ""))
    return _row(db, t, with_blocks=True)


@router.put("/{template_id}/title")
def set_title(template_id: int, payload: TitleIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    was = _template(db, template_id).title
    try:
        t = S.rename(db, template_id, payload.title)
        db.commit()
    except S.AnnexTplError as e:
        db.rollback()
        _fail(e)
    log_action(db, user, "annex_tpl_rename", "annex_template", t.id, f"договор {t.contract_id}: «{was}» → «{t.title}»")
    return _row(db, t)


@router.put("/{template_id}/main")
def set_main(template_id: int, payload: MainIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Основной шаблон договора — подставляется в новый ДС, если для его брендов шаблон ещё не выбирали."""
    try:
        t = S.set_main(db, template_id, payload.main)
        db.commit()
    except S.AnnexTplError as e:
        db.rollback()
        _fail(e)
    log_action(db, user, "annex_tpl_main", "annex_template", t.id,
               f"{_label(db, t)}: " + ("основной" if t.is_main else "больше не основной"))
    return _row(db, t)


# ── шаблон в ДС: выбор на сборке и «Сохранить как шаблон» из конструктора (владелец 27.10.2026) ─────────────────────────────

def _annex_contract(db: Session, annex_id: int, user):
    a = AP.annex_of(db, annex_id, user)
    return a, AP.contract_of(db, a.contract_id)


@router.put("/annex/{annex_id}/choice")
def choose(annex_id: int, payload: ChoiceIn, db: Session = Depends(get_db), user: User = Depends(ANNEX_EDIT)):
    """Выбрать шаблон черновика ДС (пусто — по умолчанию). Подтверждённый собран и заморожен — его пересоздают, а не перевыбирают."""
    a, c = _annex_contract(db, annex_id, user)
    if a.no is not None:
        raise HTTPException(409, "Приложение подтверждено — шаблон выбирают до подтверждения")
    try:
        if payload.template_id is not None:
            S.resolve_for_contract(db, c, chosen_id=payload.template_id)      # шаблон должен относиться к договору
    except S.AnnexTplError as e:
        _fail(e)
    a.tpl_template_id = payload.template_id
    db.commit()
    t = _template(db, payload.template_id) if payload.template_id else None
    log_action(db, user, "annex_tpl_choice", "contract", c.id,
               f"ДС #{a.id}: " + (f"шаблон «{t.title}»" if t else "шаблон по умолчанию"))
    return D.choice(db, c, a)


@router.post("/annex/{annex_id}/save-as", status_code=201)
def save_as(annex_id: int, payload: SaveAsIn, db: Session = Depends(get_db), user: User = Depends(ANNEX_EDIT)):
    """Сохранить документ ДС как новый именованный шаблон договора: пункты — с текстом, который на экране (правки аккаунта и унаследованные,
    с подстановками), суммы и даты не запекаются. Черновик сразу переключается на новый шаблон."""
    a, c = _annex_contract(db, annex_id, user)
    version = (D.version_row(db, a.template_version_id) if D.is_frozen(a) else D.resolve(db, c, a)[0])
    state = D.model_of(db, a, c, AP.annex_deals(db, a.id))
    if version is None or not state["model"]:
        raise HTTPException(409, state["reason"] or "У приложения нет документа по шаблону — сохранять нечего")
    try:
        blocks = S.blocks_from_model(version.blocks, state["model"]["blocks"])
        v = S.fork_custom(db, c, user, title=payload.title, source_id=version.template_id, blocks=blocks, main=payload.main)
        if a.no is None:
            a.tpl_template_id = v.template_id
        db.commit()
    except S.AnnexTplError as e:
        db.rollback()
        _fail(e)
    t = _template(db, v.template_id)
    log_action(db, user, "annex_tpl_save_as", "annex_template", t.id,
               f"договор {c.contract_number or c.id}: из ДС #{a.id} — {_label(db, t)}" + (" · основной" if t.is_main else ""))
    return {"template": _row(db, t), "choice": D.choice(db, c, a) if a.no is None else None}


@router.get("/behind")
def behind(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Договоры, у которых кастомный шаблон ДС отстал от базового: юристу — решить «оставить свой» или «перенять базу»."""
    rows = S.customs_behind(db)
    contracts = {c.id: c for c in db.query(Contract).filter(Contract.id.in_({r["contract_id"] for r in rows})).all()} if rows else {}
    return [{**r, "contract_number": getattr(contracts.get(r["contract_id"]), "contract_number", None),
             "counterparty": getattr(contracts.get(r["contract_id"]), "counterparty_name", None),
             "format": getattr(contracts.get(r["contract_id"]), "cooperation_format", None)} for r in rows]


@router.get("/brands/{contract_id}")
def contract_brands(contract_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Бренды, к которым можно отнести шаблон договора: бренды сделок его плательщика и уже
    записанные в память «договор + бренд → шаблон». Плательщик — как у сборки ДС:
    `payer_counterparty_id`, иначе `counterparty_id`."""
    return _brands_of(db, _contract(db, contract_id))


def _brands_of(db: Session, c) -> list:
    """Один список на окно «Новый шаблон» и на проверку при создании: иначе сервер принял бы бренд,
    которого окно не предлагает (ревью 31.10.2026: чужой id доходил до внешнего ключа и давал 500)."""
    rows = db.execute(sa_text("""
        SELECT DISTINCT b.id, b.name FROM sales_brands b
         WHERE b.id IN (SELECT d.brand_id FROM sales_deals d
                         WHERE coalesce(d.payer_counterparty_id, d.counterparty_id) = :cp AND d.brand_id IS NOT NULL)
            OR b.id IN (SELECT brand_id FROM annex_tpl_brand_memory WHERE contract_id = :k)
         ORDER BY b.name"""), {"cp": c.counterparty_id, "k": c.id}).all()
    return [{"id": r.id, "name": r.name} for r in rows]


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
    t0 = _template(db, template_id)
    try:
        # Вид — ДО версии: запрет должен сработать раньше, чем что-то запишется. Версия не сохранилась (например,
        # «Изменений нет») — откатывается и вид: одно действие, одна транзакция.
        if payload.annex_word is not None and t0.scope == "custom" and t0.contract_id:
            from app.annex_tpl import doc_kind as DK
            try:
                DK.assign(_contract(db, t0.contract_id), payload.annex_word, user)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))
        v = S.save_version(db, template_id, payload.blocks, user, payload.adopt_base)
        db.commit()
    except S.AnnexTplError as e:
        db.rollback()
        _fail(e)
    except HTTPException:
        db.rollback()
        raise
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
