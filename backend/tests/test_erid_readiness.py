# -*- coding: utf-8 -*-
"""Единое правило «ЕРИД готов» (владелец 02.10.2026).

Маркер ОРД выдаёт сразу, регистрация в ЕРИР идёт потом: RegistrationRequired → Registering →
Active. Готов — только при Active или Registering; чужой маркер (самореклама площадки)
нашего статуса не имеет и готов сразу. До 02.10 правил было два: копия нацеливания
смотрела статус, а стадия, ступень ОРД, пиксель Weborama и перенос в РК — только
«маркер не пустой», и на проде три комплекта в RegistrationRequired на одном экране
были готовы, на другом нет.
"""
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.database import SessionLocal
from app.ord import readiness


from app.launch_prep import erid_service as svc  # noqa: E402
from app.routers import launch_prep as lp  # noqa: E402

def _patch(mp, name, value):
    """Подмена в роутере и в сервисе ЕРИД: функции выпуска живут в
    `app.launch_prep.erid_service` (02.10.2026), роутер держит их же имена."""
    mp.setattr(lp, name, value)
    if hasattr(svc, name):
        mp.setattr(svc, name, value)

def _set(erid="KraXXX", status="Active", source="наш", no=1, sid=1):
    return SimpleNamespace(id=sid, no=no, erid=erid, ord_status=status, erid_source=source)


@pytest.mark.parametrize("status,ready", [
    ("Active", True), ("Registering", True),
    # Временно готов и маркер в очереди ОРД (владелец 05.10.2026: 11 комплектов висели 3–5 дней).
    ("RegistrationRequired", True), ("Created", False), ("RegistrationError", False),
    (None, False),
])
def test_own_marker_ready_only_when_registered(status, ready):
    assert readiness.erid_ready(_set(status=status)) is ready


def test_empty_marker_never_ready():
    assert readiness.erid_ready(_set(erid="", status="Active")) is False
    assert readiness.erid_ready(_set(erid=None, status="Active")) is False
    assert readiness.ready_erid(_set(erid="  ", status="Active")) is None


def test_foreign_marker_ready_without_status():
    assert readiness.erid_ready(_set(status=None, source="площадки")) is True


def test_sql_fragment_matches_python_rule():
    """Одно правило в двух видах: SQL-условие обязано отвечать то же, что функция."""
    db = SessionLocal()
    try:
        cases = [("K1", "Active", "наш"), ("K2", "Registering", "наш"),
                 ("K3", "RegistrationRequired", "наш"), ("", "Active", "наш"),
                 (None, None, "наш"), ("K4", None, "площадки"), ("K5", None, None)]
        for erid, st, src in cases:
            got = db.execute(text(
                "SELECT " + readiness.ready_sql("s") + " FROM (SELECT CAST(:e AS text) AS erid, "
                "CAST(:st AS text) AS ord_status, CAST(:src AS text) AS erid_source) s"),
                {"e": erid, "st": st, "src": src}).scalar()
            want = readiness.erid_ready(_set(erid=erid, status=st, source=src))
            assert bool(got) is want, (erid, st, src)
    finally:
        db.close()


def test_targeting_copy_reads_the_same_rule():
    from app.dsp import targeting_creative as tc
    assert tc.erid_of(_set(status="Created")) == tc.TEST_ERID
    assert tc.erid_of(_set(status="Registering")) == "KraXXX"
    assert tc.ERID_READY_STATUSES == readiness.READY_STATUSES


def test_stage_check_erid_issued_waits_for_registration():
    from app.sales import stage_checks as sc
    ctx = SimpleNamespace(sets=[_set(status="Active", no=1),
                                _set(status="Created", no=2)])
    r = sc._erid_issued(ctx)
    assert r.state != "ok"
    assert "№2" in str(r)


def test_direct_advertiser_one_reading():
    assert readiness.is_direct(SimpleNamespace(ord_direct_advertiser=True)) is True
    assert readiness.is_direct(SimpleNamespace(ord_direct_advertiser=None)) is False
    assert readiness.is_direct(SimpleNamespace()) is False


# ── объявление маркера: на выпуске и на опросе статуса ─────────────────────

class _Db:
    def __init__(self, s):
        self.s = s

    def query(self, model):
        s = self.s
        return SimpleNamespace(filter=lambda *a: SimpleNamespace(first=lambda: s))

    def commit(self):
        pass

    def rollback(self):
        pass


@pytest.fixture
def lp_wired(monkeypatch):
    from app.routers import launch_prep as lp
    seen = {"announced": 0, "logged": []}
    _patch(monkeypatch, "active_pairs", lambda db, set_id: [1])
    _patch(monkeypatch, "_ord_chain", lambda db, d: ("F-1", None))
    _patch(monkeypatch, "_files_with_content", lambda db, set_id: [])
    _patch(monkeypatch, "_target_urls", lambda db, set_id: [])
    _patch(monkeypatch, "announce_marker",
                        lambda db, s, d, actor, out: seen.__setitem__("announced", seen["announced"] + 1))
    _patch(monkeypatch, "log_action", lambda db, u, action, *a, **kw: seen["logged"].append(a))
    return lp, seen


def test_issue_with_unregistered_marker_is_not_announced(lp_wired, monkeypatch):
    lp, seen = lp_wired
    s = _set(erid=None, status=None)

    def issue(db, cset, *a, **kw):
        cset.erid, cset.ord_status = "KraNEW", "Created"     # не готов и по временному правилу
        return {"erid": "KraNEW", "status": "Created"}
    monkeypatch.setattr("app.ord.submit.issue_marker", issue)
    lp.issue_marker_for_set(_Db(s), s, SimpleNamespace(id=1, code="ABC", brand_id=None), None)
    assert seen["announced"] == 0


def test_issue_with_registering_marker_is_announced(lp_wired, monkeypatch):
    lp, seen = lp_wired
    s = _set(erid=None, status=None)

    def issue(db, cset, *a, **kw):
        cset.erid, cset.ord_status = "KraNEW", "Registering"
        return {"erid": "KraNEW", "status": "Registering"}
    monkeypatch.setattr("app.ord.submit.issue_marker", issue)
    lp.issue_marker_for_set(_Db(s), s, SimpleNamespace(id=1, code="ABC", brand_id=None), None)
    assert seen["announced"] == 1


@pytest.mark.parametrize("after,pending,announced", [
    ("Registering", True, 1),            # стал готов, площадки ещё «согласован» — объявить
    ("Active", True, 1),
    ("Active", False, 0),                # уже объявлен (площадки «ерид получен») — молчать
    ("Created", True, 0),                # не готов — молчать
])
def test_refresh_announces_ready_marker_not_yet_announced(lp_wired, monkeypatch, after, pending, announced):
    """Объявлен ли маркер — по состоянию площадок, а не по переходу статуса (ревью 02.10.2026):
    опрос сам фиксирует статус, и упавшее после него объявление переход бы потеряло;
    а комплекты, объявленные по старому правилу, второго письма получать не должны."""
    lp, seen = lp_wired
    s = _set(erid="KraNEW", status="RegistrationRequired")

    def refresh(db, cset):
        cset.ord_status = after
        return {"erid": cset.erid, "status": after}
    monkeypatch.setattr("app.ord.submit.refresh_creative_status", refresh)
    monkeypatch.setattr(svc, "_has_unannounced", lambda db, set_id: pending)
    monkeypatch.setattr(svc, "_sync_marker", lambda db, deal_id: None)
    lp.refresh_and_announce(_Db(s), s, SimpleNamespace(id=1, code="ABC", brand_id=None), None)
    assert seen["announced"] == announced


def test_cron_catches_up_ready_but_unannounced(monkeypatch):
    """Готовый маркер с площадками в «согласован» объявляется кроном, даже если статус уже
    конечный и опрашивать его нечего (объявление однажды упало)."""
    import inspect
    from app.launch_prep import erid_auto
    assert "catch_up" in inspect.getsource(erid_auto.run)


def test_cron_refresh_goes_through_announce(monkeypatch):
    """Крон опроса статуса обязан объявлять маркер, ставший готовым, — иначе площадки
    так и не узнают о нём до следующего ручного действия."""
    import inspect
    from app.launch_prep import erid_auto
    src = inspect.getsource(erid_auto.refresh_statuses)
    assert "refresh_and_announce" in src
