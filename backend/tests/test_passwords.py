# -*- coding: utf-8 -*-
"""Совместимость хеширования паролей при уходе от passlib.

Замена библиотеки хеширования — единственная правка волны 1, у которой цена
ошибки «никто не может войти, включая владельца». Поэтому проверяется не
«новый код работает», а «новый код понимает то, что записала старая библиотека,
и наоборот».

Перекрёстные тесты держатся, пока passlib ещё установлен. Когда его уберут из
requirements, они сами пропустятся (skip), а прямые тесты останутся.
"""
import pytest

from app.passwords import MAX_BCRYPT_BYTES, hash_password, verify_password

try:
    from passlib.context import CryptContext
    _legacy = CryptContext(schemes=["bcrypt"], deprecated="auto")
except Exception:                                        # pragma: no cover
    _legacy = None

legacy_only = pytest.mark.skipif(_legacy is None, reason="passlib уже удалён")


def test_hash_looks_like_what_passlib_wrote():
    """Формат тот же: все живые хеши в базе начинаются с $2b$."""
    assert hash_password("Пароль12345").startswith("$2b$")


def test_roundtrip():
    h = hash_password("Пароль12345")
    assert verify_password("Пароль12345", h)
    assert not verify_password("Пароль1234", h)


def test_two_hashes_of_one_password_differ():
    """Соль случайная — иначе одинаковые пароли видно по базе."""
    assert hash_password("одинаковый") != hash_password("одинаковый")


@legacy_only
def test_new_code_verifies_a_passlib_hash():
    """Главный тест: уже сохранённые пароли продолжают подходить."""
    h = _legacy.hash("Старый Пароль 123")
    assert verify_password("Старый Пароль 123", h)
    assert not verify_password("не тот", h)


@legacy_only
def test_passlib_verifies_a_new_hash():
    """Обратная сторона: откат на passlib не потребует перехеширования."""
    h = hash_password("Новый Пароль 123")
    assert _legacy.verify("Новый Пароль 123", h)


@legacy_only
def test_long_password_is_truncated_the_same_way():
    """passlib обрезал до 72 БАЙТ. Обрезать иначе — сломать длинные пароли."""
    base = "Ж" * 40                      # 80 байт в utf-8
    assert len(base.encode()) > MAX_BCRYPT_BYTES
    h = _legacy.hash(base)
    assert verify_password(base, h)
    # то, что отличается только за границей 72 байт, обязано совпасть — так было
    assert verify_password(base + "хвост", h)


def test_broken_hash_is_false_not_an_exception():
    """Вход прогоняет проверку и для несуществующего юзера — исключение здесь
    вернуло бы timing-оракул, по которому перечисляют учётки."""
    for bad in ("", "не хеш", "$2b$обрезанный", None):
        assert verify_password("что угодно", bad) is False
