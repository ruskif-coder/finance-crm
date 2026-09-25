"""Исходник баннера рядом с подготовленным под DSP (владелец 25.09.2026).

Баннер под НАШУ DSP хранится подготовленным (`sandbox.prepare_for_dsp`): в нём наши
вставки — адаптивный `ad.size`, макрос ссылки `{LINK_UNESC}`, раскладка в корень. Так
решено, чтобы предпросмотр, нацеливание и боевая выгрузка брали один файл.

Но площадка, скачивающая баннер в кабинете, крутит его СВОЕЙ системой и ждёт архив, какой
прислал клиент. Поэтому, когда подготовка что-то меняет, исходник кладётся рядом:
`creatives/orig/<то же имя>`. Путь выводится из пути файла, а не хранится колонкой —
у файла ровно один исходник, и связь не может разойтись.

Нет исходника — значит, подготовка ничего не меняла (или файл под чужую DSP), и
хранимый файл и есть исходный.
"""
import os
import shutil

from app.files_safe import UPLOADS_ROOT, inside_uploads, remove_upload

ORIG_DIR = "orig"


def original_rel(rel_path: str) -> str:
    """`creatives/cre12_x.zip` → `creatives/orig/cre12_x.zip`."""
    head, name = os.path.split(rel_path)
    return os.path.join(head, ORIG_DIR, name).replace(os.sep, "/")


def original_abs(rel_path: str, root: str = UPLOADS_ROOT) -> str:
    return inside_uploads(original_rel(rel_path), root=root) or ""


def save(rel_path: str, data: bytes, root: str = UPLOADS_ROOT) -> None:
    full = original_abs(rel_path, root)
    if not full:
        return
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as fh:
        fh.write(data)


def copy(src_rel: str, dst_rel: str, root: str = UPLOADS_ROOT) -> None:
    """Продление РК копирует файл — и его исходник, если он есть."""
    src, dst = original_abs(src_rel, root), original_abs(dst_rel, root)
    if src and dst and os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)


def remove(rel_path: str, root: str = UPLOADS_ROOT) -> None:
    remove_upload(original_rel(rel_path), root=root)


def path_for_publisher(rel_path: str, root: str = UPLOADS_ROOT) -> str:
    """Что отдать площадке: исходник, если он есть, иначе сам файл."""
    orig = original_abs(rel_path, root)
    if orig and os.path.exists(orig):
        return orig
    return inside_uploads(rel_path, root=root) or ""
