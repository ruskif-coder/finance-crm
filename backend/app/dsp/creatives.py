"""Конвейер креатива для DSP: архив → HTML → обёртка → креатив в кампании.

Цепочка по официальной доке и тесту владельца ([[dsp-api]]):

    Upload.getUploadFileUrl(type=zip) → URL с токеном
    POST multipart file=@archive.zip на этот URL → в ответ HTML-код баннера
    Creative.add(campaign_xxhash, …) → xxhash креатива
    Creative.edit(xxhash, data.html_code=<обёрнутый HTML>)

**Загрузка идёт НЕ через JSON-RPC.** Это обычный multipart-POST на выданный URL, поэтому
и живёт отдельной функцией, а не методом клиента: у клиента весь транспорт — JSON-RPC, и
подмешивать туда второй вид запроса значило бы, что «подменный транспорт» в тестах больше
не описывает всё общение с DSP.

Обёртка добавляет то, без чего креатив не считается площадкой: viewability-скрипт и
макросы. Значения макросов подставляет САМ DSP при выдаче — мы их не раскрываем, а
оставляем как есть; развернуть их у себя значило бы прибить креатив к одной площадке.
"""
import logging
import re
from typing import Optional

import httpx

log = logging.getLogger("finance.dsp")

VIEWABILITY_SRC = "https://static.bumlam.com/engine/viewability.js"

# Макросы DSP. Раскрывает их сам DSP в момент выдачи; наша задача — не потерять.
MACROS = ("{CAMP_ID}", "{CR_ID}", "{TR_KEY}", "{LINK_UNESC}", "{RID}", "{RND}",
          "{PUBLISHER}", "{S_DMN_OR_APP_ENC}", "{SRC_XXH64}")

ZIP_MAGIC = b"PK\x03\x04"
MAX_ZIP_BYTES = 20 * 1024 * 1024      # как ограничение на договорные файлы в contracts.py


class CreativeError(RuntimeError):
    """Ошибка конвейера креатива: не тот файл, не тот ответ загрузчика."""


def check_zip(data: bytes, filename: str = "") -> None:
    """Проверить, что это действительно zip и он не безразмерный.

    Загрузчик DSP на чужой файл отвечает своей страницей, а не ошибкой, и мы получили бы
    «HTML» из его формы вместо баннера — молча и правдоподобно.
    """
    if not data:
        raise CreativeError("Пустой файл")
    if len(data) > MAX_ZIP_BYTES:
        raise CreativeError(f"Архив больше {MAX_ZIP_BYTES // (1024 * 1024)} МБ")
    if not data.startswith(ZIP_MAGIC):
        raise CreativeError(f"Это не zip-архив: {filename or 'файл'} начинается не с PK")


def upload_zip(client, data: bytes, filename: str = "creative.zip",
               *, local_ref=None, timeout: float = 60.0) -> dict:
    """Загрузить архив и получить HTML-код баннера.

    Возвращает `{"url": …, "html": …}` — URL нужен для разбора, когда загрузчик ответит
    не тем, чего ждали.
    """
    check_zip(data, filename)
    url = client.upload_get_url("zip")
    if not isinstance(url, str) or not url.startswith("http"):
        raise CreativeError(f"Upload.getUploadFileUrl вернул не URL: {str(url)[:200]}")
    try:
        r = httpx.post(url, files={"file": (filename, data, "application/zip")},
                       timeout=timeout)
        r.raise_for_status()
        html = r.text
    except httpx.HTTPError as e:
        raise CreativeError(f"Загрузка архива не удалась: {e!r}") from e
    if not html or "<" not in html:
        raise CreativeError(f"Загрузчик вернул не HTML: {html[:200]!r}")
    # Журнал ведёт клиент, но multipart идёт мимо него — записываем сами тем же контуром.
    client.journal_raw("Upload.file", "upload", local_ref,
                       {"url": url, "filename": filename, "bytes": len(data)},
                       {"html_bytes": len(html)}, None, True, None)
    return {"url": url, "html": html}


def wrap_html(html: str, *, erid: Optional[str] = None, viewability: bool = True,
              extra_script: Optional[str] = None) -> str:
    """Обернуть HTML баннера так, как ждёт DSP.

    `extra_script` — наш счётчик, который вшивается В КРЕАТИВ перед отправкой (уточнение
    владельца 06.09.2026). Их два, и какой именно — решает `traffic_catalog.creative_script`
    по признаку «на сайте стоит наш код». Выбор делается ТАМ, а не здесь: одна точка на
    систему, иначе часть креативов уехала бы в DSP с чужим счётчиком.

    Сетевых вызовов не делает — обёртку видно до отправки, и в этом её проверка.
    """
    if not html or not html.strip():
        raise CreativeError("Нечего оборачивать: пустой HTML")
    head = []
    if extra_script and extra_script.strip():
        # Первым: счётчик должен успеть встать до отрисовки баннера.
        head.append(extra_script.strip())
    if viewability:
        head.append(f'<script src="{VIEWABILITY_SRC}"></script>')
        head.append("<script>window.adsn = window.adsn || {};"
                    " window.adsn.viewability = window.adsn.viewability || {};</script>")
    if erid:
        # Маркировка живёт полем креатива, но в разметке она нужна видимой — иначе на
        # площадке её негде показать.
        head.append(f'<meta name="erid" content="{erid}">')
    if not head:
        return html
    block = "\n".join(head)
    if re.search(r"<head[^>]*>", html, re.I):
        return re.sub(r"(<head[^>]*>)", r"\1\n" + block, html, count=1, flags=re.I)
    if re.search(r"<html[^>]*>", html, re.I):
        return re.sub(r"(<html[^>]*>)", r"\1\n<head>\n" + block + "\n</head>", html,
                      count=1, flags=re.I)
    return f"<head>\n{block}\n</head>\n{html}"


def macros_found(html: str) -> list:
    """Какие макросы DSP остались в разметке. Пустой список — повод насторожиться:
    креатив без `{RID}`/`{LINK_UNESC}` не отследится и не кликнется."""
    return [m for m in MACROS if m in (html or "")]


def build_creative_params(*, title: str, link: str, erid: Optional[str] = None,
                          self_inn: Optional[str] = None, self_name: Optional[str] = None,
                          adomain: Optional[str] = None,
                          total_shows: Optional[int] = None,
                          total_clicks: Optional[int] = None) -> dict:
    """Тело креатива по плану.

    Лимиты — ТОЛЬКО `total`: при `uniform_pro` день и час на креативе конфликтуют с API
    (готча из теста владельца). `description` не трогаем ни здесь, ни в `Creative.edit` —
    ломается.
    """
    if not title or not title.strip():
        raise CreativeError("У креатива должно быть имя")
    if not link or not link.strip():
        raise CreativeError("У креатива должна быть посадочная ссылка")
    params = {"title": title.strip()[:255], "link": link.strip()}
    if erid:
        params["erid"] = erid.strip()
    if self_inn:
        params["self_inn"] = self_inn.strip()
    if self_name:
        params["self_name"] = self_name.strip()
    if adomain:
        params["adomain"] = adomain.strip()
    limits = {}
    if total_shows:
        limits["show"] = {"total": int(total_shows)}
    if total_clicks:
        limits["click"] = {"total": int(total_clicks)}
    if limits:
        params["limits"] = limits
    return params
