"""Заявки о сбоях: приём от людей и разбор.

ДВЕ РАЗНЫЕ ДВЕРИ, и это главное решение файла.

· ПИСАТЬ может каждый, кто вошёл — правом `settings_bugs` подача НЕ закрыта. Заявка это
  свидетельство, а не привилегия: закрыв её правом, мы получили бы ровно то состояние,
  ради выхода из которого всё и затевается — человек видит сбой и не может о нём сказать.
· ЧИТАТЬ журнал и менять статусы — по праву `settings_bugs`. Там чужие скриншоты,
  адреса страниц и имена; это разбор, а не подача.

Разбор зерна, почему это не бэклог отладки и откуда берётся обстановка — в шапке миграции
`2026-09-17_bug_reports.sql` и в `app/bugs/models.py`.
"""
import os
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit import log_action
from app.routers.auth import get_current_user
from app.bugs import models as m
from app.database import get_db
from app.files_safe import UPLOADS_ROOT, existing_upload_path
from app.models import User
from app.permissions import require_permission

router = APIRouter()

VIEW = require_permission("settings_bugs", "view")
EDIT = require_permission("settings_bugs", "edit")


class BugIn(BaseModel):
    comment: str
    page_url: Optional[str] = None
    page_title: Optional[str] = None
    app_version: Optional[str] = None
    viewport: Optional[str] = None


class BugPatch(BaseModel):
    status: Optional[str] = None
    resolution: Optional[str] = None


def _short(v: Optional[str], n: int) -> Optional[str]:
    """Обрезаем ДО базы, а не полагаемся на длину колонки: адрес страницы бывает длиннее
    любого разумного предела, и падение вставки читалось бы как «кнопка не работает»."""
    return (v or "").strip()[:n] or None


def _user_name(db: Session, user_id: Optional[int]) -> Optional[str]:
    if not user_id:
        return None
    u = db.query(User).filter(User.id == user_id).first()
    return (u.name or u.email) if u else None


def out(db: Session, r: m.BugReport, *, with_files: bool = False) -> dict:
    d = {
        "id": r.id, "contour": r.contour,
        "contour_label": m.CONTOUR_LABEL.get(r.contour, r.contour),
        "author": r.author_name, "publisher_id": r.publisher_id,
        "page_url": r.page_url, "page_title": r.page_title,
        "app_version": r.app_version, "viewport": r.viewport,
        "comment": r.comment, "status": r.status,
        "created_at": r.created_at, "seen_at": r.seen_at,
        "resolved_at": r.resolved_at, "resolution": r.resolution,
        "backlog_item_id": r.backlog_item_id,
        "files": len(r.files or []),
    }
    if with_files:
        d["file_list"] = [{"id": f.id, "name": f.original_name,
                           "size_bytes": f.size_bytes} for f in (r.files or [])]
        # Браузер и его версия нужны только на разборе — в списке это шум.
        d["user_agent"] = r.user_agent
        # КТО прочитал и кто закрыл. Поля писались с самого начала, но наружу не
        # отдавались — то есть в базе лежал ответ на вопрос «кто этим занимался», а
        # увидеть его было негде. Имя, а не id: id в интерфейсе никому ничего не говорит.
        d["seen_by"] = _user_name(db, r.seen_by)
        d["resolved_by"] = _user_name(db, r.resolved_by)
    return d


def create_report(db: Session, *, contour: str, author_name: str, comment: str,
                  user_id: Optional[int] = None, account_id: Optional[int] = None,
                  publisher_id: Optional[int] = None, page_url: Optional[str] = None,
                  page_title: Optional[str] = None, app_version: Optional[str] = None,
                  user_agent: Optional[str] = None,
                  viewport: Optional[str] = None) -> m.BugReport:
    """Общая точка приёма для обоих контуров.

    Кабинет площадки в базу не пишет сам — он зовёт шлюз, а шлюз зовёт эту функцию. Две
    копии приёма разошлись бы на первой же правке, и разошлись бы молча: заявки от
    площадок просто оказались бы устроены иначе, чем заявки сотрудников.
    """
    text = (comment or "").strip()
    if not text:
        raise HTTPException(400, "Опишите, что случилось — без этого заявку не разобрать")
    r = m.BugReport(
        contour=contour, author_user_id=user_id, author_account_id=account_id,
        author_name=(author_name or "—")[:160], publisher_id=publisher_id,
        page_url=_short(page_url, 500), page_title=_short(page_title, 300),
        app_version=_short(app_version, 32), user_agent=_short(user_agent, 500),
        viewport=_short(viewport, 32), comment=text, status="новая")
    db.add(r)
    db.flush()          # id нужен сразу: к нему цепляются файлы и ссылка в уведомлении
    return r


def announce(db: Session, r: m.BugReport, actor=None) -> None:
    """Уведомление о новой заявке. Отдельной функцией — её зовут оба контура.

    Падение уведомления НЕ роняет приём: заявка уже принята, и потерять её из-за
    недоступного телеграма было бы худшим из возможных исходов.
    """
    from app.notify import bus
    who = f"{m.CONTOUR_LABEL.get(r.contour, r.contour)} · {r.author_name}"
    where = r.page_title or r.page_url or "страница не указана"
    first = (r.comment or "").strip().replace("\n", " ")
    facts = [("страница", where), ("от кого", who)]
    if r.files:
        facts.append(("скриншотов", str(len(r.files))))
    try:
        bus.emit(db, "bug_report_new",
                 title="Заявка о сбое",
                 body=first[:300] + ("…" if len(first) > 300 else ""),
                 link="/settings/bugs", entity_type="bug_report", entity_id=r.id,
                 actor=actor, facts=facts)
    except Exception:                                    # noqa: BLE001
        import logging
        logging.getLogger("finance").warning(
            "заявка %s принята, уведомление не ушло", r.id, exc_info=True)


def attach(db: Session, r: m.BugReport, *, content: bytes, filename: str,
           content_type: Optional[str]) -> m.BugReportFile:
    """Скриншот к заявке. Проверки те же, что у вложений площадки: вид по расширению,
    предел размера, имя на диске собираем МЫ."""
    if len(r.files or []) >= m.MAX_FILES:
        raise HTTPException(400, f"К заявке можно приложить {m.MAX_FILES} снимков")
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in m.ALLOWED_EXT:
        raise HTTPException(415, f"Разрешены снимки экрана: {', '.join(sorted(m.ALLOWED_EXT))}")
    if len(content) > m.MAX_FILE_BYTES:
        raise HTTPException(413, f"Снимок больше {m.MAX_FILE_BYTES // 1024 // 1024} МБ")

    # Каталог по месяцу: уборка по сроку ходит папками, а не перебором строк.
    sub = f"{m.UPLOAD_SUBDIR}/{datetime.utcnow():%Y-%m}"
    root = os.path.join(UPLOADS_ROOT, sub)
    os.makedirs(root, exist_ok=True)
    safe = re.sub(r"[^\w.\-]", "_", os.path.basename(filename or "screen"))[:80]
    stored = f"b{r.id}_{len(r.files or []) + 1}_{safe}"
    with open(os.path.join(root, stored), "wb") as fh:
        fh.write(content)
    f = m.BugReportFile(report_id=r.id, rel_path=f"{sub}/{stored}",
                        original_name=filename, content_type=content_type,
                        size_bytes=len(content))
    db.add(f)
    return f


# ── подача: доступна каждому, кто вошёл ───────────────────────────────────

@router.post("")
def bug_create(payload: BugIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    r = create_report(db, contour=m.STAFF, author_name=user.name or user.email,
                      user_id=user.id, comment=payload.comment,
                      page_url=payload.page_url, page_title=payload.page_title,
                      app_version=payload.app_version, viewport=payload.viewport)
    db.commit()
    log_action(db, user, "bug_report_new", "bug_report", r.id,
               f"заявка о сбое: {(r.page_title or r.page_url or '—')}")
    return out(db, r, with_files=True)


@router.post("/{report_id}/file")
async def bug_attach(report_id: int, file: UploadFile = File(...),
                     db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Снимок к СВОЕЙ заявке. Чужую дополнить нельзя: заявка — свидетельство, и дописать
    в чужое свидетельство не должен никто, включая разбирающего."""
    r = db.query(m.BugReport).filter(m.BugReport.id == report_id).first()
    if not r:
        raise HTTPException(404, "Заявка не найдена")
    if r.author_user_id != user.id:
        raise HTTPException(403, "Можно дополнять только свою заявку")
    f = attach(db, r, content=await file.read(), filename=file.filename or "screen.png",
               content_type=file.content_type)
    db.commit()
    return {"id": f.id, "name": f.original_name, "size_bytes": f.size_bytes}


@router.post("/{report_id}/sent")
def bug_sent(report_id: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    """Заявка дописана — уведомляем. Отдельным вызовом, потому что снимки грузятся ПОСЛЕ
    создания: уведоми мы сразу, в нём стояло бы «скриншотов 0» на заявке со снимками."""
    r = db.query(m.BugReport).filter(m.BugReport.id == report_id).first()
    if not r or r.author_user_id != user.id:
        raise HTTPException(404, "Заявка не найдена")
    announce(db, r, actor=user)
    db.commit()
    return {"ok": True}


# ── разбор: по праву ──────────────────────────────────────────────────────

@router.get("")
def bug_list(status: Optional[str] = None, contour: Optional[str] = None,
             limit: int = 200, db: Session = Depends(get_db),
             user: User = Depends(VIEW)):
    q = db.query(m.BugReport)
    if status:
        q = q.filter(m.BugReport.status == status)
    if contour:
        q = q.filter(m.BugReport.contour == contour)
    rows = q.order_by(m.BugReport.created_at.desc()).limit(min(limit, 1000)).all()
    counts = {s: db.query(m.BugReport).filter(m.BugReport.status == s).count()
              for s in m.STATUSES}
    return {"items": [out(db, r) for r in rows], "counts": counts,
            "statuses": m.STATUSES, "contours": m.CONTOUR_LABEL}


@router.get("/{report_id}")
def bug_one(report_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    r = db.query(m.BugReport).filter(m.BugReport.id == report_id).first()
    if not r:
        raise HTTPException(404, "Заявка не найдена")
    # «Её вообще прочитали?» — единственный вопрос приславшего. Отметку ставим один раз,
    # при первом открытии, и больше не трогаем: она про первую реакцию, а не про последнюю.
    if r.seen_at is None:
        r.seen_at, r.seen_by = datetime.utcnow(), user.id
        db.commit()
    return out(db, r, with_files=True)


@router.get("/{report_id}/file/{file_id}")
def bug_file(report_id: int, file_id: int, db: Session = Depends(get_db),
             user: User = Depends(VIEW)):
    f = (db.query(m.BugReportFile)
         .filter(m.BugReportFile.id == file_id,
                 m.BugReportFile.report_id == report_id).first())
    if not f:
        raise HTTPException(404, "Снимок не найден")
    path = existing_upload_path(f.rel_path)
    if not path:
        raise HTTPException(404, "Файл снимка не найден на диске")
    return FileResponse(path, media_type=f.content_type or "image/png",
                        filename=f.original_name or "screen.png")


@router.patch("/{report_id}")
def bug_patch(report_id: int, payload: BugPatch, db: Session = Depends(get_db),
              user: User = Depends(EDIT)):
    r = db.query(m.BugReport).filter(m.BugReport.id == report_id).first()
    if not r:
        raise HTTPException(404, "Заявка не найдена")
    if payload.resolution is not None:
        r.resolution = payload.resolution.strip() or None
    if payload.status is not None:
        if payload.status not in m.STATUSES:
            raise HTTPException(400, f"Статус бывает: {', '.join(m.STATUSES)}")
        # Закрытие без причины не принимается — то же правило, что в бэклоге отладки:
        # «закрыто» без объяснения через месяц не отличить от «забыли».
        if payload.status in m.CLOSED_STATUSES and not (r.resolution or "").strip():
            raise HTTPException(400, "Напишите, чем закончилось — иначе статус не принимается")
        r.status = payload.status
        closed = payload.status in m.CLOSED_STATUSES
        r.resolved_at = datetime.utcnow() if closed else None
        r.resolved_by = user.id if closed else None
    db.commit()
    log_action(db, user, "bug_report_status", "bug_report", r.id,
               f"статус «{r.status}»" + (f": {(r.resolution or '')[:120]}" if r.resolution else ""))
    return out(db, r, with_files=True)


@router.post("/{report_id}/backlog")
def bug_to_backlog(report_id: int, db: Session = Depends(get_db),
                   user: User = Depends(EDIT)):
    """Завести из заявки запись наблюдения. Связь односторонняя и ставится один раз."""
    from app.backlog_models import BacklogItem

    r = db.query(m.BugReport).filter(m.BugReport.id == report_id).first()
    if not r:
        raise HTTPException(404, "Заявка не найдена")
    if r.backlog_item_id:
        raise HTTPException(400, "По этой заявке наблюдение уже заведено")
    item = BacklogItem(
        title=f"Заявка №{r.id}: {(r.page_title or r.page_url or 'без страницы')}"[:300],
        area="заявка о сбое",
        context=f"{m.CONTOUR_LABEL.get(r.contour, r.contour)} · {r.author_name}\n"
                f"{r.page_url or ''}",
        # Главное поле бэклога заполняем словами ЧЕЛОВЕКА: он и описал, как выглядит сбой.
        signal_bad=r.comment, created_by=user.id)
    db.add(item)
    db.flush()
    r.backlog_item_id = item.id
    db.commit()
    log_action(db, user, "bug_report_backlog", "bug_report", r.id,
               f"заведено наблюдение №{item.id}")
    return {"backlog_item_id": item.id, **out(db, r, with_files=True)}


__all__ = ["router", "create_report", "announce", "attach", "out"]
