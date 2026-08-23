"""
Пакетная привязка кандидатов — вторая колонка сверки.

Привязка касается только нашей базы: в Битрикс не уходит ничего, любую связь
снимают крестиком. Поэтому предпросмотра здесь нет, а вся цена ошибки — в отчёте.

Главный сценарий отказа: две наши записи предложили одну и ту же компанию.
Первая привяжется, вторая получит 409 — и это обязано быть названо поимённо,
иначе оператор увидит «готово» и решит, что связалось всё выбранное.
"""
import pytest
from fastapi import HTTPException

from app.routers import sales_reconcile as sr
from app.sales.models import SalesAgency


class _Rec:
    def __init__(self, our_id, name):
        self.id = our_id
        self.short_name = name
        self.name = name


class _Query:
    def __init__(self, recs):
        self.recs = recs

    def filter(self, *a, **k):
        return self

    def all(self):
        return self.recs


class _FakeDb:
    def __init__(self, recs=()):
        self.recs = list(recs)
        self.rolled_back = 0

    def query(self, *a, **k):
        return _Query(self.recs)

    def rollback(self):
        self.rolled_back += 1


@pytest.fixture
def linker(monkeypatch):
    """Подменяет саму привязку: тело уже покрыто, здесь проверяется обход по списку."""
    state = {"linked": [], "fail": {}}

    def _do(db, model, kind, data, current_user):
        if data.our_id in state["fail"]:
            raise HTTPException(status_code=409, detail=state["fail"][data.our_id])
        state["linked"].append((data.our_id, data.bx_id, data.master))
        return {"ok": True}
    monkeypatch.setattr(sr, "_do_link", _do)
    monkeypatch.setattr(sr, "log_action", lambda *a, **k: None)
    return state


def _payload(pairs, master="ours"):
    return sr.LinkManyIn(items=[sr.LinkManyItemIn(our_id=i, bx_id=b) for i, b in pairs],
                         master=master)


def test_all_selected_are_linked(linker):
    db = _FakeDb([_Rec(1, "Nectarin"), _Rec(2, "MGCom")])
    res = sr.link_many("agencies", _payload([(1, "10"), (2, "20")]), db=db, current_user=None)
    assert linker["linked"] == [(1, "10", "ours"), (2, "20", "ours")]
    assert [d["name"] for d in res["done"]] == ["Nectarin", "MGCom"]
    assert res["failed"] == []


def test_conflict_does_not_stop_the_rest_and_is_named(linker):
    """Две записи на одну компанию — штатный случай, а не сбой прогона."""
    linker["fail"] = {2: "Компания уже привязана к «Nectarin»"}
    db = _FakeDb([_Rec(1, "Nectarin"), _Rec(2, "Нектарин Медиа"), _Rec(3, "MGCom")])
    res = sr.link_many("agencies", _payload([(1, "10"), (2, "10"), (3, "30")]),
                       db=db, current_user=None)
    assert [d["our_id"] for d in res["done"]] == [1, 3]
    assert res["failed"][0]["name"] == "Нектарин Медиа"
    assert "Nectarin" in res["failed"][0]["error"]
    assert db.rolled_back == 1


def test_master_is_passed_through(linker):
    db = _FakeDb([_Rec(1, "A")])
    sr.link_many("agencies", _payload([(1, "10")], master="bitrix"), db=db, current_user=None)
    assert linker["linked"][0][2] == "bitrix"


def test_unknown_record_still_reported_by_id(linker):
    """Имя не нашлось — запись всё равно должна быть в отчёте, а не исчезнуть."""
    linker["fail"] = {99: "Запись не найдена"}
    db = _FakeDb([])
    res = sr.link_many("agencies", _payload([(99, "10")]), db=db, current_user=None)
    assert res["failed"][0]["name"] == "#99"


def test_bitrix_is_not_touched():
    """Привязка — только наша база. Появление записи в Битрикс здесь означало бы,
    что пакетная кнопка делает больше, чем обещает её название."""
    import inspect
    src = inspect.getsource(sr.link_many) + inspect.getsource(sr._do_link)
    for call in ("vibecode_post", "vibecode_patch", "vibecode_delete"):
        assert call not in src, f"{call} в привязке — она не должна писать в Битрикс"


def test_model_is_resolved_from_kind():
    assert sr._kind_or_400("agencies") is SalesAgency
