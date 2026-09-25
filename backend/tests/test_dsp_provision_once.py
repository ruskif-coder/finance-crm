# -*- coding: utf-8 -*-
"""Выгрузка РК в DSP: сбой, таймаут или двойной клик оставляют в кабинете ОДИН объект.

Этап 4 аудита 23.09.2026 (4.H1, 4.H2, 4.L4, 4.L5). Креатив и кампанию в DSP не удалить
по API — дубль остаётся навсегда и делит показы с настоящим. Поэтому проверяется не
«выгрузка прошла», а сколько раз был вызван СОЗДАЮЩИЙ метод.

Всё на подставном клиенте: живой кабинет здесь не нужен и опасен. Настоящая только
блокировка — она в базе, и проверять её подделкой значило бы проверять подделку.
"""
import threading
import time
from datetime import date
from types import SimpleNamespace

import pytest

from app.dsp import creatives as cr
from app.dsp import provision as prov
from app.dsp.client import MsError


class FakeMs:
    """Кабинет DSP в памяти: журнал вызовов, креативы с их кодом, управляемые сбои."""
    contour = "prod"

    def __init__(self, *, fail_edit=0, add_timeout=0, add_delay=0.0,
                 list_rows=None, list_fails=False, creative_timeout=0):
        self.calls = []
        self.journal = {}        # (метод, local_ref) -> хеш удачного вызова
        self.unknown = set()     # (метод, local_ref) — ушло, ответа нет
        self.cabinet = {}        # хеш креатива -> html
        self.campaigns = []      # что реально заведено в кабинете
        self.fail_edit = fail_edit
        self.add_timeout = add_timeout
        self.add_delay = add_delay
        self.list_rows = list_rows
        self.list_fails = list_fails
        self.creative_timeout = creative_timeout
        self._n = 0
        self._lock = threading.Lock()

    def _hash(self):
        with self._lock:
            self._n += 1
            return f"{self._n:016X}"

    # журнал
    def last_ok_xxhash(self, method, entity_type, local_ref):
        return self.journal.get((method, str(local_ref)))

    def unknown_outcome(self, method, entity_type, local_ref):
        return (method, str(local_ref)) in self.unknown

    def unknown_refs(self, method, entity_type, refs):
        return {str(r) for r in refs if (method, str(r)) in self.unknown}

    def journal_raw(self, method, entity_type, local_ref, request, response,
                    ms_xxhash, ok, error):
        """Отметка сверки: как в настоящем журнале, она снимает «исход неизвестен»."""
        if ok and ms_xxhash:
            self.journal[(method, str(local_ref))] = ms_xxhash
        self.unknown.discard((method, str(local_ref)))

    def campaign_get_info(self, xx):
        found = [c for c in self.campaigns if c["xxhash"] == xx]
        if not found:
            raise MsError("Campaign.getInfo: Campaign not found")
        return {"xxhash": xx, "title": found[0]["title"]}

    # кампании
    def campaign_list_by_partner(self):
        self.calls.append("Campaign.getListByPartner")
        if self.list_fails:
            raise MsError("Campaign.getListByPartner: обрыв")
        return list(self.list_rows if self.list_rows is not None else self.campaigns)

    def campaign_add(self, params, local_ref=None):
        self.calls.append("Campaign.add")
        time.sleep(self.add_delay)
        xx = self._hash()
        self.campaigns.append({"xxhash": xx, "title": params["title"]})
        if self.add_timeout:
            # Кампания в кабинете СОЗДАНА, а ответ до нас не дошёл.
            self.add_timeout -= 1
            self.unknown.add(("Campaign.add", str(local_ref)))
            raise MsError("Campaign.add: ReadTimeout")
        self.journal[("Campaign.add", str(local_ref))] = xx
        return xx

    # креативы
    def creative_add(self, camp, params, local_ref=None):
        self.calls.append("Creative.add")
        self.added = getattr(self, "added", []) + [params]
        xx = self._hash()
        self.cabinet[xx] = ""
        if self.creative_timeout:
            # Креатив в кабинете СОЗДАН, ответа нет — хеша мы не знаем.
            self.creative_timeout -= 1
            self.unknown.add(("Creative.add", str(local_ref)))
            raise MsError("Creative.add: ReadTimeout")
        self.journal[("Creative.add", str(local_ref))] = xx
        return xx

    def creative_edit(self, xx, params, local_ref=None):
        self.calls.append("Creative.edit")
        if self.fail_edit:
            self.fail_edit -= 1
            raise MsError("Creative.edit: обрыв связи")
        self.cabinet[xx] = params["data"]["html_code"]

    def creative_get_info(self, xx):
        self.calls.append("Creative.getInfo")
        if xx not in self.cabinet:
            raise MsError("Creative.getInfo: Creative not found")
        return {"data": {"html_code": self.cabinet[xx]}}

    def upload_get_url(self, file_type="zip"):
        return "https://upload.test/x"


class FakeDb:
    def __init__(self, deal):
        self.deal = deal
        self.commits = 0

    def query(self, model):
        return SimpleNamespace(get=lambda _id: self.deal)

    def flush(self):
        pass

    def commit(self):
        self.commits += 1


def _camp(cid):
    return SimpleNamespace(id=cid, deal_id=1, ms_campaign_xxhash=None, month=date(2026, 10, 1),
                           date_start=date(2026, 10, 1), date_end=date(2026, 10, 31),
                           plan_show=1000, plan_click=0, plan_budget=0, ms_synced_at=None)


def _row(n=1):
    cre = SimpleNamespace(id=n, ms_title=f"баннер {n}", erid="Kra23test", ms_creative_xxhash=None,
                          status=prov.CREATIVE_OK[0])
    pl = SimpleNamespace(id=100 + n, plan_show=500, weborama_pixel=None, is_direct=False,
                         status=prov.PLACEMENT_OK[0], publisher_id=1)
    return {"creative": cre, "placement": pl,
            "publisher": SimpleNamespace(name="площадка", our_code=False, domain="site.test"),
            "file": SimpleNamespace(original_name="b.zip", path="x", is_archive=True),
            "target": SimpleNamespace(advertiser_url="https://landing.test")}


@pytest.fixture
def wired(monkeypatch):
    """Всё, что вокруг вызовов DSP, — заглушками; сами вызовы идут в FakeMs."""
    from app.routers import traffic_catalog

    state = {"rows": [_row(1)]}
    monkeypatch.setattr(prov, "_rows", lambda db, camp: state["rows"])
    monkeypatch.setattr(prov, "pixel_setup",
                        lambda db, deal_id: {"needed": False, "mode": None, "tag": None})
    monkeypatch.setattr(prov, "_read_archive", lambda f: b"PK")
    monkeypatch.setattr(cr, "upload_zip", lambda c, data, filename=None, local_ref=None:
                        {"html": "<div>баннер</div>", "width": 300, "height": 250,
                         "size": "300x250"})
    monkeypatch.setattr(traffic_catalog, "creative_script", lambda db, our: "")
    monkeypatch.setattr(traffic_catalog, "viewability_src", lambda db: "")
    return state


def _db():
    return FakeDb(SimpleNamespace(id=1, code="ABC123", title="Сделка"))


# ── 4.1: обрыв между add и edit ─────────────────────────────────────────────

def test_edit_failure_does_not_make_the_retry_create_a_second_creative(wired):
    ms = FakeMs(fail_edit=1)
    camp = _camp(990401)

    first = prov.provision(_db(), camp, client=ms)
    assert first["failed"] and not first["done"]
    assert ms.calls.count("Creative.add") == 1

    second = prov.provision(_db(), camp, client=ms)
    assert ms.calls.count("Creative.add") == 1, (
        "повтор после обрыва завёл второй креатив — в кабинете сирота без кода")
    assert second["done"], second
    cre = wired["rows"][0]["creative"]
    assert cre.ms_creative_xxhash == second["done"][0]["xxhash"]
    assert ms.cabinet[cre.ms_creative_xxhash], "код в креатив так и не доехал"


def test_creative_removed_in_the_cabinet_is_created_again(wired):
    """Сирота, которого снесли руками, — единственный случай, когда add повторяется."""
    ms = FakeMs(fail_edit=1)
    camp = _camp(990402)
    prov.provision(_db(), camp, client=ms)
    ms.cabinet.clear()

    out = prov.provision(_db(), camp, client=ms)
    assert ms.calls.count("Creative.add") == 2
    assert out["done"]


def test_creative_with_its_code_in_place_is_just_remembered(wired):
    """Код доехал, а наш коммит — нет: ни add, ни edit, хеш просто запоминается."""
    ms = FakeMs()
    camp = _camp(990403)
    ms.creative_add("C", {}, local_ref="cr1")
    ms.creative_edit(ms.journal[("Creative.add", "cr1")], {"data": {"html_code": "<b/>"}})
    ms.calls.clear()

    out = prov.provision(_db(), camp, client=ms)
    assert "Creative.add" not in ms.calls and "Creative.edit" not in ms.calls
    assert out["done"][0]["xxhash"] == ms.journal[("Creative.add", "cr1")]


# ── 4.3: пустая кампания и таймаут Campaign.add ─────────────────────────────

def test_nothing_ready_means_no_campaign_in_dsp(wired):
    wired["rows"] = []
    ms = FakeMs()
    with pytest.raises(prov.DspProvisionError):
        prov.provision(_db(), _camp(990404), client=ms)
    assert "Campaign.add" not in ms.calls, "в кабинете появилась пустая кампания"


def test_campaign_timeout_then_retry_finds_the_created_one(wired):
    ms = FakeMs(add_timeout=1)
    camp = _camp(990405)
    with pytest.raises(prov.DspProvisionError):
        prov.provision(_db(), camp, client=ms)

    prov.provision(_db(), camp, client=ms)
    assert ms.calls.count("Campaign.add") == 1, "таймаут породил вторую кампанию"
    assert camp.ms_campaign_xxhash == ms.campaigns[0]["xxhash"]


def test_campaign_timeout_and_no_list_means_no_blind_retry(wired):
    ms = FakeMs(add_timeout=1)
    camp = _camp(990406)
    with pytest.raises(prov.DspProvisionError):
        prov.provision(_db(), camp, client=ms)
    ms.list_fails = True

    with pytest.raises(prov.DspProvisionError) as e:
        prov.provision(_db(), camp, client=ms)
    assert ms.calls.count("Campaign.add") == 1
    assert "кабинет" in str(e.value)


# ── 4.2: двойной клик ───────────────────────────────────────────────────────

def test_two_simultaneous_clicks_create_one_campaign(wired):
    ms = FakeMs(add_delay=0.5)
    camp = _camp(990407)
    results, errors = [], []

    def click():
        try:
            results.append(prov.provision(_db(), camp, client=ms))
        except prov.DspProvisionError as e:
            errors.append(str(e))

    threads = [threading.Thread(target=click) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert ms.calls.count("Campaign.add") == 1, ms.calls
    assert ms.calls.count("Creative.add") == 1, ms.calls
    assert len(results) == 1 and len(errors) == 1, (results, errors)
    assert "уже идёт" in errors[0]


def test_creative_timeout_is_not_retried_blindly(wired):
    """Ревью 23.09.2026. Таймаут на самом `Creative.add` в журнале — строка без ответа и
    без хеша: `last_ok_xxhash` её не видит, и повтор заводил второй креатив. Перечислить
    креативы кампании у DSP нечем — значит, повтор запрещён до сверки с кабинетом."""
    ms = FakeMs(creative_timeout=1)
    camp = _camp(990408)
    prov.provision(_db(), camp, client=ms)

    out = prov.provision(_db(), camp, client=ms)
    assert ms.calls.count("Creative.add") == 1, "таймаут породил второй креатив"
    assert out["failed"] and "кабинет" in out["failed"][0]["error"]



# ── ссылки боевого креатива (владелец 25.09.2026) ───────────────────────────
#
# Оба адреса — из РЕАЛЬНОЙ посадочной таблицы запуска: `link` — посадочная целиком,
# `adomain` («конечный URL», у DSP обязателен для ротации и не длиннее 128) — только её
# основной домен. На проде 18 посадочных из 138 длиннее 128 символов.

def test_combat_creative_gets_landing_and_its_domain(wired):
    ms = FakeMs()
    long_url = "https://www.apteka.test/catalog/" + "x" * 300 + "?utm_source=simb"
    wired["rows"][0]["target"] = SimpleNamespace(advertiser_url=long_url)
    out = prov.provision(_db(), _camp(990501), client=ms)
    assert out["done"], out
    params = ms.added[-1]
    assert params["link"] == long_url
    assert params["adomain"] == "https://www.apteka.test/"
    assert len(params["adomain"]) <= 128


def test_landing_domain_helper():
    assert cr.landing_domain("https://apteka.ru/tovar/1?x=2") == "https://apteka.ru/"
    assert cr.landing_domain("apteka.ru/tovar") == "https://apteka.ru/"
    assert cr.landing_domain("http://Sub.Apteka.ru:8080/a") == "http://sub.apteka.ru/"
    assert cr.landing_domain("") is None and cr.landing_domain("не адрес") is None
    assert cr.landing_domain("https://120на80.рф/catalog") == "https://xn--12080-6ve4g.xn--p1ai/"
