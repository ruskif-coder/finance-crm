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
from types import SimpleNamespace
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit import log_action
from app.cabinet import journal, overview
from app.cabinet.models import (CABINET_STATES, Cabinet, CabinetAccount,
                                CabinetPublisher)
from app.database import get_db
from app.models import User
from app.passwords import hash_password
from app.permissions import require_permission
from app.sales.models import SalesPublisher, SalesRep
from app.sales.reps import ensure_rep, staff_users

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
            # CPM живёт на ПЛОЩАДКЕ, здесь только показывается: кабинет — про доступ, а
            # цена про договор. 0 и NULL одинаково означают «не согласован».
            "cpm": float(p.cpm_contract) if p.cpm_contract else None,
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
    rep_users = {r.id: r.user_id for r in db.query(SalesRep).all()}

    by_cab = {}
    for lnk in links:
        by_cab.setdefault(lnk.cabinet_id, []).append(lnk.publisher_id)
    acc_by_cab = {}
    for a in accounts:
        acc_by_cab.setdefault(a.cabinet_id, []).append(a)

    # Показатели считаются ПАЧКОЙ на все площадки сразу: по кабинету на запрос дало бы
    # N+1 там, где данные всё равно нужны целиком.
    pending = overview.creatives_pending(db)
    live = overview.campaigns_live(db)
    recons = overview.recons_open(db)
    services = overview.services_by_publisher(db)
    logs = overview.logs_by_cabinet(db)

    out = []
    for c in cabinets:
        # Для СПИСКА площадок служебный кабинет видит все, а для КОНТАКТОВ — только свои
        # связи, которых у него нет. Это не противоречие: он наш, и его люди не контакты
        # площадок. Поэтому ниже два разных набора идентификаторов.
        service = c.kind == 'служебный'
        own_ids = by_cab.get(c.id, [])
        mine = ([pubs[i] for i in own_ids if i in pubs]
                if not service else list(pubs.values()))
        shown_ids = [p.id for p in mine]
        accounts = acc_by_cab.get(c.id, [])
        last_login = max((a.last_login_at for a in accounts if a.last_login_at),
                         default=None)
        svc = {}
        for pid in shown_ids:
            for item in services.get(pid, []):
                svc.setdefault(item["name"], set()).update(item["surfaces"])
        box = logs.get(c.id, {"rows": [], "total": 0})
        out.append({
            "id": c.id, "name": c.name, "kind": c.kind, "state": c.state,
            "manager_id": c.manager_id, "manager": reps.get(c.manager_id),
            "manager_user_id": rep_users.get(c.manager_id),
            "note": c.note,
            "publishers": [_publisher_out(p) for p in sorted(mine, key=lambda x: x.name)],
            "accounts": [_account_out(a) for a in accounts],
            # У служебного кабинета контактов площадок нет по построению — колонка
            # наполняется его собственными учётками. Разделение сделано ЗДЕСЬ, а не на
            # экране: форма строки одна, и склейка на фронте развела бы правило надвое.
            "contacts": (overview.service_accounts_as_contacts(db, c.id) if service
                         else overview.contacts_of(db, own_ids)),
            "activity": overview.activity(shown_ids, pending, live, recons, last_login),
            "services": [{"name": n, "surfaces": sorted(s)}
                         for n, s in sorted(svc.items())],
            "log": box["rows"], "log_total": box["total"],
        })

    taken = {lnk.publisher_id for lnk in links}
    # «Без учёток» считается по кабинету, а не по человеку: кабинет без единой учётки
    # физически нерабочий — площадка не может войти, и это не предупреждение, а факт.
    return {
        "cabinets": out,
        "kpi": {
            "cabinets": len(out),
            "active": sum(1 for c in out if c["state"] == 'активен'),
            "draft": sum(1 for c in out if c["state"] == 'черновик'),
            "accounts": sum(len(c["accounts"]) for c in out),
            "creatives_pending": sum(c["activity"]["creatives_pending"] for c in out),
            "campaigns_live": sum(c["activity"]["campaigns_live"] for c in out),
            "without_accounts": sum(1 for c in out if not c["accounts"]),
        },
        "our_contacts": overview.our_contacts(db),
        # Свободные — те, что ещё не в кабинете. Площадка живёт ровно в одном, поэтому
        # список выбора не может показывать занятые: это была бы ошибка при сохранении
        # вместо запрета при выборе.
        "free_publishers": [_publisher_out(p) for p in pubs.values() if p.id not in taken],
        # Сотрудники — по УЧЁТКАМ, а не по справочнику ответственных. До 03.09.2026
        # список читал `sales_reps` и показывал 11 человек из 20: без профиля там нет
        # ни одного трафика и ни одного менеджера паблишеров — то есть тех, кого чаще
        # всего и надо показать площадке. Отключённые учётки в выбор не попадают.
        # `any_role=True`: контактом может быть и юрист, и финансист — рабочая группа
        # у них не проставлена, а к площадке они выходят.
        "managers": staff_users(db, any_role=True),
        # Должности — тем же ответом: контактное лицо заводится прямо здесь, и отдельный
        # запрос за справочником дал бы паузу ровно в момент открытия формы.
        "positions": [{"id": r.id, "name": r.name} for r in db.execute(text(
            "SELECT id, name FROM sales_contact_positions ORDER BY sort_order, name"))],
    }


def _manager_rep_id(db: Session, user_id: Optional[int]) -> Optional[int]:
    """Учётка → профиль ответственного. 0 и None одинаково означают «снять»."""
    if not user_id:
        return None
    try:
        return ensure_rep(db, user_id).id
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class CabinetIn(BaseModel):
    name: str
    # Ответственный выбирается УЧЁТКОЙ: кабинеты ведут менеджеры паблишеров, а их в
    # справочнике ответственных нет ни одного (app/sales/reps.py). Профиль заводится
    # при выборе.
    manager_user_id: Optional[int] = None
    note: Optional[str] = None


@router.post("/")
def create_cabinet(payload: CabinetIn, db: Session = Depends(get_db),
                   current_user: User = Depends(EDIT)):
    """Пустой кабинет. Площадки и люди добавляются отдельными действиями — так и
    задумано: кабинет без площадок это не ошибка, а первый шаг."""
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Укажите название кабинета")
    c = Cabinet(name=name, manager_id=_manager_rep_id(db, payload.manager_user_id),
                note=(payload.note or "").strip() or None)
    db.add(c)
    db.commit()
    log_action(db, current_user, "cabinet_create", "cabinet", c.id, name)
    return {"id": c.id}


class CabinetPatch(BaseModel):
    name: Optional[str] = None
    state: Optional[str] = None
    manager_user_id: Optional[int] = None
    note: Optional[str] = None


# ── наши контакты у площадок ──────────────────────────────────────────────────
#
# Стоят ВЫШЕ `PUT /{cabinet_id}` намеренно. FastAPI подбирает маршрут ПО ПОРЯДКУ
# объявления, и путь с параметром перехватывает буквальный: `PUT /cabinets/our-contacts`
# уходил в правку кабинета, где «our-contacts» разбирался как номер, и запрос падал
# на валидации. Прибор `tests/test_route_order.py` следит, чтобы это не повторилось.

class OurContactIn(BaseModel):
    role: str
    # Учётка сотрудника. Профиль ответственного (`sales_reps`) заводится под ней сам —
    # см. `app/sales/reps.py`: выбирают человека, а не строку справочника.
    user_id: int
    is_shown: bool = True


class OurContactsIn(BaseModel):
    """Список целиком, а не по одной записи.

    Контактов единицы, и порядок в списке — часть смысла: первым площадка видит того,
    к кому идти в первую очередь. Отправлять его по одной строке значило бы собирать
    порядок из нескольких запросов и получить его наполовину применённым при обрыве.
    """
    items: List[OurContactIn]


@router.put("/our-contacts")
def set_our_contacts(payload: OurContactsIn, db: Session = Depends(get_db),
                     current_user: User = Depends(EDIT)):
    """Кого из наших видит площадка. Общие на все кабинеты (владелец, 30.08.2026)."""
    seen = set()
    for it in payload.items:
        if it.user_id in seen:
            raise HTTPException(status_code=400,
                                detail="Один сотрудник не может стоять дважды")
        seen.add(it.user_id)
        if not (it.role or "").strip():
            raise HTTPException(status_code=400, detail="У контакта должна быть роль")

    # Профили заводим ДО удаления старых строк: `ensure_rep` откажет на отключённой
    # учётке, и список контактов должен в этом случае остаться прежним, а не опустеть.
    try:
        rep_ids = [ensure_rep(db, it.user_id).id for it in payload.items]
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e

    db.execute(text("DELETE FROM cabinet_our_contact"))
    for i, (it, rep_id) in enumerate(zip(payload.items, rep_ids)):
        db.execute(text(
            "INSERT INTO cabinet_our_contact (role, rep_id, sort_order, is_shown) "
            "VALUES (:r, :p, :o, :s)"),
            {"r": it.role.strip(), "p": rep_id, "o": i, "s": it.is_shown})
    db.commit()
    log_action(db, current_user, "cabinet_our_contacts", "cabinet", 0,
               f"контактов: {len(payload.items)}")
    return {"items": overview.our_contacts(db)}


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
        # В ленту кабинета попадает только смена состояния, а не всякая правка: имя и
        # заметку меняем мы у себя, а приостановка меняет то, что человек может делать.
        if payload.state in ('приостановлен', 'активен') and c.state != payload.state:
            journal.write(db, 'кабинет_пауза' if payload.state == 'приостановлен'
                          else 'кабинет_возобновлён',
                          cabinet_id=c.id, actor_name=current_user.name,
                          entity_type='cabinet', entity_id=c.id)
        c.state = payload.state; changes.append(f"состояние: {c.state}")
    if payload.manager_user_id is not None:
        c.manager_id = _manager_rep_id(db, payload.manager_user_id)
        changes.append("ответственный")
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
        pub = db.query(SalesPublisher).filter(SalesPublisher.id == pid).first()
        journal.write(db, 'площадка_добавлена', cabinet_id=cabinet_id,
                      publisher_id=pid, actor_name=current_user.name,
                      subject=pub.name if pub else None,
                      entity_type='sales_publisher', entity_id=pid)
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
    pub = db.query(SalesPublisher).filter(SalesPublisher.id == publisher_id).first()
    # Строка журнала заводится ДО удаления связи: после него `publisher_id` в ленте
    # останется, а вот имя площадки взять было бы уже неоткуда.
    journal.write(db, 'площадка_убрана', cabinet_id=cabinet_id,
                  publisher_id=publisher_id, actor_name=current_user.name,
                  subject=pub.name if pub else None,
                  entity_type='sales_publisher', entity_id=publisher_id)
    db.delete(row)
    db.commit()
    log_action(db, current_user, "cabinet_publishers", "cabinet", cabinet_id,
               f"откреплена площадка {publisher_id}")
    return {"detached": publisher_id}


class AccessIn(BaseModel):
    """Кому выдаём доступ.

    У кабинета площадки — только `contact_id`: человек уже заведён в реестре, и вторая
    запись о нём означала бы две истории по одному пользователю (владелец, 30.08.2026).
    У СЛУЖЕБНОГО кабинета наоборот: его люди — наши, контактами площадок они не
    являются и в реестре им места нет, поэтому там принимаются имя и почта.
    """
    contact_id: Optional[int] = None
    can_approve: bool = True
    name: Optional[str] = None
    email: Optional[str] = None


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

    # Два входа, и путать их нельзя: в кабинет площадки человек приходит ИЗ РЕЕСТРА, в
    # служебный — заводится здесь. Обмен местами означал бы либо вторую запись о том же
    # человеке, либо нашего сотрудника, приписанного к чужой площадке.
    if c.kind == 'служебный':
        if payload.contact_id:
            raise HTTPException(
                status_code=400,
                detail="В служебный кабинет доступ выдаётся нашему человеку, "
                       "а не контакту площадки")
        name = (payload.name or "").strip()
        email = (payload.email or "").strip().lower()
        if not name or "@" not in email:
            raise HTTPException(status_code=400, detail="Нужны имя и почта")
        row = SimpleNamespace(id=None, name=name, email=email, publisher_id=None,
                              pub=None)
    else:
        if not payload.contact_id:
            raise HTTPException(
                status_code=400,
                detail="Доступ выдаётся контакту площадки — выберите его из списка")
        row = db.execute(text(
            "SELECT c.id, c.name, c.email, c.publisher_id, p.name AS pub "
            "FROM sales_publisher_contacts c "
            "JOIN sales_publishers p ON p.id = c.publisher_id "
            "WHERE c.id = :i"), {"i": payload.contact_id}).first()
        if not row:
            raise HTTPException(status_code=404, detail="Контакт не найден")
        if not (row.email or "").strip():
            raise HTTPException(
                status_code=400,
                detail=f"У контакта «{row.name}» нет почты — по ней он входит")
    # Площадка контакта должна быть В ЭТОМ кабинете: иначе человек получит доступ к
    # чужому инвентарю, а выглядеть это будет как обычная выдача.
    if row.publisher_id:
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

    acc = CabinetAccount(cabinet_id=cabinet_id, contact_id=row.id,   # None у служебного
                         email=email, name=row.name or email,
                         can_approve=bool(payload.can_approve))
    db.add(acc)
    db.flush()
    journal.write(db, 'учётка_создана', cabinet_id=cabinet_id, account_id=acc.id,
                  actor_name=current_user.name, subject=acc.name,
                  entity_type='cabinet_account', entity_id=acc.id)
    db.commit()
    log_action(db, current_user, "cabinet_access_grant", "cabinet", cabinet_id,
               f"{c.name}: доступ {email} ({row.pub})")
    return {"id": acc.id}


class AccountPatch(BaseModel):
    is_active: Optional[bool] = None
    can_approve: Optional[bool] = None
    # Почта — это ЛОГИН. Правится здесь же, потому что «мало ли что поменять надо»
    # (владелец, 30.08.2026), но со всеми теми же проверками, что при выдаче доступа.
    name: Optional[str] = None
    email: Optional[str] = None


@router.put("/accounts/{account_id}")
def update_account(account_id: int, payload: AccountPatch, db: Session = Depends(get_db),
                   current_user: User = Depends(EDIT)):
    """Отключить или сменить роль. Учётка НЕ удаляется: её вердикты останутся в истории,
    а снимок автора на них — единственное, чем они подписаны."""
    acc = db.query(CabinetAccount).filter(CabinetAccount.id == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Учётка не найдена")
    changes = []
    if payload.name is not None and payload.name.strip() and payload.name != acc.name:
        acc.name = payload.name.strip(); changes.append("имя")
    if payload.email is not None:
        email = payload.email.strip().lower()
        if not email or "@" not in email:
            raise HTTPException(status_code=400, detail="Нужна почта — по ней вход")
        if email != acc.email:
            busy = (db.query(CabinetAccount)
                    .filter(CabinetAccount.email == email,
                            CabinetAccount.id != acc.id).first())
            if busy:
                raise HTTPException(status_code=400,
                                    detail=f"Учётка на {email} уже существует")
            acc.email = email; changes.append("почта")
    if payload.is_active is not None and bool(payload.is_active) != bool(acc.is_active):
        acc.is_active = bool(payload.is_active)
        changes.append("включён" if acc.is_active else "отключён")
        # Включение обратно отдельной строкой не пишем: у ленты один смысл — «доступ
        # менялся», и «отключена/создана» его уже несут.
        if not acc.is_active:
            journal.write(db, 'учётка_отключена', cabinet_id=acc.cabinet_id,
                          account_id=acc.id, actor_name=current_user.name,
                          subject=acc.name, entity_type='cabinet_account',
                          entity_id=acc.id)
    if payload.can_approve is not None and bool(payload.can_approve) != bool(acc.can_approve):
        acc.can_approve = bool(payload.can_approve)
        changes.append("согласует" if acc.can_approve else "только просмотр")
        journal.write(db, 'уровень', cabinet_id=acc.cabinet_id, account_id=acc.id,
                      actor_name=current_user.name,
                      subject=f"{acc.name} → "
                              f"{'все' if acc.can_approve else 'просмотр'}",
                      entity_type='cabinet_account', entity_id=acc.id)
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
    journal.write(db, 'пароль', cabinet_id=acc.cabinet_id, account_id=acc.id,
                  actor_name=current_user.name, subject=acc.name,
                  entity_type='cabinet_account', entity_id=acc.id)
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
    # Несуществующая площадка — 404, а не пустой список контактов.
    if not db.query(SalesPublisher.id).filter(SalesPublisher.id == publisher_id).first():
        raise HTTPException(status_code=404, detail="Площадка не найдена")
    rows = db.execute(text(
        "SELECT c.id, c.name, c.email, c.role, c.is_primary, a.id AS account_id, "
        "       a.is_active, a.can_approve "
        "FROM sales_publisher_contacts c "
        "LEFT JOIN cabinet_account a ON a.contact_id = c.id "
        "WHERE c.publisher_id = :p ORDER BY c.is_primary DESC NULLS LAST, c.name"),
        {"p": publisher_id}).all()
    return {"contacts": [dict(r._mapping) for r in rows]}


# ============================== журнал и наши контакты ==============================

@router.get("/{cabinet_id}/log")
def cabinet_log(cabinet_id: int, days: int = 90, limit: int = 300,
                db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    """Полная лента кабинета — то, что за ссылкой «Весь лог».

    Окно по умолчанию шире карточки (90 дней против 30): в карточке лента отвечает на
    «что происходит», здесь — на «что было», и это разные вопросы.
    """
    # Несуществующий кабинет — 404: пустой журнал читается как «ничего не делали».
    if not db.query(Cabinet.id).filter(Cabinet.id == cabinet_id).first():
        raise HTTPException(status_code=404, detail="Кабинет не найден")
    from datetime import datetime, timedelta

    from app.cabinet.journal import BY_KEY

    since = datetime.utcnow() - timedelta(days=max(1, min(days, 365)))
    rows = db.execute(text(
        "SELECT l.action, l.tone, l.actor_side, l.actor_name, l.subject, l.created_at, "
        "       p.name AS publisher "
        "  FROM cabinet_log l "
        "  LEFT JOIN sales_publishers p ON p.id = l.publisher_id "
        " WHERE l.cabinet_id = :c AND l.created_at >= :since "
        " ORDER BY l.created_at DESC, l.id DESC LIMIT :lim"),
        {"c": cabinet_id, "since": since, "lim": max(1, min(limit, 1000))})
    out = []
    for r in rows:
        a = BY_KEY.get(r.action)
        out.append({"label": a.label if a else r.action, "action": r.action,
                    "tone": r.tone, "side": r.actor_side, "actor": r.actor_name,
                    "subject": r.subject, "publisher": r.publisher, "at": r.created_at})
    return {"rows": out, "days": days}
