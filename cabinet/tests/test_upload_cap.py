# -*- coding: utf-8 -*-
"""Кабинет не читает в память файл больше предела (аудит 23.09.2026, 1.M2).

Медиакит, снимок к заявке и файл к доработке читались целиком (`await file.read()`),
и только потом ядро проверяло размер. Учётка площадки, прислав сотни мегабайт, роняла
процесс кабинета по памяти (лимит контейнера 512 МБ) — повторяемо. Теперь чтение
порциями и отказ 413 на первой порции сверх предела.
"""
import asyncio
import io

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app import main


class Counting(io.BytesIO):
    """Файл, который считает, сколько из него прочитали."""
    def __init__(self, size):
        super().__init__(b"x" * size)
        self.taken = 0

    def read(self, n=-1):
        chunk = super().read(n)
        self.taken += len(chunk)
        return chunk


def test_small_file_is_read_whole():
    f = UploadFile(file=io.BytesIO(b"abc"), filename="a.png")
    assert asyncio.run(main.read_capped(f, 10)) == b"abc"


def test_oversized_file_is_refused_without_reading_it_all():
    raw = Counting(5 * 1024 * 1024)
    f = UploadFile(file=raw, filename="big.pdf")
    with pytest.raises(HTTPException) as e:
        asyncio.run(main.read_capped(f, 1024 * 1024))
    assert e.value.status_code == 413
    assert raw.taken <= 2 * 1024 * 1024 + main.CHUNK, "файл прочитан целиком"


def test_every_upload_goes_through_the_cap():
    src = io.open(main.__file__, encoding="utf-8").read()
    assert "await file.read()" not in src, "осталось чтение файла без предела"
