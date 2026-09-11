# -*- coding: utf-8 -*-
"""Путь из базы не склеивается с корнем хранилища вручную — ни на чтение, ни на удаление.

ЗАЧЕМ. Относительный ключ файла лежит в базе, и код доверяет ему как своему. Доверие
законное, но держится на том, что запись никто не испортил — ни ошибкой миграции, ни
правкой в psql, ни импортом, который однажды подставит не то. Стоит этому случиться, и
`os.path.join(корень, путь)` с `..` внутри читает — или СТИРАЕТ — за пределами хранилища.

ЧЕМ ЭТО БЫЛО. На 11.09.2026 проверка стояла в одном месте из десяти; свели к
`app/files_safe.py`. Но первая редакция этого гейта смотрела только на `FileResponse(` и
только в `app/routers/`, а значит охраняла ровно те одиннадцать точек, которые уже
поправили. Мимо неё прошёл весь остальной класс:

  · пятнадцать `os.remove` по пути из базы. Закономерность видна глазами: в каждой паре
    «скачать / удалить» GET был переведён, а стоящий на пятнадцать строк ниже DELETE —
    нет. При этом докстрока `files_safe` обещала «на все места, где файл отдают **или
    удаляют**»;
  · отдача файла не через `FileResponse`: zip комплекта креативов и архив скриншотов
    собирались `Response(content=…)`, а отправка в ОРД и в DSP — через `open()` и base64.
    Последние две дороже всех: содержимое уходит наружу НЕОБРАТИМО;
  · всё, что лежит вне `app/routers/` — `sales/bitrix/deal_sync.py`, `dsp/provision.py`,
    `launch_prep/sandbox.py`.

И две ЛОКАЛЬНЫЕ КОПИИ проверки — то самое расхождение, ради которого заводился общий
модуль. Одна из них (в `deal_sync`) сравнивала строку пути, а не разрешённый путь, и
пропускала `deal_files/../../../etc/passwd`: строка начинается правильно, а `os.remove`
уходил в `/etc`. Замерено 11.09.2026.

ПОЧЕМУ ПРАВИЛО ТАКОЕ ЖЁСТКОЕ. «Ни одного голого `os.remove` в `app/`» проверяется одной
строкой и не имеет серой зоны. Правило с исключениями («кроме случаев, когда имя мы
только что сгенерировали») пришлось бы толковать при каждой новой правке, а толкование
и есть то место, где защита протекает.
"""
import ast
import pathlib

import pytest
from fastapi import HTTPException

from app.files_safe import (existing_upload_path, inside_uploads, remove_upload,
                            safe_upload_path)

APP = pathlib.Path(__file__).resolve().parent.parent / "app"
SAFE_MODULE = "files_safe.py"


def _sources():
    for path in sorted(APP.rglob("*.py")):
        if path.name == SAFE_MODULE:
            continue
        yield path, ast.parse(path.read_text(encoding="utf-8")), path.relative_to(APP)


# ── поведение самой функции ──────────────────────────────────────────────────

def test_normal_path_resolves_inside_storage():
    assert safe_upload_path("creatives/cre1_banner.zip") == "/app/uploads/creatives/cre1_banner.zip"


@pytest.mark.parametrize("evil", [
    "../../etc/passwd",
    "creatives/../../../etc/shadow",
    "/etc/passwd",
    "deal_files/../../../etc/passwd",   # проходило локальную проверку в deal_sync
])
def test_traversal_is_refused(evil):
    with pytest.raises(HTTPException) as e:
        safe_upload_path(evil)
    assert e.value.status_code == 400
    assert inside_uploads(evil) is None


def test_subdir_narrows_the_boundary():
    """Файл договора не должен отдаваться ручкой, которая работает с другой папкой."""
    with pytest.raises(HTTPException):
        safe_upload_path("creatives/x.zip", subdir="publishers")


def test_sibling_directory_with_common_prefix_is_refused():
    """`/app/uploads-evil` НЕ внутри `/app/uploads`, хотя и начинается так же.

    Классическая ошибка ручной проверки: сравнение без разделителя на конце.
    """
    with pytest.raises(HTTPException):
        safe_upload_path("../uploads-evil/secret.pdf")


def test_empty_path_says_what_is_wrong():
    """«У записи не указан файл» и «файл не найден» — разные сообщения намеренно:
    первое про запись в базе, второе про диск, и чинятся они по-разному."""
    with pytest.raises(HTTPException) as e:
        safe_upload_path("")
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e2:
        existing_upload_path("creatives/нет-такого-файла-" + "x" * 12 + ".zip")
    assert e2.value.status_code == 404


def test_null_byte_is_a_bad_record_not_a_server_error():
    """`\\0` в пути роняет `realpath` через ValueError. Это испорченная запись — 400,
    а не 500."""
    assert inside_uploads("creatives/x\0.zip") is None
    with pytest.raises(HTTPException) as e:
        safe_upload_path("creatives/x\0.zip")
    assert e.value.status_code == 400


# ── тихий режим: для архивов и уборки ────────────────────────────────────────

def test_quiet_mode_returns_none_instead_of_refusing():
    """Отказ клиенту не к месту в двух случаях: сборка архива (одна испорченная строка
    из тридцати не должна лишать остальных) и удаление (строки в базе уже нет, отказывать
    некому)."""
    assert inside_uploads("../../etc/passwd") is None
    assert inside_uploads("creatives/ok.zip") == "/app/uploads/creatives/ok.zip"


def test_remove_never_reaches_outside_and_never_raises():
    assert remove_upload("../../etc/passwd") is False
    assert remove_upload("deal_files/../../../etc/passwd", subdir="deal_files") is False
    assert remove_upload("") is False
    assert remove_upload(None) is False
    # Несуществующий файл ВНУТРИ хранилища — тоже False, но без исключения: строку из
    # базы к этому моменту уже удалили, и ошибка на уборке превратила бы успешное
    # удаление записи в 500 на глазах у того, кто всё сделал правильно.
    assert remove_upload("creatives/нет-такого-" + "x" * 12 + ".zip") is False


# ── гейт 1: ни одного голого удаления ────────────────────────────────────────

DELETERS = {"remove", "unlink", "rmtree"}


def _raw_deletions():
    """Вызовы `os.remove` / `os.unlink` / `shutil.rmtree` вне `files_safe`."""
    for path, tree, rel in _sources():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if isinstance(fn, ast.Attribute) and fn.attr in DELETERS:
                mod = getattr(fn.value, "id", None)
                if mod in ("os", "shutil"):
                    yield str(rel), node.lineno, f"{mod}.{fn.attr}"


# Осознанные исключения — по ФАЙЛУ И ВЫЗОВУ, не по номеру строки. Номера смещаются от
# любой соседней правки, и гейт, кричащий на каждую правку, выключают. Каждая пара здесь
# это место, где файл стирается мимо общей проверки, и она должна быть объяснена.
EXEMPT_DELETIONS = {
    # Песочница удаляет КАТАЛОГ целиком, а не файл по ключу, и свою границу проверяет
    # сама — через `_is_inside`, который с 11.09.2026 внутри зовёт `inside_uploads`.
    # Завести для этого `remove_upload` нельзя: он про файлы.
    ("launch_prep/sandbox.py", "shutil.rmtree"),
}


def test_no_raw_file_deletion_outside_the_shared_check():
    bad = [f"{rel}:{line}  {what}" for rel, line, what in _raw_deletions()
           if (rel.replace("\\", "/"), what) not in EXEMPT_DELETIONS]
    assert not bad, (
        "Эти места стирают файл, не пропустив путь через app/files_safe.remove_upload:\n  "
        + "\n  ".join(bad)
        + "\n\nПуть из базы нельзя склеивать с корнем напрямую: испорченная запись "
          "уведёт удаление за пределы хранилища. Если место законное — объясните его "
          "в EXEMPT_DELETIONS."
    )


def test_nobody_imports_the_deleters_by_name():
    """`from os import remove` обошёл бы гейт выше: вызов стал бы `remove(...)`, а не
    `os.remove(...)`. Сегодня таких импортов нет ни одного — закрепляем это, пока их нет,
    а не после того, как кто-то так напишет."""
    bad = []
    for _path, tree, rel in _sources():
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in ("os", "shutil"):
                for alias in node.names:
                    if alias.name in DELETERS:
                        bad.append(f"{rel}:{node.lineno}  from {node.module} import {alias.name}")
    assert not bad, (
        "Удаление импортировано по имени — так вызов не видно гейту:\n  "
        + "\n  ".join(bad) + "\n\nЗовите app/files_safe.remove_upload.")


def test_the_deletion_gate_sees_the_exempt_sites():
    """Страховка от зелёного теста, который ничего не нашёл: если обход сломается,
    исключения перестанут находиться, и это заметно."""
    found = {(rel.replace("\\", "/"), what) for rel, _l, what in _raw_deletions()}
    missing = sorted(EXEMPT_DELETIONS - found)
    assert not missing, (
        f"Гейт больше не видит эти места: {missing}. Либо их убрали (тогда уберите и из "
        "EXEMPT_DELETIONS), либо сломался обход — и тогда гейт зелёный впустую.")


# ── гейт 2: ни одной ручной склейки с корнем хранилища ───────────────────────

# Как в коде называется корень хранилища. Строковый литерал ловим тоже: `"/app/uploads"`
# писали руками в sales_dashboard.
ROOT_NAMES = {"UPLOADS_ROOT", "UPLOADS_DIR", "uploads_root"}
ROOT_LITERAL = "/app/uploads"


def _root_joins():
    """`os.path.join(<корень>, …, <поле записи>, …)` — ручная склейка пути ИЗ БАЗЫ.

    Разделяющий признак — не номер строки, а ФОРМА второго аргумента. Путь из базы всегда
    приходит обращением к полю (`f.path`, `rec.path`, `row.rights_letter_path`), а имя,
    сгенерированное в этом же запросе, — простой переменной (`stored`, `rel`) или
    константой каталога (`CREATIVES_DIR`). Поэтому правило звучит так: склеивать корень
    с ПОЛЕМ ЗАПИСИ нельзя, склеивать со своим именем — можно.

    Так гейт не привязан к строкам и не кричит на каждую соседнюю правку — а именно
    из-за этого гейты и выключают.
    """
    for path, tree, rel in _sources():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (isinstance(fn, ast.Attribute) and fn.attr == "join") or not node.args:
                continue
            first = node.args[0]
            root_hit = ((isinstance(first, ast.Name) and first.id in ROOT_NAMES)
                        or (isinstance(first, ast.Constant) and first.value == ROOT_LITERAL))
            if not root_hit:
                continue
            # Поле записи среди остальных аргументов — прямым обращением, без разбора
            # вложенных вызовов: `str(deal.id)` это построение КАТАЛОГА для записи, а не
            # путь из базы.
            if any(isinstance(a, ast.Attribute) for a in node.args[1:]):
                yield f"{rel}:{node.lineno}"


def test_no_hand_built_paths_from_the_storage_root():
    bad = sorted(set(_root_joins()))
    assert not bad, (
        "Корень хранилища склеен с полем записи напрямую:\n  " + "\n  ".join(bad)
        + "\n\nПуть из базы обязан пройти через app/files_safe: inside_uploads (тихо), "
          "safe_upload_path / existing_upload_path (с отказом) или remove_upload."
    )


def test_the_join_gate_can_still_see():
    """Страховка: обход обязан находить склейки вообще, иначе он зелёный впустую.

    Проверяем на заведомо негодном образце, а не на живом коде: живой код сейчас чист,
    и пустой результат там ничего не доказывает.
    """
    sample = ast.parse("import os\nos.path.join(UPLOADS_ROOT, rec.path)\n")
    hits = []
    for node in ast.walk(sample):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "join" and node.args
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id in ROOT_NAMES
                and any(isinstance(a, ast.Attribute) for a in node.args[1:])):
            hits.append(node.lineno)
    assert hits == [2], "правило перестало распознавать даже образец — обход сломан"


# ── гейт 3: отдача файла наружу ──────────────────────────────────────────────

# Вызовы, которыми файл уходит наружу или читается целиком. `FileResponse` — только один
# из них, и первая редакция гейта видела только его.
LOOKBACK = 16
SAFE_CALLS = ("existing_upload_path", "safe_upload_path", "inside_uploads")
SERVE_MARKERS = ("FileResponse(",)


def _file_response_sites():
    for path, _tree, rel in _sources():
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if line.lstrip().startswith("#"):
                continue
            if any(m in line for m in SERVE_MARKERS):
                yield f"{rel}:{i + 1}", "\n".join(lines[max(0, i - LOOKBACK):i + 1])


def test_every_file_response_uses_the_shared_check():
    bad = [where for where, chunk in _file_response_sites()
           if not any(c in chunk for c in SAFE_CALLS)]
    assert not bad, (
        "Эти места отдают файл наружу, не пропустив путь через app/files_safe:\n  "
        + "\n  ".join(bad))


def test_the_gate_actually_sees_the_sites():
    """Страховка от зелёного теста, который ничего не нашёл."""
    assert len(list(_file_response_sites())) >= 8
