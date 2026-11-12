# -*- coding: utf-8 -*-
"""Архив «Скачать для Диадока» (реестр v3, 12.11.2026; владелец: класть то, что есть, недостающее — в «не вошло.txt»).
Поломка, которую ловит: комплект без PDF счёта, PDF УПД или XML УПД из 1С молча выпадает из архива, и в Диадок уходит неполный
пакет; сканы (подписанная бумага) попадают в архив для ЭДО."""
from app.master_deal import bundle


def test_missing_1c_files_are_named_per_kit():
    kits = [{"upd_no": 1, "upd_doc_no": "1247"}, {"upd_no": 2, "upd_doc_no": None}]
    files = {1: {"invoice": {"id": 5}, "upd": {"id": 6}, "xml": {"id": 7}}, 2: {"upd": {"id": 8}}}
    assert bundle.missing_onec(kits, files) == ["Комплект 2: нет счёта (pdf) и XML УПД из 1С"]


def test_kit_with_nothing_from_1c():
    assert bundle.missing_onec([{"upd_no": 3, "upd_doc_no": None}], {}) == ["Комплект 3: нет счёта (pdf), УПД (pdf) и XML УПД из 1С"]


def test_diadoc_bundle_takes_1c_files_not_scans():
    assert bundle.diadoc_kinds() == {"счёт 1С", "УПД 1С", "УПД 1С xml"}
