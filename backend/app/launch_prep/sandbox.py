"""Распаковка HTML5-баннера в песочницу.

ЧТО ЭТО. Архив с баннером разворачивается на диск в каталог со случайным именем, и этот
каталог раздаётся статикой с ОТДЕЛЬНОГО домена (`sb.simbad.pro`, локально `sb.localhost`), где нет ни нашей сессии, ни
нашего API. Показать чужой исполняемый код иначе нельзя: с нашего домена он получает наши
куки и хранилище, а из `blob:` не находит собственные файлы по относительным путям.

ПОЧЕМУ РАСПАКОВКА ЗДЕСЬ, А НЕ В РАЗДАЧЕ. Раздача — обычный `file_server` Caddy, у него нет
и не должно быть кода. Значит все проверки живут на входе, при загрузке файла, и архив,
который их не прошёл, на диск не попадает вовсе.

ТРИ ПРОВЕРКИ, И КАЖДАЯ ЗАКРЫВАЕТ ИЗВЕСТНУЮ ДЫРУ:

1. **Путь наружу** (`zip slip`): имя вида `../../etc/passwd` или абсолютное. Проверяется
   не строкой, а сравнением РАЗРЕШЁННОГО пути с корнем каталога — строковые проверки
   обходятся кодировками и симлинками.
2. **Размер после распаковки** (`zip bomb`): 40 КБ архива разворачиваются в гигабайты.
   Считается сумма ЗАЯВЛЕННЫХ размеров до записи и фактических во время неё — заявленному
   в заголовке верить нельзя.
3. **Состав**: внутрь пускаем только то, из чего состоит баннер. Исполняемое (`.exe`,
   `.sh`, `.php`) и всё незнакомое отбрасывается молча — баннеру оно не нужно, а нам
   означало бы «раздаём произвольные файлы с домена под своим именем».

Каталог называется СЛУЧАЙНЫМ токеном: раздача без авторизации (иначе баннер не откроется
в кабинете паблишера), и единственная защита — неподбираемость адреса.
"""
import io
import os
import re
import secrets
import shutil
import zipfile
from typing import Optional, Tuple

from app.files_safe import inside_uploads

# Каталог песочницы внутри общего хранилища. Отдельный от `creatives/`: там лежат
# исходные архивы под нашей авторизацией, здесь — распакованное под раздачу наружу.
SANDBOX_DIR = "sandbox"

# Из чего состоит баннер. Список закрытый: незнакомое расширение — повод не раздавать
# файл, а не повод расширить список.
ALLOWED_INNER = {
    ".html", ".htm", ".css", ".js", ".json", ".map",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp4", ".webm", ".mp3", ".ogg", ".txt", ".xml",
}

MAX_TOTAL_BYTES = 60 * 1024 * 1024      # столько занимает распакованный баннер целиком
MAX_FILES = 500                          # больше — это не баннер, а чей-то проект
MAX_SINGLE_BYTES = 25 * 1024 * 1024      # один файл внутри


class SandboxError(RuntimeError):
    """Архив не годится для раздачи. Текст показывается человеку как есть."""


def _is_inside(root: str, target: str) -> bool:
    """Ведёт ли путь ВНУТРЬ каталога. Сравниваем разрешённые пути, а не строки.

    Внутри — общая проверка `app/files_safe.inside_uploads`, чтобы правило было одним
    на весь проект: здесь оно раньше жило четвёртой копией, и разойтись копиям мешало
    только то, что их никто не трогал. Подпись оставлена прежней — тут удобнее спросить
    «внутрь ли этого каталога», а не «внутрь ли хранилища».
    """
    return inside_uploads(os.path.relpath(target, root), root=root) is not None


def _pick_entry(names) -> Optional[str]:
    """Точка входа: `index.html` в корне, иначе самый мелкий по вложенности html.

    Ищется один раз при загрузке и запоминается: гадать при каждом открытии — значит
    гадать по-разному, и человек будет видеть то один баннер, то другой.
    """
    htmls = [n for n in names if n.lower().endswith((".html", ".htm"))]
    if not htmls:
        return None
    roots = [n for n in htmls if os.path.basename(n).lower() == "index.html"]
    pool = roots or htmls
    return sorted(pool, key=lambda n: (n.count("/"), len(n)))[0]


def unpack(archive_path: str, uploads_root: str) -> Tuple[str, str]:
    """Развернуть архив в песочницу. Возвращает `(токен, путь до точки входа)`.

    Бросает `SandboxError` с человеческим текстом — он показывается прямо при загрузке,
    чтобы негодный архив не дожил до момента, когда его пойдут смотреть.
    """
    try:
        zf = zipfile.ZipFile(archive_path)
    except zipfile.BadZipFile:
        raise SandboxError("Файл не читается как ZIP-архив")

    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if not infos:
            raise SandboxError("Архив пуст")
        if len(infos) > MAX_FILES:
            raise SandboxError(
                f"В архиве {len(infos)} файлов — это больше похоже на проект, "
                f"чем на баннер (предел {MAX_FILES})")

        declared = sum(i.file_size for i in infos)
        if declared > MAX_TOTAL_BYTES:
            raise SandboxError(
                f"Распакованный архив занял бы {declared // 1024 // 1024} МБ "
                f"(предел {MAX_TOTAL_BYTES // 1024 // 1024} МБ)")

        keep = [i for i in infos
                if os.path.splitext(i.filename)[1].lower() in ALLOWED_INNER]
        if not keep:
            raise SandboxError("В архиве нет ни одного файла, из которых состоит баннер")

        entry = _pick_entry([i.filename for i in keep])
        if not entry:
            raise SandboxError(
                "В архиве нет html-файла — показать такой баннер нечем. "
                "Обычно точка входа называется index.html")

        token = secrets.token_urlsafe(24)
        root = os.path.join(uploads_root, SANDBOX_DIR, token)
        os.makedirs(root, exist_ok=True)

        written = 0
        try:
            for info in keep:
                target = os.path.join(root, info.filename)
                # Проверяем ДО создания каталогов: иначе `../` уже создаст чужую папку.
                if os.path.isabs(info.filename) or not _is_inside(root, target):
                    raise SandboxError(
                        f"Архив пытается записать файл вне своей папки: {info.filename}")
                if info.file_size > MAX_SINGLE_BYTES:
                    raise SandboxError(
                        f"Файл {info.filename} внутри архива слишком большой")

                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as dst:
                    while True:
                        chunk = src.read(64 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        # Фактический размер, а не заявленный: заголовок архива пишет
                        # тот, кто архив собрал, и верить ему нельзя.
                        if written > MAX_TOTAL_BYTES:
                            raise SandboxError(
                                "Распакованный архив оказался больше заявленного — "
                                "похоже на архив-бомбу")
                        dst.write(chunk)
        except Exception:
            shutil.rmtree(root, ignore_errors=True)
            raise

    return token, entry


AD_SIZE_RE = re.compile(
    r"""<meta[^>]*name=['"]ad\.size['"][^>]*content=['"]([^'"]+)['"]""", re.I)
WH_RE = re.compile(r"width\s*=\s*(\d+)\s*,\s*height\s*=\s*(\d+)", re.I)


def stash_html(uploads_root: str, html: str, token: Optional[str] = None) -> Tuple[str, str]:
    """Положить ГОТОВУЮ разметку в песочницу и вернуть `(токен, точка входа)`.

    Зачем отдельно от `unpack`: разметку, которую вернул загрузчик DSP, распаковывать
    неоткуда — она уже собрана, а её картинки и скрипты лежат на ЧУЖОМ CDN, куда указывает
    подставленный им `<base href>`.

    Показать такое в `srcdoc` на нашем домене нельзя, и это не баг, а наш CSP: `base-uri
    'self'` отменяет чужой `<base>`, `img-src 'self' data: blob:` не пускает их картинки,
    `script-src 'self'` — их скрипты. Рамка получается пустой. Ровно для чужого кода и
    заведён отдельный домен песочницы, где ограничений по источникам нет.

    `token` можно передать, чтобы переиспользовать каталог: демо-стенд грузит баннер за
    баннером, и каждый раз новый случайный каталог означал бы, что песочница растёт от
    тренировок и никогда не убирается — сроков хранения у неё для них нет.
    """
    token = token or secrets.token_urlsafe(24)
    root = os.path.join(uploads_root, SANDBOX_DIR, token)
    if not _is_inside(os.path.join(uploads_root, SANDBOX_DIR), root):
        raise SandboxError("Недопустимый токен песочницы")
    shutil.rmtree(root, ignore_errors=True)      # каталог держит ОДИН баннер, не историю
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(html or "")
    return token, "index.html"


def parse_ad_size(html: str) -> Optional[tuple]:
    """`(ширина, высота)` из мета-тега баннера, или None, если тега нет.

    ЕДИНСТВЕННЫЙ разбор этого тега в проекте. Второй потребитель появился 09.09.2026 —
    конвейер DSP отказывается грузить архив без размера, и заводить там свою регулярку
    значило бы позволить двум чтениям разойтись.

    Ноль здесь возвращается как ноль: `0x0` — это ЗАЯВЛЕННЫЙ адаптивный баннер, и он
    отличается от «тег вообще не написан». Для предпросмотра разница неважна, для
    загрузчика — принципиальна.
    """
    m = AD_SIZE_RE.search(html or "")
    if not m:
        return None
    wh = WH_RE.search(m.group(1))
    if not wh:
        return None
    return int(wh.group(1)), int(wh.group(2))


# Что вшиваем баннеру без объявленного размера (владелец 25.09.2026): такой баннер
# считаем АДАПТИВНЫМ. `0x0` — законное объявление адаптивного, DSP его принимает.
ADAPTIVE_META = '<meta name="ad.size" content="width=0,height=0">'
_HEAD_RE = re.compile(r"<head\b[^>]*>", re.I)
_HTML_RE = re.compile(r"<html\b[^>]*>", re.I)

# Макрос ссылки клика: вместо него DSP подставляет посадочную (владелец 25.09.2026).
DSP_CLICK_MACRO = "{LINK_UNESC}"
_HREF_RE = re.compile(r"""(<a\b[^>]*?\bhref\s*=\s*)(["'])(.*?)\2""", re.I | re.S)
# Заглушка чужой рекламной системы (`%banner.reference_mrc_user1%`, `{CLICK_URL}`,
# `[CLICKTAG]`), пустая ссылка или `#`. Настоящий адрес сюда не попадает — это может быть
# ссылка на инструкцию, и молча подменять её нельзя.
_PLACEHOLDER_RE = re.compile(r"^\s*(#?|%[^%]*%|\{[^}]*\}|\[[^\]]*\])\s*$")


def click_problem(html: str) -> Optional[str]:
    """Что не так со ссылкой клика: None — макрос DSP стоит; иначе причина словами."""
    hrefs = [m.group(3) for m in _HREF_RE.finditer(html or "")]
    if DSP_CLICK_MACRO in hrefs:
        return None
    return "ссылка без макроса" if hrefs else "нет ссылки"


def _fix_links(html: str) -> Tuple[str, bool]:
    changed = False

    def sub(m):
        nonlocal changed
        val = m.group(3)
        if val != DSP_CLICK_MACRO and _PLACEHOLDER_RE.match(val):
            changed = True
            return f"{m.group(1)}{m.group(2)}{DSP_CLICK_MACRO}{m.group(2)}"
        return m.group(0)

    return _HREF_RE.sub(sub, html), changed


def prepare_for_dsp(data: bytes) -> Tuple[bytes, list]:
    """Архив, готовый для DSP. `(байты, что поправлено)` — список из 'ad.size' / 'link'.

    ЗАЧЕМ. DSP не принимает архив без `<meta name="ad.size">` (код 2053), а клик ведёт
    через макрос `{LINK_UNESC}` в `<a href>`. Узнавали мы о нехватке при отправке — через
    неделю после загрузки, когда баннер уже согласовывали площадки. Поэтому поправляем
    ОДИН РАЗ, при загрузке: хранится уже исправленный архив, и предпросмотр, нацеливание
    и боевая выгрузка берут один и тот же файл (владелец 25.09.2026).

      · размер не объявлен — баннер считаем адаптивным, вшиваем `width=0,height=0`.
        Ищем во ВСЁМ файле, а не в начале: второй тег поверх настоящего (стоящего дальше
        восьми килобайт) подменил бы объявленный размер адаптивным;
      · ссылка клика — заглушку чужой системы, пустую и `#` меняем на макрос DSP.

    Правится та точка входа, которую показывает песочница (`_pick_entry`). Если править
    нечего — архив не пересобирается вовсе, байт в байт.
    """
    try:
        src = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return data, []
    with src:
        infos = [i for i in src.infolist() if not i.is_dir()]
        entry = _pick_entry([i.filename for i in infos])
        if not entry:
            return data, []
        html = src.read(entry).decode("utf-8", "ignore")
        changes = []
        if parse_ad_size(html) is None:
            m = _HEAD_RE.search(html) or _HTML_RE.search(html)
            html = (html[:m.end()] + ADAPTIVE_META + html[m.end():]) if m \
                else ADAPTIVE_META + html
            changes.append("ad.size")
        html, linked = _fix_links(html)
        if linked:
            changes.append("link")
        if not changes:
            return data, []
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as out:
            for info in src.infolist():
                body = html.encode("utf-8") if info.filename == entry \
                    else src.read(info.filename)
                out.writestr(info, body, compress_type=info.compress_type)
    return buf.getvalue(), changes


def read_size(uploads_root: str, token: str, entry: str) -> Optional[str]:
    """Размер баннера из него самого: `<meta name="ad.size" content="width=..,height=..">`.

    Это стандарт рекламных площадок, и он единственный надёжный источник: имя файла
    врёт («adfox», «dcp»), а спрашивать размер у аккаунта значит спрашивать то, что уже
    написано внутри. Нули — законный ответ: так помечают адаптивный баннер, и выдумывать
    ему размер нельзя, он тянется по контейнеру.
    """
    # `token` и `entry` приходят из базы, и читать по ним файл без проверки границы
    # значит доверять записи больше, чем можно: испорченная строка увела бы чтение за
    # пределы песочницы. Размер наружу отдаётся маленький, но путь — тот же класс.
    # Ключ считается ОТ КОРНЯ хранилища, а `subdir` лишь сужает границу. С 12.09.2026
    # (v2.6.6) здесь стоял путь без `sandbox/`, граница его отвергала, и размер не
    # читался НИ У ОДНОГО баннера: всё показывалось «адаптивным» (найдено 25.09.2026).
    path = inside_uploads(os.path.join(SANDBOX_DIR, token, entry),
                          root=uploads_root, subdir=SANDBOX_DIR)
    if path is None:
        return None
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
            head = fh.read(8192)          # мета живёт в начале документа
    except OSError:
        return None
    wh = parse_ad_size(head)
    if not wh:
        return None
    w, h = wh
    return f"{w}x{h}" if w > 0 and h > 0 else None


def remove(uploads_root: str, token: Optional[str]) -> None:
    """Убрать распакованное. Зовётся вместе с удалением файла комплекта."""
    if not token:
        return
    root = os.path.join(uploads_root, SANDBOX_DIR, token)
    if _is_inside(os.path.join(uploads_root, SANDBOX_DIR), root):
        shutil.rmtree(root, ignore_errors=True)


def public_url(token: Optional[str], entry: Optional[str]) -> Optional[str]:
    """Адрес баннера в песочнице.

    База — из окружения (`SANDBOX_BASE_URL`), а не из кода: домен песочницы отличается
    на стенде и на проде, и зашитый адрес означал бы, что на проде показывается стенд.
    Пусто — песочница не настроена, и экран должен сказать это, а не показать битую рамку.
    """
    base = (os.getenv("SANDBOX_BASE_URL") or "").strip().rstrip("/")
    if not (base and token and entry):
        return None
    return f"{base}/{token}/{entry}"
