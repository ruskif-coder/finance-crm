# -*- coding: utf-8 -*-
"""Автопроверки заявки — формальное, что не надо проверять глазами (канон премодерации, п. 3).

Каждая проверка — `{"key", "label", "state", "detail"}`; `state`: `ok` — в порядке, `bad` — нарушение,
`warn` — посмотреть человеку, `na` — проверить нечем (например, площадки SSP ещё не сопоставлены с нашими).
Проверки у каждой заявки свои: ЕРИД и ссылка у заявок одного баннера разные.
"""
import re
from typing import List, Optional
from urllib.parse import parse_qs, urlsplit

from app.premod import markup as M

OK, BAD, WARN, NA = "ok", "bad", "warn", "na"
_INN = re.compile(r"^\d{10}(\d{2})?$")


def _check(key: str, label: str, state: str, detail: str = "") -> dict:
    return {"key": key, "label": label, "state": state, "detail": detail}


def erid_in_link(url: Optional[str]) -> Optional[str]:
    """ЕРИД, зашитый в ссылку клика на любой глубине редиректов, или None."""
    seen = 0
    while url and seen < 6:
        qs = parse_qs(urlsplit(url).query)
        if "erid" in qs:
            return qs["erid"][0]
        url = next((v[0] for k, v in qs.items() if v and v[0].lower().startswith("http")), None)
        seen += 1
    return None


def erid_check(api_erid: Optional[str], html: str) -> dict:
    meta = M.erid(html)
    link = erid_in_link(M.click_href(html))
    if not api_erid or not meta:
        return _check("erid", "ЕРИД", BAD, "нет ЕРИД в " + ("заявке" if not api_erid else "разметке"))
    if meta != api_erid:
        return _check("erid", "ЕРИД", BAD, f"в заявке {api_erid}, в разметке {meta}")
    if link and link != api_erid:
        return _check("erid", "ЕРИД", BAD, f"в ссылке клика {link}, в заявке {api_erid}")
    return _check("erid", "ЕРИД", OK, "совпадает в заявке, разметке" + (" и ссылке" if link else ""))


def ord_check(html: str) -> dict:
    info = M.ord_info(html)
    if not info:
        return _check("ord", "Сведения для ОРД", BAD, "нет меты ad.ordinfo")
    missing = [w for w, ok in (("наименования", info["name"]), ("ИНН", _INN.match(info["inn"]))) if not ok]
    if missing:
        return _check("ord", "Сведения для ОРД", BAD, "нет " + " и ".join(missing))
    return _check("ord", "Сведения для ОРД", OK, f"{info['name']}, ИНН {info['inn']}")


def size_check(html: str) -> dict:
    size = M.size(html)
    if size is None:
        return _check("size", "Размер", WARN, "размер не объявлен")
    # Сверка с блоками площадки — после сопоставления площадок SSP с нашими (владелец 07.11: позже).
    return _check("size", "Размер", NA, f"{size} · с блоками площадок не сверяем — площадки SSP не сопоставлены")


def hosts_check(html: str) -> dict:
    hosts = M.external_hosts(M.sanitize(html))
    if not hosts:
        return _check("hosts", "Внешние скрипты", OK, "нет")
    return _check("hosts", "Внешние скрипты", WARN, ", ".join(hosts))


def run(api_erid: Optional[str], html: str) -> List[dict]:
    return [erid_check(api_erid, html), ord_check(html), size_check(html), hosts_check(html)]
