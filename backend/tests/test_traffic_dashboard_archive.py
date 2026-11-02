"""Дашборд трафика: РК сделок в терминальных стадиях («Архив успешных», «не случилась», «сорвалась»)
не показываются, пока не включён показ архива (владелец 22.10.2026, пример — NSNHTE: сделка «не случилась»,
а РК висела «ожидает сборки»). Стадии последовательны, так что терминальная сделка не бывает «живой» —
исключений по статусу РК нет. Только чтение базы стенда.

С 02.11.2026 архив трафика шире (владелец): «трафик контролит сделку недолго, от сборки до завершения, для трафика
уход на итоговую сверку — является архивом рекламной кампании». Поэтому в архиве и РК сделок на «Итоговой сверке» и
на любой стадии после неё (закрывающие, ЭДО, ОРД, оплата) — до 02.11 они висели в реестре трафика неделями."""
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
          JOIN sales_stage_phases p ON p.id = s.phase_id
         WHERE s.is_terminal OR s.is_lost
            OR (p.sort_order, s.sort_order) >= (
                SELECT rp.sort_order, r.sort_order FROM sales_stages r
                  JOIN sales_stage_phases rp ON rp.id = r.phase_id WHERE r.name = 'Итоговая сверка')"""))}


def test_deal_on_final_recon_is_traffic_archive(db):
    """Поломка, которую ловит: правило архива снова смотрит только на терминальные стадии — РК, завершённая кнопкой
    «Завершить» (сделка уходит на «Итоговую сверку»), остаётся в реестре трафика."""
    recon = {r[0] for r in db.execute(text("""
        SELECT c.id FROM ad_campaign c JOIN sales_deals d ON d.id = c.deal_id
          JOIN sales_stages s ON s.id = d.our_stage_id WHERE s.name = 'Итоговая сверка'"""))}
    if not recon:
        pytest.skip('на стенде нет РК сделок на «Итоговой сверке»')
    default = {r['id'] for r in td.dashboard(scope='all', archive=False, db=db, user=_admin())['rows']}
    assert not (default & recon), 'РК сделок на «Итоговой сверке» видны без показа архива'


def test_live_stages_stay_in_the_list(db):
    """«В размещении» и раньше — работа трафика, в архив не уходят."""
    live = {r[0] for r in db.execute(text("""
        SELECT c.id FROM ad_campaign c JOIN sales_deals d ON d.id = c.deal_id
          JOIN sales_stages s ON s.id = d.our_stage_id
         WHERE s.name IN ('Бронь', 'Готовятся к старту', 'В размещении')"""))}
    if not live:
        pytest.skip('на стенде нет РК живых стадий')
    default = {r['id'] for r in td.dashboard(scope='all', archive=False, db=db, user=_admin())['rows']}
    assert live <= default


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
