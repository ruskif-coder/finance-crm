"""Состояние системы: проверки, из которых собирается экран и список алертов.

Заведено 07.09.2026 после случая, когда база DSP лежала три часа и об этом никто не узнал.
Разбор показал три РАЗНЫЕ причины, и модуль отвечает на все три:

  · у сервиса не было `restart: always` → статические проверки конфигурации;
  · никто не узнал о падении       → проверки живости;
  · процесс жил, но не работал      → проверки РЕЗУЛЬТАТА, а не порта.

Третья — главная и самая неочевидная. Мёртвый контейнер видно. Живой процесс, переставший
делать работу, не видно ничем: ровно так же тихо отвалился ключ Битрикса, и обнаружилось
это случайно, через сутки.

**Докера здесь нет и не будет.** Замерено 07.09.2026: у контейнера бэкенда ни
`/var/run/docker.sock`, ни клиента. Это не недоработка, а решение: сокет докера — пульт
управления хостом, кто в него пишет, тот запускает контейнер с примонтированным корнем и
получает root на машине. Бэкенд доступен из интернета, работает под root внутри контейнера
и делит сервер с чужой системой (TruckCRM). Список контейнеров принесёт агент на хосте —
он пишет файл, который сюда монтируется ТОЛЬКО НА ЧТЕНИЕ, и направление доверия
переворачивается: хост рассказывает контейнеру, а не контейнер командует хостом.

Поэтому здесь ровно то, что видно изнутри — и этого больше, чем кажется: `/app/uploads`
смонтирован с хоста, и `disk_usage` по нему отдаёт свободное место НАСТОЯЩЕГО диска.
"""

import logging
import os
import shutil
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger("finance.status")

UPLOADS_ROOT = "/app/uploads"

# Пороги свободного места (владелец 07.09.2026), в процентах.
DISK_WARN_PCT = 20
DISK_CRIT_PCT = 10

# Колонки, в которых лежат ключи файлов. Список ЗАМЕРЕН 07.09.2026 запросом к
# information_schema, а не переписан из заметки: там их значилось шесть, на деле десять —
# с августа добавились приложения к договору, письма о правах, скриншоты доработок и
# медиакиты. Каждое новое хранилище обязано попадать сюда, иначе его файлы будут
# считаться сиротами и наоборот.
PATH_COLUMNS = [
    ("sales_deal_files", "path"),
    ("contracts", "attached_filename"),
    ("launch_prep_creative_file", "path"),
    ("launch_prep_creative_set", "rights_letter_path"),
    ("launch_prep_pair_file", "path"),
    ("sales_publisher_contracts", "document_path"),
    ("sales_publisher_documents", "path"),
    ("sales_publishers", "media_kit_path"),
    ("operation_files", "path"),
    ("sales_annexes", "file_path"),
]


# Четыре тона, а не три (дизайн-хендофф 07.09.2026). `idle` — «данных нет, и это норма»:
# cron стоит только на сервере, синк с Битриксом запускается руками. Раньше такие строки
# звались `unknown` и читались как поломка, попадая в счёт отказов вместе с настоящими.
#
# `consequence` — ЧТО ЭТО ЗНАЧИТ, а не что случилось: «отправок в DSP не будет» вместо
# «нет DSP_API_URL». Имена ключей уходят в `keys` и печатаются второй строкой.
# `action` — только туда, где вопрос действительно решается; кнопки в никуда не заводим.
def _check(key, group, title, tone, value=None, note=None,
           consequence=None, keys=None, action=None):
    # Незнакомый тон СВОДИМ к худшему, а не пропускаем дальше: `collect()` берёт по нему
    # вес из словаря, и чужое слово роняло весь экран состояния (11.09.2026, «crit»).
    # Падать тут нельзя — экран нужен как раз в плохую минуту; поэтому деградируем
    # безопасно и говорим об этом в лог, а сам словарь стережёт прибор
    # `tests/test_system_status.py`.
    if tone not in WORST:
        log.warning("Экран состояния: неизвестный тон %r у проверки %r — считаю за «bad»",
                    tone, key)
        tone = "bad"
    return {"key": key, "group": group, "title": title, "tone": tone,
            "value": value, "note": note, "consequence": consequence,
            "keys": keys, "action": action}


def _age(dt) -> float | None:
    """Возраст в часах. Наивное время считаем UTC — так его пишет вся база."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0


# ── службы ───────────────────────────────────────────────────────────────────

def check_core_db(db: Session):
    t = time.time()
    try:
        db.execute(text("SELECT 1")).scalar()
        ms = int((time.time() - t) * 1000)
        return _check("db_core", "Службы", "Основная база", "ok", f"{ms} мс")
    except Exception as e:                       # noqa: BLE001 — причина уходит в detail
        # ОТКАТ ОБЯЗАТЕЛЕН. Упавший запрос оставляет сессию в состоянии
        # `InFailedSqlTransaction`, и тогда КАЖДЫЙ следующий запрос той же сессии падает
        # ещё до попадания в базу — а ниже по `collect()` их шесть, и они уже без try.
        # Без отката «база не отвечает» превращалась в 500 всего экрана: строку про
        # отказ рисовать было некому. Замерено 11.09.2026 на отравленной сессии.
        try:
            db.rollback()
        except Exception:                        # noqa: BLE001 — соединение уже потеряно
            pass
        return _check("db_core", "Службы", "Основная база", "bad", "не отвечает", str(e)[:200])


def check_dsp_db():
    """Проверка по РЕЗУЛЬТАТУ, а не по порту.

    Поднятый пустой контейнер после потери тома отвечает на подключение и рапортует «ок».
    Поэтому спрашиваем не «жив ли», а «есть ли в нём наши объекты»: гипертаблица и
    непрерывный агрегат. Функция для этого в проекте уже написана — берём её, а не пишем
    второй запрос, который однажды разойдётся с первым.
    """
    try:
        from app.dsp.db import dsp_ping
        p = dsp_ping()
    except Exception as e:                       # noqa: BLE001
        return _check("db_dsp", "Службы", "База DSP", "bad", "не отвечает", str(e)[:200])
    if not (p.get("hypertable_dsp_stat_raw") and p.get("cagg_dsp_stat_daily")):
        return _check("db_dsp", "Службы", "База DSP", "bad",
                      "отвечает, но пуста",
                      "нет гипертаблицы или агрегата — похоже на потерянный том")
    return _check("db_dsp", "Службы", "База DSP", "ok", f"timescale {p.get('timescaledb')}")


def _http_probe(key, title, url, timeout=3.0):
    import httpx
    t = time.time()
    try:
        r = httpx.get(url, timeout=timeout)
        ms = int((time.time() - t) * 1000)
        if r.status_code >= 500:
            return _check(key, "Службы", title, "bad", f"HTTP {r.status_code}")
        return _check(key, "Службы", title, "ok", f"{ms} мс")
    except Exception as e:                       # noqa: BLE001
        return _check(key, "Службы", title, "bad", "не отвечает", str(e)[:200])


def check_pdf():
    # Бьём в `/health`, а НЕ в корень. На `/` Express отдаёт 404, а проба считает живым
    # всё, что меньше 500 — то есть мёртвый сервис с работающим процессом выглядел
    # зелёным (найдено внешним аудитом 11.09.2026, F3-15). Ложнозелёная строка на экране
    # состояния хуже отсутствующей: из-за неё смотрят в другую сторону.
    return _http_probe("pdf", "Сайдкар печати",
                       os.getenv("PDF_SERVICE_URL", "http://pdf:3001") + "/health")


def check_cabinet():
    # Имя по сети — то же, что и container_name, поэтому адрес одинаков на стенде и на
    # проде. Своей переменной не заводим: она была бы четвёртым местом, где записано одно
    # и то же имя.
    return _http_probe("cabinet", "Кабинет паблишера", "http://cabinet_backend:8001/api/health")


# ── базы ─────────────────────────────────────────────────────────────────────

def check_db_sizes(db: Session):
    rows = db.execute(text(
        "SELECT datname, pg_database_size(datname) AS bytes FROM pg_database "
        "WHERE datistemplate = false ORDER BY 2 DESC")).all()
    detail = ", ".join(f"{r.datname} {r.bytes / 2**20:.0f} МБ" for r in rows)
    return _check("db_sizes", "Базы", "Размер баз", "ok", f"{len(rows)} шт.", detail)


def check_db_connections(db: Session):
    row = db.execute(text(
        "SELECT count(*) AS total, "
        "       count(*) FILTER (WHERE state = 'active') AS active, "
        "       max(EXTRACT(epoch FROM now() - query_start)) FILTER "
        "           (WHERE state = 'active' AND query NOT LIKE '%pg_stat_activity%') AS longest "
        "FROM pg_stat_activity WHERE datname = current_database()")).first()
    longest = int(row.longest or 0)
    sev = "warn" if longest > 60 else "ok"
    return _check("db_conn", "Базы", "Подключения", sev,
                  f"{row.total} всего, {row.active} активных",
                  f"самый долгий запрос — {longest} с" if longest else None)


# ── диск и хранилище ─────────────────────────────────────────────────────────

def check_disk():
    """Свободное место НА ДИСКЕ ХОСТА.

    `/app/uploads` — bind-mount, поэтому `disk_usage` по нему отдаёт файловую систему
    сервера, а не контейнера. Замер 07.09.2026: прод 79 ГБ, свободно 45 (41 %).
    """
    total, used, free = shutil.disk_usage(UPLOADS_ROOT)
    pct = free / total * 100
    sev = "bad" if pct < DISK_CRIT_PCT else "warn" if pct < DISK_WARN_PCT else "ok"
    # Подпись переписана 07.09.2026: было «21% · 139 из 661 ГБ», и владелец справедливо
    # переспросил, 139 — это занято или свободно. На экране состояния двусмысленная цифра
    # хуже отсутствующей: её прочитают наоборот и успокоятся не вовремя.
    return _check("disk", "Диск", "Свободное место", sev,
                  f"свободно {free / 2**30:.0f} ГБ ({pct:.0f}%)",
                  f"занято {used / 2**30:.0f} из {total / 2**30:.0f} ГБ · "
                  f"порог: жёлтый {DISK_WARN_PCT}%, красный {DISK_CRIT_PCT}%")


def _walk_uploads():
    files = {}
    for root, _, names in os.walk(UPLOADS_ROOT):
        for n in names:
            full = os.path.join(root, n)
            try:
                files[os.path.relpath(full, UPLOADS_ROOT).replace("\\", "/")] = os.path.getsize(full)
            except OSError:
                pass
    return files


def check_storage(db: Session):
    files = _walk_uploads()
    total = sum(files.values())
    by_dir = {}
    for rel, size in files.items():
        by_dir[rel.split("/", 1)[0] if "/" in rel else "(корень)"] = \
            by_dir.get(rel.split("/", 1)[0] if "/" in rel else "(корень)", 0) + size
    detail = " · ".join(f"{k} {v / 2**20:.0f} МБ" for k, v in
                        sorted(by_dir.items(), key=lambda x: -x[1])[:6])
    return _check("storage", "Диск", "Хранилище файлов", "ok",
                  f"{len(files)} файлов · {total / 2**20:.0f} МБ", detail)


# Каталоги, файлы в которых НЕ являются сиротами по устройству: на них никто и не
# ссылается. `bx_consolidate` — технический кэш выгрузок Битрикса (замер 07.09.2026: 151
# файл из 162 «сирот»). Без этого исключения счётчик горел бы всегда, а счётчик, который
# горит всегда, перестают читать — и он пропускает настоящую находку.
TECHNICAL_DIRS = {"bx_consolidate"}


def check_orphans(db: Session):
    """Файлы на диске, на которые не ссылается ни одна строка.

    Замер 27.08.2026 давал 77 % объёма — почти всё это выгрузки медиапланов из Битрикса.
    Проверка сторожит не объём, а РОСТ: увеличение числа сирот означает, что где-то
    удаляют строку и забывают файл.

    Песочница считается ПО КАТАЛОГУ: в базе лежит токен, а не каждый распакованный файл,
    и пофайловая сверка объявила бы сиротой весь баннер целиком.
    """
    known = set()
    for table, column in PATH_COLUMNS:
        try:
            for (v,) in db.execute(text(
                    f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL AND {column} <> ''")):
                known.add(str(v).lstrip("/").replace("\\", "/"))
        except Exception:                        # noqa: BLE001 — таблицы может не быть
            db.rollback()
    tokens = set()
    try:
        for (v,) in db.execute(text(
                "SELECT sandbox_token FROM launch_prep_creative_file "
                "WHERE sandbox_token IS NOT NULL")):
            tokens.add(str(v))
    except Exception:                            # noqa: BLE001
        db.rollback()

    files = _walk_uploads()
    orphans, orphan_bytes, technical = 0, 0, 0
    by_dir = {}
    for rel, size in files.items():
        if rel in known or os.path.basename(rel) in known:
            continue
        top = rel.split("/", 1)[0] if "/" in rel else "(корень)"
        if top in TECHNICAL_DIRS:
            technical += 1
            continue
        if rel.startswith("sandbox/") and rel.split("/")[1] in tokens:
            continue
        orphans += 1
        orphan_bytes += size
        by_dir[top] = by_dir.get(top, 0) + 1
    pct = orphan_bytes / max(1, sum(files.values())) * 100
    sev = "warn" if pct > 50 else "ok"
    detail = ", ".join(f"{k}: {v}" for k, v in sorted(by_dir.items(), key=lambda x: -x[1]))
    if technical:
        detail = (detail + " · " if detail else "") + f"технических не в счёт: {technical}"
    return _check("orphans", "Диск", "Файлы без строки в базе", sev,
                  f"{orphans} шт. · {orphan_bytes / 2**20:.0f} МБ ({pct:.0f}%)", detail or None)


# ── фоновые задания ──────────────────────────────────────────────────────────

def _last_run(db: Session, table, started="started_at", finished="finished_at",
              error_col=None, where=None):
    """Последний прогон задания. ¨­⠪á¨á ¤ ­­®© ª®¬ ­¤ë:

WHERE [/R ª ⠫®£] [/Q] [/F] [/T] 蠡«®­...

¯¨ᠭ¨¥:
    ⮡ࠦ ¥â à ᯮ«®¦¥­¨¥ 䠩«®¢, ᮢ¯ ¤ îé¨å á 蠡«®­®¬ ¯®¨᪠.
    ® 㬮«砭¨î ¯®¨áª ¢믮«­ï¥âáï ¢ ⥪ã饬 ª ⠫®£¥ ¨ ¢ ª ⠫®£ å,
    㪠§ ­­ëå ¢ ¯¥६¥­­®© á।ë PATH.

 ࠬ¥âàë:
    /R       ¥ªãàᨢ­ë© ¯®¨áª ¨ ®⮡ࠦ¥­¨¥ 䠩«®¢, ᮮ⢥âáâ¢ãîé¨å
             㪠§ ­­®¬ã 蠡«®­ã, ­ 稭 ï á 㪠§ ­­®£® ª ⠫®£ .

    /Q       ®§¢à â ⮫쪮 ª®¤  ¢ë室  ¡¥§ ®⮡ࠦ¥­¨ï ᯨ᪠
             ­ ©¤¥­­ëå 䠩«®¢ (â¨娩 ०¨¬)

    /F       ⮡ࠦ¥­¨¥ ­ ©¤¥­­ëå 䠩«®¢ ¢ ª ¢ë窠å.

    /T       ⮡ࠦ¥­¨¥ ࠧ¬¥à , ¤ âë ¨ ¢६¥­¨ ¨§¬¥­¥­¨ï ¤«ï ¢á¥å
             ­ ©¤¥­­ëå 䠩«®¢.

    蠡«®­    ¡«®­ ¯®¨᪠ ¤«ï ¨᪮¬ëå 䠩«®¢.
              蠡«®­¥ ¬®¦­® ¨ᯮ«짮¢ âì ¯®¤á⠭®¢®ç­ë¥ §­ ª¨ * ¨ ?.
              ª¦¥ ¬®¦­® § ¤ ¢ âì ª®­áâàãª樨 "$¯¥à:蠡«®­" ¨ "¯ãâì:蠡«®­",
             £¤¥ "¯¥à" ¯।á⠢«ï¥â ¯¥६¥­­ãî á।ë, ¨
             ¯®¨áª ®áãé¥á⢫ï¥âáï ¯® ¯ãâï¬, 㪠§ ­­ë¬ ¢ ¯¥६¥­­®©
             á।ë "¯¥à". â¨ ª®­áâàãª樨 ­¥ ᫥¤ã¥â ¨ᯮ«짮¢ âì
             á ¯ ࠬ¥â஬ /R. à¨ ¯®¨᪥ ª 蠡«®­ã ⠪¦¥
             ¤®¡ ¢«ïîâáï à áè¨७¨ï ¨§ ¯¥६¥­­®© PATHEXT.

     /?      뢮¤ á¯ࠢª¨ ¯® ¨ᯮ«짮¢ ­¨î.

  ਬ¥砭¨¥. â  á«㦥¡­ ï ¯ணࠬ¬  ¢®§¢à 頥â ª®¤ ®訡ª¨ 0, ¥᫨
              ¯®¨áª ¡ë« ãᯥè­ë¬, 1 - ¥᫨ ¡¥§ãᯥè­ë¬, ¨
              2, ¥᫨ ¢®§­¨ª«¨ ®訡ª¨.

ਬ¥àë:
    WHERE /?
    WHERE ¨¬ï_䠩« 1 ¨¬ï_??????.*
    WHERE $windir:*.* 
    WHERE /R c:\windows *.exe *.dll *.bat  
    WHERE /Q ??.??? 
    WHERE "c:\windows;c:\windows\system32:*.dll"
    WHERE /F /T *.dll  — доп. условие отбора.

    Нужно затем, что СУХОЙ прогон тоже пишет строку, и без отсева экран показывал бы
    «рассылка жива» после холостого запуска, ничего не отправившего. Прибор, который
    обязан сообщать о поломке, обманывался бы проверкой этой самой поломки.
    """
    try:
        row = db.execute(text(
            f"SELECT {started} AS s, {finished} AS f"
            + (f", {error_col} AS e" if error_col else ", NULL AS e")
            + f" FROM {table}" + (f" WHERE {where}" if where else "")
            + f" ORDER BY {started} DESC LIMIT 1")).first()
        return row
    except Exception:                            # noqa: BLE001
        db.rollback()
        return None


def check_notify_dispatch(db: Session):
    """Рассылка уведомлений идёт по cron ежечасно. Умрёт cron — замолчит тихо.

    Смотрим факт РЕЗУЛЬТАТА, а не запуска: строка появляется по завершении прогона.
    """
    # Только БОЕВЫЕ прогоны: сухой ничего не отправляет, и засчитывать его за живую
    # рассылку значит гасить единственный сигнал о том, что cron умер.
    row = _last_run(db, "notification_scan_runs", error_col="error",
                    where="NOT dry_run")
    if row is None or row.s is None:
        return _check("job_notify", "Фоновые задания", "Рассылка уведомлений", "idle",
                      "ни одного прогона",
                      "на стенде это норма — cron стоит только на сервере")
    hours = _age(row.f or row.s)
    sev = "bad" if hours > 6 else "warn" if hours > 2 else "ok"
    if row.e:
        sev = "bad"
    # У КРАСНОЙ строки обязано быть последствие словами — это правило экрана, и его
    # держит прибор `test_bad_checks_say_what_it_costs`. Ветка «давно не было прогона»
    # его не ставила, и красное состояние читалось как «job_notify: bad» без объяснения.
    # Поймано 13.09.2026: на стенде cron не ходит, возраст прогона перевалил за 6 часов,
    # и проверка покраснела молча — до этого дня она просто не успевала дойти до bad.
    consequence = None
    if sev == "bad":
        consequence = ("Отложенные уведомления не уходят: человек не узнает о сроке, "
                       "пока не откроет систему сам"
                       if not row.e else
                       "Рассылка падает с ошибкой — очередь копится, письма и сообщения "
                       "не доходят")
    return _check("job_notify", "Фоновые задания", "Рассылка уведомлений", sev,
                  f"{hours:.1f} ч назад", (row.e or "")[:200] or None,
                  consequence=consequence)


def check_bitrix_sync(db: Session):
    row = _last_run(db, "sales_bitrix_sync_log", error_col="error_text")
    if row is None or row.s is None:
        return _check("job_bitrix", "Фоновые задания", "Синхронизация с Битриксом", "idle",
                      "ни одного прогона", "автосинки нет — запускается руками",
                      consequence="Автосинки нет — расхождение с Битриксом растёт молча",
                      # Ведём на экран, где синк запускается, а не дёргаем его отсюда:
                      # это тяжёлая операция, и место ей там, где её подтверждают.
                      action={"label": "Открыть сверку", "href": "/directory/reconcile"})
    hours = _age(row.f or row.s)
    sev = "bad" if row.e else "ok"
    return _check("job_bitrix", "Фоновые задания", "Синхронизация с Битриксом", sev,
                  f"{hours:.0f} ч назад", (row.e or "")[:200] or None)


# ── внешние связи ────────────────────────────────────────────────────────────

def check_external_config():
    """Настроены ли внешние связи. Живой запрос здесь НЕ делается намеренно.

    Дёргать чужие API при каждом открытии экрана — способ получить бан по частоте и
    медленный экран. Живые пробы делает фоновый прогон; здесь видно, чем СЕЙЧАС нельзя
    воспользоваться в принципе, потому что нечем.
    """
    out = []
    # Текст говорит ПОСЛЕДСТВИЕ, а не факт: «отправок не будет» вместо «нет переменной».
    # Кнопки «Открыть .env» здесь НЕТ намеренно — файл лежит на сервере, из браузера его
    # не открыть, и кнопка была бы обещанием, которого интерфейс не выполнит.
    for key, title, names, hurts in (
            ("ext_bitrix", "Битрикс", ("VIBECODE_API_KEY",),
             "Синхронизация со сделками не работает"),
            ("ext_ord", "ОРД", ("ORD_LOGIN", "ORD_PASSWORD"),
             "ЕРИД не выпустить — маркировка встанет"),
            ("ext_dsp", "DSP", ("DSP_API_URL", "DSP_ACCESS_TOKEN", "DSP_PARTNER_XXHASH"),
             "Интеграция не настроена — отправок в DSP не будет"),
            # Weborama не значилась здесь до 11.09.2026, хотя коннектор настроен, работает
            # и на нём держится заведение пикселей. Четыре связи наблюдались, пятая — нет:
            # пропади у неё доступ, экран состояния остался бы зелёным, а заведение
            # молча перестало бы работать. Именно про такие «тихие» отказы и заведён
            # весь этот модуль.
            ("ext_wcm", "Weborama", ("WEBORAMA_EMAIL", "WEBORAMA_PASSWORD"),
             "Пиксели не завести — сверки показов с верификатором не будет"),
            ("ext_tg", "Телеграм", ("TELEGRAM_BOT_TOKEN",),
             "Бот не поднят — уведомления не уйдут"),
            # Почта (13.09.2026). Проверяем ровно те две переменные, без которых гейт
            # считает себя ненастроенным: адрес сервера и адрес отправителя. Логин с
            # паролем бывают пустыми законно — часть ящиков пускает по IP.
            ("ext_mail", "Почта", ("MAIL_SMTP_HOST", "MAIL_FROM"),
             "Письма не уходят — уведомления копятся в очереди, площадкам не написать")):
        missing = [n for n in names if not (os.getenv(n) or "").strip()]
        out.append(_check(key, "Внешние связи", title,
                          "warn" if missing else "ok",
                          "не настроено" if missing else "настроено",
                          ("нет: " + ", ".join(missing)) if missing else None,
                          consequence=hurts if missing else None,
                          keys=missing or None))
    return out


def check_telegram_live():
    """ЖИВАЯ проверка Телеграма: доходит ли запрос, а не задан ли токен.

    Заведена 08.09.2026 после происшествия, которое эта же группа проверок пропустила:
    токен был на месте, экран показал бы зелёное, а бот при этом молчал — связь рвалась
    на сети. Ровно та ошибка, против которой написан заголовок этого модуля: проверять
    РЕЗУЛЬТАТ, а не конфигурацию.

    `getWebhookInfo` выбран намеренно: он и подтверждает связь, и отдаёт то, чего иначе
    не узнать — сколько обновлений Телеграм держит у себя. Растущая очередь означает,
    что до нас не достучались, и НИ ОДИН наш журнал этого не покажет.

    Вызов дешёвый, но всё равно наружу — поэтому идёт только в фоновом прогоне
    (`live=True`), а не при каждом открытии экрана.
    """
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        return _check("tg_live", "Внешние связи", "Телеграм: связь", "idle",
                      "не проверялось", "бот не настроен")
    try:
        # Через тот же прокси, что и отправка: иначе проверка ходила бы другим путём
        # и отчитывалась о связи, которой приложение не пользуется.
        import httpx
        from app.notify import telegram as _tg
        r = httpx.get(_tg.API.format(token=token, method="getWebhookInfo"),
                      timeout=8, proxy=_tg.proxy())
        info = (r.json() or {}).get("result", {}) if r.status_code == 200 else {}
    except Exception as e:                       # noqa: BLE001
        return _check("tg_live", "Внешние связи", "Телеграм: связь", "bad",
                      "не отвечает", str(e)[:160],
                      consequence="Бот недоступен — привязка и уведомления не работают")
    pending = info.get("pending_update_count") or 0
    err = info.get("last_error_message")
    if pending > 5:
        return _check("tg_live", "Внешние связи", "Телеграм: связь", "bad",
                      f"{pending} в очереди", f"последняя ошибка: {err}" if err else None,
                      consequence="Телеграм не может доставить нам обновления — "
                                  "коды привязки до нас не доходят")
    if err:
        return _check("tg_live", "Внешние связи", "Телеграм: связь", "warn",
                      f"{pending} в очереди", f"последняя ошибка: {err}")
    return _check("tg_live", "Внешние связи", "Телеграм: связь", "ok", "очередь пуста")


def check_pub_bot_poll(db):
    """Опрос Телеграма у бота площадок: РАБОТАЕТ ли он, а не настроен ли.

    Заведена 21.09.2026 вместе с самим опросом, и по той же причине, по которой
    08.09.2026 заведена соседняя `check_telegram_live`: та проверка ловила «токен есть,
    экран зелёный, бот молчит» по РАСТУЩЕЙ ОЧЕРЕДИ у Телеграма. Для бота площадок этот
    признак больше не работает вовсе — вебхук снят, очередь у Телеграма всегда пуста,
    и мёртвый крон опроса выглядел бы идеально здоровым.

    Единственный честный признак здесь — когда опрос ПОСЛЕДНИЙ РАЗ поговорил с
    Телеграмом. Отметку ставит сам опрос (`app/notify/tg_poll.py`), в том числе когда
    сообщений не было: важен канал, а не трафик.

    Порог 15 минут при кроне раз в минуту: связь рваная (жив один адрес Телеграма из
    восьми и отвечает через раз), поэтому единичные пропуски — норма, а четверть часа
    тишины — уже поломка.
    """
    from app.notify import telegram
    if not telegram.configured(telegram.PUB):
        return _check("tg_poll_pub", "Внешние связи", "Бот площадок: опрос", "idle",
                      "бот не настроен")
    try:
        from app.notify.tg_poll import last_ok
        seen = last_ok(db, telegram.PUB)
    except Exception as e:                       # noqa: BLE001
        return _check("tg_poll_pub", "Внешние связи", "Бот площадок: опрос", "bad",
                      "не удалось прочитать", str(e)[:160])
    if seen is None:
        return _check("tg_poll_pub", "Внешние связи", "Бот площадок: опрос", "bad",
                      "ни разу не отработал",
                      "крон не поставлен либо не может достучаться до Телеграма",
                      consequence="Площадка жмёт «Старт» в боте и не получает ответа — "
                                  "привязка не проходит, а снаружи это выглядит как "
                                  "«бот сломан»")
    from datetime import datetime
    mins = int((datetime.utcnow() - seen).total_seconds() // 60)
    when = seen.strftime("%d.%m %H:%M")
    if mins > 15:
        return _check("tg_poll_pub", "Внешние связи", "Бот площадок: опрос", "bad",
                      f"молчит {mins} мин", f"последний успешный заход {when} UTC",
                      consequence="Сообщения площадок не забираются — «Старт» остаётся "
                                  "без ответа, коды привязки протухают")
    return _check("tg_poll_pub", "Внешние связи", "Бот площадок: опрос", "ok",
                  f"{mins} мин назад", f"последний заход {when} UTC")


def check_dsp_journal(db_dsp_ok: bool):
    """Последняя отправка в DSP по нашему журналу — работает ли связь на самом деле."""
    if not db_dsp_ok:
        return _check("ext_dsp_last", "Внешние связи", "DSP: последняя отправка", "idle",
                      "журнал недоступен")
    try:
        from app.dsp.db import dsp_engine
        with dsp_engine().connect() as c:
            row = c.execute(text(
                "SELECT ts, ok, error FROM dsp_send_log "
                "WHERE contour = 'prod' ORDER BY ts DESC LIMIT 1")).first()
    except Exception as e:                       # noqa: BLE001
        return _check("ext_dsp_last", "Внешние связи", "DSP: последняя отправка", "idle",
                      "журнал недоступен", str(e)[:150])
    if row is None:
        # «БОЕВЫХ», а не просто «отправок»: запрос выше фильтрует по контуру `prod`, и без
        # этого слова строка читается как «связью не пользовались ни разу», хотя в журнале
        # могут лежать десятки демо-отправок (на стенде 11.09.2026 их 36).
        return _check("ext_dsp_last", "Внешние связи", "DSP: последняя отправка", "idle",
                      "боевых отправок не было")
    hours = _age(row.ts)
    return _check("ext_dsp_last", "Внешние связи", "DSP: последняя отправка",
                  "ok" if row.ok else "bad",
                  f"{hours:.0f} ч назад", (row.error or "")[:200] or None)


# ── конфигурация ─────────────────────────────────────────────────────────────

def check_debug_off():
    on = (os.getenv("DEBUG", "false") or "").lower() == "true"
    return _check("cfg_debug", "Конфигурация", "Swagger закрыт",
                  "bad" if on else "ok",
                  "ОТКРЫТ" if on else "закрыт",
                  "DEBUG=true открывает /docs без аутентификации" if on else None)


# Каталог бэкапов, каким его видит бэкенд (монтируется `:ro`). Вынесен константой,
# чтобы проверку можно было прогнать на временном каталоге: подменять `/app/backups` в
# тесте значит писать в боевой монтаж.
BACKUPS_PATH = "/app/backups"


def check_backup_visibility():
    """Свежесть бэкапа — ОТДЕЛЬНОЙ строкой на каждую базу.

    Проверка существует ради честности экрана: без неё раздел «Бэкапы» просто отсутствовал
    бы, и отсутствие читалось бы как «всё хорошо». Каталог закрывается одной строкой `:ro`
    в compose.

    ОДНА СТРОКА НА ВСЕХ — ВРАЛА (найдено владельцем 15.09.2026). Брался самый свежий файл
    каталога, а бэкап аналитической базы делается в 03:10, через десять минут после
    основной, — то есть «самый свежий» это ВСЕГДА он. Экран показывал дамп dsp_analytics
    на 24 КБ и подписывал его «Последний бэкап»; основной базы на экране не было вовсе.
    Хуже того, по нему же считалась и тревога: упади бэкап основной базы совсем, строка
    осталась бы зелёной — прибор, поставленный ради главного, сообщал бы о второстепенном.

    Разделение по имени файла — то же, что у ротации в `deploy.sh`: `backup_<дата>.sql`
    у основной базы, `backup_dsp_analytics_<дата>.sql` у аналитической. Правило одно на
    два места, и разъехаться им нельзя: там оно решает, что удалять, здесь — о чём
    отчитываться.
    """
    path = BACKUPS_PATH
    if not os.path.isdir(path):
        return [_check("backups", "Бэкапы", "Каталог бэкапов", "idle",
                       "нет доступа",
                       "нужен монтаж каталога только на чтение: "
                       "`${BACKUPS_DIR:-./backups}:/app/backups:ro`",
                       consequence="Бэкенд не видит каталог — проверить восстановление нельзя")]

    files = [f for f in os.listdir(path) if f.endswith((".dump", ".sql"))]
    if not files:
        return [_check("backups", "Бэкапы", "Каталог бэкапов", "bad", "пуст",
                       consequence="Восстанавливать нечем")]

    def newest(pred):
        got = [f for f in files if pred(f)]
        if not got:
            return None
        return max(got, key=lambda f: os.path.getmtime(os.path.join(path, f)))

    DBS = (
        ("backups", "Основная база",
         lambda f: f.startswith("backup_") and not f.startswith("backup_dsp_analytics_")),
        ("backups_dsp", "Аналитическая база (DSP)",
         lambda f: f.startswith("backup_dsp_analytics_")),
    )
    out = []
    for key, title, pred in DBS:
        name = newest(pred)
        if name is None:
            out.append(_check(key, "Бэкапы", title, "bad", "бэкапов нет",
                              "проверьте строку в cron: `deploy.sh backup` для основной, "
                              "`deploy.sh backup dsp_analytics` для аналитической",
                              consequence="Эту базу восстанавливать нечем"))
            continue
        full = os.path.join(path, name)
        hours = (time.time() - os.path.getmtime(full)) / 3600
        size = os.path.getsize(full)
        sev = "bad" if hours > 48 else "warn" if hours > 26 else "ok"
        # Имя файла в подписи — чтобы было видно, ЧЕЙ каталог мы читаем: каталогов
        # бэкапов на проде исторически три, и смонтировать не тот значит получить
        # зелёную строку про чужие старые дампы.
        out.append(_check(key, "Бэкапы", title, sev,
                          f"{hours:.0f} ч назад · {size / 2**20:.1f} МБ · {name}",
                          f"всего файлов в каталоге: {len(files)}"))
    return out


# ── аптайм и ошибки ──────────────────────────────────────────────────────────

# Момент импорта модуля = момент старта процесса. Отдельной зависимости (psutil) ради
# одной цифры не заводим, а `/proc/1` в контейнере показывает старт КОНТЕЙНЕРА, что не
# одно и то же: бэкенд перезапускается и без пересоздания контейнера.
STARTED_AT = datetime.now(timezone.utc)


def started_label() -> str:
    """Момент перезапуска — по Москве, как журнал рядом. `STARTED_AT` в UTC, и подпись
    «перезапуск 23.09 в 22:30» при запуске в 01:30 МСК 24-го путала (ревью 23.09.2026)."""
    from app import timez
    return timez.to_msk(STARTED_AT.replace(tzinfo=None)).strftime("%d.%m в %H:%M")

LOG_PATH = "/app/logs/backend.log"


def uptime() -> dict:
    sec = (datetime.now(timezone.utc) - STARTED_AT).total_seconds()
    d, rem = divmod(int(sec), 86400)
    h, m = divmod(rem // 60, 60)
    return {"seconds": int(sec),
            "human": (f"{d} дн {h:02d}:{m:02d}" if d else f"{h:02d}:{m:02d}"),
            "started_at": STARTED_AT.isoformat()}


def errors_24h() -> dict:
    """Ошибки в логе за сутки — по МЕТКЕ ВРЕМЕНИ строки, а не по всему файлу.

    Файл ротируется по 5 МБ и живёт неделями; счёт по всему файлу отвечал бы на вопрос
    «сколько ошибок было когда-то», а нужен другой: «сколько сейчас».
    """
    # Граница — в ТОМ ЖЕ поясе, что метки строк. С 23.09.2026 процесс живёт по Москве, и
    # `%(asctime)s` пишет московское время; граница от UTC делала «сутки» 27-часовыми.
    from app.timez import msk_now
    cutoff = (msk_now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    n, last = 0, None
    try:
        with open(LOG_PATH, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if " ERROR " not in line:
                    continue
                # Формат строки: «2026-09-07 11:48:12,345 ERROR finance: …»
                if line[:19] >= cutoff:
                    n += 1
                    last = line.strip()[:200]
    except OSError:
        return {"count": None, "last": None}
    return {"count": n, "last": last}


# ── активность ───────────────────────────────────────────────────────────────

def activity(db: Session) -> dict:
    """Пользователи и действия за сутки, по часам.

    Источник — `audit_log`, а НЕ таблица финансовых операций. На экране состояния полезен
    другой вопрос: прошла ли через систему работа вообще. Обрыв активности до нуля в
    рабочий час — признак поломки, а число проведённых операций это бизнес-показатель, и
    его место в сводке руководителя.

    Ряд ВСЕГДА длиной 24 часа, даже если в базе пусто: дырявый ряд рисуется как «данных
    нет», а сплошной с нулями — как «работы не было». Это разные утверждения.
    """
    rows = db.execute(text(
        "SELECT date_trunc('hour', created_at) AS h, "
        "       count(*) AS actions, count(DISTINCT user_id) AS users "
        "FROM audit_log WHERE created_at > now() - interval '24 hours' "
        "GROUP BY 1")).all()
    by_hour = {r.h.replace(tzinfo=None): (r.actions, r.users) for r in rows}

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    series = []
    for i in range(23, -1, -1):
        h = now - timedelta(hours=i)
        a, u = by_hour.get(h, (0, 0))
        series.append({"hour": h.isoformat(), "actions": a, "users": u})

    total = db.execute(text(
        "SELECT count(*) AS actions, count(DISTINCT user_id) AS users "
        "FROM audit_log WHERE created_at > now() - interval '24 hours'")).first()
    return {"users_24h": total.users or 0, "actions_24h": total.actions or 0,
            "series": series}


# ── сборка ───────────────────────────────────────────────────────────────────

# Словарь тонов — ЕДИНСТВЕННЫЙ источник вокабуляра экрана состояния, и `_check`
# сверяется с ним на входе. До 11.09.2026 шесть проверок ставили пятое слово «crit»
# (диск, рассылка, синк Битрикса, DEBUG, возраст бэкапа), которого здесь не было, и
# `collect()` падал с `KeyError` — то есть админский статус отдавал 500 РОВНО ТОГДА,
# когда на него пришли смотреть из-за поломки. Пятое слово убрано, а не добавлено:
# «bad» уже означает худшее, его знают и счётчики ниже, и экран настроек.
WORST = {"bad": 3, "warn": 2, "idle": 1, "ok": 0}


def _disk_bar():
    """Полоса занятости для шапки блока «Диск»: цвет по порогам 80 / 90 % занятости."""
    total, used, free = shutil.disk_usage(UPLOADS_ROOT)
    used_pct = used / total * 100
    return {"used_pct": round(used_pct, 1),
            "used_gb": round(used / 2**30), "total_gb": round(total / 2**30),
            "free_gb": round(free / 2**30), "free_pct": round(free / total * 100)}


def _safe(fn, *args):
    """Проверка, упавшая сама, становится строкой «bad», а не отказом всего экрана.

    ЗАЧЕМ. Экран состояния нужен ровно в плохую минуту, и именно тогда у проверок
    больше всего шансов упасть: база в откате, `/app/uploads` не смонтирован, внешняя
    служба отвечает мусором. До 11.09.2026 любое такое падение поднималось до роутера
    и превращалось в 500 — то есть чем хуже состояние системы, тем меньше про него
    видно. Это тот же дефект, что и «неизвестный тон» в `_check`, только шире.

    Подпись строки-заглушки собирается из имени функции, а не берётся из второго
    списка названий: расходиться нечему, а читать её будут в разборе, а не каждый день.
    """
    try:
        return fn(*args)
    except Exception as e:                       # noqa: BLE001 — причина уходит в detail
        log.exception("Экран состояния: проверка %s упала", fn.__name__)
        return _check(fn.__name__, "Службы", f"Проверка «{fn.__name__}»", "bad",
                      "не выполнена", str(e)[:200],
                      consequence="Об этой части системы сейчас ничего не известно")


def _safe_value(fn, *args, default):
    """То же для не-проверок (KPI, диск, счётчики): пустое значение вместо отказа.

    Строкой в списке проверок они не становятся, поэтому подставляем заведомо «пустой»
    ответ нужной формы — экран покажет прочерк, а не 500."""
    try:
        return fn(*args)
    except Exception:                            # noqa: BLE001
        log.exception("Экран состояния: %s не посчиталось", fn.__name__)
        return default


def collect(db: Session, live: bool = False) -> dict:
    # ПОРЯДОК ВАЖЕН: `check_core_db` идёт первой и делает `rollback()`, если база
    # ответила ошибкой, — иначе все запросы ниже падали бы на мёртвой транзакции.
    checks = [_safe(check_core_db, db)]
    dsp = _safe(check_dsp_db)
    checks.append(dsp)
    checks += [_safe(check_pdf), _safe(check_cabinet),
               _safe(check_db_sizes, db), _safe(check_db_connections, db),
               _safe(check_disk), _safe(check_storage, db), _safe(check_orphans, db),
               _safe(check_notify_dispatch, db), _safe(check_bitrix_sync, db)]
    ext = _safe(check_external_config)
    checks += ext if isinstance(ext, list) else [ext]
    checks.append(_safe(check_dsp_journal, dsp["tone"] == "ok"))
    # Читает только нашу базу, наружу не ходит — поэтому в обычном прогоне, а не в
    # живом: поломку опроса надо видеть сразу при открытии экрана, а не раз в час.
    checks.append(_safe(check_pub_bot_poll, db))
    # Живые запросы наружу — только по явному запросу (фоновый прогон раз в час).
    # Дёргать чужие сервисы при каждом открытии экрана — способ получить бан по частоте.
    if live:
        checks.append(_safe(check_telegram_live))
    checks.append(_safe(check_debug_off))
    # Бэкапы отдают СПИСОК — по строке на базу (см. докстроку проверки).
    bk = _safe(check_backup_visibility)
    checks += bk if isinstance(bk, list) else [bk]

    worst = max((WORST[c["tone"]] for c in checks), default=0)
    act = _safe_value(activity, db, default={"actions_24h": 0, "users_24h": 0})
    errs = _safe_value(errors_24h, default={"count": None})
    up = uptime()
    disk = _safe_value(_disk_bar, default={"used_gb": 0, "total_gb": 0,
                                           "free_gb": 0, "free_pct": 0})

    ok_n = sum(1 for c in checks if c["tone"] == "ok")
    need_setup = sum(1 for c in checks if c["tone"] in ("warn", "idle"))
    broken = sum(1 for c in checks if c["tone"] == "bad")

    core = next((c for c in checks if c["key"] == "db_core"), None)
    pdf = next((c for c in checks if c["key"] == "pdf"), None)
    cab = next((c for c in checks if c["key"] == "cabinet"), None)

    # KPI — шесть значений одной строкой. Каждое СЧИТАЕТСЯ из проверок выше, а не
    # запрашивается заново: второй источник того же числа разъехался бы с первым.
    kpi = [
        {"key": "passed", "label": "Проверок пройдено",
         "value": f"{ok_n} / {len(checks)}",
         "hint": (f"{need_setup} требуют настройки" if need_setup else "все зелёные")
                 + (f" · отказов {broken}" if broken else "")},
        {"key": "uptime", "label": "Аптайм бэкенда", "value": up["human"],
         "hint": "перезапуск " + started_label()},
        {"key": "db", "label": "Ответ базы", "value": (core or {}).get("value") or "—",
         "hint": f"сайдкар {(pdf or {}).get('value') or '—'} · "
                 f"кабинет {(cab or {}).get('value') or '—'}"},
        {"key": "disk", "label": "Диск свободно",
         "value": f"{disk['free_gb']} ГБ · {disk['free_pct']}%",
         "hint": f"порог жёлтый {DISK_WARN_PCT}%"},
        {"key": "actions", "label": "Действий за сутки", "value": str(act["actions_24h"]),
         "hint": f"{act['users_24h']} пользователя"},
        {"key": "errors", "label": "Ошибок за сутки",
         "value": "—" if errs["count"] is None else str(errs["count"]),
         "hint": "в логе бэкенда"},
    ]

    return {
        "checked_at": datetime.now(timezone.utc),
        "overall": {3: "bad", 2: "warn", 1: "idle", 0: "ok"}[worst],
        "checks": checks,
        "kpi": kpi,
        "disk": disk,
        "uptime": up,
        "errors": errs,
        "activity": act,
        # Очередь «требует внимания» — срез тех же проверок, а не второй список. Второй
        # источник разъехался бы с первым, и экран показывал бы одно, а очередь другое.
        "alerts": [c for c in checks if c["tone"] in ("bad", "warn", "idle")],
    }
