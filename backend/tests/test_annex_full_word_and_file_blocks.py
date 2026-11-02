# -*- coding: utf-8 -*-
"""Решения владельца 02.11.2026.

1. В тексте документа вид «дс» пишется ПОЛНОСТЬЮ: «Дополнительное соглашение» — не «Доп. соглашение» и не просто
   «Соглашение». Слово документа с заглавной в тексте шаблона («по настоящему Соглашению») тоже переходит в полную форму, в
   своём падеже. Прилагательное склоняется вместе с существительным, поэтому замена основой («Доп. соглашени» + окончание)
   больше не работает — формы заданы явно по окончанию.
2. Файлы .docx и PDF печатают РОВНО блоки конструктора: пункты, номера и тексты шаблона. До этого файлы собирал старый
   генератор со своими зашитыми пунктами 1.1–3 («счет-фактуры, Акта», «в 2 (двух) экземплярах»), а из конструктора брал только
   пункт 1 — клиенту уходил не тот текст, что видел аккаунт (ДС № 30, 02.11.2026).
"""
import io

import pytest
from docx import Document

from app.annex_tpl import doc_kind as DK
from app.annex_tpl.document import clauses_of
from app.sales import annex_docx

# ── 1. Полное слово ──────────────────────────────────────────────────────────────────────────────────────────────────


def test_number_is_spelled_out():
    assert DK.number_text("дс", "30") == "Дополнительное соглашение № 30"


@pytest.mark.parametrize("old,new", [
    ("по настоящему Соглашению", "по настоящему Дополнительному соглашению"),
    ("На условиях настоящего Соглашения", "На условиях настоящего Дополнительного соглашения"),
    ("Настоящее Соглашение вступает в силу", "Настоящее Дополнительное соглашение вступает в силу"),
    ("не урегулированном настоящим Соглашением", "не урегулированном настоящим Дополнительным соглашением"),
    ("согласно Доп. соглашению №30", "согласно Дополнительному соглашению №30"),
    ("настоящего Доп.соглашения", "настоящего Дополнительного соглашения"),
    ("настоящим Приложением", "настоящим Дополнительным соглашением"),
    ("отдельными Приложениями", "отдельными Дополнительными соглашениями"),
    ("в настоящем Соглашении", "в настоящем Дополнительном соглашении"),
])
def test_every_spelling_of_the_document_word_becomes_the_full_form(old, new):
    assert DK.rebrand(old, "дс") == new


def test_lowercase_agreements_and_the_mobile_app_are_not_the_document():
    s = "отдельными соглашениями к Договору, размещение в мобильном приложении"
    assert DK.rebrand(s, "дс") == s


def test_the_full_form_is_left_alone():
    s = "по настоящему Дополнительному соглашению; Дополнительное соглашение № 30"
    assert DK.rebrand(s, "дс") == s


def test_the_application_kind_does_not_touch_the_word_agreement():
    s = "по настоящему Соглашению и Приложению"
    assert DK.rebrand(s, "приложение") == s


def test_an_old_abbreviated_number_is_printed_in_full():
    assert DK.renumber("Доп. соглашение № 30", "дс") == "Дополнительное соглашение № 30"


# ── 2. Файл = блоки конструктора ─────────────────────────────────────────────────────────────────────────────────────

MODEL = {"blocks": [
    {"id": "head", "sys": "head"}, {"id": "place", "sys": "place"}, {"id": "pre", "sys": "pre"},
    {"id": "p1", "num": "1.", "sub": False, "text": "Предмет по настоящему Соглашению.\n"},
    {"id": "mp", "sys": "table"},
    {"id": "p11", "num": "1.1.", "sub": True, "text": "Оплата на основании счета, УПД."},
    {"id": "n1", "num": "1.3.", "sub": True, "text": "Исполнитель направляет счет, УПД в течение 5 рабочих дней."},
    {"id": "p5", "num": "5.", "sub": False, "text": "Составлено в форме электронного документа."},
    {"id": "sign", "sys": "sign"},
]}


def test_clauses_follow_the_model_in_order_with_the_full_word():
    got = clauses_of(MODEL, "дс")
    assert [c.get("sys") or c["num"] for c in got] == ["head", "place", "pre", "1.", "table", "1.1.", "1.3.", "5.", "sign"]
    assert got[3]["text"] == "Предмет по настоящему Дополнительному соглашению."
    assert got[5]["sub"] is True


def _doc(**kw):
    d = {"number": "Дополнительное соглашение № 30", "kind": "дс", "contract": {"number": "РМ 30-02-25"},
         "date": None, "signed_place": "г. Москва", "customer": {"name": "Заказчик"}, "executor": {"name": "Исполнитель"},
         "rows": [], "amount_words": "сто", "vat_words": "двадцать", "vat_rate": 22.0, "body": "Предмет."}
    d.update(kw)
    return d


def _text(data: bytes) -> str:
    return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)


def test_docx_prints_exactly_the_constructor_clauses():
    text = _text(annex_docx.build_docx(_doc(clauses=clauses_of(MODEL, "дс"))))
    assert "1.3.\tИсполнитель направляет счет, УПД в течение 5 рабочих дней." in text
    assert "5.\tСоставлено в форме электронного документа." in text
    assert "1.1.\tОплата на основании счета, УПД." in text
    assert "счет-фактуры" not in text and "экземплярах" not in text, "зашитые пункты старого генератора попали в файл"
    assert text.index("1.\t") < text.index("1.1.\t") < text.index("1.3.\t") < text.index("5.\t") < text.index("Подписи Сторон")


def test_docx_without_a_template_keeps_the_old_text():
    """ДС, собранные до конструктора (модели нет), печатаются как раньше — иначе их файл опустел бы."""
    text = _text(annex_docx.build_docx(_doc()))
    assert "1.1.\t" in text and "1.2.\t" in text


def test_pdf_page_renders_the_clauses_from_the_document():
    import pathlib
    page = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "pages" / "directory" / "annexes" / "pdf" / "[id].js"
    if not page.exists():
        pytest.skip("в контейнере бэкенда фронта нет — проверяется в репозитории")
    src = page.read_text(encoding="utf-8")
    assert "d.clauses" in src


def test_the_frozen_document_on_screen_says_the_same_as_the_file():
    """Экран подтверждённого ДС показывает замороженную модель; слово в ней — то же, что в файле (полное), иначе аккаунт
    видит «Доп. соглашение № 30», а клиенту уходит «Дополнительное соглашение № 30» (репетиция 02.11.2026)."""
    from app.annex_tpl.document import rebrand_model
    model = {"number": "Доп. соглашение № 30", "kind": "дс",
             "blocks": [{"id": "p1", "num": "1.", "text": "по настоящему Соглашению",
                         "parts": [{"t": "по настоящему Соглашению «"}, {"t": "Соглашение Плюс", "key": "бренд"}, {"t": "»"}]}],
             "closing_basis": {"text": "согласно Доп. соглашению №30"}}
    out = rebrand_model(model, "дс")
    assert out["number"] == "Дополнительное соглашение № 30"
    assert out["blocks"][0]["text"] == "по настоящему Дополнительному соглашению"
    assert out["blocks"][0]["parts"][0]["t"] == "по настоящему Дополнительному соглашению «"
    assert out["blocks"][0]["parts"][1]["t"] == "Соглашение Плюс", "подставленное значение не трогаем"
    assert out["closing_basis"]["text"] == "согласно Дополнительному соглашению №30"
    assert model["number"] == "Доп. соглашение № 30", "исходная модель не меняется"
