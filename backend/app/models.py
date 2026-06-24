from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False)
    label = Column(String, nullable=False)
    is_system = Column(Integer, default=0)  # 1 — системная роль (admin/manager/viewer), нельзя изменить/удалить
    created_at = Column(DateTime, server_default=func.now())
    permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")

class RolePermission(Base):
    __tablename__ = "role_permissions"
    id = Column(Integer, primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    section = Column(String, nullable=False)  # dashboard / pl / balance / planfact / operations / import / settings_balances
    can_view = Column(Integer, default=0)
    can_create = Column(Integer, default=0)
    can_edit = Column(Integer, default=0)
    can_delete = Column(Integer, default=0)
    role = relationship("Role", back_populates="permissions")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    role = relationship("Role")

class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user_name = Column(String)  # денормализовано — видно даже если пользователя удалят/деактивируют
    action = Column(String, nullable=False)  # login_success / login_failed / create_user / update_user / create_operation / ...
    entity_type = Column(String, nullable=True)  # user / operation / ...
    entity_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class Article(Base):
    __tablename__ = "articles"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    group = Column(String)
    subgroup = Column(String)
    type = Column(String)  # income / expense
    sort_order = Column(Integer, default=0)  # порядок вывода в справочнике статей и в выпадающих списках
    operations = relationship("Operation", back_populates="article")

class Counterparty(Base):
    __tablename__ = "counterparties"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    vat_rate = Column(Float, default=0)
    inn = Column(String, nullable=True)
    status = Column(String, nullable=False, default="действующий")  # действующий / виртуальный — скрытый параметр, пока без отображения в UI
    group_override = Column(String, nullable=True)  # ручная "Группа" в реестре — приоритетнее авто-вычисленной самой частой статьи
    contract_number = Column(String, nullable=True)  # № договора
    contract_date = Column(Date, nullable=True)  # дата договора
    note = Column(Text, nullable=True)  # примечание (например, по дебиторке) — свободный текст
    operations = relationship("Operation", back_populates="counterparty")

class Operation(Base):
    __tablename__ = "operations"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    status = Column(String, nullable=False)  # оплачено / план оплат / план поступлений
    income = Column(Float, default=0)
    expense = Column(Float, default=0)
    bank = Column(String)
    period = Column(String)
    vat_rate = Column(Float, default=0)
    vat_fact = Column(Float, default=0)
    article_id = Column(Integer, ForeignKey("articles.id"))
    counterparty_id = Column(Integer, ForeignKey("counterparties.id"))
    ds_num = Column(String)
    invoice = Column(String)
    invoice_date = Column(Date)
    description = Column(String)
    document_link = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))
    article = relationship("Article", back_populates="operations")
    counterparty = relationship("Counterparty", back_populates="operations")