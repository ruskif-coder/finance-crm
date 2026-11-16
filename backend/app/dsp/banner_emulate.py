# -*- coding: utf-8 -*-
"""Разметка баннера «как её собрал бы загрузчик DSP» — для проверки на отправке на согласование (владелец 16.11.2026).

На отправке боевого креатива в DSP ещё нет, а проверять надо уже тогда. Поэтому берём подготовленный архив из песочницы и
повторяем то, что делает загрузчик (сверено 16.11 с 720 живыми разметками DSP):
  · `<base href>` на место, где лежат файлы баннера (у DSP — её CDN, у нас — адрес, который браузер сайдкара отдаёт из
    присланных файлов);
  · `<meta name="ad.erid">` и `<meta name="ad.ordinfo">` (имя и ИНН рекламодателя) — по ним скрипт DSP рисует плашку;
  · `<meta name="ad.id">`, настройки `window.adsn.viewability` и скрипт видимости — в конце `<head>`;
  · в теле ровно одна ссылка — обёртка `<a href="{LINK_UNESC}" target="_blank">`, собственные ссылки баннера убираются.
Дальше разметка идёт в ту же обёртку `creatives.wrap_html`, что и при заливке, и в ту же проверку в браузере.

После заливки настоящая разметка DSP проверяется ещё раз (`banner_check`, этап креатива РК) — она ловит, если загрузчик
когда-нибудь начнёт размечать иначе, чем здесь.
"""
import base64
import html as html_mod
import json
import os
import re
from typing import Optional, Tuple

_HEAD_OPEN = re.compile(r"<head\b[^>]*>", re.I)
_HEAD_CLOSE = re.compile(r"</head\s*>", re.I)
_BODY_OPEN = re.compile(r"<body\b[^>]*>", re.I)
_BODY_CLOSE = re.compile(r"</body\s*>", re.I)
_BASE_TAG = re.compile(r"<base\b[^>]*>", re.I)
_LINK_TAG = re.compile(r"<a\b[^>]*>|</a\s*>", re.I)
WRAPPER = '<a href="{LINK_UNESC}" target="_blank" style="cursor:pointer">'


class TooBig(RuntimeError):
    """Файлы баннера не помещаются в запрос к браузеру сайдкара."""


def _ensure_head_body(html: str) -> str:
    if not _HEAD_OPEN.search(html):
        m = re.search(r"<html\b[^>]*>", html, re.I)
        html = (html[:m.end()] + "<head></head>" + html[m.end():]) if m else "<head></head>" + html
    if not _HEAD_CLOSE.search(html):
        # `</head>` в HTML необязателен (живой баннер 16.11.2026) — закрываем перед `<body>`, а без него сразу за `<head>`
        b = _BODY_OPEN.search(html)
        at = b.start() if b else _HEAD_OPEN.search(html).end()
        html = html[:at] + "</head>" + html[at:]
    if not _BODY_OPEN.search(html):
        end = _HEAD_CLOSE.search(html)
        tail = html[end.end():]
        tail = re.sub(r"</html\s*>", "", tail, flags=re.I)
        html = html[:end.end()] + "<body>" + tail + "</body>"
    return html


def _wrap_body(html: str) -> str:
    """Собственные ссылки баннера убрать, тело обернуть ссылкой DSP — как загрузчик."""
    b, e = _BODY_OPEN.search(html), None
    for e in _BODY_CLOSE.finditer(html):
        pass
    inner_end = e.start() if e else len(html)
    inner = _LINK_TAG.sub("", html[b.end():inner_end])
    return html[:b.end()] + WRAPPER + inner + "</a>" + html[inner_end:]


def emulate_loader(html: str, *, base: str, erid: str, ord_name: Optional[str], ord_inn: Optional[str],
                   viewability_src: Optional[str]) -> str:
    html = _BASE_TAG.sub("", _ensure_head_body(html or ""))
    top = [f'<meta name="ad.erid" content="{html_mod.escape(erid or "", quote=True)}">']
    if ord_name or ord_inn:
        info = json.dumps({"customer": {"name": ord_name or "", "inn": ord_inn or ""}}, ensure_ascii=True, separators=(",", ":"))
        top.append(f'<meta name="ad.ordinfo" content="{html_mod.escape(info, quote=True)}">')
    top.append(f'<base href="{html_mod.escape(base, quote=True)}">')
    bottom = ['<meta name="ad.id" content="{CAMP_ID}-{CR_ID}">']
    src = (viewability_src or "").strip()
    if src:
        bottom.append('<script type="text/javascript">window.adsn=window.adsn ||{};window.adsn.viewability = '
                      '{"s_trk": "{TR_KEY}", "cr_id":"{CR_ID}", "camp_id":"{CAMP_ID}"};</script>')
        bottom.append(f'<script type="text/javascript" src="{html_mod.escape(src, quote=True)}"></script>')
    h = _HEAD_OPEN.search(html)
    html = html[:h.end()] + "\n" + "\n".join(top) + html[h.end():]
    c = _HEAD_CLOSE.search(html)
    html = html[:c.start()] + "\n".join(bottom) + html[c.start():]
    return _wrap_body(html)


def click_link(advertiser_url: Optional[str], publisher_domain: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Куда ведёт клик и откуда это взялось: посадочная пары, а пока её нет — сайт площадки (владелец 16.11.2026)."""
    if (advertiser_url or "").strip():
        return advertiser_url.strip(), "посадочная"
    d = (publisher_domain or "").strip()
    if not d:
        return None, None
    return (d if d.lower().startswith(("http://", "https://")) else "https://" + d), "сайт площадки"


def sandbox_files(root: str, cap: int) -> dict:
    """Файлы распакованного баннера {относительный путь: base64}. Больше `cap` байт — TooBig."""
    out, total = {}, 0
    for dirpath, _dirs, names in os.walk(root):
        for n in names:
            full = os.path.join(dirpath, n)
            total += os.path.getsize(full)
            if total > cap:
                raise TooBig(f"файлы баннера больше {cap // (1024 * 1024)} МБ")
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            with open(full, "rb") as fh:
                out[rel] = base64.b64encode(fh.read()).decode("ascii")
    return out
