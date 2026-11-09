# -*- coding: utf-8 -*-
"""Разбор разметки креатива SSP: что в нём заявлено и как показать его безопасно.

Разметку SSP отдаёт по `preview_url` без авторизации (замер 07.11.2026, 120 креативов): мета ЕРИД
(`ad.erid`, у всех), сведения для ОРД (`ad.ordinfo` — JSON с заказчиком и ИНН, у 118), размер
(`ad.size`, у 107), скрипт видимости, ссылка клика через редирект SSP и трекер с дважды закодированной
посадочной, от одного до четырёх скрытых пикселей (`display:none`). Хосты поставщиков здесь не
называются — всё опознаётся по устройству разметки, а не по адресам.

ХЕШ ПАКЕТА. Один и тот же баннер SSP заводит отдельной заявкой на каждую площадку: у заявок разные ЕРИД,
трекинг, ссылка клика, пиксели с доменом площадки, `ad.id`. Хеш считается по разметке, из которой всё
это вырезано, — остаётся сам баннер и рекламодатель. Совпал хеш — смотреть второй раз нечего.
"""
import hashlib
import html as html_lib
import json
import re
from typing import List, Optional
from urllib.parse import parse_qs, urlsplit

from app.launch_prep.sandbox import parse_ad_size

_META = r"""<meta[^>]*\bname=["']{name}["'][^>]*\bcontent=(["'])(.*?)\1[^>]*>"""
# Вся мета, которая у заявок одного баннера своя: идентификаторы показа и кампании, ЕРИД.
_PER_REQUEST_META = re.compile(r"""<meta[^>]*\bname=["'](?:ad\.erid|ad\.id|ms\.[\w-]+)["'][^>]*>""", re.I)
# Сведения для ОРД: в хеш идут разобранными — у пары заявок одного заказчика мета записана по-разному.
_ORDINFO_META = re.compile(r"""<meta[^>]*\bname=["']ad\.ordinfo["'][^>]*>""", re.I)
_HIDDEN_IMG = re.compile(r"""<img\b[^>]*display\s*:\s*none[^>]*>""", re.I)
_SCRIPT = re.compile(r"""<script\b[^>]*>.*?</script>""", re.I | re.S)
_SCRIPT_SRC = re.compile(r"""<script\b[^>]*\bsrc=["']([^"']+)["']""", re.I)
_A_HREF = re.compile(r"""(<a\b[^>]*?)\s+href=(["'])(.*?)\2""", re.I | re.S)
_TARGET = re.compile(r"""\s+target=(["']).*?\1""", re.I)
_SPACES = re.compile(r"\s+")
# Параметры, в которых редиректы несут следующий адрес. Порядок — от внутреннего к внешнему.
_NEXT_URL_PARAMS = ("rurl", "url")
_MAX_HOPS = 5


def _meta(html: str, name: str) -> Optional[str]:
    m = re.search(_META.format(name=re.escape(name)), html or "", re.I | re.S)
    return html_lib.unescape(m.group(2)) if m else None


def erid(html: str) -> Optional[str]:
    return _meta(html, "ad.erid")


def ord_info(html: str) -> Optional[dict]:
    """Заказчик из `ad.ordinfo`: `{"name", "inn"}` или None, если меты нет или она не читается."""
    raw = _meta(html, "ad.ordinfo")
    if not raw:
        return None
    try:
        customer = (json.loads(raw) or {}).get("customer") or {}
    except (ValueError, AttributeError):
        return None
    return {"name": (customer.get("name") or "").strip(), "inn": str(customer.get("inn") or "").strip()}


def size(html: str) -> Optional[str]:
    """`300x250`; `адаптивный` — объявлен 0×0; None — размер не объявлен вовсе."""
    wh = parse_ad_size(html)
    if wh is None:
        return None
    w, h = wh
    return f"{w}x{h}" if w > 0 and h > 0 else "адаптивный"


def click_href(html: str) -> Optional[str]:
    m = _A_HREF.search(html or "")
    return html_lib.unescape(m.group(3)) if m else None


def landing(html: str) -> Optional[str]:
    """Посадочная: разворачиваем вложенные редиректы, пока в адресе есть следующий адрес."""
    url = click_href(html)
    for _ in range(_MAX_HOPS):
        if not url:
            return None
        qs = parse_qs(urlsplit(url).query)
        nxt = next((qs[p][0] for p in _NEXT_URL_PARAMS
                    if p in qs and qs[p][0].lower().startswith("http")), None)
        if not nxt:
            return url
        url = nxt
    return url


def _is_counter(script: str) -> bool:
    """Скрипт, который считает показ: видимость SSP или счётчик рекламодателя (`data-pixel`, у 41 из 120)."""
    head = script[:script.find(">") + 1].lower()
    return "viewability" in script.lower() or "data-pixel" in head


def _drop_counters(html: str) -> str:
    return _SCRIPT.sub(lambda m: "" if _is_counter(m.group(0)) else m.group(0), html)


def sanitize(html: str) -> str:
    """Разметка для нашей песочницы: без пикселей и счётчиков, клик никуда не ведёт.

    Иначе наш просмотр уходит площадке показом (в пикселе — её домен), рекламодателю — показом в его
    статистике, а клик — переходом.
    """
    out = _HIDDEN_IMG.sub("", html or "")
    out = _drop_counters(out)
    out = _A_HREF.sub(lambda m: _TARGET.sub("", m.group(1)), out)
    return out


def external_hosts(html: str) -> List[str]:
    """Хосты внешних скриптов — что исполнит баннер у зрителя (после вырезания нашего обвеса)."""
    hosts = {urlsplit(u).hostname for u in _SCRIPT_SRC.findall(html or "") if u.lower().startswith("http")}
    return sorted(h for h in hosts if h)


def image_hash(html: str) -> str:
    """Ключ пакета: баннер и рекламодатель без всего, что у заявок одного баннера своё."""
    body = _PER_REQUEST_META.sub("", sanitize(html))
    customer = ord_info(html) or {}
    body = _ORDINFO_META.sub("", body) + f"|{customer.get('name', '')}|{customer.get('inn', '')}"
    body = _SPACES.sub(" ", body).strip()
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


_INVISIBLE = re.compile(r"<(script|style|noscript|template|title)\b[^>]*>.*?</\1\s*>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")


def visible_text(html: str) -> Optional[str]:
    """Текст, который увидит зритель HTML5-баннера: без скриптов, стилей и тегов. None — текста нет."""
    text = html_lib.unescape(_TAG.sub(" ", _INVISIBLE.sub(" ", html or ""))).replace(" ", " ")
    return _SPACES.sub(" ", text).strip() or None
