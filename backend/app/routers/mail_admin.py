# -*- coding: utf-8 -*-
"""Настройки → Почта: журнал писем наружу, шаблоны, проверка канала.

ГРАНИЦА ПРАВ ЗДЕСЬ НЕ КОСМЕТИЧЕСКАЯ (решение владельца 13.09.2026):

  · `view` — журнал. Его смотрят трафики и аккаунты: они пишут площадкам и должны
    видеть, дошло ли письмо, не спрашивая админа;
  · `edit` — шаблоны, настройки отправителя и проверочное письмо. Текст, уходящий
    наружу от имени компании, правит один человек, а не каждый, кто его отправляет.

ГРАНИЦА «СЕКРЕТ / НЕ СЕКРЕТ» ТОЖЕ ПРОВЕДЕНА ЯВНО. Хост, логин и пароль ящика живут в
`.env` и на экран НЕ попадают даже админу — тот же порядок, что у токенов ОРД, DSP и
бота. На экране правится то, что не является доступом: имя отправителя, приставка к теме,
подпись. Показывать пароль «только админу» значит завести ещё одно место, откуда он
утечёт.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.mail import client as mail
from app.mail import editor
from app.mail import preview
from app.mail import templates as tpl
from app import retention
from app.mail.models import KIND_LABELS, KIND_TEST, MailLog, MailTemplate
from app.models import User
from app.permissions import require_permission

router = APIRouter()

VIEW = require_permission("settings_mail", "view")
EDIT = require_permission("settings_mail", "edit")

# Настройки, которые НЕ являются доступом и потому правятся на экране.
SET_FROM_NAME = "mail_from_name"       # переопределяет MAIL_FROM_NAME, если задано
SET_SUBJECT_PREFIX = "mail_subject_prefix"
SET_SIGNATURE = "mail_signature"

LOG_LIMIT_MAX = 500


def _setting(db: Session, key: str) -> str:
    return (db.execute(sa_text("SELECT value FROM company_settings WHERE key = :k"),
                       {"k": key}).scalar() or "")


def _save_setting(db: Session, key: str, value: str) -> None:
    db.execute(sa_text(
        "INSERT INTO company_settings (key, value) VALUES (:k, :v) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"),
        {"k": key, "v": value})


def _seed(db: Session) -> None:
    """Завести заводские шаблоны, если их ещё нет.

    Не миграцией: текст письма правят люди, и накат миграции не должен возвращать
    «заводской» вариант поверх выправленного.
    """
    have = {k for (k,) in db.query(MailTemplate.key).all()}
    added = False
    for s in tpl.SEED:
        if s["key"] in have:
            continue
        db.add(MailTemplate(key=s["key"], title=s["title"], subject=s["subject"],
                            body=s["body"]))
        added = True
    if added:
        db.commit()


@router.get("/state")
def state(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Состояние канала одним ответом: настроен ли, чем правится, что в очереди."""
    cfg = mail.config()
    stuck = db.query(MailLog).filter(MailLog.status != "sent").count()
    return {
        # Пароль и логин НЕ отдаём — см. шапку модуля. Отдаём только факт настроенности
        # и адрес отправителя: он и так виден каждому получателю письма.
        "configured": cfg.ok,
        # Почему не настроена — словами. «Не настроена» без причины отправляет человека
        # перебирать семь переменных; замер 14.09.2026 показал, что ошибиться можно
        # ровно одной — подписью вместо адреса в MAIL_FROM.
        "problem": cfg.problem,
        "sender": cfg.sender or None,
        "host": cfg.host or None,
        "mode": cfg.mode,
        "env_hint": "Хост, логин и пароль ящика правятся в .env на сервере",
        "from_name": _setting(db, SET_FROM_NAME) or cfg.sender_name,
        "subject_prefix": _setting(db, SET_SUBJECT_PREFIX),
        "signature": _setting(db, SET_SIGNATURE),
        "queued": stuck,
        "kinds": KIND_LABELS,
    }


class SettingsIn(BaseModel):
    from_name: Optional[str] = None
    subject_prefix: Optional[str] = None
    signature: Optional[str] = None


@router.put("/settings")
def save_settings(payload: SettingsIn, db: Session = Depends(get_db),
                  user: User = Depends(EDIT)):
    for key, val in ((SET_FROM_NAME, payload.from_name),
                     (SET_SUBJECT_PREFIX, payload.subject_prefix),
                     (SET_SIGNATURE, payload.signature)):
        if val is not None:
            _save_setting(db, key, val.strip()[:500])
    db.commit()
    log_action(db, user, "mail_settings", "settings", None,
               f"имя отправителя: {(payload.from_name or '')[:60]}")
    return state(db, user)


@router.get("/templates")
def list_templates(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    _seed(db)
    rows = db.query(MailTemplate).order_by(MailTemplate.key).all()
    return {"items": [{"id": r.id, "key": r.key, "title": r.title, "subject": r.subject,
                       "body": r.body, "is_active": r.is_active,
                       "updated_at": r.updated_at,
                       "fields": tpl.known_fields(r.key)} for r in rows]}


@router.get("/cards/text")
def card_text(contour: str, key: str, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Тема и текстовая часть письма по текущему шаблону."""
    try:
        return preview.text_part(db, contour, key)
    except (KeyError, IndexError):
        raise HTTPException(404, "Такой карточки нет")


@router.get("/editor/{contour}")
def editor_state(contour: str, keys: str = "", db: Session = Depends(get_db),
                 user: User = Depends(VIEW)):
    """Всё для экрана редактора одним ответом: оболочка, карточки, подстановки, проверки.

    Одним, а не четырьмя: экран показывает их СОГЛАСОВАННО — подстановки считаются из
    состава, проверки из подстановок. Четыре запроса означали бы четыре момента времени
    и, при медленной сети, взаимно противоречивые числа на одном экране.
    """
    if contour not in (editor.STAFF, editor.PUB):
        raise HTTPException(404, "Нет такого контура")
    chosen = [k for k in keys.split("|") if k]
    cards_list = editor.cards(db, contour)
    data = [{"tone": c["tone"], "tag": c["tag"]} for c in cards_list if c["key"] in chosen]
    return {
        "shell": editor.shell(db, contour),
        "cards": cards_list,
        "fields": editor.fields_of(contour),
        "values": editor.values(db, contour, data),
        "checks": editor.checks(db, contour, chosen),
    }


@router.get("/editor/{contour}/preview", response_class=HTMLResponse)
def editor_preview(contour: str, keys: str = "", db: Session = Depends(get_db),
                   user: User = Depends(VIEW)):
    """Собранное письмо — тем же рисовальщиком, что и живая отправка."""
    if contour not in (editor.STAFF, editor.PUB):
        raise HTTPException(404, "Нет такого контура")
    brand = _setting(db, SET_FROM_NAME) or "SIMB-AD"
    return HTMLResponse(editor.compose(db, contour,
                                       [k for k in keys.split("|") if k], brand=brand))


@router.post("/editor/{contour}/test")
def editor_test(contour: str, keys: str = "", db: Session = Depends(get_db),
                user: User = Depends(EDIT)):
    """Отправить СОБРАННОЕ письмо себе — ровно в том виде, в каком его увидит адресат.

    Только себе, как и проверка канала: кнопка с произвольным адресом превращает систему
    в отправщик писем кому угодно от имени компании. Проверить вёрстку можно и на своём
    ящике — а почтовые клиенты режут разметку по-разному, и «в браузере выглядит хорошо»
    про письмо не значит ничего.
    """
    if contour not in (editor.STAFF, editor.PUB):
        raise HTTPException(404, "Нет такого контура")
    if not mail.valid_address(user.email or ""):
        raise HTTPException(400, "У вашей учётки нет почтового адреса")
    chosen = [k for k in keys.split("|") if k]
    if not chosen:
        raise HTTPException(400, "В письме нет ни одной карточки — отправлять нечего")

    from app.mail import send as gate
    brand = _setting(db, SET_FROM_NAME) or "SIMB-AD"
    html = editor.compose(db, contour, chosen, brand=brand)
    cards_list = [c for c in editor.cards(db, contour) if c["key"] in chosen]
    vals = editor.values(db, contour,
                         [{"tone": c["tone"], "tag": c["tag"]} for c in cards_list])
    sh = editor.shell(db, contour)
    # Тема — ИЗ ОБОЛОЧКИ, а не «Проверка»: проверяем в том числе и её, она первое, что
    # видит получатель. Приставка говорит, что письмо проверочное.
    subject = ("[проверка] " + editor.subst(sh["subject"]["value"], vals))[:200]
    body = "\n\n".join(
        f'{c["title"]}\n{c["body"] or ""}'.strip() for c in cards_list)

    row = gate.send_and_log(db, to=user.email, to_name=getattr(user, "name", None),
                            subject=subject, body=body, html=html,
                            kind=KIND_TEST, user_id=user.id)
    if row.status != "sent":
        raise HTTPException(400, f"Письмо не ушло: {row.error or 'причина не названа'}")
    log_action(db, user, "mail_test", "settings", None,
               f"Пробное письмо контура {contour} на {user.email}: карточек {len(chosen)}")
    return {"status": row.status, "to": row.to_email, "cards": len(chosen)}


class ShellIn(BaseModel):
    patch: dict


@router.put("/editor/{contour}/shell")
def save_shell(contour: str, payload: ShellIn, db: Session = Depends(get_db),
               user: User = Depends(EDIT)):
    if contour not in (editor.STAFF, editor.PUB):
        raise HTTPException(404, "Нет такого контура")
    editor.save_shell(db, contour, payload.patch)
    db.commit()
    log_action(db, user, "mail_shell", "settings", None,
               f"контур {contour}: {', '.join(payload.patch)}")
    return {"shell": editor.shell(db, contour)}


@router.put("/editor/{contour}/card/{key}")
def save_card(contour: str, key: str, payload: ShellIn, db: Session = Depends(get_db),
              user: User = Depends(EDIT)):
    if contour not in (editor.STAFF, editor.PUB):
        raise HTTPException(404, "Нет такого контура")
    try:
        editor.save_card(db, contour, key, payload.patch)
    except KeyError:
        raise HTTPException(404, "Такой карточки нет")
    db.commit()
    log_action(db, user, "mail_card_text", "settings", None, f"{contour}: {key}")
    return {"cards": editor.cards(db, contour)}


class TemplateIn(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None
    is_active: Optional[bool] = None


@router.put("/templates/{key}")
def save_template(key: str, payload: TemplateIn, db: Session = Depends(get_db),
                  user: User = Depends(EDIT)):
    """Правка шаблона. Неизвестное поле подстановки — отказ, а не молчаливое сохранение.

    Опечатка в имени поля при отправке НЕ падает: получатель просто видит скобки в
    письме, и узнаём мы об этом от него. Поэтому проверка стоит здесь.
    """
    row = db.query(MailTemplate).filter(MailTemplate.key == key).first()
    if row is None:
        raise HTTPException(404, "Шаблон не найден")
    subject = row.subject if payload.subject is None else payload.subject
    body = row.body if payload.body is None else payload.body
    bad = tpl.unknown_fields(key, subject, body)
    if bad:
        known = ", ".join(f"{{{n}}}" for n in tpl.known_fields(key))
        raise HTTPException(
            400, f"Неизвестные поля: {', '.join('{' + b + '}' for b in bad)}. "
                 f"Для этого письма доступны: {known or '— нет полей —'}")
    if not (subject or "").strip() or not (body or "").strip():
        raise HTTPException(400, "Тема и текст письма не могут быть пустыми")
    row.subject, row.body = subject, body
    if payload.is_active is not None:
        row.is_active = payload.is_active
    row.updated_at, row.updated_by = datetime.utcnow(), user.id
    db.commit()
    log_action(db, user, "mail_template", "settings", row.id, f"Шаблон «{row.title}»")
    return {"key": row.key, "subject": row.subject, "body": row.body,
            "is_active": row.is_active}


@router.get("/channels")
def channels(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Состояние ВСЕХ каналов модуля одним ответом: почта и оба телеграм-бота.

    Каналов у рассылки несколько, а вопрос к ним один — «настроен ли и чем проверить».
    Три отдельных места для этого ответа означали бы, что ненастроенный канал находят
    последним, уже разбирая «почему не пришло».

    Секретов здесь нет: токены и пароль ящика живут в `.env`, на экран уходит только
    ФАКТ настроенности и то, что и так видно получателю — адрес отправителя, имя бота.
    """
    from app.notify import telegram
    from app.notify.models import UserNotificationChannels

    cfg = mail.config()
    staff_chats = (db.query(UserNotificationChannels)
                   .filter(UserNotificationChannels.tg_verified_at.isnot(None)).count())
    pub_chats = db.execute(sa_text(
        "SELECT count(*) FROM cabinet_account_tg WHERE verified_at IS NOT NULL")).scalar()

    return {
        "mail": {
            "configured": cfg.ok, "problem": cfg.problem,
            "sender": cfg.sender or None, "host": cfg.host or None, "mode": cfg.mode,
            "queued": db.query(MailLog).filter(MailLog.status != "sent").count(),
            "from_name": _setting(db, SET_FROM_NAME) or cfg.sender_name,
            "subject_prefix": _setting(db, SET_SUBJECT_PREFIX),
            "signature": _setting(db, SET_SIGNATURE),
            "env_hint": "Хост, логин и пароль ящика правятся в .env на сервере",
        },
        # Ботов ДВА и они разные по существу: наш рабочий пишет сотрудникам, бот
        # площадок — наружу. Один бот на оба контура означал бы, что площадка видит
        # внутренний алёрт-бот подрядчика, а обработчик `/start` гадает, чей перед ним код.
        "bots": [
            {"contour": "staff", "label": "Наш рабочий бот",
             "hint": "Пишет сотрудникам: очередь сделок, поломки, просрочки.",
             "configured": telegram.configured(telegram.STAFF),
             "username": telegram.bot_username(telegram.STAFF),
             "env": telegram.ENV_TOKEN_STAFF, "linked": staff_chats,
             "linked_hint": "учёток привязали чат"},
            {"contour": "pub", "label": "Бот площадок",
             "hint": "Пишет паблишерам в их кабинет. Подключает его каждый себе сам — "
                     "создать за человека чат мы не можем.",
             "configured": telegram.configured(telegram.PUB),
             "username": telegram.bot_username(telegram.PUB),
             "env": telegram.ENV_TOKEN_PUB, "linked": pub_chats or 0,
             "linked_hint": "учёток кабинета привязали чат"},
        ],
    }


@router.get("/log/{row_id}")
def mail_one(row_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Одно письмо целиком. Нужно общему журналу отправок: он показывает строки обоих
    контуров, а тело письма лежит только у внешнего — и лежит ИТОГОВОЕ, а не ссылка на
    шаблон, поэтому видно ровно то, что получила площадка.
    """
    row = db.query(MailLog).filter(MailLog.id == row_id).first()
    if row is None:
        raise HTTPException(404, "Письма нет в журнале")
    return {"id": row.id, "subject": row.subject, "body": row.body, "html": row.html,
            "to_email": row.to_email, "to_name": row.to_name, "reply_to": row.reply_to,
            "status": row.status, "error": row.error, "kind": row.kind,
            "kind_label": KIND_LABELS.get(row.kind, row.kind),
            "created_at": row.created_at, "sent_at": row.sent_at}


@router.get("/log")
def mail_log(limit: int = 100, offset: int = 0, kind: Optional[str] = None,
             status: Optional[str] = None, q: Optional[str] = None,
             db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Журнал писем. Поиск по адресу и теме — по ним человек и вспоминает письмо."""
    limit = max(1, min(int(limit or 100), LOG_LIMIT_MAX))
    query = db.query(MailLog)
    if kind:
        query = query.filter(MailLog.kind == kind)
    if status:
        query = query.filter(MailLog.status == status)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(MailLog.to_email.ilike(like) | MailLog.subject.ilike(like))
    total = query.count()
    rows = query.order_by(MailLog.id.desc()).offset(max(0, offset)).limit(limit).all()
    names = dict(db.query(User.id, User.name).all())
    # Срок хранения отдаём экрану, а не пишем на нём числом: иначе экран обещает три
    # месяца, уборка живёт по своему сроку, и расходятся они молча.
    return {"total": total, "keep_months": retention.JOURNAL_MONTHS, "items": [{
        "id": r.id, "to_email": r.to_email, "to_name": r.to_name,
        "reply_to": r.reply_to, "subject": r.subject, "body": r.body,
        "kind": r.kind, "kind_label": KIND_LABELS.get(r.kind, r.kind),
        "entity_type": r.entity_type, "entity_id": r.entity_id,
        "user": names.get(r.user_id), "status": r.status, "error": r.error,
        "attempts": r.attempts, "created_at": r.created_at, "sent_at": r.sent_at,
    } for r in rows]}


@router.post("/test")
def send_test(db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Проверочное письмо СЕБЕ. Только себе — и это не перестраховка.

    Кнопка «отправить проверку» с произвольным адресом превращает систему в отправщик
    писем кому угодно от имени компании. Проверить канал можно и на своём ящике.
    """
    if not mail.valid_address(user.email or ""):
        raise HTTPException(400, "У вашей учётки нет почтового адреса")
    from app.mail import send as gate
    row = gate.send_and_log(
        db, to=user.email, to_name=getattr(user, "name", None),
        subject="Проверка почтового канала",
        body="Если вы читаете это письмо, почтовый гейт настроен и работает.",
        kind=KIND_TEST, user_id=user.id)
    if row.status != "sent":
        raise HTTPException(400, f"Письмо не ушло: {row.error or 'причина не названа'}")
    log_action(db, user, "mail_test", "settings", None, f"Проверка на {user.email}")
    return {"status": row.status, "to": row.to_email, "id": row.id}
