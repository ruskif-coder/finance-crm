# -*- coding: utf-8 -*-
"""Имя скачиваемого документа (владелец 09.11.2026): «вид - номер - дата - контрагент - мастер сделка - доп инфа если нужна»,
«независимо с какого экрана качаю — формат един». Ломается, если поменять порядок частей, разделитель, формат даты, оставить
в имени знак, который не примет Windows, или пустую часть с разделителем."""
from datetime import date

from app import doc_names as DN


def test_parts_go_in_owner_order_with_one_separator():
    assert DN.name("Счёт № 287", date(2026, 11, 6), "ИЗИ-НЭТ ООО", "M-0004") == "Счёт № 287 от 06.11.2026 · ИЗИ-НЭТ ООО · M-0004.pdf"


def test_extra_goes_last_and_extension_is_kept():
    assert (DN.name("УПД № 240", date(2026, 11, 6), "ИЗИ-НЭТ ООО", "M-0004", "ЭДО", ".xml")
            == "УПД № 240 от 06.11.2026 · ИЗИ-НЭТ ООО · M-0004 · ЭДО.xml")


def test_missing_parts_drop_without_empty_separators():
    assert DN.name("Договор № РМ-01", None, "ООО Ромашка", None) == "Договор № РМ-01 · ООО Ромашка.pdf"
    assert DN.name("ДС без номера", None, None, None, None, ".docx") == "ДС без номера.docx"


def test_windows_forbidden_characters_never_reach_the_name():
    n = DN.name("ДС № 1", date(2026, 5, 31), 'ООО "Ромашка/Север"', "M-0001")
    assert not set('\/:*?"<>|') & set(n) and "Ромашка Север" in n


def test_name_stays_within_the_filesystem_limit():
    n = DN.name("ДС № 68", date(2026, 5, 31), "Контрагент " * 40, "M-0001", "доп " * 40, ".docx")
    assert len(n.encode("utf-8")) <= 255 and n.endswith(".docx")


def test_annex_number_is_short_like_on_screens():
    assert DN.short_annex("Доп. соглашение № 68") == "ДС № 68"
    assert DN.short_annex("Дополнительное соглашение №68") == "ДС № 68"
    assert DN.short_annex("Приложение № 17") == "ПР № 17"
    assert DN.short_annex(None, 7) == "ДС № 7"
    assert DN.short_annex(None, None) == "ДС без номера"
