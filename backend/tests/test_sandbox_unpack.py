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


# ── размер баннера: вшиваем, если не объявлен (владелец 25.09.2026) ──────────
#
# DSP не принимает архив без `<meta name="ad.size">` (код 2053), а узнаём мы об этом
# только при отправке — через неделю после загрузки. Баннер без тега считаем
# адаптивным и вшиваем `width=0,height=0` при загрузке: хранится уже исправленный,
# и предпросмотр, нацеливание и боевая выгрузка берут один и тот же готовый архив.

def _zbytes(entries):
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


def _read(data, name):
    import io
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return z.read(name)


def test_missing_ad_size_is_injected_as_adaptive():
    from app.dsp.creatives import ad_size_in_zip
    src = _zbytes({'index.html': '<!DOCTYPE html><html><head><title>b</title></head>'
                                 '<body>баннер</body></html>',
                   'bg.jpg': b'\xff\xd8JPEG'})
    assert ad_size_in_zip(src) is None
    out, changes = sandbox.prepare_for_dsp(src)
    assert 'ad.size' in changes
    assert ad_size_in_zip(out) == (0, 0), "DSP обязан найти тег в исправленном архиве"
    html = _read(out, 'index.html').decode('utf-8')
    assert html.index('ad.size') < html.index('<title>'), "тег в <head>, до всего прочего"
    assert 'баннер' in html
    assert _read(out, 'bg.jpg') == b'\xff\xd8JPEG', "остальные файлы не трогаем"


def test_declared_ad_size_is_left_byte_for_byte():
    src = _zbytes({'index.html': '<html><head><meta name="ad.size" '
                                 'content="width=240,height=400"></head>'
                                 '<body><a href="{LINK_UNESC}">x</a></body></html>'})
    out, changes = sandbox.prepare_for_dsp(src)
    assert changes == []
    assert out == src, "объявленный размер — архив не пересобираем вовсе"


def test_tag_goes_into_the_entry_the_sandbox_shows():
    """Вшиваем туда же, откуда баннер показывает песочница: в корневой index.html."""
    src = _zbytes({'extra/page.html': '<html><head></head></html>',
                   'index.html': '<html><head></head><body>x</body></html>'})
    out, changes = sandbox.prepare_for_dsp(src)
    assert 'ad.size' in changes
    assert b'ad.size' in _read(out, 'index.html')
    assert b'ad.size' not in _read(out, 'extra/page.html')


def test_html_without_head_still_gets_the_tag():
    src = _zbytes({'index.html': '<div class="banner"></div>'})
    out, changes = sandbox.prepare_for_dsp(src)
    assert 'ad.size' in changes
    from app.dsp.creatives import ad_size_in_zip
    assert ad_size_in_zip(out) == (0, 0)


def test_archive_without_html_is_returned_as_is():
    """Без html чинить нечего: отказ скажет распаковка, а не вшивание."""
    src = _zbytes({'pic.png': b'\x89PNG'})
    assert sandbox.prepare_for_dsp(src) == (src, [])


# ── ссылка клика: макрос DSP (владелец 25.09.2026) ───────────────────────────
#
# DSP подставляет посадочную вместо `{LINK_UNESC}` в `<a href>`. Баннер, собранный под
# другую рекламную систему, несёт её макрос (`%banner.reference_mrc_user1%`), и клик в
# нашей DSP не ведёт никуда — молча. Заглушки чужих систем, пустую ссылку и `#` меняем
# на наш макрос; настоящий адрес не трогаем — это может быть ссылка на инструкцию.

LINK = sandbox.DSP_CLICK_MACRO


def test_foreign_click_macro_is_replaced():
    src = _zbytes({'index.html': '<html><head></head><body>'
                   '<a href="%banner.reference_mrc_user1%" target="%banner.target%">b</a>'
                   '</body></html>'})
    out, changes = sandbox.prepare_for_dsp(src)
    html = _read(out, 'index.html').decode('utf-8')
    assert 'link' in changes
    assert f'href="{LINK}"' in html
    assert '%banner.reference_mrc_user1%' not in html


def test_empty_and_hash_links_become_the_macro():
    src = _zbytes({'index.html': "<html><head></head><body><a href=''>1</a>"
                   '<a href="#">2</a></body></html>'})
    out, changes = sandbox.prepare_for_dsp(src)
    html = _read(out, 'index.html').decode('utf-8')
    assert html.count(LINK) == 2


def test_real_url_and_our_macro_are_left_alone():
    src = _zbytes({'index.html': '<html><head><meta name="ad.size" content="width=0,height=0">'
                   '</head><body><a href="{LINK_UNESC}">b</a>'
                   '<a href="https://brand.ru/instr.pdf">инструкция</a></body></html>'})
    out, changes = sandbox.prepare_for_dsp(src)
    assert changes == [] and out == src


def test_click_state_is_reported():
    """Чего вшиванием не исправить — называется, а не молчит."""
    ok = '<html><head></head><body><a href="{LINK_UNESC}">b</a></body></html>'
    none = '<html><head></head><body><div>без ссылки</div></body></html>'
    real = '<html><head></head><body><a href="https://brand.ru">b</a></body></html>'
    assert sandbox.click_problem(ok) is None
    assert sandbox.click_problem(none) == 'нет ссылки'
    assert sandbox.click_problem(real) == 'ссылка без макроса'


# ── HTML в корне архива: загрузчик DSP ищет его только там (прод, 25.09.2026) ──
#
# Архив, упакованный на Mac, лежит во вложенной папке (с кириллическим именем, без
# пометки кодировки) плюс `__MACOSX/` и `.DS_Store`. Песочница точку входа находит, а
# загрузчик DSP отвечает «Html file not found» (код 2021). Готовя архив, поднимаем
# содержимое папки точки входа в корень и отбрасываем служебный мусор Mac.

def test_nested_banner_is_lifted_to_the_root():
    folder = 'html_brand_АПТЕКА_dcp/'
    src = _zbytes({folder + 'index.html': '<html><head><meta name="ad.size" content="width=0,height=0">'
                                          '</head><body><a href="{LINK_UNESC}">b</a><img src="bg.jpg"></body></html>',
                   folder + 'bg.jpg': b'\xff\xd8JPEG',
                   '__MACOSX/' + folder + '._index.html': b'junk',
                   folder + '.DS_Store': b'junk'})
    out, changes = sandbox.prepare_for_dsp(src)
    assert 'root' in changes
    import io
    with zipfile.ZipFile(io.BytesIO(out)) as z:
        names = sorted(z.namelist())
    assert names == ['bg.jpg', 'index.html'], names


def test_banner_already_at_the_root_is_not_rebuilt_for_this():
    src = _zbytes({'index.html': '<html><head><meta name="ad.size" content="width=0,height=0">'
                                 '</head><body><a href="{LINK_UNESC}">b</a></body></html>',
                   'img/pic.png': b'\x89PNG'})
    out, changes = sandbox.prepare_for_dsp(src)
    assert changes == [] and out == src


def test_mac_junk_is_dropped_even_when_banner_is_at_the_root():
    src = _zbytes({'index.html': '<html><head><meta name="ad.size" content="width=0,height=0"></head><body><a href="{LINK_UNESC}">b</a></body></html>',
                   'bg.jpg': b'\xff\xd8JPEG',
                   '__MACOSX/._index.html': b'junk',
                   '.DS_Store': b'junk'})
    out, changes = sandbox.prepare_for_dsp(src)
    assert changes == ['mac']
    import zipfile as _z
    import io as _io
    assert sorted(_z.ZipFile(_io.BytesIO(out)).namelist()) == ['bg.jpg', 'index.html']
