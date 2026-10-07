# -*- coding: utf-8 -*-
"""Проверка креатива: заведение, показ, удаление и уборка по сроку (07.10.2026).

Правило хранения (владелец 07.10.2026): проверка живёт 48 часов; потом креатив нацеливания
останавливается в DSP, файлы и строка удаляются. Строка исчезает только ПОСЛЕ подтверждённой
остановки — удалять креатив в DSP нечем, и забытый, он крутился бы без хозяина.
"""
import logging
import os
import re
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.creative_check import analyze as az
from app.creative_check.models import LIFETIME_HOURS, CreativeCheck
from app.files_safe import remove_upload
from app.launch_prep import sandbox

log = logging.getLogger("finance.creative_check")

UPLOADS_ROOT = "/app/uploads"
STORE_DIR = "creative_check"


class CheckInputError(ValueError):
    """Введено не то: сказать человеку, что именно."""


def normalize_url(raw: Optional[str]) -> str:
    """Посадочная — просто домен (владелец 07.10.2026). `example.ru` → `https://example.ru`."""
    v = (raw or "").strip()
    if not v:
        raise CheckInputError("Укажите домен рекламодателя")
    if not re.match(r"^[a-z][a-z0-9+.\-]*://", v, re.I):
        v = "https://" + v
    parsed = urlparse(v)
    host = parsed.hostname or ""
    if parsed.scheme.lower() not in ("http", "https") or "." not in host or " " in v:
        raise CheckInputError("Домен введён неверно: нужен адрес вида example.ru")
    if len(v) > 500:
        raise CheckInputError("Адрес слишком длинный")
    return v


def default_publishers(db: Session) -> List[dict]:
    """Площадки по умолчанию: наш код и веб-поверхность, не в архиве (владелец 07.10.2026)."""
    rows = db.execute(text("""
        SELECT p.id, p.name, p.domain FROM sales_publishers p
         WHERE p.our_code AND p.status <> 'АРХИВ'
           AND EXISTS (SELECT 1 FROM sales_publisher_surfaces s
                        WHERE s.publisher_id = p.id AND s.kind = 'web')
         ORDER BY lower(p.name)""")).all()
    return [{"id": r[0], "name": r[1], "domain": r[2]} for r in rows]


def create(db: Session, user, title: str, url: str, filename: str, data: bytes) -> CreativeCheck:
    # Название ОБЯЗАТЕЛЬНО (владелец 07.10.2026, поверх макета): иначе проверки не отличить друг от друга.
    # Домен необязателен: без него посадочной служит наш сайт (`FALLBACK_LINK` при заведении копии),
    # в базе хранится пустая строка.
    title = (title or "").strip()
    if not title:
        raise CheckInputError("Укажите название")
    link = normalize_url(url) if (url or "").strip() else ""
    result = az.analyze(filename, data)          # az.CheckRejected — наверх, текстом человеку
    pubs = [p["id"] for p in default_publishers(db)]
    now = datetime.utcnow()
    chk = CreativeCheck(
        created_by=user.id, title=title[:200], advertiser_url=link, kind=result.kind,
        original_name=(filename or "creative")[:200], file_path="", publisher_ids=pubs,
        verdict={"warnings": result.warnings,
                 "prepared": [az.PREPARED_LABELS.get(p, p) for p in result.prepared],
                 "info": result.info},
        created_at=now, expires_at=now + timedelta(hours=LIFETIME_HOURS))
    db.add(chk)
    db.flush()                                   # id нужен для имени файла
    rel = f"{STORE_DIR}/chk{chk.id}.zip"
    absolute = os.path.join(UPLOADS_ROOT, rel)
    try:
        os.makedirs(os.path.dirname(absolute), exist_ok=True)
        with open(absolute, "wb") as fh:
            fh.write(result.zip_bytes)
        token, entry = sandbox.unpack(absolute, UPLOADS_ROOT)
    except (OSError, sandbox.SandboxError) as e:
        db.rollback()
        remove_upload(rel, root=UPLOADS_ROOT)
        raise az.CheckRejected(f"Не удалось сохранить креатив: {e}")
    chk.file_path, chk.sandbox_token, chk.entry_path = rel, token, entry
    db.commit()
    return chk


def view(db: Session, chk: CreativeCheck) -> dict:
    """Карточка проверки для экрана: замечания, срок, площадки с доменами, ссылка предпросмотра."""
    names = {}
    if chk.publisher_ids:
        for pid, name, domain in db.execute(
                text("SELECT id, name, domain FROM sales_publishers WHERE id = ANY(:ids)"),
                {"ids": list(chk.publisher_ids)}):
            names[pid] = {"id": pid, "name": name, "domain": domain}
    v = chk.verdict or {}
    return {
        "id": chk.id, "title": chk.title, "advertiser_url": chk.advertiser_url, "kind": chk.kind,
        "original_name": chk.original_name,
        "warnings": v.get("warnings", []), "prepared": v.get("prepared", []), "info": v.get("info", {}),
        "created_at": chk.created_at.isoformat(), "expires_at": chk.expires_at.isoformat(),
        "dsp_state": chk.dsp_state,
        "sandbox_url": sandbox.public_url(chk.sandbox_token, chk.entry_path),
        "publishers": [names[i] for i in chk.publisher_ids if i in names],
    }


def remove_files(chk: CreativeCheck) -> None:
    remove_upload(chk.file_path, root=UPLOADS_ROOT)
    sandbox.remove(UPLOADS_ROOT, chk.sandbox_token)


def delete(db: Session, chk: CreativeCheck, *, client=None) -> None:
    """Остановить нацеливание, затем стереть файлы и строку. Остановка не удалась — исключение,
    строка остаётся (её доберёт уборка)."""
    from app.dsp import check_creative
    check_creative.stop(db, chk, client=client)
    remove_files(chk)
    db.delete(chk)
    db.commit()


def cleanup_expired(db: Session, *, client=None) -> dict:
    """Уборка по сроку: каждая просроченная проверка останавливается и стирается. Сбой DSP на одной
    проверке не мешает остальным; не остановленная остаётся до следующего прохода."""
    done, kept = 0, []
    rows = (db.query(CreativeCheck).filter(CreativeCheck.expires_at < datetime.utcnow())
            .order_by(CreativeCheck.id).all())
    for chk in rows:
        cid = chk.id
        try:
            delete(db, chk, client=client)
            done += 1
        except Exception as e:                     # noqa: BLE001 — одна проверка не роняет уборку
            db.rollback()
            kept.append(f"№{cid}: {e}")
            log.warning("Проверка креатива №%s не убрана: %s", cid, e)
    return {"removed": done, "kept": kept}
