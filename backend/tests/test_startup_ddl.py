"""
Стартовый код не имеет права ничего разрушать.

Блок `with engine.begin()` в app/main.py выполняется при КАЖДОМ запуске контейнера.
Пока среди идемпотентных ADD COLUMN там жили DROP TABLE и два DROP COLUMN, каждый
рестарт бэкенда был окном поломки схемы — и обычно это сходило с рук, потому что
удалять было уже нечего.

Ставки меняет кабинет паблишера: наружу отдаются не таблицы, а представления
pub.*_v1, и view над удалённой колонкой падает. Падает при этом у внешнего
пользователя, а не у нас, и в момент, который мы не выбирали — при перезапуске
контейнера по любой причине. Добавляющая операция представление сломать не может,
разрушающая может.

Поэтому правило: в стартовом коде только ADD COLUMN IF NOT EXISTS, CREATE INDEX
IF NOT EXISTS и ADD CONSTRAINT. Всё остальное — в migrations/, где оно проходит
через согласование и выполняется один раз, а не при каждом старте.

Перенос сделан 2026-08-23, миграция 2026-08-23_startup_ddl_to_migrations.sql.
"""
import ast
import io
import re
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
MAIN = APP / "main.py"

# Глаголы, которые в стартовом коде означают потерю данных или структуры.
DESTRUCTIVE = (
    r"\bDROP\s+TABLE\b",
    r"\bDROP\s+COLUMN\b",
    r"\bDROP\s+INDEX\b",
    r"\bDROP\s+CONSTRAINT\b",
    r"\bDROP\s+SCHEMA\b",
    r"\bTRUNCATE\b",
    r"\bDELETE\s+FROM\b",
    r"\bALTER\s+TABLE\s+\S+\s+RENAME\b",
)

# Изменение данных. Само по себе не разрушает схему, но выполняться на каждом
# старте не должно: бэкфилл — разовая операция, его место в миграции.
# Поимённые исключения к списку выше. Каждое — с причиной, и каждое проверяется на
# нужность соседним прибором: разрешение, которому нечего разрешать, притупляет стража.
#
# Обходить стража молча нельзя даже там, где обход безобиден: `db.query(...).delete()`
# через ORM этот тест не заметил бы вовсе — и именно поэтому так делать не следует.
# Исключение должно быть видно в ревью, а не спрятано сменой способа записи.
ALLOWED_DESTRUCTIVE = (
    # Возврат умолчания, а не разрушение: в `cabinet_account_mute` строка ОЗНАЧАЕТ
    # «выключено», её отсутствие — «включено». Включить вид уведомления обратно можно
    # только удалив строку, и удаляется ровно одна, по первичному ключу.
    "DELETE FROM cabinet_account_mute WHERE account_id = :a AND kind = :k",
    # Список наших контактов у площадок переписывается целиком: их единицы, и ПОРЯДОК
    # в списке — часть смысла (первым площадка видит того, к кому идти сначала).
    # Собирать порядок правками по строке значило бы получать его наполовину
    # применённым при обрыве. Таблица — настройка, а не учётные данные: терять здесь
    # нечего, кроме самой настройки, которую тем же запросом и восстанавливают.
    "DELETE FROM cabinet_our_contact",
    # Разметка видимости блоков карточки — тоже НАСТРОЙКА, а не учётные данные, и она
    # переписывается целиком по кнопке «Сохранить все». Строк семь, ключ — пара
    # (стадия, блок), и правка по одной строке давала бы промежуточные состояния, в
    # которых блок виден с двух стадий сразу или не виден ни с одной. Терять здесь
    # нечего, кроме самой разметки, которую тот же запрос и записывает заново; удаление
    # идёт внутри транзакции сохранения каталога, так что при обрыве не остаётся и её.
    "DELETE FROM sales_stage_blocks",
    # Ручные показы верификатора: ОДНА строка на кампанию, и правится она перезаписью.
    # Апсерт по дате тут не годится — исправленный период оставил бы рядом старое число,
    # и в сверку пошла бы их СУММА, то есть вдвое завышенный показатель у верификатора.
    # Пустое значение стирает строку намеренно: ошиблись при вводе — надо иметь чем
    # убрать, иначе неверное число остаётся в сверке навсегда. Удаляется ровно свой
    # источник (`weborama_manual`) и только по своей кампании; ни факт, ни снятое через
    # API этим запросом не задеть.
    "DELETE FROM ad_campaign_stat WHERE campaign_id = :c AND placement_id IS NULL AND source = 'weborama_manual'",
)

DATA_MUTATING = (
    r"\bUPDATE\s+\w+\s+SET\b",
    r"\bINSERT\s+INTO\b",
)


def _sql_literals(path: Path):
    """Все строковые литералы модуля, похожие на SQL.

    Разбор через AST, а не поиском по тексту: иначе тест ловит собственные
    комментарии и падает на объяснении, почему DROP запрещён. У f-строк
    (`text(f"CREATE INDEX ... {_ix}")`) ast.walk отдаёт составные части — их
    достаточно, ключевое слово всегда в статической части.
    """
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value
            if re.search(r"\b(ALTER|CREATE|DROP|INSERT|UPDATE|DELETE|TRUNCATE)\b", s, re.I):
                out.append(s)
    return out


def test_startup_has_no_destructive_sql():
    """Ни одной разрушающей операции в коде, выполняемом при старте."""
    found = []
    for sql in _sql_literals(MAIN):
        for pat in DESTRUCTIVE:
            if re.search(pat, sql, re.I):
                found.append((pat, " ".join(sql.split())[:90]))
    assert not found, (
        "разрушающая операция в стартовом коде main.py — её место в migrations/:\n"
        + "\n".join(f"  {p} → {s}" for p, s in found)
    )


def test_startup_does_not_mutate_data():
    """Бэкфилл — разовая операция, а не работа при каждом запуске контейнера."""
    found = []
    for sql in _sql_literals(MAIN):
        for pat in DATA_MUTATING:
            if re.search(pat, sql, re.I):
                found.append((pat, " ".join(sql.split())[:90]))
    assert not found, (
        "изменение данных в стартовом коде main.py — его место в migrations/:\n"
        + "\n".join(f"  {p} → {s}" for p, s in found)
    )


def test_startup_ddl_is_idempotent():
    """ADD COLUMN и CREATE INDEX без IF NOT EXISTS падают при втором запуске.

    Контейнер поднимается не один раз, и второй старт не должен отличаться от первого.
    """
    bad = []
    for sql in _sql_literals(MAIN):
        flat = " ".join(sql.split())
        if re.search(r"\bADD COLUMN\b", flat, re.I) and not re.search(r"\bADD COLUMN IF NOT EXISTS\b", flat, re.I):
            bad.append(flat[:90])
        if re.search(r"\bCREATE (UNIQUE )?INDEX\b", flat, re.I) and not re.search(r"\bIF NOT EXISTS\b", flat, re.I):
            bad.append(flat[:90])
    assert not bad, "неидемпотентная операция в стартовом коде:\n" + "\n".join("  " + b for b in bad)


def test_moved_operations_live_in_migrations():
    """Перенос — это перенос, а не удаление.

    Если файл миграции когда-нибудь исчезнет, база, не прошедшая эту точку, останется
    с таблицей sales_service_variants и колонками platform/currency, которых нет в
    моделях. Тест держит запись о том, что было сделано.
    """
    f = MIGRATIONS / "2026-08-23_startup_ddl_to_migrations.sql"
    assert f.exists(), "миграция переноса пропала — история того, что делал стартовый блок, потеряна"
    body = io.open(f, encoding="utf-8").read().upper()
    for needed in ("DROP TABLE IF EXISTS SALES_SERVICE_VARIANTS",
                   "DROP COLUMN IF EXISTS PLATFORM",
                   "DROP COLUMN IF EXISTS CURRENCY",
                   "PLAN_DEAL_IDX",
                   "SALES_YEAR_PLANS"):
        assert needed in body, f"в миграции переноса нет «{needed}»"


def test_no_destructive_sql_anywhere_in_app():
    """То же правило для всего пакета app/, а не только для main.py.

    Стартовый блок — не единственное место, откуда можно уронить схему: любой
    импортируемый модуль выполняет код на уровне модуля при подъёме приложения.
    Роутеры сюда тоже попадают: разрушающий SQL внутри обработчика запроса — это
    та же поломка контракта, только по чужому клику.

    Одним тестом, а не параметризацией по файлам: правило одно, и шесть десятков
    зелёных строк в прогоне ради него — шум, в котором теряется настоящее падение.
    """
    found = []
    for path in sorted(APP.rglob("*.py")):
        for sql in _sql_literals(path):
            one = " ".join(sql.split())
            if any(frag in one for frag in ALLOWED_DESTRUCTIVE):
                continue
            for pat in DESTRUCTIVE:
                if re.search(pat, sql, re.I):
                    found.append(f"{path.relative_to(APP)}: {' '.join(sql.split())[:80]}")
    assert not found, "разрушающий SQL в app/:\n" + "\n".join("  " + s for s in found)



def test_every_exception_is_still_needed():
    """Разрешение, которому нечего разрешать, — мусор, притупляющий стража.

    Исключение живёт ровно до тех пор, пока в коде есть то, ради чего оно заведено.
    Без этой проверки список растёт и однажды прикроет настоящую находку.
    """
    body = " | ".join(" ".join(sql.split())
                      for path in APP.rglob("*.py") for sql in _sql_literals(path))
    unused = [frag for frag in ALLOWED_DESTRUCTIVE if frag not in body]
    assert not unused, f"разрешения ни к чему не относятся, уберите: {unused}"

def test_startup_runs_no_schema_ddl():
    """На старте не осталось НИ ОДНОЙ схемной операции — только create_all.

    31.08.2026 весь ALTER/CREATE INDEX/ADD CONSTRAINT вынесен в
    migrations/2026-08-31_startup_ddl_extracted.sql. Причина не «чище», а конкретная:
    эти операции берут AccessExclusiveLock, и на первом старте нового кода против свежей
    базы они деадлочили с логинами (RowShareLock), а зависшие bcrypt-воркеры исчерпывали
    пул — вход виснул. Схема правится миграцией ДО старта; сюда её возвращать нельзя.

    Проверяем строковые литералы (AST), поэтому комментарии, объясняющие запрет, под него
    не попадают. `create_all` — не литерал, его этот тест не трогает.
    """
    offenders = []
    for sql in _sql_literals(MAIN):
        flat = " ".join(sql.split())
        if re.search(r"\bALTER\s+TABLE\b|\bCREATE\s+(UNIQUE\s+)?INDEX\b|\bADD\s+CONSTRAINT\b",
                     flat, re.I):
            offenders.append(flat[:90])
    assert not offenders, (
        "схемный DDL вернулся в стартовый код main.py — его место в migrations/ "
        "(2026-08-31_startup_ddl_extracted.sql), иначе снова деадлок при первом старте:\n"
        + "\n".join("  " + o for o in offenders)
    )


def test_extracted_ddl_migration_exists_and_is_additive():
    """Перенос стартового DDL — это перенос, а не удаление, и он только добавляет.

    Держит запись о том, что делал стартовый блок, и запрещает протащить в этот файл
    разрушающую операцию под видом «переноса».
    """
    f = MIGRATIONS / "2026-08-31_startup_ddl_extracted.sql"
    assert f.exists(), "миграция выноса стартового DDL пропала"
    body = io.open(f, encoding="utf-8").read()
    up = body.upper()
    # ключевые вещи, ради которых миграция и заведена
    for needed in ("AMOUNT_WITH_VAT", "STAFF_GROUP", "CAN_APPROVE",
                   "IX_SALES_DEALS_CODE", "SALES_DEALS_OUR_STAGE_ID_FKEY"):
        assert needed in up, f"в миграции выноса нет «{needed}»"
    # ничего разрушающего/меняющего данные (DO-блок с NOTICE — не в счёт)
    for pat in (r"\bDROP\s+TABLE\b", r"\bDROP\s+COLUMN\b", r"\bTRUNCATE\b",
                r"\bDELETE\s+FROM\b", r"\bUPDATE\s+\w+\s+SET\b", r"\bINSERT\s+INTO\b"):
        assert not re.search(pat, up), f"в миграции выноса разрушающая/меняющая операция: {pat}"
