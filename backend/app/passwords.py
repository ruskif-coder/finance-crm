# -*- coding: utf-8 -*-
"""Хеширование паролей — напрямую bcrypt, без passlib.

Почему ушли от passlib (2026-08-23): последний его релиз — 2020 год, с
`bcrypt>=4.1` он несовместим и печатает `(trapped) error reading bcrypt version`
при каждом старте контейнера, а внутри импортирует модуль `crypt`, удалённый в
Python 3.13. То есть библиотека одновременно шумит в логах и держит нас на
Python 3.11.

Формат хеша не меняется. passlib для схемы bcrypt писал ровно то же, что пишет
сам bcrypt: `$2b$<cost>$<salt+digest>`. Проверено на живых данных — все хеши и
на стенде, и на проде начинаются с `$2b$`, а перекрёстная проверка
(passlib хеширует → bcrypt сверяет, и наоборот) закреплена тестом
`tests/test_passwords.py`. Перехеширование не требуется, вход не ломается.
"""
import bcrypt

# bcrypt читает не больше 72 байт пароля — это свойство самого алгоритма, а не
# нашей реализации. passlib молча обрезал до 72 байт, и мы обязаны обрезать так
# же, иначе длинный пароль перестанет подходить к уже сохранённому хешу.
# Обрезаем именно БАЙТЫ, а не символы: passlib делал так же, и bcrypt всё равно
# работает с байтами.
MAX_BCRYPT_BYTES = 72


def _prepare(password: str) -> bytes:
    return (password or "").encode("utf-8")[:MAX_BCRYPT_BYTES]


def hash_password(password: str) -> str:
    """Хеш пароля в формате `$2b$…` — тот же, что писал passlib."""
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """Совпал ли пароль. Битый или пустой хеш — False, а не исключение.

    Тихий False важен для входа: `login` прогоняет проверку даже для
    несуществующего пользователя, чтобы время ответа не выдавало, заведена
    учётка или нет. Исключение здесь вернуло бы этот timing-оракул обратно.
    """
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_prepare(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
