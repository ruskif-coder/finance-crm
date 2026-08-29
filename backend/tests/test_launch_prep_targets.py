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
