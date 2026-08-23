"""Реестр документов Диадока и связь документ↔операция.

Таблицы создаются миграцией backend/migrations/2026-08-20_diadoc_documents.sql —
create_all() их не заводит сам по себе на пустой базе раньше миграции, порядок
всегда «миграция, потом код».

Реестр отделён от Operation.document_link намеренно: там лежат ссылки на входящие
документы, проставленные вручную, и импорт их не трогает.
"""

from sqlalchemy import (Column, Integer, String, Float, Date, DateTime,
                        ForeignKey, UniqueConstraint, func)
from sqlalchemy.orm import relationship

from app.database import Base


class DiadocDocument(Base):
    __tablename__ = "diadoc_documents"

    id = Column(Integer, primary_key=True, index=True)

    box_id = Column(String, nullable=False)
    letter_id = Column(String, nullable=False)
    # Ключ идемпотентности: повторная загрузка того же файла не плодит дубли.
    document_id = Column(String, nullable=False, unique=True)

    doc_type = Column(String, nullable=False, default="Счет")
    direction = Column(String, nullable=False, default="outgoing")

    number = Column(String)
    number_norm = Column(String)
    doc_date = Column(Date)

    total = Column(Float)
    vat = Column(Float)

    counterparty_inn = Column(String)
    counterparty_kpp = Column(String)
    counterparty_name = Column(String)
    counterparty_id = Column(Integer, ForeignKey("counterparties.id", ondelete="SET NULL"))

    status = Column(String)
    file_name = Column(String)
    link = Column(String)
    comment = Column(String)

    imported_at = Column(DateTime, server_default=func.now())
    imported_by = Column(Integer, ForeignKey("users.id"))

    links = relationship("OperationDocument", back_populates="document",
                         cascade="all, delete-orphan")


class OperationDocument(Base):
    __tablename__ = "operation_documents"
    __table_args__ = (UniqueConstraint("operation_id", "document_id",
                                       name="uq_operation_document"),)

    id = Column(Integer, primary_key=True, index=True)
    operation_id = Column(Integer, ForeignKey("operations.id", ondelete="CASCADE"),
                          nullable=False)
    document_id = Column(Integer, ForeignKey("diadoc_documents.id", ondelete="CASCADE"),
                         nullable=False)

    # number_date | number | amount_window | manual
    match_rule = Column(String, nullable=False, default="manual")
    amount_mismatch = Column(Float)

    matched_by = Column(Integer, ForeignKey("users.id"))
    matched_at = Column(DateTime, server_default=func.now())

    document = relationship("DiadocDocument", back_populates="links")
