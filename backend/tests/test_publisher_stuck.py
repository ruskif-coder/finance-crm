# -*- coding: utf-8 -*-
"""«Согласования → Подвисшие» (владелец 03.10.2026): креативы, которые площадка держит
дольше трёх рабочих дней, все открытые доработки с комментарием площадки и отказы — по
сделкам до стадии «Итоговая сверка» (её саму уже не показываем)."""
from datetime import date, datetime

from app.launch_prep import matrix as M
from app.launch_prep import stuck as S

TODAY = date(2026, 9, 29)          # вторник


def _c(**kw):
    base = dict(sent_at=datetime(2026, 9, 23, 10), agreed_at=None, withdrawn_at=None,
                verdict=None, decided_at=None, state="согласование", today=TODAY)
    return S.classify(**{**base, **kw})


def test_waiting_longer_than_three_workdays_is_stuck():
    assert _c() == {"kind": "waiting", "days": 4}                      # ср → вт
    assert _c(sent_at=datetime(2026, 9, 24, 10)) is None               # чт → вт = 3, ещё нет


def test_threshold_is_the_matrix_one():
    assert S.LATE_WORKDAYS is M.LATE_WORKDAYS


def test_every_open_rework_is_shown_however_fresh():
    got = _c(sent_at=datetime(2026, 9, 28, 10), verdict="на доработку",
             decided_at=datetime(2026, 9, 29, 9))
    assert got == {"kind": "rework", "days": 0}


def test_rework_after_agreement_withdrawn_from_cabinet_is_still_rework():
    got = _c(agreed_at=datetime(2026, 9, 24), verdict="на доработку",
             decided_at=datetime(2026, 9, 25, 9))
    assert got["kind"] == "rework"


def test_refusal_is_shown():
    assert _c(verdict="отказ", decided_at=datetime(2026, 9, 28))["kind"] == "refused"
    assert _c(state="отказ площадки")["kind"] == "refused"


def test_agreed_withdrawn_or_unsent_are_not_stuck():
    assert _c(agreed_at=datetime(2026, 9, 24)) is None
    assert _c(state="ерид получен") is None
    assert _c(withdrawn_at=datetime(2026, 9, 25)) is None
    assert _c(sent_at=None) is None


def test_load_respects_stage_cutoff_and_groups_by_publisher():
    """На живой базе стенда: ни одной сделки со «Итоговой сверки» и дальше, ни одной
    проигранной; площадки отсортированы по самому долгому ожиданию."""
    from sqlalchemy import text
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        out = S.load(db, date.today())
        deals = {r["deal_id"] for p in out["publishers"] for r in p["rows"]}
        if deals:
            bad = db.execute(text("""
                SELECT d.id FROM sales_deals d
                  JOIN sales_stages s ON s.id = d.our_stage_id
                  JOIN sales_stage_phases ph ON ph.id = s.phase_id
                 WHERE d.id = ANY(:ids)
                   AND (s.is_lost OR (ph.sort_order, s.sort_order) >= (
                        SELECT ph2.sort_order, s2.sort_order FROM sales_stages s2
                          JOIN sales_stage_phases ph2 ON ph2.id = s2.phase_id
                         WHERE s2.name = 'Итоговая сверка'))
            """), {"ids": list(deals)}).all()
            assert not bad
        keys = [(p["burning"], p["max_days"]) for p in out["publishers"]]
        assert keys == sorted(keys, reverse=True)
        for p in out["publishers"]:
            assert {"tg", "max"} <= set(p)
            for r in p["rows"]:
                if r["kind"] == "rework":
                    assert r["reason"], "доработка без комментария площадки"
    finally:
        db.close()


def test_route_has_the_approvals_permission():
    import inspect
    from app.routers import publisher_matrix as R
    assert "stuck" in inspect.getsource(R) and "VIEW" in inspect.getsource(R.get_stuck)


def test_target_refusal_marks_only_sent_pairs():
    """Отказ — свойство получателя; неотправленная пара его строкой не становится."""
    assert _c(state="отказ площадки", sent_at=None) is None


def test_rework_on_agreed_target_is_not_shown():
    """Получатель уже согласован/в размещении — старая доработка не висит."""
    assert _c(state="ерид получен", verdict="на доработку", decided_at=datetime(2026, 9, 25)) is None


def test_replaced_set_rework_is_not_open():
    """Доработку закрыл новый комплект (replaces_set_id) — старая пара остаётся историей,
    в «Подвисших» её нет (ревью 03.10.2026: на стенде таких было 8)."""
    from sqlalchemy import text
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        shown = {r["pair_id"] for p in S.load(db)["publishers"] for r in p["rows"]}
        old = {x for (x,) in db.execute(text("""
            SELECT p.id FROM launch_prep_pair p JOIN launch_prep_target t ON t.id = p.target_id
             WHERE EXISTS (SELECT 1 FROM launch_prep_creative_set n
                            WHERE n.replaces_set_id = p.set_id AND n.publisher_id = t.publisher_id)
        """))}
        assert not shown & old
    finally:
        db.close()


# «Горит / срочно / терпит» — по старту размещения (владелец 03.10.2026); то же правило,
# что «просрочено / срочно» в кабинете площадки (cabinet-frontend/lib/urgency.js).
def test_start_passed_is_burning():
    assert S.start_urgency(date(2026, 9, 28), TODAY) == "burning"


def test_three_workdays_to_start_is_urgent():
    assert S.start_urgency(TODAY, TODAY) == "urgent"                  # старт сегодня
    assert S.start_urgency(date(2026, 10, 2), TODAY) == "urgent"      # вт → пт = 3
    assert S.start_urgency(date(2026, 10, 5), TODAY) == "calm"        # вт → пн = 4


def test_no_start_is_calm():
    assert S.start_urgency(None, TODAY) == "calm"


def test_burning_rows_go_first():
    rows = [{"urgency": "calm", "days": 9, "deal_code": "A", "code": "1"},
            {"urgency": "burning", "days": 1, "deal_code": "B", "code": "2"},
            {"urgency": "urgent", "days": 5, "deal_code": "C", "code": "3"}]
    assert [r["urgency"] for r in S.order_rows(rows)] == ["burning", "urgent", "calm"]
