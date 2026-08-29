"""ORM-зеркало ОРД (backend/migrations/2026-08-25_ord_mirror_v2.sql).

Своя таблица здесь только у изначальных договоров: это первое звено ЧУЖОЙ цепочки,
про которую мы знаем лишь часть. Юрлица и наши договоры живут в основных справочниках
(`counterparties`, `contracts`) и помечены там колонками `ord_*`.

Стороны изначального договора — атрибуты, а не ссылки: 87 из 91 рекламодателя нам не
контрагенты, счетов мы им не выставляем.

Связь с доходным идёт через идентификатор ОРД, а не через contracts.id: четыре доходных
договора из 52 у нас не заведены, и связь для них теряться не должна.
"""
from sqlalchemy import (Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric,
                        String, Text, UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class OrdInitialContract(Base):
    """Изначальный договор: рекламодатель → исполнитель. Справочник сборки."""
    __tablename__ = "ord_initial_contracts"
    id = Column(Integer, primary_key=True)
    ord_id = Column(String(64), nullable=False, unique=True)
    ord_cid = Column(String(64))
    number = Column(String(128))
    date = Column(Date, nullable=False)
    expiration_date = Column(Date)
    amount = Column(Numeric(18, 2))
    type = Column(String(40))
    subject_type = Column(String(40))
    action_type = Column(String(40))
    is_agent_acting_for_publisher = Column(Boolean)
    advertiser_inn = Column(String(20), index=True)
    advertiser_name = Column(Text)
    contractor_inn = Column(String(20))
    contractor_name = Column(Text)
    status = Column(String(40))
    status_at = Column(DateTime)
    error_text = Column(Text)
    origin = Column(String(8), nullable=False, default="ord")
    # Контур, выдавший идентификатор: demo и prod дают РАЗНЫЕ id, и демовский
    # снаружи неотличим от боевого. См. 2026-08-26_ord_submissions.sql.
    ord_env = Column(String(8))
    synced_at = Column(DateTime)

    final_links = relationship("OrdInitialFinalLink", back_populates="initial_contract",
                               cascade="all, delete-orphan")


class OrdInitialFinalLink(Base):
    """Привязка изначального договора к нашему доходному.

    Один изначальный бывает под несколькими доходными — измерено: 126 договоров
    дают 150 связей.
    """
    __tablename__ = "ord_initial_final_links"
    __table_args__ = (UniqueConstraint("initial_contract_id", "final_ord_id"),)
    id = Column(Integer, primary_key=True)
    initial_contract_id = Column(Integer, ForeignKey("ord_initial_contracts.id",
                                                     ondelete="CASCADE"), nullable=False)
    final_ord_id = Column(String(64), nullable=False, index=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"))
    synced_at = Column(DateTime)

    initial_contract = relationship("OrdInitialContract", back_populates="final_links")


class OrdCreative(Base):
    """Журнал передачи креатива. Мастер — мы, ОРД только регистрирует."""
    __tablename__ = "ord_creatives"
    id = Column(Integer, primary_key=True)
    native_customer_id = Column(String(64), nullable=False, unique=True)
    ord_id = Column(String(64), unique=True)
    erid = Column(String(64))
    status = Column(String(40))
    status_at = Column(DateTime)
    error_text = Column(Text)
    final_ord_id = Column(String(64))
    initial_id = Column(Integer, ForeignKey("ord_initial_contracts.id"))
    creative_set_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    synced_at = Column(DateTime)

class OrdSubmission(Base):
    """Журнал отправок в ОРД — одна строка на попытку.

    Пишется и КОММИТИТСЯ до HTTP-запроса, а не после ответа. Регистрация в ЕРИР
    необратима, а ответ может потеряться по таймауту: без следа «попытка началась»
    повтор создаёт дубль, который уже не отозвать. Незавершённая попытка
    (`finished_at IS NULL`) блокирует повтор, пока человек не сверится с кабинетом.

    `local_id` без внешнего ключа намеренно: указывает в разные таблицы в зависимости
    от `kind`. Тело запроса хранится целиком — отказ ОРД указывает на поле, а собирается
    отправка из десятка мест нашей схемы, и без тела разбирать нечего.

    Таблица создана миграцией backend/migrations/2026-08-26_ord_submissions.sql.
    """
    __tablename__ = "ord_submissions"
    id = Column(Integer, primary_key=True)
    kind = Column(String(32), nullable=False)
    local_id = Column(Integer, nullable=False)
    env = Column(String(8), nullable=False)          # demo | prod
    request = Column(JSONB)
    started_at = Column(DateTime, server_default=func.now(), nullable=False)
    finished_at = Column(DateTime)
    http_status = Column(Integer)
    ord_id = Column(String(64))
    ord_status = Column(String(32))
    error = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id"))


class OrdKktu(Base):
    """Справочник ККТУ, зеркало (backend/migrations/2026-08-27_ord_kktu.sql).

    Единственное зеркало ОРД без колонки `ord_env`: код здесь — сам классификатор,
    внешний по отношению к обоим контурам, а не идентификатор, выданный контуром.
    Обоснование целиком — в шапке миграции.
    """
    __tablename__ = "ord_kktu"
    code = Column(String(32), primary_key=True)
    level = Column(Integer, nullable=False, index=True)
    parent_code = Column(String(32), index=True)
    name = Column(Text, nullable=False)
    synced_at = Column(DateTime)

