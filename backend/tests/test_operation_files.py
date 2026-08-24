"""
Сканы документов, приложенные к операции.

Здесь принимается чужой файл и кладётся на диск — то есть это единственное место
модуля операций, где ошибка стоит не неверной цифры, а доступа к файловой системе.
Поэтому тесты не про «загрузилось», а про то, что отклоняется:

- расширение вне белого списка: на диск не должен попадать исполняемый файл;
- размер: без потолка один запрос забивает том, на котором лежат все документы;
- ключ с выходом за корень хранилища: путь берётся из базы, а база — не доверенный
  источник, если в неё однажды попадёт мусор.

Отдельно закреплено, что скачивание отдаёт ИСХОДНОЕ имя файла: на диске оно несёт
префикс операции и случайный суффикс (иначе два скана с именем «Акт.pdf» затирали
бы друг друга — та же готча, что у документов площадок), а человеку нужно его имя.
"""
import asyncio
import os

import pytest
from fastapi import HTTPException

from app.routers import operations as O


class _Upload:
    """Минимальная замена UploadFile: роутеру нужны только filename и read()."""

    def __init__(self, filename, data):
        self.filename = filename
        self._data = data

    async def read(self):
        return self._data


class _User:
    id = 1
    name = 'Тест'
    email = 'test@example.com'


class _Db:
    """Заглушка сессии: до записи в базу ни один из проверяемых отказов не доходит."""

    def __init__(self, operation=None, file_row=None):
        self._operation = operation
        self._file_row = file_row
        self.added = []
        self.committed = 0

    def query(self, model):
        db = self

        class _Q:
            def __init__(self):
                self._model = model

            def filter(self, *a, **k):
                return self

            def order_by(self, *a, **k):
                return self

            def first(self):
                return db._operation if model.__name__ == 'Operation' else db._file_row

            def all(self):
                return []

        return _Q()

    def add(self, obj):
        self.added.append(obj)

    @property
    def files(self):
        """Только приложенные файлы: в add() попадает ещё и запись журнала действий."""
        return [o for o in self.added if type(o).__name__ == 'OperationFile']

    def commit(self):
        self.committed += 1

    def refresh(self, obj):
        pass

    def delete(self, obj):
        pass


def _upload(name, data, db=None):
    return asyncio.run(O.upload_operation_file(
        1, _Upload(name, data), db=db or _Db(operation=object()), current_user=_User()))


def test_extension_outside_whitelist_is_rejected():
    with pytest.raises(HTTPException) as e:
        _upload('payload.exe', b'MZ')
    assert e.value.status_code == 415


def test_oversized_file_is_rejected():
    """Потолок обязателен: том с файлами общий на все подсистемы."""
    with pytest.raises(HTTPException) as e:
        _upload('big.pdf', b'x' * (O.OP_FILE_MAX_BYTES + 1))
    assert e.value.status_code == 413


def test_empty_file_is_rejected():
    with pytest.raises(HTTPException) as e:
        _upload('empty.pdf', b'')
    assert e.value.status_code == 400


def test_upload_to_missing_operation_is_rejected():
    with pytest.raises(HTTPException) as e:
        _upload('ok.pdf', b'data', db=_Db(operation=None))
    assert e.value.status_code == 404


def test_whitelist_covers_scan_formats_and_excludes_executables():
    """Сканы приходят и картинками, и в контейнерах — а исполняемого быть не должно."""
    assert {'.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff'} <= O.OP_FILE_EXTENSIONS
    for bad in ('.exe', '.sh', '.bat', '.js', '.html', '.svg'):
        assert bad not in O.OP_FILE_EXTENSIONS, bad


class _Row:
    def __init__(self, path):
        self.id = 5
        self.operation_id = 1
        self.path = path
        self.original_name = 'Акт №77.pdf'


def test_path_escaping_storage_root_is_refused():
    """Ключ приходит из базы, а база не доверенный источник.

    Без проверки склейка корня с '../../etc/passwd' отдаёт наружу любой файл
    контейнера — и отдаёт его через обычный, разрешённый правом эндпоинт.
    """
    with pytest.raises(HTTPException) as e:
        O.download_operation_file(1, 5, db=_Db(file_row=_Row('../../etc/passwd')),
                                  current_user=_User())
    assert e.value.status_code == 400


def test_path_outside_operations_subdir_is_refused():
    """Даже внутри хранилища эндпоинт операций не отдаёт чужие подкаталоги."""
    with pytest.raises(HTTPException) as e:
        O.download_operation_file(1, 5, db=_Db(file_row=_Row('contracts/secret.pdf')),
                                  current_user=_User())
    assert e.value.status_code == 400


def test_missing_file_on_disk_is_not_a_crash():
    """Запись есть, файла нет — это 404, а не пятисотка."""
    with pytest.raises(HTTPException) as e:
        O.download_operation_file(1, 5, db=_Db(file_row=_Row('operations/нет-такого.pdf')),
                                  current_user=_User())
    assert e.value.status_code == 404


def test_stored_key_is_relative_and_carries_entity_kind(tmp_path, monkeypatch):
    """Ключ в базе — относительный, имя на диске несёт вид сущности и суффикс.

    Относительный ключ переживает смену тома и переезд в S3 (соглашение от
    2026-08-23). Префикс `op<id>_` и случайный суффикс нужны, чтобы два скана с
    именем «Акт.pdf» не затёрли друг друга в общем каталоге.
    """
    monkeypatch.setattr(O, 'UPLOADS_ROOT', str(tmp_path))
    db = _Db(operation=object())
    _upload('Акт №77.pdf', b'%PDF-1.4', db=db)

    row = db.files[0]
    assert row.path.startswith('operations/')
    assert not os.path.isabs(row.path)
    assert row.original_name == 'Акт №77.pdf'      # человеку — исходное имя
    stored = os.path.basename(row.path)
    assert stored.startswith('op1_')                # на диске — с видом сущности
    assert stored != 'Акт №77.pdf'
    assert os.path.exists(tmp_path / row.path)


def test_two_files_with_the_same_name_do_not_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(O, 'UPLOADS_ROOT', str(tmp_path))
    db = _Db(operation=object())
    _upload('Акт.pdf', b'first', db=db)
    _upload('Акт.pdf', b'second', db=db)
    paths = {r.path for r in db.files}
    assert len(paths) == 2, 'одинаковые имена затёрли друг друга'
    assert len(list((tmp_path / 'operations').iterdir())) == 2
