# -*- coding: utf-8 -*-
"""Таблицы почтового гейта. Создаются миграцией `2026-09-13_mail.sql`.

Две сущности, и путать их нельзя: **шаблон** — то, что правят люди, **журнал** — то, что
случилось. В журнал ложится ИТОГОВЫЙ текст письма, а не ссылка на шаблон: поправленная
формулировка не должна менять того, что уже ушло площадке.
"""
from sqlalchemy import (BigInteger, Boolean, Column, DateTime, ForeignKey, Integer,
                        String, Text)
from sqlalchemy.sql import func

from app.database import Base

# Виды писем. Список здесь, а не строками по коду: он же в фильтре журнала и в подписях.
KIND_NOTIFY = "notify"            # уведомление сотруднику
KIND_URL_REQUEST = "url_request"  # запрос посадочной ссылки у площадки
KIND_TEST = "test"                # проверочное письмо себе
KINDS = (KIND_NOTIFY, KIND_URL_REQUEST, KIND_TEST)

KIND_LABELS = {
    KIND_NOTIFY: "Уведомление",
    KIND_URL_REQUEST: "Запрос посадочной",
    KIND_TEST: "Проверка",
}

STATUSES = ("queued", "sent", "failed")


class MailTemplate(Base):
    """Шаблон письма. Правится на экране, а не выкладкой.

    `key` НЕИЗМЕНЯЕМ — по нему код находит текст. Переименование означает, что отправка
    перестанет находить шаблон, и узнаем мы об этом от площадки, а не от системы. Та же
    причина, по которой неизменяем ключ права.
    """
    __tablename__ = "mail_templates"

    id = Column(Integer, primary_key=True)
    key = Column(String(64), nullable=False, unique=True)
    title = Column(String(255), nullable=False)
    subject = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    updated_at = Column(DateTime)
    updated_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class MailLog(Base):
    """Журнал писем НАРУЖУ.

    Внутренние уведомления сотрудникам живут в `notification_deliveries`: там получатель
    всегда наш пользователь, и заводить ему строку с адресом незачем. Здесь адресат вне
    системы — площадка, паблишер, контрагент, — и цена ошибки другая.
    """
    __tablename__ = "mail_log"

    id = Column(BigInteger, primary_key=True)
    to_email = Column(String(320), nullable=False)
    to_name = Column(String(255))
    reply_to = Column(String(320))
    subject = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    kind = Column(String(32), nullable=False)
    # Без внешнего ключа намеренно: указывает в разные таблицы в зависимости от вида —
    # как `ord_submissions.local_id` и `weborama_refs.local_id`.
    entity_type = Column(String(32))
    entity_id = Column(Integer)
    user_id = Column(Integer, ForeignKey("users.id"))
    # Тихие часы площадки: письмо ждёт своего часа в журнале, а не теряется и не
    # будит ночью (миграция 2026-09-14_mail_send_after.sql). NULL — сразу.
    send_after = Column(DateTime)
    # Разметка на момент составления (миграция 2026-09-14_mail_log_html.sql).
    # Нужна ДОСЫЛКЕ: собрать её заново нечем — тона, тега, фактов и контекста в
    # журнале нет, — а пересчитанная по сегодняшнему состоянию она спорила бы с
    # текстом, с которым приехала.
    html = Column(Text)
    status = Column(String(16), nullable=False, default="queued", server_default="queued")
    error = Column(Text)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    # Message-ID письма: по нему в почтовом ящике находят ответ на конкретную отправку.
    message_id = Column(String(255))
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    sent_at = Column(DateTime)
