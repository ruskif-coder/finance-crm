"""
Пакетный прогон сверки: одна кнопка на выбранные записи.

Главное, что здесь удерживается, — правило выбора главной компании. Порядок
привязок в базе не задан (`_links_by_our` читает без `order_by`), поэтому «первая
привязанная» — это произвольная. На Roki она указывает на компанию с нулём сделок:
пакетный прогон, взявший её якорем, молча увёз бы туда обе сделки и переименовал
пустышку в имя агентства. Поэтому запись с несколькими компаниями без явно
выбранной звёздочки не обрабатывается, а пропускается с названной причиной.

Второе — изоляция сбоев: ошибка на одной записи не должна прекращать проход,
иначе половина выбранного остаётся необработанной без следа в отчёте.
"""
import pytest
from fastapi import HTTPException

from app.routers import sales_reconcile as sr


class _FakeModel:
    """Заглушка ORM-модели: _sync_plan строит фильтр по model.id."""
    id = 0


class _Rec:
    def __init__(self, our_id, short_name):
        self.id = our_id
        self.short_name = short_name
        self.name = short_name


class _FakeQuery:
    def __init__(self, db):
        self.db = db

    def filter(self, *a, **k):
        return self

    def first(self):
        # _sync_plan делает ровно один .first() на запись, по порядку items
        return self.db.records.pop(0) if self.db.records else None


class _FakeDb:
    def __init__(self, records=()):
        self.records = list(records)
        self.rolled_back = 0

    def query(self, *a, **k):
        return _FakeQuery(self)

    def rollback(self):
        self.rolled_back += 1

    def add(self, *a, **k):
        pass

    def flush(self):
        pass

    def commit(self):
        pass


@pytest.fixture
def plan_env(monkeypatch):
    """Битрикс и справочник для _sync_plan."""
    state = {"companies": [], "links": {}, "row": {}}
    monkeypatch.setattr(sr, "_fetch_companies", lambda kind, refresh=False: state["companies"])
    monkeypatch.setattr(sr, "_record_and_links",
                        lambda db, model, kind, our_id: (None, state["row"], state["links"].get(our_id, [])))
    monkeypatch.setattr(sr, "_consolidate_plan",
                        lambda kind, row, links, primary, with_counts: (
                            {"bx_id": primary, "title": "гл", "deal_count": 1, "rename_to": "СТД"},
                            [{"bx_id": b, "title": "лишняя", "deal_count": 3,
                              "rename_to": "XXX_лишняя"} for b in links if b != primary]))
    return state


def _item(our_id, primary=None):
    return sr.SyncItemIn(our_id=our_id, primary_bx_id=primary)


# ---- план: что будет сделано ----

def test_multi_company_without_star_is_skipped(plan_env):
    """Ключевая защита: без явно выбранной главной запись НЕ склеивается.

    «Первая привязанная» — произвольная компания, и на Roki это компания с нулём
    сделок. Автоматический выбор здесь дороже пропуска.
    """
    plan_env["row"] = {"short_name": "Roki"}
    plan_env["links"] = {76: ["2050", "1640"]}
    plan = sr._sync_plan(_FakeDb([_Rec(76, "Roki")]), _FakeModel, "agencies", [_item(76)])
    assert plan[0]["action"] == "skip"
    assert "звёздочкой" in plan[0]["reason"]


def test_star_outside_own_links_is_skipped(plan_env):
    plan_env["row"] = {"short_name": "Roki"}
    plan_env["links"] = {76: ["2050", "1640"]}
    plan = sr._sync_plan(_FakeDb([_Rec(76, "Roki")]), _FakeModel, "agencies",
                         [_item(76, primary="9999")])
    assert plan[0]["action"] == "skip"
    assert "не привязана" in plan[0]["reason"]


def test_multi_company_with_star_is_consolidated(plan_env):
    plan_env["row"] = {"short_name": "Roki"}
    plan_env["links"] = {76: ["2050", "1640"]}
    plan = sr._sync_plan(_FakeDb([_Rec(76, "Roki")]), _FakeModel, "agencies",
                         [_item(76, primary="1640")])
    assert plan[0]["action"] == "consolidate"
    assert plan[0]["primary"]["bx_id"] == "1640"
    assert plan[0]["deals_to_move"] == 3


def test_single_company_is_renamed(plan_env):
    plan_env["row"] = {"short_name": "MI", "name_en": "Media Instinct"}
    plan_env["links"] = {21: ["124"]}
    plan_env["companies"] = [{"id": "124", "title": "Старое имя"}]
    plan = sr._sync_plan(_FakeDb([_Rec(21, "MI")]), _FakeModel, "agencies", [_item(21)])
    assert plan[0]["action"] == "rename"
    assert plan[0]["was"] == "Старое имя"
    assert plan[0]["now"] == "MI | Media Instinct"


def test_name_already_standard_does_nothing(plan_env):
    """Лишняя запись в боевой Битрикс — тоже цена. Совпало — не трогаем."""
    plan_env["row"] = {"short_name": "MI", "name_en": "Media Instinct"}
    plan_env["links"] = {21: ["124"]}
    plan_env["companies"] = [{"id": "124", "title": "MI | Media Instinct"}]
    plan = sr._sync_plan(_FakeDb([_Rec(21, "MI")]), _FakeModel, "agencies", [_item(21)])
    assert plan[0]["action"] == "nothing"


def test_record_without_companies_is_created(plan_env):
    plan_env["row"] = {"short_name": "AMDG"}
    plan_env["links"] = {2: []}
    plan = sr._sync_plan(_FakeDb([_Rec(2, "AMDG")]), _FakeModel, "agencies", [_item(2)])
    assert plan[0]["action"] == "create"
    assert plan[0]["now"] == "AMDG"


# ---- прогон: изоляция сбоев и отчёт ----

@pytest.fixture
def run_env(monkeypatch):
    calls = {"done": []}
    monkeypatch.setattr(sr, "log_action", lambda *a, **k: None)

    def _mk(action, fail_on=()):
        def _fn(db, model, kind, data, current_user):
            if data.our_id in fail_on:
                raise HTTPException(status_code=502, detail="Битрикс отклонил на середине")
            calls["done"].append((action, data.our_id))
            if action == "consolidate":
                return {"moved_deals": 2, "retired": 1, "rename_to": "СТД"}
            if action == "rename":
                return {"renamed": [{"bx_id": "1"}], "standard": "СТД"}
            return {"bx_id": "777", "title": "СТД"}
        return _fn

    monkeypatch.setattr(sr, "_do_consolidate", _mk("consolidate"))
    monkeypatch.setattr(sr, "_do_rename", _mk("rename"))
    monkeypatch.setattr(sr, "_do_create", _mk("create"))
    return calls, _mk


def test_failure_on_one_record_does_not_stop_the_rest(run_env, monkeypatch):
    """Иначе половина выбранного молча остаётся необработанной."""
    calls, _mk = run_env
    monkeypatch.setattr(sr, "_do_rename", _mk("rename", fail_on={2}))
    monkeypatch.setattr(sr, "_sync_plan", lambda db, model, kind, items: [
        {"our_id": 1, "name": "A", "action": "rename"},
        {"our_id": 2, "name": "B", "action": "rename"},
        {"our_id": 3, "name": "C", "action": "rename"},
    ])
    db = _FakeDb()
    res = sr.sync_run("agencies", sr.SyncIn(items=[_item(1), _item(2), _item(3)]),
                      db=db, current_user=None)
    assert [d["our_id"] for d in res["done"]] == [1, 3]
    assert [f["our_id"] for f in res["failed"]] == [2]
    assert "отклонил" in res["failed"][0]["error"]
    assert db.rolled_back == 1


def test_skipped_records_are_named_not_silent(run_env, monkeypatch):
    """Молчаливый пропуск читается как «сделано»."""
    _calls, _mk = run_env
    monkeypatch.setattr(sr, "_sync_plan", lambda db, model, kind, items: [
        {"our_id": 5, "name": "Roki", "action": "skip", "reason": "главная не выбрана"},
        {"our_id": 6, "name": "MI", "action": "nothing", "reason": "имя уже по стандарту"},
    ])
    res = sr.sync_run("agencies", sr.SyncIn(items=[_item(5), _item(6)]),
                      db=_FakeDb(), current_user=None)
    assert res["done"] == []
    assert {s["our_id"] for s in res["skipped"]} == {5, 6}
    assert all(s["reason"] for s in res["skipped"])


def test_each_action_goes_to_its_own_operation(run_env, monkeypatch):
    calls, _mk = run_env
    monkeypatch.setattr(sr, "_sync_plan", lambda db, model, kind, items: [
        {"our_id": 1, "name": "A", "action": "consolidate"},
        {"our_id": 2, "name": "B", "action": "rename"},
        {"our_id": 3, "name": "C", "action": "create"},
    ])
    # у склейки главная всегда задана: план выдаёт consolidate только при выбранной ★
    res = sr.sync_run("agencies", sr.SyncIn(items=[_item(1, primary="10"), _item(2), _item(3)]),
                      db=_FakeDb(), current_user=None)
    assert calls["done"] == [("consolidate", 1), ("rename", 2), ("create", 3)]
    assert [d["action"] for d in res["done"]] == ["consolidate", "rename", "create"]


def test_deletion_is_not_part_of_the_batch():
    """Удаление необратимо и остаётся отдельной кнопкой — пакет его не делает."""
    import inspect
    src = inspect.getsource(sr.sync_run)
    # слово retired встречается в отчёте склейки («помечено XXX_ N»), поэтому
    # проверяем именно вызовы удаления, а не упоминание
    assert "vibecode_delete" not in src
    assert "_retired_candidates" not in src
    assert "retired_delete" not in src
