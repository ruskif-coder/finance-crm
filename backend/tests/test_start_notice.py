# -*- coding: utf-8 -*-
"""«Кампания стартовала» площадке — при ЕЁ первом запуске, каким бы путём он ни шёл
(аудит 01.10.2026, В-4). Раньше письмо уходило только с кнопки РК и сразу ВСЕМ площадкам
РК — в том числе ещё не запущенным; запуск кнопкой площадки не писал никому."""
import inspect

import app.main  # noqa: F401
from app.routers import traffic_dashboard as td


def test_first_start_is_marked_once():
    """Первый запуск — по отметке в базе, а не по статусу «было до»: площадку могли
    поставить на паузу или завершить, ни разу не запустив (владелец 02.10.2026)."""
    from types import SimpleNamespace as NS
    p = NS(status="запущен", first_started_at=None)
    assert td._mark_first_start(p) and p.first_started_at is not None
    assert not td._mark_first_start(p), "второй запуск — не первый"
    paused_never_ran = NS(status="запущен", first_started_at=None)   # пауза → запущен
    assert td._mark_first_start(paused_never_ran), "запуск после паузы без старта — первый"
    assert not td._mark_first_start(NS(status="пауза", first_started_at=None))


def test_both_paths_notify_only_started_placements():
    camp_src = inspect.getsource(td.set_campaign_status)
    pl_src = inspect.getsource(td.set_placement_status)
    assert "_tell_publishers_started(db, c, started)" in camp_src
    assert "_tell_publishers_started(" in pl_src and "_mark_first_start(p)" in pl_src


def test_notice_goes_only_to_given_placements(monkeypatch):
    from types import SimpleNamespace as NS
    from app.notify import outward
    sent = []
    monkeypatch.setattr(outward, "notify_publisher", lambda db, k, pid, **kw: sent.append(kw["entity_id"]))
    import app.routers.launch_prep as lp
    monkeypatch.setattr(lp, "_deal_brand_name", lambda db, d: "Б")
    monkeypatch.setattr(lp, "deal_period_text", lambda d: "10.2026")
    rows = [(NS(id=1), NS(id=10, domain="a.ru", name="a")), (NS(id=2), NS(id=11, domain="b.ru", name="b"))]

    class Q:
        def __init__(self, r):
            self.r = r

        def __getattr__(self, n):
            return lambda *a, **k: self

        def first(self):
            return NS(id=5)

        def all(self):
            return self.r
    db = NS(query=lambda *a: Q(rows), rollback=lambda: None)
    td._tell_publishers_started(db, NS(id=1, deal_id=5), [2])
    assert sent == [2]


def test_first_start_is_kept_only_when_dsp_really_runs():
    from types import SimpleNamespace as NS
    pl = NS(id=5, first_started_at="x")

    class Q:
        def filter(self, *a):
            return [pl]
    db = NS(query=lambda *a: Q())
    assert td._keep_first_starts(db, [5], "LAUNCHED") == [5] and pl.first_started_at == "x"
    assert td._keep_first_starts(db, [5], None) == [5], "РК без DSP — старт засчитан"
    assert td._keep_first_starts(db, [5], "STOPPED") == [] and pl.first_started_at is None
