# -*- coding: utf-8 -*-
"""Проверка загруженного креатива: картинка или HTML5-архив (владелец 07.10.2026).

БЛОКИРУЕМ ТОЛЬКО полную несовместимость и битый архив: чужой тип файла, не читается, нет HTML,
не открывается архив, слишком велик. Всё остальное — ЗАМЕЧАНИЯ: человек всё равно может получить
нацеливание и посмотреть баннер глазами.

Картинка заворачивается в HTML5-архив (index.html + файл): загрузчик DSP принимает только zip,
а креатив в DSP по сути и есть html_code. Архив готовится тем же `sandbox.prepare_for_dsp`, что и
боевые баннеры, — одна подготовка на проект.
"""
import io
import os
import re
import struct
import zipfile
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from app.dsp import creatives as cr
from app.launch_prep import sandbox

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# Ориентиры веса, а не требования площадок: сверх них — замечание, не отказ.
HEAVY_IMAGE_BYTES = 300 * 1024
HEAVY_ARCHIVE_BYTES = 1024 * 1024
RASTER_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
IMAGE_EXT = RASTER_EXT | {".svg"}

PREPARED_LABELS = {
    "ad.size": "размер не был объявлен — вшит адаптивный (width=0,height=0)",
    "link": "ссылка клика заменена макросом {LINK_UNESC}",
    "root": "HTML поднят из вложенной папки в корень архива",
    "mac": "убран мусор Mac-архиватора",
}


class CheckRejected(Exception):
    """Креатив несовместим или архив битый: причины словами."""

    def __init__(self, *messages: str):
        self.messages = [m for m in messages if m]
        super().__init__("; ".join(self.messages))


@dataclass
class Analysis:
    kind: str                      # image | html5
    zip_bytes: bytes               # то, что едет в DSP и показывается в песочнице
    warnings: List[str] = field(default_factory=list)
    prepared: List[str] = field(default_factory=list)
    info: dict = field(default_factory=dict)


# ── картинки ────────────────────────────────────────────────────────────────

_JPEG_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def _jpeg_size(b: bytes) -> Optional[Tuple[int, int]]:
    i = 2
    while i + 9 < len(b):
        if b[i] != 0xFF:
            i += 1
            continue
        marker = b[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker in _JPEG_SOF:
            h, w = struct.unpack(">HH", b[i + 5:i + 9])
            return w, h
        i += 2 + struct.unpack(">H", b[i + 2:i + 4])[0]
    return None


def _webp_size(b: bytes) -> Optional[Tuple[int, int]]:
    chunk = b[12:16]
    if chunk == b"VP8 " and len(b) >= 30:
        w, h = struct.unpack("<HH", b[26:30])
        return w & 0x3FFF, h & 0x3FFF
    if chunk == b"VP8L" and len(b) >= 25:
        bits = struct.unpack("<I", b[21:25])[0]
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8X" and len(b) >= 30:
        return int.from_bytes(b[24:27], "little") + 1, int.from_bytes(b[27:30], "little") + 1
    return None


def _svg_size(b: bytes) -> Optional[Tuple[int, int]]:
    head = b[:4096].decode("utf-8", "ignore")
    m = re.search(r"<svg\b[^>]*>", head, re.I | re.S)
    if not m:
        return None
    tag = m.group(0)

    def num(attr):
        v = re.search(rf"\b{attr}\s*=\s*[\"']\s*([\d.]+)\s*(?:px)?\s*[\"']", tag, re.I)
        return int(float(v.group(1))) if v else None

    w, h = num("width"), num("height")
    if w and h:
        return w, h
    vb = re.search(r"viewBox\s*=\s*[\"']\s*[\d.\-]+[ ,]+[\d.\-]+[ ,]+([\d.]+)[ ,]+([\d.]+)", tag, re.I)
    if vb:
        return int(float(vb.group(1))), int(float(vb.group(2)))
    return 0, 0                      # svg без размеров — адаптивный


def detect_image(b: bytes) -> Optional[str]:
    """Тип по содержимому, а не по имени: переименованный файл не должен проходить."""
    if b.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if b.startswith(b"\xff\xd8"):
        return ".jpg"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return ".webp"
    if b"<svg" in b[:4096].lower():
        return ".svg"
    return None


def image_size(b: bytes) -> Optional[Tuple[int, int]]:
    kind = detect_image(b)
    if kind == ".png" and len(b) >= 24:
        return struct.unpack(">II", b[16:24])
    if kind == ".gif" and len(b) >= 10:
        return struct.unpack("<HH", b[6:10])
    if kind == ".jpg":
        return _jpeg_size(b)
    if kind == ".webp":
        return _webp_size(b)
    if kind == ".svg":
        return _svg_size(b)
    return None


def _wrap_picture(ext: str, data: bytes, w: int, h: int) -> bytes:
    pic = f"banner{ext}"
    dims = f' width="{w}" height="{h}"' if w and h else ""
    html = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f'<meta name="ad.size" content="width={w},height={h}">'
        '<style>html,body{margin:0;padding:0}img{display:block;border:0}</style></head>'
        f'<body><a href="{sandbox.DSP_CLICK_MACRO}" target="_blank"><img src="{pic}"{dims}></a></body></html>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("index.html", html)
        z.writestr(pic, data)
    return buf.getvalue()


def _analyze_image(data: bytes) -> Analysis:
    ext = detect_image(data)
    if not ext:
        raise CheckRejected("Файл не читается как изображение (png, jpg, gif, webp, svg)")
    size = image_size(data)
    if size is None:
        raise CheckRejected("Не удалось прочитать размер изображения — файл повреждён?")
    w, h = size
    warnings = []
    if len(data) > HEAVY_IMAGE_BYTES:
        warnings.append(f"Тяжёлая картинка: {len(data) // 1024} КБ (ориентир — до {HEAVY_IMAGE_BYTES // 1024} КБ)")
    return Analysis("image", _wrap_picture(ext, data, w, h), warnings, [],
                    {"size": f"{w}x{h}" if w and h else "адаптивный", "bytes": len(data),
                     "entry": "index.html"})


# ── HTML5-архивы ────────────────────────────────────────────────────────────

_EXTERNAL = re.compile(
    r"""(?:\bsrc\s*=\s*|<link\b[^>]*?\bhref\s*=\s*|url\(\s*|@import\s+)["']?(https?://[^"'\s)>]+)""", re.I)
_DYNAMIC = [
    (re.compile(r"\beval\s*\(|new\s+Function\s*\("), "динамическое выполнение кода (eval / new Function)"),
    (re.compile(r"document\.write\s*\("), "document.write"),
    (re.compile(r"<iframe\b", re.I), "iframe внутри баннера"),
    (re.compile(r"window\.open\s*\(|\b(?:top|parent)\.location\b"),
     "попап или редирект страницы (window.open / top.location)"),
]
_TEXT_EXT = (".html", ".htm", ".js", ".css")
_MAX_SCAN = 2 * 1024 * 1024
_MAX_SCAN_FILES = 40


def _scan_texts(z: zipfile.ZipFile) -> List[str]:
    out = []
    for info in z.infolist():
        if info.is_dir() or not info.filename.lower().endswith(_TEXT_EXT) or info.file_size > _MAX_SCAN:
            continue
        out.append(z.read(info.filename).decode("utf-8", "ignore"))
        if len(out) >= _MAX_SCAN_FILES:
            break
    return out


def _remarks(texts: List[str], entry_html: str, archive_bytes: int) -> List[str]:
    warnings = []
    blob = "\n".join(texts)
    hosts, plain = set(), set()
    for m in _EXTERNAL.finditer(blob):
        url = m.group(1)
        hosts.add(urlparse(url).hostname or url)
        if url.lower().startswith("http://"):
            plain.add(url)
    if hosts:
        warnings.append("Внешние ресурсы: " + ", ".join(sorted(hosts)[:6])
                        + " — площадки и DSP могут их блокировать")
    if plain:
        warnings.append("Небезопасные http://-ссылки на ресурсы (нужен https): "
                        + ", ".join(sorted(plain)[:3]))
    for rx, text in _DYNAMIC:
        if rx.search(blob):
            warnings.append(f"В коде найдено: {text}")
    problem = sandbox.click_problem(entry_html)
    if problem:
        warnings.append(f"Клик: {problem} — перед боевым запуском посмотрите ссылку в коде")
    if archive_bytes > HEAVY_ARCHIVE_BYTES:
        warnings.append(f"Тяжёлый архив: {archive_bytes // 1024} КБ (ориентир — до {HEAVY_ARCHIVE_BYTES // 1024} КБ)")
    return warnings


def _analyze_zip(name: str, data: bytes) -> Analysis:
    try:
        cr.check_zip(data, name)
    except cr.CreativeError as e:
        raise CheckRejected(str(e))
    try:
        prepared_bytes, prepared = sandbox.prepare_for_dsp(data)
        z = zipfile.ZipFile(io.BytesIO(prepared_bytes))
    except zipfile.BadZipFile:
        raise CheckRejected("Файл не читается как ZIP-архив")
    except sandbox.SandboxError as e:
        raise CheckRejected(str(e))
    with z:
        entry = sandbox._pick_entry([i.filename for i in z.infolist() if not i.is_dir()])
        if not entry:
            raise CheckRejected("В архиве нет HTML-файла — баннеру нужен index.html")
        entry_html = z.read(entry).decode("utf-8", "ignore")
        warnings = _remarks(_scan_texts(z), entry_html, len(data))
        wh = sandbox.parse_ad_size(entry_html)
    size = "адаптивный" if not wh or wh == (0, 0) else f"{wh[0]}x{wh[1]}"
    return Analysis("html5", prepared_bytes, warnings, list(prepared),
                    {"size": size, "bytes": len(data), "entry": os.path.basename(entry)})


def analyze(filename: str, data: bytes) -> Analysis:
    ext = os.path.splitext(filename or "")[1].lower()
    if not data:
        raise CheckRejected("Пустой файл")
    if len(data) > MAX_UPLOAD_BYTES:
        raise CheckRejected(f"Файл больше {MAX_UPLOAD_BYTES // 1024 // 1024} МБ")
    if ext in IMAGE_EXT:
        return _analyze_image(data)
    if ext == ".zip":
        return _analyze_zip(filename, data)
    if ext in (".html", ".htm"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("index.html", data)
        return _analyze_zip("index.zip", buf.getvalue())
    raise CheckRejected("Недопустимый тип файла. Нужна картинка (png, jpg, gif, webp, svg), "
                        "HTML5-архив (zip) или html")
