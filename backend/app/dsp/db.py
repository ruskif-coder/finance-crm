"""Второе подключение бэкенда — аналитическая база DSP (контур «DSP-коннектор»).

Отдельный контейнер `finance_dsp_db` (TimescaleDB на pg16), своя база `dsp_analytics`:
сырьё stat-API DSP (`dsp_stat_raw` → continuous aggregate `dsp_stat_daily`),
журнал отправок (`dsp_send_log`), курсоры выкачки (`dsp_sync_cursor`). В основную базу
контур отдаёт ТОЛЬКО суточный срез — апсертом в `ad_campaign_stat`.

Схема живёт в `migrations/dsp/2026-09-02_dsp_analytics.sql` и накатывается в dsp_analytics
руками: hypertable/continuous aggregate — DDL Timescale, ORM их не описывает, create_all
здесь НЕ вызывается.

Подключение ленивое: без `DSP_DATABASE_URL` бэкенд поднимается как раньше (дашборд читает
только основную базу), а первое обращение к аналит. базе даёт понятную ошибку.
"""
import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DSP_DATABASE_URL = os.getenv("DSP_DATABASE_URL")

# Таймаут соединения — не украшение: журнал этой базы читает дашборд трафика на каждой
# загрузке (зависшие попытки DSP), и недоступный хост без таймаута подвешивал бы экран
# на TCP-соединении вместо «нет данных» (ревью 23.09.2026).
_engine = (create_engine(DSP_DATABASE_URL, pool_pre_ping=True, future=True,
                         connect_args={"connect_timeout": 3})
           if DSP_DATABASE_URL else None)
DspSessionLocal = (sessionmaker(bind=_engine, autoflush=False, autocommit=False)
                   if _engine else None)


def dsp_engine():
    if _engine is None:
        raise RuntimeError("DSP_DATABASE_URL не задан — аналитическая база DSP не подключена")
    return _engine


def get_dsp_db():
    """FastAPI-зависимость на сессию аналитической базы."""
    if DspSessionLocal is None:
        raise RuntimeError("DSP_DATABASE_URL не задан — аналитическая база DSP не подключена")
    db = DspSessionLocal()
    try:
        yield db
    finally:
        db.close()


def dsp_ping() -> dict:
    """Проверка живости: версия Timescale и наличие наших объектов. Для смоука/диагностики."""
    with dsp_engine().connect() as c:
        ver = c.execute(text(
            "SELECT extversion FROM pg_extension WHERE extname='timescaledb'")).scalar()
        hyper = c.execute(text(
            "SELECT count(*) FROM timescaledb_information.hypertables "
            "WHERE hypertable_name='dsp_stat_raw'")).scalar()
        cagg = c.execute(text(
            "SELECT count(*) FROM timescaledb_information.continuous_aggregates "
            "WHERE view_name='dsp_stat_daily'")).scalar()
        return {"timescaledb": ver, "hypertable_dsp_stat_raw": bool(hyper),
                "cagg_dsp_stat_daily": bool(cagg)}
