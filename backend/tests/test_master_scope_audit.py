# -*- coding: utf-8 -*-
"""Мастер-сделка и область «свои» (аудит 21.10.2026, S3–S5).

- «Отправить в ДО» показывал соседние сделки договора с суммами сверки без фильтра «свои»;
- к чужому пакету можно было присоединиться, и после этого пакет не открывался никому из «своих»;
- реестр пускал к пакету по одной своей сделке, а карточка — только если свои все (и отдавал суммы всего пакета).
Правило одно — `scope.all_in_scope`: свои ВСЕ сделки пакета."""
from types import SimpleNamespace

from app.master_deal import scope as SC
from app.master_deal import service as MS


def test_all_in_scope(monkeypatch):
    m = SimpleNamespace(id=1)
    monkeypatch.setattr(SC, "package_owners", lambda db, m: [(1, 2), (3, 4)])
    assert SC.all_in_scope(None, m, None) and SC.all_in_scope(None, m, [1, 4])
    assert not SC.all_in_scope(None, m, [1])


def test_candidates_hide_foreign_packages(monkeypatch):
    pk = [SimpleNamespace(id=10, code="M-0010"), SimpleNamespace(id=11, code="M-0011")]

    class _Q:
        def filter(self, *a):
            return self

        def order_by(self, *a):
            return self

        def all(self):
            return pk

    class _Db:
        def query(self, *a):
            return _Q()

        def execute(self, *a, **k):
            return SimpleNamespace(fetchall=lambda: [])
    monkeypatch.setattr(SC, "all_in_scope", lambda db, m, own: m.id == 10)
    d = SimpleNamespace(ord_final_contract_id=5, period_from=__import__("datetime").date(2026, 10, 1))
    assert [c["id"] for c in MS.candidates(_Db(), d, own=[1])] == [10]
    assert [c["id"] for c in MS.candidates(_Db(), d)] == [10, 11]        # «все» — без фильтра


def test_siblings_hide_foreign_deals():
    rows = [{"id": 1, "sales_rep_id": 7, "account_manager_id": None}, {"id": 2, "sales_rep_id": 8, "account_manager_id": 9}]
    assert [r["id"] for r in MS._own_only(rows, [7])] == [1]
    assert [r["id"] for r in MS._own_only(rows, None)] == [1, 2]


def test_double_send_to_do_is_409_not_500(monkeypatch):
    """Второе «Отправить в ДО» из соседней вкладки падало на UNIQUE(deal_id) — 500 и дыра в нумерации (аудит 21.10.2026, D5)."""
    import pytest
    from fastapi import HTTPException
    from sqlalchemy.exc import IntegrityError
    from app.routers import master_deals as R
    d = SimpleNamespace(id=5, code="AAA111")
    monkeypatch.setattr(R, "_deal", lambda db, i, user: d)
    monkeypatch.setattr(R, "_lock_deals", lambda db, ids: None)

    def boom(*a, **k):
        raise IntegrityError("INSERT", {}, Exception("uq_master_deal_items_deal_id"))
    monkeypatch.setattr(R.MS, "send_with", boom)

    class _Db:
        def rollback(self):
            pass
    with pytest.raises(HTTPException) as e:
        R.deal_send(5, R.SendIn(target="new"), _Db(), SimpleNamespace(id=1))
    assert e.value.status_code == 409
