# -*- coding: utf-8 -*-
"""Ссылки площадки не исполняют код (аудит 23.09.2026, 7.M1).

Чаты площадки, ссылки на макеты и мессенджеры сохранялись без проверки схемы и рисуются
кликабельными — в реестре, карточке, сводке и в кабинете самой площадки. Ссылка вида
`javascript:…` в таком поле — сохранённый XSS: код выполнится у того, кто кликнет.
Проверка стоит на сервере — там, где значение принимается; на экране — вторым рубежом.
"""
import io
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.links import safe_url
from app.routers import publishers as P

BAD = ("javascript:alert(1)", " JavaScript:alert(1)", "data:text/html,<b>x</b>",
       "vbscript:msgbox", "file:///etc/passwd")
GOOD = ("https://t.me/chat", "http://site.test/", "tg://resolve?domain=x", "")


@pytest.mark.parametrize("v", BAD)
def test_dangerous_schemes_are_refused(v):
    with pytest.raises(ValueError):
        safe_url(v)


@pytest.mark.parametrize("v", GOOD)
def test_normal_links_pass(v):
    assert safe_url(v) == (v.strip() or None)


@pytest.mark.parametrize("model,field", [
    (P.PublisherIn, "chat_url"), (P.PublisherIn, "chat_url_max"),
    (P.PublisherPatch, "chat_url"), (P.PublisherPatch, "chat_url_max"),
    (P.ContactIn, "max_url")])
def test_every_link_field_is_checked(model, field):
    required = {n: "x" for n, f in model.model_fields.items() if f.is_required()}
    with pytest.raises(ValidationError):
        model(**{**required, field: "javascript:alert(1)"})


def test_a_new_figma_link_is_checked_and_an_old_one_is_left_alone():
    """Ссылка на макет правится двумя путями (модель и сырое тело карточки) — оба идут
    через `_figma`. Старое значение без схемы («нет» — так на проде) не мешает сохранить
    карточку; новое опасное — отказ."""
    from fastapi import HTTPException

    assert P._figma("нет", "нет") == "нет"
    assert P._figma(None, " https://figma.com/x ") == "https://figma.com/x"
    with pytest.raises(HTTPException) as e:
        P._figma("нет", "javascript:alert(1)")
    assert e.value.status_code == 422
    src = io.open(Path(P.__file__), encoding="utf-8").read()
    assert src.count("_figma(") >= 3, "один из путей правки макета идёт мимо проверки"
