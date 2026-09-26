"""Подстановка получателей и комплекты: проверяется то, что подсказывает человеку.

Модуль ничего не решает за аккаунта — он предлагает. Значит цена ошибки здесь не «упало»,
а «предложил не то, и человек согласился»: список площадок выглядит осмысленным в любом
случае, и подмена заметна только на выпуске маркера или, хуже, у площадки.

Отсюда состав проверок: разрешение услуги честно называет источник и честно признаёт
незнание; кандидаты не выходят за отмеченные услуги и рабочие поверхности; вердикт
неизменяем; в колонке пути лежит относительный ключ, а не абсолютный путь.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.database import SessionLocal
from app.launch_prep.models import LaunchPrepCreativeSet
from app.routers.launch_prep import (CREATIVES_DIR, _candidates, _derive_form,
                                     _set_state, resolve_service)
from app.sales.models import (SalesDeal, SalesPublisherService, SalesPublisherSurface,
                              SalesService)
from tests._launch_prep_cleanup import drop_campaign_creatives

NO_BASE = 9500


@pytest.fixture
def db():
    session = SessionLocal()
    _purge(session)
    try:
        yield session
    finally:
        _purge(session)
        session.close()


def _purge(session):
    session.rollback()
    drop_campaign_creatives(session, NO_BASE)   # до комплектов: FK без каскада
    session.query(LaunchPrepCreativeSet).filter(
        LaunchPrepCreativeSet.no >= NO_BASE).delete(synchronize_session=False)
    session.commit()


# ── разрешение услуги ────────────────────────────────────────────────────────
def test_service_is_resolved_from_product_by_name(db):
    """Ссылки на услугу у сделки нет — есть имя, и оно совпадает у живых сделок."""
    svc = db.query(SalesService).filter(SalesService.is_active.is_(True)).first()
    assert svc, "в справочнике нет ни одной услуги"
    deal = db.query(SalesDeal).filter(SalesDeal.product == svc.name).first()
    if deal is None:
        pytest.skip(f"нет сделки с продуктом «{svc.name}»")

    got, reason = resolve_service(db, deal)
    assert got is not None and got.id == svc.id
    assert reason, "источник обязан называться: подсказка без обоснования — догадка"


def test_unknown_product_is_reported_not_swallowed(db):
    """Продукт есть, а услуги такой нет — дыра в справочнике, и её должно быть видно.

    Молчаливое «услуга не определена» отправило бы человека искать причину в разметке
    площадок, где всё в порядке.
    """
    deal = SimpleNamespace(id=-1, product='Такой услуги нет 12345')
    got, reason = resolve_service(db, deal)
    assert got is None
    assert 'не найден в справочнике' in reason and 'Такой услуги нет 12345' in reason


def test_missing_product_says_so(db):
    got, reason = resolve_service(db, SimpleNamespace(id=-1, product=None))
    assert got is None and 'не указан продукт' in reason


# ── кандидаты в получатели ───────────────────────────────────────────────────
def test_candidates_never_leave_the_marked_services(db):
    """Предложить площадку без этой услуги — предложить то, чего она не продаёт."""
    marked = db.query(SalesPublisherService).filter(
        SalesPublisherService.is_active.is_(True)).first()
    if marked is None:
        pytest.skip("ни одна услуга не отмечена ни у одной площадки")

    got = _candidates(db, marked.service_id, [])
    assert got, "услуга отмечена, но кандидатов нет — сломана склейка поверхностей"

    allowed = {(r.publisher_id, r.surface_kind) for r in
               db.query(SalesPublisherService).filter(
                   SalesPublisherService.service_id == marked.service_id,
                   SalesPublisherService.is_active.is_(True)).all()}
    for c in got:
        assert (c["publisher_id"], c["surface_kind"]) in allowed


def test_candidates_only_on_working_surfaces(db):
    """«Поверхность есть» и «мы с ней работаем» — разные признаки, и склеивать их нельзя.

    Именно на этой склейке в исходном Excel «у них нет приложения» не отличалось от
    «приложение есть, но мы его не продаём».
    """
    marked = db.query(SalesPublisherService).filter(
        SalesPublisherService.is_active.is_(True)).first()
    if marked is None:
        pytest.skip("ни одна услуга не отмечена")

    for c in _candidates(db, marked.service_id, []):
        surface = db.query(SalesPublisherSurface).filter(
            SalesPublisherSurface.publisher_id == c["publisher_id"],
            SalesPublisherSurface.kind == c["surface_kind"]).first()
        assert surface is not None and surface.we_work, (
            f"площадка {c['name']} предложена на нерабочей поверхности")


def test_candidates_carry_tech_requirements(db):
    """ТТ едут вместе с площадкой: кнопка на экране отправки не должна ходить в справочник."""
    marked = db.query(SalesPublisherService).filter(
        SalesPublisherService.is_active.is_(True)).first()
    if marked is None:
        pytest.skip("ни одна услуга не отмечена")
    got = _candidates(db, marked.service_id, [])
    assert got and 'tech_requirements' in got[0]


def test_surface_filter_narrows_candidates(db):
    marked = db.query(SalesPublisherService).filter(
        SalesPublisherService.is_active.is_(True)).first()
    if marked is None:
        pytest.skip("ни одна услуга не отмечена")
    narrowed = _candidates(db, marked.service_id, [marked.surface_kind])
    assert all(c["surface_kind"] == marked.surface_kind for c in narrowed)


# ── форма материала ──────────────────────────────────────────────────────────
def test_form_is_derived_from_files():
    """Форма — из состава файлов, а не из отдельного вопроса человеку."""
    f = lambda n: SimpleNamespace(original_name=n)
    assert _derive_form([f('banner.zip')]) == 'BannerHtml5'
    assert _derive_form([f('index.html')]) == 'BannerHtml5'
    assert _derive_form([f('roll.mp4')]) == 'Video'
    assert _derive_form([f('300x600.png')]) == 'Banner'
    assert _derive_form([]) is None
    # Смешанный комплект: архив перевешивает — HTML5-баннер остаётся HTML5-баннером,
    # даже если рядом лежит превью-картинка.
    assert _derive_form([f('300x600.png'), f('banner.zip')]) == 'BannerHtml5'


# ── состояние комплекта ──────────────────────────────────────────────────────
def test_set_state_is_computed_from_verdict_and_marker():
    s = SimpleNamespace(erid=None, sent_at=None)
    assert _set_state(s, None) == 'черновик'
    assert _set_state(s, SimpleNamespace(verdict=None)) == 'черновик'
    assert _set_state(s, SimpleNamespace(verdict='на доработку')) == 'на доработку'
    assert _set_state(s, SimpleNamespace(verdict='ок')) == 'готов к отправке'

    sent = SimpleNamespace(erid=None, sent_at='2026-08-26')
    assert _set_state(sent, SimpleNamespace(verdict='ок')) == 'отправлен'

    # Разворот цепочки 28.08.2026: пока хоть одна пара у трафика, комплект площадкам
    # НЕ отправлен. Одно слово на оба состояния читалось как «ушло в площадку».
    at_traffic = [{"pair_id": 1, "traffic_verdict": None},
                  {"pair_id": 2, "traffic_verdict": 'ок'}]
    assert _set_state(sent, SimpleNamespace(verdict='ок'), at_traffic) == 'у трафика'
    passed = [{"pair_id": 1, "traffic_verdict": 'ок'}, {"pair_id": 2, "traffic_verdict": 'ок'}]
    assert _set_state(sent, SimpleNamespace(verdict='ок'), passed) == 'отправлен'
    # Маркер старше всего: у маркированного комплекта спрашивать «где он» уже поздно.
    assert _set_state(SimpleNamespace(erid='E1', sent_at='2026-08-26'),
                      SimpleNamespace(verdict='ок'), at_traffic) == 'маркирован'

    marked = SimpleNamespace(erid='ERID123', sent_at='2026-08-26')
    assert _set_state(marked, SimpleNamespace(verdict='ок')) == 'маркирован'


# ── путь файла ───────────────────────────────────────────────────────────────
def test_stored_path_is_a_relative_key():
    """Соглашение от 23.08.2026, и этот модуль — его первый потребитель.

    Абсолютный путь в колонке привязал бы записи к текущему устройству хранения: переезд
    в объектное хранилище пришлось бы делать миграцией данных, а не заменой корня.
    """
    assert not CREATIVES_DIR.startswith('/'), "ключ обязан быть относительным"
    assert CREATIVES_DIR == 'creatives'


def test_primary_review_requires_reason_for_rework():
    """«На доработку» без причины возвращается клиенту тем же составом."""
    from app.routers.launch_prep import PrimaryReviewIn, primary_review
    from app.database import SessionLocal as SL
    s = SL()
    try:
        row = s.query(LaunchPrepCreativeSet).first()
        if row is None:
            pytest.skip("в базе нет ни одного комплекта")
        with pytest.raises(HTTPException) as e:
            primary_review(row.id, PrimaryReviewIn(verdict='на доработку'), s,
                           SimpleNamespace(role=SimpleNamespace(key='admin'),
                                           id=None, name='тест'))
        assert 'причин' in e.value.detail.lower()
    finally:
        s.close()


# ── статус площадки в подборе (владелец 30.08.2026) ──────────────────────────
#
# Фильтра не было НИКАКОГО: замер показал, что stoletov.ru числится «НА ПАУЗЕ», а на ней
# шесть пар прошли всю цепочку и получен ЕРИД. Архив теперь не предлагается, пауза
# приезжает помеченной — она временная, и запрет заблокировал бы законный случай.

def test_archived_publisher_is_not_offered(db):
    """Архивная площадка не приезжает в подборе — доказательно.

    Первая версия этого прибора была ЗЕЛЕНА ВХОЛОСТУЮ: она проверяла, что в выдаче нет
    архивных, а их там не было и без фильтра — у архивных площадок нет активных услуг с
    рабочей поверхностью, и джойн отсекал их сам. Снятие фильтра теста не роняло.

    Поэтому здесь берётся площадка, которая В ВЫДАЧЕ ЕСТЬ, переводится в архив, и
    проверяется, что она из неё пропала. Изменение откатывается в любом случае.
    """
    from app.routers.launch_prep import _candidates
    from app.sales.models import SalesPublisher, SalesPublisherService

    sid = db.query(SalesPublisherService.service_id).first()
    if sid is None:
        pytest.skip('на стенде нет услуг у площадок')
    before = _candidates(db, sid[0], [])
    if not before:
        pytest.skip('у услуги нет ни одной площадки')

    victim_id = before[0]['publisher_id']
    row = db.query(SalesPublisher).filter(SalesPublisher.id == victim_id).first()
    was = row.status
    try:
        row.status = 'АРХИВ'
        db.commit()
        after = _candidates(db, sid[0], [])
        assert victim_id not in {c['publisher_id'] for c in after}, (
            'площадка в архиве всё ещё предлагается в подборе'
        )
        assert len(after) == len(before) - 1
    finally:
        row.status = was
        db.commit()


def test_paused_publisher_is_offered_but_marked(db):
    """Пауза остаётся в подборе и несёт пометку — тоже доказательно.

    Площадка переводится в паузу и обязана остаться в списке, но уже с `status_warn`.
    Проверка «пометка совпадает со статусом» без этого зелена на любых данных.
    """
    from app.routers.launch_prep import PICKER_WARN_STATUSES, _candidates
    from app.sales.models import SalesPublisher, SalesPublisherService

    sid = db.query(SalesPublisherService.service_id).first()
    if sid is None:
        pytest.skip('на стенде нет услуг у площадок')
    before = _candidates(db, sid[0], [])
    if not before:
        pytest.skip('у услуги нет ни одной площадки')

    victim_id = before[0]['publisher_id']
    row = db.query(SalesPublisher).filter(SalesPublisher.id == victim_id).first()
    was = row.status
    try:
        row.status = PICKER_WARN_STATUSES[0]
        db.commit()
        after = {c['publisher_id']: c for c in _candidates(db, sid[0], [])}
        assert victim_id in after, 'паузовая площадка исчезла из подбора — запрет вместо пометки'
        assert after[victim_id]['status_warn'] is True
        assert after[victim_id]['status'] == PICKER_WARN_STATUSES[0]
    finally:
        row.status = was
        db.commit()


def test_candidates_carry_our_code_flag(db):
    """Выбор площадок делится на «наш код / не наш код» (владелец 26.09.2026): у каждой
    группы своё «добавить всех». Признак едет с кандидатом и совпадает со справочником —
    иначе баннер под нашу DSP ушёл бы площадке, которая крутит в чужой."""
    from app.sales.models import SalesPublisher
    marked = db.query(SalesPublisherService).filter(
        SalesPublisherService.is_active.is_(True)).first()
    if marked is None:
        pytest.skip("ни одна услуга не отмечена")
    got = _candidates(db, marked.service_id, [])
    assert got
    for c in got:
        pub = db.query(SalesPublisher).filter(SalesPublisher.id == c["publisher_id"]).one()
        assert c["our_code"] is bool(pub.our_code), c["name"]
