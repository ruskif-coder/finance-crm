"""Настройки уведомлений: реестр событий, профили, подписки, личные каналы.

Разделение доступа:
  * профили и их подписки — только админ (это политика для всей компании);
  * личные настройки (/me) — каждый правит свои и ничьи больше.

Страница строится ИЗ реестра (app/notify/registry.py) — новое событие появляется
в интерфейсе само, без правки фронта. См. docs/mockup_notifications.html.
"""
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit import log_action, require_admin
from app.database import get_db
from app.models import User
from app.notify import registry
from app.notify.models import (NotificationProfile, NotificationSubscription,
                               UserNotificationChannels)
from app.notify.recipients import RESOLVER_LABELS
from app.routers.auth import get_current_user

router = APIRouter()
logger = logging.getLogger("finance")

CH_FIELDS = {"app": "ch_app", "tg": "ch_tg", "mail": "ch_mail", "digest": "ch_digest"}


# ─────────────────────────────── реестр ───────────────────────────────

@router.get("/catalog")
def catalog(current_user: User = Depends(get_current_user)):
    """Всё, что нужно фронту, чтобы нарисовать матрицу: направления, каналы,
    события с их дефолтами и человеческие подписи резолверов."""
    return {
        "directions": [{"key": k, "label": l} for k, l in registry.DIRECTIONS],
        "channels": registry.CHANNELS,
        "resolvers": [{"value": k, "label": v} for k, v in RESOLVER_LABELS.items()],
        "events": [{
            "key": e.key, "direction": e.direction, "group": e.group, "title": e.title,
            "description": e.description, "tone": e.tone, "scan": e.scan, "locked": e.locked,
            "channels": {c: bool(e.channels.get(c)) for c in registry.CHANNELS},
            "params": e.params, "recipients": e.recipients,
        } for e in registry.EVENTS.values()],
    }


# ─────────────────────────────── профили ───────────────────────────────

class ProfileIn(BaseModel):
    label: str
    description: Optional[str] = None
    copy_from: Optional[int] = None      # создать на основе существующего профиля


def _profile_row(db: Session, p: NotificationProfile) -> Dict[str, Any]:
    """users — сколько человек назначено ЯВНО. Незаполненных сюда не приплюсовываем:
    формально они попадают в профиль по умолчанию, но показывать «Аккаунт · 14 чел.»,
    когда аккаунтов трое, — врать. Их количество отдаётся отдельным полем unassigned,
    чтобы было видно, что кого-то забыли распределить."""
    users = (db.query(User).filter(User.notification_profile_id == p.id,
                                   User.is_active == 1).count())
    row = {"id": p.id, "key": p.key, "label": p.label, "description": p.description,
           "is_system": p.is_system, "is_default": p.is_default, "users": users}
    if p.is_default:
        row["unassigned"] = (db.query(User)
                             .filter(User.notification_profile_id.is_(None),
                                     User.is_active == 1).count())
    return row


@router.get("/profiles")
def list_profiles(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    rows = db.query(NotificationProfile).order_by(NotificationProfile.id).all()
    return [_profile_row(db, p) for p in rows]


@router.post("/profiles")
def create_profile(data: ProfileIn, db: Session = Depends(get_db),
                   current_user: User = Depends(require_admin)):
    label = (data.label or "").strip()
    if not label:
        raise HTTPException(status_code=400, detail="Название профиля обязательно")
    key = f"custom_{int(db.query(NotificationProfile).count()) + 1}"
    while db.query(NotificationProfile).filter(NotificationProfile.key == key).first():
        key += "x"
    p = NotificationProfile(key=key, label=label, description=data.description,
                            is_system=False, is_default=False, created_by=current_user.id)
    db.add(p)
    db.flush()
    if data.copy_from:                    # копия — самый частый способ завести профиль
        for src in (db.query(NotificationSubscription)
                    .filter(NotificationSubscription.profile_id == data.copy_from).all()):
            db.add(NotificationSubscription(
                profile_id=p.id, event_key=src.event_key, is_enabled=src.is_enabled,
                ch_app=src.ch_app, ch_tg=src.ch_tg, ch_mail=src.ch_mail, ch_digest=src.ch_digest,
                params=src.params, recipients=src.recipients, updated_by=current_user.id))
    db.commit()
    log_action(db, current_user, "create_notification_profile", "notification_profile", p.id, label)
    return _profile_row(db, p)


@router.delete("/profiles/{profile_id}")
def delete_profile(profile_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(require_admin)):
    p = db.query(NotificationProfile).filter(NotificationProfile.id == profile_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Профиль не найден")
    if p.is_system:
        raise HTTPException(status_code=400, detail="Системный профиль удалить нельзя")
    # Сотрудники профиля не остаются без уведомлений — переводятся на профиль по умолчанию.
    db.query(User).filter(User.notification_profile_id == p.id).update(
        {User.notification_profile_id: None}, synchronize_session=False)
    db.query(NotificationSubscription).filter(
        NotificationSubscription.profile_id == p.id).delete(synchronize_session=False)
    db.delete(p)
    db.commit()
    log_action(db, current_user, "delete_notification_profile", "notification_profile",
               profile_id, p.label)
    return {"ok": True}


# ─────────────────────────────── подписки ───────────────────────────────

class SubIn(BaseModel):
    event_key: str
    is_enabled: bool = True
    channels: Dict[str, bool] = {}
    params: Dict[str, Any] = {}
    recipients: List[Dict[str, Any]] = []


class SubsIn(BaseModel):
    items: List[SubIn]


def _merged(db: Session, *, profile_id: Optional[int] = None,
            user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Реестр + сохранённые строки. source показывает, откуда взято значение:
    default (реестр) / profile / personal — без этого пользователь не понимает,
    почему галочка поменялась сама после правки профиля."""
    stored = {}
    if profile_id is not None:
        for s in (db.query(NotificationSubscription)
                  .filter(NotificationSubscription.profile_id == profile_id).all()):
            stored[s.event_key] = ("profile", s)
    if user_id is not None:
        prof = _profile_id_for(db, user_id)
        if prof is not None:
            for s in (db.query(NotificationSubscription)
                      .filter(NotificationSubscription.profile_id == prof).all()):
                stored[s.event_key] = ("profile", s)
        for s in (db.query(NotificationSubscription)
                  .filter(NotificationSubscription.user_id == user_id).all()):
            stored[s.event_key] = ("personal", s)

    out = []
    for e in registry.EVENTS.values():
        src, s = stored.get(e.key, ("default", None))
        if s is None:
            channels = {c: bool(e.channels.get(c)) for c in registry.CHANNELS}
            enabled, params, recips = True, dict(e.params), list(e.recipients)
        else:
            channels = {c: bool(getattr(s, CH_FIELDS[c])) for c in registry.CHANNELS}
            enabled, params, recips = bool(s.is_enabled), dict(s.params or {}), list(s.recipients or [])
        out.append({"event_key": e.key, "direction": e.direction, "group": e.group,
                    "title": e.title, "description": e.description, "tone": e.tone,
                    "scan": e.scan, "locked": e.locked, "source": src,
                    "is_enabled": enabled, "channels": channels, "params": params,
                    "recipients": recips})
    return out


def _profile_id_for(db: Session, user_id: int) -> Optional[int]:
    u = db.query(User).filter(User.id == user_id).first()
    if u is None:
        return None
    if u.notification_profile_id:
        return u.notification_profile_id
    d = db.query(NotificationProfile).filter(NotificationProfile.is_default.is_(True)).first()
    return d.id if d else None


def _save(db: Session, items: List[SubIn], actor: User, *, profile_id=None, user_id=None):
    for it in items:
        ev = registry.get(it.event_key)
        if ev is None:
            raise HTTPException(status_code=400, detail=f"Неизвестное событие: {it.event_key}")
        q = db.query(NotificationSubscription).filter(
            NotificationSubscription.event_key == it.event_key)
        q = (q.filter(NotificationSubscription.profile_id == profile_id) if profile_id
             else q.filter(NotificationSubscription.user_id == user_id))
        row = q.first()
        if row is None:
            row = NotificationSubscription(profile_id=profile_id, user_id=user_id,
                                           event_key=it.event_key)
            db.add(row)
        row.is_enabled = it.is_enabled
        for c, field in CH_FIELDS.items():
            setattr(row, field, bool(it.channels.get(c)))
        row.params = it.params or {}
        row.recipients = it.recipients or []
        row.updated_by = actor.id
    db.commit()


@router.get("/profiles/{profile_id}/subscriptions")
def profile_subs(profile_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(require_admin)):
    return _merged(db, profile_id=profile_id)


@router.put("/profiles/{profile_id}/subscriptions")
def save_profile_subs(profile_id: int, data: SubsIn, db: Session = Depends(get_db),
                      current_user: User = Depends(require_admin)):
    if not db.query(NotificationProfile).filter(NotificationProfile.id == profile_id).first():
        raise HTTPException(status_code=404, detail="Профиль не найден")
    _save(db, data.items, current_user, profile_id=profile_id)
    log_action(db, current_user, "save_notification_profile_subs", "notification_profile",
               profile_id, f"событий: {len(data.items)}")
    return {"ok": True}


# ───────────────────────────── личные настройки ─────────────────────────────

class ChannelsIn(BaseModel):
    quiet_from: Optional[int] = None
    quiet_to: Optional[int] = None
    digest_freq: Optional[str] = None
    digest_hour: Optional[int] = None
    digest_minute: Optional[int] = None
    mail_override: Optional[str] = None
    mute_until: Optional[str] = None


@router.get("/me")
def my_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ch = (db.query(UserNotificationChannels)
          .filter(UserNotificationChannels.user_id == current_user.id).first())
    prof = _profile_id_for(db, current_user.id)
    p = db.query(NotificationProfile).filter(NotificationProfile.id == prof).first() if prof else None
    return {
        "profile": {"id": p.id, "label": p.label} if p else None,
        "channels": {
            "tg_linked": bool(ch and ch.tg_verified_at),
            "mail": (ch.mail_override if ch and ch.mail_override else current_user.email),
            "quiet_from": ch.quiet_from if ch else None,
            "quiet_to": ch.quiet_to if ch else None,
            "digest_freq": (ch.digest_freq if ch else "daily"),
            "digest_hour": (ch.digest_hour if ch else 9),
            "digest_minute": (ch.digest_minute if ch else 30),
            "mute_until": (ch.mute_until if ch else None),
        },
        "items": _merged(db, user_id=current_user.id),
    }


@router.put("/me/subscriptions")
def save_my_subs(data: SubsIn, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    _save(db, data.items, current_user, user_id=current_user.id)
    return {"ok": True}


@router.delete("/me/subscriptions/{event_key}")
def reset_my_sub(event_key: str, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """«Вернуть как в профиле» — убираем личное переопределение, а не выключаем событие."""
    (db.query(NotificationSubscription)
     .filter(NotificationSubscription.user_id == current_user.id,
             NotificationSubscription.event_key == event_key)
     .delete(synchronize_session=False))
    db.commit()
    return {"ok": True}


@router.put("/me/channels")
def save_my_channels(data: ChannelsIn, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    ch = (db.query(UserNotificationChannels)
          .filter(UserNotificationChannels.user_id == current_user.id).first())
    if ch is None:
        ch = UserNotificationChannels(user_id=current_user.id)
        db.add(ch)
    for k, v in data.dict(exclude_unset=True).items():
        setattr(ch, k, v)
    db.commit()
    return {"ok": True}


# ─────────────────────────── журнал отправок ───────────────────────────

@router.get("/deliveries")
def deliveries(limit: int = 100, offset: int = 0, event_key: Optional[str] = None,
               channel: Optional[str] = None, status: Optional[str] = None,
               db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Кому, когда и что ушло. Без этого спор «мне не приходило» неразрешим,
    а молотящее вхолостую правило не находится."""
    from app.notify.models import NotificationDelivery, NotificationScanRun

    q = db.query(NotificationDelivery)
    if event_key:
        q = q.filter(NotificationDelivery.event_key == event_key)
    if channel:
        q = q.filter(NotificationDelivery.channel == channel)
    if status:
        q = q.filter(NotificationDelivery.status == status)
    total = q.count()
    rows = (q.order_by(NotificationDelivery.created_at.desc(), NotificationDelivery.id.desc())
            .offset(max(offset, 0)).limit(min(max(limit, 1), 500)).all())

    names = dict(db.query(User.id, User.name).all())
    titles = {k: e.title for k, e in registry.EVENTS.items()}
    last_run = (db.query(NotificationScanRun)
                .order_by(NotificationScanRun.id.desc()).first())
    return {
        "total": total,
        "last_scan": None if last_run is None else {
            "started_at": last_run.started_at, "finished_at": last_run.finished_at,
            "dry_run": last_run.dry_run, "matches": last_run.matches,
            "sent": last_run.sent, "suppressed": last_run.suppressed,
            "error": last_run.error,
        },
        "items": [{
            "id": r.id, "created_at": r.created_at, "event_key": r.event_key,
            "event_title": titles.get(r.event_key, r.event_key),
            "user": names.get(r.user_id, "—"), "channel": r.channel, "status": r.status,
            "suppress_reason": r.suppress_reason, "error": r.error, "title": r.title,
        } for r in rows],
    }


# ─────────────────────────── Telegram ───────────────────────────

@router.post("/me/telegram/link")
def tg_link(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Выдать код привязки. Пользователь отправляет боту «/start <код>» — chat_id
    запоминается на вебхуке. Ни пароль, ни токен пользователя тут не участвуют."""
    from app.notify import telegram
    if not telegram.configured():
        raise HTTPException(status_code=400,
                            detail="Бот не настроен: не задан TELEGRAM_BOT_TOKEN")
    ch = (db.query(UserNotificationChannels)
          .filter(UserNotificationChannels.user_id == current_user.id).first())
    if ch is None:
        ch = UserNotificationChannels(user_id=current_user.id)
        db.add(ch)
    code, expires = telegram.new_link_code()
    ch.tg_link_code, ch.tg_link_expires = code, expires
    ch.tg_chat_id, ch.tg_verified_at = None, None      # перепривязка сбрасывает старый чат
    db.commit()
    # Кроме кода отдаём диплинк: по нему Telegram сам подставит «/start <код>»,
    # человеку остаётся нажать «Начать». Раньше на экране было только имя бота из
    # .env — где именно вводить код, приходилось догадываться.
    return {"code": code, "expires_at": expires,
            "bot": telegram.bot_username(), "link": telegram.link_url(code)}


@router.delete("/me/telegram")
def tg_unlink(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ch = (db.query(UserNotificationChannels)
          .filter(UserNotificationChannels.user_id == current_user.id).first())
    if ch:
        ch.tg_chat_id = ch.tg_verified_at = ch.tg_link_code = ch.tg_link_expires = None
        db.commit()
    return {"ok": True}


def _reply_later(chat_id: str, text: str):
    """Ответ пользователю ПОСЛЕ того, как мы уже ответили Телеграму.

    Ошибку глушим намеренно: фоновая задача выполняется, когда ответ на запрос уже ушёл,
    и поднять её наверх некуда. В журнал она попадает через логгер вызова.
    """
    from app.notify import telegram
    try:
        telegram.send_message(chat_id, text)
    except Exception:
        logger.warning("tg_webhook: ответ пользователю не ушёл", exc_info=True)


@router.post("/telegram/webhook/{secret}")
def tg_webhook(secret: str, update: Dict[str, Any], bg: BackgroundTasks,
               db: Session = Depends(get_db)):
    """Апдейты от Telegram. Эндпоинт публичный (иначе бот не достучится), поэтому:
      * закрыт секретом в пути — он же ставится в setWebhook;
      * из тела берём ТОЛЬКО код и chat_id, всё остальное игнорируем;
      * тело апдейта — данные, а не команда: никакой логики по его содержимому нет.
    Всегда отвечаем 200, иначе Telegram будет ретраить один и тот же апдейт.

    ОТВЕТ ПОЛЬЗОВАТЕЛЮ УХОДИТ ФОНОВОЙ ЗАДАЧЕЙ, а не внутри запроса (08.09.2026).
    Раньше он слался здесь же, с таймаутом 10 с. Связь с Телеграмом у нас рваная —
    закреплённый адрес отвечает пять раз из шести, — и на неудачной попытке обработчик
    висел, Телеграм не дожидался ответа и считал доставку неуспешной. Копилось это тихо:
    исходящие уведомления шли нормально, а привязка по коду просто молчала, и у Телеграма
    накопилось 13 неотданных обновлений.
    """
    from app.notify import telegram
    expected = os.getenv("TELEGRAM_WEBHOOK_SECRET") or ""
    if not expected or secret != expected:
        raise HTTPException(status_code=404, detail="Not found")

    code, chat_id = telegram.parse_start_command(update)
    if not code or not chat_id:
        return {"ok": True}

    row = (db.query(UserNotificationChannels)
           .filter(UserNotificationChannels.tg_link_code == code).first())
    if row is None or (row.tg_link_expires and row.tg_link_expires < datetime.utcnow()):
        bg.add_task(_reply_later, chat_id,
                    "Код не найден или просрочен. "
                    "Получите новый в разделе «Мои уведомления».")
        return {"ok": True}

    # Привязка записывается СРАЗУ и синхронно: она и есть результат запроса. В фон уходит
    # только ответное сообщение — если оно не дойдёт, человек всё равно уже привязан.
    row.tg_chat_id = chat_id
    row.tg_verified_at = datetime.utcnow()
    row.tg_link_code = row.tg_link_expires = None
    db.commit()
    user = db.query(User).filter(User.id == row.user_id).first()
    bg.add_task(_reply_later, chat_id,
                f"Готово, {user.name if user else ''}. Уведомления будут приходить сюда.")
    return {"ok": True}


@router.post("/events/{event_key}/test")
def event_test(event_key: str, db: Session = Depends(get_db),
               current_user: User = Depends(require_admin)):
    """Прислать себе в бот ОДНО конкретное событие — как оно будет выглядеть вживую.

    Владелец 08.09.2026. Общая «проверка связи» отвечает на вопрос «канал жив?», но не на
    вопрос «что я увижу, когда это сработает». А увидеть надо заранее: половина событий
    состояниевые, их запускает сканер по расписанию, и дождаться настоящего — значит
    ждать сутки и чужую просрочку.

    Шлём ТОЛЬКО себе и только админу: это проверка, а не рассылка. Текст собирается той
    же склейкой «заголовок + тело», что и в `channels.deliver_tg`, — иначе проверка показывала
    бы не то, что придёт.

    В журнал отправок не пишем: там живут настоящие доставки, и тест исказил бы счётчики.
    Результат виден сразу — в боте либо в тексте ошибки.
    """
    from app.notify import registry, telegram

    ev = registry.get(event_key)
    if ev is None:
        raise HTTPException(status_code=404, detail="Событие не найдено в реестре")
    ch = (db.query(UserNotificationChannels)
          .filter(UserNotificationChannels.user_id == current_user.id).first())
    if not telegram.configured():
        raise HTTPException(status_code=400,
                            detail="Бот не настроен: на сервере нет TELEGRAM_BOT_TOKEN")
    if not ch or not ch.tg_chat_id or not ch.tg_verified_at:
        raise HTTPException(status_code=400,
                            detail="Ваш Telegram не привязан: «Мои настройки» → «Привязать»")

    # Тело — описание события из реестра плюс честная оговорка. Подставлять выдуманные
    # номера сделок нельзя: тест, неотличимый от настоящего алерта, заставит человека
    # искать несуществующую просрочку.
    body = (ev.description or "").strip()
    parts = [ev.title]
    if body:
        parts.append(body)
    tail = "⚙ Это проверка вида уведомления. Настоящее придёт с данными объекта"
    tail += (" и кнопкой «%s»." % ev.action) if ev.action else "."
    parts.append(tail)
    text = "\n\n".join(parts)
    try:
        telegram.send_message(ch.tg_chat_id, text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Не отправилось: {e}")
    log_action(db, current_user, "notify_event_test", "notification", None, event_key)
    return {"ok": True, "text": text}


@router.post("/me/telegram/test")
def tg_test(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Тестовое сообщение себе. Без него настройка канала — гадание."""
    from app.notify import telegram
    ch = (db.query(UserNotificationChannels)
          .filter(UserNotificationChannels.user_id == current_user.id).first())
    if not telegram.configured():
        raise HTTPException(status_code=400, detail="Бот не настроен")
    if not ch or not ch.tg_chat_id or not ch.tg_verified_at:
        raise HTTPException(status_code=400, detail="Telegram не привязан")
    try:
        telegram.send_message(ch.tg_chat_id, "Проверка связи: уведомления настроены верно.")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Не отправилось: {e}")
    return {"ok": True}
