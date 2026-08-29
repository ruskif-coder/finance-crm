"""Кабинеты паблишеров — администрирование со стороны ядра.

Экран живёт в контуре «Паблишеры»: кабинет — свойство отношений с площадкой, а не
отдельная сущность системы.

Порядок работы (владелец, 28.08.2026): заводится пустой кабинет → к нему прикрепляются
площадки → людям площадки выдаётся доступ → настраиваются рабочие чаты.

**Доступ выдаётся КОНТАКТУ площадки**, а не заводится новым человеком: контакты уже есть
в реестре (48 на 26 площадках), и вторая запись означала бы две точки правки, из которых
одна обязательно останется старой.

**Восстановления по почте нет** — пароль выдаёт и сбрасывает админ (решение владельца
23.08.2026). Внешний контур без почтового канала восстановления остаётся и без всего
класса атак на него. Каждая выдача идёт в журнал действий.
"""
import secrets
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit import log_action
from app.cabinet.models import (CABINET_STATES, Cabinet, CabinetAccount,
                                CabinetPublisher)
from app.database import get_db
from app.models import User
from app.passwords import hash_password
from app.permissions import require_permission
from app.sales.models import SalesPublisher, SalesRep

router = APIRouter()

VIEW = require_permission("dir_publishers_cabinets", "view")
EDIT = require_permission("dir_publishers_cabinets", "edit")

MIN_PASSWORD = 8


def _publisher_out(p: SalesPublisher) -> dict:
    """Площадка глазами настройки кабинета — вместе с готовностью и чатами.

    **Готовность важнее удобства.** Без кода площадки пара не получит имени, и
    согласование упрётся в ошибку уже ПОСЛЕ того, как человек вошёл и нажал
    «Согласовать». Экран обязан показать это заранее — восемь площадок из 41 без кода
    (замер 28.08.2026).
    """
    problems = []
    if not p.code:
        problems.append("нет кода площадки — пара не получит имени")
    if p.status != "СОТРУДНИЧАЕМ":
        problems.append(f"статус «{p.status}»")
    return {"id": p.id, "name": p.name, "domain": p.domain, "code": p.code,
            "status": p.status, "problems": problems,
            "chat_title": p.chat_title, "chat_url": p.chat_url,
            "chat_url_max": p.chat_url_max}


def _account_out(a: CabinetAccount) -> dict:
    state = ("отключён" if not a.is_active
             else "нет пароля" if not a.hashed_password else "работает")
    return {"id": a.id, "email": a.email, "name": a.name,
            "is_active": bool(a.is_active), "can_approve": bool(a.can_approve),
            "contact_id": a.contact_id, "state": state,
            "last_login_at": a.last_login_at}


@router.get("/")
def list_cabinets(db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    """Всё дерево одним ответом: кабинеты, их площадки, их люди и свободные площадки.

    Тем же приёмом, что сборка креативов: несколько запросов на один экран дают мигание
    и рассинхрон, когда часть уже обновилась, а часть нет.
    """
    cabinets = db.query(Cabinet).order_by(Cabinet.kind.desc(), Cabinet.name).all()
    links = db.query(CabinetPublisher).all()
    pubs = {p.id: p for p in db.query(SalesPublisher).order_by(SalesPublisher.name).all()}
    accounts = db.query(CabinetAccount).order_by(CabinetAccount.name).all()
    reps = {r.id: r.name for r in db.query(SalesRep).all()}

    by_cab = {}
    for lnk in links:
        by_cab.setdefault(lnk.cabinet_id, []).append(lnk.publisher_id)
    acc_by_cab = {}
    for a in accounts:
        acc_by_cab.setdefault(a.cabinet_id, []).append(a)

    out = []
    for c in cabinets:
        mine = ([pubs[i] for i in by_cab.get(c.id, []) if i in pubs]
                if c.kind != 'служебный' else list(pubs.values()))
        out.append({
            "id": c.id, "name": c.name, "kind": c.kind, "state": c.state,
            "manager_id": c.manager_id, "manager": reps.get(c.manager_id),
            "note": c.note,
            "publishers": [_publisher_out(p) for p in sorted(mine, key=lambda x: x.name)],
            "accounts": [_account_out(a) for a in acc_by_cab.get(c.id, [])],
        })

    taken = {lnk.publisher_id for lnk in links}
    return {
        "cabinets": out,
        # Свободные — те, что ещё не в кабинете. Площадка живёт ровно в одном, поэтому
        # список выбора не может показывать занятые: это была бы ошибка при сохранении
        # вместо запрета при выборе.
        "free_publishers": [_publisher_out(p) for p in pubs.values() if p.id not in taken],
        "managers": [{"id": r.id, "name": r.name} for r in
                     db.query(SalesRep).filter(SalesRep.is_active.is_(True))
                     .order_by(SalesRep.name).all()],
        # Должности — тем же ответом: контактное лицо заводится прямо здесь, и отдельный
        # запрос за справочником дал бы паузу ровно в момент открытия формы.
        "positions": [{"id": r.id, "name": r.name} for r in db.execute(text(
            "SELECT id, name FROM sales_contact_positions ORDER BY sort_order, name"))],
    }


class CabinetIn(BaseModel):
    name: str
    manager_id: Optional[int] = None
    note: Optional[str] = None


@router.post("/")
def create_cabinet(payload: CabinetIn, db: Session = Depends(get_db),
                   current_user: User = Depends(EDIT)):
    """Пустой кабинет. Площадки и люди добавляются отдельными действиями — так и
    задумано: кабинет без площадок это не ошибка, а первый шаг."""
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Укажите название кабинета")
    c = Cabinet(name=name, manager_id=payload.manager_id,
                note=(payload.note or "").strip() or None)
    db.add(c)
    db.commit()
    log_action(db, current_user, "cabinet_create", "cabinet", c.id, name)
    return {"id": c.id}


class CabinetPatch(BaseModel):
    name: Optional[str] = None
    state: Optional[str] = None
    manager_id: Optional[int] = None
    note: Optional[str] = None


@router.put("/{cabinet_id}")
def update_cabinet(cabinet_id: int, payload: CabinetPatch, db: Session = Depends(get_db),
                   current_user: User = Depends(EDIT)):
    c = db.query(Cabinet).filter(Cabinet.id == cabinet_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Кабинет не найден")
    changes = []
    if payload.name is not None and payload.name.strip():
        c.name = payload.name.strip(); changes.append("название")
    if payload.state is not None:
        if payload.state not in CABINET_STATES:
            raise HTTPException(status_code=400,
                                detail=f"Состояние: {', '.join(CABINET_STATES)}")
        # Активировать пустой кабинет незачем: человеку нечего было бы увидеть, а
        # состояние сказало бы, что всё готово.
        if payload.state == 'активен' and c.kind != 'служебный' and not c.publishers:
            raise HTTPException(status_code=400,
                                detail="В кабинете нет площадок — активировать нечего")
        c.state = payload.state; changes.append(f"состояние: {c.state}")
    if payload.manager_id is not None:
        c.manager_id = payload.manager_id or None; changes.append("ответственный")
    if payload.note is not None:
        c.note = payload.note.strip() or None; changes.append("заметка")
    db.commit()
    if changes:
        log_action(db, current_user, "cabinet_update", "cabinet", c.id,
                   f"{c.name}: {', '.join(changes)}")
    return {"id": c.id, "state": c.state}


class PublishersIn(BaseModel):
    publisher_ids: List[int]


@router.post("/{cabinet_id}/publishers")
def attach_publishers(cabinet_id: int, payload: PublishersIn,
                      db: Session = Depends(get_db), current_user: User = Depends(EDIT)):
    """Прикрепить площадки. Занятую другим кабинетом — отклоняем С ИМЕНЕМ владельца.

    «Площадка уже в кабинете» без имени заставляет искать её по всем кабинетам руками.
    """
    c = db.query(Cabinet).filter(Cabinet.id == cabinet_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Кабинет не найден")
    if c.kind == 'служебный':
        raise HTTPException(status_code=400,
                            detail="Служебный кабинет видит все площадки — прикреплять нечего")

    added = 0
    for pid in dict.fromkeys(payload.publisher_ids or []):
        busy = db.query(CabinetPublisher).filter(
            CabinetPublisher.publisher_id == pid).first()
        if busy:
            if busy.cabinet_id == cabinet_id:
                continue
            owner = db.query(Cabinet).filter(Cabinet.id == busy.cabinet_id).first()
            pub = db.query(SalesPublisher).filter(SalesPublisher.id == pid).first()
            raise HTTPException(
                status_code=400,
                detail=f"«{pub.name if pub else pid}» уже в кабинете «{owner.name}» — "
                       f"площадка живёт ровно в одном")
        db.add(CabinetPublisher(cabinet_id=cabinet_id, publisher_id=pid))
        added += 1
    db.commit()
    log_action(db, current_user, "cabinet_publishers", "cabinet", cabinet_id,
               f"{c.name}: прикреплено {added}")
    return {"added": added}


@router.delete("/{cabinet_id}/publishers/{publisher_id}")
def detach_publisher(cabinet_id: int, publisher_id: int, db: Session = Depends(get_db),
                     current_user: User = Depends(EDIT)):
    row = db.query(CabinetPublisher).filter(
        CabinetPublisher.cabinet_id == cabinet_id,
        CabinetPublisher.publisher_id == publisher_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Площадка не в этом кабинете")
    db.delete(row)
    db.commit()
    log_action(db, current_user, "cabinet_publishers", "cabinet", cabinet_id,
               f"откреплена площадка {publisher_id}")
    return {"detached": publisher_id}


class AccessIn(BaseModel):
    contact_id: int
    can_approve: bool = True


@router.post("/{cabinet_id}/accounts")
def grant_access(cabinet_id: int, payload: AccessIn, db: Session = Depends(get_db),
                 current_user: User = Depends(EDIT)):
    """Выдать доступ КОНТАКТУ площадки. Имя и почта берутся из контакта, не набираются.

    Учётка рождается без пароля: пароль выдаётся отдельным действием, чтобы в журнале
    было видно и заведение, и выдачу доступа, а не одно вместо двух.
    """
    c = db.query(Cabinet).filter(Cabinet.id == cabinet_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Кабинет не найден")

    row = db.execute(text(
        "SELECT c.id, c.name, c.email, c.publisher_id, p.name AS pub "
        "FROM sales_publisher_contacts c JOIN sales_publishers p ON p.id = c.publisher_id "
        "WHERE c.id = :i"), {"i": payload.contact_id}).first()
    if not row:
        raise HTTPException(status_code=404, detail="Контакт не найден")
    if not (row.email or "").strip():
        raise HTTPException(status_code=400,
                            detail=f"У контакта «{row.name}» нет почты — по ней он входит")
    # Площадка контакта должна быть В ЭТОМ кабинете: иначе человек получит доступ к
    # чужому инвентарю, а выглядеть это будет как обычная выдача.
    if c.kind != 'служебный':
        in_cab = db.query(CabinetPublisher).filter(
            CabinetPublisher.cabinet_id == cabinet_id,
            CabinetPublisher.publisher_id == row.publisher_id).first()
        if not in_cab:
            raise HTTPException(
                status_code=400,
                detail=f"«{row.pub}» не прикреплена к этому кабинету")

    email = row.email.strip().lower()
    exists = db.query(CabinetAccount).filter(CabinetAccount.email == email).first()
    if exists:
        raise HTTPException(status_code=400,
                            detail=f"Доступ на {email} уже выдан")

    acc = CabinetAccount(cabinet_id=cabinet_id, contact_id=row.id,
                         email=email, name=row.name or email,
                         can_approve=bool(payload.can_approve))
    db.add(acc)
    db.commit()
    log_action(db, current_user, "cabinet_access_grant", "cabinet", cabinet_id,
               f"{c.name}: доступ {email} ({row.pub})")
    return {"id": acc.id}


class AccountPatch(BaseModel):
    is_active: Optional[bool] = None
    can_approve: Optional[bool] = None


@router.put("/accounts/{account_id}")
def update_account(account_id: int, payload: AccountPatch, db: Session = Depends(get_db),
                   current_user: User = Depends(EDIT)):
    """Отключить или сменить роль. Учётка НЕ удаляется: её вердикты останутся в истории,
    а снимок автора на них — единственное, чем они подписаны."""
    acc = db.query(CabinetAccount).filter(CabinetAccount.id == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Учётка не найдена")
    changes = []
    if payload.is_active is not None and bool(payload.is_active) != bool(acc.is_active):
        acc.is_active = bool(payload.is_active)
        changes.append("включён" if acc.is_active else "отключён")
    if payload.can_approve is not None and bool(payload.can_approve) != bool(acc.can_approve):
        acc.can_approve = bool(payload.can_approve)
        changes.append("согласует" if acc.can_approve else "только просмотр")
    db.commit()
    if changes:
        log_action(db, current_user, "cabinet_account_update", "cabinet",
                   acc.cabinet_id, f"{acc.email}: {', '.join(changes)}")
    return {"id": acc.id}


class PasswordIn(BaseModel):
    password: Optional[str] = None


@router.post("/accounts/{account_id}/password")
def set_password(account_id: int, payload: PasswordIn, db: Session = Depends(get_db),
                 current_user: User = Depends(EDIT)):
    """Выдать или сбросить пароль. Возвращается ОДИН раз — показать и передать.

    Хранить его негде: в базе только хеш. Пустой запрос означает «придумай сам» — так
    надёжнее, чем пароль, набранный админом в спешке.

    Канал передачи — рабочий чат площадки: почтового у внешнего контура нет и не будет.
    """
    acc = db.query(CabinetAccount).filter(CabinetAccount.id == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Учётка не найдена")
    pw = (payload.password or "").strip() or secrets.token_urlsafe(12)
    if len(pw) < MIN_PASSWORD:
        raise HTTPException(status_code=400, detail=f"Пароль короче {MIN_PASSWORD} знаков")
    acc.hashed_password = hash_password(pw)
    db.commit()
    log_action(db, current_user, "cabinet_account_password", "cabinet", acc.cabinet_id,
               f"{acc.email}: пароль выдан")
    return {"password": pw}


class ChatsIn(BaseModel):
    """Рабочие чаты площадки: Телеграм и MAX (владелец, 28.08.2026).

    Площадке они НЕ показываются — это наш канал связи. Внутри кабинета остаётся
    переписка по конкретному заданию: причина доработки и текст запроса ссылки.
    """
    chat_title: Optional[str] = None
    chat_url: Optional[str] = None
    chat_url_max: Optional[str] = None


@router.put("/publisher/{publisher_id}/chats")
def set_chats(publisher_id: int, payload: ChatsIn, db: Session = Depends(get_db),
              current_user: User = Depends(EDIT)):
    p = db.query(SalesPublisher).filter(SalesPublisher.id == publisher_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Площадка не найдена")
    for field in ("chat_url", "chat_url_max"):
        v = (getattr(payload, field) or "").strip()
        if v and not v.lower().startswith(("http://", "https://", "tg://")):
            raise HTTPException(status_code=400,
                                detail="Ссылка должна начинаться с http://, https:// или tg://")
    p.chat_title = (payload.chat_title or "").strip() or None
    p.chat_url = (payload.chat_url or "").strip() or None
    p.chat_url_max = (payload.chat_url_max or "").strip() or None
    db.commit()
    log_action(db, current_user, "cabinet_chats", "sales_publisher", p.id,
               f"{p.name}: чаты обновлены")
    return {"id": p.id}


@router.get("/publisher/{publisher_id}/contacts")
def publisher_contacts(publisher_id: int, db: Session = Depends(get_db),
                       current_user: User = Depends(VIEW)):
    """Контакты площадки — из них выдаётся доступ. Уже выданные помечены."""
    rows = db.execute(text(
        "SELECT c.id, c.name, c.email, c.role, c.is_primary, a.id AS account_id, "
        "       a.is_active, a.can_approve "
        "FROM sales_publisher_contacts c "
        "LEFT JOIN cabinet_account a ON a.contact_id = c.id "
        "WHERE c.publisher_id = :p ORDER BY c.is_primary DESC NULLS LAST, c.name"),
        {"p": publisher_id}).all()
    return {"contacts": [dict(r._mapping) for r in rows]}
