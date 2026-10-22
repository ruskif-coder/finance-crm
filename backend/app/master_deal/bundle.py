# -*- coding: utf-8 -*-
"""«Скачать всё · zip» (хендофф реестра v2, 21.10.2026): готовые файлы пакета одним архивом — ДС (.docx, тот же документ, что
кнопка «ДС» конструктора) и приложенные сканы. Что собрать нельзя (заявка юристу открыта, не хватает реквизитов), в архив не
кладём, а называем в «не вошло.txt» — пустой молчащий архив хуже, чем список причин."""
import os
import zipfile
from io import BytesIO

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.master_deal import to_annex as TA

def _safe_name(s: str) -> str:
    bad = '\\/:*?"<>|\r\n\t'
    return "".join("_" if ch in bad else ch for ch in (s or "")).strip() or "файл"

def _annex_docx(db: Session, annex_id: int) -> tuple:
    """(имя, байты) ДС — теми же функциями, что ручка `/annexes/{id}/docx`; отказ — HTTPException с причиной."""
    from app.routers import annexes as AX
    from app.sales import annex_docx as docx_build
    a = AX._annex(db, annex_id)
    AX._assert_no_open_legal(db, a)
    doc = AX._doc(db, a)
    AX.assert_printable(doc)
    name = AX.file_name(no=a.no, doc_date=doc["date"], brand=doc.get("brand"),
                        payer=(doc.get("customer") or {}).get("name")).replace(".pdf", ".docx")
    return name, docx_build.build_docx(doc)

def build(db: Session, m) -> tuple:
    """(имя архива, байты). Пустой пакет (ДС ещё нет и сканов нет) — архив с одним «не вошло.txt»."""
    from app.files_safe import existing_upload_path
    buf, skipped, used = BytesIO(), [], set()

    def put(z, name, data):
        base, ext = os.path.splitext(_safe_name(name))
        n, i = base + ext, 1
        while n in used:
            i += 1
            n = f"{base} ({i}){ext}"
        used.add(n)
        z.writestr(n, data)

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for a in TA.annexes_of(db, m):
            try:
                name, data = _annex_docx(db, a["id"])
                put(z, name.replace("ДС без номера", a["number"]), data)      # черновик — номером из раскладки

            except Exception as e:  # noqa: BLE001 — причина уходит в «не вошло.txt»
                skipped.append(f"{a['number']}: {getattr(e, 'detail', None) or e}")
        for fid, fname, path, label in db.execute(text("""
                SELECT f.id, f.filename, f.path, coalesce(a.number, 'УПД № ' || f.upd_no::text, 'скан')
                  FROM master_deal_files f LEFT JOIN sales_annexes a ON a.id = f.annex_id
                 WHERE f.master_deal_id = :m ORDER BY f.id"""), {"m": m.id}).all():
            try:
                with open(existing_upload_path(path), "rb") as fh:
                    put(z, f"скан · {label} — {fname}", fh.read())
            except Exception:  # noqa: BLE001
                skipped.append(f"скан «{fname}»: файла нет на диске")
        if skipped or not used:
            z.writestr("не вошло.txt", "\n".join(skipped or ["В пакете пока нет готовых файлов: ДС не созданы, сканов нет."]))
    return f"{m.code}.zip", buf.getvalue()
