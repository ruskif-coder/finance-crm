# -*- coding: utf-8 -*-
"""Дайджест сотрудникам: один плохой адрес не останавливает всех (аудит 23.09.2026,
5.M4 и 5.L5).

5.M4. Строки получателя без годного адреса не помечались — оставались `queued` навсегда.
Выборка берёт первые 500 строк очереди по времени, и когда таких застрявших набиралось
500, дайджест не уходил НИКОМУ. Адрес-переадресацию при этом можно было сохранить любой
строкой — отсюда и берутся плохие адреса.

5.L5. Отключённому сотруднику дайджест уходил дальше.

Отправка подменена; строки очереди и учётки — настоящие, снимаются за собой.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import app.main  # noqa: F401 — все модели
from app.database import SessionLocal
from app.models import User
from app.notify import channels, digest
from app.notify.models import NotificationDelivery, UserNotificationChannels
from app.routers import notify_settings

EMAILS = ("digest-good@example.org", "digest-bad@example.org", "digest-gone@example.org")


@pytest.fixture
def world(monkeypatch):
    s = SessionLocal()
    live = s.query(NotificationDelivery).filter(
        NotificationDelivery.channel == "digest",
        NotificationDelivery.status == "queued").count()
    if live:
        s.close()
        pytest.skip(f"на стенде живая очередь дайджеста ({live}) — не трогаем")
    admin = s.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
    users = []
    for email, active in zip(EMAILS, (1, 1, 0)):
        u = User(email=email, name="Дайджест", hashed_password="x",
                 role_id=admin.role_id, is_active=active)
        s.add(u)
        users.append(u)
    s.commit()
    good, bad, gone = users
    # Плохой адрес — переадресацией, как это и случается на деле.
    s.add(UserNotificationChannels(user_id=bad.id, mail_override="не адрес"))
    old = datetime.utcnow() - timedelta(days=2)
    rows = [NotificationDelivery(event_key="test_digest", user_id=u.id, channel="digest",
                                 status="queued", title="т", created_at=old)
            for u in (good, bad, gone)]
    s.add_all(rows)
    s.commit()
    ids = {u.email: r.id for u, r in zip(users, rows)}

    sent = []
    monkeypatch.setattr(digest.mail, "configured", lambda: True)
    monkeypatch.setattr(channels, "deliver_digest",
                        lambda to, **kw: sent.append(to) or "sent|")
    yield SimpleNamespace(ids=ids, sent=sent)
    all_ids = list(ids.values())
    s.query(NotificationDelivery).filter(NotificationDelivery.id.in_(all_ids)).delete(
        synchronize_session=False)
    s.query(UserNotificationChannels).filter(
        UserNotificationChannels.user_id.in_([u.id for u in users])).delete(
        synchronize_session=False)
    s.query(User).filter(User.email.in_(EMAILS)).delete(synchronize_session=False)
    s.commit()
    s.close()


def test_a_bad_address_is_marked_and_the_rest_are_delivered(world):
    digest.run()
    s = SessionLocal()
    try:
        st = {r.id: (r.status, r.error, r.suppress_reason)
              for r in s.query(NotificationDelivery)
              .filter(NotificationDelivery.id.in_(list(world.ids.values()))).all()}
    finally:
        s.close()
    assert st[world.ids[EMAILS[0]]][0] == "sent"
    bad = st[world.ids[EMAILS[1]]]
    assert bad[0] != "queued", "строка без адреса осталась в очереди навсегда"
    gone = st[world.ids[EMAILS[2]]]
    assert gone[0] == "suppressed", "отключённому сотруднику ушёл дайджест"
    assert world.sent == [EMAILS[0]]


def test_a_bad_override_address_is_refused_when_saved():
    with pytest.raises(ValidationError):
        notify_settings.ChannelsIn(mail_override="не адрес")
    assert notify_settings.ChannelsIn(mail_override="").mail_override in ("", None)
    assert notify_settings.ChannelsIn(mail_override="a.b@example.org").mail_override
