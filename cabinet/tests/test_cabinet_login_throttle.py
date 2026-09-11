# -*- coding: utf-8 -*-
"""Вход в кабинет: перебор ограничен И по учётке, И по адресу.

ЗАЧЕМ. Локаут по одной почте не мешает перебору ОДНОГО пароля по многим учёткам —
именно поэтому ядру после пентеста 18.07.2026 добавили счётчик по адресу. Внешний
контур остался без него до 11.09.2026 (F1-03 внешнего аудита), а перебор опаснее как
раз здесь: адрес входа известен площадке, учёток у кабинета немного, и ходят туда не
наши сотрудники.

Две вещи, которые ломаются молча и потому закреплены тестом:

  1. **адрес берётся из последнего звена `X-Forwarded-For`.** Всё, что прислал клиент,
     стоит СЛЕВА; правее дописывает Caddy — то, что он видел на сокете. Брали бы левое —
     подделка заголовка давала бы новый счётчик на каждую попытку, и лимита нет;
  2. **словарь попыток не растёт без предела.** Ключ приходит снаружи, и без потолка
     неаутентифицированный запрос наращивает память процесса — при `mem_limit: 512m`
     это отказ в обслуживании, а не неудобство.

Живьём через Caddy проверено 11.09.2026: 21-я попытка — 429, 22-я с подделанным
заголовком — тоже 429.
"""
import os
import sys
import time
import types

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import main as cab_main          # noqa: E402


def _req(xff=None, peer="10.0.0.1"):
    headers = {"x-forwarded-for": xff} if xff is not None else {}
    return types.SimpleNamespace(
        headers=headers, client=types.SimpleNamespace(host=peer))


@pytest.fixture(autouse=True)
def _clean():
    cab_main._ip_attempts.clear()
    yield
    cab_main._ip_attempts.clear()


# ── откуда берётся адрес ─────────────────────────────────────────────────────

def test_takes_the_last_hop():
    assert cab_main.client_ip(_req("1.2.3.4, 203.0.113.9")) == "203.0.113.9"


def test_spoofed_left_part_does_not_create_a_second_counter():
    spoofed = "9.9.9.9, 203.0.113.9"
    for _ in range(cab_main.MAX_LOGIN_PER_IP):
        cab_main._check_ip_rate_limit(cab_main.client_ip(_req(spoofed)))
    assert list(cab_main._ip_attempts) == ["203.0.113.9"]
    with pytest.raises(HTTPException) as e:
        cab_main._check_ip_rate_limit(cab_main.client_ip(_req(spoofed)))
    assert e.value.status_code == 429


def test_falls_back_to_the_socket():
    assert cab_main.client_ip(_req(None, peer="10.0.0.7")) == "10.0.0.7"
    assert cab_main.client_ip(_req(" , ", peer="10.0.0.7")) == "10.0.0.7"
    assert cab_main.client_ip(None) == "unknown"


# ── словарь не растёт бесконечно ─────────────────────────────────────────────

def test_tracked_addresses_stay_bounded():
    for i in range(cab_main.MAX_TRACKED_IPS + 300):
        cab_main._check_ip_rate_limit(f"198.51.100.{i}")
    assert len(cab_main._ip_attempts) <= cab_main.MAX_TRACKED_IPS + 1


def test_limit_survives_the_overflow():
    """Главное свойство: переполнение не превращается в снятие лимита."""
    for i in range(cab_main.MAX_TRACKED_IPS + 100):
        cab_main._check_ip_rate_limit(f"198.51.100.{i}")
    victim = "203.0.113.9"
    for _ in range(cab_main.MAX_LOGIN_PER_IP):
        cab_main._check_ip_rate_limit(victim)
    with pytest.raises(HTTPException):
        cab_main._check_ip_rate_limit(victim)


def test_stale_addresses_are_forgotten():
    old = time.time() - cab_main.LOGIN_IP_WINDOW_SECONDS - 60
    for i in range(50):
        cab_main._ip_attempts[f"198.51.100.{i}"] = [old]
    cab_main._prune_ip_attempts(time.time())
    assert cab_main._ip_attempts == {}
