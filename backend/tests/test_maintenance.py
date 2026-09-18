# -*- coding: utf-8 -*-
"""Техобслуживание закрывает систему — и не закрывает себя самого.

Режим опасен обеими крайностями. Не закроет ничего — мы правим прод при живых
пользователях, думая, что они снаружи. Закроет лишнее — админ не войдёт снять его, и
выходить придётся через консоль базы в тот момент, когда это сложнее всего.

Поэтому прибор описывает ГРАНИЦУ: что закрыто, что открыто и почему.
"""
from datetime import datetime, timedelta

from app import maintenance as mnt


def _db():
    from app.database import SessionLocal
    return SessionLocal()


def test_an_ordinary_request_is_closed_and_the_admin_passes():
    """Две половины правила разом: людям закрыто, админу нет."""
    assert mnt.blocks("/api/operations", "POST", is_admin=False, mode="active")
    assert mnt.blocks("/api/operations", "GET", is_admin=False, mode="active")
    assert not mnt.blocks("/api/operations", "POST", is_admin=True, mode="active")


def test_the_way_back_in_stays_open():
    """Вход и состояние режима — единственные открытые двери.

    Без входа админ не войдёт снять обслуживание. Без состояния экран не объяснит, почему
    всё закрыто, и покажет пустую ошибку вместо заглушки.
    """
    assert not mnt.blocks("/api/auth/login", "POST", is_admin=False, mode="active")
    assert not mnt.blocks("/api/maintenance", "GET", is_admin=False, mode="active")


def test_the_root_entry_does_not_open_everything():
    """Ловушка первой редакции: в списке открытых есть корень «/».

    Сравнение по префиксу после `rstrip("/")` превращало его в пустую строку, и открытым
    оказывался КАЖДЫЙ адрес. Режим при этом включался, рисовал заглушку и не закрывал
    ничего — худший вид поломки: тот, который выглядит как работа.
    """
    assert mnt.blocks("/api/sales/deals", "GET", is_admin=False, mode="active")
    assert mnt.blocks("/api/anything/at/all", "POST", is_admin=False, mode="active")
    # Корень и `/api/health` из списка убраны: первого прослойка не видит вовсе (она
    # смотрит только `/api/`), второго в проекте не существует. Защита несуществующего
    # адреса опаснее её отсутствия — в неё верят.
    assert "/" not in mnt.OPEN_PATHS and "/api/health" not in mnt.OPEN_PATHS


def test_before_the_start_nothing_is_closed():
    """Объявлено — не значит наступило: десять минут человек работает как обычно."""
    assert not mnt.blocks("/api/operations", "POST", is_admin=False, mode="announced")
    assert not mnt.blocks("/api/operations", "GET", is_admin=False, mode="announced")


def test_the_state_survives_a_restart():
    """Состояние в БАЗЕ, а не в памяти процесса: перезапуск контейнера не должен снимать
    режим молча — иначе мы правим прод, считая, что люди снаружи."""
    db = _db()
    try:
        st = mnt.announce(db, by="прибор")
        assert st["mode"] == "announced"
        # Новая сессия = то же, что новый процесс после рестарта.
        other = _db()
        try:
            assert other is not db
            assert mnt.state(other)["mode"] == "announced"
        finally:
            other.close()
    finally:
        mnt.cancel(db)
        db.close()


def test_announcement_gives_exactly_ten_minutes():
    """Срок фиксирован (владелец 17.09.2026): выбор из вариантов на кнопке, которую
    жмут в спешке, — лишний вопрос, а лишний вопрос в спешке ошибается."""
    db = _db()
    try:
        st = mnt.announce(db, by="прибор")
        start = datetime.fromisoformat(st["from"])
        left = start - datetime.utcnow()
        assert timedelta(minutes=9) < left <= timedelta(minutes=10)
    finally:
        mnt.cancel(db)
        db.close()


def test_a_broken_value_does_not_lock_everyone_out():
    """Испорченное время в настройке выключает режим, а не запирает систему: опечатка
    не должна стоить рабочего дня всем."""
    db = _db()
    try:
        mnt._set(db, mnt.KEY_FROM, "не-дата")
        db.commit()
        st = mnt.state(db)
        assert st["mode"] == "off" and st.get("broken") == "не-дата"
    finally:
        mnt.cancel(db)
        db.close()


def test_cancel_clears_everything():
    """После снятия не остаётся ни времени, ни текста, ни автора: полурежим хуже режима."""
    db = _db()
    try:
        mnt.announce(db, by="прибор", note="текст")
        st = mnt.cancel(db)
        assert st["mode"] == "off"
        assert mnt._get(db, mnt.KEY_NOTE) is None and mnt._get(db, mnt.KEY_BY) is None
    finally:
        db.close()


def test_the_screen_is_told_whether_this_person_passes():
    """Ответ о состоянии несёт `passes` — и это половина заслона, а не украшение.

    18.09.2026 админ включил обслуживание и остался снаружи собственного портала.
    Виноват был не заслон: прослойка пускала его честно. Виноват экран — заглушка
    рисовалась всем, у кого режим активен, роли она не спрашивала. Снимать режим
    пришлось из консоли базы, то есть ровно тогда, когда это сложнее всего.

    Право теперь считает ОДНО место — сервер. Прибор держит контракт: поле есть, оно
    булево и оно отвечает на вопрос «пускает ли МЕНЯ».
    """
    import inspect

    from app.routers import maintenance as api
    src = inspect.getsource(api.maintenance_state)
    assert '"passes"' in src
    assert 'key", None) == "admin"' in src


def test_the_stub_hides_from_whoever_passes():
    """Вторая половина того же правила — на экране. Заглушка обязана СПРАШИВАТЬ сервер,
    а не роль из localStorage: второй расчёт одного права однажды разойдётся с первым."""
    from pathlib import Path

    src = Path("/app/../frontend/components/Maintenance.jsx")
    if not src.exists():                      # фронт рядом не всегда (образ бэкенда)
        import pytest
        pytest.skip("фронт недоступен из этого контейнера")
    text = src.read_text(encoding="utf-8")
    assert "state.passes" in text
