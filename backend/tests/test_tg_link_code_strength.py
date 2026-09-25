# -*- coding: utf-8 -*-
"""Код привязки Телеграма: не подбирается перебором (аудит 23.09.2026, 9.4 / 1.L4).

Код был 24 бита (шесть hex-знаков), жил полчаса, попытки с чата не считались: чужой чат,
угадавший код, получал уведомления сотрудника — с суммами. Теперь 40 бит и счётчик: пять
неверных кодов с одного чата — чат на время перестаёт приниматься, ВЕРНЫЙ код тоже.

Счётчик — В БАЗЕ (ревью 24.09.2026): живой опрос бота идёт кроном раз в минуту новым
процессом, и счётчик в памяти обнулялся бы каждую минуту. Свои записи тест снимает.
"""
from sqlalchemy import text

from app.database import SessionLocal
from app.notify import telegram
from app.routers import cabinet_gateway, notify_settings

CHAT = '-9990001'


def _upd(chat, text_):
    return {"message": {"chat": {"id": chat}, "text": text_}}


def test_code_is_40_bits_and_is_recognised_bare():
    code, _ = telegram.new_link_code()
    assert len(code) == 10 and int(code, 16) >= 0
    assert telegram.parse_start_command(_upd(1, code))[0] == code


def _purge(db):
    db.execute(text("DELETE FROM company_settings WHERE key LIKE :k"), {"k": f"tg_bad:%:{CHAT}"})
    db.commit()


def test_a_chat_guessing_codes_is_cut_off_across_processes():
    db = SessionLocal()
    try:
        for handler in (notify_settings.handle_staff_update, cabinet_gateway.handle_pub_update):
            _purge(db)
            said = []
            for _ in range(telegram.MAX_BAD_CODES):
                handler(db, _upd(CHAT, 'AAAAAAAAAA'), lambda c, t: said.append(t))
            # новый процесс — новая сессия: счётчик обязан это пережить
            db2 = SessionLocal()
            try:
                said.clear()
                handler(db2, _upd(CHAT, 'BBBBBBBBBB'), lambda c, t: said.append(t))
                assert said and 'Слишком много' in said[-1], "блок не пережил новый процесс"
            finally:
                db2.close()
    finally:
        _purge(db)
        db.close()


def test_the_two_bots_count_separately():
    db = SessionLocal()
    try:
        _purge(db)
        for _ in range(telegram.MAX_BAD_CODES):
            telegram.note_bad_code(db, telegram.PUB, CHAT)
        assert telegram.chat_blocked(db, telegram.PUB, CHAT)
        assert not telegram.chat_blocked(db, telegram.STAFF, CHAT)
    finally:
        _purge(db)
        db.close()
