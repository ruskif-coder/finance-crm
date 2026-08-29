"""Скриншоты размещения: имя собираем мы, картинку пережимаем.

Обе задачи здесь, а не в роутере, ровно потому, что обе — правила, а не обработка
запроса: их проверяют тестами по входу и выходу, без клиента и без базы.
"""
import io
import os
import re
from typing import Optional, Tuple

# Предел на пару. Проверяется в коде, а не триггером: триггеров в проекте нет ни одного,
# и заводить первый ради счётчика не стоит. Владелец: снимают до 5 сайтов по 3–5 кадров,
# то есть 10 — это запас от случайной выгрузки папки, а не рамка для работы.
MAX_PAIR_FILES = 10

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

# Замер на настоящих файлах: PNG 1186 КБ → WebP q82 198 КБ, шестикратно. На скриншотах
# с текстом и шумом разрыв обычно больше. JPEG звенит вокруг текста и превращает адресную
# строку в мыло; AVIF жмёт лучше на 15–20 %, но кодирует в разы дольше и тянет ещё одну
# библиотеку; PNG-оптимизация даёт единицы процентов. Pillow уже стоит.
WEBP_QUALITY = 85
MAX_SIDE = 1920

CONTENT_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".webp": "image/webp", ".pdf": "application/pdf"}


def _ascii_code(value: Optional[str], fallback: str) -> str:
    """Кусок имени: только латиница и цифры.

    Кириллица в именах внутри zip ломается у части распаковщиков Windows, а архив уходит
    клиенту — ломаться ему нельзя. Пустой результат заменяется запасным куском, чтобы имя
    не схлопнулось в цепочку дефисов.
    """
    cleaned = re.sub(r"[^A-Za-z0-9]", "", value or "")
    return cleaned or fallback


def traffic_file_name(deal_code: Optional[str], publisher_code: Optional[str],
                      creative_no: int, seq: int, ext: str) -> str:
    """`HCLA6E-SMK1-cr2-01.webp` — вся цепочка в имени, без единого действия человека.

    `cr` перед номером креатива обязателен: без него `HCLA6E-SMK1-2-01` неотличимо от
    кода пары `HCLA6E-SMK1-01` с лишним числом.

    Порядковый номер даёт правильную сортировку сам собой: по имени = по загрузке =
    по маршруту съёмки. Подписей к файлам нет намеренно — грузят пакетом.
    """
    deal = _ascii_code(deal_code, "deal")
    pub = _ascii_code(publisher_code, "site")
    return f"{deal}-{pub}-cr{int(creative_no)}-{int(seq):02d}{ext}"


def creative_download_name(deal_code: Optional[str], creative_no: int, ext: str) -> str:
    """Под каким именем материал ложится на диск проверяющему: `HCLA6E-cr1.zip`.

    Имя нужно ровно затем же, зачем и у скриншотов: в загрузках у трафика лежат десятки
    файлов из разных кампаний, и `banner_final_v2.zip` среди них не опознать. Латиница —
    по той же причине: файл уходит дальше, в том числе клиенту.

    Расширение приходит снаружи: у одиночного файла оно СВОЁ, и подменять его на `.zip`
    нельзя — картинка перестанет открываться двойным щелчком.
    """
    return f"{_ascii_code(deal_code, 'deal')}-cr{int(creative_no)}{ext}"


def convert(content: bytes, ext: str) -> Tuple[bytes, str, str]:
    """Картинку — в WebP q=85 со стороной до 1920. Возвращает (байты, расширение, тип).

    Четыре правила, и каждое из-за конкретной причины:

    1. **PDF не трогаем** — это не картинка;
    2. **метаданные срезаются** — в EXIF попадают модель устройства и путь к файлу;
    3. **не конвертируем, если не стало меньше** — уже пережатый скриншот иногда растёт,
       и класть больший файл вместо меньшего было бы прямым вредом;
    4. **исходник не храним** — иначе экономии нет вовсе. Конвертация необратима, и для
       «посмотреть, как встал баннер» этого достаточно с запасом.

    Нечитаемый файл возвращается как есть: отказывать в загрузке доказательства из-за
    того, что мы не смогли его пережать, — не наше решение.
    """
    if ext not in IMAGE_EXTENSIONS:
        return content, ext, CONTENT_TYPES.get(ext, "application/octet-stream")

    try:
        from PIL import Image
        img = Image.open(io.BytesIO(content))
        img.load()
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        if max(img.size) > MAX_SIDE:
            ratio = MAX_SIDE / max(img.size)
            img = img.resize((max(1, round(img.width * ratio)),
                              max(1, round(img.height * ratio))), Image.LANCZOS)
        buf = io.BytesIO()
        # Без `exif=`/`icc_profile=` — Pillow их не переносит, и это ровно то, что нужно.
        img.save(buf, format="WEBP", quality=WEBP_QUALITY, method=6)
        out = buf.getvalue()
    except Exception:       # noqa: BLE001 — битый или незнакомый файл кладём как есть
        return content, ext, CONTENT_TYPES.get(ext, "application/octet-stream")

    if len(out) >= len(content):
        return content, ext, CONTENT_TYPES.get(ext, "application/octet-stream")
    return out, ".webp", "image/webp"


def split_ext(original_name: Optional[str]) -> str:
    return os.path.splitext(original_name or "")[1].lower()
