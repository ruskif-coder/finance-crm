from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from app.database import Base

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False)
    label = Column(String, nullable=False)
    is_system = Column(Integer, default=0)  # 1 — системная роль (admin/manager/viewer), нельзя изменить/удалить
    created_at = Column(DateTime, server_default=func.now())
    # Рабочая группа роли (для конструктора МП): 'seller' / 'account' / 'traffic' / None.
    # Пользователи наследуют её через свою роль — это классификация «кто продавец/аккаунт»,
    # отдельная от прав доступа. is_master — «мастер группы» (помечается ★ в пикерах МП).
    staff_group = Column(String)
    is_master = Column(Boolean, nullable=False, default=False)
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
    can_view_operations = Column(Integer, default=0)  # counterparties: показывать операции в карточке
    # Видимость сделок: 'all' — все, 'own' — только свои (где пользователь сейлз/аккаунт
    # через SalesRep.user_id). Осмысленно для секции sales_dashboard.
    deals_scope = Column(String, default="all")
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
    consent_accepted_at = Column(DateTime, nullable=True)  # 152-ФЗ: момент принятия согласия на обработку ПДн
    bitrix_user_id = Column(String, nullable=True)  # привязка к сотруднику в Битрикс24 (ручной выбор в настройках)
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

class ArticleGroup(Base):
    __tablename__ = "article_groups"
    # Справочник групп статей верхнего уровня. Группа у статьи (Article.group) хранится как строка
    # (денормализовано, чтобы reports.py читал её напрямую), а эта таблица — канонический список
    # допустимых имён групп для строгого выпадающего списка и для пустых, ещё не заполненных групп.
    # Сидируется из существующих Article.group при старте (seed_article_groups в main.py).
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    sort_order = Column(Integer, default=0)

class Counterparty(Base):
    __tablename__ = "counterparties"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    vat_rate = Column(Float, default=0)  # УСТАРЕЛО (2026-07-16): одна ставка на контрагента не покрывает случай
    # «по доходным НДС 22%, по расходным (премии за объём) 0%» — см. vat_rate_income/vat_rate_expense ниже.
    # Колонка не удалена (см. CLAUDE.md про осторожность с деструктивными изменениями), но больше
    # не читается/не пишется через API/UI — оставлена для истории.
    # НДС и статья по умолчанию раздельно по направлениям (2026-07-16, add_vat_article_defaults.sql).
    # NULL = не задано (автоподстановка в форме операций просто не сработает). Заполняются бэкфиллом
    # backfill_vat_articles.py (НДС — из самой свежей операции направления, чтобы не тянуть ставку 20%
    # из эпохи до перехода 20→22%; статья — самая частая) и далее редактируются в карточке контрагента.
    vat_rate_income = Column(Float, nullable=True)
    vat_rate_expense = Column(Float, nullable=True)
    default_article_income_id = Column(Integer, ForeignKey("articles.id"), nullable=True)
    default_article_expense_id = Column(Integer, ForeignKey("articles.id"), nullable=True)
    inn = Column(String, nullable=True)
    kpp = Column(String, nullable=True)
    ogrn = Column(String, nullable=True)
    okpo = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    edo_id = Column(String, nullable=True)
    director_name = Column(String, nullable=True)
    website = Column(String, nullable=True)
    address_fact = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="действующий")  # действующий / виртуальный — скрытый параметр, пока без отображения в UI
    group_override = Column(String, nullable=True)  # ручная "Группа" в реестре — приоритетнее авто-вычисленной самой частой статьи
    contract_number = Column(String, nullable=True)  # УСТАРЕЛО: дублировало 1:N таблицу Contract под видом 1:1 поля. Заменено
    # привязкой Contract.counterparty_id (см. ниже) + Counterparty.contracts. Колонка не удалена и не трогается существующими
    # значениями (см. CLAUDE.md про осторожность с деструктивными изменениями), но больше не читается/не пишется через
    # API/UI (routers/counterparties.py, directories.js) — оставлена для истории.
    contract_date = Column(Date, nullable=True)  # УСТАРЕЛО — см. комментарий к contract_number выше.
    note = Column(Text, nullable=True)  # примечание (например, по дебиторке) — свободный текст
    term_days = Column(Integer, nullable=True)  # отсрочка платежа в днях; NULL = берётся DEFAULT_TERM_DAYS (см. reports.py)
    is_own_company = Column(Boolean, default=False, nullable=False)  # наше юрлицо — используется как плательщик/получатель
    operations = relationship("Operation", back_populates="counterparty",
                             foreign_keys="Operation.counterparty_id")
    contracts = relationship("Contract", back_populates="counterparty",
                             foreign_keys="Contract.counterparty_id")
    own_contracts = relationship("Contract", back_populates="own_company",
                                 foreign_keys="Contract.own_company_id")
    bank_accounts = relationship("CounterpartyBankAccount", back_populates="counterparty",
                                 cascade="all, delete-orphan", order_by="CounterpartyBankAccount.sort_order")


class CounterpartyBankAccount(Base):
    __tablename__ = "counterparty_bank_accounts"
    id = Column(Integer, primary_key=True)
    counterparty_id = Column(Integer, ForeignKey("counterparties.id"), nullable=False)
    bank_name = Column(String, nullable=True)   # краткое наименование банка (ПолучательБанк1)
    bank_city = Column(String, nullable=True)   # город банка (ПолучательБанк2)
    rs = Column(String, nullable=True)          # расчётный счёт (ПолучательСчет)
    ks = Column(String, nullable=True)          # корреспондентский счёт (ПолучательКорсчет)
    bik = Column(String, nullable=True)         # БИК банка (ПолучательБИК)
    sort_order = Column(Integer, default=0)
    counterparty = relationship("Counterparty", back_populates="bank_accounts")

class Contract(Base):
    __tablename__ = "contracts"
    id = Column(Integer, primary_key=True)
    contract_number = Column(String, nullable=True)  # № договора — в файле встречаются и строки, и числа, храним как текст
    contract_date = Column(Date, nullable=True)  # дата договора
    inn = Column(String, nullable=True)
    counterparty_name = Column(String, nullable=True)  # ООО КОНТРАГЕНТ — текстовое поле. Раньше это был единственный способ
    # связать договор с контрагентом (без FK). Теперь это денормализованный снимок, синхронизируемый с Counterparty.name
    # на сервере при наличии counterparty_id (см. routers/contracts.py) — не редактируется напрямую для привязанных строк.
    # Для строк без привязки (counterparty_id is NULL, не успели сопоставить — см. link_contracts_to_counterparties.py)
    # остаётся обычным свободным текстом, как раньше.
    counterparty_id = Column(Integer, ForeignKey("counterparties.id"), nullable=True)  # FK на единый реестр контрагентов
    # ("единый источник данных для всех полей контрагент в системе" — см. CLAUDE.md). NULL = историческая строка, ещё не
    # сопоставленная с реестром (см. link_contracts_to_counterparties.py); обязателен при создании НОВОГО договора
    # (проверяется в create_contract, не на уровне Pydantic-модели, т.к. она общая с update_contract).
    own_company_id = Column(Integer, ForeignKey("counterparties.id"), nullable=True)  # наше юрлицо — сторона договора
    counterparty = relationship("Counterparty", back_populates="contracts",
                                foreign_keys=[counterparty_id])
    own_company   = relationship("Counterparty", back_populates="own_contracts",
                                 foreign_keys=[own_company_id])
    marketing_name = Column(String, nullable=True)  # НАЗВАНИЕ МАРКЕТИНГОВОЕ
    cooperation_format = Column(String, nullable=True)  # ФОРМАТ СОТРУДНИЧЕСТВА
    services = Column(Text, nullable=True)  # УСЛУГИ
    end_date_text = Column(String, nullable=True)  # ДАТА ОКОНЧАНИЯ ДОГОВОРА — текст, формат в исходнике непостоянный
    prolongation = Column(String, nullable=True)  # ПРОЛОНГАЦИЯ — свободный текст в БД, фронт ограничивает списком (PROLONGATION_OPTIONS в settings.js)
    payment_form = Column(String, nullable=True)  # ФОРМА ОПЛАТЫ
    payment_term = Column(String, nullable=True)  # УСТАРЕЛО: старое текстовое "срок оплаты". Заменено на payment_term_days/payment_term_condition (см. migrate_payment_term.py). Колонка не удалена (см. CLAUDE.md про осторожность с деструктивными изменениями) и не используется в API/UI — оставлена для истории.
    payment_term_days = Column(Integer, nullable=True)  # срок оплаты, кол-во дней
    payment_term_condition = Column(String, nullable=True)  # срок оплаты, условие: С даты УПД / С даты АКТ / По периоду — свободный текст в БД, фронт ограничивает списком
    note = Column(Text, nullable=True)
    document_link = Column(String, nullable=True)   # URL на документ в ЭДО или другой системе — открывается по кнопке 🔗
    attached_filename = Column(String, nullable=True)  # имя файла, сохранённого на сервере в /app/uploads/contracts/; NULL = файл не прикреплён
    created_at = Column(DateTime, server_default=func.now())

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
    own_company_id = Column(Integer, ForeignKey("counterparties.id"), nullable=True)  # наше юрлицо-плательщик/получатель
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))
    article = relationship("Article", back_populates="operations")
    counterparty = relationship("Counterparty", back_populates="operations",
                                foreign_keys="Operation.counterparty_id")
    own_company  = relationship("Counterparty", foreign_keys="Operation.own_company_id")

class LoginAttempt(Base):
    """Хранит счётчик неудачных попыток входа и время разблокировки для каждого email.
    Одна строка на email — при успешном входе сбрасывается (не удаляется).
    Таблица создаётся автоматически через Base.metadata.create_all() при старте backend.
    Преимущество перед in-memory dict (_LOGIN_ATTEMPTS): переживает перезапуск контейнера."""
    __tablename__ = "login_attempts"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    failed_count = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
