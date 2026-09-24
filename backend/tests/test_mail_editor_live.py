# -*- coding: utf-8 -*-
"""«Шаблоны писем» управляют НАСТОЯЩИМИ письмами (аудит 23.09.2026, 5.M1; владелец
24.09.2026: подключить).

До этого правки на экране видели только предпросмотр и «Отправить себе»: живые
отправители собирали письмо своим кодом, а имя отправителя, приставку темы и подпись не
читал никто. Экран обещал то, чего не делал, — худший вид неработающей настройки.

Что проверяется — по одному прибору на каждый вход:
  · имя отправителя, приставка темы и подпись — в ЛЮБОМ письме (одна точка: клиент);
  · правка карточки события — в живом письме сотруднику и площадке;
  · оболочка (тема, заголовок) — в дайджесте.

Настройки стенда снимаются снимком до теста и возвращаются после.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

import app.main  # noqa: F401 — все модели
from app.database import SessionLocal
from app.mail import client as mail
from app.mail import editor, live
from app.models import User
from app.notify import bus, channels, digest, registry
from app.notify.models import NotificationDelivery

KEYS = ("mail_from_name", "mail_subject_prefix", "mail_signature",
        "mail_shell_staff", "mail_shell_pub", "mail_cards_staff", "mail_cards_pub")


@pytest.fixture
def db(monkeypatch):
    s = SessionLocal()
    snap = dict(s.execute(text("SELECT key, value FROM company_settings WHERE key = ANY(:k)"),
                          {"k": list(KEYS)}).all())
    monkeypatch.setattr(mail, "configured", lambda: True)
    monkeypatch.setattr(mail, "config", lambda: mail.MailConfig(
        host="smtp.example.invalid", port=465, user="", password="",
        sender="noreply@example.org", sender_name="ИзОкружения", mode="ssl"))
    # Начинаем с ЧИСТЫХ настроек: иначе проверка «без настроек письмо прежнее» зависела
    # бы от того, что вписано на стенде.
    s.execute(text("DELETE FROM company_settings WHERE key = ANY(:k)"), {"k": list(KEYS)})
    s.commit()
    mail.screen_cache_clear()
    yield s
    s.rollback()
    mail.screen_cache_clear()
    s.execute(text("DELETE FROM company_settings WHERE key = ANY(:k)"), {"k": list(KEYS)})
    for k, v in snap.items():
        s.execute(text("INSERT INTO company_settings (key, value) VALUES (:k, :v)"),
                  {"k": k, "v": v})
    s.commit()
    s.close()


def _set(db, key, value):
    db.execute(text("INSERT INTO company_settings (key, value) VALUES (:k, :v) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"),
               {"k": key, "v": value})
    db.commit()
    mail.screen_cache_clear()


def _capture(monkeypatch):
    got = {}

    def transport(msg):
        got["msg"] = msg
    return got, transport


# ── имя отправителя, приставка темы, подпись ────────────────────────────────

def test_sender_settings_reach_every_letter(db):
    _set(db, "mail_from_name", "Команда Медиаплан")
    _set(db, "mail_subject_prefix", "[SIMB-AD]")
    _set(db, "mail_signature", "С уважением, отдел трафика")
    seen = {}
    mail.send(to="someone@example.org", subject="Проверка", body="текст",
              html="<html><body><p>разметка</p></body></html>",
              transport=lambda m: seen.update(m=m))
    m = seen["m"]
    assert "Команда Медиаплан" in str(m["From"]) or "=?utf-8?" in str(m["From"])
    assert m["Subject"].startswith("[SIMB-AD] "), m["Subject"]
    parts = {p.get_content_type(): p.get_content() for p in m.walk()
             if p.get_content_type() in ("text/plain", "text/html")}
    assert "отдел трафика" in parts["text/plain"]
    assert "отдел трафика" in parts["text/html"]


def test_without_settings_the_letter_is_unchanged(db):
    seen = {}
    mail.send(to="someone@example.org", subject="Проверка", body="текст",
              transport=lambda m: seen.update(m=m))
    assert seen["m"]["Subject"] == "Проверка"


# ── карточка события ────────────────────────────────────────────────────────

def test_a_card_edit_reaches_a_live_staff_letter(db, monkeypatch):
    key = editor.cards(db, editor.STAFF)[0]["key"]
    ev = registry.get(key)
    editor.save_card(db, editor.STAFF, ev.key, {"body": "Новый текст карточки {имя}"})
    db.commit()
    admin = db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
    sent = {}
    monkeypatch.setattr(mail, "send", lambda **kw: sent.update(kw) or "<id>")
    monkeypatch.setattr(channels, "quiet_now", lambda ch, ev: False)
    monkeypatch.setattr(bus, "_channels_for", lambda db, uid, ev: ["mail"])
    # Через шину — так рождается настоящее письмо: слова карточки применяются там, где у
    # события есть данные для подстановок.
    bus.emit(db, ev.key, title="Заголовок события", body="исходный текст",
             link="/deals/1", user_ids=[admin.id])
    db.rollback()
    assert "Новый текст карточки" in sent["html"], "правка карточки не дошла до письма"
    assert "исходный текст" not in sent["html"]
    assert (admin.name or "коллеги") in sent["html"], "подстановка {имя} не заполнена"


def test_a_card_edit_reaches_a_live_publisher_letter(db):
    from app.notify.outward.kinds import by_key
    kind = by_key(editor.cards(db, editor.PUB)[0]["key"])
    editor.save_card(db, editor.PUB, kind.key, {"title": "Свежий материал для {площадка}"})
    db.commit()
    card = live.card(db, editor.PUB, kind.key,
                     {"title": kind.label, "body": "b", "action": "Открыть",
                      "link_abs": "https://lk.test/"},
                     {"площадка": "Сайт-Тест"})
    assert card["title"] == "Свежий материал для Сайт-Тест"


# ── оболочка — в дайджесте ──────────────────────────────────────────────────

def test_the_shell_reaches_the_staff_digest(db, monkeypatch):
    live_q = db.query(NotificationDelivery).filter(
        NotificationDelivery.channel == "digest",
        NotificationDelivery.status == "queued").count()
    if live_q:
        pytest.skip("на стенде живая очередь дайджеста — не трогаем")
    editor.save_shell(db, editor.STAFF, {"headline": "ШАПКА-ТЕСТ {всего}",
                                         "subject": "ТЕМА-ТЕСТ {всего}"})
    db.commit()
    admin = db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
    u = User(email="shell-test@example.org", name="Шапка", hashed_password="x",
             role_id=admin.role_id, is_active=1)
    db.add(u)
    db.commit()
    row = NotificationDelivery(event_key="test_shell", user_id=u.id, channel="digest",
                               status="queued", title="т",
                               created_at=datetime.utcnow() - timedelta(days=2))
    db.add(row)
    db.commit()
    got = {}
    monkeypatch.setattr(channels, "deliver_digest",
                        lambda **kw: got.update(kw) or "sent|")
    try:
        digest.run()
    finally:
        db.query(NotificationDelivery).filter(NotificationDelivery.id == row.id).delete()
        db.query(User).filter(User.id == u.id).delete()
        db.commit()
    assert got.get("subject", "").startswith("ТЕМА-ТЕСТ 1 событие"), got.get("subject")
    assert "ШАПКА-ТЕСТ 1 событие" in got.get("html", "")
