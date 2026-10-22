# -*- coding: utf-8 -*-
"""ДС и область видимости «свои» (аудит 21.10.2026, S1/S6/S7).

Ни одна ручка `/annexes/{id}*` (чтение, PDF, DOCX, правка, подтверждение) и заявки юристу по ДС не проверяли, чьи сделки
в документе: роль «свои» перебором id скачивала ДС чужих сделок — суммы, реквизиты, — в том числе ДС мастер-пакетов мимо
строгого `_master_ro`. Правило — как у карточки мастер-сделки: документ «свой», если свои ВСЕ его сделки; ДС без сделок —
только автору. Прибор `test_deal_scope` этот роутер не видел: он ищет в теле ручки `query(SalesDeal)`."""
import ast
import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.sales import scope as SC


@pytest.mark.parametrize("owners,own,created_by,uid,want", [
    ([(1, 2)], None, None, 9, True),               # роль «все»
    ([(1, 2), (3, 4)], [1, 4], None, 9, True),     # все сделки свои (продавец или аккаунт)
    ([(1, 2), (5, 6)], [1], None, 9, False),       # одна чужая — документ не свой
    ([], [1], 9, 9, True),                          # ДС без сделок — автору
    ([], [1], 7, 9, False),                         # …и только ему
    ([(1, 2)], [], None, 9, False),                 # «свои» без привязки к продавцу — ничего
])
def test_annex_visible_rule(owners, own, created_by, uid, want):
    assert SC.annex_visible(owners, own, created_by, uid) is want


def test_annex_lookup_refuses_foreign_document(monkeypatch):
    from app.routers import annexes as R
    a = SimpleNamespace(id=5, created_by=None)

    class _Q:
        def filter(self, *a):
            return self

        def first(self):
            return a

    class _Db:
        def query(self, *a):
            return _Q()
    monkeypatch.setattr(SC, "own_rep_ids_or_all", lambda db, user, section="sales_registry": [1])
    monkeypatch.setattr(SC, "annex_owners", lambda db, ids: {5: [(8, 9)]})
    with pytest.raises(HTTPException) as e:
        R._annex(_Db(), 5, SimpleNamespace(id=3))
    assert e.value.status_code == 403
    assert R._annex(_Db(), 5) is a                  # служебный вызов без пользователя — без проверки


def _routes(module):
    """(путь, функция) всех ручек модуля."""
    out = []
    for name, fn in inspect.getmembers(module, inspect.isfunction):
        for r in getattr(module, "router").routes:
            if getattr(r, "endpoint", None) is fn:
                out.append((r.path, fn))
    return out


def _calls_scoped_lookup(fn) -> bool:
    """В теле ручки ДС берётся через `_annex(db, id, user)` или проверяется `annex_in_scope`."""
    tree = ast.parse(inspect.getsource(fn).lstrip())
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            name = getattr(n.func, "id", None) or getattr(n.func, "attr", None)
            if name == "_annex" and len(n.args) >= 3:
                return True
            if name == "annex_in_scope":
                return True
    return False


@pytest.mark.parametrize("modname", ["app.routers.annexes", "app.routers.legal_requests"])
def test_every_annex_route_checks_scope(modname):
    import importlib
    mod = importlib.import_module(modname)
    bad = [p for p, fn in _routes(mod) if "{annex_id}" in p and not _calls_scoped_lookup(fn)]
    assert not bad, f"ручки ДС без проверки области «свои»: {bad}"


def test_legal_request_create_checks_annex_scope():
    """Заявка юристу заводится по annex_id из тела — без проверки ею блокировали выпуск чужого ДС."""
    from app.routers import legal_requests as LR
    assert _calls_scoped_lookup(LR.create)


@pytest.mark.parametrize("fn", ["create_annex", "preview"])
def test_deal_ids_from_request_are_scoped(fn):
    """Сделки, присланные в теле или в адресе, — через `_scope_deal_ids`: иначе разнесение выручки писалось в чужие сделки."""
    from app.routers import annexes as R
    assert "_scope_deal_ids" in inspect.getsource(getattr(R, fn))
