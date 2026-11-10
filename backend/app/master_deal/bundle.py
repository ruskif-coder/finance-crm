# -*- coding: utf-8 -*-
"""«Скачать всё · zip» (хендофф реестра v2, 21.10.2026): готовые файлы пакета одним архивом — ДС (.docx, тот же документ, что
кнопка «ДС» конструктора) и приложенные сканы. Что собрать нельзя (заявка юристу открыта, не хватает реквизитов), в архив не
кладём, а называем в «не вошло.txt» — пустой молчащий архив хуже, чем список причин."""
import os
import zipfile
from io import BytesIO

from sqlalchemy.orm import Session

from app import doc_names as DN
from app.master_deal import to_annex as TA

def _safe_name(s: str) -> str:
    bad = '\\/:*?"<>|\r\n\t'
    return "".join("_" if ch in bad else ch for ch in (s or "")).strip() or "файл"

def _annex_docx(db: Session, annex_id: int) -> tuple:
    """(имя, байты) ДС — сервисом печатной сборки, тем же, что ручка `/annexes/{id}/docx`; отказ — HTTPException с причиной."""
    from app.sales import annex_print
    return annex_print.printable_docx(db, annex_id)


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
        from app.sales import annex_external as X
        from app.sales.models import SalesAnnex
        for a in TA.annexes_of(db, m):
            row = db.get(SalesAnnex, a["id"])
            if X.is_external(row):
                # Подписан вне системы (03.11.2026): документ — файл клиента (он ляжет ниже, сканом) или ссылка ЭДО. Наш DOCX
                # не собираем: это был бы наш текст под чужим подписанным документом.
                if row.edo_link:
                    put(z, DN.for_annex(db, row, ".txt", "ссылка ЭДО"), f"{a['number']} подписан вне системы.\nДокумент в ЭДО: {row.edo_link}\n")
                continue
            try:
                _, data = _annex_docx(db, a["id"])
                put(z, DN.for_annex(db, row, ".docx", number=a["number"]), data)     # черновик — номером из раскладки

            except Exception as e:  # noqa: BLE001 — причина уходит в «не вошло.txt»
                skipped.append(f"{a['number']}: {getattr(e, 'detail', None) or e}")
        from app.master_deal.models import MasterDealFile
        for f in db.query(MasterDealFile).filter(MasterDealFile.master_deal_id == m.id).order_by(MasterDealFile.id):
            try:
                with open(existing_upload_path(f.path), "rb") as fh:
                    put(z, DN.for_package_file(db, m, f), fh.read())     # то же имя, что при скачивании файла по одному
            except Exception:  # noqa: BLE001
                skipped.append(f"скан «{f.filename}»: файла нет на диске")
        if skipped or not used:
            z.writestr("не вошло.txt", "\n".join(skipped or ["В пакете пока нет готовых файлов: ДС не созданы, сканов нет."]))
    return DN.for_package_zip(db, m), buf.getvalue()
