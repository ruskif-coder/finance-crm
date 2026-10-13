# -*- coding: utf-8 -*-
"""Тизер в DSP — ВСЁ, что про этот тип креатива, живёт здесь (владелец 13.10.2026).

Правило владельца: любое движение в DSP идёт через пакет `app/dsp`, и кода про тизер нет
больше нигде. Вызывающие места (`provision`, экран сборки) знают только три имени отсюда:
`is_teaser`, `material_problem`/`format_warning` и `create`.

Что такое тизер Купера (эталон `Creative.getInfo`, замер 13.10.2026):
  * `type=TEASER`; в `data` — картинка `imgMask` 640×200 (ссылка на CDN DSP) и иконка `iconMask`
    80×80; заголовок и текст обязательны, но площадка их не показывает — идут заглушкой;
  * `link` — ссылка клика (диплинк в приложение), `adomain` — веб-адрес на случай, если диплинк не
    сработает; `erid` на креативе;
  * картинка не едет в теле запроса: её сначала грузят модулем `teaser` (`Upload.getUploadFileUrl`),
    ответ несёт `file_url` — он и идёт в `imgMask`.

Диплинк `storefront://…` DSP по API пока отвергает («Invalid macro», проба 13.10.2026) — владелец:
считаем, что принимать будут в том виде, в каком он у нас есть, поэтому здесь он уходит как есть, а
отказ DSP показывается текстом в отчёте выгрузки.
"""
import io
import logging
from typing import Optional

import httpx

from app.dsp import creatives as cr
from app.dsp.client import MsError, safe_error
from app.launch_prep import pub_rules

log = logging.getLogger("finance.dsp")

HTML = "HTML"
TEASER = "TEASER"

IMG_W, IMG_H = 640, 200
IMG_FORMAT = f"{IMG_W}x{IMG_H}"
IMG_EXT = (".jpg", ".jpeg", ".png")
IMG_MAX_BYTES = 6 * 1024 * 1024

# Иконку требует DSP, площадка её не показывает — одна на всех (владелец 13.10.2026). Адрес — в настройке
# `dsp_teaser_icon_url` (app/dsp/config.py), а не в коде: он на CDN поставщика DSP.
ICON_FORMAT = "80x80"
NO_ICON = ("не задана иконка тизера — настройка dsp_teaser_icon_url (адрес картинки 80×80 на CDN DSP)")
# Заголовок и текст обязательны у DSP, Купер их не показывает.
STUB_TEXT = "Реклама"

FILE_MISSING = "к креативу не привязан файл комплекта"
NOT_ARCHIVE = "файл креатива не архив — загрузчик DSP принимает zip"


def format_of(rule: Optional[dict]) -> str:
    return (rule or {}).get("creative_format") or HTML


def is_teaser(rule: Optional[dict]) -> bool:
    return format_of(rule) == TEASER


def _ext(f) -> str:
    name = (getattr(f, "original_name", None) or getattr(f, "path", None) or "").lower()
    return "." + name.rsplit(".", 1)[-1] if "." in name else ""


def material_problem(fmt: str, f) -> Optional[str]:
    """Почему файл комплекта не годится площадке с ЭТИМ форматом. Пусто — годится.

    Один вопрос для двух мест: выгрузка (причина отказа) и экран сборки (предупреждение
    до отправки). Два разных ответа на «подходит ли материал» разошлись бы.
    """
    if fmt not in (HTML, TEASER):
        return f"формат «{fmt}» конвейер пока не отправляет в DSP"
    if not f:
        return FILE_MISSING
    if fmt == TEASER:
        if getattr(f, "is_archive", False):
            return (f"площадка принимает тизер: нужна картинка {IMG_W}×{IMG_H} (jpg или png), "
                    f"а в комплекте архив")
        if _ext(f) not in IMG_EXT:
            return f"для тизера нужна картинка {IMG_W}×{IMG_H} в jpg или png"
        return None
    if not getattr(f, "is_archive", False):
        return NOT_ARCHIVE
    return None


def format_warning(fmt: str, files) -> Optional[str]:
    """Предупреждение на экране сборки: ни один файл комплекта не подходит формату площадки.
    Нет файлов — сравнивать не с чем, молчим (комплект ещё собирается)."""
    files = list(files or [])
    if not files:
        return None
    problems = [material_problem(fmt, f) for f in files]
    return None if any(p is None for p in problems) else problems[0]


def check_image(data: bytes, filename: str = "") -> None:
    """Картинка тизера: настоящее изображение jpg/png ровно 640×200. Свой отказ до сети —
    DSP формат не проверяет (так было с размером баннера), и кривая картинка ушла бы в кабинет."""
    if not data:
        raise cr.CreativeError("Файл тизера пустой")
    if len(data) > IMG_MAX_BYTES:
        raise cr.CreativeError(f"Картинка тизера больше {IMG_MAX_BYTES // 1024 // 1024} МБ")
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        fmt, size = im.format, im.size
    except Exception as e:  # noqa: BLE001 — любой сбой разбора = «это не картинка»
        raise cr.CreativeError(f"Файл «{filename}» не читается как картинка") from e
    if fmt not in ("JPEG", "PNG"):
        raise cr.CreativeError(f"Картинка тизера — jpg или png, а не {fmt}")
    if size != (IMG_W, IMG_H):
        raise cr.CreativeError(
            f"Картинка тизера должна быть {IMG_W}×{IMG_H}, а в файле {size[0]}×{size[1]}")


def upload_image(client, data: bytes, filename: str = "teaser.jpg",
                 *, local_ref=None, timeout: float = 60.0) -> dict:
    """Загрузить картинку модулем `teaser` → `{"url": <CDN>, "resolution": "640x200"}`.

    Загрузчик отвечает 200 и text/html, а телом — JSON (как и у архива): `{"result": {"file":
    {"file_url", "resolution", …}}}` либо `{"error": …}` (замер 13.10.2026).
    """
    check_image(data, filename)
    url = client.upload_get_url("teaser")
    if not isinstance(url, str) or not url.startswith("http"):
        raise cr.CreativeError(f"Upload.getUploadFileUrl вернул не URL: {str(url)[:200]}")
    req = {"url": "<адрес загрузки DSP>", "filename": filename, "bytes": len(data),
           "module": "teaser"}
    mime = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
    try:
        r = httpx.post(url, files={"file": (filename, data, mime)}, timeout=timeout)
        r.raise_for_status()
        body = r.json()
    except (httpx.HTTPError, ValueError) as e:
        cr._journal_upload(client, local_ref, req, None, False, safe_error(e))
        raise cr.CreativeError(f"Загрузка картинки тизера не удалась: {safe_error(e)}") from e
    err = body.get("error") if isinstance(body, dict) else None
    file = ((body.get("result") or {}).get("file") or {}) if isinstance(body, dict) else {}
    if err or not file.get("file_url"):
        msg = (err or {}).get("message") if isinstance(err, dict) else (err or "в ответе нет file_url")
        cr._journal_upload(client, local_ref, req, str(body)[:1000], False, str(msg))
        raise cr.CreativeError(f"Загрузчик отклонил картинку тизера: {msg}")
    cr._journal_upload(client, local_ref, req, {"file_url": file["file_url"],
                                                "resolution": file.get("resolution")}, True, None)
    return {"url": file["file_url"], "resolution": file.get("resolution")}


def teaser_data(img_url: str, icon_url: str) -> dict:
    return {"imgMask": img_url, "imgFormats": [IMG_FORMAT],
            "iconMask": icon_url, "iconFormats": [ICON_FORMAT],
            "title": STUB_TEXT, "text": STUB_TEXT, "wrapper": False}


def build_params(*, title: str, link: str, adomain: Optional[str], erid: Optional[str],
                 img_url: str, icon_url: str, total_shows: Optional[int] = None,
                 pixel: Optional[str] = None) -> dict:
    """Тело `Creative.add` для тизера. Без `size`, `self_inn`/`self_name`, `extension_link` и
    аудитных полей — у тизера их нет (документация DSP, 13.10.2026). Лимит — `total` показов, день и час нули."""
    if not title or not title.strip():
        raise cr.CreativeError("У креатива должно быть имя")
    if not link or not link.strip():
        raise cr.CreativeError("У креатива должна быть ссылка клика")
    params = {"type": TEASER, "title": title.strip()[:cr.TITLE_MAX], "link": link.strip(),
              "data": teaser_data(img_url, icon_url),
              "limits": {"show": {"total": int(total_shows or 0), "hour": 0, "day": 0},
                         "click": {"total": 0, "hour": 0, "day": 0},
                         "budget": {"total": 0, "hour": 0, "day": 0}}}
    if adomain:
        params["adomain"] = adomain.strip()
    if erid:
        params["erid"] = erid.strip()
    if pixel:
        params["pixel"] = pixel.strip()
    return params


def state(c, xxhash: str) -> str:
    """`ok` — креатив на месте и картинка в нём есть; `empty` — объект без картинки; `gone` — нет.
    Недоступность DSP наверх, как у `html_state`: молчащая связь не должна выглядеть как «всё хорошо»."""
    try:
        info = c.creative_get_info(xxhash) or {}
    except MsError as e:
        if "not found" in str(e).lower():
            return "gone"
        raise
    data = info.get("data") if isinstance(info, dict) else None
    return "ok" if isinstance(data, dict) and data.get("imgMask") else "empty"


def links_of(target) -> tuple:
    """(ссылка клика, конечный адрес). Клик — ссылка в приложении, если она есть у пары (своя схема
    или диплинк SDK), иначе веб; `adomain` — веб-адрес."""
    own = getattr(target, "advertiser_url", None)
    web = pub_rules.web_url(own)
    deep = (getattr(target, "deeplink_url", None) or "").strip()
    if not deep and own and (pub_rules.is_app_link(own) or pub_rules.is_app_scheme(own)):
        deep = own.strip()
    return (deep or web), web


def link_pair(target) -> tuple:
    """(ссылка клика, конечный адрес) для тизера: веб-ссылка нормализуется правилом HTML-креативов,
    ссылка в приложении уходит как есть."""
    link, web = links_of(target)
    click = cr.landing_link(web) if link == web else link
    return click, cr.landing_adomain(web)


def create(c, campaign: str, *, ref: str, known: Optional[str], img_state: str, title: str,
           link: str, adomain: Optional[str], erid: Optional[str], data: bytes, filename: str,
           icon_url: str = "", total_shows: Optional[int] = None, pixel_of=None, before_add=None) -> str:
    """Завести тизер и вернуть xxhash. Картинка грузится модулем `teaser`, дальше один
    `Creative.add` (разметки вторым вызовом, как у HTML, нет).

    `known` + `img_state == "empty"` — прошлый проход завёл объект без картинки: дописываем её
    правкой, а не заводим второй креатив (в кабинете его не удалить). Вызывается из
    `assemble.ensure`; напрямую — только в тестах.
    """
    if not (icon_url or "").strip():
        raise cr.CreativeError(NO_ICON)          # до загрузки картинки: сироту в CDN не плодим
    up = upload_image(c, data, filename or "teaser.jpg", local_ref=ref)
    if known and img_state == "empty":
        c.creative_edit(known, {"data": teaser_data(up["url"], icon_url)}, local_ref=ref)
        return known
    pixel = pixel_of(up) if pixel_of else None
    if before_add:
        before_add()
    params = build_params(title=title, link=link, adomain=adomain, erid=erid, img_url=up["url"], icon_url=icon_url,
                          total_shows=total_shows, pixel=pixel)
    return c.creative_add(campaign, params, local_ref=ref)
