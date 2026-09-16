# -*- coding: utf-8 -*-
"""Письмо уведомления: каркас, карточка события, дайджест.

Собрано по хендоффу «Уведомления · спокойная схема» (14.09.2026), файл
`code/email-template-calm.html`. Предыдущая редакция красила тоном подложку карточки,
рамку, полосу слева и кнопку — владелец назвал результат «фигня», и он прав: письмо из
семи просроченных событий превращалось в сплошное красное полотно, внутри которого уже
ничего не различить.

## Правило спокойной схемы

**Карточка нейтральная, важность несёт один элемент внутри неё.**

    подложка и рамка      белая и серая ВСЕГДА, при любом тоне
    пилюля важности       цвет + СЛОВО: срочно / нужно решение / готово / к сведению
    тег вида              всегда серый: это классификация, а не важность
    ровно одна плашка     покрашено то число, ради которого письмо пришло
    кнопка                всегда синяя

Слово важнее цвета: пилюля читается в чёрно-белой печати, при дальтонизме и в клиенте,
вырезавшем фоны, — подложка и полоса в этих условиях исчезают молча. Два цветных
элемента рядом (пилюля и тег) снова дали бы светофор, поэтому тег серый.

Кнопка синяя при любом тоне намеренно: красная кнопка в тревожном письме не добавляет
срочности, но ломает привычку — основное действие в системе выглядит одинаково везде.
Цветом остаётся предупреждение, не действие.

Тон события в данных НЕ меняется: `bad | warn | ok | info` приходят из реестра и из
ступени сработки как прежде, меняется только отрисовка.

## Почему таблицами и инлайновыми стилями

В почте нет ни внешних стилей, ни `flex`, ни переменных: Outlook рисует движком Word,
Gmail вырезает `<style>`, часть клиентов не понимает `div` с процентной шириной. Таблица
шириной 600 и стиль в атрибуте — то, что доезжает везде. Пилюля и плашка собраны
ВЛОЖЕННЫМИ ТАБЛИЦАМИ, а не `span` с рамкой: Outlook теряет `border` у строчного элемента,
и пилюля осталась бы словом без подложки.

У кнопки есть вариант для Outlook (`v:roundrect` в условном комментарии): движок Word не
красит фон у ссылки, и кнопка выглядела бы простым текстом.

## Почему не CSS-переменные

`var(--accent)` в письме не работает — токены развёрнуты в литералы. Это единственное
место в проекте, где цвет написан шестнадцатеричным числом осознанно, и список ниже
держится вручную рядом с `styles/globals.css`.

## Одно письмо и дайджест — один сборщик

`notification_html` — одно событие, `digest_html` — несколько со счётчиками в шапке.
Карточка у них общая (`_card`), каркас общий (`_letter`). Держать их порознь значило бы
получить два разных письма об одном событии в зависимости от того, пришло оно сразу или
попало в утреннюю пачку — ровно то расхождение, которое мы уже чинили в досылке.

## Текстовая часть обязательна

Письмо уходит `multipart/alternative`. Часть получателей читает почту без разметки, а
часть фильтров считает письмо без текстовой части подозрительным.
"""
from __future__ import annotations

import html as _html
import os
from datetime import datetime
from typing import Iterable, Optional, Sequence, Tuple, Union

from app.timez import msk_now

# ── токены дизайн-системы, развёрнутые в литералы ────────────────────────────
CANVAS = "#EBEEF6"          # фон вокруг письма
CARD = "#FFFFFF"
SOFT = "#F6F7FB"            # подложка плашки и строки контекста
BORDER = "#E3E7F1"
HAIR = "#EDF0F7"            # внутренние разделители
T1 = "#1C2433"
T2 = "#525C70"
T3 = "#79839A"
T4 = "#A3ABBD"
ACCENT = "#4F6CE6"

# Шкала скругления. Одна лесенка на всё письмо: конверт мягче карточки, карточка мягче
# кнопки, кнопка мягче плашки. Разнобой радиусов читается как небрежность даже когда
# каждый по отдельности выглядит нормально.
R_LETTER = 16
R_CARD = 14
R_BUTTON = 11
R_PLATE = 10          # строка контекста, счётчик
R_CHIP = 9            # пилюля, тег вида, плашка факта

FONT = "'Manrope',Arial,sans-serif"
MONO = "Consolas,'Courier New',monospace"

# Пилюля важности: подложка · рамка · текст · слово.
# Слово несёт тон само по себе — сокращать его до значка нельзя.
PILLS = {
    "bad":  ("#FBEAEA", "#F0C9CA", "#C93A3E", "срочно"),
    "warn": ("#FBF0DE", "#F2DFC0", "#B26A0C", "нужно решение"),
    "ok":   ("#E6F5EF", "#CDE9DE", "#1F7D5E", "готово"),
    "info": ("#ECEFFD", "#D7DEFA", "#4F6CE6", "к сведению"),
}
# Тот же порядок, что в app/notify/tone.py. Письмо не импортирует словарь
# уведомлений намеренно — почта не должна зависеть от шины, — а совпадение
# сторожит прибор test_tone_vocabulary.
TONE_ORDER = ("bad", "warn", "info", "ok")

# Цвет ЗНАЧЕНИЯ в плашке. Тон карточки его не задаёт: в карточке «просрочка 14 дней»
# красное только «14 дн.», сумма и период нейтральны.
FACT_FG = {
    "danger": "#C93A3E", "warning": "#B26A0C", "income": "#1F7D5E",
    "accent": ACCENT, "muted": T2,
}

Fact = Union[Tuple[str, str], dict]

# Знак отправителя и ссылка на настройки — один адрес на оба вида письма и на оба
# контура. Растр лежит в `frontend/public/assets`, собран из того же SVG скриптом
# `scripts/svg_to_png.py`: почтовые клиенты SVG не рисуют вовсе.
LOGO_PATH = "/assets/logo-mediaplan@2x.png"
SETTINGS_PATH = "/settings/notifications"


def abs_url(path: Optional[str]) -> Optional[str]:
    """Адрес письма всегда абсолютный: относительный в почте никуда не ведёт.

    Без `DOMAIN` возвращается None, и письмо собирается без картинки и без ссылки —
    это верно для стенда, где домена нет, и не должно ронять отправку.
    """
    base = (os.getenv("DOMAIN") or "").strip()
    if not base or not path:
        return None
    return "https://" + base + path


def _esc(v) -> str:
    return _html.escape("" if v is None else str(v), quote=True)


def _k(f: Fact) -> str:
    return (f[0] if isinstance(f, tuple) else f.get("k", "")) or ""


def _v(f: Fact) -> str:
    return (f[1] if isinstance(f, tuple) else f.get("v", "")) or ""


def facts_line(facts: Iterable[Fact]) -> str:
    """Факты одной строкой: «ключ: значение · ключ: значение».

    Так их показывает телеграм и текстовая часть письма. Отдельной сборки у каждого
    канала нет намеренно: разошлись бы разделители и порядок, и одно событие читалось
    бы по-разному в зависимости от того, куда пришло.
    """
    return " · ".join(f"{_k(f)}: {_v(f)}" for f in (facts or ()))


# ── текстовая часть ──────────────────────────────────────────────────────────

def text_body(title: str, body: Optional[str], link_abs: Optional[str],
              facts: Iterable[Fact] = ()) -> str:
    """То же письмо словами. Факты склеиваются в строку `ключ: значение · …` — так же,
    как их склеивает телеграм: одно событие показывает одинаковые числа во всех каналах.
    """
    parts = [title or ""]
    if (body or "").strip():
        parts.append(body.strip())
    line = facts_line(facts)
    if line:
        parts.append(line)
    if link_abs:
        parts.append(link_abs)
    return "\n\n".join(parts)


# ── кирпичи карточки ─────────────────────────────────────────────────────────

def _pill(tone: str) -> str:
    """Пилюля важности — вложенная таблица, иначе Outlook съест рамку."""
    bg, border, fg, word = PILLS.get(tone, PILLS["info"])
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'align="left" style="margin-right:6px;background-color:{bg};'
        f'border-collapse:separate;border-spacing:0;border:1px solid {border};border-radius:{R_CHIP}px;"><tr>'
        f'<td style="padding:3px 9px;font-family:{MONO};font-size:9px;font-weight:700;'
        f'letter-spacing:0.06em;text-transform:uppercase;color:{fg};white-space:nowrap;">'
        f'<span style="display:inline-block;width:6px;height:6px;background-color:{fg};'
        f'border-radius:2px;vertical-align:middle;">&nbsp;</span>&nbsp;{word}'
        f'</td></tr></table>')


def _tag(tag: str) -> str:
    """Тег вида. Всегда серый: классификация, а не важность."""
    if not (tag or "").strip():
        return ""
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'align="left" style="background-color:{SOFT};border-collapse:separate;border-spacing:0;border-radius:{R_CHIP}px;"><tr>'
        f'<td style="padding:3px 8px;font-family:{MONO};font-size:9px;font-weight:700;'
        f'letter-spacing:0.06em;text-transform:uppercase;color:{T3};white-space:nowrap;">'
        f'{_esc(tag)}</td></tr></table>')


def _facts(facts: Iterable[Fact], tone: str) -> str:
    """Плашки фактов. Покрашена РОВНО ОДНА — помеченная `hot`.

    Горячая получает тинт и рамку тона, остальные — серую подложку без рамки. Цвет
    значения выбирает СОБЫТИЕ, а не письмо: в «ЕРИД выпущен» зелёный стоит на номере,
    а не на дате, и панель с телеграмом красят то же самое.
    """
    items = list(facts or ())
    if not items:
        return ""
    pill_bg, pill_border, _, _ = PILLS.get(tone, PILLS["info"])
    cells = []
    for f in items:
        hot = isinstance(f, dict) and bool(f.get("hot"))
        fg = FACT_FG.get((isinstance(f, dict) and f.get("fg")) or "", T1)
        bg = pill_bg if hot else SOFT
        br = pill_border if hot else bg
        cells.append(
            f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            f'align="left" class="fact" style="margin:0 6px 6px 0;background-color:{bg};'
            f'border-collapse:separate;border-spacing:0;border:1px solid {br};border-radius:{R_CHIP}px;"><tr>'
            f'<td style="padding:4px 8px;white-space:nowrap;">'
            f'<span style="font-family:{MONO};font-size:9px;letter-spacing:0.06em;'
            f'text-transform:uppercase;color:{T3};">{_esc(_k(f))}</span>'
            f'<span style="font-family:{MONO};font-size:11px;font-weight:700;'
            f'color:{fg};">&nbsp;{_esc(_v(f))}</span></td></tr></table>')
    return ('<div style="padding-top:9px;font-size:0;">' + "".join(cells)
            + '<div style="clear:both;line-height:0;font-size:0;">&nbsp;</div></div>')


def _button(link_abs: Optional[str], action: str, code: str = "") -> str:
    """Кнопка действия. Синяя при любом тоне.

    Для Outlook рядом лежит `v:roundrect`: движок Word не красит фон у ссылки, и без
    него кнопка выглядела бы обычным текстом. Оба варианта спрятаны условными
    комментариями, поэтому каждый клиент видит ровно один.
    """
    if not link_abs:
        return ""
    href = _esc(link_abs)
    label = _esc(action or "Открыть")
    code_cell = (f'<td align="right" style="font-family:{MONO};font-size:9px;'
                 f'letter-spacing:0.06em;text-transform:uppercase;color:{T4};'
                 f'white-space:nowrap;">{_esc(code)}</td>') if code else "<td></td>"
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'border="0" style="margin-top:8px;"><tr><td align="left" class="btn">'
        f'<!--[if mso]>'
        f'<v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" '
        f'xmlns:w="urn:schemas-microsoft-com:office:word" href="{href}" '
        f'style="height:32px;v-text-anchor:middle;width:180px;" arcsize="34%" '
        f'stroke="f" fillcolor="{ACCENT}"><w:anchorlock/>'
        f'<center style="color:#FFFFFF;font-family:Arial,sans-serif;font-size:12.5px;'
        f'font-weight:bold;">{label}</center></v:roundrect>'
        f'<![endif]-->'
        f'<!--[if !mso]><!-->'
        f'<a href="{href}" target="_blank" style="display:inline-block;padding:9px 14px;'
        f'background-color:{ACCENT};color:#FFFFFF;border-radius:{R_BUTTON}px;'
        f'font-family:{FONT};'
        f'font-size:12.5px;font-weight:700;text-decoration:none;line-height:1;">'
        f'{label}</a>'
        f'<!--<![endif]-->'
        f'</td>{code_cell}</tr></table>')


def _card(*, title: str, body: Optional[str], link_abs: Optional[str],
          tone: str = "info", tag: str = "", when: str = "", action: str = "Открыть",
          facts: Iterable[Fact] = (), context: Optional[str] = None,
          code: str = "") -> str:
    """Одно событие карточкой. Подложка и рамка от тона НЕ зависят."""
    ctx_html = ""
    if (context or "").strip():
        # Внешнему контуру строка контекста обязательна: у площадки идут несколько
        # кампаний сразу, и «ваш креатив ждёт решения» без неё бесполезно.
        ctx_html = (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'border="0" style="margin-top:7px;background-color:{SOFT};'
            f'border-collapse:separate;border-spacing:0;border-radius:{R_PLATE}px;"><tr><td style="padding:7px 10px;font-family:{FONT};'
            f'font-size:12px;color:{T1};">{_esc(context)}</td></tr></table>')

    body_html = ""
    if (body or "").strip():
        body_html = (f'<div style="padding-top:7px;font-family:{FONT};font-size:12.5px;'
                     f'color:{T2};line-height:1.45;">'
                     f'{_esc(body).replace(chr(10), "<br>")}</div>')

    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'border="0" style="margin-bottom:10px;background-color:{CARD};'
        f'border-collapse:separate;border-spacing:0;border:1px solid {BORDER};border-radius:{R_CARD}px;"><tr>'
        f'<td style="padding:12px 14px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'border="0"><tr><td align="left" style="white-space:nowrap;">'
        f'{_pill(tone)}{_tag(tag)}</td>'
        f'<td align="right" style="font-family:{MONO};font-size:9px;color:{T4};'
        f'white-space:nowrap;">{_esc(when)}</td></tr></table>'
        f'<div style="padding-top:8px;font-family:{FONT};font-size:14px;font-weight:600;'
        f'color:{T1};line-height:1.35;">{_esc(title)}</div>'
        f'{ctx_html}{body_html}{_facts(facts, tone)}'
        f'{_button(link_abs, action, code)}'
        f'</td></tr></table>')


# ── каркас письма ────────────────────────────────────────────────────────────

def _counters(counts: Sequence[Tuple[str, int]]) -> str:
    """Счётчики по тонам — КОНТУРНЫЕ, без заливки: залитые спорили бы с пилюлями
    карточек за внимание, а их работа — только сказать, чего сколько."""
    cells = []
    for tone, n in counts:
        if not n:
            continue
        _, border, fg, word = PILLS.get(tone, PILLS["info"])
        cells.append(
            f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            f'align="left" style="margin:0 8px 0 0;background-color:{CARD};'
            f'border-collapse:separate;border-spacing:0;border:1px solid {border};border-radius:{R_PLATE}px;"><tr>'
            f'<td style="padding:6px 10px;font-family:{FONT};font-size:11px;'
            f'font-weight:600;color:{fg};white-space:nowrap;">'
            f'<span style="display:inline-block;width:6px;height:6px;'
            f'background-color:{fg};border-radius:2px;vertical-align:middle;">&nbsp;</span>'
            f'&nbsp;{word}&nbsp;<span style="font-family:{MONO};font-size:12px;'
            f'font-weight:700;">{n}</span></td></tr></table>')
    if not cells:
        return ""
    return (f'<tr><td class="pad" style="padding:14px 22px 10px 22px;'
            f'border-bottom:1px solid {HAIR};">' + "".join(cells)
            + '<div style="clear:both;line-height:0;font-size:0;">&nbsp;</div>'
              '</td></tr>')


# Вес заголовков на ступень легче макета (700 шапка / 600 карточка вместо 800 / 700).
# Решение владельца 14.09.2026: на письме из шести событий жирными шли и шапка, и все
# шесть заголовков — тяжёлое перестаёт выделяться, когда тяжело всё. Разница в одну
# ступень между шапкой и карточкой сохранена: иерархия важнее общей лёгкости.
def _letter(*, brand: str, logo_url: Optional[str], when: datetime, headline: str,
            sub: str, counters: Sequence[Tuple[str, int]], cards: Sequence[str],
            footer: str, settings_url: Optional[str], preheader: str = "") -> str:
    mark = (f'<img src="{_esc(logo_url)}" width="132" height="16" alt="{_esc(brand)}" '
            f'style="display:block;width:132px;height:16px;">') if logo_url else (
        f'<span style="font-family:{FONT};font-size:15px;font-weight:700;'
        f'letter-spacing:-0.02em;color:{T1};">{_esc(brand)}</span>')

    sub_html = (f'<tr><td style="font-family:{FONT};font-size:13px;color:{T2};'
                f'line-height:1.45;">{_esc(sub)}</td></tr>') if sub else ""

    foot_link = (
        f' · <a href="{_esc(settings_url)}" style="color:{T3};'
        f'text-decoration:underline;">настроить уведомления</a>') if settings_url else ""

    return (
        '<!DOCTYPE html>'
        '<html lang="ru" xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:o="urn:schemas-microsoft-com:office:office"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="x-apple-disable-message-reformatting">'
        '<meta name="color-scheme" content="light only">'
        f'<title>{_esc(headline)}</title>'
        '<!--[if mso]><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96'
        '</o:PixelsPerInch></o:OfficeDocumentSettings></xml><![endif]-->'
        '<style>'
        'body,table,td,a{-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%}'
        'table,td{mso-table-lspace:0pt;mso-table-rspace:0pt}'
        'img{-ms-interpolation-mode:bicubic;border:0;height:auto;line-height:100%;'
        'outline:none;text-decoration:none}'
        
        # Без !important: скруглённые таблицы объявляют раздельную модель
        # инлайном, и оно обязано выигрывать.
        'table{border-collapse:collapse}'
        'body{margin:0 !important;padding:0 !important;width:100% !important}'
        f'a{{color:{ACCENT};text-decoration:none}}'
        '@media screen and (max-width:620px){'
        '.wrap{width:100% !important}'
        '.pad{padding-left:16px !important;padding-right:16px !important}'
        '.fact{display:block !important;width:100% !important;'
        'margin:0 0 6px 0 !important}'
        '.btn a{display:block !important;text-align:center !important}'
        '.h1{font-size:17px !important}}'
        '</style></head>'
        f'<body style="margin:0;padding:0;background-color:{CANVAS};">'
        # Предзаголовок — то, что клиент показывает в списке писем рядом с темой.
        # Без него туда попадает первая видимая строка, то есть слово из логотипа.
        '<div style="display:none;font-size:1px;line-height:1px;max-height:0;'
        'max-width:0;opacity:0;overflow:hidden;mso-hide:all;">'
        f'{_esc(preheader or headline)}&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'border="0" style="background-color:{CANVAS};"><tr>'
        f'<td align="center" style="padding:24px 12px;">'
        f'<table role="presentation" class="wrap" width="600" cellpadding="0" '
        f'cellspacing="0" border="0" style="width:600px;max-width:600px;'
        f'background-color:{CARD};border-collapse:separate;border-spacing:0;border:1px solid {BORDER};border-radius:{R_LETTER}px;">'
        f'<tr><td class="pad" style="padding:18px 22px 14px 22px;'
        f'border-bottom:1px solid {HAIR};">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'border="0"><tr><td align="left" style="vertical-align:middle;">{mark}</td>'
        f'<td align="right" style="vertical-align:middle;font-family:{MONO};'
        f'font-size:9px;letter-spacing:0.06em;text-transform:uppercase;color:{T4};">'
        f'{when.strftime("%d.%m.%Y")} · {when.strftime("%H:%M")}</td></tr></table>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'border="0" style="margin-top:12px;"><tr>'
        f'<td class="h1" style="font-family:{FONT};font-size:18px;font-weight:700;'
        f'letter-spacing:-0.02em;color:{T1};line-height:1.3;padding-bottom:4px;">'
        f'{_esc(headline)}</td></tr>{sub_html}</table>'
        f'</td></tr>'
        + _counters(counters) +
        '<tr><td class="pad" style="padding:14px 22px 6px 22px;">'
        + "".join(cards) +
        f'</td></tr>'
        f'<tr><td class="pad" style="padding:12px 22px 18px 22px;">'
        f'<div style="padding-top:12px;border-top:1px solid {HAIR};font-family:{FONT};'
        f'font-size:11px;color:{T3};line-height:1.5;">{_esc(footer)}</div>'
        f'</td></tr></table>'
        f'<table role="presentation" class="wrap" width="600" cellpadding="0" '
        f'cellspacing="0" border="0" style="width:600px;max-width:600px;"><tr>'
        f'<td align="center" style="padding:12px 16px 0 16px;font-family:{FONT};'
        f'font-size:10px;color:{T4};line-height:1.5;">'
        f'{_esc(brand)} · письмо собрано автоматически{foot_link}'
        f'</td></tr></table>'
        '</td></tr></table></body></html>')


# ── два вида письма ──────────────────────────────────────────────────────────

def notification_html(*, title: str, body: Optional[str], link_abs: Optional[str],
                      tone: str = "info", tag: str = "", action: str = "Открыть",
                      facts: Iterable[Fact] = (), brand: str = "SIMB-AD",
                      when: Optional[datetime] = None,
                      logo_url: Optional[str] = None,
                      settings_url: Optional[str] = None,
                      code: str = "",
                      context: Optional[str] = None,
                      audience: str = "staff") -> str:
    """Одно событие письмом.

    Заголовок письма и заголовок карточки совпадают намеренно: письмо про одно событие,
    и придумывать для шапки второй текст значило бы сказать то же самое дважды разными
    словами. Отличает их подзаголовок — он отвечает, почему письмо пришло.
    """
    # Умолчание — МОСКОВСКОЕ время, а не datetime.now(): контейнер живёт в UTC, и
    # забытый параметр давал получателю время на три часа в прошлом. Ловушку убираем,
    # а не сторожим: у отправителя не должно быть способа ошибиться молча.
    when = when or msk_now()
    _, _, _, word = PILLS.get(tone, PILLS["info"])
    card = _card(title=title, body=body, link_abs=link_abs, tone=tone, tag=tag,
                 when=when.strftime("%H:%M"), action=action, facts=facts,
                 context=context, code=code)
    # АДРЕСАТ МЕНЯЕТ СЛОВА, а не только адрес ссылки. «Включён в вашем профиле» и
    # «настраивается в системе» — это наш внутренний язык: у площадки нет ни профиля,
    # ни доступа в систему, и такое письмо читается как отправленное не тому. Увидели
    # это 16.09.2026 в предпросмотре — за полтора месяца отправки никто не заметил.
    if audience == "pub":
        sub = f"{word.capitalize()} · по вашей площадке"
        footer = "Что приходит на почту — настраивается в кабинете."
    else:
        sub = f"{word.capitalize()} · этот вид уведомления включён в вашем профиле"
        footer = "Что приходит и как часто — настраивается в системе."
    return _letter(
        brand=brand, logo_url=logo_url, when=when, headline=title,
        sub=sub, counters=(), cards=[card], footer=footer,
        settings_url=settings_url, preheader=(body or title))


def composed_html(*, cards_data: Sequence[dict], headline: str, sub: str,
                  preheader: str, footer: str, brand: str = "SIMB-AD",
                  when: Optional[datetime] = None, logo_url: Optional[str] = None,
                  settings_url: Optional[str] = None,
                  counters: bool = True) -> str:
    """Письмо, СОБРАННОЕ ИЗ ЗАДАННОЙ ОБОЛОЧКИ и произвольного набора карточек.

    Отличается от `digest_html` одним: шапку здесь не сочиняет код, её задаёт человек в
    редакторе шаблонов. Поэтому заголовок, подзаголовок, прехедер и подвал приходят
    готовыми строками — правила подстановки уже применены вызывающим.

    Карточки рисуются тем же `_card`, что и в живой отправке: другой рисовальщик
    означал бы, что редактор показывает не то письмо.
    """
    when = when or msk_now()
    order = {t: i for i, t in enumerate(TONE_ORDER)}
    rows = sorted(cards_data, key=lambda x: order.get(x.get("tone") or "info", 9))
    counts = [(t, sum(1 for x in rows if (x.get("tone") or "info") == t))
              for t in TONE_ORDER] if counters else ()
    cards = [_card(title=x.get("title") or "", body=x.get("body"),
                   link_abs=x.get("link_abs"), tone=x.get("tone") or "info",
                   tag=x.get("tag") or "", when=x.get("when") or "",
                   action=x.get("action") or "Открыть", facts=x.get("facts") or (),
                   context=x.get("context"), code=x.get("code") or "")
             for x in rows]
    return _letter(brand=brand, logo_url=logo_url, when=when, headline=headline,
                   sub=sub, counters=counts, cards=cards, footer=footer,
                   settings_url=settings_url, preheader=preheader)


def digest_html(*, items: Sequence[dict], to_name: str = "",
                brand: str = "SIMB-AD", when: Optional[datetime] = None,
                logo_url: Optional[str] = None,
                settings_url: Optional[str] = None) -> str:
    """Дайджест: несколько событий одним письмом со счётчиками в шапке.

    Шапка называет ЧИСЛО событий и сколько из них требуют действия — это то, ради чего
    письмо открывают. «У вас 6 уведомлений» без разбивки заставляет читать все шесть,
    чтобы понять, есть ли срочное.

    Порядок карточек — по тяжести тона, как в панели: сначала то, что блокирует работу.
    """
    when = when or msk_now()
    order = {t: i for i, t in enumerate(TONE_ORDER)}
    rows = sorted(items, key=lambda x: order.get(x.get("tone") or "info", 9))
    counts = [(t, sum(1 for x in rows if (x.get("tone") or "info") == t))
              for t in TONE_ORDER]
    need = sum(n for t, n in counts if t in ("bad", "warn"))

    who = f"{to_name}, за" if to_name else "За"
    headline = (f"{who} сутки {len(rows)} "
                f"{_plural(len(rows), 'событие', 'события', 'событий')}")
    # Три разных предложения, а не одно с подстановкой: «6 требуют действия, остальные —
    # к сведению» при шести событиях из шести обещает несуществующий остаток.
    if not need:
        sub = "Все — к сведению, действий не требуется."
    elif need == len(rows):
        sub = "Все требуют действия сегодня."
    else:
        sub = (f"{need} {_plural(need, 'требует', 'требуют', 'требуют')} действия сегодня, "
               f"остальные — к сведению.")

    cards = [_card(title=x.get("title") or "", body=x.get("body"),
                   link_abs=x.get("link_abs"), tone=x.get("tone") or "info",
                   tag=x.get("tag") or "", when=x.get("when") or "",
                   action=x.get("action") or "Открыть", facts=x.get("facts") or (),
                   context=x.get("context"), code=x.get("code") or "")
             for x in rows]
    return _letter(brand=brand, logo_url=logo_url, when=when, headline=headline, sub=sub,
                   counters=counts, cards=cards,
                   footer="Полная очередь всегда в дашборде. Состав и час дайджеста — "
                          "в настройках уведомлений.",
                   settings_url=settings_url, preheader=sub)


def _plural(n: int, one: str, few: str, many: str) -> str:
    """Согласование с числом. Одиннадцать — главная ловушка: по последней цифре оно
    было бы «событие»."""
    n = abs(int(n))
    if 11 <= n % 100 <= 14:
        return many
    last = n % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many
