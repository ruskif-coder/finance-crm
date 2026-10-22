# -*- coding: utf-8 -*-
"""Юр запросы (спринт 3, 14.10.2026): заявка от ДС на пункт после МП, правка — в шаблон договора, открытая заявка блокирует выпуск."""
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.model_registry  # noqa: F401
from app.legal import service as S
from app.permissions import SECTIONS
from app.routers import annexes as A
from app.routers import legal_requests as R
from app.legal import service as legal_service

BLOCKS = [{"id": "p1", "title": "Предмет"}, {"id": "tbl", "sys": "table"}, {"id": "p5", "title": "Экземпляры"}]
USER = SimpleNamespace(id=7)


def _annex(no=None, frozen=False):
    return SimpleNamespace(id=10, contract_id=20, no=no, blocks={"blocks": []} if frozen else None)


class _Db:
    def __init__(self):
        self.added = []

    def add(self, x):
        self.added.append(x)


def test_request_goes_only_to_lawyer_zone_and_only_from_a_draft():
    r = S.create(_Db(), _annex(), BLOCKS, "p5", "  поправить срок  ", USER)
    assert (r.status, r.text, r.block_id, r.contract_id, r.created_by) == ("открыта", "поправить срок", "p5", 20, 7)
    assert S.create(_Db(), _annex(), BLOCKS, None, "добавить пункт", USER).block_id is None      # новый пункт
    assert S.create(_Db(), _annex(no=1, frozen=True), BLOCKS, "p5", "x", USER).annex_id == 10   # подтверждённое конструктором — можно
    for args, code in (((_annex(), BLOCKS, "p1", "x"), 400),          # зона аккаунта — правит сам
                       ((_annex(), BLOCKS, "p5", "  "), 400),         # пустой текст
                       ((_annex(no=3), BLOCKS, "p5", "x"), 409)):     # подтверждённое до конструктора
        with pytest.raises(S.LegalError) as e:
            S.create(_Db(), *args, USER)
        assert e.value.status == code


def _req(status="открыта", created=None):
    return SimpleNamespace(id=1, contract_id=20, status=status, created_at=created or datetime(2026, 10, 14, 10),
                           taken_by=None, taken_at=None, closed_by=None, closed_at=None, answer=None, result_version_id=None)


def test_done_needs_a_template_version_saved_after_the_request(monkeypatch):
    monkeypatch.setattr(S.tpl, "custom_of", lambda db, cid: None)
    with pytest.raises(S.LegalError) as e:
        S.done(None, _req(), USER)
    assert e.value.status == 409
    monkeypatch.setattr(S.tpl, "custom_of", lambda db, cid: SimpleNamespace(id=5))
    monkeypatch.setattr(S.tpl, "current", lambda db, tid: SimpleNamespace(id=99, created_at=datetime(2026, 10, 14, 9)))
    with pytest.raises(S.LegalError):
        S.done(None, _req(), USER)                                    # версия старее заявки — правки нет
    monkeypatch.setattr(S.tpl, "current", lambda db, tid: SimpleNamespace(id=99, created_at=datetime(2026, 10, 14, 11)))
    r = S.done(None, _req(), USER, "сделал")
    assert (r.status, r.result_version_id, r.answer, r.closed_by, r.taken_by) == ("сделана", 99, "сделал", 7, 7)


def test_take_and_reject():
    r = S.take(_req(), USER)
    assert r.status == "в работе" and r.taken_by == 7
    with pytest.raises(S.LegalError):
        S.take(r, USER)
    with pytest.raises(S.LegalError) as e:
        S.reject(_req(), USER, " ")
    assert e.value.status == 400                                      # отказ без ответа аккаунту
    assert S.reject(_req("в работе"), USER, "так нельзя").status == "отклонена"
    with pytest.raises(S.LegalError):
        S.reject(_req("сделана"), USER, "x")


def test_open_request_blocks_confirm_and_clean_exports_but_not_client_files(monkeypatch):
    monkeypatch.setattr(legal_service, "blocking_reason", lambda db, aid: "открыта заявка")
    monkeypatch.setattr(A, "_annex", lambda db, i, *a: SimpleNamespace(id=1, no=None, contract_id=2))
    for call in (lambda: A.confirm_annex(1, A.ConfirmIn(), None, USER),
                 lambda: A.annex_pdf(1, None, USER, with_basis=False),
                 lambda: A.annex_docx(1, None, USER, with_basis=False)):
        with pytest.raises(HTTPException) as e:
            call()
        assert e.value.status_code == 409 and "открыта заявка" in e.value.detail
    monkeypatch.setattr(A, "_doc", lambda db, a: (_ for _ in ()).throw(RuntimeError("дошли до сборки")))
    with pytest.raises(RuntimeError):
        A.annex_docx(1, None, USER, with_basis=True)                  # клиентский файл не блокируется


def test_section_lives_in_finance_and_lawyer_routes_need_it():
    sec = next(s for s in SECTIONS if s["key"] == "legal_requests")
    assert sec["group"] == "Финансы" and sec["label"] == "Юр запросы"
    paths = {(r.path, tuple(r.methods)[0]): r for r in R.router.routes}
    assert {p for p, _ in paths} >= {"", "/annex/{annex_id}", "/{rid}/take", "/{rid}/done", "/{rid}/reject"}


def test_blocking_reason_counts_open_only(monkeypatch):
    monkeypatch.setattr(S, "open_for_annex", lambda db, aid: [])
    assert S.blocking_reason(None, 1) is None
    monkeypatch.setattr(S, "open_for_annex", lambda db, aid: [1, 2])
    assert "2" in S.blocking_reason(None, 1)


def test_done_rebuilds_a_confirmed_annex_but_not_a_draft(monkeypatch):
    """Владелец 14.10.2026: «ДС не пересоздался с учётом правок юриста автоматически»."""
    from app.routers import annexes as A2
    calls = []
    monkeypatch.setattr(A2, "rebuild_frozen", lambda db, a, c: calls.append(a.id))
    monkeypatch.setattr(A2, "_sent_to_onec", lambda a: False)

    class Db:
        def __init__(self, a):
            self.a = a

        def query(self, m):
            return SimpleNamespace(filter=lambda *x: SimpleNamespace(first=lambda: self.a if m is R.SalesAnnex else SimpleNamespace(id=20)))
    confirmed = SimpleNamespace(id=10, no=1, number="Приложение № 1", contract_id=20, blocks={"blocks": []})
    assert "пересоздано" in R._rebuild_annex_of(Db(confirmed), SimpleNamespace(annex_id=10))
    assert calls == [10]
    draft = SimpleNamespace(id=11, no=None, number=None, contract_id=20, blocks=None)
    assert R._rebuild_annex_of(Db(draft), SimpleNamespace(annex_id=11)) is None and calls == [10]


def test_customs_behind_lists_only_changed_and_route_beats_template_id(monkeypatch):
    from app.annex_tpl import service as T
    from app.routers import annex_templates as AT
    rows = [SimpleNamespace(id=1, contract_id=11), SimpleNamespace(id=2, contract_id=12)]
    q = SimpleNamespace(filter=lambda *a: q, order_by=lambda *a: SimpleNamespace(all=lambda: rows))
    monkeypatch.setattr(T, "base_state", lambda db, t: {"changed": t.id == 2, "known": 1, "now": 3})
    out = T.customs_behind(SimpleNamespace(query=lambda m: q))
    assert out == [{"template_id": 2, "contract_id": 12, "known": 1, "now": 3}]
    paths = [r.path for r in AT.router.routes]
    assert paths.index("/behind") < paths.index("/{template_id}")      # иначе «behind» ушёл бы в id шаблона


def test_closed_and_taken_go_to_author_and_every_lawyer(monkeypatch):
    """Владелец 16.10.2026: как конвейер согласований — «взята / выполнена / отклонена» видят автор заявки и ВСЕ юристы."""
    from types import SimpleNamespace
    import app.notify.legal as NL
    from app.database import SessionLocal
    from app.notify.recipients import by_staff_group
    sent = []
    monkeypatch.setattr(NL, "emit", lambda db, key, **k: sent.append((key, k.get("user_ids"))))
    db = SessionLocal()
    try:
        lawyers = by_staff_group(db, "legal")
        r = SimpleNamespace(annex_id=1, contract_id=1, text="t", answer=None, status="сделана", created_by=-7, taken_by=None)
        NL.taken(db, r, "1", None)
        NL.closed(db, r, "1", None)
        for key, ids in sent:
            assert ids[0] == -7 and set(lawyers) <= set(ids), key
    finally:
        db.close()
