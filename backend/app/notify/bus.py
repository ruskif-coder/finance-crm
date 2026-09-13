"""emit() — единственная точка входа для событийных уведомлений.

Вызывающий объявляет ТОЛЬКО факт («МП отправлен на согласование») и данные объекта.
Кому слать и в какие каналы — решают реестр (registry.py), подписки в базе и резолверы
(recipients.py). До этого «кому» было зашито прямо в media_plans.py, и любое изменение
политики требовало правки роутера.

Как и notify_many, коммит НЕ делает — коммитит вызывающий, чтобы уведомление и сама
операция ложились одной транзакцией.

Фаза 1: реально доставляется только канал «в приложении» (строка в notifications, как
и раньше). Telegram/почта/дайджест уже проходят через расчёт и пишутся в журнал
отправок статусом queued — их обработчики появятся в фазах 4–5.
"""
import os
from datetime import date, datetime
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from app.models import Notification, User
from app.notify import registry, recipients as rcp
from app.notify.models import (NotificationSubscription, NotificationProfile,
                               NotificationDelivery, UserNotificationChannels)
from app.notify import telegram
from app.mail import client as mail

# Каналы, у которых уже есть обработчик. Остальные копятся в журнале как queued
# и уйдут, когда обработчик появится (фаза 5: почта и дайджест).
# Каналы, которые умеют доставлять ПРЯМО СЕЙЧАС. Остальные (дайджест) ложатся в журнал
# статусом queued и ждут своей отправки — не теряются.
#
# `mail` живой с 13.09.2026. Включение ничего не меняет само по себе: почтовый канал
# выбирается подпиской, а на момент включения его не было включено ни у кого (замер: 0 из
# 33 подписок) — просто потому, что отправлять было нечем.
LIVE_CHANNELS = {"app", "tg", "mail"}


def _effective(db: Session, user_id: int, event_key: str):
    """Действующая настройка события для пользователя.
    Порядок разрешения: личная подписка → подписка его профиля → дефолт реестра."""
    personal = (db.query(NotificationSubscription)
                .filter(NotificationSubscription.user_id == user_id,
                        NotificationSubscription.event_key == event_key).first())
    if personal:
        return personal

    user = db.query(User).filter(User.id == user_id).first()
    profile_id = getattr(user, "notification_profile_id", None) if user else None
    if profile_id is None:
        default = (db.query(NotificationProfile)
                   .filter(NotificationProfile.is_default.is_(True)).first())
        profile_id = default.id if default else None
    if profile_id is not None:
        sub = (db.query(NotificationSubscription)
               .filter(NotificationSubscription.profile_id == profile_id,
                       NotificationSubscription.event_key == event_key).first())
        if sub:
            return sub
    return None


def _channels_for(db: Session, user_id: int, ev: registry.Event) -> List[str]:
    """Список каналов для конкретного получателя. Событие с locked=True нельзя выключить
    совсем — у него всегда остаётся хотя бы «в приложении»."""
    sub = _effective(db, user_id, ev.key)
    if sub is None:
        chans = [c for c in registry.CHANNELS if ev.channels.get(c)]
    elif not sub.is_enabled:
        chans = []
    else:
        flags = {"app": sub.ch_app, "tg": sub.ch_tg, "mail": sub.ch_mail, "digest": sub.ch_digest}
        chans = [c for c in registry.CHANNELS if flags.get(c)]
    if ev.locked and not chans:
        chans = ["app"]
    return chans


def _quiet_now(ch: Optional[UserNotificationChannels], ev: registry.Event) -> bool:
    """Тихие часы и «не беспокоить до». Событие с locked=True проходит сквозь них:
    отказ по сделке и просрочка не ждут утра."""
    if ch is None or ev.locked:
        return False
    today = date.today()
    if ch.mute_until and ch.mute_until >= today:
        return True
    a, b = ch.quiet_from, ch.quiet_to
    if a is None or b is None:
        return False
    h = datetime.now().hour
    return (a <= h < b) if a < b else (h >= a or h < b)   # интервал через полночь


def _deliver_tg(db: Session, uid: int, ev: registry.Event, title: str, body: Optional[str],
                link: Optional[str], entity_type, entity_id) -> str:
    """Отправка в Telegram. Возвращает статус для журнала.
    Ничего не теряем: не настроен бот или не привязан чат — строка ложится в queued."""
    if not telegram.configured():       # проверяем ДО обращения к базе: бот не настроен —
        return "queued|no_channel"      # ходить за привязками незачем
    ch = (db.query(UserNotificationChannels)
          .filter(UserNotificationChannels.user_id == uid).first())
    if ch is None or not ch.tg_chat_id or not ch.tg_verified_at:
        return "queued|no_channel"
    if _quiet_now(ch, ev):
        return "queued|quiet_hours"
    text = title if not body else f"{title}\n{body}"
    try:
        telegram.send_message(ch.tg_chat_id, text, link=link)
        return "sent|"
    except Exception as e:
        return f"failed|{str(e)[:200]}"


def _deliver_mail(db: Session, uid: int, ev: registry.Event, title: str,
                  body: Optional[str], link: Optional[str]) -> str:
    """Отправка письма сотруднику. Возвращает статус для журнала.

    Симметрично телеграму, и по той же причине: ничего не теряем. Почта не настроена,
    у человека нет адреса, тихие часы — строка ложится в `queued` и уходит досылкой,
    а не исчезает.

    Адрес берётся из учётки (`users.email`): в этой системе он же логин, второго
    хранилища адреса сотрудника нет и заводить его незачем.
    """
    if not mail.configured():           # проверяем ДО обращения к базе, как у бота
        return "queued|no_channel"
    u = db.query(User).filter(User.id == uid).first()
    if u is None or not mail.valid_address(u.email or ""):
        return "queued|no_channel"
    ch = (db.query(UserNotificationChannels)
          .filter(UserNotificationChannels.user_id == uid).first())
    if _quiet_now(ch, ev):
        return "queued|quiet_hours"
    text = title if not body else title + "\n\n" + body
    if link:
        # Ссылку даём абсолютной: в письме относительный адрес никуда не ведёт, а
        # открывают письмо не в нашей вкладке.
        base = (os.getenv("DOMAIN") or "").strip()
        text += "\n\n" + (("https://" + base) if base else "") + link
    try:
        mail.send(to=u.email, subject=title[:200], body=text,
                  to_name=getattr(u, "name", None))
        return "sent|"
    except mail.MailNotConfigured:
        return "queued|no_channel"
    except Exception as e:              # noqa: BLE001 — в журнал уходит любая причина
        return f"failed|{str(e)[:200]}"


def emit(db: Session, event_key: str, *, title: str, body: Optional[str] = None,
         link: Optional[str] = None, entity_type: Optional[str] = None,
         entity_id: Optional[int] = None, actor=None, ctx: Optional[dict] = None,
         user_ids: Optional[Iterable[int]] = None) -> List[int]:
    """Породить событие. Возвращает id получателей, которым что-то ушло.

    user_ids — явный список получателей в обход резолверов (для случаев, где адресаты
    считаются доменной логикой). Обычный путь — оставить None и описать получателей
    в реестре события.
    """
    ev = registry.get(event_key)
    if ev is None:
        raise ValueError(f"Событие {event_key} не зарегистрировано в реестре")

    ctx = ctx or {}
    if user_ids is None:
        user_ids = rcp.resolve(db, ev.recipients, ctx)

    actor_id = getattr(actor, "id", None)
    targets = [u for u in dict.fromkeys(user_ids) if u and u != actor_id]

    delivered: List[int] = []
    for uid in targets:
        chans = _channels_for(db, uid, ev)
        if not chans:
            db.add(NotificationDelivery(event_key=ev.key, entity_type=entity_type,
                                        entity_id=entity_id, user_id=uid, channel="app",
                                        status="suppressed", suppress_reason="disabled",
                                        title=title))
            continue
        for ch in chans:
            if ch not in LIVE_CHANNELS:
                db.add(NotificationDelivery(event_key=ev.key, entity_type=entity_type,
                                            entity_id=entity_id, user_id=uid, channel=ch,
                                            status="queued", title=title))
                continue
            if ch == "mail":
                status, _, reason = _deliver_mail(db, uid, ev, title, body,
                                                  link).partition("|")
                db.add(NotificationDelivery(
                    event_key=ev.key, entity_type=entity_type, entity_id=entity_id,
                    user_id=uid, channel="mail", status=status, title=title,
                    suppress_reason=(reason or None) if status == "queued" else None,
                    error=(reason or None) if status == "failed" else None))
                if status == "sent" and uid not in delivered:
                    delivered.append(uid)
                continue
            if ch == "tg":
                status, _, reason = _deliver_tg(db, uid, ev, title, body, link,
                                                entity_type, entity_id).partition("|")
                db.add(NotificationDelivery(
                    event_key=ev.key, entity_type=entity_type, entity_id=entity_id,
                    user_id=uid, channel="tg", status=status, title=title,
                    suppress_reason=(reason or None) if status == "queued" else None,
                    error=(reason or None) if status == "failed" else None))
                if status == "sent" and uid not in delivered:
                    delivered.append(uid)
                continue
            n = Notification(user_id=uid, kind=ev.key, title=title, body=body, link=link,
                             entity_type=entity_type, entity_id=entity_id)
            db.add(n)
            db.flush()          # нужен n.id для ссылки из журнала отправок
            db.add(NotificationDelivery(event_key=ev.key, entity_type=entity_type,
                                        entity_id=entity_id, user_id=uid, channel=ch,
                                        status="sent", title=title, notification_id=n.id))
            if uid not in delivered:
                delivered.append(uid)
    return delivered
