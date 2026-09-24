# -*- coding: utf-8 -*-
"""Перевод сделки подчиняется правилам — везде, кроме реестра (аудит 23.09.2026, 3.M1).

Решение владельца 24.09.2026:
  · КАРТОЧКА подчиняется правилам — «чтобы привыкали ответственные»;
  · автоматические переводы (привязка медиаплана, «Завершить РК») — тоже;
  · РЕЕСТР (правка в строке, массовая) сознательно пропускает то, что нельзя, —
    временно, до разбора старых сделок. Это не дефект, и прибор ниже держит его как
    решение, чтобы его не «починили» по ошибке.

Дыра была одна на всех: вызывающие смотрели только на список блокеров, а цель,
неприменимая к услуге сделки, возвращает пустой список и признак `not_applicable`.
Автоматика вдобавок не смотрела, нужна ли воронка реализации.
"""
import io
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import sales_dashboard as sd
from app.sales import stage_move

APP = Path(__file__).resolve().parent.parent / "app"
TARGET = SimpleNamespace(id=7, name="Бронь", phase=None, is_terminal=False)


def _plan(**kw):
    return stage_move.Plan(target=TARGET, current=None, **kw)


def test_automatic_moves_ask_one_question():
    assert stage_move.may_move(_plan()) is True
    assert stage_move.may_move(_plan(not_applicable=True)) is False
    assert stage_move.may_move(_plan(needs_pipeline=True)) is False
    assert stage_move.may_move(_plan(blockers=["не выполнено"])) is False


def test_both_automatic_moves_use_it():
    for path, fn in (("routers/media_plans.py", "_advance_deal_on_link"),
                     ("routers/traffic_dashboard.py", "finish_campaign")):
        src = io.open(APP / path, encoding="utf-8").read()
        body = src[src.index(f"def {fn}("):]
        body = body[:body.index("\n@router") if "\n@router" in body else len(body)]
        body = body[:body.index("\ndef ", 10)] if "\ndef " in body[10:] else body
        assert "stage_move.may_move(plan)" in body, f"{fn}: решает по одним блокерам"


def test_the_card_refuses_a_stage_that_does_not_apply(monkeypatch):
    deal = SimpleNamespace(id=1, our_stage_id=3, realization_pipeline_id=None)

    class _Db:
        def query(self, model):
            return SimpleNamespace(filter=lambda *a: SimpleNamespace(first=lambda: deal))

    cat = SimpleNamespace(stages=[TARGET], by_id={7: TARGET}, next_of=lambda i: TARGET)
    monkeypatch.setattr(sd, "_assert_deal_in_scope", lambda db, u, d: None)
    monkeypatch.setattr(sd, "Catalog", lambda db: cat)
    monkeypatch.setattr(stage_move, "plan_move",
                        lambda db, d, t, c=None: _plan(not_applicable=True))
    monkeypatch.setattr(stage_move, "is_master", lambda u: True)
    monkeypatch.setattr(stage_move, "apply_move",
                        lambda *a, **kw: pytest.fail("карточка перевела в неприменимую стадию"))
    with pytest.raises(HTTPException) as e:
        sd.move_deal(1, sd.MoveIn(to_stage_id=7, comment="к", override_reason="мастер"),
                     _Db(), SimpleNamespace(id=1))
    assert e.value.status_code == 400 and "не относится" in e.value.detail


def test_the_registry_bypass_is_a_decision_not_a_bug():
    """Реестр переводит, глядя на блокеры и право мастера, — неприменимость и воронку
    он НЕ проверяет. Так решил владелец 24.09.2026, временно. Упал этот прибор — значит,
    реестр начали запирать: сверьтесь с владельцем, разобраны ли старые сделки."""
    src = io.open(APP / "routers/sales_dashboard.py", encoding="utf-8").read()
    body = src[src.index("def bulk_update_deals("):]
    body = body[:body.index("\n@router")]
    assert "plan.blockers and not force" in body
    assert not re.search(r"may_move\(|plan\.allowed|not_applicable", body)


# ── 7.2: «следующая стадия» — одна на все места (аудит 3.M2) ─────────────────

NEXT = SimpleNamespace(id=5, name="МП Отправлено", phase=None, is_terminal=False)
FIRST = SimpleNamespace(id=1, name="Подготовка МП", phase=None, is_terminal=False)


@pytest.fixture
def one_rule(monkeypatch):
    """`Catalog.next_of` отвечает ПЕРВОЙ стадией (как с терминала), общая функция —
    своей. Ручки обязаны спросить общую."""
    deal = SimpleNamespace(id=1, our_stage_id=9, realization_pipeline_id=None, code="X")

    class _Db:
        def query(self, model):
            return SimpleNamespace(filter=lambda *a: SimpleNamespace(first=lambda: deal))

        def rollback(self):
            pass

        def commit(self):
            pass

    cat = SimpleNamespace(stages=[FIRST, NEXT], by_id={1: FIRST, 5: NEXT},
                          next_of=lambda i: FIRST)
    # Отрисовка стадии в ответе к вопросу «куда» отношения не имеет.
    monkeypatch.setattr(sd, "stage_public", lambda *a, **kw: {})
    targets = []
    monkeypatch.setattr(sd, "_assert_deal_in_scope", lambda db, u, d: None)
    monkeypatch.setattr(sd, "_deal_by_ref", lambda db, ref: deal)
    monkeypatch.setattr(sd, "Catalog", lambda db: cat)
    monkeypatch.setattr(stage_move, "plan_move",
                        lambda db, d, t, c=None: targets.append(t) or
                        stage_move.Plan(target=t, current=None))
    monkeypatch.setattr(stage_move, "apply_move", lambda *a, **kw: {"moved": True})
    monkeypatch.setattr(sd, "log_action", lambda *a, **kw: None)
    state = SimpleNamespace(deal=deal, db=_Db(), targets=targets, cat=cat)
    return state


def test_default_target_is_the_shared_next_stage(one_rule, monkeypatch):
    monkeypatch.setattr(stage_move, "next_stage", lambda db, d, c=None: NEXT)
    db = one_rule.db
    sd.move_preview("X", None, None, db, SimpleNamespace(id=1))
    sd.move_deal(1, sd.MoveIn(comment="к"), db, SimpleNamespace(id=1))
    assert one_rule.targets == [NEXT, NEXT], (
        f"предпросмотр/кнопка ведут не туда, куда показывает карточка: {one_rule.targets}")


def test_from_a_terminal_stage_there_is_nowhere_to_go(one_rule, monkeypatch):
    monkeypatch.setattr(stage_move, "next_stage", lambda db, d, c=None: None)
    out = sd.move_preview("X", None, None, one_rule.db, SimpleNamespace(id=1))
    assert out["target"] is None
    with pytest.raises(HTTPException) as e:
        sd.move_deal(1, sd.MoveIn(comment="к"), one_rule.db, SimpleNamespace(id=1))
    assert e.value.status_code == 400 and "Некуда" in e.value.detail


# ── «Следующая» со стадии, неприменимой к услуге сделки (ревью этапа 7) ──────

def test_next_from_a_stage_outside_the_deals_chain_goes_forward():
    """Реестр сознательно ставит сделку и на неприменимую стадию (решение 24.09.2026),
    её меняют услугу посреди пути. «Следующая» оттуда — ближайшая применимая ВПЕРЕДИ,
    а не первая стадия цепочки: иначе кнопка «двинуть» отправляла сделку в начало."""
    from app.sales import stage_scope
    st = {i: SimpleNamespace(id=i, is_terminal=False) for i in (1, 2, 3, 4)}
    cat = SimpleNamespace(flow=[1, 2, 3, 4], by_id=st)
    marks = {3: {99}}                       # стадия 3 — только для чужой услуги
    deal = SimpleNamespace(our_stage_id=3, service_id=7)
    assert stage_scope.next_for(deal, cat, marks).id == 4
    deal_last = SimpleNamespace(our_stage_id=4, service_id=7)
    marks_last = {4: {99}}
    assert stage_scope.next_for(deal_last, cat, marks_last) is None
