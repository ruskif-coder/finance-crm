# -*- coding: utf-8 -*-
"""Приложенный к операции файл виден в строке реестра.

ЧТО СЛУЧИЛОСЬ (22.09.2026). Человек прикладывал к операции скан — файл ложился и в
базу, и на диск, — а в колонке «Документы» оставался прочерк. Пиктограмма зависела
ТОЛЬКО от `document_link`, то есть от внешней ссылки; про файлы строка реестра не
знала вовсе, потому что ручка списка их не отдавала.

Ни ошибки, ни пустого ответа: файл был на месте, открыть его из реестра было нечем.
Со стороны это выглядело как «файл не прикрепился» — то есть как потеря данных.

Прибор держит два утверждения, и оба нужны:

  1. ручка списка отдаёт приложенные файлы в строке — иначе колонка снова ослепнет;
  2. отдаёт ОДНИМ запросом на страницу, а не по строке. Реестр показывает до
     пятисот операций за раз, и запрос на каждую превратил бы открытие страницы в
     полминуты ожидания — молча, потому что данные-то верные.

Сам подсчёт запросов — не придирка к производительности: этот проект уже ловил
N+1 на экране в 57 строк, делавшем 60 запросов.
"""
import io

import pytest
from fastapi import UploadFile
from sqlalchemy import event

from app.database import SessionLocal
from app.models import Operation, OperationFile, User
from app.routers.operations import get_operations, upload_operation_file


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def admin(db):
    u = db.query(User).filter(User.is_active == 1).order_by(User.id).first()
    if u is None:
        pytest.skip("нужна живая учётка")
    return u


@pytest.fixture
def op_with_file(db, admin):
    """Операция с реально загруженным файлом. Загружаем ручкой, а не INSERT'ом:
    строка в базе без файла на диске проверяла бы половину пути."""
    import asyncio

    op = db.query(Operation).order_by(Operation.id).first()
    if op is None:
        pytest.skip("нужна хотя бы одна операция")
    up = UploadFile(filename="ТЕСТ скан.pdf", file=io.BytesIO(b"%PDF-1.4 test"))
    # asyncio.run, а НЕ get_event_loop: второй отдаёт цикл текущего потока, а его к
    # этому моменту мог закрыть любой из полутора тысяч тестов, идущих раньше. Первая
    # редакция зеленела в одиночном прогоне и разваливалась в общем — то есть прибор
    # врал ровно там, где на него смотрят.
    asyncio.run(upload_operation_file(op.id, file=up, db=db, current_user=admin))
    db.commit()
    row = (db.query(OperationFile).filter(OperationFile.operation_id == op.id)
           .order_by(OperationFile.id.desc()).first())
    yield op, row
    # Уборка: и запись, и файл на диске. Удаление НЕ заглушаем: первая редакция
    # обернула его в try/except и звала несуществующее поле `stored_path` — записи
    # исчезали, файлы оставались, и прибор молча копил сирот на стенде. Шесть штук
    # за один прогон. Проверка успеха здесь и есть разница между «убрал» и «думаю,
    # что убрал».
    from app.files_safe import remove_upload
    fresh = db.query(OperationFile).filter(OperationFile.id == row.id).first()
    if fresh is not None:
        gone = remove_upload(fresh.path, subdir="operations")
        db.delete(fresh)
        db.commit()
        assert gone, "файл теста остался на диске: %s" % fresh.path


# Списочные умолчания ручки — объекты `Query(None)`, и при ПРЯМОМ вызове, в обход
# FastAPI, они приезжают в функцию как есть: фильтр пытается сравнить поле со
# служебным объектом и падает. Поэтому передаём их явно.
_DEFAULTS = dict(status=None, bank=None, article_id=None, counterparty_id=None,
                 period=None, gaps=None, ids=None)


def _list(db, admin, limit=500):
    return get_operations(skip=0, limit=limit, db=db, current_user=admin, **_DEFAULTS)


def _row_of(db, admin, op_id):
    """Строку берём точечно по id: реестр сортирован по дате и отдаёт страницу, а
    операция стенда может лежать далеко за её пределами. Первая редакция прибора на
    этом и покраснела — искала строку среди пятисот свежих."""
    args = dict(_DEFAULTS, ids=[op_id])
    res = get_operations(skip=0, limit=500, db=db, current_user=admin, **args)
    return next((r for r in res["items"] if r["id"] == op_id), None)


def test_attached_file_reaches_the_registry_row(db, admin, op_with_file):
    """Файл в строке — с именем: список выбора без имён не список."""
    op, f = op_with_file
    row = _row_of(db, admin, op.id)
    assert row is not None
    names = [x["name"] for x in row["files"]]
    assert "ТЕСТ скан.pdf" in names, "приложенный файл не доехал до строки реестра"
    assert all(x.get("id") for x in row["files"]), "без id файл нечем открыть"


def test_row_without_files_says_so_explicitly(db, admin):
    """Пустой список, а не отсутствие ключа: экран отличает «файлов нет» от
    «ручка про файлы не знает» только по наличию поля."""
    res = _list(db, admin, limit=50)
    assert res["items"], "нужна хотя бы одна операция"
    assert all("files" in r for r in res["items"])
    assert all(isinstance(r["files"], list) for r in res["items"])


def test_files_are_fetched_in_one_query(db, admin, op_with_file):
    """Один запрос за файлами на всю страницу, а не по строке.

    Считаем обращения именно к таблице файлов: общее число запросов зависит от
    соседнего кода и сделало бы прибор ложно-красным при любой правке рядом.
    """
    hits = []

    def before(conn, cursor, statement, params, context, executemany):
        if "operation_files" in statement.lower():
            hits.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", before)
    try:
        _list(db, admin)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", before)

    assert len(hits) == 1, (
        "запросов к файлам операций: %d — значит тянем по строке, а не пачкой"
        % len(hits))
