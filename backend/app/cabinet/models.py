"""Кабинеты паблишеров и учётки — со стороны ЯДРА. Мастер данных здесь.

Три уровня, и они не взаимозаменяемы:

  · **кабинет** — организация: сеть аптек или одиночная площадка. К нему прикрепляются
    площадки и люди;
  · **площадка** живёт ровно в ОДНОМ кабинете. Иначе задание появилось бы у двоих, оба
    бы ответили, и второй получил бы «вердикт уже выставлен» — со стороны это выглядит
    поломкой, а не правилом;
  · **учётка** растёт из КОНТАКТА площадки. Люди со стороны площадки уже заведены
    (`sales_publisher_contacts`), и вторая запись об одном человеке означает две точки
    правки, из которых одна обязательно останется старой.

Видимость считается от кабинета: добавили площадку — её увидели все его люди сразу.

Таблицы созданы миграциями 2026-08-28_publisher_cabinet.sql,
2026-08-28_cabinet_org.sql и 2026-08-30_cabinet_log_and_our_contacts.sql.
"""
from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, Text,
                        UniqueConstraint)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

CABINET_KINDS = ('площадка', 'служебный')
CABINET_STATES = ('черновик', 'активен', 'приостановлен')


class Cabinet(Base):
    """Организация внешнего контура.

    `kind='служебный'` — НАШ кабинет: видит все площадки и связей не хранит. Отдельный
    вид, а не «кабинет со всеми площадками в связке»: связка со всеми заняла бы каждую
    площадку, и настоящие кабинеты собрать стало бы нельзя.

    `state` относится к кабинету ЦЕЛИКОМ. Отключать по одному человеку — способ забыть
    третьего; `черновик` означает «площадки прикрепили, людей ещё нет», и вход в таком
    кабинете невозможен.
    """
    __tablename__ = "cabinet"
    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)
    kind = Column(Text, nullable=False, default='площадка', server_default='площадка')
    state = Column(Text, nullable=False, default='черновик', server_default='черновик')
    manager_id = Column(Integer, ForeignKey("sales_reps.id"))
    note = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime)

    publishers = relationship("CabinetPublisher", back_populates="cabinet",
                              cascade="all, delete-orphan")
    accounts = relationship("CabinetAccount", back_populates="cabinet")


class CabinetPublisher(Base):
    """Площадка кабинета. Ключ по ПЛОЩАДКЕ, а не по паре — она живёт в одном кабинете."""
    __tablename__ = "cabinet_publisher"
    publisher_id = Column(Integer, ForeignKey("sales_publishers.id", ondelete="RESTRICT"),
                          primary_key=True)
    cabinet_id = Column(Integer, ForeignKey("cabinet.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    added_at = Column(DateTime, server_default=func.now())

    cabinet = relationship("Cabinet", back_populates="publishers")


class CabinetAccount(Base):
    """Учётка внешнего лица. Принадлежит кабинету, растёт из контакта площадки.

    `hashed_password IS NULL` — доступ заведён, пароль ещё не выдан. Это НЕ то же, что
    `is_active = false`: первое ждёт нашего действия, второе — решение админа, и путать
    их нельзя, иначе «почему он не может войти» становится неотвечаемым вопросом.

    `can_approve` — роль внутри кабинета. Технический специалист смотрит баннер,
    коммерческий отвечает за размещение; без разделения любой заведённый человек
    закрывает пару и запускает выпуск ЕРИД.
    """
    __tablename__ = "cabinet_account"
    id = Column(Integer, primary_key=True)
    cabinet_id = Column(Integer, ForeignKey("cabinet.id"))
    contact_id = Column(Integer, ForeignKey("sales_publisher_contacts.id",
                                            ondelete="SET NULL"))
    email = Column(Text, nullable=False, unique=True)
    name = Column(Text, nullable=False)
    hashed_password = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True, server_default='true')
    can_approve = Column(Boolean, nullable=False, default=True, server_default='true')
    created_at = Column(DateTime, server_default=func.now())
    last_login_at = Column(DateTime)

    cabinet = relationship("Cabinet", back_populates="accounts")


class CabinetAccountPublisher(Base):
    """ЗАМОРОЖЕНО 28.08.2026. Прямая связь «человек ↔ площадка» до появления кабинета.

    Не удалена по правилу проекта (устаревшее замораживается, а не дропается), но не
    читается: видимость считается от кабинета. Два ответа на вопрос «чьи это площадки»
    однажды разошлись бы — и разошлись бы молча.
    """
    __tablename__ = "cabinet_account_publisher"
    __table_args__ = (UniqueConstraint("account_id", "publisher_id",
                                       name="cabinet_account_publisher_pkey"),)
    account_id = Column(Integer, ForeignKey("cabinet_account.id", ondelete="CASCADE"),
                        primary_key=True)
    publisher_id = Column(Integer, ForeignKey("sales_publishers.id", ondelete="RESTRICT"),
                          primary_key=True)
    added_at = Column(DateTime, server_default=func.now())


# Тон строки журнала — он же цвет квадратного маркера в ленте. Словарь в КОДЕ, как
# `CABINET_STATES` рядом и как виды уведомлений: набор меняется вместе с экранами.
LOG_TONES = ('info', 'ok', 'warn', 'bad')
# Чья сторона совершила действие. Лента одна на оба контура, и площадка должна отличать
# своё («согласован креатив») от нашего («выдан пароль»).
LOG_SIDES = ('площадка', 'мы')


class CabinetLog(Base):
    """Журнал действий кабинета. Два читателя, и от этого всё остальное.

    Смотрят его администратор на экране «Кабинеты паблишеров» и САМА ПЛОЩАДКА у себя в
    кабинете. Поэтому скрытых строк здесь нет: флаг видимости однажды забудут проставить,
    и внутреннее уедет наружу. Вместо флага правило — в `subject` не попадает ничего,
    чего площадке видеть нельзя.

    Отдельная таблица, а не `audit_log`: внешние действия не смешиваются с внутренними, и
    лента для площадки не собирается фильтром по чужому журналу. До 30.08.2026 кабинет не
    писал вообще никуда — ни одного вызова `log_action` в шлюзе.
    """
    __tablename__ = "cabinet_log"
    id = Column(Integer, primary_key=True)
    cabinet_id = Column(Integer, ForeignKey("cabinet.id", ondelete="CASCADE"),
                        nullable=False)
    publisher_id = Column(Integer, ForeignKey("sales_publishers.id", ondelete="SET NULL"))
    account_id = Column(Integer, ForeignKey("cabinet_account.id", ondelete="SET NULL"))
    # Имя строкой, а не только ссылкой: учётку отключают, человек уходит — журнал обязан
    # остаться читаемым.
    actor_name = Column(Text, nullable=False)
    actor_side = Column(Text, nullable=False)
    action = Column(Text, nullable=False)
    tone = Column(Text, nullable=False)
    subject = Column(Text)
    entity_type = Column(Text)
    entity_id = Column(Integer)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class CabinetOurContact(Base):
    """Кого из НАШИХ видит площадка. Общие для всех кабинетов.

    `cabinet_id` здесь нет намеренно — это и есть «показываются всем» (владелец,
    30.08.2026). Ссылка на `sales_reps`, а не строка в `company_settings`: контакт видит
    внешняя сторона, и повисший id показался бы ей пустой строкой вместо человека.

    Почта берётся через `sales_reps.user_id → users.email`, поэтому сотрудник без учётки
    в системе показывается без способа связаться — в выборе такие помечаются.
    """
    __tablename__ = "cabinet_our_contact"
    id = Column(Integer, primary_key=True)
    role = Column(Text, nullable=False)
    rep_id = Column(Integer, ForeignKey("sales_reps.id"), nullable=False, unique=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default='0')
    # Скрыть, не удаляя: роль временно не показываем, связь при этом не теряется.
    is_shown = Column(Boolean, nullable=False, default=True, server_default='true')
