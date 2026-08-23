# -*- coding: utf-8 -*-
"""Схемы ссылок: единственная проверка и её потребители.

Ссылка из данных всегда рано или поздно попадает в `<a href={...}>` на фронте.
`javascript:` в этом атрибуте исполняется в сессии кликнувшего, а токен лежит в
localStorage — то есть это захват аккаунта. Проверка была в двух копиях
(`contracts.py`, `operations.py`), а третий потребитель — реестр документов
Диадока — не проверял ничего; сведено в `app/links.py` 2026-08-23.
"""
import pytest
from fastapi import HTTPException

from app.links import validate_link
from app.routers.diadoc import _parse_csv

GOOD = "https://diadoc.kontur.ru/aaa/Document/Show?letterId=bbb&documentId=ccc"


@pytest.mark.parametrize("url", [
    "http://example.com/doc.pdf",
    "https://example.com/doc.pdf",
    "  https://example.com/doc.pdf  ",
])
def test_safe_schemes_pass(url):
    assert validate_link(url).startswith("http")


@pytest.mark.parametrize("url", [
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD4=",
    "file:///etc/passwd",
    "vbscript:msgbox(1)",
])
def test_dangerous_schemes_are_rejected(url):
    with pytest.raises(HTTPException):
        validate_link(url)
    assert validate_link(url, raise_on_bad=False) is None


def test_empty_is_none_not_an_error():
    """Пустое значение — это «ссылки нет», а не битая ссылка."""
    assert validate_link(None) is None
    assert validate_link("") is None
    assert validate_link("   ") is None


# --- реестр Диадока ---------------------------------------------------------

def _csv(link: str) -> bytes:
    head = ("Ссылка;Имя файла;Номер документа;Дата документа;Всего;НДС;ИНН;КПП;"
            "Название организации;Статус документа;Комментарий")
    row = f"{link};acc.pdf;№1;01.01.2026;100;20;7700000000;770001001;ООО Ромашка;Подписан;"
    return (head + "\n" + row + "\n").encode("utf-8")


def test_diadoc_link_is_rebuilt_not_copied():
    """Разбор собирает ссылку из частей, а не переносит строку из файла."""
    rows = _parse_csv(_csv(GOOD))
    assert len(rows) == 1
    assert rows[0]["link"] == GOOD


def test_javascript_prefix_cannot_survive_the_parser():
    """Регулярка ищет ПОДСТРОКУ, поэтому такая строка успешно разбирается —
    и раньше легла бы в базу целиком, вместе со схемой javascript:."""
    poisoned = ("javascript:alert(document.cookie)//"
                "diadoc.kontur.ru/aaa/Document/Show?letterId=bbb&documentId=ccc")
    rows = _parse_csv(_csv(poisoned))
    assert len(rows) == 1, "строка должна разбираться — в этом и была ловушка"
    assert rows[0]["link"] == GOOD
    assert "javascript" not in rows[0]["link"].lower()


def test_row_without_a_diadoc_link_is_skipped():
    assert _parse_csv(_csv("https://example.com/nope")) == []
