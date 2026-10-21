# -*- coding: utf-8 -*-
"""Жизнь заявки юристу: создать → взять в работу → сделана (с версией шаблона договора) или отклонена (с ответом).

Решения владельца 13–14.10.2026: заявка всегда от конкретного ДС; правка юриста ложится в КАСТОМНЫЙ шаблон ДС договора (текст договора
не трогаем), поэтому этот ДС и все следующие по договору собираются уже с правкой; открытая заявка блокирует выпуск своего ДС.
Ошибки — `LegalError` с текстом для человека; роутер превращает их в 4xx."""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.annex_tpl import service as tpl
from app.annex_tpl.check import zone_at
from app.legal.models import OPEN, LegalRequest


class LegalError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def open_for_annex(db: Session, annex_id: int) -> list:
    return (db.query(LegalRequest).filter(LegalRequest.annex_id == annex_id, LegalRequest.status.in_(OPEN))
            .order_by(LegalRequest.id).all())


def blocking_reason(db: Session, annex_id: int) -> Optional[str]:
    """Текст отказа выпуска, если по ДС есть открытые заявки юристу; иначе None."""
    n = len(open_for_annex(db, annex_id))
    if not n:
        return None
    return f"По приложению открыто заявок юристу: {n}. Выпуск — после ответа юриста (раздел «Юр запросы»)"


def law_block_ids(blocks: list) -> set:
    return {b["id"] for i, b in enumerate(blocks) if not b.get("sys") and zone_at(blocks, i) == "law"}


def create(db: Session, annex, blocks: list, block_id: Optional[str], text: str, user) -> LegalRequest:
    """`blocks` — блоки версии шаблона, по которой собирается ДС: пункт заявки обязан быть из зоны юриста (после таблицы МП)."""
    text = (text or "").strip()
    if not text:
        raise LegalError(400, "Опишите, что поправить: текст заявки пуст")
    # Черновик или подтверждённое, собранное конструктором (пока не ушло в 1С — его и так можно пересоздать). Собранное до конструктора
    # — нет: шаблона, в который легла бы правка, у него нет.
    if annex.no is not None and not (isinstance(annex.blocks, dict) and "blocks" in annex.blocks):
        raise LegalError(409, "Приложение собрано до конструктора — пересоздайте его на новом шаблоне, тогда можно просить юриста")
    if block_id and block_id not in law_block_ids(blocks):
        raise LegalError(400, "Юрист правит только пункты после таблицы медиаплана; пункты до неё аккаунт правит сам")
    r = LegalRequest(annex_id=annex.id, contract_id=annex.contract_id, block_id=block_id or None, text=text,
                     status="открыта", created_by=getattr(user, "id", None), created_at=datetime.utcnow())
    db.add(r)
    return r


def take(r: LegalRequest, user) -> LegalRequest:
    if r.status != "открыта":
        raise LegalError(409, f"Заявка уже «{r.status}»")
    r.status, r.taken_by, r.taken_at = "в работе", getattr(user, "id", None), datetime.utcnow()
    return r


def done(db: Session, r: LegalRequest, user, answer: Optional[str] = None) -> LegalRequest:
    """«Сделана» — только когда юрист сохранил версию кастомного шаблона договора ПОСЛЕ подачи заявки: иначе правки нет нигде,
    а ДС разблокировался бы с прежним текстом."""
    if r.status not in OPEN:
        raise LegalError(409, f"Заявка уже «{r.status}»")
    custom = tpl.custom_of(db, r.contract_id)
    v = tpl.current(db, custom.id) if custom else None
    if not v or (v.created_at and r.created_at and v.created_at < r.created_at):
        raise LegalError(409, "Сначала сохраните правку в шаблоне ДС этого договора (кнопка «Шаблон ДС» в реестре договоров) — "
                              "новой версии после заявки нет")
    now = datetime.utcnow()
    r.status, r.result_version_id, r.answer = "сделана", v.id, (answer or "").strip() or None
    r.closed_by, r.closed_at = getattr(user, "id", None), now
    if not r.taken_at:
        r.taken_by, r.taken_at = r.closed_by, now
    return r


def reject(r: LegalRequest, user, answer: str) -> LegalRequest:
    answer = (answer or "").strip()
    if not answer:
        raise LegalError(400, "Отклоняя заявку, напишите аккаунту почему")
    if r.status not in OPEN:
        raise LegalError(409, f"Заявка уже «{r.status}»")
    r.status, r.answer, r.closed_by, r.closed_at = "отклонена", answer, getattr(user, "id", None), datetime.utcnow()
    return r
