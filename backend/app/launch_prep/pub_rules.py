"""Особенности площадок для трафика: канал размещения, ссылки в app, доп. код Adfox.

Решения владельца 27–29.09.2026 (docs/ПЛАН_админка_трафиков_особенности_площадок.md,
шпаргалка — docs/ШПАРГАЛКА_креатив_под_площадку.md). Настройки живут на поверхности
площадки (`sales_publisher_surfaces`), диплинк — на паре «креатив × площадка».

Одна точка на правила: сборка (что спросить у аккаунта), отправка трафику (что запирает),
выгрузка в DSP (что встаёт в href) и выдача архива под Adfox читают отсюда.
"""
import re
from typing import Dict, Iterable, Optional, Tuple

from sqlalchemy.orm import Session

from app.sales.models import SalesPublisherSurface

CHANNELS = {"dsp": "наша DSP", "adfox": "Adfox", "outside": "вне контура"}
# Режим «веб» (прямая веб-ссылка в href) снят 05.10.2026: загрузчик DSP требует кликовый
# макрос в каждой ссылке баннера (код 2051), веб-ссылка его не несёт. Площадке, которой
# нужна обычная посадочная, режим не нужен вовсе: макрос DSP в href, посадочная — в link.
APP_LINKS = {"both": "диплинк в href + веб в url/adomain",
             # Площадка принимает диплинк SDK прямо в посадочной (владелец 02.10.2026).
             "sdk": "диплинк SDK (deeplink+://) в посадочной"}

# Что подсказать человеку у поля посадочной — по режиму площадки. Подсказка, не запрет
# (владелец 02.10.2026: «пока без жёсткой проверки»).
LANDING_HINTS = {
    "both": ("Здесь — веб-ссылка https://…, диплинк приложения — в поле рядом; в диплинке "
             "обязателен кликовый макрос DSP {LINK_ESC} или {LINK_UNESC}"),
    "sdk": ("Площадка принимает диплинк SDK: deeplink+://navigate?primaryUrl=<ссылка https "
            "в base64>&primaryTrackingUrl={LINK_ESC}"),
}


def normalize_app_links(value: Optional[str]) -> Optional[str]:
    """Режим ссылок к сохранению: снятый «веб» (05.10.2026) = без режима — по смыслу то же:
    макрос DSP в href, посадочная в link. Иначе строку со старым «веб» нельзя было бы
    пересохранить (ревью 05.10.2026)."""
    v = (value or "").strip() or None
    return None if v == "web" else v


def landing_hint(rule: Optional[dict]) -> Optional[str]:
    return LANDING_HINTS.get((rule or {}).get("app_links"))


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


# ── Посадочная app-площадки в формате диплинка SDK (владелец 02.10.2026) ─────────────
#
# `deeplink+://navigate?primaryUrl=<base64 https>&primaryTrackingUrl={LINK_ESC}` — так
# площадки присылают ссылку для приложения. SDK открывает внутри приложения `primaryUrl`,
# а `primaryTrackingUrl` дёргает фоном — это кликовая ссылка DSP, засчитывает клик.
# `{LINK_ESC}` DSP подставляет ТОЛЬКО в коде баннера, поэтому строка целиком встаёт в
# `<a href>`; в `link`/`adomain` DSP, ОРД и прочее, где нужен веб-адрес, — `web_url()`.
APP_LINK_PREFIX = "deeplink+://"


def app_link_web(url: Optional[str]) -> Optional[str]:
    """Веб-адрес из `primaryUrl` диплинка SDK; None — это не диплинк или он битый."""
    import base64
    import binascii
    from urllib.parse import unquote
    u = (url or "").strip()
    if not u.lower().startswith(APP_LINK_PREFIX) or "?" not in u:
        return None
    for part in u.split("?", 1)[1].split("&"):
        key, _, val = part.partition("=")
        if key != "primaryUrl" or not val:
            continue
        raw = unquote(val)          # не unquote_plus: «+» — законный символ base64
        try:
            web = base64.b64decode(raw + "=" * (-len(raw) % 4),
                                   altchars=b"-_" if ("-" in raw or "_" in raw) else None,
                                   validate=True).decode("utf-8").strip()
        except (binascii.Error, ValueError, UnicodeDecodeError):
            return None
        return web if web.lower().startswith(("https://", "http://")) else None
    return None


def is_app_link(url: Optional[str]) -> bool:
    return (url or "").strip().lower().startswith(APP_LINK_PREFIX)


# Своя схема приложения площадки: `storefront://product_selection/4846` у kuper (владелец
# 06.10.2026). Только app-поверхность; опасные схемы — никогда.
_APP_SCHEME_RE = re.compile(r"^([a-z][a-z0-9+.\-]*)://\S+$", re.I)
_BAD_SCHEMES = ("javascript", "data", "file", "vbscript", "about", "blob")


def is_app_scheme(url: Optional[str]) -> bool:
    """Ссылка своей схемой приложения (не http(s), не наш диплинк SDK, не опасная)."""
    m = _APP_SCHEME_RE.match((url or "").strip())
    return bool(m) and m.group(1).lower() not in _BAD_SCHEMES + ("http", "https")         and not is_app_link(url)


def web_url(url: Optional[str]) -> Optional[str]:
    """Веб-адрес посадочной: у диплинка SDK — раскодированный `primaryUrl`; у ссылки своей
    схемой приложения веб-адреса нет — None (в DSP и ОРД она не уходит); иначе как есть."""
    u = (url or "").strip()
    if not u:
        return None
    if is_app_scheme(u):
        return None
    return app_link_web(u) if is_app_link(u) else u


def validate_landing(value: Optional[str], surface_kind: Optional[str] = None) -> Optional[str]:
    """ВЕБ-ссылка пары — всегда http(s), на любой поверхности (владелец 06.10.2026: «первая
    всегда веб»). Ссылка в приложении — отдельное поле, `validate_app_link`.
    Ошибка — `ValueError` с текстом для человека."""
    v = (value or "").strip()
    if not v:
        return None
    if not v.lower().startswith(("http://", "https://")):
        raise ValueError("Веб-ссылка должна начинаться с http:// или https://"
                         + (" — ссылку в приложении (storefront://…, deeplink+://…) впишите "
                            "во второе поле" if surface_kind == "app" else ""))
    return v


def validate_app_link(value: Optional[str]) -> Optional[str]:
    """Ссылка в приложении (владелец 06.10.2026): своя схема приложения (`storefront://…`),
    диплинк SDK (`deeplink+://…`) или тот же https. Опасные схемы — отказ: поле где-то
    отрисуется ссылкой. Кликовый макрос НЕ требуется: в баннер ссылка ставится, только если
    он в ней есть (`click_href`), иначе клик идёт через макрос DSP."""
    v = (value or "").strip()
    if not v:
        return None
    if len(v) > 1024:
        raise ValueError("Ссылка в приложении длиннее 1024 символов")
    # Пробелы и управляющие символы внутри — склейка двух ссылок или подмена; intent://
    # запускает любой компонент Android-приложения (ревью 06.10.2026).
    if re.search(r"\s|[\x00-\x1f\x7f]", v):
        raise ValueError("В ссылке в приложении не должно быть пробелов и переводов строки")
    if v.lower().startswith("intent:"):
        raise ValueError("Ссылки intent:// не принимаем — укажите схему приложения или https://")
    if v.lower().startswith(("http://", "https://")) or is_app_link(v) or is_app_scheme(v):
        return v
    raise ValueError("Ссылка в приложении — адрес вида storefront://…, deeplink+://… или "
                     "https://…")


def split_landing(raw: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Старая посадочная одной строкой → (веб, приложение). Для переноса 06.10.2026:
    диплинк SDK — в приложение, его primaryUrl — в веб; «веб … приложение» одной строкой
    (так вписывали у kuper) — по частям."""
    v = (raw or "").strip()
    if not v:
        return None, None
    if is_app_link(v):
        return app_link_web(v), v
    parts = v.split()
    web = next((x for x in parts if x.lower().startswith(("http://", "https://"))), None)
    app = next((x for x in parts if is_app_link(x) or is_app_scheme(x)), None)
    return web, app


def needs_deeplink(rule: Optional[dict]) -> bool:
    return bool(rule and rule.get("app_links") == "both")


# Кликовый макрос DSP, обязательный в КАЖДОЙ ссылке баннера: загрузчик отклоняет архив без него
# (код 2051, «Any link must contains {LINK_UNESC}»; первый случай 05.10.2026: LBS2QH × Максавит).
# Именно `{LINK_UNESC}`. С 05.10 по 07.10 макросом считался и `{LINK_ESC}` (по строке документации
# «оба — только в коде баннера»), и SDK-диплинк `…&primaryTrackingUrl={LINK_ESC}` уходил в href —
# DSP отклонил 16 загрузок 07.10 (4FKFD2, LBS2QH); за всё время журнала не принято ни одной ссылки
# с одним `{LINK_ESC}`. Такая ссылка в баннер не встаёт: остаётся макрос DSP, клик идёт на веб.
CLICK_MACROS = ("{LINK_UNESC}",)


def has_click_macro(url: Optional[str]) -> bool:
    return any(m in (url or "") for m in CLICK_MACROS)


def _wanted_href(rule: Optional[dict], advertiser_url: Optional[str],
                 deeplink_url: Optional[str]) -> Optional[str]:
    """Что правило площадки хотело бы поставить в href (без проверки макроса)."""
    # С 06.10.2026 ссылка в приложении — своё поле (`deeplink_url`): диплинк SDK живёт там,
    # а не в посадочной. Старые строки с диплинком в посадочной читаются как прежде.
    app = (deeplink_url or "").strip() or None
    legacy = (advertiser_url or "").strip() if is_app_link(advertiser_url) else None
    mode = (rule or {}).get("app_links")
    if mode == "web":     # старый режим (с 05.10 при сохранении пустой) — в href веб-ссылка
        return (advertiser_url or "").strip() or None
    if mode in ("sdk", "both"):
        return app or legacy
    # Без правила площадки диплинк SDK всё равно идёт в баннер: иначе он потерялся бы —
    # в `link` уходит веб-адрес (02.10.2026).
    return (app if is_app_link(app) else None) or legacy


def click_href(rule: Optional[dict], advertiser_url: Optional[str],
               deeplink_url: Optional[str]) -> Optional[str]:
    """Что поставить в `<a href>` вместо макроса DSP. None — оставить макрос DSP: ссылку без
    кликового макроса DSP не примет (2051), а клик через макрос уходит на посадочную из link."""
    href = _wanted_href(rule, advertiser_url, deeplink_url)
    return href if has_click_macro(href) else None


def click_warning(rule: Optional[dict], advertiser_url: Optional[str],
                  deeplink_url: Optional[str]) -> Optional[str]:
    """Пояснение трафику, если правило площадки хотело ссылку в href, но в ней нет макроса."""
    href = _wanted_href(rule, advertiser_url, deeplink_url)
    if not href or has_click_macro(href):
        return None
    return ("ссылка из правила площадки без кликового макроса {LINK_UNESC} (загрузчик DSP "
            "принимает только его) — в баннере оставлен макрос DSP, клик уйдёт на посадочную")


def pair_problem(rule: Optional[dict], advertiser_url: Optional[str],
                 deeplink_url: Optional[str]) -> Optional[str]:
    """Чего не хватает паре по правилу площадки. None — всё есть."""
    if needs_deeplink(rule) and not (deeplink_url or "").strip() and not is_app_link(advertiser_url):
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
    if rule.get("app_links") == "sdk":
        return "в href — диплинк SDK из посадочной, в url/adomain — его веб-адрес"
    return None


# ── Площадка в РК: наша DSP / внешняя / смешанная (владелец 30.09.2026) ─────────────────
#
# Строка размещения РК — одна на площадку, без деления на web и app, а канал задаётся у
# ПОВЕРХНОСТИ: у Максавита web через Adfox, app — через нашу DSP. Поэтому режим площадки
# в РК считается по тем её поверхностям, по которым в сделке ОТПРАВЛЯЛИСЬ креативы (нет
# отправленных — по всем выбранным в сделке); канал поверхности — из «Особенностей
# площадок». Признак «наш код» — только запасной, когда поверхностей в сделке нет вовсе.
EXTERNAL_CHANNELS = ("adfox", "outside")
MODE_DSP, MODE_EXTERNAL, MODE_MIXED = "dsp", "external", "mixed"


def placement_modes(db: Session, keys) -> Dict[Tuple[int, int], dict]:
    """{(deal_id, publisher_id): {"mode", "external": [поверхности вне нашей DSP]}} пачкой."""
    from sqlalchemy import text
    keys = {(d, p) for d, p in keys if d and p}
    if not keys:
        return {}
    deals = list({d for d, _ in keys})
    pubs = list({p for _, p in keys})
    rows = db.execute(text("""
        SELECT t.deal_id, t.publisher_id, t.surface_kind,
               bool_or(p.sent_at IS NOT NULL) AS sent
          FROM launch_prep_target t
          LEFT JOIN launch_prep_pair p ON p.target_id = t.id AND p.withdrawn_at IS NULL
         WHERE t.deal_id = ANY(:d) AND t.publisher_id = ANY(:p)
         GROUP BY 1, 2, 3
    """), {"d": deals, "p": pubs}).all()
    surf = {}
    for d, p, kind, sent in rows:
        surf.setdefault((d, p), []).append((kind, bool(sent)))
    chan, kinds_of, working_of = {}, {}, {}
    for r in db.query(SalesPublisherSurface).filter(SalesPublisherSurface.publisher_id.in_(pubs)):
        chan[(r.publisher_id, r.kind)] = r.placement_channel
        kinds_of.setdefault(r.publisher_id, []).append(r.kind)
        if r.we_work:
            working_of.setdefault(r.publisher_id, []).append(r.kind)
    our = dict(db.execute(text("SELECT id, our_code FROM sales_publishers WHERE id = ANY(:p)"),
                          {"p": pubs}).all())
    out = {}
    for key in keys:
        d, p = key
        lst = surf.get(key, [])
        # Поверхности сделки: отправленные → выбранные → все поверхности площадки. Последнее —
        # для РК без сборки запуска по этой площадке (замер 30.09 на копии прода: так у
        # Максавита в большинстве сентябрьских РК). «Наш код» — лишь если поверхностей нет.
        # Запасной вариант — поверхности, с которыми мы РАБОТАЕМ (`we_work`): у трёх
        # Adfox-площадок app в реестре есть, но «не работаем» (владелец 30.09.2026:
        # Adfox — только web на трёх площадках), и считать его значило бы звать DSP зря.
        kinds = ([k for k, sent in lst if sent] or [k for k, _ in lst]
                 or working_of.get(p) or kinds_of.get(p, []))
        if not kinds:
            ext = our.get(p) is False
            out[key] = {"mode": MODE_EXTERNAL if ext else MODE_DSP, "external": []}
            continue
        external = sorted({k for k in kinds if chan.get((p, k)) in EXTERNAL_CHANNELS})
        mode = (MODE_EXTERNAL if len(external) == len(set(kinds))
                else MODE_MIXED if external else MODE_DSP)
        out[key] = {"mode": mode, "external": external}
    return out
