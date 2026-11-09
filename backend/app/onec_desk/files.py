# -*- coding: utf-8 -*-
"""Файлы из 1С к комплекту: PDF счёта, PDF УПД и (необязательно) XML УПД для ЭДО. Лежат в `master_deal_files` рядом со
сканами, своими видами и с `upd_no` комплекта; сканы подписанного читаются только по видам «скан ДС» / «скан УПД».
Один файл каждого вида на комплект, новый заменяет прежний — прежний файл с диска убирает вызывающий ПОСЛЕ коммита."""
import os
import re
import uuid

from sqlalchemy.orm import Session

from app.master_deal import status as ST
from app.master_deal.models import MasterDealFile
from app.onec_desk.service import DONE, DeskError

ROOT, SUBDIR = "/app/uploads", "master_files"
MAX_BYTES = 20 * 1024 * 1024
SLOTS = {"invoice": ("счёт 1С", (".pdf",)), "upd": ("УПД 1С", (".pdf",)), "xml": ("УПД 1С xml", (".xml", ".zip"))}
KINDS = {kind: slot for slot, (kind, _) in SLOTS.items()}
MEDIA = {".pdf": "application/pdf", ".xml": "application/xml", ".zip": "application/zip"}   # .zip — архив ЭДО с УПД внутри


def _query(db: Session, m, k):
    return db.query(MasterDealFile).filter(MasterDealFile.master_deal_id == m.id, MasterDealFile.upd_no == k.upd_no,
                                           MasterDealFile.kind.in_(list(KINDS)))


def files_of(db: Session, m, k) -> dict:
    return {KINDS[f.kind]: {"id": f.id, "filename": f.filename, "size": f.size or 0,
                            "at": f.uploaded_at.isoformat(timespec="seconds") if f.uploaded_at else None}
            for f in _query(db, m, k).order_by(MasterDealFile.id)}


def save(db: Session, m, k, user, *, slot: str, filename: str, content: bytes) -> dict:
    if slot not in SLOTS:
        raise DeskError(400, "Файл: счёт, УПД или XML УПД")
    if m.status not in (ST.WAIT_1C, ST.ISSUE, ST.WAIT_PAY, ST.WAIT_SCANS):
        raise DeskError(409, "Файлы 1С прикладывают, когда пакет ждёт 1С или позже, до архива")
    kind, exts = SLOTS[slot]
    original = filename or f"{slot}{exts[0]}"
    ext = os.path.splitext(original)[1].lower()
    if ext not in exts:
        raise DeskError(415, f"{kind}: нужен файл {', '.join(exts)}")
    if not content:
        raise DeskError(400, "Файл пустой")
    if len(content) > MAX_BYTES:
        raise DeskError(413, f"Файл больше {MAX_BYTES // 1024 // 1024} МБ")
    os.makedirs(os.path.join(ROOT, SUBDIR), exist_ok=True)
    safe = re.sub(r"[^\w.-]", "_", original)
    rel = os.path.join(SUBDIR, f"{m.id}_1c_{uuid.uuid4().hex[:8]}_{safe}")
    with open(os.path.join(ROOT, rel), "wb") as fh:
        fh.write(content)
    old = _query(db, m, k).filter(MasterDealFile.kind == kind).first()
    old_path = old.path if old is not None else None
    if old is not None:
        db.delete(old)
        db.flush()
    f = MasterDealFile(master_deal_id=m.id, kind=kind, upd_no=k.upd_no, filename=original, path=rel, size=len(content),
                       content_type=MEDIA[ext], uploaded_by=getattr(user, "id", None))
    db.add(f)
    db.flush()
    return {"id": f.id, "filename": original, "old_path": old_path, "path": rel, "kind": kind}


def get(db: Session, m, k, file_id: int) -> MasterDealFile:
    f = _query(db, m, k).filter(MasterDealFile.id == file_id).first()
    if f is None:
        raise DeskError(404, "Файл не найден")
    return f


def delete(db: Session, m, k, file_id: int) -> tuple:
    if m.status == ST.ARCHIVE:
        raise DeskError(409, "Пакет в архиве — документы закрытого пакета не меняются")
    if k.onec_state == DONE:
        raise DeskError(409, "Заявка внесена — файл можно заменить, но не убрать")
    f = get(db, m, k, file_id)
    name, path = f.filename, f.path
    db.delete(f)
    db.flush()
    return name, path


def read(f: MasterDealFile) -> bytes:
    """Содержимое файла пакета с диска (для разбора XML УПД)."""
    from app.files_safe import existing_upload_path
    with open(existing_upload_path(f.path), "rb") as fh:
        return fh.read()
