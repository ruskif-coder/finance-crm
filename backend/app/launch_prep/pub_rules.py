"""Особенности площадок для трафика: канал размещения, ссылки в app, доп. код Adfox.

Решения владельца 27–29.09.2026 (docs/ПЛАН_админка_трафиков_особенности_площадок.md,
шпаргалка — docs/ШПАРГАЛКА_креатив_под_площадку.md). Настройки живут на поверхности
площадки (`sales_publisher_surfaces`), диплинк — на паре «креатив × площадка».

Одна точка на правила: сборка (что спросить у аккаунта), отправка трафику (что запирает),
выгрузка в DSP (что встаёт в href) и выдача архива под Adfox читают отсюда.
"""
from typing import Dict, Iterable, Optional, Tuple

from sqlalchemy.orm import Session

from app.sales.models import SalesPublisherSurface

CHANNELS = {"dsp": "наша DSP", "adfox": "Adfox", "outside": "вне контура"}
APP_LINKS = {"web": "веб-ссылка в href", "both": "диплинк в href + веб в url/adomain"}


def rules_for(db: Session, keys: Iterable[Tuple[int, str]]) -> Dict[Tuple[int, str], dict]:
    """{(publisher_id, kind): правило} пачкой — один запрос на экран или выгрузку."""
    keys = {(p, k) for p, k in keys if p and k}
    if not keys:
        return {}
    pubs = {p for p, _ in keys}
    out = {}
    for s in db.query(SalesPublisherSurface).filter(SalesPublisherSurface.publisher_id.in_(pubs)):
        if (s.publisher_id, s.kind) in keys:
            out[(s.publisher_id, s.kind)] = rule_of(s)
    return out


def rule_of(s) -> dict:
    return {"channel": s.placement_channel, "app_links": s.app_links if s.kind == "app" else None,
            "adfox_code": s.adfox_extra_code if s.placement_channel == "adfox" else None}


def needs_deeplink(rule: Optional[dict]) -> bool:
    return bool(rule and rule.get("app_links") == "both")


def click_href(rule: Optional[dict], advertiser_url: Optional[str],
               deeplink_url: Optional[str]) -> Optional[str]:
    """Что поставить в `<a href>` вместо макроса DSP. None — оставить макрос, как было."""
    mode = (rule or {}).get("app_links")
    if mode == "web":
        return (advertiser_url or "").strip() or None
    if mode == "both":
        return (deeplink_url or "").strip() or None
    return None


def pair_problem(rule: Optional[dict], advertiser_url: Optional[str],
                 deeplink_url: Optional[str]) -> Optional[str]:
    """Чего не хватает паре по правилу площадки. None — всё есть."""
    if needs_deeplink(rule) and not (deeplink_url or "").strip():
        return "площадка требует диплинк — впишите его рядом с посадочной"
    if (rule or {}).get("channel") == "adfox" and not ((rule or {}).get("adfox_code") or "").strip():
        return "площадка в Adfox, а доп. код для %user6% не задан — заполните в админке трафика"
    return None


def applied_label(rule: Optional[dict]) -> Optional[str]:
    """Какое правило применено — для карточки креатива у трафика."""
    if not rule:
        return None
    if rule.get("channel") == "adfox":
        return "Adfox: %user6% после <body>, макроса DSP нет"
    if rule.get("channel") == "outside":
        return "вне контура: архив как прислал клиент"
    if rule.get("app_links") == "web":
        return "в href — веб-ссылка"
    if rule.get("app_links") == "both":
        return "в href — диплинк, в url/adomain — веб"
    return None


def validate_deeplink(value: Optional[str]) -> Optional[str]:
    """Диплинк — схема приложения (`maksavit://…`) или https. Запрещены схемы, которыми
    поле, отрисованное ссылкой, превращается в XSS."""
    v = (value or "").strip()
    if not v:
        return None
    scheme = v.split(":", 1)[0].lower() if ":" in v else ""
    if not scheme or scheme in ("javascript", "data", "vbscript", "file") or len(v) > 1024:
        raise ValueError("Диплинк — адрес вида app://… или https://…, не длиннее 1024 символов")
    return v
