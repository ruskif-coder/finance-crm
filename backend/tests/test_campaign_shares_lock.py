# -*- coding: utf-8 -*-
"""Параллельная смена статусов площадок РК не портит доли (07.10.2026, LBS2QH).

БЫЛО. Трафик включил четыре площадки почти разом: четыре `PUT …/placement/{id}/status` шли параллельно.
Каждый запрос ставит свой статус и сразу зовёт `build.recompute_shares`, а неподтверждённых статусов
соседей он не видит. Каждый считал «три прежние + я = четыре запущенных»; потолок доли 15 % для четырёх
площадок невыполним и поднимается до равной доли, и во все строки легло 0,25 / 125 000 при сумме 1,75.
Последним ночным пересчётом это исправилось бы, но трафики увидели цифры.

ТЕПЕРЬ. Статусы и доли РК меняются по одному: `ext_lock.lock_campaign_shares` — блокирующий замок
ТРАНЗАКЦИИ (снимается на `commit`, когда изменения уже видны соседям) и берётся ДО первой записи, иначе
два запроса, держащие строки друг друга, получили бы взаимный затор.

Тест пишет только свои строки (временная РК у существующей сделки) и убирает их.
"""
import inspect
import threading
import time
from datetime import date, timedelta

import pytest

from app import ext_lock
from app.ad import build
from app.ad.models import AdCampaign, AdCampaignPlacement
from app.database import SessionLocal
from app.sales.models import SalesDeal, SalesPublisher

KEY = 990777         # номер РК для замка (в базе его нет — замок про число, а не про строку)


# ── сам замок ───────────────────────────────────────────────────────────────

def test_second_holder_waits_until_the_first_commits():
    a, b = SessionLocal(), SessionLocal()
    got_b = threading.Event()
    try:
        ext_lock.lock_campaign_shares(a, KEY)

        def second():
            ext_lock.lock_campaign_shares(b, KEY)
            got_b.set()
        t = threading.Thread(target=second, daemon=True)
        t.start()
        assert not got_b.wait(0.7), "второй прошёл, пока первый держит замок"
        a.commit()                                  # снятие — на commit, как у настоящих запросов
        assert got_b.wait(5), "второй не получил замок после commit первого"
        t.join(5)
    finally:
        a.rollback()
        b.rollback()
        a.close()
        b.close()


def test_waiting_is_bounded_and_says_what_to_do():
    a, b = SessionLocal(), SessionLocal()
    try:
        ext_lock.lock_campaign_shares(a, KEY + 1)
        started = time.monotonic()
        with pytest.raises(ext_lock.CampaignBusy) as e:
            ext_lock.lock_campaign_shares(b, KEY + 1, wait_seconds=1)
        assert 0.8 < time.monotonic() - started < 6
        assert "повторите" in str(e.value)
    finally:
        a.rollback()
        b.rollback()
        a.close()
        b.close()


def test_different_campaigns_do_not_block_each_other():
    a, b = SessionLocal(), SessionLocal()
    try:
        ext_lock.lock_campaign_shares(a, KEY + 2)
        ext_lock.lock_campaign_shares(b, KEY + 3, wait_seconds=1)     # не должен ждать
    finally:
        a.rollback()
        b.rollback()
        a.close()
        b.close()


# ── порядок в обработчиках: замок раньше первой записи ─────────────────────

@pytest.mark.parametrize("name,first_write", [
    ("set_placement_status", "p.status ="),
    ("set_campaign_status", "c.status ="),
    ("set_creative_status", "cr.status ="),
])
def test_handlers_take_the_lock_before_they_write(name, first_write):
    from app.routers import traffic_dashboard as td
    src = inspect.getsource(getattr(td, name))
    assert "_lock_shares(" in src, f"{name}: нет замка"
    assert src.index("_lock_shares(") < src.index(first_write), (
        f"{name}: замок должен быть ДО записи статуса — иначе два запроса, держащие строки друг "
        "друга, получат взаимный затор")


def test_recompute_and_the_nightly_paths_take_the_lock_too():
    assert "lock_campaign_shares" in inspect.getsource(build.recompute_shares)
    assert "lock_campaign_shares" in inspect.getsource(build.refresh_weights)
    assert "lock_campaign_shares" in inspect.getsource(build.sync_placements)


# ── сама гонка ──────────────────────────────────────────────────────────────

@pytest.fixture
def temp_campaign():
    """РК на 7 площадок: три крутят, четыре ждут запуска. Живёт только в этом тесте."""
    db = SessionLocal()
    deal = db.query(SalesDeal).order_by(SalesDeal.id).first()
    pubs = db.query(SalesPublisher).order_by(SalesPublisher.id).limit(7).all()
    if deal is None or len(pubs) < 7:
        db.close()
        pytest.skip("на стенде нет сделки и семи площадок")
    camp = AdCampaign(deal_id=deal.id, month=date(2026, 10, 1), status="запущена",
                      date_start=date.today() - timedelta(days=10),
                      date_end=date.today() + timedelta(days=20), plan_show=500000)
    db.add(camp)
    db.flush()
    weights = [5283662, 2590831, 573443, 8046424, 1634288, 2986728, 1027027]
    ids = []
    for i, (pub, w) in enumerate(zip(pubs, weights)):
        p = AdCampaignPlacement(campaign_id=camp.id, publisher_id=pub.id, weight=w,
                                status="запущен" if i < 3 else "ждёт запуска")
        db.add(p)
        db.flush()
        ids.append(p.id)
    db.commit()
    cid = camp.id
    db.close()
    yield cid, ids
    db = SessionLocal()
    try:
        db.query(AdCampaignPlacement).filter(AdCampaignPlacement.campaign_id == cid).delete()
        db.query(AdCampaign).filter(AdCampaign.id == cid).delete()
        db.commit()
    finally:
        db.close()


def _stored(cid):
    db = SessionLocal()
    try:
        return {p.id: round(p.share or 0.0, 4) for p in
                db.query(AdCampaignPlacement).filter(AdCampaignPlacement.campaign_id == cid)}
    finally:
        db.close()


def _truth(cid):
    """Что должны лежать доли при ИТОГОВЫХ статусах: свежая раскладка без чьей-либо гонки."""
    db = SessionLocal()
    try:
        _pls, out = build.campaign_layout(db, cid)
        return {r["id"]: round(r["share"] or 0.0, 4) for r in out["rows"]}
    finally:
        db.close()


def _two_starts(cid, ids, locked: bool):
    """Два запроса «запустить площадку» одновременно — как нажал трафик. Возвращает итоговые доли."""
    first, second = ids[3], ids[4]
    a_written = threading.Event()
    a_may_commit = threading.Event()

    def handler(pid, signal=None, wait=None):
        db = SessionLocal()
        try:
            if locked:
                ext_lock.lock_campaign_shares(db, cid)
            p = db.get(AdCampaignPlacement, pid)
            p.status = "запущен"
            build.recompute_shares(db, cid)
            if signal:
                signal.set()
            if wait:
                wait.wait(5)           # DSP-вызовы внутри запроса занимают секунды
            db.commit()
        finally:
            db.rollback()
            db.close()

    ta = threading.Thread(target=handler, args=(first, a_written, a_may_commit), daemon=True)
    ta.start()
    assert a_written.wait(5)
    tb = threading.Thread(target=handler, args=(second,), daemon=True)
    tb.start()
    time.sleep(0.8)                    # B дошёл до своей записи (без замка) или стоит на замке
    a_may_commit.set()
    ta.join(10)
    tb.join(10)
    return _stored(cid), _truth(cid)


def test_control_without_the_lock_the_shares_are_wrong(temp_campaign, monkeypatch):
    """КОНТРОЛЬ: замок отключён целиком (и в обработчике, и в самом пересчёте) — гонка воспроизводится.
    Иначе тест ниже ничего бы не доказывал."""
    monkeypatch.setattr(ext_lock, "lock_campaign_shares", lambda *a, **k: None)
    cid, ids = temp_campaign
    stored, truth = _two_starts(cid, ids, locked=False)
    assert stored != truth, "гонка не воспроизвелась — проверка замка выше теряет смысл"


def test_with_the_lock_the_shares_match_the_final_statuses(temp_campaign):
    cid, ids = temp_campaign
    stored, truth = _two_starts(cid, ids, locked=True)
    assert stored == truth, (stored, truth)
    assert abs(sum(stored.values()) - 1.0) < 1e-3, "сумма долей должна быть 1"
