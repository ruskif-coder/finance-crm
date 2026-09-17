# -*- coding: utf-8 -*-
"""Заявки о сбоях: приём открыт, разбор закрыт, закрытие требует причины.

Раздел устроен вокруг одного напряжения. ПОДАЧА должна быть доступна всем — иначе
получится ровно то, ради выхода из чего он заводится: человек видит сбой и не может о
нём сказать. РАЗБОР должен быть закрыт: там чужие снимки экрана, адреса страниц и имена.

Приборы держат обе половины и границу между ними.
"""
import pytest
from sqlalchemy import text

# Внешние ключи заявки смотрят в users, cabinet_account, sales_publishers и
# debug_backlog: без этих модулей в реестре SQLAlchemy не соберёт таблицу вовсе, и
# падает не тест, а импорт.
from app import backlog_models as _backlog_models  # noqa: F401
from app import models as _core_models  # noqa: F401
from app.cabinet import models as _cabinet_models  # noqa: F401
from app.sales import models as _sales_models  # noqa: F401
from app.bugs import models as m


def _db():
    from app.database import SessionLocal
    return SessionLocal()


def _mk(db, **kw):
    from app.routers import bugs as api
    kw.setdefault("contour", m.STAFF)
    kw.setdefault("author_name", "прибор")
    kw.setdefault("comment", "кнопка не нажимается")
    r = api.create_report(db, **kw)
    db.commit()
    return r


def _drop(db, r):
    db.execute(text("DELETE FROM bug_report WHERE id = :i"), {"i": r.id})
    db.commit()


def test_a_report_without_words_is_refused():
    """Пустая заявка бесполезна: разбирать в ней нечего, а в журнале она занимает место
    и создаёт впечатление, что о сбое сообщили."""
    from fastapi import HTTPException
    from app.routers import bugs as api

    db = _db()
    try:
        with pytest.raises(HTTPException):
            api.create_report(db, contour=m.STAFF, author_name="прибор", comment="   ")
    finally:
        db.rollback()
        db.close()


def test_the_surroundings_are_captured_not_asked():
    """Адрес страницы, версия и размер окна сохраняются как есть.

    Это главное, ради чего заявка имеет смысл: без них она равна «у меня что-то не
    работает». Требовать от человека переписать адрес руками — значит получать опечатки.
    """
    db = _db()
    r = _mk(db, page_url="/traffic/queue?tab=all", page_title="Конвейер трафика",
            app_version="2.6.14", viewport="1920x1080")
    try:
        assert r.page_url == "/traffic/queue?tab=all"
        assert r.page_title == "Конвейер трафика"
        assert r.app_version == "2.6.14" and r.viewport == "1920x1080"
    finally:
        _drop(db, r); db.close()


def test_long_values_are_trimmed_before_the_insert():
    """Адрес бывает длиннее колонки. Обрезаем ДО вставки: падение здесь читалось бы как
    «кнопка не работает», и заявка о сбое потерялась бы из-за сбоя."""
    db = _db()
    r = _mk(db, page_url="/x?" + "a" * 900, user_agent="U" * 900)
    try:
        assert len(r.page_url) <= 500 and len(r.user_agent) <= 500
    finally:
        _drop(db, r); db.close()


def test_both_contours_land_in_one_journal():
    """Площадка пишет в тот же журнал, с пометкой контура (владелец 17.09.2026).

    Отдельный список означал бы, что половина заявок теряется из виду просто потому,
    что лежит в другом месте.
    """
    db = _db()
    a = _mk(db, contour=m.STAFF, author_name="сотрудник")
    b = _mk(db, contour=m.PUB, author_name="площадка")
    try:
        rows = db.query(m.BugReport).filter(m.BugReport.id.in_([a.id, b.id])).all()
        assert {r.contour for r in rows} == {m.STAFF, m.PUB}
        assert m.CONTOUR_LABEL[m.PUB] == "площадка"
    finally:
        _drop(db, a); _drop(db, b); db.close()


def test_closing_without_a_reason_is_refused():
    """«Закрыто» без объяснения через месяц неотличимо от «забыли» — то же правило,
    что в бэклоге отладки."""
    from fastapi import HTTPException
    from app.routers.bugs import BugPatch, bug_patch

    db = _db()
    r = _mk(db)

    class _U:
        id = None
    try:
        with pytest.raises(HTTPException):
            bug_patch(r.id, BugPatch(status="исправлено"), db=db, user=_U())
    finally:
        db.rollback()
        _drop(db, r); db.close()


def test_submitting_is_open_and_reading_is_not():
    """Граница раздела. Подача закрыта только входом, журнал — правом `settings_bugs`.

    Прибор смотрит на сам код: зависимости ручек, а не на список маршрутов. Повесь
    кто-нибудь право на подачу — и заявки перестанут приходить от тех, кто чаще всего
    и натыкается на сбой.
    """
    import inspect
    from app.routers import bugs as api

    submit = inspect.getsource(api.bug_create) + inspect.getsource(api.bug_attach)
    assert "get_current_user" in submit
    assert "require_permission" not in submit, "подача закрыта правом — так нельзя"

    read = inspect.getsource(api.bug_list) + inspect.getsource(api.bug_one)
    assert "VIEW" in read, "журнал открыт без права"


def test_a_stranger_cannot_add_to_someone_elses_report():
    """Заявка — свидетельство. Дописать в чужое не должен никто, включая разбирающего."""
    import inspect
    from app.routers import bugs as api

    src = inspect.getsource(api.bug_attach)
    assert "author_user_id != user.id" in src


def test_the_notification_is_registered_and_urgent():
    """Событие есть в реестре и идёт панелью и телеграмом, а не дайджестом: за заявкой
    стоит ждущий человек, и сутки ожидания равны «нам всё равно»."""
    from app.notify import registry

    ev = registry.get("bug_report_new")
    assert ev is not None
    assert ev.channels.get("app") and ev.channels.get("tg")
    assert not ev.channels.get("digest")
