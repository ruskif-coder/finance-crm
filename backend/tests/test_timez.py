# -*- coding: utf-8 -*-
"""Время: в базе UTC, человеку — Москва.

Правило выведено замером 14.09.2026, а не принято по вкусу: контейнеры и postgres жили
в UTC (`TZ` не была задана ни у одного сервиса, `now()` отдаёт `+00`), а люди в Москве.
С 23.09.2026 в Москву переведён и сам процесс бэкенда — база осталась в UTC, и почему
именно так, сказано в приборах внизу файла.

Нарушение этого правила тихое в обе стороны — время выглядит настоящим, просто не тем, —
и за один разбор нашлось в четырёх местах:

* шапка письма показывала UTC: получатель видел время на три часа в прошлом;
* тихие часы ПЛОЩАДОК (21:00–09:00) считались от UTC и работали с 00:00 до 12:00 —
  письмо в 23:00 уходило ночью, утреннее ждало до полудня;
* тихие часы СОТРУДНИКОВ — тот же дефект: заданные 22:00–08:00 работали как 01:00–11:00;
* штампы выгрузок («Выгружено 14.09.2026 19:25») и имена файлов — тоже UTC.

Приборы ниже держат каждую из этих четырёх точек.
"""
import inspect
from datetime import datetime, timedelta

from app import timez
from app.notify import channels
from app.notify.outward import schedule as sc


class _Ch:
    """Каналы сотрудника с заданными тихими часами. Своего класса-заглушки не избежать:
    настоящая строка требует пользователя, профиля и подписки, а проверяется здесь
    арифметика часа."""
    def __init__(self, a, b):
        self.quiet_from, self.quiet_to, self.mute_until = a, b, None


class _Ev:
    locked = False


def test_msk_is_three_hours_ahead_of_utc():
    assert timez.MSK_OFFSET == 3
    d = datetime(2026, 9, 14, 19, 30)
    assert timez.to_msk(d) == datetime(2026, 9, 14, 22, 30)
    assert abs((timez.msk_now() - datetime.utcnow()).total_seconds()
               - 3 * 3600) < 2


def test_employee_quiet_hours_are_moscow(monkeypatch):
    """Тихие часы сотрудника считаются по московскому часу.

    Человек ставит 22:00–08:00, имея в виду свои вечер и утро. Пока час брался из
    `datetime.now()` контейнера, окно работало с 01:00 до 11:00: письмо в 23:00
    приходило ночью, а в 10:00 — не приходило вовсе.
    """
    ch = _Ch(22, 8)
    cases = [(23, True), (2, True), (7, True), (9, False), (14, False), (21, False)]
    for msk_hour, expected in cases:
        fake = datetime(2026, 9, 14, msk_hour, 30)
        monkeypatch.setattr(timez, "msk_now", lambda f=fake: f)
        monkeypatch.setattr(channels.timez, "msk_now", lambda f=fake: f)
        got = channels.quiet_now(ch, _Ev())
        assert got is expected, f"{msk_hour}:30 МСК — ожидалось тихо={expected}"


def test_publisher_quiet_hours_are_utc_in_and_moscow_by_meaning():
    """У площадок вход UTC, а смысл — московский (плюс её собственное смещение).

    Проверяется та пара часов, где ошибка видна в обе стороны: днём и глубокой ночью
    разницы не заметно, а на границах она и живёт.
    """
    # 23:00 МСК = 20:00 UTC — ночь, письмо ждёт утра
    assert sc.due_at(datetime(2026, 9, 14, 20), 0, immediate=False) is not None
    # 09:30 МСК = 06:30 UTC — тихие часы кончились
    assert sc.due_at(datetime(2026, 9, 14, 6, 30), 0, immediate=False) is None


def test_nothing_shows_container_time_to_a_human():
    """Ратчет: `datetime.now()` не возвращается в код.

    С 23.09.2026 причина стала ровно обратной, а запрет — строже. Раньше внутри
    контейнера это было UTC: для показа врало на три часа, а для записи случайно
    совпадало с `utcnow()`. Теперь процесс живёт по Москве (`timez.set_process_timezone`,
    зовётся первой строкой `main.py`), и совпадение кончилось: записанный в колонку
    `datetime.now()` встанет московским числом рядом с гринвичскими соседями. Различить
    их потом нечем — оба выглядят правдой.

    Для показа `timez.msk_now()`, для записи `datetime.utcnow()`.

    Смотрим ДЕРЕВО, а не текст. Регулярка краснела на строке документации в самом
    `timez.py`, где этот вызов только упомянут; сторож, краснеющий на объяснении, почему
    так делать нельзя, — сторож, которому перестают верить. Вызов С АРГУМЕНТОМ
    (`datetime.now(timezone.utc)`) разрешён: там пояс задан явно.
    """
    import ast
    from pathlib import Path

    app = Path(__file__).resolve().parent.parent / "app"
    stray = []
    for p in app.rglob("*.py"):
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or node.args or node.keywords:
                continue
            f = node.func
            if (isinstance(f, ast.Attribute) and f.attr == "now"
                    and isinstance(f.value, ast.Name)
                    and f.value.id in ("datetime", "dt", "_dt")):
                stray.append(f"{p.relative_to(app)}:{f.lineno}")
    assert not stray, ("datetime.now() — московское время в гринвичской колонке: "
                       + ", ".join(stray))


def test_letter_default_time_is_moscow():
    """Умолчание времени в письме — московское. Параметр можно забыть, и подставиться
    должно правильное."""
    src = inspect.getsource(__import__("app.mail.render", fromlist=["x"]))
    assert "when = when or msk_now()" in src
    assert "when = when or datetime.now()" not in src


def test_quiet_hours_window_crosses_midnight_for_employees():
    """Окно через полночь: 23 больше начала, 3 меньше конца, оба тихие. Обычное
    сравнение `a <= h < b` даёт здесь ровно наоборот — тихим становится день."""
    ch = _Ch(21, 9)
    quiet = []
    for h in range(24):
        fake = datetime(2026, 9, 14, h)
        import app.notify.channels as c
        orig = c.timez.msk_now
        c.timez.msk_now = lambda f=fake: f
        try:
            if c.quiet_now(ch, _Ev()):
                quiet.append(h)
        finally:
            c.timez.msk_now = orig
    assert quiet == [0, 1, 2, 3, 4, 5, 6, 7, 8, 21, 22, 23]


def test_mute_until_uses_the_moscow_day():
    """«Не беспокоить до» — по московскому календарю: первые три часа суток по UTC
    ещё вчерашние, и молчание кончалось бы на три часа позже обещанного."""
    src = inspect.getsource(channels.quiet_now)
    assert "date.today()" not in src, "день берётся из UTC"
    assert "now.date()" in src


def test_db_writes_stay_utc():
    """В базу пишется `utcnow()`. Колонки наивные, и смешать в них две шкалы значит
    получить сортировку, в которой вечер идёт раньше утра."""
    now_utc = datetime.utcnow()
    assert abs((now_utc - (timez.msk_now() - timedelta(hours=3))).total_seconds()) < 2


# ─── Пояс самого процесса (23.09.2026) ────────────────────────────────────────────
#
# До этой даты перевод `to_msk` чинил только те места, где о нём вспомнили. Оставался
# третий вид времени, который никто не переводил, потому что он и не выглядит временем:
# `date.today()` — «сегодня». В контейнере без пояса это сегодня ПО ГРИНВИЧУ, то есть с
# полуночи до трёх ночи по Москве система считала, что ещё вчера. Тридцать шесть мест:
# срочность задач, просрочка бэклога, границы флайта, дата подтверждения приложения к
# договору, имя выгружаемого файла. Туда же уходили метки в `backend.log`.
#
# Ошибка жила три часа в сутки и всегда была правдоподобной: дата настоящая, просто
# вчерашняя. Днём невоспроизводима — поэтому и не находилась.

def test_process_lives_in_moscow():
    """Местное время процесса — московское.

    Установку зовём явно: тесты поднимают не `main.py`, а модули по отдельности, и без
    этого прибор проверял бы пояс запуска pytest, а не тот, что ставит приложение.
    """
    import time
    timez.set_process_timezone()
    assert datetime.now().hour == timez.msk_now().hour, "tzname=%r" % (time.tzname,)


def test_today_is_the_moscow_day():
    """«Сегодня» — московское. Ровно то, что ломалось с полуночи до трёх ночи."""
    from datetime import date
    timez.set_process_timezone()
    assert date.today() == timez.msk_now().date()


def test_moscow_timezone_did_not_move_the_database_clock():
    """Инвариант колонок: python и postgres по-прежнему в ОДНОМ поясе.

    Ради этого пояс базы и не трогали. Семьдесят три колонки заполняет postgres
    (`server_default=func.now()`), остальные — python (`utcnow()`). Сдвинь одну из
    половин — и в одной колонке окажутся строки из разных поясов; разделить их задним
    числом будет нечем, это не чинится, а переписывается.

    Сверяемся с живой базой, а не сами с собой: своя арифметика сошлась бы и в случае,
    когда обе стороны уехали вместе.
    """
    from sqlalchemy import text

    from app.database import SessionLocal
    timez.set_process_timezone()
    db = SessionLocal()
    try:
        db_now = db.execute(text("SELECT now() AT TIME ZONE 'UTC'")).scalar()
        drift = abs((datetime.utcnow() - db_now).total_seconds())
    finally:
        db.close()
    assert drift < 120, ("python и postgres разошлись на %.0f c: utcnow=%s, now()=%s"
                         % (drift, datetime.utcnow(), db_now))


def test_timezone_is_set_before_logging_is_configured():
    """Пояс ставится РАНЬШЕ настройки логирования.

    `%(asctime)s` берёт местное время процесса, но `basicConfig` закрепляет обработчики:
    строка, записанная после него, уже не переедет. Порядок строк в `main.py` здесь и
    есть механизм — переставь их местами, и журнал молча вернётся к Гринвичу, тогда как
    всё остальное останется верным. То есть поломка коснётся ровно того, ради чего всё
    и делалось, и не покраснеет больше нигде.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "app" / "main.py").read_text(
        encoding="utf-8")
    assert src.index("set_process_timezone()") < src.index("logging.basicConfig")


def test_child_process_inherits_the_timezone():
    """Пояс достаётся и дочерним процессам, а не только тому, кто его поставил.

    Проверка отдельная: `TZ` кладётся в окружение процесса, наследование ожидаемо, но
    при переходе на несколько воркеров журнал одного из них мог бы тихо уехать на три
    часа — а различить два журнала по времени никто не станет.
    """
    import subprocess
    import sys

    timez.set_process_timezone()
    out = subprocess.run([sys.executable, "-c", "import time; print(time.tzname[0])"],
                         capture_output=True, text=True, timeout=60)
    assert out.stdout.strip() == "MSK", "дочерний процесс: %r" % out.stdout.strip()


def test_audit_day_filter_covers_the_moscow_night():
    """Фильтр журнала по дню берёт МОСКОВСКИЕ сутки — проверяется САМА РУЧКА.

    Это НЕ чинится поясом процесса, и потому проверяется отдельно: `created_at` лежит в
    UTC, а человек выбирает московский календарный день. Сравнение в лоб отдавало сутки
    по Гринвичу — события с 00:00 до 03:00 уезжали в следующий день, вечерние с 21:00
    приходили из предыдущего. Три часа журнала каждые сутки лежали не в своей дате, и
    выглядело это не ошибкой, а тем, что ночью ничего не делали.

    Первая редакция повторяла арифметику фильтра у себя и называла это проверкой
    ручки — перепиши кто-нибудь ручку, прибор остался бы зелёным (найдено внешним
    аудитом 23.09.2026). Теперь зовётся `get_audit_log`, и граница проверяется с ОБЕИХ
    сторон: ночное событие попадает в свои сутки и НЕ попадает в соседние.
    """
    from datetime import date

    from app.database import SessionLocal
    from app.models import AuditLog, User
    from app.routers.users import get_audit_log

    db = SessionLocal()
    try:
        who = db.query(User).order_by(User.id).first()
        # 01:00 по Москве 14-го — это 22:00 13-го по Гринвичу.
        db.add(AuditLog(user_id=None, user_name="прибор пояса", action="tz_probe",
                        entity_type="tz", created_at=datetime(2026, 9, 13, 22, 0)))
        db.flush()          # видно ручке в той же сессии; в базе не остаётся — ниже откат

        def found(day):
            res = get_audit_log(skip=0, limit=10, action="tz_probe", user_id=None,
                                date_from=day, date_to=day, db=db, current_user=who)
            return res["total"]

        assert found(date(2026, 9, 14)) == 1, "ночное событие выпало из своих суток"
        assert found(date(2026, 9, 13)) == 0, "ночное событие попало во вчера"
    finally:
        db.rollback()
        db.close()


def test_backlog_sorts_a_row_without_creation_time():
    """Строка бэклога без `created_at` не роняет список.

    Сортировка брала `created.timestamp()`, подставляя `datetime.min` вместо пустого.
    У наивной даты `.timestamp()` читает её как местное время, и в московском поясе
    нулевой год уезжает за край календаря: «year 0 is out of range». Одна такая строка —
    и весь экран «Бэклог отладки» отвечает ошибкой. Поломку внёс перевод процесса в
    Москву; до него тот же код работал (найдено внешним аудитом 23.09.2026).
    """
    from app.routers.backlog import _sort_key

    timez.set_process_timezone()
    rows = [
        {"status": "open", "overdue": False, "severity": "low", "created_at": None},
        {"status": "open", "overdue": False, "severity": "low",
         "created_at": datetime(2026, 9, 1)},
        {"status": "open", "overdue": False, "severity": "low",
         "created_at": datetime(2026, 9, 20)},
    ]
    got = sorted(rows, key=_sort_key)
    # Свежие выше, строка без даты — в самом конце.
    assert [r["created_at"] for r in got] == [
        datetime(2026, 9, 20), datetime(2026, 9, 1), None]


def test_no_naive_timestamp_calls():
    """Ни одного `.timestamp()` в коде.

    Тот же класс, что и голый `datetime.now()`, только тише: `.timestamp()` у наивной
    даты читает её как МЕСТНОЕ время процесса. Пока процесс жил в UTC, это совпадало с
    правдой; с переходом на Москву каждое такое место тихо сдвинулось на три часа, а
    одно — упало. Мой разбор рисков перед переводом искал только `now()` и эти два
    места пропустил; нашёл их внешний аудит. Чтобы пропуск не повторился, запрет
    структурный. Секунды — `time.time()`, разница дат — вычитанием.
    """
    import ast
    from pathlib import Path

    app = Path(__file__).resolve().parent.parent / "app"
    stray = []
    for p in app.rglob("*.py"):
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "timestamp" and not node.args):
                stray.append(f"{p.relative_to(app)}:{node.lineno}")
    assert not stray, ("`.timestamp()` читает наивную дату как московскую: "
                       + ", ".join(stray))
