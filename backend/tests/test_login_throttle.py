# -*- coding: utf-8 -*-
"""Троттлинг входа: адрес берётся из доверенного звена, а счётчик не растёт бесконечно.

Оба свойства невидимы снаружи. Обход лимита не оставляет следа в логах — запросы
выглядят как приходящие с разных адресов; рост памяти не виден до отказа контейнера.
Поэтому гейт, а не заметка.

История. Пентест 18.07.2026 добавил per-IP лимит поверх локаута по email: локаут один
только по почте не мешает перебору одного пароля по многим учёткам. Разбор внешнего
аудита 11.09.2026 нашёл в этой защите две дыры сразу:

  1. адрес брался из ПЕРВОГО элемента `X-Forwarded-For`, а его пишет клиент. Подставив
     свой заголовок, любой получал новый счётчик на каждую попытку;
  2. ключом словаря `_ip_attempts` служило ровно это подставляемое значение, и ключи
     не удалялись никогда — значит неаутентифицированный запрос наращивал память
     процесса без предела, при `mem_limit: 512m`.

Вторая дыра опаснее первой и в самом аудите названа не была.
"""
import time
import types

import pytest

from app.routers import auth


def _req(xff=None, peer="10.0.0.1"):
    """Минимальный дублёр запроса: троттлингу нужны только заголовки и сокет."""
    headers = {"x-forwarded-for": xff} if xff is not None else {}
    return types.SimpleNamespace(
        headers=headers, client=types.SimpleNamespace(host=peer))


@pytest.fixture(autouse=True)
def _clean():
    """Словарь живёт в модуле — чистим до и после, иначе тесты видят чужие попытки."""
    auth._ip_attempts.clear()
    yield
    auth._ip_attempts.clear()


# ── откуда берётся адрес ─────────────────────────────────────────────────────

def test_takes_the_last_hop_not_the_client_supplied_first():
    """Клиент прислал свой адрес, Caddy дописал настоящий справа — берём правый."""
    assert auth.client_ip(_req("1.2.3.4, 203.0.113.9")) == "203.0.113.9"


def test_spoofed_header_alone_does_not_become_the_key():
    """Единственное значение подделать можно — но только когда прокси нет вовсе.

    За Caddy такого не бывает: он дописывает увиденный адрес всегда. Тест закрепляет
    именно правило «правый», чтобы подделка слева не давала нового счётчика.
    """
    spoofed = "9.9.9.9, 203.0.113.9"
    for _ in range(auth.MAX_LOGIN_PER_IP):
        auth._check_ip_rate_limit(auth.client_ip(_req(spoofed)))
    # 20 попыток выбраны, счётчик у настоящего адреса, а не у подставленного
    assert len(auth._ip_attempts) == 1
    assert "203.0.113.9" in auth._ip_attempts
    with pytest.raises(Exception):
        auth._check_ip_rate_limit(auth.client_ip(_req(spoofed)))


def test_falls_back_to_the_socket_when_header_is_absent_or_empty():
    assert auth.client_ip(_req(None, peer="10.0.0.7")) == "10.0.0.7"
    assert auth.client_ip(_req("", peer="10.0.0.7")) == "10.0.0.7"
    assert auth.client_ip(_req(" , ", peer="10.0.0.7")) == "10.0.0.7"


# ── словарь не растёт бесконечно ─────────────────────────────────────────────

def test_tracked_addresses_stay_bounded():
    """Много разных адресов НЕ дают неограниченного роста.

    Именно так выглядит атака: каждый запрос с новым значением заголовка. Держим
    потолок с запасом на переполнение — важно, что число конечно, а не точная граница.
    """
    for i in range(auth.MAX_TRACKED_IPS + 500):
        auth._check_ip_rate_limit(f"198.51.100.{i}")
    assert len(auth._ip_attempts) <= auth.MAX_TRACKED_IPS + 1


def test_stale_addresses_are_forgotten():
    """Протухшее окно уносит с собой и ключ, а не оставляет пустой список."""
    old = time.time() - auth.LOGIN_IP_WINDOW_SECONDS - 60
    for i in range(auth.MAX_TRACKED_IPS + 10):
        auth._ip_attempts[f"198.51.100.{i}"] = [old]
    auth._prune_ip_attempts(time.time())
    assert auth._ip_attempts == {}


def test_a_live_address_keeps_its_counter_through_pruning():
    """Уборка не должна снимать защиту с того, кто стучится прямо сейчас."""
    now = time.time()
    auth._ip_attempts["203.0.113.9"] = [now, now, now]
    old = now - auth.LOGIN_IP_WINDOW_SECONDS - 60
    for i in range(50):
        auth._ip_attempts[f"198.51.100.{i}"] = [old]
    auth._prune_ip_attempts(now)
    assert auth._ip_attempts.get("203.0.113.9") == [now, now, now]


def test_limit_still_works_after_the_dictionary_overflowed():
    """Главное свойство: переполнение не превращается в снятие лимита."""
    for i in range(auth.MAX_TRACKED_IPS + 100):
        auth._check_ip_rate_limit(f"198.51.100.{i}")
    victim = "203.0.113.9"
    for _ in range(auth.MAX_LOGIN_PER_IP):
        auth._check_ip_rate_limit(victim)
    with pytest.raises(Exception):
        auth._check_ip_rate_limit(victim)
