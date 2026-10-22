"""Дашборд трафика: РК сделок в терминальных стадиях («Архив успешных», «не случилась», «сорвалась»)
не показываются, пока не включён показ архива (владелец 22.10.2026, пример — NSNHTE: сделка «не случилась»,
а РК висела «ожидает сборки»). Стадии последовательны, так что терминальная сделка не бывает «живой» —
исключений по статусу РК нет. Только чтение базы стенда."""
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import app.launch_prep.models  # noqa: F401
import app.models  # noqa: F401
from app.database import SessionLocal
from app.routers import traffic_dashboard as td


@pytest.fixture
def db():
    d = SessionLocal()
    yield d
    d.close()


def _admin():
    return SimpleNamespace(id=-1, role=SimpleNamespace(key='admin', is_master=True), role_id=None)


def _closed_ids(db):
    return {r[0] for r in db.execute(text("""
        SELECT c.id FROM ad_campaign c JOIN sales_deals d ON d.id = c.deal_id
          JOIN sales_stages s ON s.id = d.our_stage_id
         WHERE s.is_terminal OR s.is_lost"""))}


def test_closed_deals_are_hidden_by_default_and_shown_with_archive(db):
    closed = _closed_ids(db)
    if not closed:
        pytest.skip('на стенде нет РК закрытых сделок')
    default = {r['id'] for r in td.dashboard(scope='all', archive=False, db=db, user=_admin())['rows']}
    with_archive = {r['id'] for r in td.dashboard(scope='all', archive=True, db=db, user=_admin())['rows']}
    assert not (default & closed), 'РК закрытых сделок видны без показа архива'
    assert closed <= with_archive, 'показ архива не вернул РК закрытых сделок'
    assert default <= with_archive


def test_response_says_how_many_are_in_archive(db):
    got = td.dashboard(scope='all', archive=False, db=db, user=_admin())
    assert got['archived'] == len(_closed_ids(db))
