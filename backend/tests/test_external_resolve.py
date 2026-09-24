# -*- coding: utf-8 -*-
"""Выход из «исход неизвестен» для DSP и Weborama (владелец 23.09.2026).

Этап 4 аудита сделал так, что вызов, ушедший без ответа, запирает повтор: объект в чужом
кабинете мог создаться, а удалить второй там нечем. Но запертое без выхода — тупик: снять
его можно было только запросом в базу. Выход тот же, что у ОРД: человек сверяется с
кабинетом и отмечает одно из двух.

  · «Нашёл» + id — объект записывается как наш, следующее нажатие продолжает с него;
  · «Нет в кабинете» — попытка закрыта как «не создано», повтор разрешён.

DSP проверяет найденный хеш своим чтением; Weborama — тегом вставки (метода чтения
проекта и кампании мы вживую не проверяли, там id принимается как введён — и это
пишется в журнал попытки).
"""
from types import SimpleNamespace

import pytest

import app.models  # noqa: F401 — пользователи для внешнего ключа журнала
from app.ad import unknown as U
from app.database import SessionLocal
from app.dsp import provision as dprov
from app.weborama import provision as wprov
from app.weborama.client import WcmError
from app.weborama.models import (KIND_CAMPAIGN, KIND_INSERTION, KIND_PROJECT,
                                 WeboramaRef, WeboramaSubmission)
from tests.test_dsp_provision_once import FakeMs, _camp, _db, wired  # noqa: F401

ACC = "TESTACC_R4"
USER = SimpleNamespace(id=None, name="трафик")


# ── Weborama ─────────────────────────────────────────────────────────────────

@pytest.fixture
def wdb(monkeypatch):
    s = SessionLocal()

    def purge():
        s.rollback()
        s.query(WeboramaRef).filter(WeboramaRef.account_id == ACC).delete()
        s.query(WeboramaSubmission).filter(WeboramaSubmission.account_id == ACC).delete()
        s.commit()
    purge()
    monkeypatch.setattr(wprov, "account_id", lambda db: ACC)
    yield s
    purge()
    s.close()


def _hung(db, kind, local_id, label="ТЕСТ · объект"):
    sub = WeboramaSubmission(account_id=ACC, kind=kind, local_id=local_id,
                             method="/advertiser/x.json", request={"label": label})
    db.add(sub)
    db.commit()
    return sub


def _wcamp():
    return SimpleNamespace(id=999510, deal_id=999511)


def test_weborama_hung_attempt_is_listed_with_what_to_look_for(wdb):
    sub = _hung(wdb, KIND_PROJECT, 999511, "HCLA6E · Бренд · 2026-10")
    items = [x for x in U.list_unknown(wdb, _wcamp(), systems=("weborama",)) if x["system"] == "weborama"]
    assert [(x["ref"], x["label"]) for x in items] == [(str(sub.id), "HCLA6E · Бренд · 2026-10")]


def test_weborama_not_found_reopens_the_retry(wdb):
    sub = _hung(wdb, KIND_PROJECT, 999511)
    U.resolve(wdb, _wcamp(), "weborama", str(sub.id), found=False, external_id=None, user=USER)
    assert not wprov._open_attempt(wdb, ACC, KIND_PROJECT, 999511)
    assert not [x for x in U.list_unknown(wdb, _wcamp(), systems=("weborama",)) if x["system"] == "weborama"]


def test_weborama_found_becomes_ours(wdb):
    sub = _hung(wdb, KIND_CAMPAIGN, 999510)
    U.resolve(wdb, _wcamp(), "weborama", str(sub.id), found=True, external_id="4321",
              user=USER)
    ref = wprov._ref(wdb, ACC, KIND_CAMPAIGN, 999510)
    assert ref is not None and ref.wcm_id == "4321"
    assert not wprov._open_attempt(wdb, ACC, KIND_CAMPAIGN, 999510)


def test_weborama_insertion_is_checked_by_its_tag(wdb, monkeypatch):
    sub = _hung(wdb, KIND_INSERTION, 999512)
    monkeypatch.setattr(U, "_placement_ids", lambda db, camp: [999512])

    class NoSuch:
        def insertion_tag(self, iid):
            raise WcmError("Weborama ответила 404")

    with pytest.raises(U.ResolveError):
        U.resolve(wdb, _wcamp(), "weborama", str(sub.id), found=True, external_id="777",
                  user=USER, wcm_client=NoSuch())
    assert wprov._open_attempt(wdb, ACC, KIND_INSERTION, 999512), (
        "непроверенный id записан как наш")


def test_someone_elses_attempt_is_not_resolved_from_this_campaign(wdb):
    sub = _hung(wdb, KIND_PROJECT, 123)        # проект чужой сделки
    with pytest.raises(U.ResolveError):
        U.resolve(wdb, _wcamp(), "weborama", str(sub.id), found=False, external_id=None,
                  user=USER)


def test_weborama_id_already_ours_elsewhere_is_refused(wdb):
    """Ревью 23.09.2026. Тег вставки доказывает, что она есть, но не что она этой
    площадки: id, уже записанный за другим объектом, приняли бы — и показы одной
    площадки легли бы на другую."""
    wdb.add(WeboramaRef(account_id=ACC, kind=KIND_CAMPAIGN, local_id=999599,
                        wcm_id="4321", label="ТЕСТ · чужая"))
    wdb.commit()
    sub = _hung(wdb, KIND_CAMPAIGN, 999510)
    with pytest.raises(U.ResolveError):
        U.resolve(wdb, _wcamp(), "weborama", str(sub.id), found=True, external_id="4321",
                  user=USER)


def test_resolution_waits_for_a_running_provision(wdb):
    """Ревью 23.09.2026. Попытка без `finished_at` бывает и ИДУЩЕЙ: соседний клик ещё
    ждёт ответа. Отметить её «нет в кабинете» — открыть повтор, пока первый вызов
    может создать объект. Сверка идёт под тем же замком, что и заведение."""
    from sqlalchemy import text

    from app.database import engine
    from app.ext_lock import WEBORAMA_PROVISION

    sub = _hung(wdb, KIND_PROJECT, 999511)
    holder = engine.connect()
    holder.execute(text("SELECT pg_advisory_lock(:a, :b)"),
                   {"a": WEBORAMA_PROVISION, "b": 999511})
    try:
        with pytest.raises(U.ResolveError) as e:
            U.resolve(wdb, _wcamp(), "weborama", str(sub.id), found=False,
                      external_id=None, user=USER)
        assert "идёт" in str(e.value)
    finally:
        holder.execute(text("SELECT pg_advisory_unlock(:a, :b)"),
                       {"a": WEBORAMA_PROVISION, "b": 999511})
        holder.close()


# ── DSP ──────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _free_hashes(monkeypatch):
    """По умолчанию хеш ничей: проверку занятости отдельные тесты включают сами."""
    monkeypatch.setattr(U, "_hash_taken", lambda db, xx: False)

def _timed_out_creative(wired):  # noqa: F811
    ms = FakeMs(creative_timeout=1)
    camp = _camp(990520)
    dprov.provision(_db(), camp, client=ms)
    return ms, camp


def test_dsp_hung_creative_is_listed(wired, monkeypatch):  # noqa: F811
    ms, camp = _timed_out_creative(wired)
    monkeypatch.setattr(U, "_creatives", lambda db, c: [wired["rows"][0]["creative"]])
    items = [x for x in U.list_unknown(_db(), camp, dsp_client=ms, systems=("dsp",)) if x["system"] == "dsp"]
    assert [x["ref"] for x in items] == ["cr1"]


def test_dsp_found_hash_is_continued_not_recreated(wired, monkeypatch):  # noqa: F811
    ms, camp = _timed_out_creative(wired)
    created = [h for h in ms.cabinet]            # то, что DSP успел завести
    monkeypatch.setattr(U, "_creatives", lambda db, c: [wired["rows"][0]["creative"]])
    U.resolve(_db(), camp, "dsp", "cr1", found=True, external_id=created[0].lower(),
              user=USER, dsp_client=ms)

    out = dprov.provision(_db(), camp, client=ms)
    assert ms.calls.count("Creative.add") == 1, "найденный креатив завели заново"
    assert out["done"] and out["done"][0]["xxhash"] == created[0]
    assert ms.cabinet[created[0]], "код в найденный креатив не дошит"


def test_dsp_unknown_hash_is_refused(wired, monkeypatch):  # noqa: F811
    ms, camp = _timed_out_creative(wired)
    monkeypatch.setattr(U, "_creatives", lambda db, c: [wired["rows"][0]["creative"]])
    with pytest.raises(U.ResolveError):
        U.resolve(_db(), camp, "dsp", "cr1", found=True, external_id="FFFFFFFFFFFFFFFF",
                  user=USER, dsp_client=ms)


def test_dsp_not_found_reopens_the_retry(wired, monkeypatch):  # noqa: F811
    ms, camp = _timed_out_creative(wired)
    monkeypatch.setattr(U, "_creatives", lambda db, c: [wired["rows"][0]["creative"]])
    U.resolve(_db(), camp, "dsp", "cr1", found=False, external_id=None, user=USER,
              dsp_client=ms)

    out = dprov.provision(_db(), camp, client=ms)
    assert ms.calls.count("Creative.add") == 2 and out["done"]


def test_dsp_hash_already_ours_elsewhere_is_refused(wired, monkeypatch):  # noqa: F811
    ms, camp = _timed_out_creative(wired)
    created = [h for h in ms.cabinet]
    monkeypatch.setattr(U, "_creatives", lambda db, c: [wired["rows"][0]["creative"]])
    monkeypatch.setattr(U, "_hash_taken", lambda db, xx: True)
    with pytest.raises(U.ResolveError):
        U.resolve(_db(), camp, "dsp", "cr1", found=True, external_id=created[0],
                  user=USER, dsp_client=ms)


def test_dsp_campaign_must_carry_our_name(wired, monkeypatch):  # noqa: F811
    """Ревью 23.09.2026. `getInfo` отвечает на ЛЮБУЮ кампанию кабинета. Опечатка в хеше
    чужой РК привязала бы к нам её — и следующий «Запустить» отправил бы туда наш план."""
    ms = FakeMs(add_timeout=1)
    camp = _camp(990530)
    with pytest.raises(dprov.DspProvisionError):
        dprov.provision(_db(), camp, client=ms)
    ms.campaigns.append({"xxhash": "ABCDABCDABCDABCD", "title": "ЧУЖАЯ · 2026-10"})
    with pytest.raises(U.ResolveError):
        U.resolve(_db(), camp, "dsp", "campaign", found=True,
                  external_id="ABCDABCDABCDABCD", user=USER, dsp_client=ms)
    assert camp.ms_campaign_xxhash is None

    ours = ms.campaigns[0]["xxhash"]
    U.resolve(_db(), camp, "dsp", "campaign", found=True, external_id=ours,
              user=USER, dsp_client=ms)
    assert camp.ms_campaign_xxhash == ours
