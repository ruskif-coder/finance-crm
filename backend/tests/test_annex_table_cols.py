# -*- coding: utf-8 -*-
"""Колонки таблицы МП в шаблоне ДС (владелец 17.11.2026: клиент — «Диджитал Альянс», ДС № 31 — просит в ДС свой формат таблицы).

Поломки, которые ловит набор:
- шаблон без настройки печатает не прежние 13 колонок или ИТОГО не на своём месте — у всех остальных клиентов поменялась бумага;
- таблица по образцу клиента печатает не те значения: имя рекламодателя вместо юр. названия, «APP» вместо подменённого,
  объём складывается в ИТОГО, хотя колонке сказано не складывать;
- пустое юр. название молча подменяется коротким именем (правило `{юр_название}`), а не запирает выгрузку;
- проверка шаблона пропускает неизвестное поле, таблицу без денег, «свой текст» без текста;
- смена колонок не видна в журнале версий шаблона;
- Word рисует не те колонки, что посчитал `view`."""
from datetime import date
from io import BytesIO

import pytest
from docx import Document

from app.annex_tpl import check as CK
from app.annex_tpl import table_cols as TC
from app.annex_tpl.diff import diff

ROW = {"deal_id": 1, "network": "SIMB-AD", "position": "еФарм", "geo": "РФ", "format": "Баннеры", "device": "APP",
       "model": "CPM", "volume": 500000, "date_from": date(2026, 9, 1), "date_to": date(2026, 9, 30), "unit_price": 247.5,
       "amount": 123750.0, "vat": 27225.0, "gross": 150975.0, "kind": "base"}
ROW2 = {**ROW, "deal_id": 2, "device": "WEB", "volume": 753425, "amount": 151250.0, "vat": 33275.0, "gross": 184525.0}
DOC = {"rows": [ROW, ROW2], "vat_rate": 22, "period_from": date(2026, 9, 1), "period_to": date(2026, 9, 30)}

ALLIANCE = [
    {"key": "advertiser_legal", "label": "Рекламодатель"},
    {"key": "brand", "label": "Объект рекламирования/Бренд"},
    {"key": "const", "label": "Интернет–ресурс (сайт)", "value": "Simb-ad"},
    {"key": "device", "label": "Информационный носитель", "map": {"APP": "IN-APP / (Desktop+Mobile)", "WEB": "WEB / (Desktop+Mobile)"}},
    {"key": "period", "label": "Период оказания услуг"},
    {"key": "volume", "label": "Количество единиц", "sum": False},
    {"key": "unit", "label": "Единица измерения"},
    {"key": "amount", "label": "Стоимость без НДС (руб.)"},
    {"key": "gross", "label": "Стоимость с НДС (руб.)"},
]


NAMES = {1: ("Alfasigma", "ALFASIGMA S.p.A.", "Альфазокс"), 2: ("Teva", None, "Троксевазин")}


def test_default_is_the_old_thirteen_columns():
    v = TC.view(None, DOC, TC.of_blocks([{"id": "t", "sys": "table"}]))
    assert [h["label"] for h in v["head"]] == [
        "Место\nразмещения", "Позиция", "Гео", "Формат", "Девайс", "Тип ротации\n(для медийных\nформатов)", "Модель\nзакупки",
        "Объем размещения", "Период", "Стоимость\nза единицу\nзакупки", "Стоимость\nразмещения", "НДС 22%",
        "Стоимость\nразмещения\nс учетом НДС"]
    assert v["rows"][0]["cells"] == ["SIMB-AD", "еФарм", "РФ", "Баннеры", "APP", "—", "CPM", "500 000", "01.09.2026 –\n30.09.2026",
                                     "247,50", "123 750,00", "27 225,00", "150 975,00"]
    assert v["total"] == {"span": 7, "cells": ["", "", "", "", "", "", "", "1 253 425", "", "", "275 000,00", "60 500,00", "335 500,00"]}


def test_alliance_layout_prints_like_their_ds():
    v = TC.view(None, DOC, TC.normalize(ALLIANCE), NAMES)
    assert [h["label"] for h in v["head"]][:4] == ["Рекламодатель", "Объект рекламирования/Бренд", "Интернет–ресурс (сайт)", "Информационный носитель"]
    assert v["rows"][0]["cells"] == ["ALFASIGMA S.p.A.", "Альфазокс", "Simb-ad", "IN-APP / (Desktop+Mobile)", "01.09.2026 –\n30.09.2026",
                                     "500 000", "Показов", "123 750,00", "150 975,00"]
    assert v["rows"][1]["cells"][3] == "WEB / (Desktop+Mobile)"
    assert v["total"] == {"span": 7, "cells": ["", "", "", "", "", "", "", "275 000,00", "335 500,00"]}     # объём не сложен


def test_empty_legal_name_is_named_not_replaced():
    v = TC.view(None, DOC, TC.normalize(ALLIANCE), NAMES)
    assert v["rows"][1]["cells"][0] == "—"
    assert v["missing"] == ["юр. название рекламодателя «Teva» (справочник рекламодателей) — для колонки таблицы"]


@pytest.mark.parametrize("cols, err", [
    ([{"key": "id_заказа"}, {"key": "amount"}], "неизвестное поле"),
    ([{"key": "brand"}, {"key": "volume"}], "хотя бы одна колонка с деньгами"),
    ([{"key": "const", "label": "Сайт"}, {"key": "amount"}], "нужен текст"),
    ([{"key": "amount", "map": {"1": "2"}}], "только у текстовых"),
])
def test_normalize_refuses(cols, err):
    with pytest.raises(ValueError, match=err):
        TC.normalize(cols)


def test_default_list_is_stored_as_nothing():
    assert TC.normalize([{"key": k} for k in TC.DEFAULT]) is None


def test_check_and_diff_see_columns():
    blocks = [{"id": "h", "sys": "head"}, {"id": "pl", "sys": "place"}, {"id": "p", "sys": "pre"}, {"id": "t", "sys": "table", "columns": [{"key": "brand"}]},
              {"id": "s", "sys": "sign"}]
    assert any("с деньгами" in i["text"] for i in CK.check(blocks))
    new = [dict(b) for b in blocks]
    new[3]["columns"] = TC.normalize(ALLIANCE)
    assert CK.check(new) == []
    assert diff(blocks, new)[0][:3] == ["~", "Таблица МП", "изменены колонки"]


def test_docx_draws_the_view():
    from app.sales.annex_docx import _table
    d = {**DOC, "table_columns": TC.normalize(ALLIANCE), "table_names": {str(k): v for k, v in NAMES.items()}}   # как после JSON
    doc = Document()
    _table(doc, d)
    out = BytesIO()
    doc.save(out)
    t = Document(BytesIO(out.getvalue())).tables[0]
    assert len(t.columns) == 9
    assert [c.text for c in t.rows[1].cells][:4] == ["ALFASIGMA S.p.A.", "Альфазокс", "Simb-ad", "IN-APP / (Desktop+Mobile)"]
    assert t.rows[-1].cells[0].text == "ИТОГО:" and t.rows[-1].cells[-1].text == "335 500,00"


def test_group_titles_dropped_when_brand_is_a_column():
    doc = {**DOC, "rows": [{"group_title": "Alfasigma / Альфазокс · еФарм · APP"}, ROW]}
    assert [list(r) for r in TC.view(None, doc, TC.normalize(ALLIANCE), NAMES)["rows"]] == [["cells"]]
    assert TC.view(None, doc, TC.of_blocks(None))["rows"][0] == {"group": "Alfasigma / Альфазокс · еФарм · APP"}
