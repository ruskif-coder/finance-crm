# -*- coding: utf-8 -*-
"""Прибор: факт на дашборде не должен смешивать наш счётчик с чужим измерением.

Находка родилась раньше поломки, и это редкий случай, когда прибор ставится ДО неё.
`ad_campaign_stat` с самого начала ключуется по `(РК, площадка, дата, источник)` — то
есть рассчитана на несколько источников одного дня. При этом все шесть запросов к ней в
дашборде трафика суммировали строки без разбора источника. Пока источник был один, это
было незаметно; первая же запись статистики верификатора удвоила бы факт, и число
осталось бы правдоподобным.

Поэтому здесь не проверка расчёта, а проверка ФОРМЫ ЗАПРОСА: любой SQL, читающий
`ad_campaign_stat`, обязан упомянуть источник. Тест смотрит на строковые константы во
всём `app/`, а не на конкретные функции, — иначе седьмой запрос, написанный завтра,
проедет мимо прибора.
"""
import ast
import pathlib

from app.ad.stat_sources import KNOWN, OWN, VERIFIER, fact_sources, is_verifier

APP = pathlib.Path(__file__).resolve().parent.parent / "app"

TABLE = "ad_campaign_stat"


def _sql_literals():
    """Все строковые константы в app/, похожие на SQL по этой таблице."""
    out = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                s = node.value
                if TABLE in s and ("from " + TABLE) in s.lower():
                    out.append((path.relative_to(APP.parent), node.lineno, s))
    return out


def test_every_read_of_the_table_names_its_source():
    found = _sql_literals()
    assert found, "не нашёл ни одного запроса к ad_campaign_stat — прибор смотрит не туда"
    holes = [(p, n) for p, n, s in found if "source" not in s.lower()]
    assert not holes, (
        "запрос к ad_campaign_stat без упоминания источника — факт смешается с "
        "измерением верификатора и удвоится: " + str(holes))


def test_our_counter_and_verifier_do_not_overlap():
    assert not (set(OWN) & set(VERIFIER)), (
        "источник не может быть одновременно нашим счётчиком и независимым измерением")


def test_verifier_never_enters_the_fact():
    for s in VERIFIER:
        assert s not in fact_sources(), f"{s} — измеритель, его показы не идут в факт"
        assert is_verifier(s)


def test_weborama_is_declared_as_a_verifier():
    """Решение владельца 10.09.2026: справочная величина, НЕ к закрытию."""
    assert "weborama" in VERIFIER
    assert "weborama" not in OWN


def test_demo_source_of_the_stand_is_counted():
    """На стенде демо-генератор — единственный факт.

    Выкинуть его из суммы значит показать пустой дашборд ровно там, где мы проверяем
    расчёты, и принять пустоту за поломку коннектора.
    """
    assert "demo" in fact_sources()


def test_sources_written_by_scripts_are_declared():
    """Источник, который кто-то пишет, но никто не объявил, не попадёт ни в одну группу.

    Такой факт не сложится и не сверится — он просто исчезнет с экрана.
    """
    scripts = APP.parent / "scripts"
    written = set()
    for path in sorted(scripts.glob("*.py")):
        src = path.read_text(encoding="utf-8")
        if TABLE not in src:
            continue
        tree = ast.parse(src, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "source":
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    written.add(node.value.value)
    # словарь демо-скрипта: он пишет через :s-параметр, поэтому добираем литералом
    if (scripts / "2026-09-04_demo_traffic_month.py").exists():
        written.add("demo")
    unknown = {s for s in written if s not in KNOWN} - {"аккаунт", "трафики", "кабинет"}
    assert not unknown, f"источник пишется, но не объявлен в stat_sources: {unknown}"
