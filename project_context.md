# Финансовая система — база знаний проекта

## Стек технологий
- **Бэкенд:** Python 3.11 + FastAPI + SQLAlchemy + PostgreSQL 16
- **Фронтенд:** Next.js 14 + React + Recharts
- **Инфраструктура:** Docker Compose (локально на Windows 11 с Rancher Desktop)
- **Папка проекта:** `F:\finance`

## Запуск
```
cd F:\finance
docker compose up -d
```
- Фронтенд: http://localhost:3000
- Бэкенд API: http://localhost:8000
- БД: PostgreSQL на порту 5432

## Структура проекта
```
F:\finance\
├── docker-compose.yml
├── backend\
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app\
│       ├── main.py
│       ├── database.py
│       ├── models.py
│       └── routers\
│           ├── auth.py
│           ├── operations.py
│           ├── reports.py
│           ├── counterparties.py
│           ├── articles.py
│           └── settings.py
└── frontend\
    ├── Dockerfile
    ├── package.json
    ├── components\
    │   └── Navbar.js
    ├── pages\
    │   ├── _app.js
    │   ├── index.js
    │   ├── login.js
    │   ├── dashboard.js
    │   ├── operations.js
    │   ├── pl.js
    │   ├── balance.js
    │   ├── settings.js
    │   └── import.js
    └── styles\
        └── globals.css
```

## База данных — таблицы
- **users** — пользователи (id, name, email, hashed_password, role, is_active)
- **articles** — статьи расходов (id, name, group, subgroup, type)
- **counterparties** — контрагенты (id, name, vat_rate)
- **operations** — операции (id, date, status, income, expense, bank, period, vat_rate, vat_fact, article_id, counterparty_id, ds_num, invoice, invoice_date, description, created_by)
- **bank_balances** — стартовые остатки по банкам (id, bank, opening_balance)

## Ключевые паттерны

### Копирование файлов в контейнер (через cmd, не PowerShell)
```
docker exec -i finance_frontend sh -c "cat > /app/pages/file.js" < "F:\finance\frontend\pages\file.js"
docker exec -i finance_backend sh -c "cat > /app/app/routers/file.py" < "F:\finance\backend\app\routers\file.py"
```

### Пересборка фронтенда
```
docker exec -it finance_frontend sh -c "cd /app && rm -rf .next && npm run build && echo DONE"
docker restart finance_frontend
```

### Рестарт бэкенда (не требует пересборки)
```
docker restart finance_backend
```

### Бэкап БД
```
docker exec -t finance_db pg_dump -U finance_user finance > F:\finance\backup_name.sql
```

### Восстановление БД
```
docker exec -i finance_db psql -U finance_user -d finance < "F:\finance\backup_name.sql"
```

### SQL через cmd
```
docker exec -i finance_db psql -U finance_user -d finance < "F:\finance\script.sql"
```

## Данные
- **Источник:** Google таблица / Excel файл `CLOUDE_Simb-AD____PM_Cashflow.xlsx`, лист `CF BEST`, header=6
- **Период данных:** июль 2023 — июнь 2026
- **Всего операций:** 2776
- **Банки:** АльфаБанк (красный), ОПТ Банк (зелёный), Совкомбанк (серый), Наличные (синий)
- **Статусы:** ОПЛАЧЕНО, ПЛАН ПОСТУПЛЕНИЙ, ПЛАН ОПЛАТ
- **Статей:** 34 с группами и подгруппами

## Группировка статей для P&L
- **ВЫРУЧКА:** РЕАЛИЗАЦИЯ
- **СЕБЕСТОИМОСТЬ:** АПТЕКА, СК АГЕНТСКАЯ, СК ПАРТНЕРСКАЯ, ПАБЛИШЕР, БАННЕРЫ, ОРД, НАЛОГИ|Реклама, ПОДРЯДЧИКИ
- **ОПЕРАЦИОННЫЕ:** ФОТ, ПРЕМИЯ, БОНУСЫ, АВАНС, НАЛОГИ|НДФЛ, НАЛОГИ|Страх.Взносы, ОФИС, БАНК, КРЕДИТЫ, ДОЛГ, ПОДПИСКИ, IT, РАЗРАБОТКА
- **МАРКЕТИНГ:** МЕРОПРИЯТИЯ, PR, ПРЕДСТАВИТЕЛЬСКИЕ, ГОЛЬФ
- **НАЛОГИ:** НАЛОГИ, НАЛОГИ|НДС, НАЛОГИ|Прибыль, НАЛОГИ|ПРОЧИЕ, НАЛОГИ|Пени
- **НЕ В P&L:** ТРАНЗИТ, ДИВИДЕНТЫ, ПРОЧЕЕ

## Особенности реализации
- Периоды нормализованы: русские месяцы → YYYY-MM, кварталы → Q1 2025 и т.д.
- Квартальные операции (Q1-Q4) разбиваются на 3 месяца равными долями при отображении
- Фильтрация по периоду в P&L происходит ПОСЛЕ нормализации кварталов
- Стартовые остатки по банкам хранятся в таблице bank_balances
- localStorage инициализируется только в useEffect (не SSR)
- Файлы копируются через cmd (не PowerShell) из-за кодировки кириллицы

## Что сделано
- ✅ Авторизация (JWT токены, роли admin/manager/viewer)
- ✅ Импорт Excel (лист CF BEST)
- ✅ Список операций — пагинация, сортировка, мультифильтры, редактирование, цветные плашки банков
- ✅ ДДС — графики, разбивка по банкам, накопительный остаток, фильтр периода, группировка по дате/периоду
- ✅ P&L — трёхуровневая структура (группа→подгруппа→статья), валовая прибыль, EBITDA, чистая прибыль с маржой
- ✅ Баланс — денежные средства по банкам, дебиторка, кредиторка с мультифильтрами
- ✅ Настройки — стартовые остатки по банкам
- ✅ Единая шапка Navbar на всех страницах

## Что осталось сделать
- ⬜ Реестр контрагентов (страница с НДС, поиском, редактированием)
- ⬜ Navbar на страницах operations, settings, import
- ⬜ Управление пользователями (добавление команды, роли)
- ⬜ Парсер банковских выписок (Альфа, ОПТ, Совком — PDF/CSV)
- ⬜ Экспорт отчётов в Excel/PDF
- ⬜ План/Факт раздел (загрузка данных из БДДС листов)
- ⬜ Синхронизация с Google Sheets
- ⬜ Синхронизация с 1С (обсудить формат)
- ⬜ Перенос на боевой Linux сервер

## Пользователи системы
- admin@finance.ru / admin123 (роль: admin)

## Важные команды для проверки
```bash
# Проверить статусы контейнеров
docker ps

# Проверить логи бэкенда
docker logs finance_backend --tail 20

# Проверить данные в БД
docker exec -it finance_db psql -U finance_user -d finance -c "SELECT COUNT(*) FROM operations;"

# Проверить статьи с группами
docker exec -it finance_db psql -U finance_user -d finance -c "SELECT name, \"group\", subgroup FROM articles ORDER BY \"group\", name;"
```
