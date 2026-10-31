# -*- coding: utf-8 -*-
"""Мастер-сделки (владелец 15.10.2026): развилка «Отправить в ДО», конструктор закрытия, реестр, статусы, выставление, сканы.
Здесь только ручки: разбор запроса, область видимости, журнал. Логика — пакет `app/master_deal` (scope, registry, view, files,
status, issue, deal_stages, …). Пишущие ручки берут пакет через `_master_rw`: все сделки пакета в области пользователя и строка
пакета заблокирована до коммита (аудит 20.10: иначе запись проходила, а ответ был 403; две параллельные отметки шли обе)."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, constr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.master_deal import deal_stages as DST
from app.master_deal import files as FL
from app.master_deal import registry as RG
from app.master_deal import scope as SC
from app.master_deal import service as MS
from app.master_deal import status as MST
from app.master_deal import to_annex as TA
from app.master_deal import view as VW
from app.notify import closing as CN
from app.models import User
from app.permissions import require_permission
from app.routers.final_recon import _deal

router = APIRouter()

# Своё право с 19.10.2026 (`master_deals`: нет / просмотр / редактирование) — реестр в «Финансах» и карточка пакета.
# Область видимости — от реестра сделок: «свои» видят пакеты, где есть их сделка.
MD_VIEW = require_permission("master_deals", "view")
MD_EDIT = require_permission("master_deals", "edit")


# ── пакет и область ───────────────────────────────────────────────────────────────────────────────

def _master(db: Session, code: str, user, *, lock: bool = False):
    from app.master_deal.models import MasterDeal
    q = db.query(MasterDeal).filter(MasterDeal.code == code)
    m = (q.with_for_update() if lock else q).first()
    if not m:
        raise HTTPException(404, "Мастер-сделка не найдена")
    if not SC.in_scope(db, m, SC.own_reps(db, user)):
        raise HTTPException(403, "Мастер-сделка вне вашей зоны видимости")
    return m


def _scope_all(db: Session, m, user) -> list:
    """Сделки пакета; каждая — в области видимости пользователя (как карточка сделки)."""
    from app.master_deal.models import MasterDealItem
    ids = [i.deal_id for i in db.query(MasterDealItem).filter(MasterDealItem.master_deal_id == m.id).order_by(MasterDealItem.id)]
    return [_deal(db, i, user) for i in ids]


def _master_ro(db: Session, code: str, user):
    """Пакет для чтения его документов (архив, сканы): та же область, что у карточки — ВСЕ сделки пакета свои (ревью 21.10.2026).
    Одной своей сделки мало: в архиве и сканах лежат ДС и суммы чужих сделок того же пакета."""
    m = _master(db, code, user)
    _scope_all(db, m, user)
    return m


def _master_rw(db: Session, code: str, user):
    """Пакет для записи: заблокирован и ВСЕ его сделки в области пользователя — проверка до записи, не после."""
    m = _master(db, code, user, lock=True)
    _scope_all(db, m, user)
    return m


def _view(db: Session, m, user) -> dict:
    return VW.card(db, m, user, _scope_all(db, m, user))


def _err(e: MS.MasterError):
    raise HTTPException(e.status, e.message)


def _done(db: Session, user, m, action: str, details: str, **extra) -> dict:
    db.commit()
    log_action(db, user, action, "master_deal", m.id, f"{m.code}: {details}")
    return {**extra, **_view(db, m, user)} if extra else _view(db, m, user)


# ── развилка «Отправить в ДО» ─────────────────────────────────────────────────────────────────────

class SendIn(BaseModel):
    target: str                       # new | join | existing
    master_id: Optional[int] = None
    with_deals: List[int] = []        # доп. сделки того же договора и месяца — в тот же пакет сразу


@router.get("/deal/{deal_id}/fork")
def deal_fork(deal_id: int, db: Session = Depends(get_db), user: User = Depends(MD_VIEW)):
    """Что показать в модалке «Отправить в ДО»: уже в пакете / открытые пакеты того же договора и месяца / почему нельзя."""
    from app.master_deal import scope as SC
    return MS.fork(db, _deal(db, deal_id, user), SC.own_reps(db, user))


def _lock_deals(db: Session, ids) -> None:
    """Сделки «Отправить в ДО» — под замком строк, по возрастанию id (один порядок — без взаимной блокировки): второе нажатие
    из соседней вкладки ждёт первое и видит, что сделка уже в пакете (аудит 21.10.2026, D5)."""
    from app.sales.models import SalesDeal
    db.query(SalesDeal.id).filter(SalesDeal.id.in_(sorted(set(ids)))).order_by(SalesDeal.id).with_for_update().all()


@router.put("/deal/{deal_id}/send")
def deal_send(deal_id: int, payload: SendIn, db: Session = Depends(get_db), user: User = Depends(MD_EDIT)):
    from sqlalchemy.exc import IntegrityError
    d = _deal(db, deal_id, user)
    extra = [_deal(db, i, user) for i in dict.fromkeys(payload.with_deals) if i != deal_id]
    _lock_deals(db, [d.id] + [x.id for x in extra])
    try:
        out = MS.send_with(db, d, extra, user, target=payload.target, master_id=payload.master_id)
    except MS.MasterError as e:
        db.rollback()
        raise HTTPException(e.status, e.message)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Сделку уже отправили в ДО — обновите экран")
    db.commit()
    where = {"new": "своё ДС", "join": "в мастер-сделку"}.get(payload.target, "мастер-сделка")
    log_action(db, user, "deal_send_to_do", "sales_deal", d.id,
               f"{d.code}: «Отправить в ДО» — {where} {out['master']['code']}" + (f", вместе с {', '.join(out['added'])}" if out.get("added") else "")
               + (f", стадия «{out['moved_to']}»" if out["moved_to"] else ""))
    return out


# ── реестр и карточка ─────────────────────────────────────────────────────────────────────────────

@router.get("/registry/list")
def master_registry(db: Session = Depends(get_db), user: User = Depends(MD_VIEW)):
    return {"rows": RG.rows(db, user), "statuses": list(MST.STATUSES), "hidden": list(MST.HIDDEN)}


@router.get("/{code}")
def master_view(code: str, db: Session = Depends(get_db), user: User = Depends(MD_VIEW)):
    """Карточка пакета: шапка и сделки, раскладка, номера ДС договора, документы, выставление, «что нужно сейчас»."""
    return _view(db, _master(db, code, user), user)


@router.get("/{code}/efficiency")
def master_efficiency(code: str, db: Session = Depends(get_db),
                      user: User = Depends(require_permission("master_deals_finance", "view"))):
    """Эффективность пакета отдельно — для тех, у кого есть право «Эффективность мастер-сделок»."""
    from app.master_deal import efficiency as EF
    from app.master_deal import scope as SC
    m = _master(db, code, user)
    deals = _scope_all(db, m, user)
    eff = EF.of_master(db, deals)
    return EF.with_full(db, deals, eff) if SC.can_special(db, user) else eff


# ── статус ────────────────────────────────────────────────────────────────────────────────────────

class StatusIn(BaseModel):
    to: str


@router.post("/{code}/status")
def master_status(code: str, payload: StatusIn, db: Session = Depends(get_db), user: User = Depends(MD_EDIT)):
    """Ручной шаг статуса: вперёд — у кого есть редактирование, назад на шаг — мастер или админ."""
    m = _master_rw(db, code, user)
    was = m.status
    try:
        MST.move(db, m, payload.to, user)
    except MST.StatusError as e:
        db.rollback()
        raise HTTPException(e.status, e.message)
    moved = DST.journal_tail(DST.follow(db, m, was, user), m.status)
    CN.status_changed(db, m, was, user)
    return _done(db, user, m, "master_deal_status", f"статус «{was}» → «{MST.label(db, m)}»{moved}")


# ── раскладка и ДС ────────────────────────────────────────────────────────────────────────────────

class SettingsIn(BaseModel):
    addons_separate: Optional[bool] = None
    bonus_addons: Optional[str] = None          # zero | hide
    ds_by_brand: Optional[bool] = None
    ds_by_service: Optional[bool] = None
    upd_by_brand: Optional[bool] = None
    upd_by_service: Optional[bool] = None
    moved: Optional[List[str]] = None            # id строк-допов, перенесённых в основной ДС


class StartNoIn(BaseModel):
    no: int
    # Вид документа по договору — «приложение» | «дс» (владелец 31.10.2026). Выбирается здесь, при первой сборке, вместе
    # со стартовым номером, и фиксируется в договоре; дальше менять — только администратор (`doc_kind.assign`).
    # Не прислан — вид не трогаем.
    annex_word: Optional[str] = None


class AddDealIn(BaseModel):
    deal_id: int


class BasisIn(BaseModel):
    text: Optional[str] = None       # пусто — вернуть текст по умолчанию


@router.post("/{code}/preview")
def master_preview(code: str, payload: SettingsIn, db: Session = Depends(get_db), user: User = Depends(MD_VIEW)):
    """Предпросмотр черновика раскладки — тот же серверный расчёт, ничего не пишет."""
    from app.master_deal import layout as LY
    m = _master(db, code, user)
    _scope_all(db, m, user)
    return LY.layout(db, m, payload.dict(exclude_none=True))


@router.put("/{code}/settings")
def master_settings(code: str, payload: SettingsIn, db: Session = Depends(get_db), user: User = Depends(MD_EDIT)):
    from app.master_deal import package as PK
    m = _master_rw(db, code, user)
    try:
        PK.save_settings(db, m, payload.dict(exclude_none=True), user)
    except MS.MasterError as e:
        _err(e)
    return _done(db, user, m, "master_deal_settings",
                 "раскладка сохранена — " + ", ".join(f"{k}={v}" for k, v in payload.dict(exclude_none=True).items()))


@router.get("/{code}/start-no/check")
def master_start_no_check(code: str, no: int, db: Session = Depends(get_db), user: User = Depends(MD_VIEW)):
    from app.master_deal import package as PK
    return PK.check_start_no(db, _master(db, code, user), no)


@router.put("/{code}/start-no")
def master_start_no(code: str, payload: StartNoIn, db: Session = Depends(get_db), user: User = Depends(MD_EDIT)):
    from app.master_deal import package as PK
    m = _master_rw(db, code, user)
    try:
        PK.set_start_no(db, m, payload.no, user)
    except MS.MasterError as e:
        _err(e)
    note = f"последний ДС по договору — № {payload.no}"
    if payload.annex_word is not None:
        from app.annex_tpl import doc_kind as DK
        from app.models import Contract
        c = db.get(Contract, m.contract_id)
        try:
            word = DK.assign(c, payload.annex_word, user)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))
        note += f"; вид документа — {DK.forms(word)['ui'] if word else 'не выбран'}"
    return _done(db, user, m, "master_deal_start_no", note)


@router.post("/{code}/deals")
def master_add_deal(code: str, payload: AddDealIn, db: Session = Depends(get_db), user: User = Depends(MD_EDIT)):
    from app.master_deal import package as PK
    m = _master_rw(db, code, user)
    d = _deal(db, payload.deal_id, user)
    try:
        PK.add_deal(db, m, d, user)
    except MS.MasterError as e:
        _err(e)
    return _done(db, user, m, "master_deal_deals", f"+ {d.code}")


@router.delete("/{code}/deals/{deal_id}")
def master_remove_deal(code: str, deal_id: int, db: Session = Depends(get_db), user: User = Depends(MD_EDIT)):
    from app.master_deal import package as PK
    m = _master_rw(db, code, user)
    d = _deal(db, deal_id, user)
    try:
        PK.remove_deal(db, m, deal_id)
    except MS.MasterError as e:
        _err(e)
    return _done(db, user, m, "master_deal_deals", f"× {d.code}")


@router.post("/{code}/to-annex")
def master_to_annex(code: str, db: Session = Depends(get_db), user: User = Depends(MD_EDIT)):
    """«В конструктор ДС →»: черновики ДС пакета из сохранённой раскладки (строки — снимком), распределение по сделкам, комплекты УПД."""
    m = _master_rw(db, code, user)
    try:
        made = TA.create(db, m, user)
    except MS.MasterError as e:
        db.rollback()
        _err(e)
    CN.ds_created(db, m, [x["number"] for x in made], user)
    return _done(db, user, m, "master_deal_to_annex", "ДС пакета созданы — " + ", ".join(x["number"] for x in made), annexes=made)


@router.post("/{code}/revert")
def master_revert(code: str, db: Session = Depends(get_db), user: User = Depends(MD_EDIT)):
    """«Вернуть в раскладку»: удалить черновики ДС пакета — пока ни один не подтверждён и по ним нет заявок юристу."""
    m = _master_rw(db, code, user)
    try:
        n = TA.revert(db, m)
    except MS.MasterError as e:
        db.rollback()
        _err(e)
    return _done(db, user, m, "master_deal_revert", f"возврат в раскладку, удалено черновиков ДС: {n}")


@router.post("/{code}/confirm-ds")
def master_confirm_ds(code: str, db: Session = Depends(get_db), user: User = Depends(MD_EDIT)):
    """Подтвердить ДС пакета одним действием (основной, затем допы) тем же путём, что кнопка в конструкторе ДС, но одной транзакцией:
    отказ по любому — ни один номер не занят."""
    from app.routers import annexes as AX
    from app.sales.models import SalesAnnex
    m = _master_rw(db, code, user)
    drafts = (db.query(SalesAnnex).filter(SalesAnnex.master_deal_id == m.id, SalesAnnex.no.is_(None))
              .order_by(SalesAnnex.sub_no.isnot(None), SalesAnnex.id).all())
    if not drafts:
        raise HTTPException(409, "Неподтверждённых ДС в пакете нет")
    was = m.status
    # Атомарно (владелец 21.10.2026: до релиза): все ДС пакета подтверждаются в ОДНОЙ транзакции — основной, затем допы (номер допов
    # берётся от основного, записанного `flush` в этой же транзакции). Отказ по любому — откат всего: ни один номер не занят.
    def work():
        out = []
        for a in drafts:
            AX.confirm_one(db, a, AX.ConfirmIn(), user)
            db.flush()                                 # сессии без autoflush: номер основного ДС должен быть виден ДС допов
            out.append(a)
        if m.status == MST.AGREE:                      # все ДС пакета подтверждены — ждём 1С
            m.status, m.updated_at = MST.WAIT_1C, datetime.utcnow()
        return out
    try:
        done = AX.commit_confirm(db, None, drafts[0].id, work)
    except HTTPException:
        db.rollback()                                  # отказ проверки на любом ДС — откат и уже сделанных в этой транзакции
        raise
    for a in done:
        db.refresh(a)
        log_action(db, user, "annex_confirm", "contract", a.contract_id, a.number)
    if m.status == MST.WAIT_1C and was == MST.AGREE:   # «ждём 1С» — только когда статус и правда сменился
        CN.status_changed(db, m, was, user)
    done = [a.number for a in done]
    return _done(db, user, m, "master_deal_confirm_ds", "ДС подтверждены — " + ", ".join(map(str, done)), confirmed=done)


@router.put("/{code}/upd/{upd_no}/basis")
def master_upd_basis(code: str, upd_no: int, payload: BasisIn, db: Session = Depends(get_db), user: User = Depends(MD_EDIT)):
    """Основание для закрытия по одной УПД (одна УПД = одно основание); до отправки в 1С."""
    m = _master_rw(db, code, user)
    try:
        TA.set_basis(db, m, upd_no, payload.text)
    except MS.MasterError as e:
        _err(e)
    return _done(db, user, m, "master_deal_upd_basis",
                 f"основание УПД № {upd_no} — " + ((payload.text or "").strip()[:200] or "по умолчанию"))


# ── выставление: ЭДО / бумага, сканы ──────────────────────────────────────────────────────────────

class SentIn(BaseModel):
    track_no: Optional[constr(max_length=64)] = None      # колонка varchar(64): длиннее — 422, а не 500 (аудит 20.10)


def _issue_act(db: Session, code: str, user, fn, what: str):
    m = _master_rw(db, code, user)
    was = m.status
    try:
        fn(m)
    except MST.StatusError as e:
        db.rollback()
        raise HTTPException(e.status, e.message)
    moved = DST.journal_tail(DST.follow(db, m, was, user), m.status)   # «Отправлено» уводит пакет в «ждём оплату» — сделки в «Оплату»
    return _done(db, user, m, "master_deal_issue", f"{what}{moved}")


@router.post("/{code}/issue/signed")
def master_issue_signed(code: str, db: Session = Depends(get_db), user: User = Depends(MD_EDIT)):
    """Бумага: распечатано и подписано у нас."""
    from app.master_deal import issue as IS
    return _issue_act(db, code, user, lambda m: IS.signed_by_us(db, m, user), "подписано у нас")


@router.post("/{code}/issue/sent")
def master_issue_sent(code: str, payload: SentIn, db: Session = Depends(get_db), user: User = Depends(MD_EDIT)):
    """Отправлено клиенту → «ждём оплату». ЭДО — документы закрыты; бумага — ждём сканы."""
    from app.master_deal import issue as IS
    track = (payload.track_no or "").strip()
    return _issue_act(db, code, user, lambda m: IS.sent(db, m, user, track), "отправлено клиенту" + (f", трек {track}" if track else ""))


@router.post("/{code}/files")
async def master_file_upload(code: str, file: UploadFile = File(...), annex_id: Optional[int] = Form(None),
                             upd_no: Optional[int] = Form(None), db: Session = Depends(get_db), user: User = Depends(MD_EDIT)):
    """Скан подписанного документа — к ОДНОМУ ДС (annex_id) или ОДНОМУ УПД (upd_no); повторная загрузка заменяет скан."""
    from app.files_safe import remove_upload
    content = await file.read()
    m = _master_rw(db, code, user)
    try:
        out = FL.save_scan(db, m, user, filename=file.filename, content=content, annex_id=annex_id, upd_no=upd_no)
        db.commit()
    except MS.MasterError as e:
        db.rollback()
        _err(e)
    except IntegrityError:                              # параллельная загрузка к тому же документу
        db.rollback()
        raise HTTPException(409, "К этому документу скан только что загрузили — обновите страницу")
    if out["old_path"]:
        remove_upload(out["old_path"])                  # прежний файл — только после коммита
    return _done(db, user, m, "master_deal_file",
                 f"скан к «{out['target']['label']}» — «{out['filename']}»" + (" (замена)" if out["replaced"] else ""))


@router.get("/{code}/zip")
def master_zip(code: str, db: Session = Depends(get_db), user: User = Depends(MD_VIEW)):
    """«Скачать всё · zip»: ДС пакета (.docx) и сканы; что не собралось — в «не вошло.txt»."""
    from io import BytesIO
    from urllib.parse import quote
    from fastapi.responses import StreamingResponse
    from app.master_deal import bundle
    name, data = bundle.build(db, _master_ro(db, code, user))
    return StreamingResponse(BytesIO(data), media_type="application/zip",
                             headers={"Content-Disposition": f"attachment; filename=\"{code}.zip\"; filename*=UTF-8''{quote(name)}"})


@router.get("/{code}/files/{file_id}")
def master_file_download(code: str, file_id: int, db: Session = Depends(get_db), user: User = Depends(MD_VIEW)):
    from fastapi.responses import FileResponse
    from app.files_safe import existing_upload_path
    try:
        f = FL.get(db, _master_ro(db, code, user), file_id)
    except MS.MasterError as e:
        _err(e)
    return FileResponse(existing_upload_path(f.path), filename=f.filename, media_type=FL.media_type(f.filename))


@router.delete("/{code}/files/{file_id}")
def master_file_delete(code: str, file_id: int, db: Session = Depends(get_db), user: User = Depends(MD_EDIT)):
    """Убрать скан. Без скана хоть одного документа бумажные документы снова открыты."""
    from app.files_safe import remove_upload
    m = _master_rw(db, code, user)
    try:
        name, path = FL.delete(db, m, file_id, user)
        db.commit()
    except MS.MasterError as e:
        db.rollback()
        _err(e)
    remove_upload(path)
    return _done(db, user, m, "master_deal_file_delete", f"скан «{name}» удалён")
