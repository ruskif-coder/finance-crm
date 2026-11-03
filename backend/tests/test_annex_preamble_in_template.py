# -*- coding: utf-8 -*-
"""Преамбула ДС — текст шаблона (владелец 02.11.2026: «дать возможность в конструкторе ДС править первый блок и тоже
сохранять в шаблоне»; первый блок — преамбула).

До этого преамбула («ООО …, именуемое в дальнейшем «Заказчик», в лице … заключили настоящее …») была зашита в трёх
генераторах. Теперь у системного блока «pre» может быть текст шаблона с подстановками; без текста — прежняя формула,
и выпущенные шаблоны не меняются. Поломки: текст преамбулы не доходит до файла; стороны в тексте преамбулы собраны не
той функцией, что в старой формуле (две формулировки «именуемое в дальнейшем» разошлись бы); неизвестный тег в
преамбуле проходит проверку шаблона.
"""
import io
import pathlib

import pytest
from docx import Document

from app.annex_tpl import assemble as AS
from app.annex_tpl import check as CH
from app.annex_tpl.document import preamble_of
from app.annex_tpl.party import party_line
from app.annex_tpl.subs import SUBS
from app.sales import annex_docx

CUST = {"name": "ООО «Ромашка»", "legal_name": "ООО «Ромашка»", "position_gen": "Генерального директора",
        "director_gen": "Иванова Ивана Ивановича", "basis_gen": "Устава"}


def test_party_tags_are_in_the_dictionary():
    assert SUBS["заказчик"]["group"] == SUBS["исполнитель"]["group"] == "Стороны"


def test_party_line_is_the_one_of_the_old_formula():
    assert annex_docx._party_line is party_line
    assert party_line(CUST, "Заказчик") == ("ООО «Ромашка», именуемое в дальнейшем «Заказчик», в лице Генерального директора "
                                            "Иванова Ивана Ивановича, действующего на основании Устава")


def test_preamble_text_is_resolved_like_any_clause():
    blocks = [{"id": "head", "sys": "head"}, {"id": "pre", "sys": "pre", "text": "{заказчик} и {исполнитель} заключили {вид_документа}"}]
    out, empties = AS._blocks(blocks, {"заказчик": "А", "исполнитель": "Б", "вид_документа": "Дополнительное соглашение"})
    pre = out[1]
    assert pre["sys"] == "pre" and pre["text"] == "А и Б заключили Дополнительное соглашение"
    assert pre["template_text"] == "{заказчик} и {исполнитель} заключили {вид_документа}"
    assert any(p.get("key") == "заказчик" for p in pre["parts"])


def test_preamble_without_text_stays_the_old_formula():
    out, _ = AS._blocks([{"id": "pre", "sys": "pre"}], {})
    assert "text" not in out[0]
    assert preamble_of({"blocks": out}, "дс") is None


def test_preamble_of_the_model_speaks_the_full_word():
    model = {"blocks": [{"id": "pre", "sys": "pre", "text": "заключили настоящее Доп. соглашение"}]}
    assert preamble_of(model, "дс") == "заключили настоящее Дополнительное соглашение"


def test_unknown_tag_in_the_preamble_is_refused():
    blocks = [{"id": "head", "sys": "head"}, {"id": "place", "sys": "place"},
              {"id": "pre", "sys": "pre", "text": "{заказчик} и {нет_такого}"},
              {"id": "p1", "num": "1.", "title": "Предмет", "text": "Предмет договора"},
              {"id": "mp", "sys": "table"}, {"id": "sign", "sys": "sign"}]
    issues = CH.check(blocks)
    assert any("{нет_такого}" in i["text"] for i in issues)


def _text(data):
    return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)


def _doc(**kw):
    d = {"number": "Дополнительное соглашение № 30", "kind": "дс", "contract": {"number": "РМ 30-02-25"}, "date": None,
         "signed_place": "г. Москва", "customer": CUST, "executor": {"name": "Исполнитель"}, "rows": [],
         "amount_words": "сто", "vat_words": "двадцать", "vat_rate": 22.0, "body": "Предмет."}
    d.update(kw)
    return d


def test_docx_prints_the_template_preamble():
    text = _text(annex_docx.build_docx(_doc(preamble="Стороны договорились о нижеследующем:")))
    assert "Стороны договорились о нижеследующем:" in text and "с одной стороны" not in text


def test_docx_without_template_preamble_keeps_the_formula():
    assert "с одной стороны" in _text(annex_docx.build_docx(_doc()))


def test_pdf_page_and_constructor_read_the_template_preamble():
    root = pathlib.Path(__file__).resolve().parents[2] / "frontend"
    if not (root / "components/annex/AnnexModelPanel.jsx").exists():
        pytest.skip("в контейнере бэкенда фронта нет — проверяется в репозитории")
    assert "d.preamble" in (root / "pages/directory/annexes/pdf/[id].js").read_text(encoding="utf-8")
    assert "b.parts" in (root / "components/annex/AnnexModelPanel.jsx").read_text(encoding="utf-8")
