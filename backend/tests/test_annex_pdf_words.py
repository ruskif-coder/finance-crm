# -*- coding: utf-8 -*-
"""PDF называет документ тем же словом, что DOCX и конструктор (ревью 31.10.2026).

Страница печати `pages/directory/annexes/pdf/[id].js` в правку «синхронизировать» не
попала: слово в пунктах она выбирала признаком мастер-сделки, в сокращённой форме
(«настоящим ДС»), а дательный в основании получала заменой строки «Приложение» →
«Приложению». С тумблером договора это давало заголовок «Доп. соглашение № 68» и в тех же
пунктах «настоящим Приложением», а в основании — «К Доп. соглашение № 7». PDF уходит на
подпись, поэтому слово ему отдаёт бэкенд — из того же `doc_kind`, что и остальным.

Поломка, которую ловят тесты: формы слова снова считаются на странице, или бэкенд
перестаёт класть их в документ.
"""
import pathlib

import pytest

from app.annex_tpl import doc_kind
from app.annex_tpl.document import with_words

PDF = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "pages" / "directory" / "annexes" / "pdf" / "[id].js"


@pytest.mark.parametrize("doc,ins,pl_ins,dat_number", [
    # тумблер договора «дс» у обычного ДС
    ({"kind": "дс", "number": "Доп. соглашение № 68"},
     "Доп. соглашением", "Доп. соглашениями", "Доп. соглашению № 68"),
    # мастер-сделка, замороженная до 31.10 (вида в модели нет) — доп. соглашение, как DOCX
    ({"is_master": True, "number": "Доп. соглашение № 7"},
     "Доп. соглашением", "Доп. соглашениями", "Доп. соглашению № 7"),
    # старый обычный ДС без вида — приложение
    ({"number": "Приложение № 12"},
     "Приложением", "Приложениями", "Приложению № 12"),
])
def test_document_carries_its_words_in_every_case(doc, ins, pl_ins, dat_number):
    out = with_words(dict(doc))
    assert out["words"]["ins"] == ins
    assert out["words"]["pl_ins"] == pl_ins
    assert out["number_dat"] == dat_number


def test_with_words_does_not_mutate_its_input():
    doc = {"kind": "дс", "number": "Доп. соглашение № 1"}
    with_words(doc)
    assert "words" not in doc


def test_instrumental_forms_are_declared_for_both_variants():
    for k in doc_kind.KINDS:
        f = doc_kind.forms(k)
        assert f["ins"] and f["pl_ins"]


def test_pdf_page_takes_the_word_from_the_document():
    if not PDF.exists():
        pytest.skip("в контейнере бэкенда фронта нет — проверяется в репозитории")
    src = PDF.read_text(encoding="utf-8")
    assert "d.words" in src
    assert "настоящим Приложением" not in src and "настоящим ДС" not in src
    assert ".replace('Приложение', 'Приложению')" not in src


@pytest.mark.parametrize("doc,number", [
    # подписан «Приложением», тумблер договора потом переключили на «ДС»: предпросмотр собрал номер
    # по тумблеру, а вид документа зафиксирован — заголовок обязан остаться словом подписания
    ({"kind": "приложение", "number": "Доп. соглашение № 12"}, "Приложение № 12"),
    # подписан до 31.10, вида в модели нет — как было: «Приложение»
    ({"number": "Доп. соглашение № 12"}, "Приложение № 12"),
    # обратный случай: подписан «ДС»
    ({"kind": "дс", "number": "Приложение № 5"}, "Доп. соглашение № 5"),
    # мастер-сделка с номером в старой сокращённой форме — заголовок тем же словом, что пункты
    ({"is_master": True, "number": "ДС № 7-01"}, "Доп. соглашение № 7-01"),
    # номер, который не начинается со слова документа, не трогаем
    ({"kind": "дс", "number": "б/н"}, "б/н"),
])
def test_heading_word_follows_the_fixed_kind_not_the_current_toggle(doc, number):
    """Номер — один счётчик, от вида не зависит (владелец 31.10.2026); слово перед ним — вид, зафиксированный
    при подписании, как и в пунктах. Иначе после переключения тумблера скачанный заново подписанный документ
    назывался бы в заголовке одним словом, а в пунктах — другим (ревью 31.10.2026)."""
    out = with_words(dict(doc))
    assert out["number"] == number
    assert out["number_dat"] == doc_kind.to_dative(number, out["kind"]) or number == "б/н"


@pytest.mark.parametrize("annex,contract_word,model_kind,want", [
    # подтверждён после 31.10: вид записан в ДС — он главнее всего
    ({"doc_kind": "приложение", "status": "подтверждён", "blocks": {"blocks": []}}, "дс", "дс", "приложение"),
    # черновик без шаблона: модели нет — слово по тумблеру договора, как в предпросмотре
    ({"doc_kind": None, "status": "черновик", "blocks": None}, "дс", None, "дс"),
    # подписан до 31.10 без шаблона: тумблер, выбранный потом, его не переименовывает
    ({"doc_kind": None, "status": "подтверждён", "blocks": None}, "дс", None, None),
    # живой черновик с шаблоном: вид модели
    ({"doc_kind": None, "status": "черновик", "blocks": None}, "приложение", "дс", "дс"),
])
def test_which_kind_the_printed_document_takes(annex, contract_word, model_kind, want):
    from types import SimpleNamespace

    from app.annex_tpl.document import fixed_kind
    a = SimpleNamespace(master_deal_id=None, **annex)
    c = SimpleNamespace(annex_word=contract_word)
    assert fixed_kind(a, c, model_kind) == want
