"""Подключение к основной базе.

Пул задан ЯВНО, а не умолчаниями SQLAlchemy — и это не украшение. Настоящий потолок
одновременной работы в системе задаёт не число процессов, а число соединений: из 791
эндпоинта 772 объявлены обычным `def`, а такие FastAPI исполняет в пуле потоков (по
умолчанию сорок). То есть сорок запросов могут идти параллельно, а соединений при
умолчаниях было пять плюс десять — и лишние ждали в очереди молча, выглядя как
«сервер тормозит» (разбор внешнего аудита 11.09.2026, F4-11).

Арифметика, по которой выбраны числа: `pool_size + max_overflow` на КАЖДЫЙ процесс
бэкенда не должно превышать `max_connections` базы за вычетом места для кабинета,
служебных подключений и `psql` руками. Замер 11.09.2026: `max_connections = 100`,
занято обычно 4.

`pool_pre_ping` — проверка живости соединения перед выдачей. Без него первый запрос
после ночного простоя (или после `docker restart finance_db`) падал бы на разорванном
соединении. У аналитической базы DSP он стоял с самого начала, у основной — нет.

`pool_recycle` меньше любого разумного таймаута на стороне сервера и прокси: соединение,
которое база уже закрыла, а мы ещё держим, даёт ту же ошибку на ровном месте.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required — check .env")

engine = create_engine(
    DATABASE_URL,
    pool_size=20,          # постоянные соединения
    max_overflow=20,       # временные под всплеск; 20 + 20 < 100 с большим запасом
    pool_timeout=10,       # сколько ждать свободного, прежде чем честно отказать
    pool_recycle=1800,     # 30 мин: переоткрываем до того, как закроет та сторона
    pool_pre_ping=True,
    future=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
