# -*- coding: utf-8 -*-
"""Предпросмотр писем: то же письмо, что уйдёт, но с примерными данными.

## Главное правило: рисует ТОТ ЖЕ КОД, что отправляет

Разметка берётся у `mail/render.py` — никакой второй вёрстки «как в письме» на экране
нет и быть не должно. Иначе экран показывал бы одно, а получатель видел другое, и
расхождение обнаружилось бы у площадки. По той же причине тема и словесная часть
собираются через `templates.apply` — ту же функцию, что зовут оба контура при отправке.

## Что такое «карточка»

Карточка — это ОДИН ВИД события внутри письма: чип, тон, заголовок, пояснение, плашки
фактов и кнопка. Письмо про одно событие содержит одну карточку, дайджест — несколько.
Экран почты перечисляет все виды обоих контуров, чтобы на вопрос «а как это выглядит у
получателя» отвечал экран, а не воображение.

## Откуда берутся примерные данные

Из самого каталога: у внутреннего события есть `title`, `description`, `tone`, `action`,
у внешнего — `label`, `hint`, `tag`, `tone`. Придумывать тексты заново нельзя: расхождение
между предпросмотром и настройками читается как ошибка системы. Числа в плашках —
единственное, что здесь вымышлено, и они помечены как пример.
"""
from __future__ import annotations

from typing import List, Optional

from app.mail import render
from app.mail import templates as tpl
from app.notify import registry
from app.notify.outward import kinds as outward_kinds

STAFF, PUB = "staff", "pub"

# Ключи шаблонов по контурам. Здесь же список read-only для экрана: контуров два, и
# каждый правится своим текстом.
TEMPLATE_OF = {STAFF: "notify", PUB: "pub_notify"}

# Виды со СВОИМ шаблоном. «Запрос посадочной» — часть уведомлений площадке (владелец
# 16.09.2026), но письмо у него своё: его пишет человек, выбирая формулировку вопроса, а
# ответ должен прийти живому отправителю (`reply_to`), а не в ящик системы. Отсюда и
# отдельный шаблон, и простой текст вместо карточки.
#
# ЭТО РАСХОЖДЕНИЕ, А НЕ ЗАМЫСЕЛ: вид объявлен построенным в каталоге, но уходит мимо
# общего отправителя (`launch_prep._mail_url_request`), поэтому у него нет ни строки в
# ленте кабинета, ни сообщения в боте. Экран это показывает честно — чтобы решение
# «свести или оставить» принималось глядя на письмо, а не на код.
OWN_TEMPLATE = {"запрос ссылки": "url_request"}

# Запасные плашки — на случай пустой базы (чистый стенд, первый запуск). На живых
# данных их считает `editor.facts_of` из настоящей сделки и настоящей площадки.
SAMPLE_FACTS = (("сделка", "—"), ("сумма", "—"))


def contours() -> List[dict]:
    """Каталог: два контура, у каждого свой шаблон и свой набор карточек."""
    staff = [{
        "key": e.key, "label": e.title, "hint": e.description,
        "tone": e.tone, "tag": e.group, "action": e.action or "Открыть",
        "group": dict(registry.DIRECTIONS).get(e.direction, e.direction),
        # «Нельзя отключить» сказано прямо: у такого события дайджест — единственный
        # разрешённый способ уменьшить поток, и человек должен это видеть.
        "locked": e.locked,
        "built": True,
    } for e in registry.EVENTS.values()]

    pub = [{
        "key": k.key, "label": k.label, "hint": k.hint,
        "tone": k.tone, "tag": k.tag or k.label, "action": "Открыть кабинет",
        "group": ("Сразу" if k.schedule == "сразу" else "Дайджест"),
        "locked": not k.can_mute,
        # Объявленный, но ненаписанный вид площадке не показывается вовсе — и здесь
        # это видно, чтобы предпросмотр не обещал письма, которых нет.
        "built": k.built,
        "template": OWN_TEMPLATE.get(k.key, TEMPLATE_OF[PUB]),
        # Вид, который уходит ПРОСТЫМ ТЕКСТОМ, а не карточкой. Помечен, потому что
        # нарисовать ему конверт значило бы показать письмо, которого не существует.
        "plain": k.key in OWN_TEMPLATE,
    } for k in outward_kinds.KINDS]

    return [
        {"key": STAFF, "label": "Сотрудникам", "template": TEMPLATE_OF[STAFF],
         "hint": "Письма нашим людям: очередь сделок, документы, деньги, поломки.",
         "cards": staff},
        {"key": PUB, "label": "Площадкам", "template": TEMPLATE_OF[PUB],
         "hint": "Письма наружу, в кабинет паблишера. Их читают вне компании.",
         "cards": pub},
    ]


def _card_of(contour: str, key: str) -> Optional[dict]:
    for c in contours():
        if c["key"] != contour:
            continue
        for card in c["cards"]:
            if card["key"] == key:
                return card
    return None


def text_part(db, contour: str, key: str) -> dict:
    """Тема и текстовая часть — та же `templates.apply`, что и при отправке.

    Показывается рядом с вёрсткой: письмо уходит `multipart/alternative`, и получатель
    без картинок читает именно это. Пока текстовой части не было видно, о ней забывали.
    """
    card = _card_of(contour, key)
    if card is None:
        raise KeyError(key)
    link = render.abs_url("/campaigns" if contour == PUB else "/accounts/dashboard") or ""
    facts_line = render.facts_line(SAMPLE_FACTS)
    key_tpl = card.get("template") or TEMPLATE_OF[contour]

    if key_tpl == "url_request":
        # Поля у этого шаблона свои, и подставлять в него «заголовок» бессмысленно:
        # экран должен показывать те же места, что заполнит отправка. Значения — НАШИ,
        # из базы: на выдуманной площадке не видно ни длины названия, ни того, как
        # ложится настоящий период.
        from app.mail import editor          # локально: editor импортирует этот модуль

        v = editor.sample(db, PUB)
        values = {"площадка": v.get("площадка", ""), "домен": v.get("домен", ""),
                  "сделка": " · ".join(x for x in (v.get("бренд"), v.get("период")) if x),
                  "бренд": v.get("бренд", ""), "период": v.get("период", ""),
                  "сотрудник": "— кто отправляет —",
                  "текст": "Подскажите, пожалуйста, посадочную страницу — карточку "
                           "товара или подборку на вашем сайте."}
        default = values["текст"]
    else:
        values = {"заголовок": card["label"], "текст": card["hint"], "ссылка": link,
                  "факты": facts_line}
        if contour == PUB:
            values["контекст"] = "Максавит · сентябрь"
        default = render.text_body(card["label"], card["hint"], link, SAMPLE_FACTS)

    subject, body = tpl.apply(db, key_tpl, values,
                              subject_default=card["label"], text_default=default)
    return {"subject": subject, "body": body, "template": key_tpl,
            "plain": bool(card.get("plain"))}
