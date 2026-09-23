# -*- coding: utf-8 -*-
"""Прибор: любую миграцию можно накатить повторно без потерь (аудит 23.09.2026, 8.H2–8.H3).

Два случая, где повтор портил данные:
  · `2026-09-01_traffic_catalog.sql` делал `DELETE FROM publisher_block;` без условия — второй
    накат стирал каталог блоков, по которому работают балансировщик и сборка РК. А учёт
    накатов помечал файл «НЕ ПРОВЕРЕНО», то есть прямо приглашал накатить его «ещё раз»;
  · ранние файлы кабинета пересоздавали представления в редакции 28.08 — повтор откатывал
    их к старой форме, а `CREATE OR REPLACE VIEW` без `WITH (security_barrier)` снимал барьер.

Держим статически, по тексту миграций:
  1. `DELETE` / `UPDATE` без `WHERE` на ВЕРХНЕМ уровне оператора — в том числе после `WITH`;
     `WHERE` внутри подзапроса не в счёт;
  2. `TRUNCATE` — никогда вне условного `DO`;
  3. `DROP VIEW pub.…` — только внутри условного `DO`;
  4. каждое представление кабинета (`CREATE [OR REPLACE] VIEW pub.…`) несёт `security_barrier`.
`DO`-блок с `IF` считается условным: его условие видно глазами. `DO` без `IF` проверяется по
тем же правилам изнутри — дефект, завёрнутый в `DO $$ … $$`, раньше проходил.

Чего прибор НЕ ловит и не может: `WHERE` не гарантирует идемпотентности. Бэкфилл «включить
уведомления основному контакту, AND NOT notify» при повторе включал их тем, кто выключил
вручную (`2026-09-14_contact_notify`, ревью 23.09.2026). Такой бэкфилл пишется внутри `DO`
с признаком первого наката — обычно «колонки ещё нет».
"""
import pathlib
import re

import pytest

MIG = pathlib.Path(__file__).resolve().parent.parent / "migrations"

DOLLAR = re.compile(r"\$[A-Za-z_]*\$")


def _statements(sql: str):
    """Операторы файла без комментариев. Тело в долларовых кавычках (`$$`, `$mig$`, `$ddl$`)
    — одним куском: до ревью 23.09.2026 разбор знал только `$$`, и `$tag$` его ломал."""
    sql = re.sub(r"--[^\n]*", "", sql)
    out, buf, tag, i = [], [], None, 0
    while i < len(sql):
        m = DOLLAR.match(sql, i)
        if m:
            t = m.group(0)
            if tag is None:
                tag = t
            elif t == tag:
                tag = None
            buf.append(t)
            i = m.end()
            continue
        if sql[i] == ";" and tag is None:
            out.append("".join(buf).strip())
            buf = []
        else:
            buf.append(sql[i])
        i += 1
    if "".join(buf).strip():
        out.append("".join(buf).strip())
    return [st for st in out if st]


def _top_level(st: str) -> str:
    """Оператор без содержимого скобок: `WHERE` подзапроса не делает условным сам UPDATE."""
    depth, keep = 0, []
    for ch in st:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0:
            keep.append(ch)
    return " " + " ".join("".join(keep).upper().split()) + " "


def _do_body(st: str) -> str:
    m = DOLLAR.search(st)
    if not m:
        return ""
    end = st.find(m.group(0), m.end())
    return st[m.end():end if end > 0 else len(st)]


def _problems(st: str) -> list:
    head = " ".join(st.split()).upper()
    if head.startswith(("DO ", "DO$")):
        body = _do_body(st)
        if re.search(r"\bIF\b", body, re.I):
            return []
        inner = _statements(body.replace("BEGIN", ";", 1))
        return [p for s in inner for p in _problems(s)]
    bad = []
    if head.startswith("TRUNCATE"):
        bad.append("TRUNCATE")
    top = _top_level(st)
    verb = re.search(r"\b(UPDATE|DELETE\s+FROM)\b", top)
    if (verb and head.startswith(("UPDATE", "DELETE", "WITH"))
            and " WHERE " not in top[verb.end():]):
        bad.append("UPDATE/DELETE без WHERE")
    if re.match(r"DROP\s+VIEW\s+(IF\s+EXISTS\s+)?PUB\.", head):
        bad.append("DROP VIEW pub.* вне условного DO")
    return bad


def _files():
    return sorted(MIG.rglob("*.sql"))


def test_statements_are_found():
    assert len(_files()) > 50


def test_no_statement_that_a_rerun_would_repeat_destructively():
    bad = []
    for f in _files():
        for st in _statements(f.read_text(encoding="utf-8")):
            for p in _problems(st):
                bad.append(f"{f.name}: {p}: {' '.join(st.split())[:90]}")
    assert not bad, "повторный накат сотрёт/перепишет:\n  " + "\n  ".join(bad)


@pytest.mark.parametrize("sql", [
    "DELETE FROM publisher_block",
    "UPDATE t SET a = 1",
    "UPDATE t SET a = (SELECT b FROM u WHERE u.id = t.id)",   # WHERE только в подзапросе
    "WITH x AS (SELECT 1) UPDATE t SET a = 1",
    "TRUNCATE publisher_block",
    "DROP VIEW IF EXISTS pub.task_v1",
    "DO $$ BEGIN DELETE FROM publisher_block; END $$",
    "DO $mig$ BEGIN UPDATE t SET a = 1; END $mig$",
])
def test_the_gate_sees_what_it_promises(sql):
    """Прибор на прибор: каждое обещанное правило ловит свой образец."""
    assert any(_problems(st) for st in _statements(sql + ";")), sql


@pytest.mark.parametrize("sql", [
    "UPDATE t SET a = 1 WHERE a IS NULL",
    "WITH x AS (SELECT 1) UPDATE t SET a = 1 FROM x WHERE t.id = 1",
    "DO $m$ BEGIN IF NOT EXISTS (SELECT 1) THEN DELETE FROM t; DROP VIEW pub.x; END IF; END $m$",
])
def test_the_gate_lets_conditional_statements_pass(sql):
    assert not any(_problems(st) for st in _statements(sql + ";")), sql


def test_do_block_without_if_is_not_excused_by_a_word_containing_if():
    """`\\bIF\\b`, а не подстрока: `DO $$ … notify … $$` без условия — не условный блок."""
    st = "DO $$ BEGIN UPDATE t SET notify = true; END $$;"
    assert any(_problems(s) for s in _statements(st))


FUNC_RE = re.compile(r"^CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+([a-z_][\w.]*)", re.I)


def _unconditional_functions(sql: str) -> set:
    """Функции, которые файл создаёт БЕЗ условия (не внутри `DO … IF …`)."""
    return {m.group(1).lower() for st in _statements(sql)
            if (m := FUNC_RE.match(" ".join(st.split())))}


def test_only_the_latest_file_redefines_a_function():
    """Функцию, которую уточняет более поздняя миграция, ранняя создаёт только если её нет.

    Ревью 23.09.2026: повторный накат `2026-08-28_publisher_cabinet.sql` вернул
    `pub.touch_login` к редакции 28.08 — без записи входа площадки в журнал кабинета
    (её добавил `2026-08-30_cabinet_login_writes_journal.sql`). Ошибок никаких, журнал
    входов молча перестал пополняться. Гейт смотрел представления, а функции — нет.
    """
    by_func: dict = {}
    for f in _files():
        for fn in _unconditional_functions(f.read_text(encoding="utf-8")):
            by_func.setdefault(fn, []).append(f.name)
    bad = [f"{fn}: безусловно в {', '.join(files[:-1])}, уточняется в {files[-1]}"
           for fn, files in sorted(by_func.items()) if len(files) > 1]
    assert not bad, ("повторный накат ранней миграции откатит функцию к старой редакции — "
                     "оберните её создание в `DO … IF NOT EXISTS (pg_proc) …`:\n  "
                     + "\n  ".join(bad))


def test_cabinet_views_keep_the_barrier():
    bad = []
    for f in _files():
        text = re.sub(r"--[^\n]*", "", f.read_text(encoding="utf-8"))
        for m in re.finditer(r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(pub\.\w+)([^;]*?)\bAS\b",
                             text, re.I):
            if "security_barrier" not in m.group(2).lower():
                bad.append(f"{f.name}: {m.group(1)}")
    assert not bad, "представление кабинета без security_barrier:\n  " + "\n  ".join(bad)
