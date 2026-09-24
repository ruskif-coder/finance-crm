# -*- coding: utf-8 -*-
"""Ссылки площадке ведут в её КАБИНЕТ, а не во внутреннюю систему (аудит 23.09.2026, 5.H2).

Письмо, дайджест и бот площадке собирали адрес от `DOMAIN` — адреса нашей внутренней
системы. «Открыть кабинет» открывал вход в финмодуль, «Настроить уведомления» — наш
экран настроек, куда площадке не попасть. Кабинет живёт на своём адресе
(`CABINET_SITE`, на проде lk.simb-ad.com — подтверждено владельцем 24.09.2026).

Проверяется главное свойство: в том, что уходит площадке, нет ни одной ссылки на
внутренний домен.
"""
import io
import re
from pathlib import Path

import httpx

from app.mail import render
from app.notify import telegram

APP = Path(__file__).resolve().parent.parent / "app"


def test_cabinet_address_comes_from_its_own_setting(monkeypatch):
    monkeypatch.setenv("DOMAIN", "core.test")
    monkeypatch.setenv("CABINET_SITE", "lk.test")
    assert render.cabinet_url("/") == "https://lk.test/"
    monkeypatch.delenv("CABINET_SITE")
    assert render.cabinet_url("/") == "https://lk.simb-ad.com/", (
        "без настройки ссылка должна вести в боевой кабинет, а не в никуда")


def test_the_publisher_bot_links_to_the_cabinet(monkeypatch):
    monkeypatch.setenv("DOMAIN", "core.test")
    monkeypatch.setenv("CABINET_SITE", "lk.test")
    monkeypatch.setattr(telegram, "bot_token", lambda contour=telegram.STAFF: "T")
    sent = {}

    def post(url, json=None, **kw):
        sent["text"] = json["text"]
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(telegram.httpx, "post", post)
    telegram.send_message("1", "Кампания стартовала", link="/", contour=telegram.PUB)
    assert "https://lk.test/" in sent["text"]
    assert "core.test" not in sent["text"]


def test_outward_code_never_builds_a_link_from_the_internal_domain():
    """Внешний контур не зовёт `abs_url` (адрес ядра) — только `cabinet_url`."""
    for f in (APP / "notify" / "outward").rglob("*.py"):
        src = io.open(f, encoding="utf-8").read()
        assert not re.search(r"render\.abs_url\(", src), (
            f"{f.name}: ссылка площадке собирается от адреса внутренней системы")
