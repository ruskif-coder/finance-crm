"""Модели заявок о сбоях.

Отдельным пакетом, а не в общем `models.py`: тема самостоятельная и к учёту отношения не
имеет — так же вынесены бэклог отладки и уведомления.

ВНИМАНИЕ: таблицы создаёт миграция `backend/migrations/2026-09-17_bug_reports.sql`,
накатывать её ДО выкладки кода — иначе первый же запрос упадёт на отсутствующей таблице.

Разбор зерна и почему это не бэклог отладки — в шапке миграции.
"""
from sqlalchemy import (Column, DateTime, ForeignKey, Integer, String, Text, func)
from sqlalchemy.orm import relationship

from app.database import Base

STAFF, PUB = "staff", "pub"
CONTOURS = (STAFF, PUB)
CONTOUR_LABEL = {STAFF: "сотрудник", PUB: "площадка"}

# Порядок разбора, а не алфавит: новая → в работе → один из трёх исходов.
STATUSES = ["новая", "в работе", "исправлено", "не воспроизводится", "не баг"]
# Исходы, при которых заявка считается разобранной: закрытие требует причины.
CLOSED_STATUSES = {"исправлено", "не воспроизводится", "не баг"}

# Вложения. Пять — не «круглое число»: больше человек и не прикладывает, а форма с
# бесконечной скрепкой приглашает валить туда всё подряд вместо одного точного снимка.
MAX_FILES = 5
MAX_FILE_BYTES = 10 * 1024 * 1024
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp"}
UPLOAD_SUBDIR = "bugs"
# Полгода после закрытия (владелец 17.09.2026) — дальше уборка вместе с общей чисткой
# файлов. Скриншот к закрытой заявке нужен ровно до тех пор, пока спорят о том, что было.
KEEP_DAYS_AFTER_CLOSE = 183


class BugReport(Base):
    __tablename__ = "bug_report"

    id = Column(Integer, primary_key=True, index=True)
    contour = Column(String(8), nullable=False)
    author_user_id = Column(Integer, ForeignKey("users.id"))
    author_account_id = Column(Integer, ForeignKey("cabinet_account.id"))
    # Снимок: учётку отключат, а заявка обязана остаться читаемой.
    author_name = Column(String(160), nullable=False)
    publisher_id = Column(Integer, ForeignKey("sales_publishers.id"))

    page_url = Column(String(500))
    page_title = Column(String(300))
    app_version = Column(String(32))
    user_agent = Column(String(500))
    viewport = Column(String(32))

    comment = Column(Text, nullable=False)
    status = Column(String(24), nullable=False, default="новая")

    created_at = Column(DateTime, server_default=func.now())
    seen_at = Column(DateTime)
    seen_by = Column(Integer, ForeignKey("users.id"))
    resolved_at = Column(DateTime)
    resolved_by = Column(Integer, ForeignKey("users.id"))
    resolution = Column(Text)
    backlog_item_id = Column(Integer, ForeignKey("debug_backlog.id"))

    files = relationship("BugReportFile", back_populates="report",
                         cascade="all, delete-orphan")


class BugReportFile(Base):
    __tablename__ = "bug_report_file"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(Integer, ForeignKey("bug_report.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    rel_path = Column(String(300), nullable=False)
    original_name = Column(String(255))
    content_type = Column(String(100))
    size_bytes = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())

    report = relationship("BugReport", back_populates="files")
