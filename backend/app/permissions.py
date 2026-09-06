from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, RolePermission
from app.routers.auth import get_current_user

# Канонический список разделов, доступных настройке через менеджер ролей.
# "Пользователи" и "Роли" сюда не входят — они жёстко закрыты под admin (privilege
# escalation: правка ролей = выдать себе что угодно; правка юзеров = сброс паролей).
# Раздел настраивается матрицей ролей: разделы по вертикали, роли по горизонтали
# (settings.js). Группы (group) идут по соседству — их заголовки рисуются один раз.
# Секции «Продажи» и «Справочники продаж» покрывают вложенные подстраницы:
#   sales_dashboard   → Дашборд · Реестр сделок · Аналитика (общий data-слой, одно право);
#   sales_directories → Рекламодатели · Агентства · Воронки · Услуги · Бренды · Прайс.
# Отдельных прав на каждую подстраницу не заводим: они делят одни и те же эндпойнты,
# гейтить их порознь сейчас было бы косметикой. При необходимости — расщепить позже.
SECTIONS = [
    {"key": "dashboard",         "label": "ДДС",                "group": "Финансы",    "actions": ["view"]},
    {"key": "pl",                "label": "P&L",                "group": "Финансы",    "actions": ["view"]},
    # Фин. отчёт до 2026-08-17 висел на праве P&L: выдать одно без другого было нельзя.
    # Ключ новый, а не переименованный: ключи неизменяемы (см. tests/test_permissions_groups).
    {"key": "finreport",         "label": "Фин. отчёт",         "group": "Финансы",    "actions": ["view"]},
    {"key": "balance",           "label": "Баланс",             "group": "Финансы",    "actions": ["view"]},
    {"key": "planfact",          "label": "План / Факт",        "group": "Финансы",    "actions": ["view"]},
    {"key": "receivables",       "label": "Дебиторская задолженность", "group": "Финансы", "actions": ["view", "edit"]},
    # Раздел «Продажи» — три отдельные страницы. Действие "edit" на реестре гейтит
    # правку сделок и синхронизацию. deals_scope (all/own) — видимость сделок,
    # задаётся 5-уровневым контролом матрицы (нет/просмотр-свои/все/ред.-свои/все).
    {"key": "sales_dashboard",   "label": "Продажи · Дашборд",       "group": "Продажи", "actions": ["view", "edit"]},
    {"key": "sales_registry",    "label": "Продажи · Реестр сделок",  "group": "Продажи", "actions": ["view", "edit"]},
    {"key": "sales_analytics",   "label": "Продажи · Аналитика",      "group": "Продажи", "actions": ["view", "edit"]},
    {"key": "year_plan",         "label": "Продажи · Годовой план",   "group": "Продажи", "actions": ["view", "edit"]},
    # Рабочий экран аккаунт-менеджера — очередь «Что делать». Входной экран контура.
    # deals_scope (all/own) берётся от sales_registry: очередь показывает те же сделки,
    # что и реестр, — своё право на видимость завело бы два разных ответа на вопрос
    # «мои это сделки или нет».
    {"key": "accounts_dashboard", "label": "Аккаунты · Дашборд",       "group": "Аккаунты", "actions": ["view", "edit"]},
    # Медиапланы (контур аккаунта): реестр и конструктор — раздельно.
    # «approve» убрано 30.08.2026 вместе со стейт-машиной согласования МП: своего
    # состояния у плана больше нет, его состояние — стадия сделки. Колонка
    # `role_permissions.can_approve` осталась (её используют «Креативы» и «Очередь
    # трафика»), у медиапланов она просто перестала на что-либо влиять.
    {"key": "media_plans",        "label": "Медиапланы · Реестр",      "group": "Аккаунты", "actions": ["view", "edit"]},
    {"key": "media_plans_editor", "label": "Медиапланы · Конструктор", "group": "Аккаунты", "actions": ["view", "edit"]},
    # Обвязка ОРД — не отдельный модуль, а часть поля аккаунта (решение владельца
    # 2026-08-25), поэтому обе секции живут в контуре «Аккаунты», а не в справочниках.
    #
    # `ord` — зеркало кабинета: юрлица и три вида договоров. Наполняется загрузкой
    # выгрузки, на этапе 2 — синхронизацией по API.
    {"key": "ord",               "label": "Аккаунты · ОРД",           "group": "Аккаунты", "actions": ["view", "edit"]},
    # `ord_submit` — запись в ОРД: завести договор или юрлицо, выпустить ЕРИД.
    # Отделён потому, что действие необратимо: маркер, ушедший в ЕРИР, не отзывается.
    # Сама сборка правом не гейтится — она живёт на карточке сделки и открыта тем,
    # кто ведёт сделки (sales_registry), иначе стадия появилась бы у всех сразу.
    {"key": "ord_submit",        "label": "Аккаунты · ОРД отправка",  "group": "Аккаунты", "actions": ["view", "create"]},
    # Модуль креативов (сбор запуска). `approve` — ставить вердикт: первичный по ТТ и
    # вердикт площадки, записанный с её слов. Действие уже есть в ACTION_FIELDS и
    # работает в реестре медиапланов, новых полей не понадобилось.
    # Выпуск ЕРИД сюда НЕ входит — он идёт под `ord_submit`: за одним правом должна
    # стоять одна необратимость, и она там уже описана.
    {"key": "creatives",         "label": "Аккаунты · Креативы",      "group": "Аккаунты", "actions": ["view", "edit", "approve"]},
    {"key": "operations",        "label": "Операции",           "group": "Финансы",   "actions": ["view", "create", "edit", "delete"]},
    {"key": "import",            "label": "Импорт",             "group": "Финансы",   "actions": ["view"]},
    {"key": "counterparties",    "label": "Контрагенты",        "group": "Справочники", "actions": ["view", "edit", "delete", "view_operations"]},
    {"key": "contracts",         "label": "Договоры",           "group": "Справочники", "actions": ["view", "edit"]},
    # Приложения к договору (ДС). Своя секция, а не право «Договоры»: реестр приложений
    # видит суммы сделок и выпускает документы клиенту, а карточку договора правит и тот,
    # кому этого знать не нужно. `create` — завести черновик из сделки, `edit` —
    # подтвердить номер и дописать реквизиты подписанта в карточку контрагента (это те же
    # данные, которые печатаются в документе, поэтому право одно).
    {"key": "annexes",           "label": "Приложения к договорам", "group": "Справочники", "actions": ["view", "create", "edit"]},
    {"key": "dir_advertisers",   "label": "Рекламодатели",      "group": "Справочники", "actions": ["view", "edit", "delete"]},
    {"key": "dir_agencies",      "label": "Агентства",          "group": "Справочники", "actions": ["view", "edit", "delete"]},
    # Экран «Добавить данные» (/directory/add) — заводит связку вид → юрлицо → договор
    # за один проход. Действие ровно одно: `view` = «пускать ли на экран». Своих ручек
    # экран не завёл ни одной, он оркеструет существующие, и каждая спрашивает СВОЁ право
    # (counterparties · edit, contracts · edit, dir_* · edit) — блок без права гасится
    # прямо на экране. Заводить здесь `edit` значило бы второе правило поверх тех же
    # ручек: право стояло бы, а сохранение всё равно упиралось бы в право блока.
    {"key": "directory_add",     "label": "Добавить данные",    "group": "Справочники", "actions": ["view"]},
    {"key": "bx_reconcile",      "label": "Сверка с Битриксом", "group": "Справочники", "actions": ["view", "edit"]},
    # Настройки разнесены на отдельные страницы (/settings/*) — по праву на раздел,
    # как справочники. Пользователи и Роли сюда НЕ входят (admin-only, см. выше).
    # Паблишеры — свой контур: площадка перестала быть справочной записью, у неё
    # свои экраны и дальше кабинеты внешних пользователей. Ключ права при переносе
    # не менялся — он записан у живых пользователей, менять его нельзя.
    {"key": "dir_publishers",    "label": "Паблишеры · Площадки", "group": "Паблишеры", "actions": ["view", "edit"]},
    # Экран «Заполнение» — те же действия, что и в карточке, но пачкой и без
    # подтверждения. Право отдельное и самодостаточное: сотрудника первичного
    # наполнения сажают на него одно — правит пачкой, карточку видит только на чтение.
    # Эндпоинты у карточки и «Заполнения» общие, поэтому publishers.py пропускает по
    # ЛЮБОМУ из двух прав; это разделение экранов, а не защита данных.
    {"key": "dir_publishers_bulk", "label": "Паблишеры · Заполнение", "group": "Паблишеры", "actions": ["view", "edit"]},
    # Учётки внешнего кабинета. Право отдельное от реестра площадок: доступ снаружи —
    # другая ответственность, чем правка карточки, и раздаётся он уже́е.
    # Бэкфилла ролям НЕ делается: доступ к учёткам кабинета выдаёт владелец руками.
    {"key": "dir_publishers_cabinets", "label": "Паблишеры · Кабинеты", "group": "Паблишеры", "actions": ["view", "edit"]},

    # Контур «Трафики» — очередь проверки материала перед отправкой площадкам
    # (2026-08-28, docs/SCHEMA_конвейер_трафиков_на_согласование.md). Заведён с нуля:
    # раньше у трафика не было ни права, ни экрана, а вердикт за него ставился автоматом.
    #
    # `approve` — «всё ок» и «на переделку». Третьего исхода у трафика нет: закрыть
    # площадку не его полномочие, и сервер отклоняет `отказ` для этого вида проверки.
    # `edit` — приложить скриншоты и завести тестовую ссылку нацеливания.
    #
    # deals_scope сюда НЕ заводится: у трафика своя ось принадлежности —
    # sales_deals.traffic_manager_id, — и она не совпадает с «сейлз или аккаунт».
    # Видимостью управляет is_master роли: мастер видит всю очередь, остальные —
    # свои и ничьи (см. routers/traffic.py).
    {"key": "traffic_queue",     "label": "Трафики · Очередь",  "group": "Трафики", "actions": ["view", "edit", "approve"]},
    # Каталог площадок и блоков (МС-реквизиты поверхностей + рекламные блоки). Заведён
    # 2026-09-01 вместе с экраном «Каталог площадок»; доступ по умолчанию — мастера + админ
    # (бэкфилл is_master в 2026-09-01_traffic_catalog.sql). Не привязан к сделкам — deals_scope нет.
    {"key": "traffic_catalog",   "label": "Трафики · Каталог",  "group": "Трафики", "actions": ["view", "create", "edit", "delete"]},
    # Дашборд открутки РК (этап 3b, 02.09.2026). Свой ключ, а не подсадка на очередь/каталог:
    # дашборд нужен всем трафикам, админка с блоками и весами — только мастерам. edit =
    # управление (старт/стоп/пауза РК и площадки). Видимость РК — как в очереди (мастер видит
    # всё, рядовой трафик только свои по traffic_manager_id), поэтому deals_scope не заводим:
    # «свои» у трафика это не «сейлз или аккаунт». Бэкфилл — 2026-09-02_traffic_dashboard_perm.sql.
    {"key": "traffic_dashboard",  "label": "Трафики · Дашборд",  "group": "Трафики", "actions": ["view", "edit"]},
    # Демо-стенд DSP: отработка цепочки креатива на ДЕМО-клиенте DSP, вне боевых
    # кампаний. Право отдельное и БЕЗ БЭКФИЛЛА — по умолчанию не у кого (решение владельца
    # 06.09.2026): инструмент шлёт запросы во внешнюю систему, и «кто видит дашборд, тот
    # и отправляет» — не то же самое. `edit` = право нажимать отправку, `view` = смотреть
    # журнал обмена.
    {"key": "dsp_demo",           "label": "Трафики · DSP демо", "group": "Трафики", "actions": ["view", "edit"]},

    {"key": "settings_balances",    "label": "Настройки · Остатки",  "group": "Ядро", "actions": ["view", "edit"]},
    {"key": "settings_articles",    "label": "Настройки · Статьи",   "group": "Ядро", "actions": ["view", "edit"]},
    {"key": "settings_pipelines",   "label": "Настройки · Воронки",  "group": "Ядро", "actions": ["view", "edit"]},
    {"key": "settings_services",    "label": "Настройки · Услуги",   "group": "Ядро", "actions": ["view", "edit"]},
    {"key": "settings_field_audit", "label": "Настройки · Сверка полей", "group": "Ядро", "actions": ["view"]},
    {"key": "settings_audit",       "label": "Настройки · Журнал действий", "group": "Ядро", "actions": ["view"]},
    # Бэклог отладки: что держим под наблюдением после больших изменений.
    # Без "delete" осознанно — записи снимаются с наблюдения статусом, а не стиранием:
    # удалённое наблюдение не отличить от «не заводили».
    {"key": "settings_backlog",     "label": "Настройки · Бэклог отладки", "group": "Ядро", "actions": ["view", "create", "edit"]},
]

# Разделы настроек (для фронта: SettingsTabs, редирект, гейт страниц).
SETTINGS_SECTIONS = ("settings_balances", "settings_articles", "settings_pipelines",
                     "settings_services", "settings_field_audit", "settings_audit",
                     "settings_backlog")

# Секции продаж (5-уровневый контроль со свои/все) — для UI-матрицы и gate-хелперов.
SALES_SECTIONS = ("sales_dashboard", "sales_registry", "sales_analytics")

ACTION_FIELDS = {"view": "can_view", "create": "can_create", "edit": "can_edit", "delete": "can_delete", "view_operations": "can_view_operations", "approve": "can_approve"}


def get_permissions_for_user(db: Session, user: User) -> dict:
    """Возвращает {section: {action: bool}} для пользователя. Admin всегда получает полный доступ
    (без хранения строк в role_permissions — это и есть смысл «бессмертной» системной роли)."""
    if user.role.key == "admin":
        return {s["key"]: {a: True for a in s["actions"]} for s in SECTIONS}

    rows = db.query(RolePermission).filter(RolePermission.role_id == user.role_id).all()
    by_section = {r.section: r for r in rows}

    result = {}
    for s in SECTIONS:
        row = by_section.get(s["key"])
        result[s["key"]] = {
            a: bool(getattr(row, ACTION_FIELDS[a])) if row else False
            for a in s["actions"]
        }
    return result


def require_any_permission(sections, action: str = "view"):
    """Пропускает, если у роли есть право хотя бы по одному из перечисленного.

    Для эндпойнтов, обслуживающих несколько экранов: справочник кормит выпадающие
    списки на нескольких страницах, и жёсткое require_permission на один раздел
    сломало бы форму тем, у кого прав на сам справочник нет.

    `sections` принимает две формы:

    * имена разделов — тогда действие одно на всех, из `action`:
      `require_any_permission(("sales_registry", "sales_analytics"), "view")`
    * пары (раздел, действие) — когда требования разные:
      `require_any_permission((("operations", "view"),
                               ("counterparties", "view_operations")))`

    Вторая форма заведена 2026-08-23: без неё проверку «operations.view ИЛИ
    counterparties.view_operations» нельзя было выразить зависимостью, и она
    жила в теле функции — то есть была невидима для инвентаря роутов
    (tests/test_route_guards.py). Право должно объявляться в зависимости;
    телу остаётся только вопрос области видимости («чьи это данные»).

    Admin всегда проходит.
    """
    pairs = [(s, action) if isinstance(s, str) else (s[0], s[1]) for s in sections]

    def checker(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if current_user.role.key == "admin":
            return current_user
        rows = {r.section: r for r in db.query(RolePermission)
                .filter(RolePermission.role_id == current_user.role_id,
                        RolePermission.section.in_([p[0] for p in pairs])).all()}
        for section, act in pairs:
            row = rows.get(section)
            if row and bool(getattr(row, ACTION_FIELDS.get(act, "can_view"))):
                return current_user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для этого действия")
    # Метка для приборов: снаружи замыкание неотличимо от любой другой зависимости,
    # и обойти все ручки, проверяя, что каждая закрыта, было бы нечем. Ставится ЗДЕСЬ,
    # а не в тесте: тест не должен знать внутренностей фабрики.
    checker._perm_sections = tuple(x if isinstance(x, str) else x[0] for x in sections)
    checker._perm_action = action
    return checker


def require_permission(section: str, action: str = "view"):
    """Фабрика зависимостей FastAPI: пропускает запрос, только если у роли пользователя есть
    разрешение can_<action> для данного раздела. Admin всегда проходит без проверки."""
    def checker(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if current_user.role.key == "admin":
            return current_user
        row = db.query(RolePermission).filter(
            RolePermission.role_id == current_user.role_id,
            RolePermission.section == section,
        ).first()
        field = ACTION_FIELDS.get(action, "can_view")
        allowed = bool(getattr(row, field)) if row else False
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для этого действия")
        return current_user
    checker._perm_sections = (section,)
    checker._perm_action = action
    return checker
