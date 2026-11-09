# -*- coding: utf-8 -*-
"""Проверки ПАКЕТА премодерации — порт логики макета (premodLogic.checksOf) с решением владельца 08.11.2026.

Распознавания текста с картинки нет: у статики текста нет, и проверки текста — «посмотреть глазами»
(warn), а не «нарушение». У HTML5 текст берётся из разметки, и там проверки работают как в макете.
Ожидаемые значения посчитаны руками по правилам макета, а не той же функцией.
"""
from app.premod import markup as M
from app.premod import package_checks as PC

PHARMA = {"inn": "1234567890", "short": "Фармкомпания", "category": "лекарства"}
AIR = {"inn": "5555555555", "short": "Авиакомпания Небо", "category": "авиа"}
ERID_OK = [{"key": "erid", "state": "ok", "detail": "совпадает"}, {"key": "ord", "state": "ok", "detail": ""}]
ERID_BAD = [{"key": "erid", "state": "bad", "detail": "в ссылке клика X, в заявке Y"},
            {"key": "ord", "state": "ok", "detail": ""}]


def states(checks):
    return {c["key"]: c["state"] for c in checks}


def test_static_text_checks_are_look_not_violation():
    """Сломает: вернуть проверку «Реклама» по пустому тексту — у статики всё станет «нарушением»."""
    out = states(PC.package_checks("статика", None, PHARMA, "300x250", [], [ERID_OK]))
    assert out["mark"] == "warn" and out["adv"] == "warn" and out["warning"] == "warn" and out["stop"] == "warn"
    assert out["erid"] == "ok" and out["ord"] == "ok" and out["size"] == "na"
    assert out["contract"] == "off" and out["ord_registry"] == "off"
    assert PC.is_clean(PC.package_checks("статика", None, PHARMA, "300x250", [], [ERID_OK])) is True


def test_static_without_drug_category_needs_no_warning():
    out = states(PC.package_checks("статика", None, AIR, "300x250", [], [ERID_OK]))
    assert out["warning"] == "na"


def test_html5_text_is_checked_like_the_mockup():
    text = "Снимает симптомы. Реклама. Фармкомпания, ИНН 1234567890. Лучший выбор."
    out = states(PC.package_checks("HTML5", text, PHARMA, "300x250", [], [ERID_OK]))
    assert out == {**out, "mark": "ok", "adv": "ok", "warning": "warn", "stop": "warn"}
    ok = text + " Имеются противопоказания. Необходимо проконсультироваться со специалистом."
    assert states(PC.package_checks("HTML5", ok, PHARMA, "300x250", [], [ERID_OK]))["warning"] == "ok"


def test_html5_text_missing_in_markup_is_look_not_violation():
    """Сломает: вернуть «нарушение» по тексту разметки. Замер 08.11: все 30 HTML5 стенда — canvas,
    текст нарисован, а в разметке его нет; «нет в разметке» не значит «нет на баннере»."""
    out = PC.package_checks("HTML5", "Летайте с нами. Авиакомпания Небо", AIR, "300x250", [], [ERID_OK])
    assert states(out)["mark"] == "warn" and states(out)["adv"] == "ok"
    assert PC.is_clean(out) is True


def test_erid_counts_bad_requests_and_size_and_scripts():
    out = PC.package_checks("статика", None, AIR, None, ["cdn.example"], [ERID_OK, ERID_BAD])
    by = {c["key"]: c for c in out}
    assert by["erid"]["state"] == "bad" and by["erid"]["short"] == "не совпадает у 1 из 2"
    assert by["size"]["state"] == "warn" and by["scripts"]["state"] == "warn"
    assert by["scripts"]["short"] == "cdn.example"


def test_ord_violation_in_any_request_is_package_violation():
    bad_ord = [{"key": "erid", "state": "ok", "detail": ""}, {"key": "ord", "state": "bad", "detail": "нет ИНН"}]
    assert states(PC.package_checks("статика", None, AIR, "300x250", [], [ERID_OK, bad_ord]))["ord"] == "bad"


def test_short_name_drops_legal_form_and_quotes():
    assert PC.short_name('АО "Авиакомпания "Сибирь"') == "Авиакомпания Сибирь"
    assert PC.short_name("ООО «Альфа Текстайлз»") == "Альфа Текстайлз"
    assert PC.short_name(None) == "Заказчик не указан"


def test_changes_between_versions():
    old = {"size": "728x90", "text": "Витамин D3. 60 капсул. Реклама.", "hosts": []}
    new = {"size": "728x90", "text": "Витамин D3. 90 капсул. Реклама.", "hosts": ["cdn.example"]}
    assert PC.changes(old, new) == [
        {"label": "текст", "from": "60", "to": "90", "kind": "changed"},
        {"label": "скрипт", "from": "", "to": "+ cdn.example", "kind": "added"},
    ]
    assert PC.changes(old, old) == [{"label": "креатив", "from": "", "to": "изменилась картинка или разметка",
                                     "kind": "same"}]


def test_visible_text_of_markup_skips_scripts_styles_and_tags():
    html = ('<html><head><style>.a{color:red}</style><script>var x="Реклама скрыта"</script></head>'
            '<body><div>Кроссовер&nbsp;нового поколения</div><p>Реклама. ООО «Ромашка»</p></body></html>')
    assert M.visible_text(html) == "Кроссовер нового поколения Реклама. ООО «Ромашка»"
    assert M.visible_text('<img src="x.gif">') is None
    # canvas-баннер: в разметке только заголовок вкладки — текста для проверок нет
    assert M.visible_text('<head><title>index</title></head><body><canvas></canvas></body>') is None
