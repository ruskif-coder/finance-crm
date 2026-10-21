# -*- coding: utf-8 -*-
"""Шаблоны ДС: проверка шаблона, нумерация, зоны, сравнение версий, вид по формату договора (спринт 1, 13.10.2026).

Чистая логика, без базы. Ту же проверку повторяет экран макета (`frontend/lib/annexTemplate.mjs`): правило одно,
поэтому при правке здесь правится и там — тест `annexTemplate.test.mjs` держит те же случаи.
"""
import copy

from app.annex_tpl import check as C
from app.annex_tpl.diff import diff
from app.annex_tpl.formats import KNOWN_FORMATS, clean
from app.annex_tpl.subs import PROTECTED, SUBS


def base():
    return [
        {"id": "head", "sys": "head", "title": "Заголовок"},
        {"id": "place", "sys": "place", "title": "Место и дата"},
        {"id": "pre", "sys": "pre", "title": "Преамбула"},
        {"id": "p1", "title": "Предмет", "req": 1, "pin": 1, "text": "Исполнитель оказывает услуги для {бренд} с {период_с} по {период_по}."},
        {"id": "mp", "sys": "table", "title": "Таблица МП"},
        {"id": "p11", "title": "Стоимость", "sub": 1, "req": 1, "pin": 1, "money": 1,
         "text": "Стоимость {сумма}, НДС {ндс_ставка}% — {ндс_сумма}."},
        {"id": "p2", "title": "Претензии", "text": "Претензии направляются в письменной форме."},
        {"id": "sign", "sys": "sign", "title": "Подписи"},
    ]


def texts(issues):
    return " | ".join(i["text"] for i in issues)


def test_clean_template_passes():
    assert C.check(base()) == []


def test_numbering_and_zones_come_from_order():
    b = base()
    n = C.numbering(b)
    assert [n["p1"], n["p11"], n["p2"]] == ["1.", "1.1.", "2."]
    zone = {x["id"]: C.zone_at(b, i) for i, x in enumerate(b) if not x.get("sys")}
    assert zone == {"p1": "acc", "p11": "law", "p2": "law"}


def test_empty_unknown_nameless_and_stripped_money_are_all_reported():
    b = copy.deepcopy(base())
    b[5]["text"] = "Стоимость {сумма} и {что_это}"
    b[6]["text"] = "Текст пункта."
    b[3]["title"] = "Новый пункт"
    t = texts(C.check(b))
    assert "неизвестная подстановка {что_это}" in t
    assert "убрана защищённая подстановка {ндс_сумма} или {ндс_сумма_прописью}" in t
    assert "убрана защищённая подстановка {сумма} или" not in t
    assert "пункт не заполнен" in t
    assert "у пункта нет названия" in t


def test_money_block_accepts_the_phrase_form_of_the_real_template():
    """Реальный шаблон пишет «{сумма_прописью}» целой фразой, без отдельной цифры — это тоже защита."""
    b = copy.deepcopy(base())
    b[5]["text"] = "Стоимость {сумма_прописью}, включая НДС ({ндс_ставка}%) {ндс_сумма_прописью}."
    assert C.check(b) == []
    b[5]["text"] = "Стоимость {сумма_прописью}, включая НДС ({ндс_ставка}%)."
    assert "убрана защищённая подстановка {ндс_сумма} или {ндс_сумма_прописью}" in texts(C.check(b))


def test_structure_errors():
    assert texts(C.check([])) == "шаблон пуст"
    dup = base()
    dup[3]["id"] = "p2"
    assert "повтор идентификатора" in texts(C.check(dup))
    no_table = [x for x in base() if x["id"] != "mp"]
    assert "системные блоки должны идти по порядку" in texts(C.check(no_table))
    out = base()
    out.insert(0, {"id": "x", "title": "Лишний", "text": "Пункт до заголовка."})
    assert "вне области" in texts(C.check(out))


def test_pinned_block_cannot_be_removed_or_unpinned():
    prev = base()
    removed = [x for x in prev if x["id"] != "p1"]
    assert "закреплённый пункт убрать нельзя" in texts(C.check_transition(prev, removed))
    unreq = copy.deepcopy(prev)
    unreq[3]["req"] = 0
    assert "нельзя снять обязательность" in texts(C.check_transition(prev, unreq))
    assert C.check_transition(prev, copy.deepcopy(prev)) == []
    assert C.check_transition(None, prev) == []


def test_diff_marks():
    a = base()
    b = copy.deepcopy(a)
    b[6]["text"] = "Иная редакция."
    b[5]["req"] = 0
    b[3]["sub"] = 1
    b.append({"id": "n1", "title": "Новый", "text": "Содержательный текст."})
    b[-2], b[-1] = b[-1], b[-2]          # новый пункт — перед подписями
    marks = {(d[0], d[1]) for d in diff(a, b)}
    assert ("~", "Претензии") in marks and ("🔒", "Стоимость") in marks
    assert ("↳", "Предмет") in marks and ("+", "Новый") in marks
    assert diff(a, copy.deepcopy(a)) == []


def test_known_formats_mirror_the_contract_form():
    """Зеркало `COOPERATION_FORMATS` экрана договоров: расхождение списков — договор, формат которого не предложить шаблону."""
    import pathlib
    import re
    src = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "lib" / "contractTerms.js")
    if not src.exists():
        return                       # в контейнере бэкенда фронта нет — проверяется в репозитории
    m = re.search(r"COOPERATION_FORMATS = \[(.*?)\]", src.read_text(encoding="utf-8"), re.S)
    assert tuple(re.findall(r"'([^']+)'", m.group(1))) == KNOWN_FORMATS


def test_clean_format():
    assert clean("  Клиент ") == "Клиент" and clean(None) == "" and clean("") == ""


def test_substitutions_registry():
    assert set(PROTECTED) == {"сумма", "сумма_прописью", "ндс_сумма", "ндс_сумма_прописью"}
    assert SUBS["договор_дата"]["empty_ok"] and SUBS["рекламодатель"]["empty_ok"]
    assert all(v.get("where") for v in SUBS.values() if v.get("empty_ok"))
