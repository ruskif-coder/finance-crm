"""Файлы брифа сделки: хранение, отдача и уборка.

Приборы стоят на трёх местах, где ошибка не видна глазами:

  · **два файла с одним именем.** «бриф.pdf» от двух клиентов в одной сделке обязаны
    сохраниться оба. Затирание было бы молчаливым: список показал бы две строки, а на
    диске лежал бы один файл, и скачались бы два одинаковых;
  · **путь на диск не берётся из базы как есть.** Ключ файла хранится у нас, но доверие
    к нему держится на том, что запись никто не испортил. Отдача и удаление идут через
    `app/files_safe.py`, и папка сужена до своей: файл договора не должен уезжать
    ручкой брифа (разбор внешнего аудита, F1-06);
  · **удаление строки убирает файл с диска.** Иначе хранилище растёт сиротами — их там
    уже 77% объёма.

Эндпоинты зовутся напрямую с фиктивным admin — как в остальных тестах этого набора.
"""
import asyncio
import os
from types import SimpleNamespace

import pytest

import app.notify.models  # noqa: F401  — иначе маппер не найдёт notification_profiles
import app.ord.models  # noqa: F401  — сделка ссылается на зеркало изначальных договоров
from app.database import SessionLocal
from app.models import AuditLog
from app.routers import sales_dashboard as sd
from app.sales.models import SalesDeal, SalesDealBriefFile

_FAKE_ADMIN = SimpleNamespace(role=SimpleNamespace(key='admin'), id=None,
                              email='test', name='тест')

DEAL_CODE = 'TSTBRF'


class _Upload:
    """Минимальная замена UploadFile: нужен только filename и await read()."""

    def __init__(self, name, data):
        self.filename = name
        self._data = data

    async def read(self):
        return self._data


def _purge(db):
    deals = db.query(SalesDeal).filter(SalesDeal.code == DEAL_CODE).all()
    for d in deals:
        for f in db.query(SalesDealBriefFile).filter(SalesDealBriefFile.deal_id == d.id).all():
            path = os.path.join(sd.BRIEF_UPLOADS_DIR, f.filename)
            if os.path.exists(path):
                os.remove(path)
            db.delete(f)
        (db.query(AuditLog)
           .filter(AuditLog.action.in_(('upload_deal_brief_file', 'delete_deal_brief_file')),
                   AuditLog.entity_id == d.id).delete(synchronize_session=False))
        db.delete(d)
    db.commit()


@pytest.fixture
def db():
    session = SessionLocal()
    _purge(session)
    try:
        yield session
    finally:
        session.rollback()
        _purge(session)
        session.close()


@pytest.fixture
def deal(db):
    d = SalesDeal(code=DEAL_CODE, bitrix_id='local-brief-test', title='ТЕСТ бриф-файлы')
    db.add(d)
    db.commit()
    return d


def _upload(db, deal, name, data=b'%PDF-1.4 test'):
    # asyncio.run, а не get_event_loop: соседние тесты набора закрывают свою петлю, и
    # общий прогон падал «There is no current event loop», хотя в одиночку файл проходил.
    return asyncio.run(sd.store_brief_file(db, deal, _Upload(name, data), _FAKE_ADMIN))


def test_file_lands_on_disk_and_in_the_list(db, deal):
    out = _upload(db, deal, 'бриф.pdf')
    assert out['name'] == 'бриф.pdf'
    row = db.query(SalesDealBriefFile).filter(SalesDealBriefFile.deal_id == deal.id).one()
    assert os.path.exists(os.path.join(sd.BRIEF_UPLOADS_DIR, row.filename))
    assert row.original_name == 'бриф.pdf', 'человеку файл возвращается под своим именем'
    items = sd.brief_files_of(db, deal.id)
    assert [i['name'] for i in items] == ['бриф.pdf']


def test_two_files_with_the_same_name_both_survive(db, deal):
    _upload(db, deal, 'бриф.pdf', b'first')
    _upload(db, deal, 'бриф.pdf', b'second')
    rows = db.query(SalesDealBriefFile).filter(SalesDealBriefFile.deal_id == deal.id).all()
    assert len(rows) == 2
    assert len({r.filename for r in rows}) == 2, 'имена на диске обязаны различаться'
    for r in rows:
        assert os.path.exists(os.path.join(sd.BRIEF_UPLOADS_DIR, r.filename))


def test_forbidden_extension_is_refused(db, deal):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _upload(db, deal, 'скрипт.exe', b'MZ')
    assert e.value.status_code == 415
    assert db.query(SalesDealBriefFile).filter(
        SalesDealBriefFile.deal_id == deal.id).count() == 0


def test_too_big_is_refused(db, deal):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _upload(db, deal, 'огромный.pdf', b'x' * (sd.BRIEF_MAX_BYTES + 1))
    assert e.value.status_code == 413


def test_empty_file_is_refused(db, deal):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _upload(db, deal, 'пусто.pdf', b'')
    assert e.value.status_code == 400


def test_download_returns_the_original_name(db, deal):
    _upload(db, deal, 'ТЗ клиента.docx', b'docx')
    row = db.query(SalesDealBriefFile).filter(SalesDealBriefFile.deal_id == deal.id).one()
    resp = sd.brief_file_response(db, deal.id, row.id)
    assert resp.filename == 'ТЗ клиента.docx'


def test_file_of_another_deal_is_not_served(db, deal):
    """Ручка спрашивает пару «сделка × файл», а не один id: иначе чужой файл уехал бы
    по прямой ссылке тому, у кого доступ только к своей сделке."""
    from fastapi import HTTPException
    other = SalesDeal(code='TSTBR2', bitrix_id='local-brief-test-2', title='ТЕСТ вторая')
    db.add(other)
    db.commit()
    try:
        _upload(db, deal, 'чужой.pdf')
        row = db.query(SalesDealBriefFile).filter(SalesDealBriefFile.deal_id == deal.id).one()
        with pytest.raises(HTTPException) as e:
            sd.brief_file_response(db, other.id, row.id)
        assert e.value.status_code == 404
    finally:
        db.delete(other)
        db.commit()


def test_delete_removes_the_row_and_the_file(db, deal):
    _upload(db, deal, 'снимем.pdf')
    row = db.query(SalesDealBriefFile).filter(SalesDealBriefFile.deal_id == deal.id).one()
    path = os.path.join(sd.BRIEF_UPLOADS_DIR, row.filename)
    sd.delete_brief_file(db, deal, row.id, _FAKE_ADMIN)
    assert db.query(SalesDealBriefFile).filter(
        SalesDealBriefFile.deal_id == deal.id).count() == 0
    assert not os.path.exists(path), 'файл остался сиротой на диске'


def test_stored_path_stays_inside_its_own_folder(db, deal):
    """Имя с попыткой выйти из папки санитизируется на входе, а не проверяется потом."""
    _upload(db, deal, '../../etc/passwd.txt', b'x')
    row = db.query(SalesDealBriefFile).filter(SalesDealBriefFile.deal_id == deal.id).one()
    assert '/' not in row.filename and '..' not in row.filename
    full = os.path.realpath(os.path.join(sd.BRIEF_UPLOADS_DIR, row.filename))
    assert full.startswith(os.path.realpath(sd.BRIEF_UPLOADS_DIR) + os.sep)


# ── область видимости сделки в ручках конструктора МП ────────────────────────

def test_mp_brief_files_ask_for_deal_scope(db, deal):
    """Право конструктора МП не должно открывать файлы ЧУЖОЙ сделки.

    Найдено прогоном 21.09.2026. `_guard_owned` спрашивает владение ПЛАНОМ, а при
    `deals_scope='all'` (умолчание) не спрашивает ничего — сделка при этом может быть
    вне зоны видимости человека. На 21.09 не стреляло: у всех четырёх ролей с
    `media_plans_editor` область реестра 'all'. Это свойство ДАННЫХ, и прибор стоит
    ровно на том, чтобы первая роль с 'own' не получила чужие файлы молча.

    Прибор структурный: проверяем, что резолвер сделки зовёт `_assert_deal_in_scope`.
    Поведенческий потребовал бы живой роли с 'own' на стенде, то есть артефакта в
    правах — а права тут и есть предмет проверки.
    """
    import inspect

    from app.routers import media_plans as mp
    src = inspect.getsource(mp._plan_deal_for_brief)
    assert '_assert_deal_in_scope' in src, (
        'ручки файлов брифа в конструкторе МП перестали спрашивать область видимости '
        'сделки — право медиапланов снова открывает чужую сделку в обход реестра')


def test_every_mp_brief_route_goes_through_the_resolver(db):
    """Все четыре ручки обязаны идти через один резолвер — иначе проверка выше
    сторожит функцию, которую обошли стороной."""
    import inspect

    from app.routers import media_plans as mp
    for name in ('mp_list_brief_files', 'mp_upload_brief_file',
                 'mp_download_brief_file', 'mp_delete_brief_file'):
        src = inspect.getsource(getattr(mp, name))
        assert '_plan_deal_for_brief' in src, f'{name} резолвит сделку в обход общего пути'
