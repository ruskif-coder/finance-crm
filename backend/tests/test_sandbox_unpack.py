"""Распаковка баннера в песочницу: проверяется то, что защищает от чужого архива.

Архив приходит от клиента через аккаунта и разворачивается на диск, откуда раздаётся
статикой. Значит каждая дыра здесь — это чужой файл на нашем домене, и глазами такое
не ловится: негодный архив выглядит как обычный до того дня, когда его развернут.

  · **путь наружу** (`zip slip`) — имя вида `../../evil.html`. Проверка сравнивает
    РАЗРЕШЁННЫЕ пути, а не строки: строковые обходятся;
  · **бомба** — маленький архив, разворачивающийся в гигабайты. Считается и заявленный
    размер, и фактический: заголовок пишет тот, кто архив собрал;
  · **состав** — внутрь пускаем только то, из чего состоит баннер;
  · **точка входа** — ищется один раз при загрузке. Гадать при каждом открытии значит
    гадать по-разному, и человек будет видеть то один баннер, то другой.

Сеть и база не трогаются: только файлы во временном каталоге.
"""
import os
import zipfile

import pytest

from app.launch_prep import sandbox


def _zip(entries, path):
    """Собрать архив из `{имя: содержимое}`."""
    with zipfile.ZipFile(path, 'w') as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return path


@pytest.fixture
def root(tmp_path):
    return str(tmp_path / 'uploads')


def test_ordinary_banner_is_unpacked_and_entry_found(tmp_path, root):
    arc = _zip({'index.html': '<html>баннер</html>',
                'img/pic.png': b'\x89PNG', 'main.js': 'console.log(1)'},
               str(tmp_path / 'b.zip'))
    token, entry = sandbox.unpack(arc, root)

    assert entry == 'index.html'
    assert len(token) >= 24, "токен короткий — адрес раздачи станет подбираемым"
    unpacked = os.path.join(root, sandbox.SANDBOX_DIR, token)
    assert os.path.isfile(os.path.join(unpacked, 'index.html'))
    assert os.path.isfile(os.path.join(unpacked, 'img', 'pic.png'))


def test_entry_is_found_one_level_deep(tmp_path, root):
    """Часть баннеров приходит папкой внутри архива — это норма, а не брак."""
    arc = _zip({'banner_300x600/index.html': '<html/>',
                'banner_300x600/style.css': 'body{}'}, str(tmp_path / 'b.zip'))
    _, entry = sandbox.unpack(arc, root)
    assert entry == 'banner_300x600/index.html'


def test_index_wins_over_other_html(tmp_path, root):
    arc = _zip({'about.html': '<html/>', 'index.html': '<html/>'},
               str(tmp_path / 'b.zip'))
    _, entry = sandbox.unpack(arc, root)
    assert entry == 'index.html'


# ── дыры ─────────────────────────────────────────────────────────────────────
def test_path_escaping_the_folder_is_refused(tmp_path, root):
    """`zip slip`: архив пытается записать файл ВНЕ своей папки."""
    arc = _zip({'index.html': '<html/>', '../../evil.html': 'вредное'},
               str(tmp_path / 'b.zip'))
    with pytest.raises(sandbox.SandboxError) as e:
        sandbox.unpack(arc, root)
    assert 'вне своей папки' in str(e.value)

    outside = tmp_path / 'evil.html'
    assert not outside.exists(), "файл всё-таки записался наружу"


def test_declared_size_over_the_limit_is_refused(tmp_path, root):
    big = 'a' * (sandbox.MAX_TOTAL_BYTES // 2 + 1024)
    arc = _zip({'index.html': '<html/>', 'a.js': big, 'b.js': big},
               str(tmp_path / 'b.zip'))
    with pytest.raises(sandbox.SandboxError) as e:
        sandbox.unpack(arc, root)
    assert 'занял бы' in str(e.value)


def test_too_many_files_is_refused(tmp_path, root):
    entries = {f'f{i}.js': 'x' for i in range(sandbox.MAX_FILES + 5)}
    entries['index.html'] = '<html/>'
    arc = _zip(entries, str(tmp_path / 'b.zip'))
    with pytest.raises(sandbox.SandboxError) as e:
        sandbox.unpack(arc, root)
    assert 'файлов' in str(e.value)


def test_executables_do_not_reach_the_disk(tmp_path, root):
    """Незнакомое расширение не раздаётся: баннеру оно не нужно."""
    arc = _zip({'index.html': '<html/>', 'run.sh': 'rm -rf /',
                'tool.exe': b'MZ', 'shell.php': '<?php ?>'},
               str(tmp_path / 'b.zip'))
    token, _ = sandbox.unpack(arc, root)

    unpacked = os.path.join(root, sandbox.SANDBOX_DIR, token)
    left = {f for _, _, fs in os.walk(unpacked) for f in fs}
    assert left == {'index.html'}, f"на диск попало лишнее: {left}"


def test_archive_without_html_is_refused_with_a_reason(tmp_path, root):
    """Отказ на загрузке, а не при открытии: иначе брак всплывёт через неделю."""
    arc = _zip({'pic.png': b'\x89PNG'}, str(tmp_path / 'b.zip'))
    with pytest.raises(sandbox.SandboxError) as e:
        sandbox.unpack(arc, root)
    assert 'index.html' in str(e.value), "отказ обязан подсказать, чего не хватает"


def test_broken_zip_is_refused(tmp_path, root):
    path = tmp_path / 'b.zip'
    path.write_bytes(b'not a zip at all')
    with pytest.raises(sandbox.SandboxError) as e:
        sandbox.unpack(str(path), root)
    assert 'ZIP' in str(e.value)


def test_failed_unpack_leaves_no_folder(tmp_path, root):
    """Отказ на середине не оставляет полуразвёрнутый баннер, который раздался бы."""
    arc = _zip({'index.html': '<html/>', '../out.html': 'x'}, str(tmp_path / 'b.zip'))
    with pytest.raises(sandbox.SandboxError):
        sandbox.unpack(arc, root)

    base = os.path.join(root, sandbox.SANDBOX_DIR)
    left = os.listdir(base) if os.path.isdir(base) else []
    assert left == [], f"остался каталог после неудачи: {left}"


# ── уборка и адрес ───────────────────────────────────────────────────────────
def test_remove_deletes_the_served_folder(tmp_path, root):
    """Оставленный каталог продолжал бы раздаваться после удаления материала."""
    arc = _zip({'index.html': '<html/>'}, str(tmp_path / 'b.zip'))
    token, _ = sandbox.unpack(arc, root)
    sandbox.remove(root, token)
    assert not os.path.exists(os.path.join(root, sandbox.SANDBOX_DIR, token))


def test_url_is_empty_when_sandbox_is_not_configured(monkeypatch):
    """Пусто — экран говорит «песочница не настроена», а не рисует битую рамку."""
    monkeypatch.delenv('SANDBOX_BASE_URL', raising=False)
    assert sandbox.public_url('tok', 'index.html') is None


def test_url_is_built_from_the_environment(monkeypatch):
    monkeypatch.setenv('SANDBOX_BASE_URL', 'https://cr.example.com/')
    assert sandbox.public_url('tok', 'a/index.html') == 'https://cr.example.com/tok/a/index.html'
    assert sandbox.public_url(None, 'index.html') is None
