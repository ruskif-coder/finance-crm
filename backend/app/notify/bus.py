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
from datetime import datetime
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from app.models import Notification, User
from app.notify import channels, registry, recipients as rcp
from app.notify import tone as tone_of
from app.notify.models import (NotificationSubscription, NotificationProfile,
                               NotificationDelivery)

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


# Порядок тонов по тяжести. Ухудшение — движение ВЛЕВО по этому списку.


def dedup_key(event_key: str, entity_type: Optional[str], entity_id: Optional[int]) -> str:
    """Ключ схлопывания: событие плюс объект.

    Событие БЕЗ объекта схлопыванию не подлежит — у «конвейер создал сделки» нет одного
    предмета, и склеивать два разных прогона в одну строку значило бы потерять второй.
    """
    if not entity_type or entity_id is None:
        return ""
    return f"{event_key}:{entity_type}:{entity_id}"


def _upsert_app_row(db: Session, uid: int, ev, title: str, body, link,
                    entity_type, entity_id, tone: Optional[str],
                    facts: Optional[list] = None):
    """Строка в панели: обновить существующую или завести новую.

    Повторная сработка сканера НЕ создаёт вторую запись — иначе «сделка стоит 17 дней»
    копится ежедневно, и панель перестают открывать. Существующая обновляется, время
    сдвигается, порядок пересчитывается.

    СНОВА НЕПРОЧИТАННОЙ строка становится только при УХУДШЕНИИ тона. Иначе сканер
    каждые сутки поднимает наверх одно и то же, и метка непрочитанного перестаёт
    что-либо значить — а она единственное, чем человек отмечает разобранное.
    """
    key = dedup_key(ev.key, entity_type, entity_id)
    tone = tone_of.norm(tone or getattr(ev, "tone", None))
    old = None
    if key:
        old = (db.query(Notification)
               .filter(Notification.user_id == uid, Notification.dedup_key == key,
                       Notification.resolved_at.is_(None))
               .order_by(Notification.id.desc()).first())
    if old is None:
        n = Notification(user_id=uid, kind=ev.key, title=title, body=body, link=link,
                         entity_type=entity_type, entity_id=entity_id,
                         dedup_key=key or None, tone=tone,
                         facts=list(facts or []))
        db.add(n)
        return n

    worse = tone_of.worse(tone, old.tone)
    old.title, old.body, old.link, old.tone = title, body, link, tone
    # Факты обновляются вместе с заголовком: просрочка выросла с 6 дней до 9, и плашка
    # обязана сказать «9 дн.», иначе строка спорит сама с собой.
    old.facts = list(facts or [])
    old.created_at = datetime.utcnow()
    if worse:
        old.is_read = False
    return old


def emit(db: Session, event_key: str, *, title: str, body: Optional[str] = None,
         link: Optional[str] = None, entity_type: Optional[str] = None,
         entity_id: Optional[int] = None, actor=None, ctx: Optional[dict] = None,
         user_ids: Optional[Iterable[int]] = None, tone: Optional[str] = None,
         facts: Optional[list] = None, code: Optional[str] = None) -> List[int]:
    """Породить событие. Возвращает id получателей, которым что-то ушло.

    user_ids — явный список получателей в обход резолверов (для случаев, где адресаты
    считаются доменной логикой). Обычный путь — оставить None и описать получателей
    в реестре события.
    """
    ev = registry.get(event_key)
    if ev is None:
        raise ValueError(f"Событие {event_key} не зарегистрировано в реестре")

    ctx = ctx or {}
    facts = list(facts or [])
    if user_ids is None:
        user_ids = rcp.resolve(db, ev.recipients, ctx)

    actor_id = getattr(actor, "id", None)
    targets = [u for u in dict.fromkeys(user_ids) if u and u != actor_id]

    from app.mail import live
    from app.models import User

    delivered: List[int] = []
    for uid in targets:
        chans = _channels_for(db, uid, ev)
        # Слова ПИСЬМА — с правками «Шаблонов писем» (аудит 23.09.2026, 5.M1): здесь у
        # события есть данные для подстановок, дальше они едут в журнале готовыми.
        # Панель и бот говорят словами события: редактор правит письма.
        m_title, m_body = title, body
        if "mail" in chans or "digest" in chans:
            u = db.query(User.name).filter(User.id == uid).first()
            c = live.card(db, "staff", ev.key, {"title": title, "body": body},
                          live.values(db, ctx, u[0] if u else None, link),
                          fields=live.TEXT)
            m_title, m_body = c["title"], c["body"]
        if not chans:
            db.add(NotificationDelivery(body=body, link=link, facts=facts, code=code,
                                        event_key=ev.key, entity_type=entity_type,
                                        entity_id=entity_id, user_id=uid, channel="app",
                                        status="suppressed", suppress_reason="disabled",
                                        title=title))
            continue
        for ch in chans:
            if ch not in LIVE_CHANNELS:
                letter = ch == "digest"
                db.add(NotificationDelivery(body=m_body if letter else body, link=link,
                                            facts=facts, code=code,
                                            event_key=ev.key, entity_type=entity_type,
                                            entity_id=entity_id, user_id=uid, channel=ch,
                                            status="queued",
                                            title=m_title if letter else title))
                continue
            if ch == "mail":
                status, _, reason = channels.deliver_mail(
                    db, uid, ev, m_title, m_body, link, facts, code).partition("|")
                db.add(NotificationDelivery(
                    body=m_body, link=link, facts=facts, code=code,
                    event_key=ev.key, entity_type=entity_type, entity_id=entity_id,
                    user_id=uid, channel="mail", status=status, title=m_title,
                    suppress_reason=(reason or None) if status == "queued" else None,
                    error=(reason or None) if status == "failed" else None))
                if status == "sent" and uid not in delivered:
                    delivered.append(uid)
                continue
            if ch == "tg":
                status, _, reason = channels.deliver_tg(
                    db, uid, ev, title, body, link, entity_type, entity_id,
                    facts).partition("|")
                db.add(NotificationDelivery(
                    body=body, link=link, facts=facts, code=code,
                    event_key=ev.key, entity_type=entity_type, entity_id=entity_id,
                    user_id=uid, channel="tg", status=status, title=title,
                    suppress_reason=(reason or None) if status == "queued" else None,
                    error=(reason or None) if status == "failed" else None))
                if status == "sent" and uid not in delivered:
                    delivered.append(uid)
                continue
            n = _upsert_app_row(db, uid, ev, title, body, link,
                                entity_type, entity_id, tone, facts)
            db.flush()          # нужен n.id для ссылки из журнала отправок
            db.add(NotificationDelivery(body=body, link=link, event_key=ev.key, entity_type=entity_type,
                                        entity_id=entity_id, user_id=uid, channel=ch,
                                        status="sent", title=title, notification_id=n.id))
            if uid not in delivered:
                delivered.append(uid)
    return delivered
