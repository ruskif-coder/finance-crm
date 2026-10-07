# -*- coding: utf-8 -*-
"""Вход: чужой не запирает учётку, успешные входы не съедают лимит адреса.

Внешний аудит 06.10.2026 показал на стенде (и код это подтверждает):

  1. блокировка стояла на ОДНОМ email, а проверялась ДО пароля и копилась даже для
     несуществующего адреса. Пять неверных паролей на адрес администратора запирали его
     на 15 минут — и так сколько угодно раз, не зная ни пароля, ни самой учётки;
  2. лимит адреса считал и успешные входы: офис за одним внешним адресом, где человек
     открывает систему весь день в нескольких вкладках, запирал сам себя на 21-м входе.

Теперь счётчик ведётся по паре «почта + адрес»: перебирающий запирает сам себя, а
хозяин учётки с другого адреса входит. Админская разблокировка (`_clear_login_attempts`
по почте, её зовут `users.py` и подтверждение пароля) снимает замки всех пар этой почты.

Тест пишет только свои строки: у настоящей учётки снимок счётчиков возвращается как был.
"""
import types
import uuid

import pytest
from fastapi import HTTPException

from app.models import LoginAttempt, User
from app.routers import auth

IP_A, IP_B = "203.0.113.10", "203.0.113.20"
GOOD = "правильный-пароль-теста"


def _req(ip):
    return types.SimpleNamespace(headers={"x-forwarded-for": ip},
                                 client=types.SimpleNamespace(host="10.0.0.1"))


def _form(email, pw):
    return types.SimpleNamespace(username=email, password=pw)


def _try(db, email, pw, ip):
    """Код ответа входа: 200 при успехе, иначе статус исключения."""
    try:
        auth.login(_req(ip), _form(email, pw), db)
        return 200
    except HTTPException as e:
        return e.status_code


def _rows_of(db, email):
    return (db.query(LoginAttempt)
            .filter((LoginAttempt.email == email) | (LoginAttempt.email.like(email + "|%")))
            .all())


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    auth._ip_attempts.clear()
    # журнал действий не пополняем: в нём остались бы строки о входах настоящей учётки
    monkeypatch.setattr("app.audit.log_action", lambda *a, **k: None)
    monkeypatch.setattr(auth, "verify_password", lambda p, h: p == GOOD)
    yield
    auth._ip_attempts.clear()


@pytest.fixture
def ghost(db):
    """Несуществующая почта: чем пользуется нападающий. Снимаем только свои строки."""
    email = f"zz-lock-{uuid.uuid4().hex[:10]}@example.test"
    yield email
    for r in _rows_of(db, email):
        db.delete(r)
    db.commit()


@pytest.fixture
def real_user(db):
    """Настоящая активная учётка стенда; счётчики входа возвращаются как были."""
    u = db.query(User).filter(User.is_active == 1).order_by(User.id).first()
    email = auth._norm_email(u.email)
    snap = {r.email: (r.failed_count, r.locked_until) for r in _rows_of(db, email)}
    yield email
    for r in _rows_of(db, email):
        if r.email in snap:
            r.failed_count, r.locked_until = snap[r.email]
        else:
            db.delete(r)
    db.commit()


def test_stranger_cannot_lock_an_account_by_email_alone(db, ghost):
    for _ in range(auth.MAX_LOGIN_ATTEMPTS):
        assert _try(db, ghost, "мимо", IP_A) == 400
    assert _try(db, ghost, "мимо", IP_A) == 429, "перебирающий заперт"
    # другой адрес замка не видит: вход идёт дальше и отвечает как на неверный пароль
    assert _try(db, ghost, "мимо", IP_B) == 400, "чужой адрес запер бы любую учётку"


def test_the_owner_gets_in_from_another_address_while_the_guesser_is_locked(db, real_user):
    for _ in range(auth.MAX_LOGIN_ATTEMPTS):
        assert _try(db, real_user, "мимо", IP_A) == 400
    assert _try(db, real_user, GOOD, IP_A) == 429, "тот, кто перебирал, заперт и с верным паролем"
    assert _try(db, real_user, GOOD, IP_B) == 200, "хозяина это не касается"


def test_successful_logins_do_not_spend_the_address_limit(db, real_user):
    for i in range(auth.MAX_LOGIN_PER_IP + 5):
        assert _try(db, real_user, GOOD, IP_A) == 200, f"вход №{i + 1} верным паролем отвергнут"


def test_failures_still_spend_the_address_limit(db, ghost):
    """Лимит адреса остаётся защитой от перебора одного пароля по многим почтам."""
    codes = [_try(db, f"{i}-{ghost}", "мимо", IP_A) for i in range(auth.MAX_LOGIN_PER_IP + 1)]
    assert codes[:auth.MAX_LOGIN_PER_IP] == [400] * auth.MAX_LOGIN_PER_IP
    assert codes[-1] == 429
    for i in range(auth.MAX_LOGIN_PER_IP + 1):
        for r in _rows_of(db, f"{i}-{ghost}"):
            db.delete(r)
    db.commit()


def test_admin_unlock_by_email_frees_every_pair_of_that_email(db, ghost):
    for _ in range(auth.MAX_LOGIN_ATTEMPTS):
        _try(db, ghost, "мимо", IP_A)
    assert _try(db, ghost, "мимо", IP_A) == 429
    auth._clear_login_attempts(db, ghost)       # так зовёт users.py при смене пароля/почты
    auth._ip_attempts.clear()
    assert _try(db, ghost, "мимо", IP_A) == 400, "замок пары остался после разблокировки"


def test_unlock_does_not_touch_other_emails(db, ghost):
    other = "x" + ghost
    for _ in range(auth.MAX_LOGIN_ATTEMPTS):
        _try(db, other, "мимо", IP_A)
    auth._clear_login_attempts(db, ghost)
    auth._ip_attempts.clear()
    assert _try(db, other, "мимо", IP_A) == 429, "разблокировка одной почты сняла замок соседней"
    for r in _rows_of(db, other):
        db.delete(r)
    db.commit()


def test_confirm_password_keeps_one_counter_per_email(db, ghost):
    """Подтверждение пароля (`/verify-password`) считает по почте, а не по паре: у держателя
    токена нет «другого адреса», с которого можно начать счёт заново."""
    for _ in range(auth.MAX_LOGIN_ATTEMPTS):
        auth._register_failed_login(db, ghost)
    with pytest.raises(HTTPException) as e:
        auth._check_login_lockout(db, ghost)
    assert e.value.status_code == 429


def test_unlock_with_underscore_does_not_free_a_lookalike_email(db):
    """`_` в LIKE значит «любой знак»: без экранирования разблокировка `a_b` снимала
    бы замок у чужой `aXb`."""
    tag = uuid.uuid4().hex[:8]
    # нижний регистр: вход нормализует почту, и строку блокировки иначе не найти при уборке
    mine, lookalike = f"zz{tag}_b@example.test", f"zz{tag}xb@example.test"
    for _ in range(auth.MAX_LOGIN_ATTEMPTS):
        _try(db, lookalike, "мимо", IP_A)
    auth._clear_login_attempts(db, mine)
    auth._ip_attempts.clear()
    assert _try(db, lookalike, "мимо", IP_A) == 429
    for r in _rows_of(db, lookalike):
        db.delete(r)
    db.commit()


def test_a_very_long_username_is_a_wrong_password_not_a_server_error(db):
    """Колонка 255 знаков; имя из запроса длиннее раньше давало 500 на неудачном входе."""
    long_name = "a" * 400 + "@example.test"
    assert _try(db, long_name, "мимо", IP_A) == 400
    for r in db.query(LoginAttempt).filter(LoginAttempt.email.like("a" * 100 + "%")).all():
        db.delete(r)
    db.commit()


def test_alternating_wrong_and_right_logins_cannot_pump_the_address_limit(db, real_user, ghost):
    """Возврат попытки после верного входа не должен давать перебирать чужие учётки с
    одного адреса бесконечно: неудачи остаются в окне, и после 20 неудач закрыто всё."""
    codes = []
    for i in range(auth.MAX_LOGIN_PER_IP + 5):
        codes.append(_try(db, f"{i}-{ghost}", "мимо", IP_A))
        codes.append(_try(db, real_user, GOOD, IP_A))
    assert codes.count(400) == auth.MAX_LOGIN_PER_IP, "неудач прошло больше лимита адреса"
    assert codes[-1] == 429 and codes[-2] == 429
    for i in range(auth.MAX_LOGIN_PER_IP + 5):
        for r in _rows_of(db, f"{i}-{ghost}"):
            db.delete(r)
    db.commit()


# ── общий потолок на почту (решение владельца 07.10.2026) ────────────────────
# Замок на пару «почта + адрес» оставлял перебор по одной почте с многих адресов почти без
# предела (около 5 попыток на КАЖДЫЙ адрес). Владелец выбрал жёсткий потолок: 20 неудач на
# почту с любых адресов в сумме — и отказ на час, в том числе верному паролю. Цена известна:
# известную почту можно запереть на час; снимает администратор (`_clear_login_attempts`).

def _fail_from_many_addresses(db, email, total):
    """`total` неверных входов, разложенных по адресам так, чтобы замок пары (5) не сработал раньше."""
    done = 0
    for n in range(1, 100):
        for _ in range(auth.MAX_LOGIN_ATTEMPTS):
            if done == total:
                return
            assert _try(db, email, "мимо", f"203.0.113.{100 + n}") == 400
            done += 1


def test_twenty_failures_from_many_addresses_lock_the_email_for_an_hour(db, real_user):
    _fail_from_many_addresses(db, real_user, auth.MAX_LOGIN_PER_EMAIL)
    auth._ip_attempts.clear()
    assert _try(db, real_user, GOOD, "198.51.100.77") == 429, "верный пароль с нового адреса прошёл"
    row = db.query(LoginAttempt).filter(LoginAttempt.email == f"{real_user}|*").one()
    left = (row.locked_until - __import__("datetime").datetime.utcnow()).total_seconds() / 60
    assert 55 < left <= 60, f"срок отказа {left:.0f} мин, ждали около часа"


def test_nineteen_failures_do_not_lock_the_email(db, real_user):
    _fail_from_many_addresses(db, real_user, auth.MAX_LOGIN_PER_EMAIL - 1)
    auth._ip_attempts.clear()
    assert _try(db, real_user, GOOD, "198.51.100.78") == 200


def test_failures_older_than_the_window_are_forgotten(db, ghost):
    import datetime
    _try(db, ghost, "мимо", "198.51.100.79")
    row = db.query(LoginAttempt).filter(LoginAttempt.email == f"{ghost}|*").one()
    row.failed_count = auth.MAX_LOGIN_PER_EMAIL - 1
    row.updated_at = datetime.datetime.utcnow() - datetime.timedelta(minutes=auth.EMAIL_LOCKOUT_MINUTES + 5)
    db.commit()
    auth._ip_attempts.clear()
    assert _try(db, ghost, "мимо", "198.51.100.80") == 400, "давние неудачи довели до замка"
    db.expire_all()
    row = db.query(LoginAttempt).filter(LoginAttempt.email == f"{ghost}|*").one()
    assert row.failed_count == 1 and row.locked_until is None


def test_admin_unlock_frees_the_email_wide_lock(db, ghost):
    _fail_from_many_addresses(db, ghost, auth.MAX_LOGIN_PER_EMAIL)
    auth._ip_attempts.clear()
    assert _try(db, ghost, "мимо", "198.51.100.81") == 429
    auth._clear_login_attempts(db, ghost)
    auth._ip_attempts.clear()
    assert _try(db, ghost, "мимо", "198.51.100.82") == 400


def test_a_right_password_resets_the_email_wide_counter(db, real_user):
    _fail_from_many_addresses(db, real_user, 10)
    auth._ip_attempts.clear()
    assert _try(db, real_user, GOOD, "198.51.100.83") == 200
    db.expire_all()
    row = db.query(LoginAttempt).filter(LoginAttempt.email == f"{real_user}|*").one()
    assert row.failed_count == 0


def test_email_wide_counter_does_not_touch_the_password_confirmation_counter(db, ghost):
    """`/verify-password` и цепочки операций считают по «голой» почте со своими порогами (5/15 мин)."""
    _fail_from_many_addresses(db, ghost, auth.MAX_LOGIN_PER_EMAIL)
    auth._check_login_lockout(db, ghost)     # не должен бросить: голый ключ не тронут
