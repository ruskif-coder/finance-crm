"""Система уведомлений: реестр событий, резолверы получателей, emit().

Схема: backend/migrations/2026-08-15_notifications.sql
Макет интерфейса: docs/mockup_notifications.html
"""
from app.notify.bus import emit           # noqa: F401
from app.notify import registry           # noqa: F401
