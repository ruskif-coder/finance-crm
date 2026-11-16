# -*- coding: utf-8 -*-
"""Посадочная на домене ДРУГОЙ площадки сделки — предупреждение, не запрет (владелец 16.11.2026).

16.11 нашлось: приоритезация QGNY4M ушла площадкам с посадочными соседних аптек, в RLXATY у dagfarm.ru стояла ссылка
120на80.рф, в VX2QWE у aptekalegko.ru — newapteka.ru. Такое не роняет запуск, а молча отдаёт клики чужой аптеке.
Сравниваем хост посадочной с доменами площадок той же сделки: свой домен и его поддомены (web.kuper.ru у kuper.ru) — норма;
совпал с доменом другой площадки — предупреждение. Площадки одной сети подписываются: иногда у сети общий сайт, решает человек.
Смотрим только тех, кто реально в списке комплекта (пары и выбранные кандидаты), а не осиротевшие строки посадочных —
иначе ложная тревога (CZZD7F: строка 003ms.ru в комплектах 5–6 без пары)."""
from typing import Iterable, Optional
from urllib.parse import urlparse


def _host(domain_or_url: Optional[str]) -> str:
    s = (domain_or_url or "").strip().lower()
    if not s:
        return ""
    host = urlparse(s if "://" in s else "http://" + s).hostname or ""
    host = host[4:] if host.startswith("www.") else host
    try:
        return host.encode("idna").decode("ascii")          # 009.рф и 009.xn--p1ai — одно и то же
    except UnicodeError:
        return host


def _under(host: str, domain: str) -> bool:
    return bool(domain) and (host == domain or host.endswith("." + domain))


def foreign(url: Optional[str], own_domain: Optional[str], others: Iterable, own_network: Optional[str] = None) -> Optional[str]:
    """Текст предупреждения или None. `others` — (домен, сеть) площадок сделки, свою можно не исключать."""
    low = (url or "").strip().lower()
    host = _host(url) if low.startswith(("http://", "https://")) else ""   # диплинки и app-ссылки (storefront://) не сверяем
    own = _host(own_domain)
    if not host or _under(host, own):
        return None
    for domain, network in others:
        d = _host(domain)
        if d and d != own and _under(host, d):
            same = (f" — та же сеть «{network}», если у сети общий сайт, так и задумано"
                    if network and network == own_network else "")
            return f"посадочная на домене другой площадки сделки: {domain}{same}"
    return None
