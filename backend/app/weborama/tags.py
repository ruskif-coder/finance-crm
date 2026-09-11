# -*- coding: utf-8 -*-
"""Разбор ответа `insertions/{id}/tags.json`. Чистая логика.

Замерено на живом вызове 09.09.2026. Ответ — МАССИВ, и в нём не «пиксель», а формы тега:

    [{"tracking_id":"567", "ad_space_id":1080, "placement_id":0, "campaign_id":29,
      "js_ru":"<script>…</script>\\n\\n<a href=\\"…a.A=cl…\\"></a>"}]

Внутри `js_ru` ДВЕ разные ссылки, и путать их нельзя:

  · `a.A=im` — пиксель ПОКАЗА. Его ждёт поле `pixel` у креатива DSP;
  · `a.A=cl` — счётчик КЛИКА, для кликовой ссылки.

В ответе на вставку с `delivery_format_id=4` пришёл только кликовый. Простой поиск «любой
адрес с [RANDOM]» подставил бы его вместо пикселя показа: креатив уехал бы в DSP с
кликовым счётчиком на месте показного, всё «работало» бы, а показы не считались — и
выяснилось бы это по пустым отчётам через месяц. Поэтому разбираем по `a.A`, а не по виду.
"""
import re
from typing import Any, Optional

# Параметр, различающий назначение ссылки.
ACTION_IMPRESSION = "a.A=im"
ACTION_CLICK = "a.A=cl"

_URL_RE = re.compile(r"https?://[^\s\"'<>\\]+")

# Плейсхолдеры, которые Weborama оставляет для подстановки на нашей стороне.
PLACEHOLDERS = ("[RANDOM]", "[ERID_ID]", "[ERID_VALUE]", "~WIDTH~", "~HEIGHT~")


def _rows(payload: Any) -> list:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("list", "tags", "data", "items", "result"):
            v = payload.get(key)
            if isinstance(v, list):
                return [r for r in v if isinstance(r, dict)]
        return [payload]
    return []


def _urls(text: str) -> list:
    return _URL_RE.findall(text or "")


def parse(payload: Any) -> dict:
    """Что пришло: `{impression, click, js, tracking_id, others}`.

    Пусто в `impression` — законный ответ, а не сбой разбора: значит показной пиксель этой
    формой не отдаётся, и брать вместо него кликовый нельзя.
    """
    out = {"impression": None, "click": None, "js": None,
           "tracking_id": None, "campaign_id": None, "ad_space_id": None,
           "others": [], "placeholders": []}
    for row in _rows(payload):
        out["tracking_id"] = out["tracking_id"] or row.get("tracking_id")
        out["campaign_id"] = out["campaign_id"] or row.get("campaign_id")
        out["ad_space_id"] = out["ad_space_id"] or row.get("ad_space_id")
        for key, val in row.items():
            if not isinstance(val, str) or "http" not in val:
                continue
            if key.startswith("js") or "<script" in val:
                out["js"] = out["js"] or val
            for u in _urls(val):
                if ACTION_IMPRESSION in u and not out["impression"]:
                    out["impression"] = u
                elif ACTION_CLICK in u and not out["click"]:
                    out["click"] = u
                elif ACTION_IMPRESSION not in u and ACTION_CLICK not in u:
                    if u not in out["others"]:
                        out["others"].append(u)
    blob = str(payload)
    out["placeholders"] = [p for p in PLACEHOLDERS if p in blob]
    return out


def impression_pixel(payload: Any) -> Optional[str]:
    """Только показной пиксель, или None. Кликовый вместо него не подставляем НИКОГДА."""
    return parse(payload).get("impression")


# Что вообще похоже на неподставленный макрос: их `~WIDTH~`, их же `${GDPR}` и наши `[…]`.
_LEFTOVER_RE = re.compile(r"~[A-Z_0-9]+~|\$\{[A-Za-z_0-9]+\}|\[[A-Z_0-9]+\]")


def leftovers(tag: str) -> list:
    """Макросы, оставшиеся в готовом теге.

    Замерено 09.09.2026: пиксель формата 3 приходит с `~WIDTH~`, `~HEIGHT~`, `${GDPR}` и
    `${GDPR_CONSENT_284}`. В выгрузке Excel их не было — там уже стояли `a.he=1&a.wi=1`.
    DSP таких макросов не знает и подставлять не будет: строка уедет как есть, и в счётчик
    попадёт мусор вместо размера. Молчать об этом нельзя.
    """
    return sorted(set(_LEFTOVER_RE.findall(tag or "")))


def fill_size(tag: str, width, height) -> str:
    """Подставить размер вместо `~WIDTH~` / `~HEIGHT~`. Размер мы ЗНАЕМ — он объявлен в
    самом баннере (`ad.size`), поэтому выдумывать ничего не нужно."""
    out = (tag or "").replace("~WIDTH~", str(width)).replace("~HEIGHT~", str(height))
    return out


__all__ = ["parse", "impression_pixel", "leftovers", "fill_size",
           "ACTION_IMPRESSION", "ACTION_CLICK", "PLACEHOLDERS"]
