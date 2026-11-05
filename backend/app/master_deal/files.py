# -*- coding: utf-8 -*-
"""Сканы подписанных документов пакета: один файл — к одному ДС (annex_id) или одному УПД (upd_no), без архивов; повторная
загрузка к тому же документу заменяет скан (прежний файл с диска убирается). Файлы — в /app/uploads/master_files.
Ошибки — `MasterError` с кодом и текстом для человека; HTTP формирует роутер."""
import os
import re
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.master_deal import doc_sign as DS
from app.master_deal import issue as IS
from app.master_deal import status as MST
from app.master_deal.models import MasterDealFile
from app.master_deal.service import MasterError

ROOT, SUBDIR = "/app/uploads", "master_files"
MAX_BYTES = 20 * 1024 * 1024
MEDIA = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".tif": "image/tiff",
         ".tiff": "image/tiff"}


def media_type(filename: str) -> str:
    """Тип файла — по расширению, а не со слов клиента (аудит 20.10)."""
    return MEDIA.get(os.path.splitext(filename or "")[1].lower(), "application/octet-stream")


def check_upload_allowed(db: Session, doc) -> None:
    """Скан подписанного — к бумажному документу, который уже у клиента (выставлен) или подписан (замена скана). По документу,
    а не по статусу пакета: с 02.11.2026 у каждого документа своя подпись."""
    if getattr(doc, "sign_channel", None) != DS.PAPER:
        raise MasterError(409, "Скан прикладывают к бумажному документу, отправленному клиенту; ЭДО подпись принесёт само")
    if doc.sign_state not in (DS.SENT, DS.SIGNED):
        raise MasterError(409, "Скан подписанного — после отправки документа клиенту (отметка «выставлен»)")


def _target(db: Session, m, annex_id: Optional[int], upd_no: Optional[int]) -> dict:
    if (annex_id is None) == (upd_no is None):
        raise MasterError(400, "Выберите, к какому документу скан: один ДС или один УПД")
    target = {(x["annex_id"], x["upd_no"]): x for x in IS.required_scans(db, m)}.get((annex_id, upd_no))
    if target is None:
        raise MasterError(404, "Такого документа в пакете нет")
    return target


def scan_of(db: Session, m, annex_id: Optional[int], upd_no: Optional[int]) -> Optional[MasterDealFile]:
    """Скан документа — только видами сканов: рядом с ними с 05.11.2026 лежат PDF из 1С с тем же upd_no (`app/onec_desk/files.py`)."""
    q = db.query(MasterDealFile).filter(MasterDealFile.master_deal_id == m.id, MasterDealFile.kind.in_(IS.SCAN_KINDS))
    return q.filter((MasterDealFile.annex_id == annex_id) if annex_id is not None else (MasterDealFile.upd_no == upd_no)).first()


def save_scan(db: Session, m, user, *, filename: str, content: bytes, annex_id: Optional[int], upd_no: Optional[int]) -> dict:
    """Записать скан к документу; скан ушедшей клиенту бумаги — это и есть отметка «подписан». Возвращает
    {target, replaced, old_path} — прежний файл удаляет вызывающий ПОСЛЕ коммита (иначе при сбое коммита строка осталась бы без файла)."""
    if m.status == MST.ARCHIVE:          # как у удаления: скан закрытого пакета — доказательство подписи, не заменяется
        raise MasterError(409, "Пакет в архиве — сканы закрытого пакета не меняются")
    target = _target(db, m, annex_id, upd_no)
    doc = target["doc"]
    check_upload_allowed(db, doc)
    original = filename or "scan"
    if not IS.scan_ext_ok(original):
        raise MasterError(415, "Скан — pdf, jpg, png или tif: один файл — один документ, архивы не принимаются")
    if not content:
        raise MasterError(400, "Файл пустой")
    if len(content) > MAX_BYTES:
        raise MasterError(413, f"Файл больше {MAX_BYTES // 1024 // 1024} МБ")
    os.makedirs(os.path.join(ROOT, SUBDIR), exist_ok=True)
    safe = re.sub(r"[^\w.-]", "_", original)          # Python 3.11: обратная косая в выражении f-строки — синтаксическая ошибка
    rel = os.path.join(SUBDIR, f"{m.id}_{uuid.uuid4().hex[:8]}_{safe}")
    with open(os.path.join(ROOT, rel), "wb") as fh:
        fh.write(content)
    old = scan_of(db, m, annex_id, upd_no)
    old_path = old.path if old is not None else None
    if old is not None:
        db.delete(old)
        db.flush()
    db.add(MasterDealFile(master_deal_id=m.id, kind=target["kind"], annex_id=annex_id, upd_no=upd_no, filename=original, path=rel,
                          size=len(content), content_type=media_type(original), uploaded_by=getattr(user, "id", None)))
    db.flush()
    if doc.sign_state == DS.SENT:
        DS.mark(db, doc, DS.SIGNED, user)
    return {"target": target, "replaced": old is not None, "filename": original, "old_path": old_path, "path": rel}


def get(db: Session, m, file_id: int) -> MasterDealFile:
    f = db.get(MasterDealFile, file_id)
    if f is None or f.master_deal_id != m.id:
        raise MasterError(404, "Файл не найден")
    return f


def delete(db: Session, m, file_id: int, user) -> tuple:
    """Убрать скан. В архиве нельзя — пакет держится на сканах. Возвращает (имя, путь) — файл с диска убирает вызывающий после коммита."""
    f = get(db, m, file_id)
    if f.kind not in IS.SCAN_KINDS:
        raise MasterError(409, "Это файл из 1С, а не скан — он убирается в «Документах для 1С»")
    if m.status == MST.ARCHIVE:
        raise MasterError(409, "Пакет в архиве держится на подписанных документах — сначала верните его в «ждём сканы»")
    name, path = f.filename, f.path
    doc = next((x["doc"] for x in IS.required_scans(db, m) if (x["annex_id"], x["upd_no"]) == (f.annex_id, f.upd_no)), None)
    db.delete(f)
    db.flush()
    if doc is not None and doc.sign_state == DS.SIGNED and doc.sign_channel == DS.PAPER:
        DS.unsign(db, doc, user, reason="скан подписанного убран")        # бумага держит подпись только сканом
    return name, path
