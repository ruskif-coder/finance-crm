# -*- coding: utf-8 -*-
"""Таблицы контура Weborama. Созданы миграцией `2026-09-09_weborama.sql`.

Две штуки и одна колонка — ровно столько, сколько нужно, чтобы повтор стал безопасным:

  · `WeboramaRef` — наши сущности → их идентификаторы. Уникальность
    `(account_id, kind, local_id)` живёт в БАЗЕ, а не в коде: проверка в коде не спасает
    от двух одновременных нажатий, а ограничение спасает. У Weborama идемпотентности нет,
    и второй вставки на площадку нам не откатить — её нельзя ни удалить, ни переименовать.
  · `WeboramaSubmission` — журнал попыток. Строка пишется и коммитится ДО запроса: ответ
    может потеряться по таймауту, и без следа «попытка началась» повтор создаёт дубль.
  · `ad_campaign_placement.weborama_pixel` — сырой пиксель показа (описан в модели РК).

Хешей DSP здесь нет намеренно: они уже живут в `ad_campaign.ms_campaign_xxhash` и
`ad_campaign_creative.ms_creative_xxhash` и уже показываются в кабинете трафика. Второе
хранилище того же факта разошлось бы с первым.
"""
from sqlalchemy import (BigInteger, Column, DateTime, ForeignKey, Integer, String,
                        Text, func)
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base

# Виды сущностей. Строкой, а не перечислением в БД: список меняется вместе с кодом,
# а миграция ради нового вида — цена, которую платить незачем.
KIND_PROJECT = "project"
KIND_CAMPAIGN = "campaign"
KIND_INSERTION = "insertion"
KIND_TAG = "tag"                 # только для журнала: чтение, ничего не создаёт

REF_KINDS = (KIND_PROJECT, KIND_CAMPAIGN, KIND_INSERTION)


class WeboramaRef(Base):
    """Одна наша сущность = одна запись в одном аккаунте WCM.

    `local_id` без внешнего ключа намеренно: указывает в разные таблицы в зависимости от
    `kind` — сделка у проекта, РК у кампании, площадка РК у вставки. Тот же приём, что в
    `OrdSubmission.local_id`.

    `label` хранится не для красоты: переименовать в их кабинете нечем, и имя — часть
    факта. По нему сверяют строку их отчёта с нашей площадкой.
    """
    __tablename__ = "weborama_refs"

    id = Column(Integer, primary_key=True)
    account_id = Column(String(32), nullable=False)
    kind = Column(String(16), nullable=False)
    local_id = Column(Integer, nullable=False)
    wcm_id = Column(String(32), nullable=False)
    label = Column(String(255), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"))


class WeboramaSubmission(Base):
    """Журнал отправок в WCM — одна строка на попытку.

    `finished_at IS NULL` означает «исход неизвестен»: вызов ушёл, ответ не вернулся.
    Такую попытку НЕ повторяют автоматически — объект в чужой системе мог создаться, и
    повтор дал бы второй. Разбирается человеком по их кабинету.
    """
    __tablename__ = "weborama_submissions"

    id = Column(BigInteger, primary_key=True)
    account_id = Column(String(32), nullable=False)
    kind = Column(String(16), nullable=False)
    local_id = Column(Integer)
    method = Column(String(96), nullable=False)
    request = Column(JSONB)
    started_at = Column(DateTime, server_default=func.now(), nullable=False)
    finished_at = Column(DateTime)
    http_status = Column(Integer)
    wcm_id = Column(String(32))
    error = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id"))


__all__ = ["WeboramaRef", "WeboramaSubmission", "REF_KINDS",
           "KIND_PROJECT", "KIND_CAMPAIGN", "KIND_INSERTION", "KIND_TAG"]
