# -*- coding: utf-8 -*-
"""Приборы на разбор статистики Weborama. Без сети.

Образцы ответов взяты из первого живого вызова 12.09.2026, а не придуманы: четыре правила,
на которых стоит парсер, все четыре противоречат ожиданиям, и придуманный образец проверял
бы мои ожидания, а не их поведение.
"""
from datetime import date

import pytest

from app.weborama.stats import (METRICS, WcmPull, _leaves, _num, parse, pull, window)


# Форма из живого ответа: вставка снаружи, день внутри, метрики только на листе,
# нулевой клик не прислан вовсе.
LIVE = {
    "data": {"insertion": {
        "559": {"day": {"2026-09-12": {"metrics": {"impression": 10054}},
                        "2026-09-11": {"metrics": {"impression": 10802}}}},
        "32": {"day": {"2026-08-03": {"metrics": {"click": 1, "impression": 247}},
                       "2026-08-05": {"metrics": {"impression": 235}}}},
    }},
    "metadata": {"insertion": {
        "559": {"label": "SIMB-AD_banner_Desktop_tenoten_vapteke.ru"},
        "32": {"label": "SIMB-AD_banner_simbmob-fmk"},
    }},
}

# Форма с кампанией над вставкой: на каждом уровне лежит ИТОГ, равный сумме детей.
WITH_TOTALS = {
    "data": {"campaign": {"11": {
        "insertion": {"237": {"day": {"2026-09-01": {"metrics": {"impression": 18217}}}},
                      "189": {"day": {"2026-09-01": {"metrics": {"impression": 93493}}}}},
        "metrics": {"impression": 111710},
    }}},
    "metadata": {"campaign": {"11": {"label": "polisorb_more"}}},
}


def test_leaves_skips_level_totals():
    """Итог уровня равен сумме детей — сложить их значит удвоить факт."""
    leaves = _leaves(WITH_TOTALS["data"])
    assert len(leaves) == 2
    assert sum(m["impression"] for _, m in leaves) == 111710


def test_nesting_is_read_from_the_answer_not_from_the_question():
    """Порядок разрезов в запросе на структуру ответа не влияет.

    Живой замер: на `["day","insertion"]` пришло `insertion → day`. Парсер, идущий по
    списку запроса, прочёл бы id вставки как дату и развалился бы молча.
    """
    rows, _, _m = parse(LIVE)
    assert {r.insertion_id for r in rows} == {"559", "32"}
    assert {r.day for r in rows} == {date(2026, 9, 12), date(2026, 9, 11),
                                     date(2026, 8, 3), date(2026, 8, 5)}


def test_missing_metric_on_a_row_is_zero():
    """Нулевой клик они не присылают — у строки просто нет ключа."""
    rows, _, _m = parse(LIVE)
    by = {(r.insertion_id, r.day): r for r in rows}
    assert by[("32", date(2026, 8, 3))].click == 1
    assert by[("32", date(2026, 8, 5))].click == 0


def test_metric_absent_everywhere_is_reported_not_silently_zeroed():
    """ГЛАВНОЕ: неподдерживаемую метрику они не отвергают, а молча не присылают.

    Живой вызов: попросили `visibility` — ответ 200, метрики нет ни у одной строки. Если
    не сказать этого вслух, «видимость 0 %» станет выводом отчёта, а верификатор ради
    видимости и заводится.
    """
    rows, absent, _m = parse(LIVE, asked=("impression", "click", "visibility"))
    assert absent == ("visibility",)
    assert rows


def test_present_metric_is_not_reported_absent():
    rows, absent, _m = parse(LIVE, asked=("impression", "click"))
    assert absent == ()


def test_labels_come_only_from_metadata():
    """Внутри data меток нет вовсе — одни ключи-идентификаторы."""
    rows, _, _m = parse(LIVE)
    assert {r.label for r in rows} == {"SIMB-AD_banner_Desktop_tenoten_vapteke.ru",
                                       "SIMB-AD_banner_simbmob-fmk"}


def test_unknown_insertion_has_no_label_but_survives():
    payload = {"data": {"insertion": {"777": {"day": {"2026-09-01": {
        "metrics": {"impression": 5}}}}}}, "metadata": {}}
    rows, _, _m = parse(payload)
    assert rows[0].label is None and rows[0].impression == 5


@pytest.mark.parametrize("raw,want", [
    (2982, 2982),            # unique_impression приходит целым
    ("2982.00", 2982),       # reach_impression — строкой, та же величина
    ("20856.00", 20856),     # impression_without_IVT — тоже строкой
    (None, 0),
    ("", 0),
    ("не число", 0),
])
def test_numbers_arrive_as_int_or_as_string(raw, want):
    assert _num(raw) == want


def test_row_without_day_is_dropped_not_guessed():
    """Строка без разреза дня ни к чему не привязывается — угадывать дату нельзя."""
    payload = {"data": {"insertion": {"1": {"metrics": {"impression": 9}}}}, "metadata": {}}
    rows, _, _m = parse(payload)
    assert rows == []


def test_broken_date_is_dropped():
    payload = {"data": {"insertion": {"1": {"day": {"вчера": {
        "metrics": {"impression": 9}}}}}}, "metadata": {}}
    rows, _, _m = parse(payload)
    assert rows == []


def test_empty_answer_is_not_an_error():
    """Вставка без открутки в ответе отсутствует — это не отказ.

    Живой замер: наших учебных вставок 567–571 в ответе НЕТ ни одной, потому что они не
    крутились. Пустота здесь — законное состояние.
    """
    rows, absent, _m = parse({"data": {}, "metadata": {}})
    assert rows == []
    assert absent == METRICS[:0] + METRICS   # не пришло ничего из запрошенного


def test_window_includes_today():
    s, e = window(date(2026, 9, 12), days=3)
    assert (s, e) == (date(2026, 9, 10), date(2026, 9, 12))


def test_pull_asks_one_request_for_the_whole_account():
    """452 вставки приезжают одним ответом — запрос на вставку был бы 452 обращениями."""
    calls = []

    class FakeClient:
        def statistics(self, dimensions, metrics, **opts):
            calls.append((tuple(dimensions), tuple(metrics), opts))
            return LIVE

    got = pull(FakeClient(), date(2026, 9, 11), date(2026, 9, 12))
    assert len(calls) == 1
    assert calls[0][0] == ("insertion", "day")
    assert calls[0][2]["start_date"] == "2026-09-11"
    assert isinstance(got, WcmPull) and got.impressions == 10054 + 10802 + 247 + 235


# Живая форма верхнего уровня: у `data` не одна ветка, а три. `day` — тот же период в
# другом разрезе, `metrics` — итог за весь период. Числа из живого ответа 12.09.2026.
LIVE_WITH_MARGINS = {
    "data": {
        "insertion": {"559": {"day": {"2026-09-12": {"metrics": {"impression": 10054}},
                                      "2026-09-11": {"metrics": {"impression": 10802}}}}},
        "day": {"2026-09-12": {"metrics": {"impression": 10054}},
                "2026-09-11": {"metrics": {"impression": 10802}}},
        "metrics": {"impression": "20856", "impression_average": "10428.00",
                    "number_of_days": 2},
    },
    "metadata": {"insertion": {"559": {"label": "SIMB-AD_banner_Desktop_tenoten_vapteke.ru"}}},
}


def test_flat_twin_branch_is_not_added_to_the_rows():
    """Сложить ветку-двойник со строками — получить РОВНО двойное число.

    Правдоподобное и неверное: на живом ответе это 47 438 408 вместо 23 719 204.
    """
    rows, _, margins = parse(LIVE_WITH_MARGINS)
    assert sum(r.impression for r in rows) == 20856
    assert margins["grand"] == 20856
    assert margins["by_day"] == {date(2026, 9, 12): 10054, date(2026, 9, 11): 10802}


def test_checksum_uses_their_own_total_from_the_same_answer():
    class FakeClient:
        def statistics(self, dimensions, metrics, **opts):
            return LIVE_WITH_MARGINS

    got = pull(FakeClient(), date(2026, 9, 11), date(2026, 9, 12),
               metrics=("impression",))
    assert got.impressions == got.grand_total == 20856
    assert got.discrepancy == 0
    assert got.ok()


def test_checksum_catches_a_lost_branch():
    """Если разбор потеряет день, контрольная сумма это скажет числом."""
    broken = {"data": {"insertion": {"559": {"day": {
        "2026-09-12": {"metrics": {"impression": 10054}}}}},
        "metrics": {"impression": 20856}}, "metadata": {}}

    class FakeClient:
        def statistics(self, dimensions, metrics, **opts):
            return broken

    got = pull(FakeClient(), date(2026, 9, 11), date(2026, 9, 12),
               metrics=("impression",))
    assert got.discrepancy == 10054 - 20856
    assert not got.ok()


def test_no_total_in_answer_is_not_a_discrepancy():
    rows, _, margins = parse(LIVE)
    assert margins["grand"] is None


def test_the_wcm_account_has_exactly_one_home():
    """Аккаунт WCM адресует ВЕСЬ обмен с верификатором, и место у него одно.

    17.09.2026 он жил в двух местах, и ни одно не было рабочим: переменная
    `WEBORAMA_DEMO_ACCOUNT_ID` подставляется подсказкой в поле демо-экрана, а само поле
    вводится руками и никуда не сохраняется. Кнопка «ПИКСЕЛЬ WR» при этом читает
    настройку `weborama_account_id`, задать которую было НЕГДЕ: на проде она пустая, на
    стенде стояла вписанной прямо в базу и едва не потерялась при перезаписи стенда
    копией прода.

    Прибор держит ключ чтения и ключ записи одним значением: разойдись они — экран
    показывал бы сохранённое, а отправка отказывала «не задан аккаунт».
    """
    from app.routers.traffic_catalog import WEBORAMA_ACCOUNT, SiteScriptIn
    from app.weborama.provision import SETTING_ACCOUNT

    assert WEBORAMA_ACCOUNT == SETTING_ACCOUNT
    assert 'weborama_account' in SiteScriptIn.model_fields, (
        'поле аккаунта пропало из настроек — задать его снова будет негде')
