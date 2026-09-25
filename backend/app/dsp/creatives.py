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
import html as html_mod
import io
import json
import logging
import os
import re
import zipfile
from typing import Optional

import httpx

log = logging.getLogger("finance.dsp")

# Адрес скрипта видимости в коде НЕ живёт: он опознаёт поставщика, а репозиторий уходит
# на GitHub и история гита не переписывается. Значение задаётся на вкладке «Скрипт»
# админки трафика (`company_settings.dsp_viewability_src`) и приезжает сюда параметром.
# Пусто — обёртка идёт без скрипта видимости, и потребитель обязан сказать об этом вслух.

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


def ad_size_in_zip(data: bytes) -> Optional[tuple]:
    """`(ширина, высота)` из мета-тега баннера внутри архива, или None, если тега нет.

    Разбор один на проект — `launch_prep.sandbox.parse_ad_size`, тот же, которым живёт
    предпросмотр. Импорт внутри функции: конвейер DSP не должен тянуть за собой стадию
    сборки при старте.
    """
    from app.launch_prep.sandbox import parse_ad_size
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = [n for n in z.namelist() if n.lower().endswith((".html", ".htm"))]
            # index.html вперёд: в архиве бывают вспомогательные страницы без мета-тега.
            names.sort(key=lambda n: (os.path.basename(n).lower() != "index.html", n))
            for n in names:
                with z.open(n) as fh:
                    head = fh.read(8192).decode("utf-8", "ignore")
                wh = parse_ad_size(head)
                if wh:
                    return wh
    except (zipfile.BadZipFile, OSError, KeyError):
        return None
    return None


def upload_zip(client, data: bytes, filename: str = "creative.zip",
               *, local_ref=None, timeout: float = 60.0) -> dict:
    """Загрузить архив и получить HTML-код баннера.

    Возвращает `{"url": …, "html": …}` — URL нужен для разбора, когда загрузчик ответит
    не тем, чего ждали.
    """
    check_zip(data, filename)
    # Сюда попадает только то, что едет в НАШУ DSP, — значит и подготовка к ней уместна
    # всегда: архив, загруженный до 25.09.2026 или креатив, чей состав поменяли после
    # загрузки, дойдёт до загрузчика с размером и макросом ссылки. Хранимый файл не
    # меняется — правится отправляемая копия.
    from app.launch_prep.sandbox import prepare_for_dsp
    data, _ = prepare_for_dsp(data)
    require_ad_size(data)
    url = client.upload_get_url("zip")
    if not isinstance(url, str) or not url.startswith("http"):
        raise CreativeError(f"Upload.getUploadFileUrl вернул не URL: {str(url)[:200]}")
    req = {"url": url, "filename": filename, "bytes": len(data)}
    try:
        r = httpx.post(url, files={"file": (filename, data, "application/zip")},
                       timeout=timeout)
        r.raise_for_status()
        html = r.text
    except httpx.HTTPError as e:
        _journal_upload(client, local_ref, req, None, False, repr(e))
        raise CreativeError(f"Загрузка архива не удалась: {e!r}") from e

    # Загрузчик ВСЕГДА отвечает 200 и content-type text/html, а телом шлёт JSON:
    # {"result": {"width", "height", "size", "html"}} либо {"error": {"message", "code"}}.
    # Замерено 09.09.2026 на живом кабинете.
    #
    # Прежде тело считалось баннером как есть, и это две разные беды сразу: отказ
    # выглядел как «загрузчик вернул не HTML» (настоящая причина пряталась), а УСПЕХ
    # уезжал в `Creative.edit` json-обёрткой вместо разметки — молча и правдоподобно,
    # потому что и `<`, и макросы внутри строки есть, все наши проверки проходили.
    out = _parse_upload_body(html)
    if out.get("error"):
        _journal_upload(client, local_ref, req, html[:1000], False, out["error"])
        raise CreativeError(f"Загрузчик отклонил архив: {out['error']}")
    banner = out.get("html") or ""
    if not banner or "<" not in banner:
        _journal_upload(client, local_ref, req, html[:1000], False, "в ответе нет разметки")
        raise CreativeError(f"Загрузчик вернул не HTML: {html[:200]!r}")
    # Журнал ведёт клиент, но multipart идёт мимо него — записываем сами тем же контуром.
    _journal_upload(client, local_ref, req,
                    {"html_bytes": len(banner), "size": out.get("size")}, True, None)
    return {"url": url, "html": banner, "size": out.get("size"),
            "width": out.get("width"), "height": out.get("height")}


def require_ad_size(data: bytes) -> None:
    """Отказать ДО сети, если в баннере не объявлен размер.

    Загрузчик без мета-тега архив не принимает (его код 2053). Проверка здесь, а не
    только по ответу, потому что сказать это можно раньше — и сказать понятно: человеку
    нужно знать, ЧТО дописать в баннер, а не что «загрузчик отклонил архив».

    Размер НЕ подставляем: выдумать его нельзя, а имя файла врёт — то же рассуждение,
    что в `launch_prep.sandbox.read_size`. `0x0` пропускаем: это заявленный адаптивный
    баннер, и спорить с ним не наше дело.
    """
    if ad_size_in_zip(data) is None:
        raise CreativeError(
            'В баннере не объявлен размер. В index.html нужен тег '
            '<meta name="ad.size" content="width=240,height=400"> с настоящими '
            'размерами — без него DSP архив не принимает')


def _parse_upload_body(body: str) -> dict:
    """Разобрать ответ загрузчика: `{html, size, width, height}` либо `{error}`.

    Тело, которое не является его JSON, возвращаем как разметку: если загрузчик когда-то
    ответит голым HTML, конвейер не должен из-за этого встать.
    """
    s = (body or "").strip()
    if not s.startswith("{"):
        return {"html": body}
    try:
        doc = json.loads(s) or {}
    except ValueError:
        return {"html": body}

    err = doc.get("error")
    if isinstance(err, dict):
        # Сообщение приходит с html-экранированием («&lt;meta …&gt;») — читать его человеку.
        msg = html_mod.unescape(str(err.get("message") or "")).strip()
        code = err.get("code")
        return {"error": f"{msg} (код {code})" if code is not None else (msg or "без объяснения")}

    res = doc.get("result")
    if isinstance(res, dict):
        return {"html": res.get("html") or "", "size": res.get("size"),
                "width": res.get("width"), "height": res.get("height")}
    return {"html": body}


def _journal_upload(client, local_ref, req, resp, ok, error) -> None:
    """Записать попытку загрузки — В ТОМ ЧИСЛЕ неудачную.

    До 09.09.2026 писалась только удачная, и на экране получалось худшее: шаг не прошёл,
    а в журнале после `getUploadFileUrl` пусто, будто ничего и не отправляли.
    """
    try:
        client.journal_raw("Upload.file", "upload", local_ref, req, resp, None, ok, error)
    except Exception:  # noqa: BLE001 — журнал не должен подменять собой результат вызова
        log.warning("Не удалось записать в журнал попытку загрузки архива", exc_info=True)


def wrap_html(html: str, *, erid: Optional[str] = None,
              viewability_src: Optional[str] = None,
              extra_script: Optional[str] = None) -> str:
    """Обернуть HTML баннера так, как ждёт DSP.

    `viewability_src` — адрес скрипта видимости из настройки; пусто = не вшивать. Прежде
    здесь стоял булев флаг и константа с адресом в коде — адрес вынесен на экран
    09.09.2026, чтобы имя поставщика не жило в репозитории.

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
    if viewability_src and viewability_src.strip():
        head.append(f'<script src="{viewability_src.strip()}"></script>')
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


# Предел длины имени креатива — ЕГО, не наш: официальная дока говорит «>0, ≤150».
# До 09.09.2026 мы резали по 255, то есть длинное имя уезжало заведомо негодным.
TITLE_MAX = 150

# Размер: «240x400», адаптивный — «0x0». Применим к html и видео.
SIZE_RE = re.compile(r"^\d{1,5}x\d{1,5}$")


def html_state(c, xxhash: str) -> str:
    """Что с креативом в кабинете: `ok` — код на месте, `empty` — объект без кода,
    `gone` — такого нет.

    Нужна одна проверка: `Creative.add` заводит объект, а код вшивается ВТОРЫМ вызовом
    `Creative.edit`, и между ними связь может оборваться. Тогда в кабинете остаётся
    креатив без кода, и повторное заведение дало бы второй — первый по API не удалить.

    Недоступность DSP отдельным исходом НЕ делаем: молчащая связь не должна выглядеть
    как «всё хорошо», поэтому ошибка обмена поднимается наверх и человек видит её текстом.
    """
    from app.dsp.client import MsError

    try:
        info = c.creative_get_info(xxhash) or {}
    except MsError as e:
        if "not found" in str(e).lower():
            return "gone"
        raise
    data = info.get("data") if isinstance(info, dict) else None
    code = (data or {}).get("html_code") if isinstance(data, dict) else None
    return "ok" if (code or "").strip() else "empty"


def build_creative_params(*, title: str, link: str, erid: Optional[str] = None,
                          self_inn: Optional[str] = None, self_name: Optional[str] = None,
                          adomain: Optional[str] = None, size: Optional[str] = None,
                          total_shows: Optional[int] = None,
                          total_clicks: Optional[int] = None) -> dict:
    """Тело креатива по плану.

    `size` — «240x400» либо «0x0» у адаптивного. Берётся из ОТВЕТА загрузчика (он его
    и объявляет), а не выдумывается: имя файла врёт, а внутрь баннера размер пишет тот,
    кто его собрал. Без него DSP не знает, в какой блок креатив помещается.

    Лимиты — ТОЛЬКО `total`: при `uniform_pro` день и час на креативе конфликтуют с API
    (готча из теста владельца). `description` не трогаем ни здесь, ни в `Creative.edit` —
    ломается.
    """
    if not title or not title.strip():
        raise CreativeError("У креатива должно быть имя")
    if not link or not link.strip():
        raise CreativeError("У креатива должна быть посадочная ссылка")
    params = {"title": title.strip()[:TITLE_MAX], "link": link.strip()}
    if size and str(size).strip():
        s = str(size).strip().lower()
        if not SIZE_RE.match(s):
            raise CreativeError(
                f"Размер «{size}» не в формате ширинаxвысота (например 240x400, "
                f"адаптивный — 0x0)")
        params["size"] = s
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
