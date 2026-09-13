# -*- coding: utf-8 -*-
"""Ссылка нацеливания: «прицелить рекламу на себя», чтобы увидеть баннер до старта.

Что это за ссылка. У DSP есть страница, которая ставит браузеру куку кампании: открыл,
нажал «Включить» — и дальше видишь на сайте площадки именно этот креатив, хотя размещение
ещё не запущено. Ровно то, чем трафик проверяет баннер глазами. До сих пор такие ссылки
выпускались руками в админке и вставлялись в поле `test_targeting_url`.

ПОЧЕМУ НЕ БРАУЗЕРНЫЙ РОБОТ. Присланный вариант водил Playwright по форме админки. Замер
12.09.2026 показал, что этого не нужно вовсе: форма — обычная `<form method='post'>` с
единственным полем `crid`, без CSRF-токена и без проверки сессии. Один POST делает то же
самое, работает на сервере без графической оболочки и не ломается от перерисовки вёрстки.

ТРИ ЗАМЕРЕННЫХ СВОЙСТВА, КОТОРЫЕ ОПРЕДЕЛЯЮТ ВСЁ ОСТАЛЬНОЕ.

1. **Ссылка живёт 48 часов.** `exp` в выданной ссылке — ровно двое суток от выпуска
   (замер: выпуск 12.09 16:17 UTC → `exp` 14.09 16:17 UTC). Поэтому ссылку НЕ ХРАНЯТ:
   согласование идёт днями, и сохранённая ссылка умрёт раньше, чем до неё дойдут руки.
   Хранить надо идентификатор креатива, а ссылку выпускать в момент нажатия.
   Просроченная, впрочем, врёт не молча: страница пишет «Время действия ссылки истекло».

2. **Генератор НЕ ПРОВЕРЯЕТ, что креатив существует.** Он подписывает любую строку
   допустимого вида. Замер: на выдуманный `DEADBEEFDEADBEEF` выдана ссылка, и её страница
   ТЕКСТУАЛЬНО СОВПАДАЕТ со страницей настоящего креатива. То есть по виду ссылки нельзя
   понять, сработает она или нет. Из этого следует правило интерфейса: выпущенная ссылка
   не является подтверждением чего-либо, и показывать её как «проверка пройдена» нельзя.

3. **Отказов ровно два, и оба текстовые**: пустой идентификатор и недопустимые символы.
   Никакого кода состояния — HTTP всегда 200, разница только в классе плашки.

Адрес админки берётся из окружения (`DSP_ADMIN_URL`), как и адрес API. В коде его нет
намеренно — правило проекта: поставщик DSP нигде не называется.
"""
from __future__ import annotations

import html as _html
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx

log = logging.getLogger("finance.dsp")

ENV_ADMIN_URL = "DSP_ADMIN_URL"

# Путь генератора внутри админки. Контроллер веб-интерфейса, а не метод API: в JSON-RPC
# такого метода нет (наш список — Campaign.*, Creative.*, Targeting.*, Upload.*).
GENERATOR_PATH = "/?c=targeting&a=generator"

TIMEOUT = 20.0

# Их вёрстка: результат приходит плашкой bootstrap, успех и отказ отличаются классом.
_SUCCESS = re.compile(r'<div[^>]*class="[^"]*alert-success[^"]*"[^>]*>(.*?)</div>', re.S)
_DANGER = re.compile(r'<div[^>]*class="[^"]*alert-danger[^"]*"[^>]*>(.*?)</div>', re.S)
_URL = re.compile(r'https?://[^\s"<]+')
_EXP = re.compile(r'[?&]exp=(\d+)')


class TargetingLinkError(RuntimeError):
    """Ссылку выпустить не удалось: отказ генератора, сеть, неожиданный ответ."""


@dataclass
class TargetingLink:
    crid: str
    url: str
    expires_at: Optional[datetime]

    @property
    def alive(self) -> bool:
        return self.expires_at is None or self.expires_at > datetime.now(timezone.utc)


def _text(chunk: str) -> str:
    return _html.unescape(re.sub(r"<[^>]+>", "", chunk)).strip()


def _expires(url: str) -> Optional[datetime]:
    m = _EXP.search(url)
    if not m:
        return None
    try:
        return datetime.fromtimestamp(int(m.group(1)), timezone.utc)
    except (ValueError, OSError):
        return None


def issue(crid: str, *, url: Optional[str] = None,
          transport: Optional[Callable[[str, dict], str]] = None,
          timeout: float = TIMEOUT) -> TargetingLink:
    """Выпустить свежую ссылку нацеливания для креатива.

    `crid` — идентификатор креатива в DSP. У нас это `ad_campaign_creative
    .ms_creative_xxhash`: замер 12.09.2026 подтвердил, что страница его принимает.

    `transport` подменяется в тестах — тот же приём, что у клиентов DSP и Weborama:
    подменный транспорт описывает ВЕСЬ обмен, и приборы работают без сети.
    """
    crid = (crid or "").strip()
    if not crid:
        # Их собственный отказ на пустое поле звучит так же, но незачем ходить наружу,
        # чтобы это узнать.
        raise TargetingLinkError("Не задан идентификатор креатива в DSP")

    base = (url or os.getenv(ENV_ADMIN_URL) or "").strip().rstrip("/")
    if not base:
        raise TargetingLinkError(
            f"{ENV_ADMIN_URL} не задан — адрес админки DSP неизвестен")

    target = base + GENERATOR_PATH
    if transport is not None:
        body = transport(target, {"crid": crid})
    else:
        try:
            r = httpx.post(target, data={"crid": crid}, timeout=timeout,
                           follow_redirects=False)
        except httpx.HTTPError as e:
            raise TargetingLinkError(f"Генератор недоступен: {e!r}") from e
        if r.status_code >= 400:
            raise TargetingLinkError(f"Генератор ответил {r.status_code}")
        body = r.text

    ok = _SUCCESS.search(body or "")
    if ok:
        link = _URL.search(_text(ok.group(1)))
        if not link:
            raise TargetingLinkError(
                "Генератор ответил успехом, но ссылки в ответе нет: "
                + _text(ok.group(1))[:200])
        out = TargetingLink(crid=crid, url=link.group(0), expires_at=_expires(link.group(0)))
        log.info("DSP: выпущена ссылка нацеливания для %s до %s", crid, out.expires_at)
        return out

    bad = _DANGER.search(body or "")
    if bad:
        # Их текст показываем как есть: он называет причину точнее, чем наш пересказ.
        raise TargetingLinkError(f"Генератор отказал: {_text(bad.group(1))[:200]}")

    # Ни успеха, ни отказа — скорее всего вёрстку переделали. Молчать нельзя: снаружи
    # это выглядело бы как «кнопка не работает».
    raise TargetingLinkError(
        "Ответ генератора не разобран: ни плашки успеха, ни плашки отказа")
