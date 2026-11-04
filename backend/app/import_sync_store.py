# -*- coding: utf-8 -*-
"""Сессии двухшагового импорта операций (preview → apply) — в файлах, а не в памяти процесса.

Зачем (03.11.2026): бэкенд запускается несколькими процессами (`--workers`), и запросы одного человека попадают в
разные. Словарь в памяти видел бы только тот процесс, что разбирал файл: «Применить», доставшееся соседу, отвечало бы
«сессия импорта истекла» на только что разобранный файл. Каталог — внутри контейнера, общий для всех его процессов;
пересоздание контейнера сессии теряет, как теряло и прежнее хранение в памяти.

Снаружи — словарь: `store[id] = {...}`, `store.get(id)`, `store.pop(id)`, `store.items()`, `len(store)`. Значение —
копия: правка вложенного словаря без присваивания обратно не сохраняется. Файлы пишет только этот модуль (pickle своих
же данных), запись атомарна — через временный файл и `os.replace`.
"""
import os
import pickle
import tempfile

DIR = os.path.join(tempfile.gettempdir(), "finance_import_sync")
_HEX = set("0123456789abcdef")


def _path(key: str) -> str:
    # Ключ приходит из запроса: только uuid4().hex, иначе выход из каталога через «../».
    if not key or len(key) > 64 or not set(key) <= _HEX:
        raise KeyError(key)
    return os.path.join(DIR, key + ".pkl")


class FileStore:
    def __init__(self):
        os.makedirs(DIR, exist_ok=True)

    def __setitem__(self, key: str, value: dict) -> None:
        fd, tmp = tempfile.mkstemp(dir=DIR, suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            pickle.dump(value, f)
        os.replace(tmp, _path(key))

    def __getitem__(self, key: str) -> dict:
        try:
            with open(_path(key), "rb") as f:
                return pickle.load(f)
        except FileNotFoundError:
            raise KeyError(key) from None

    def __delitem__(self, key: str) -> None:
        try:
            os.remove(_path(key))
        except FileNotFoundError:
            raise KeyError(key) from None

    def __contains__(self, key: str) -> bool:
        try:
            return os.path.exists(_path(key))
        except KeyError:
            return False

    def get(self, key: str, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key: str, default=None):
        value = self.get(key, default)
        try:
            del self[key]
        except KeyError:
            pass
        return value

    def keys(self) -> list:
        return [n[:-4] for n in os.listdir(DIR) if n.endswith(".pkl")]

    def items(self) -> list:
        out = []
        for k in self.keys():
            v = self.get(k)
            if v is not None:                      # соседний процесс мог удалить файл между listdir и чтением
                out.append((k, v))
        return out

    def __len__(self) -> int:
        return len(self.keys())
