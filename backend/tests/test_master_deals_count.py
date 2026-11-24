# -*- coding: utf-8 -*-
"""Счётчик «Мастер-сделок» в меню (24.11.2026, владелец): число пакетов, стоящих в «выставление».

Сломает: счётчик посчитан своим правилом, а не тем, что показывает вкладка реестра, — в меню «3», на экране 2.
Или посчитан без области «свои» — тогда роль видит в меню чужие пакеты. Третье — цена: счётчик опрашивается
с каждой страницы раз в минуту, поэтому он обязан быть одним-двумя `SELECT`, а не проходом по пакетам."""
import pytest
from sqlalchemy import event, text

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.master_deal import registry as RG
from app.master_deal import scope as SC
from app.master_deal import status as MST
from app.models import User
from app.routers import master_deals as R

ADMIN_ROLE = "admin"


def _admin(db):
    """Админ стенда — по роли, а не по почте: почта живого человека в фикстуру не кладётся (навык testing-before-prod)."""
    from app.models import Role
    return (db.query(User).join(Role, Role.id == User.role_id)
            .filter(Role.key == ADMIN_ROLE, User.is_active == 1).order_by(User.id).first())


def _issue_tab(db) -> list:
    return [r for r in RG.rows(db, _admin(db)) if r["status"] == MST.ISSUE]


def _sql_count(db, fn):
    """Сколько запросов уйдёт в базу — слушаем конкретное соединение, а не движок.

    Слушатель на Engine не видит соединение, уже взятое сессией из пула, и счётчик молча показывал бы ноль."""
    n = 0

    def spy(*a, **k):
        nonlocal n
        n += 1
    conn = db.connection()
    event.listen(conn, "before_cursor_execute", spy)
    try:
        return fn(), n
    finally:
        event.remove(conn, "before_cursor_execute", spy)


def test_menu_count_equals_issue_tab_of_registry(monkeypatch):
    """Админ видит всё: число на иконке = числу строк вкладки «выставление».

    Если на стенде нет ни одного пакета в «выставление» — ставим на время транзакции и откатываем:
    иначе тест сравнивал бы два нуля и ничего не проверял."""
    monkeypatch.setattr(SC, "can_finance", lambda db, user: False)   # эффективность реестру здесь не нужна
    db = SessionLocal()
    try:
        if not _issue_tab(db):
            mid = db.execute(text("SELECT id FROM master_deals ORDER BY id LIMIT 1")).scalar()
            if mid is not None:
                db.execute(text("UPDATE master_deals SET status = :s WHERE id = :i"), {"s": MST.ISSUE, "i": mid})
                db.flush()
                db.expire_all()
        shown = _issue_tab(db)
        assert shown, "на стенде нет пакетов в «выставление» даже после подстановки"
        assert RG.count_status(db, _admin(db), MST.ISSUE) == len(shown)
        # та же цифра через ручку — именно её читает меню
        assert R.master_count(db=db, user=_admin(db)) == {"waiting": len(shown)}
    finally:
        db.rollback()
        db.close()


def test_count_ignores_other_statuses():
    """Пакет в «ждём оплату» в счётчик не попадает — иначе иконка звала бы туда, где работа уже сделана."""
    db = SessionLocal()
    try:
        before = RG.count_status(db, _admin(db), MST.ISSUE)
        mid = db.execute(text("SELECT id FROM master_deals WHERE status = :s ORDER BY id LIMIT 1"),
                         {"s": MST.ISSUE}).scalar()
        if mid is None:
            pytest.skip("на стенде нет пакета в «выставление»")
        db.execute(text("UPDATE master_deals SET status = :w WHERE id = :i"), {"w": MST.WAIT_PAY, "i": mid})
        db.flush()
        db.expire_all()
        assert RG.count_status(db, _admin(db), MST.ISSUE) == before - 1
    finally:
        db.rollback()
        db.close()


def test_count_respects_own_scope(monkeypatch):
    """Область «свои»: без своих сделок счётчик обязан быть нулём — чужие пакеты в меню не считаются."""
    db = SessionLocal()
    try:
        monkeypatch.setattr(SC, "own_reps", lambda db, user: {-1})
        assert RG.count_status(db, object(), MST.ISSUE) == 0
    finally:
        db.rollback()
        db.close()


def test_count_is_cheap():
    """Счётчик опрашивается раз в минуту с каждой страницы: число запросов не зависит от числа пакетов.

    Админ: выборка id по статусу + чтение роли для области. Роль «свои»: ещё один запрос на владельцев пакетов
    (одним `ANY(ids)`, а не по пакету). Проход по пакетам дал бы на стенде десятки запросов — это и ловим."""
    db = SessionLocal()
    try:
        u = _admin(db)
        _, n = _sql_count(db, lambda: RG.count_status(db, u, MST.ISSUE))
        assert n <= 3, f"счётчик сходил в базу {n} раз — так он не годится для опроса раз в минуту"
    finally:
        db.rollback()
        db.close()


def test_count_is_cheap_for_own_role(monkeypatch):
    """У роли «свои» добавляется ровно один запрос — владельцы пакетов, не по одному на пакет."""
    db = SessionLocal()
    try:
        monkeypatch.setattr(SC, "own_reps", lambda db, user: {2})
        _, n = _sql_count(db, lambda: RG.count_status(db, object(), MST.ISSUE))
        assert n <= 2, f"счётчик для роли «свои» сходил в базу {n} раз"
    finally:
        db.rollback()
        db.close()


def test_count_route_is_not_shadowed_by_package_code():
    """`/count` объявлен выше `/{code}`: иначе FastAPI отдал бы «count» карточке как код пакета."""
    from starlette.routing import Match
    from app.main import app
    scope = {"type": "http", "path": "/api/master-deals/count", "method": "GET", "root_path": "",
             "headers": [], "query_string": b""}
    for route in app.routes:
        if route.matches(scope)[0] is Match.FULL:
            assert route.path == "/api/master-deals/count", f"перехвачено маршрутом {route.path}"
            return
    pytest.fail("маршрут /api/master-deals/count не найден")
