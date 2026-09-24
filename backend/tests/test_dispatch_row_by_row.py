# -*- coding: utf-8 -*-
"""Досылка уведомлений сотрудникам — построчно (аудит 23.09.2026, 5.M5 и 5.L5).

5.M5. Досылка фиксировала результат ОДИН раз в конце. Исключение посреди — и уже
отправленные строки оставались `queued`: каждый час те же письма уходили снова, до 48
часов. Самый доступный спусковой крючок — строка события, убранного из реестра: проверка
тихих часов читает у события `locked` и падала на пустом.

5.L5. Отключённому сотруднику досылка отправляла накопленное — человек ушёл, а письма
про сделки продолжают идти ему.

Отправка подменена; строки очереди и учётки — настоящие, на стенде, и снимаются за собой.
"""
from types import SimpleNamespace

import pytest

import app.main  # noqa: F401 — все модели
from app.database import SessionLocal
from app.models import User
from app.notify import channels, dispatch
from app.notify.models import NotificationDelivery

EMAILS = ("dispatch-live@example.invalid", "dispatch-gone@example.invalid")


@pytest.fixture
def world(monkeypatch):
    s = SessionLocal()
    # Досылка берёт ВСЮ очередь стенда. Живые строки подставная отправка отметила бы
    # «отправленными» — поэтому при живой очереди прибор не запускается вовсе.
    live_queue = s.query(NotificationDelivery).filter(
        NotificationDelivery.status == "queued",
        NotificationDelivery.channel.in_(("tg", "mail"))).count()
    if live_queue:
        s.close()
        pytest.skip(f"на стенде живая очередь досылки ({live_queue}) — не трогаем")
    admin = s.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
    users = []
    for email, active in zip(EMAILS, (1, 0)):
        u = User(email=email, name="Досылка", hashed_password="x",
                 role_id=admin.role_id, is_active=active)
        s.add(u)
        users.append(u)
    s.commit()
    live, gone = users

    def row(user, key):
        r = NotificationDelivery(event_key=key, user_id=user.id, channel="mail",
                                 status="queued", title="т")
        s.add(r)
        return r

    rows = [row(live, "test_disp_ok"), row(live, "test_disp_ok"),
            row(live, "test_disp_ok"), row(live, "test_disp_removed"),
            row(gone, "test_disp_ok")]
    s.commit()
    ids = [r.id for r in rows]

    calls = []

    def deliver(db, user_id, ev, *a, **kw):
        if ev is not None and ev.locked is None:
            raise AttributeError("событие без полей")
        calls.append(user_id)
        if len(calls) == 3:
            raise RuntimeError("сбой на третьей строке")
        return "sent|"

    ok_event = SimpleNamespace(locked=False, key="test_disp_ok")
    monkeypatch.setattr(dispatch.registry, "get",
                        lambda key: ok_event if key == "test_disp_ok" else None)
    monkeypatch.setattr(channels, "deliver_mail", deliver)
    yield SimpleNamespace(ids=ids, calls=calls, live=live, gone=gone)
    s.query(NotificationDelivery).filter(NotificationDelivery.id.in_(ids)).delete(
        synchronize_session=False)
    s.query(User).filter(User.email.in_(EMAILS)).delete(synchronize_session=False)
    s.commit()
    s.close()


def _status(ids):
    s = SessionLocal()
    try:
        return {r.id: (r.status, r.suppress_reason) for r in s.query(NotificationDelivery)
                .filter(NotificationDelivery.id.in_(ids)).all()}
    finally:
        s.close()


def test_rows_are_saved_one_by_one_and_bad_rows_do_not_stop_the_run(world):
    dispatch.flush()
    st = _status(world.ids)
    first, second, third, removed, gone = world.ids
    assert st[first][0] == "sent" and st[second][0] == "sent", (
        f"отправленные остались в очереди — уйдут снова через час: {st}")
    assert st[third][0] != "sent"
    assert st[removed][0] == "suppressed", "строка убранного события уронила прогон"
    assert st[gone][0] == "suppressed", "отключённому сотруднику ушло накопленное"
    assert world.gone.id not in world.calls
