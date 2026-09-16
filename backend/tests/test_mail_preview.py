# -*- coding: utf-8 -*-
"""Предпросмотр писем: экран показывает то же, что уйдёт.

Прибор нужен потому, что расхождение здесь ТИХОЕ: предпросмотр рисуется без ошибок,
выглядит правдоподобно, а получатель видит другое письмо. Узнали бы мы об этом от
площадки — то есть после отправки.

Вторая забота — полнота. Карточки берутся из каталогов (`registry.EVENTS`,
`outward.kinds.KINDS`), и новый вид обязан появляться на экране сам. Если список
где-то переписан руками, прибор это покажет.
"""
from app.database import SessionLocal
from app.mail import preview
from app.notify import registry
from app.notify.outward import kinds as outward_kinds


def test_контуров_два_и_у_каждого_свой_шаблон():
    """Письма сотрудникам и письма площадкам правятся РАЗНЫМ текстом: у внешнего письма
    другое обращение, и общий шаблон заставил бы выбирать между ними."""
    cs = preview.contours()
    assert [c["key"] for c in cs] == ["staff", "pub"]
    assert cs[0]["template"] == "notify"
    assert cs[1]["template"] == "pub_notify"
    assert cs[0]["template"] != cs[1]["template"]


def test_карточки_берутся_из_каталогов_целиком():
    """Новый вид уведомления появляется на экране почты сам. Ручной список разошёлся бы
    с каталогом при первом же добавлении — и незаметно."""
    cs = {c["key"]: c for c in preview.contours()}
    assert len(cs["staff"]["cards"]) == len(registry.EVENTS)
    assert len(cs["pub"]["cards"]) == len(outward_kinds.KINDS)


def test_у_каждой_карточки_есть_всё_для_письма():
    """Пустой заголовок или отсутствующий тон дают письмо без шапки и без плашки — оно
    соберётся и уйдёт, просто окажется бессмысленным."""
    for c in preview.contours():
        for card in c["cards"]:
            assert card["label"], f"{c['key']}/{card['key']}: нет заголовка"
            assert card["tone"] in ("bad", "warn", "ok", "info"), card["key"]
            assert card["action"], f"{c['key']}/{card['key']}: нет подписи кнопки"


def test_ненаписанный_вид_помечен():
    """Объявленный, но не отправляемый вид площадке не показывается — и в предпросмотре
    это видно, иначе экран обещал бы письма, которых нет."""
    pub = [c for c in preview.contours() if c["key"] == "pub"][0]
    assert any(not c["built"] for c in pub["cards"]), "все виды построены — проверьте каталог"
    assert all(c["built"] for c in
               [x for x in preview.contours() if x["key"] == "staff"][0]["cards"])


def test_предпросмотр_рисуется_тем_же_кодом_что_отправка():
    """Прибор смотрит на ИМПОРТЫ: своя вёрстка письма внутри предпросмотра означала бы
    вторую разметку, которая разойдётся с первой молча.
    """
    import io
    from pathlib import Path

    from app.mail import editor

    src = io.open(Path(preview.__file__), encoding="utf-8").read() + io.open(
        Path(editor.__file__), encoding="utf-8").read()
    assert "from app.mail import render" in src
    assert "from app.mail import templates as tpl" in src
    # Никаких собственных тегов: всё, что рисуется, приходит из render.py
    assert "<table" not in src and "<div" not in src


def test_запрос_посадочной_живёт_у_площадок_и_со_своим_шаблоном():
    """Владелец 16.09.2026: «запрос посадочной — это часть уведомлений паблишеру».

    Он и был карточкой каталога, но его шаблон висел отдельным списком «письма, которые
    пишет человек», то есть в другом месте экрана, чем событие, которое его отправляет.
    Прибор держит две вещи сразу: карточка в контуре площадок, а шаблон у неё СВОЙ —
    ответ на это письмо приходит живому отправителю, и общий конверт ему не подходит.
    """
    pub = [c for c in preview.contours() if c["key"] == "pub"][0]
    card = [c for c in pub["cards"] if c["key"] == "запрос ссылки"][0]
    assert card["template"] == "url_request" != pub["template"]
    assert card["plain"] is True, "письмо простым текстом, карточки у него нет"


def test_карточка_с_чужим_ключом_не_находится():
    """Опечатка в ключе должна падать, а не рисовать пустое письмо: пустое письмо
    выглядит как «событие без текста» и уводит разбираться не туда."""
    assert preview._card_of("pub", "нет такого") is None


def test_the_brand_comes_from_the_relation_not_from_the_deal_title():
    """Бренд в подстановке — из справочника, а не разбором названия сделки.

    Разбор по «·» стоял в `sample` и на живых данных прода не работал: из 948 сделок
    точку-разделитель содержат 2, вертикальную черту 48, остальные ничего. «Бренд»
    получался равен всему внутреннему заголовку — «Berlin-Chemie | Лиотон | MI | еФарм
    WEB | 2026-10», — и подстановка {бренд} унесла бы площадке наше название услуги.

    Найдено 16.09.2026 прогоном сценария на копии прода: на стенде названия собраны
    генератором через «·», и разбор выглядел рабочим.
    """
    from app.mail import editor

    db = SessionLocal()
    try:
        v = editor.sample(db, editor.PUB)
    finally:
        db.close()
    brand = v.get("бренд") or ""
    if not brand:
        return                      # в базе нет сделки с брендом — проверять нечего
    assert "|" not in brand and "·" not in brand, (
        f"в бренд попал заголовок сделки целиком: {brand!r}")

