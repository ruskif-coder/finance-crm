"""ORM-зеркало схемы уведомлений (backend/migrations/2026-08-15_notifications.sql).

Существующая модель Notification живёт в app/models.py и НЕ трогается — это конечная
точка канала «в приложении». Здесь — то, что стоит ДО неё: профили, подписки, личные
каналы, состояние алертов, журнал отправок.

Таблицы созданы миграцией; create_all() на старте их не тронет (IF NOT EXISTS по факту
совпадения имён), но модели описаны полностью, чтобы на чистой базе поднялось всё.
"""
from sqlalchemy import (Column, Integer, SmallInteger, String, Boolean, Date, DateTime,
                        ForeignKey, CheckConstraint)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class NotificationProfile(Base):
    """Именованный набор правил. Сознательно НЕ привязан к роли: роль отвечает на вопрос
    «что можно видеть», профиль — «что человека касается»."""
    __tablename__ = "notification_profiles"
    id = Column(Integer, primary_key=True)
    key = Column(String(40), unique=True, nullable=False)
    label = Column(String(120), nullable=False)
    description = Column(String(400))
    is_system = Column(Boolean, nullable=False, default=False)
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))


class NotificationSubscription(Base):
    """Одно событие в одной области видимости. Владелец — ровно одно из profile_id/user_id;
    строка с user_id это личное переопределение поверх профиля.

    params:     пороги правила, напр. {"before_days": 10, "repeat_days": 10}
    recipients: [{"type": "resolver"|"role"|"user", "value": ...}]
    """
    __tablename__ = "notification_subscriptions"
    __table_args__ = (
        CheckConstraint("(profile_id IS NOT NULL AND user_id IS NULL) OR "
                        "(profile_id IS NULL AND user_id IS NOT NULL)",
                        name="notif_sub_owner_ck"),
    )
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("notification_profiles.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    event_key = Column(String(60), nullable=False)   # ключ реестра в коде, FK намеренно нет
    is_enabled = Column(Boolean, nullable=False, default=True)
    ch_app = Column(Boolean, nullable=False, default=True)
    ch_tg = Column(Boolean, nullable=False, default=False)
    ch_mail = Column(Boolean, nullable=False, default=False)
    ch_digest = Column(Boolean, nullable=False, default=False)
    params = Column(JSONB, nullable=False, default=dict)
    recipients = Column(JSONB, nullable=False, default=list)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("users.id"))


class UserNotificationChannels(Base):
    """Личные настройки доставки: привязка Telegram, тихие часы, расписание дайджеста."""
    __tablename__ = "user_notification_channels"
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    tg_chat_id = Column(String(40))
    tg_link_code = Column(String(12))
    tg_link_expires = Column(DateTime)
    tg_verified_at = Column(DateTime)
    mail_override = Column(String(255))
    quiet_from = Column(SmallInteger)
    quiet_to = Column(SmallInteger)
    digest_freq = Column(String(20), default="daily")
    digest_hour = Column(SmallInteger, default=9)
    digest_minute = Column(SmallInteger, default=30)
    mute_until = Column(Date)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class NotificationAlertState(Base):
    """Состояние алерта по объекту. Повтор считается от last_sent_at («прошло не меньше
    N дней»), а НЕ по кратности календарных дат — иначе пропущенный прогон сканера
    означал бы потерянное напоминание."""
    __tablename__ = "notification_alert_state"
    id = Column(Integer, primary_key=True)
    event_key = Column(String(60), nullable=False)
    entity_type = Column(String(40), nullable=False)
    entity_id = Column(Integer, nullable=False)
    stage = Column(String(30))                  # warning | due | overdue
    first_seen_at = Column(DateTime, server_default=func.now())
    last_sent_at = Column(DateTime)
    sent_count = Column(Integer, nullable=False, default=0)
    due_date = Column(Date)
    payload = Column(JSONB, nullable=False, default=dict)
    resolved_at = Column(DateTime)
    resolve_note = Column(String(200))


class NotificationDelivery(Base):
    """Журнал отправок. Он же очередь дайджеста: отложенное лежит статусом 'queued'
    и схлопывается рассылкой — отдельной таблицы для этого не заводим."""
    __tablename__ = "notification_deliveries"
    id = Column(Integer, primary_key=True)
    event_key = Column(String(60), nullable=False)
    entity_type = Column(String(40))
    entity_id = Column(Integer)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    channel = Column(String(20), nullable=False)     # app | tg | mail | digest
    status = Column(String(20), nullable=False)      # sent | failed | suppressed | queued
    suppress_reason = Column(String(40))             # quiet_hours | dedup | disabled | no_channel | muted
    error = Column(String(400))
    title = Column(String(300))
    notification_id = Column(Integer, ForeignKey("notifications.id", ondelete="SET NULL"))
    created_at = Column(DateTime, server_default=func.now())


class NotificationScanRun(Base):
    """Прогон сканера алертов. Без него «алерты не приходят» не отличить от
    «cron вообще не запускался» — а cron падает молча."""
    __tablename__ = "notification_scan_runs"
    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime)
    dry_run = Column(Boolean, nullable=False, default=False)
    rules_run = Column(Integer, nullable=False, default=0)
    matches = Column(Integer, nullable=False, default=0)
    sent = Column(Integer, nullable=False, default=0)
    suppressed = Column(Integer, nullable=False, default=0)
    error = Column(String(600))
