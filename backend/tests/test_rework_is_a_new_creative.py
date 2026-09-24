# -*- coding: utf-8 -*-
"""Доработка — НОВЫЙ порядковый креатив РК, а не подмена старого (владелец 23.09.2026).

До этого действовало решение 04.09.2026: креатив — рекламное сообщение, доработка его
не меняет, и строка креатива РК жила на КОРНЕ цепочки. Доработка переставляла на ней
пару, файл и ЕРИД. Если креатив уже уехал в DSP, там оставался старый баннер, а у нас —
новый маркер и новый файл, и выгрузка его не перезаливала: строка с хешем пропускается
(аудит 23.09.2026, 4.M9).

Новое правило владельца: «правки не перезаписываются, а уходят в новый порядковый».
Каждый комплект — своя строка со своим номером, маркером и файлом; доработка без хеша
выгружается как новый креатив, прежний остаётся как был.

База подменена: сборка строк — чистая логика над ответами запросов, и проверяется
именно она.
"""
from types import SimpleNamespace

from app.ad import build
from app.ad.models import AdCampaignCreative, AdCampaignPlacement

ROOT, REWORK = 501, 502


class _Res:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class _Q:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *a):
        return self

    def all(self):
        return self.rows


class _Db:
    def __init__(self, existing=()):
        self.pl = AdCampaignPlacement(id=11, campaign_id=1, publisher_id=7,
                                      status="у трафика")
        self.creatives = list(existing)

    def query(self, model):
        return _Q([self.pl] if model is AdCampaignPlacement else list(self.creatives))

    def execute(self, sql, params=None):
        q = str(sql)
        if "replaces_set_id IS NOT NULL" in q:
            return _Res([{"replaces_set_id": ROOT, "publisher_id": 7}])
        if "SELECT id, no FROM launch_prep_creative_set" in q:
            return _Res([{"id": ROOT, "no": 1}, {"id": REWORK, "no": 2}])
        if "DISTINCT ON (f.set_id)" in q:
            return _Res([{"set_id": ROOT, "file_id": 901}, {"set_id": REWORK, "file_id": 902}])
        if "FROM launch_prep_pair pr" in q:
            return _Res([
                {"pair_id": 81, "set_id": ROOT, "set_no": 1, "erid": "ERID-1",
                 "publisher_id": 7, "traffic_verdict": "ок", "platform_verdict": "на доработку"},
                {"pair_id": 82, "set_id": REWORK, "set_no": 2, "erid": "ERID-2",
                 "publisher_id": 7, "traffic_verdict": "ок", "platform_verdict": "ок"},
            ])
        if "sales_publishers pub" in q:
            return _Res([{"deal_code": "HCLA6E", "pub_code": "SMK"}])
        raise AssertionError(f"неожиданный запрос: {q[:80]}")

    def add(self, row):
        self.creatives.append(row)

    def flush(self):
        pass

    def commit(self):
        pass


def _camp():
    return SimpleNamespace(id=1, deal_id=1)


def test_rework_gets_its_own_row_number_marker_and_file():
    db = _Db()
    build.sync_creatives(db, _camp())

    rows = sorted(db.creatives, key=lambda c: c.creative_no)
    assert [c.creative_no for c in rows] == [1, 2], (
        "доработка склеилась с исходным креативом вместо нового порядкового")
    first, second = rows
    assert (first.erid, first.file_id, first.pair_id) == ("ERID-1", 901, 81)
    assert (second.erid, second.file_id, second.pair_id) == ("ERID-2", 902, 82)
    assert second.ms_title.endswith("-cr2")


def test_a_creative_already_in_dsp_is_not_rewritten_by_the_rework():
    """Исходный уже в DSP: доработка его не трогает — ни файл, ни маркер, ни пару."""
    uploaded = AdCampaignCreative(campaign_id=1, placement_id=11, root_set_id=ROOT,
                                  creative_no=1, status="запущен", pair_id=81,
                                  erid="ERID-1", file_id=901,
                                  ms_creative_xxhash="AAAABBBBCCCCDDDD")
    db = _Db(existing=[uploaded])
    build.sync_creatives(db, _camp())

    assert (uploaded.erid, uploaded.file_id, uploaded.pair_id) == ("ERID-1", 901, 81)
    fresh = [c for c in db.creatives if c is not uploaded]
    assert len(fresh) == 1 and fresh[0].creative_no == 2
    assert not fresh[0].ms_creative_xxhash, "доработка уехала бы как уже выгруженная"


def test_a_row_uploaded_under_the_old_rule_keeps_what_went_to_dsp():
    """Ревью 23.09.2026. По прежнему правилу строка корня несла пару, маркер и файл
    ДОРАБОТКИ и с ними уехала в DSP. Новое правило не должно переписать её обратно на
    корень: в кабинете лежит ERID-2, а у нас стало бы ERID-1."""
    uploaded = AdCampaignCreative(campaign_id=1, placement_id=11, root_set_id=ROOT,
                                  creative_no=1, status="запущен", pair_id=82,
                                  erid="ERID-2", file_id=902,
                                  ms_creative_xxhash="AAAABBBBCCCCDDDD")
    db = _Db(existing=[uploaded])
    build.sync_creatives(db, _camp())
    assert (uploaded.erid, uploaded.file_id, uploaded.pair_id) == ("ERID-2", 902, 82)


def test_the_replaced_creative_is_retired():
    """Креатив, ушедший в доработку, не висит вечно «у площадки»: его место занял новый
    порядковый, и в работе он больше не числится."""
    db = _Db()
    build.sync_creatives(db, _camp())
    old = next(c for c in db.creatives if c.creative_no == 1)
    assert old.status == "отклонён", old.status


def test_a_number_taken_by_an_uploaded_row_is_not_reused():
    """Строка из DSP сохраняет свой номер навсегда. Если он совпал с номером нового
    комплекта, новый получает следующий свободный — иначе уникальность «площадка ×
    номер» роняла бы каждую сборку этой РК."""
    frozen = AdCampaignCreative(campaign_id=1, placement_id=11, root_set_id=499,
                                creative_no=2, status="запущен",
                                ms_creative_xxhash="1111222233334444")
    db = _Db(existing=[frozen])
    build.sync_creatives(db, _camp())
    nos = [c.creative_no for c in db.creatives]
    assert len(nos) == len(set(nos)), f"номера совпали: {nos}"
