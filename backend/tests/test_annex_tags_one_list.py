# -*- coding: utf-8 -*-
"""Теги подстановок шаблона ДС: один список, по блокам; номер — со знаком «№» (владелец 02.11.2026).

1. У редактора шаблонов был СВОЙ список тегов (`frontend/lib/annexTemplate.mjs`) — 12 из 25 серверных: новые теги
   (юр. название, дата ДС, вид документа) редактор считал неизвестными и не давал сохранить шаблон, а кнопки шли
   вразнобой. Поломка, которую ловит тест: список редактора снова разошёлся с серверным или порядок блоков другой.
2. `{номер_дс}` печатал «24», владельцу нужно «№24». Во всех 28 версиях шаблонов текст уже «№ {номер_дс}» — второй
   «№» не должен появиться. Поломка: «№ №24» или «24»."""
import pathlib
import re

import pytest

from app.annex_tpl import assemble as AS
from app.annex_tpl import subs as S

MJS = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "lib" / "annexTemplate.mjs"


def test_listing_goes_block_by_block():
    items = S.listing()
    groups = [x["group"] for x in items]
    order = list(dict.fromkeys(groups))
    assert order == list(S.GROUPS), "блоки — в заданном порядке"
    assert all(groups[i] == groups[i - 1] or groups[i] not in groups[:i] for i in range(1, len(groups))), "блок не рвётся"


def test_editor_list_is_the_server_list():
    if not MJS.exists():
        pytest.skip("исходников фронта нет в контейнере — проверяется в репозитории")
    src = MJS.read_text(encoding="utf-8")
    body = re.search(r"export const SUBS = \{(.*?)\n\}", src, re.S).group(1)
    keys = re.findall(r"'([^']+)':\s*\[", body)
    assert keys == list(S.SUBS), "ключи и порядок тегов редактора = серверным"
    groups = re.search(r"export const SUB_GROUPS = \[(.*?)\n\]", src, re.S).group(1)
    assert re.findall(r"^\s*\['([^']+)',\s*\[", groups, re.M) == list(S.GROUPS)


@pytest.mark.parametrize("text,want", [
    ("{номер_дс}", "№24"),
    ("настоящего Приложения № {номер_дс} (далее", "настоящего Приложения №24 (далее"),
    ("Приложения №{номер_дс}", "Приложения №24"),
])
def test_number_tag_prints_with_sign_once(text, want):
    out = "".join(p["t"] for p in AS._parts(text, {"номер_дс": AS.number_value(24)}))
    assert out == want


def test_draft_without_number_prints_nothing():
    assert AS.number_value(None) == ""
