# -*- coding: utf-8 -*-
"""«Документы для 1С» (владелец 05.11.2026): очередь бухгалтерии и карточка комплекта. Право `onec_desk`: просмотр — видеть,
правка — вносить ответ 1С, возвращать, прикладывать файлы. Видит все пакеты (решение 05.11.2026). «Исправлено» нажимает
аккаунт — это ручка мастер-сделки (`/master-deals/{code}/upd/{n}/onec-fixed`), с её областью видимости."""
from datetime import date, datetime, timezone
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, constr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.models import User
from app.onec_desk import files as OF
from app.onec_desk import names as NM
from app.onec_desk import queue as Q
from app.onec_desk import service as SV
from app.permissions import require_permission

router = APIRouter()
VIEW = require_permission("onec_desk", "view")
EDIT = require_permission("onec_desk", "edit")


def _kit(db: Session, kit_id: int, lock: bool = False):
    """Комплект и его пакет; на запись — пакет заблокирован (как у мастер-сделки: два бухгалтера не двинут его дважды)."""
    from app.master_deal.models import MasterDeal, MasterDealUpd
    k = db.get(MasterDealUpd, kit_id)
    if k is None:
        raise HTTPException(404, "Комплект не найден")
    q = db.query(MasterDeal).filter(MasterDeal.id == k.master_deal_id)
    m = (q.with_for_update() if lock else q).one()
    if lock:
        db.refresh(k)
    return m, k


def _err(e: SV.DeskError):
    raise HTTPException(e.status, e.message)


def _done(db: Session, user, m, k, action: str, details: str) -> dict:
    db.commit()
    log_action(db, user, action, "master_deal", m.id, f"{m.code}: УПД № {k.upd_no} — {details}")
    return Q.card(db, k)


@router.get("/queue")
def desk_queue(tab: str = "wait", db: Session = Depends(get_db), user: User = Depends(VIEW)):
    if tab not in Q.TABS:
        raise HTTPException(400, "Вкладка: " + " / ".join(Q.TABS))
    return {"rows": Q.queue(db, tab), "counts": Q.counts(db)}


@router.get("/kit/{kit_id}")
def desk_kit(kit_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    _, k = _kit(db, kit_id)
    return Q.card(db, k)


class EnterIn(BaseModel):
    invoice_no: Optional[str] = None
    invoice_date: Optional[date] = None
    upd_no: Optional[str] = None
    upd_date: Optional[date] = None
    net: Optional[float] = None
    vat: Optional[float] = None
    gross: Optional[float] = None
    comment: Optional[str] = None


@router.put("/kit/{kit_id}")
def desk_enter(kit_id: int, payload: EnterIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Внести ответ 1С. Внесены все комплекты пакета — он уходит в «выставление», по счёту рождается операция."""
    m, k = _kit(db, kit_id, lock=True)
    try:
        out = SV.enter(db, m, k, payload.model_dump(), user)
    except SV.DeskError as e:
        db.rollback()
        _err(e)
    what = (f"{'правка' if out['again'] else 'внесено'}: счёт № {k.onec_invoice_no} от {k.onec_invoice_date:%d.%m.%Y}, "
            f"УПД № {k.onec_upd_no} от {k.onec_upd_date:%d.%m.%Y}" + (" — пакет в «выставление»" if out["moved"] else "")
            + (" — операция НЕ создана" if out["operation_error"] else ""))
    return {**_done(db, user, m, k, "onec_desk_enter", what), "operation_error": out["operation_error"]}


class TextIn(BaseModel):
    text: Optional[str] = None
    reason: Optional[str] = None


@router.post("/kit/{kit_id}/return")
def desk_return(kit_id: int, payload: TextIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Вернуть аккаунту: причина-подсказка и/или текст; заявка запоминается — при повторной отправке «было → стало»."""
    from app.onec_desk import board as BD
    m, k = _kit(db, kit_id, lock=True)
    req = BD.request_for(db, m, k)
    try:
        SV.give_back(db, m, k, payload.text, user, reason=payload.reason, snap=BD.snapshot(req) if req else None)
    except SV.DeskError as e:
        db.rollback()
        _err(e)
    why = ": ".join(x for x in ((payload.reason or "").strip(), (payload.text or "").strip()) if x)
    return _done(db, user, m, k, "onec_desk_return", f"возвращён аккаунту: {why}")


class RedoIn(BaseModel):
    reason: constr(max_length=500)


@router.post("/kit/{kit_id}/redo", dependencies=[Depends(VIEW)])
def desk_redo(kit_id: int, payload: RedoIn, db: Session = Depends(get_db),
              user: User = Depends(require_permission("master_deals_revert", "edit"))):
    """«Вернуть на переделку» внесённый комплект (владелец 12.11.2026, по праву «Мастер-сделки · возврат стадии»): ответ 1С
    снят, заявка снова в «Заявках на документы»; пакет дальше «ждём 1С» возвращается туда. Бухгалтеру и аккаунту — уведомление."""
    from app.master_deal import revert as RV
    from app.notify import closing as CN
    m, k = _kit(db, kit_id, lock=True)
    try:
        out = RV.redo_kit(db, m, k, user, payload.reason)
    except RV.RevertError as e:
        db.rollback()
        raise HTTPException(e.status, e.message)
    CN.reverted(db, m, out["was"], payload.reason.strip(), out, user)
    return _done(db, user, m, k, "onec_desk_redo", f"вернули на переделку: {payload.reason.strip()}")


@router.post("/kit/{kit_id}/comment")
def desk_comment(kit_id: int, payload: TextIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    m, k = _kit(db, kit_id)
    try:
        SV.comment(db, k, payload.text, user, m=m)
    except SV.DeskError as e:
        db.rollback()
        _err(e)
    return _done(db, user, m, k, "onec_desk_comment", f"комментарий: {payload.text.strip()}")


@router.post("/kit/{kit_id}/files/{slot}")
async def desk_file_upload(kit_id: int, slot: str, file: UploadFile = File(...), db: Session = Depends(get_db),
                           user: User = Depends(EDIT)):
    """PDF счёта, PDF УПД или XML УПД из 1С; повторная загрузка того же вида заменяет файл."""
    from app.files_safe import remove_upload
    content = await file.read()
    m, k = _kit(db, kit_id, lock=True)
    try:
        if slot == "xml" and k.onec_state == SV.DONE:   # догрузка во внесённую заявку — та самая УПД (09.11.2026)
            from app.onec_desk import board as BD
            SV.check_late_xml(m, k, content, BD.request_for(db, m, k))
        out = OF.save(db, m, k, user, slot=slot, filename=file.filename, content=content)
        db.commit()
    except SV.DeskError as e:
        db.rollback()
        _err(e)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Этот файл только что загрузили — обновите страницу")
    if out["old_path"]:
        remove_upload(out["old_path"])                  # прежний файл — только после коммита
    return _done(db, user, m, k, "onec_desk_file", f"{out['kind']} — «{out['filename']}»" + (" (замена)" if out["old_path"] else ""))


@router.post("/kit/{kit_id}/ds-scan")
async def desk_ds_scan(kit_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Скан подписанного ДС от бухгалтера (хендофф 09.11.2026, вкладка «Ждут сканов») — тем же путём и по тем же правилам, что в
    мастер-сделке: к выставленному бумажному ДС комплекта."""
    from app.files_safe import remove_upload
    content = await file.read()
    m, k = _kit(db, kit_id, lock=True)
    try:
        out = OF.save_ds_scan(db, m, k, user, filename=file.filename, content=content)
        db.commit()
    except SV.DeskError as e:
        db.rollback()
        _err(e)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "К этому ДС скан только что загрузили — обновите страницу")
    if out["old_path"]:
        remove_upload(out["old_path"])
    return _done(db, user, m, k, "onec_desk_file", f"скан подписанного ДС — «{out['filename']}»" + (" (замена)" if out["replaced"] else ""))


@router.get("/kit/{kit_id}/files/{file_id}")
def desk_file_download(kit_id: int, file_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    from app.files_safe import existing_upload_path
    m, k = _kit(db, kit_id)
    try:
        f = OF.get(db, m, k, file_id)
    except SV.DeskError as e:
        _err(e)
    return FileResponse(existing_upload_path(f.path), filename=NM.for_file(db, m, f), media_type=f.content_type or "application/octet-stream")


@router.delete("/kit/{kit_id}/files/{file_id}")
def desk_file_delete(kit_id: int, file_id: int, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    from app.files_safe import remove_upload
    m, k = _kit(db, kit_id, lock=True)
    try:
        name, path = OF.delete(db, m, k, file_id)
        db.commit()
    except SV.DeskError as e:
        db.rollback()
        _err(e)
    remove_upload(path)
    return _done(db, user, m, k, "onec_desk_file_delete", f"файл «{name}» убран")


@router.get("/kit/{kit_id}/ds")
def desk_ds(kit_id: int, fmt: str = "pdf", db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """ДС комплекта — посмотреть или скачать (владелец 05.11.2026). Та же сборка и те же проверки, что в реестре ДС
    (`annexes.annex_pdf/annex_docx`), но под правом «Документы для 1С»: бухгалтеру право «Приложения» не выдаётся.
    ДС, подписанный вне системы, — ровно загруженный файл; fmt=scan — скан подписанного бумажного ДС."""
    from app.files_safe import existing_upload_path
    from app.master_deal.models import MasterDealFile
    from app.routers import annexes as AX
    from app.sales import annex_external as X
    m, k = _kit(db, kit_id)
    if not k.annex_id:
        raise HTTPException(404, "У комплекта нет ДС")
    if fmt == "scan":
        f = (db.query(MasterDealFile).filter(MasterDealFile.annex_id == k.annex_id, MasterDealFile.kind == "скан ДС")
             .order_by(MasterDealFile.id.desc()).first())
        if f is None:
            raise HTTPException(404, "Скана подписанного ДС нет")
        return FileResponse(existing_upload_path(f.path), filename=NM.for_file(db, m, f))
    a = AX._annex(db, k.annex_id, user)
    if X.is_external(a):
        resp, ext = AX.external_file(a.id, db=db, user=user), None
    elif fmt == "docx":
        resp, ext = AX.annex_docx(a.id, db=db, user=user, with_basis=False), ".docx"
    elif fmt == "pdf":
        resp, ext = AX.annex_pdf(a.id, db=db, user=user, with_basis=False), ".pdf"
    else:
        raise HTTPException(400, "Формат: pdf, docx или scan")
    if ext is None:                                   # внешний ДС — расширение его файла
        import os
        ext = os.path.splitext(getattr(resp, "filename", "") or "")[1].lower() or ".pdf"
    # Имя — общим правилом документов (владелец 09.11.2026: «независимо с какого экрана качаю — формат един»)
    from app.doc_names import for_annex
    resp.headers["Content-Disposition"] = NM.disposition(for_annex(db, a, ext), f"{m.code}_DS{ext}")
    return resp


@router.get("/kit/{kit_id}/invoice-xml")
def desk_invoice_xml(kit_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """XML счёта на оплату для Диадока по формату ФНС (КНД 1110379, 12.11.2026): номер и дата из 1С, суммы — заявки."""
    from app.onec_desk import invoice_xml as IX
    m, k = _kit(db, kit_id)
    try:
        return IX.response(*IX.for_kit(db, m, k))
    except IX.InvoiceXmlError as e:
        raise HTTPException(e.status, e.message)


@router.get("/kit/{kit_id}/ds-doc")
def desk_ds_doc(kit_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """ДС для просмотра на экране (владелец 05.11.2026: «посмотреть — модалкой»): те же данные, что сайдкар печатает в PDF,
    вёрстка на фронте — тот же компонент `AnnexDocument`. PDF во фрейме не показать: CSP пускает фреймы только с песочницы."""
    from fastapi.encoders import jsonable_encoder
    from app.routers import annexes as AX
    from app.sales import annex_external as X
    _, k = _kit(db, kit_id)
    if not k.annex_id:
        raise HTTPException(404, "У комплекта нет ДС")
    a = AX._annex(db, k.annex_id, user)
    if X.is_external(a):
        raise HTTPException(409, "ДС подписан вне системы — его документ можно только скачать")
    return jsonable_encoder(AX._doc(db, a))


@router.get("/master/{code}.xlsx")
def desk_xlsx(code: str, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Пакет целиком — строки и комплекты, формат прототипа обмена с 1С."""
    from app.master_deal.models import MasterDeal
    from app.onec_desk import xlsx
    m = db.query(MasterDeal).filter(MasterDeal.code == code).first()
    if m is None:
        raise HTTPException(404, "Мастер-сделка не найдена")
    name = NM.file_name(db, m, "для 1С", ".xlsx")
    return StreamingResponse(BytesIO(xlsx.build(db, m)),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": NM.disposition(name, f"{m.code}.xlsx")})


# ── «Документы для бухгалтерии» по хендоффу (05.11.2026): вся страница одним ответом, черновик, разбор XML, «Внести» ──

@router.get("/board")
def desk_board(archive: bool = False, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Вся выдача экрана: сейчас, настройки бухгалтерии (срок закрытия, закрытый период, календарь), заявки.
    `archive` — только заявки пакетов в архиве, по кнопке «Загрузить архив» (владелец 12.11.2026)."""
    from app.onec_desk import board as BD
    return BD.board(db, archive=archive)


@router.patch("/kit/{kit_id}/draft")
def desk_draft(kit_id: int, payload: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Автосохранение формы (дебаунс на экране). В журнал не пишется — это набор текста, не действие."""
    m, k = _kit(db, kit_id, lock=True)
    try:
        at = SV.save_draft(db, m, k, payload, user)
    except SV.DeskError as e:
        db.rollback()
        _err(e)
    db.commit()
    return {"saved_at": at.isoformat()}


@router.post("/kit/{kit_id}/upd-xml")
def desk_upd_xml(kit_id: int, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Разобрать приложенный XML УПД: номер, дата, суммы, покупатель и договор — для формы и сверки со сделкой."""
    from app.onec_desk import xmlparse as XP
    m, k = _kit(db, kit_id)
    xml = OF.files_of(db, m, k).get("xml")
    if not xml:
        raise HTTPException(404, "XML УПД не приложен")
    from app.onec_desk import board as BD
    req = BD.request_for(db, m, k) or {"contract": {"no": None}, "basis": None}
    try:
        return XP.parse(OF.read(OF.get(db, m, k, xml["id"])), req["contract"]["no"], req["basis"])
    except SV.DeskError as e:
        _err(e)


@router.get("/check-number")
def desk_check_number(kind: str, no: str, exclude: Optional[int] = None, db: Session = Depends(get_db),
                      user: User = Depends(VIEW)):
    """Такой № счёта / УПД в этом году уже был — предупреждение на экране."""
    return SV.check_number(db, kind, no, exclude)


@router.post("/kit/{kit_id}/submit")
def desk_submit(kit_id: int, payload: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """«Внести и к следующему»: сервер повторяет проверки экрана и вносит ответ 1С (как PUT /kit/{id})."""
    from app.onec_desk import board as BD
    from app.onec_desk import close as CL
    m, k = _kit(db, kit_id, lock=True)
    req = BD.request_for(db, m, k)
    if req is None or req["status"] != "wait":
        raise HTTPException(409, "Заявка не ждёт бухгалтера — обновите страницу")
    try:
        out = SV.submit(db, m, k, payload, req, user, closed_until=CL.closed_until(db))
    except SV.DeskError as e:
        db.rollback()
        _err(e)
    what = (f"внесено: счёт № {k.onec_invoice_no} от {k.onec_invoice_date:%d.%m.%Y}, УПД № {k.onec_upd_no} от {k.onec_upd_date:%d.%m.%Y}"
            + (" — пакет в «выставление»" if out["moved"] else "") + (" — операция НЕ создана" if out["operation_error"] else ""))
    db.commit()
    log_action(db, user, "onec_desk_enter", "master_deal", m.id, f"{m.code}: УПД № {k.upd_no} — {what}")
    return {"ok": True, "moved": out["moved"], "operation_error": out["operation_error"], "warns": out["warns"]}


@router.post("/kit/{kit_id}/seen")
def desk_seen(kit_id: int, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Бухгалтер открыл заявку — снять «ответ» и «исправлено». Под правкой: метки — её, просмотр (Фин Менеджер) их не снимает."""
    _, k = _kit(db, kit_id)
    SV.mark_seen(db, k)
    db.commit()
    return {"ok": True}


class CloseIn(BaseModel):
    month: str
    close_at: datetime
    closed: bool = False


@router.put("/settings/close")
def desk_close(payload: CloseIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Срок закрытия месяца и отметка «закрыт» — меняет бухгалтер (по умолчанию 10-е число следующего месяца, 18:00)."""
    import re
    from app.onec_desk import close as CL
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", payload.month):
        raise HTTPException(400, "Месяц: ГГГГ-ММ")
    CL.save_close(db, payload.month, payload.close_at, payload.closed, user)
    db.commit()
    log_action(db, user, "onec_desk_close", "accounting_close", None,
               f"{payload.month}: срок {payload.close_at:%d.%m.%Y %H:%M}" + (", месяц закрыт" if payload.closed else ""))
    return CL.settings(db, datetime.now(timezone.utc))
