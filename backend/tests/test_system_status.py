# -*- coding: utf-8 -*-
"""Экран «Статус»: сам не падает и не врёт зелёным.

Пробел, найденный при прогоне 08.09.2026: у 19 проверок и ручки `/api/system/status`
не было ни одного прибора. Экран, который обязан сообщать о поломках, — последнее место,
где уместно узнавать о собственной поломке от пользователя.

Держим три свойства, каждое из которых уже ломалось в проекте или прямо рядом:

1. **сбор не роняет запрос.** Проверки ходят в базы, файловую систему и по сети; любая
   может отказать, и отказ ОДНОЙ обязан оставаться строкой в списке, а не 500-й на весь
   экран. Иначе упавший сервис прячет от нас все остальные;
2. **каждая проверка представлена целиком** — ключ, группа, заголовок и один из четырёх
   тонов. Тон `idle` заведён отдельно от `ok` намеренно: «данных нет, и это нормально» —
   не то же самое, что «всё хорошо»;
3. **счётчик KPI считается из тех же проверок**, а не запрашивается заново. Второй
   источник одного числа в этом проекте расходился уже трижды.

Живые запросы наружу (`live=True`) здесь НЕ дёргаем: тест не должен зависеть от того,
отвечает ли сегодня Телеграм.
"""
import app.ad.models           # noqa: F401
import app.launch_prep.models  # noqa: F401
import app.ord.models          # noqa: F401
import pytest

from app.database import SessionLocal
from app.system import status as st

TONES = {"ok", "warn", "bad", "idle"}


@pytest.fixture(scope="module")
def out():
    db = SessionLocal()
    try:
        yield st.collect(db, live=False)
    finally:
        db.close()


def test_collect_survives_whatever_is_down(out):
    """Сбор отработал целиком. Падение одной проверки не имеет права снести экран."""
    assert out["checks"], "проверок нет вовсе — экран покажет пустоту вместо состояния"
    assert len(out["checks"]) >= 15, f'проверок стало {len(out["checks"])} — часть потерялась'


def test_every_check_is_complete_and_uses_a_known_tone(out):
    """Неполная строка = строка, которую человек не сможет прочитать."""
    for c in out["checks"]:
        for field in ("key", "group", "title", "tone"):
            assert c.get(field), f'у проверки нет поля {field}: {c}'
        assert c["tone"] in TONES, f'{c["key"]}: неизвестный тон {c["tone"]}'


def test_check_keys_are_unique(out):
    """Ключ — адрес строки: по нему её ищут в истории состояний и в оповещениях."""
    keys = [c["key"] for c in out["checks"]]
    dupes = {k for k in keys if keys.count(k) > 1}
    assert not dupes, f'ключи проверок задвоились: {dupes}'


def test_kpi_counter_matches_the_checks(out):
    """«Проверок пройдено X / N» считается из списка, а не отдельным запросом."""
    passed = next((k for k in out["kpi"] if k["key"] == "passed"), None)
    assert passed, 'в KPI нет счётчика пройденных проверок'
    ok_n = sum(1 for c in out["checks"] if c["tone"] == "ok")
    assert passed["value"] == f'{ok_n} / {len(out["checks"])}', (
        'счётчик разошёлся со списком проверок — верный признак второго источника числа'
    )


def test_bad_checks_say_what_it_costs(out):
    """У красной строки обязано быть последствие словами.

    «db_core: bad» без объяснения заставляет гадать; смысл экрана в том, чтобы человек
    понял, что именно у него сейчас не работает.
    """
    silent = [c["key"] for c in out["checks"]
              if c["tone"] == "bad" and not (c.get("consequence") or c.get("note"))]
    assert not silent, f'красные проверки без объяснения последствий: {silent}'


# ── вокабуляр тонов: прибор, которого не хватило ─────────────────────────────
#
# Тест выше проверяет тона У ПОЛУЧЕННЫХ строк — и потому молчал, пока шесть проверок
# ставили пятое слово «crit»: на стенде ни одна из них в это состояние не попадала
# (диск в норме, каталог бэкапов не смонтирован, DEBUG выключен). А в бою `collect()`
# падал с `KeyError` ровно в плохую минуту. Разбор внешнего аудита 11.09.2026.
#
# Поэтому проверяем ИСХОДНИК, а не прогон: любое слово-тон, способное доехать до
# `_check`, обязано быть известно словарю. Так дефект ловится независимо от того,
# в каком состоянии стенд.

def test_tone_vocabulary_is_one_dictionary():
    """`WORST` и ожидания приборов — один и тот же словарь, а не две копии."""
    assert set(st.WORST) == TONES


def test_no_check_can_pass_an_unknown_tone():
    """Статический обход: у каждого вызова `_check` четвёртый аргумент — известный тон.

    Разбираем и тернарники (`"bad" if on else "ok"`), и присваивания `sev = ...`:
    именно так шесть раз и было записано «crit».
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(st))
    unknown = []

    def literals(node):
        return [n.value for n in ast.walk(node)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]

    for node in ast.walk(tree):
        # 1) прямой вызов _check(key, group, title, ТОН, ...)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "_check" and len(node.args) >= 4):
            for value in literals(node.args[3]):
                if value not in TONES:
                    unknown.append((node.lineno, value))
        # 2) sev = "..." / sev = "..." if ... else "..."
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "sev" in names:
                for value in literals(node.value):
                    if value not in TONES:
                        unknown.append((node.lineno, value))

    assert not unknown, (
        "В status.py есть тона вне словаря WORST — collect() упадёт на них с KeyError: "
        + ", ".join(f"строка {line}: {value!r}" for line, value in unknown))


def test_unknown_tone_degrades_to_bad_instead_of_crashing():
    """Если чужое слово всё-таки появится — экран обязан остаться живым.

    Падение здесь недопустимо: статус нужен как раз тогда, когда что-то сломано.
    """
    row = st._check("k", "Группа", "Заголовок", "совершенно новый тон")
    assert row["tone"] == "bad"
    assert st.WORST[row["tone"]] == max(st.WORST.values())
