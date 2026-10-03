# -*- coding: utf-8 -*-
"""Чтение журнала обмена с DSP (`dsp_send_log`, аналитическая база) — одна точка.

Пишет журнал клиент (`client.MsClient`, токены вырезаются при записи). Читают его демо-
экран, вкладка «Логи» и «Статус системы»; до 02.10.2026 каждый — своим SQL со своим
условием по контуру (аудит интеграций). Ошибку доступа к базе функции не глотают:
что показать при недоступном журнале, решает экран.
"""
from typing import Optional

from sqlalchemy import text

from app.dsp.client import DEMO, PROD


def _engine(engine=None):
    if engine is None:
        from app.dsp.db import dsp_engine
        engine = dsp_engine()
    return engine


def rows(limit: Optional[int] = 200, contour: Optional[str] = PROD, only_errors: bool = False,
         full: bool = True, engine=None) -> list:
    """Строки журнала, новые сверху. `contour=None` — оба контура; `limit=None` — все;
    `full` — с телами запроса и ответа."""
    cols = ("id, ts, method, entity_type, local_ref, ms_xxhash, ok, error, contour"
            + (", request, response" if full else ""))
    with _engine(engine).connect() as c:
        return [dict(r) for r in c.execute(text(
            f"SELECT {cols} FROM dsp_send_log WHERE true "
            + ("AND contour = :contour " if contour else "")
            + ("AND ok IS NOT TRUE " if only_errors else "")
            + "ORDER BY id DESC LIMIT :n"),
            {"n": limit, "contour": contour}).mappings().all()]


def last(contour: str = PROD, engine=None):
    """Последняя отправка контура: (ts, ok, error) или None."""
    with _engine(engine).connect() as c:
        return c.execute(text(
            "SELECT ts, ok, error FROM dsp_send_log "
            "WHERE contour = :contour ORDER BY ts DESC LIMIT 1"), {"contour": contour}).first()


def demo_created(xxhash: str, engine=None) -> bool:
    """Заводил ли этот объект демо-экран (контур demo)."""
    with _engine(engine).connect() as c:
        return c.execute(text(
            "SELECT 1 FROM dsp_send_log WHERE contour = :contour "
            "AND upper(ms_xxhash) = upper(:h) LIMIT 1"), {"h": xxhash, "contour": DEMO}).first() is not None
