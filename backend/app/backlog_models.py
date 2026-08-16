"""Модели бэклога отладки.

Отдельным файлом, а не в общем models.py: тема самостоятельная и к учёту отношения
не имеет — так же, как вынесены модели уведомлений в app/notify/models.py.

ВНИМАНИЕ: таблицы создаются миграцией `backend/migrations/2026-08-16_debug_backlog.sql`,
накатывать её ДО выкладки кода — иначе первый же запрос упадёт на отсутствующей таблице.
"""
from sqlalchemy import (Column, Integer, String, Text, Date, DateTime, ForeignKey,
                        func)
from sqlalchemy.orm import relationship

from app.database import Base

SEVERITIES = ["низкая", "средняя", "высокая"]
STATUSES = ["наблюдаем", "подтвердилось", "закрыто", "не воспроизвелось"]
# Статусы, при которых запись считается снятой с наблюдения: сканер их не трогает.
CLOSED_STATUSES = {"закрыто", "не воспроизвелось"}


class BacklogItem(Base):
    __tablename__ = "debug_backlog"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(300), nullable=False)
    area = Column(String(80))
    context = Column(Text)
    signal_ok = Column(Text)
    # Главное поле записи: через две недели именно оно отвечает на вопрос
    # «а что, собственно, я должен был здесь заметить».
    signal_bad = Column(Text)
    severity = Column(String(20), nullable=False, default="средняя")
    status = Column(String(24), nullable=False, default="наблюдаем")
    watch_until = Column(Date)
    source_link = Column(String(500))
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))
    resolved_at = Column(DateTime)
    resolved_by = Column(Integer, ForeignKey("users.id"))
    resolution = Column(Text)
    overdue_notified_at = Column(DateTime)

    notes = relationship("BacklogNote", back_populates="item",
                         cascade="all, delete-orphan", order_by="BacklogNote.id")


class BacklogNote(Base):
    __tablename__ = "debug_backlog_notes"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("debug_backlog.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id"))
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    item = relationship("BacklogItem", back_populates="notes")
