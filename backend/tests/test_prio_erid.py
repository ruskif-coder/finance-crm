# -*- coding: utf-8 -*-
"""ЕРИД площадки приоритезации выпускает наш ОРД после её «ок» — как у комплекта креативов, но текстом, а не баннером
(владелец 04.11.2026).

Поломки, которые ловит:
  * тело запроса не проходит схему ОРД или требует файл, которого у приоритезации нет (форма должна быть `Text`);
  * выпуск пишет в журнал под видом `creative` — тогда его id спутался бы с комплектом с тем же номером;
  * «Запустить» уходит в систему приоритезации без готового маркера;
  * сбой ОРД после «ок» отменяет согласование площадки;
  * крон автовыпуска не видит площадки приоритезации или теряет их сбой.
"""
import io
import json
import os
from types import SimpleNamespace

import pytest

from app.launch_prep import erid_auto
from app.ord import payloads, readiness
from app.ord import submit as ord_submit
from app.prio import erid as E
from app.prio import launch as L
from app.prio import models as M
from app.prio import service as S
from tests.test_ord_payloads import check
from tests.test_prio import FakeApi, _U, _sent, env  # noqa: F401 — фикстура

SPEC = os.path.join(os.path.dirname(__file__), 'fixtures', 'mediascout_v3_schemas.json')
BRAND = SimpleNamespace(kktu_code="12.2.2", ad_object_description=None)
REQ = SimpleNamespace(product_name="Аллервэй 5мг", target_mnn="левоцетиризин", date_start=None, date_end=None)


@pytest.fixture(scope='module')
def schemas():
    with io.open(SPEC, encoding='utf-8') as f:
        return json.load(f)['components']['schemas']


def _p(**kw):
    return SimpleNamespace(**{"id": 41, "product_url": "https://apteka.example/p/1", **kw})


def test_prio_creative_is_text_without_file_and_passes_the_schema(schemas):
    body = payloads.prio_creative(_p(), REQ, SimpleNamespace(code="ABC123", is_self_promo=False), BRAND, "CT-final", "CT-init")
    check(schemas, 'CreateCreativeRequest', body)
    assert body["form"] == "Text" and "mediaData" not in body
    assert body["textData"] == [{"textData": "Аллервэй 5мг (левоцетиризин)"}]
    assert body["advertiserUrls"] == ["https://apteka.example/p/1"]
    assert body["nativeCustomerId"] == "prio-41" and body["kktuCodes"] == ["12.2.2"]
    assert body["initialContractId"] == "CT-init" and body["type"] == "CPM"


@pytest.mark.parametrize("p,brand,word", [
    (_p(product_url=None), BRAND, "посадочная"),
    (_p(), SimpleNamespace(kktu_code=None, ad_object_description=None), "ККТУ"),
])
def test_prio_creative_refuses_what_ord_would_reject(p, brand, word):
    with pytest.raises(payloads.OrdPayloadError) as e:
        payloads.prio_creative(p, REQ, SimpleNamespace(code="ABC123"), brand, "CT-final")
    assert word in str(e.value)


def _approved_no_erid(db, d, pub):
    p = _sent(db, d, pub)
    S.set_sku(db, p, "1234567")
    return S.verdict(db, p, "ок", None)


def _no_network_ord(monkeypatch, db, answer):
    """Цепочка, бренд и ответ ОРД — подменены; коммиты журнала — flush (тест в транзакции, которую откатывает фикстура)."""
    monkeypatch.setattr(db, "commit", db.flush)
    monkeypatch.setattr("app.launch_prep.erid_service._ord_chain", lambda db_, deal: ("CT-final", "CT-init"))
    monkeypatch.setattr(E, "_brand", lambda db_, deal: BRAND)
    monkeypatch.setattr(E, "emit", lambda *a, **k: None)
    sent = []

    def post(path, body):
        sent.append((path, body))
        return 201, answer
    monkeypatch.setattr(ord_submit.client, "post", post)
    return sent


def test_issue_registers_as_prio_creative_and_fills_the_placement(env, monkeypatch):  # noqa: F811
    from app.ord.models import OrdSubmission
    db, d, pubs = env
    p = _approved_no_erid(db, d, pubs[0])
    sent = _no_network_ord(monkeypatch, db, {"id": "CR-1", "erid": "Kra1", "status": "Registering"})
    E.issue(db, d, p, None)
    assert sent and sent[0][1]["form"] == "Text" and sent[0][1]["nativeCustomerId"] == f"prio-{p.id}"
    assert (p.erid, p.ord_creative_id, p.ord_status) == ("Kra1", "CR-1", "Registering")
    assert p.ord_env == ord_submit.client.env() and readiness.erid_ready(p)
    row = db.query(OrdSubmission).filter(OrdSubmission.local_id == p.id, OrdSubmission.ord_id == "CR-1").one()
    assert row.kind == "prio_creative", "журнал под видом creative спутал бы площадку с комплектом того же номера"
    # повтор — не второй креатив, а опрос
    monkeypatch.setattr(ord_submit.client, "get", lambda path, params=None: {"erid": "Kra1", "status": "Active"})
    p.erid = None
    E.issue(db, d, p, None)
    assert len(sent) == 1 and p.ord_status == "Active"


def test_launch_waits_for_a_ready_marker(env):  # noqa: F811
    db, d, pubs = env
    p = _approved_no_erid(db, d, pubs[0])
    api = FakeApi()
    with pytest.raises(S.PrioError) as e:
        L.launch(db, d, p.id, client=api)
    assert e.value.status == 409 and "ЕРИД" in e.value.message and api.created == 0
    p.erid, p.ord_status, p.ord_env = "Kra1", "RegistrationError", "demo"
    db.flush()
    with pytest.raises(S.PrioError):
        L.launch(db, d, p.id, client=api)
    assert api.created == 0, "маркер с отказом ЕРИР ушёл в систему приоритезации"
    p.ord_status = "Active"
    db.flush()
    assert L.launch(db, d, p.id, client=api).status == M.LIVE
    assert api.camps[p.camp_id]["erid"] == "Kra1"


def test_ord_failure_after_ok_keeps_the_approval(env, monkeypatch):  # noqa: F811
    db, d, pubs = env
    p = _approved_no_erid(db, d, pubs[0])
    monkeypatch.setattr(E, "blockers", lambda db_, deal, p_: [])

    def boom(*a, **k):
        raise S.PrioError(400, "ОРД не ответил")
    monkeypatch.setattr(E, "issue", boom)
    real_rollback = db.rollback
    db.rollback = lambda: None              # откат сессии стёр бы фикстуру; в бою он чистит только упавшую попытку
    try:
        E.issue_after_verdict(db, p.id)
    finally:
        db.rollback = real_rollback
    assert p.status == M.APPROVED and not p.erid


def test_cron_part_issues_approved_and_names_what_blocks(env, monkeypatch):  # noqa: F811
    db, d, pubs = env
    a = _approved_no_erid(db, d, pubs[0])
    b = _approved_no_erid(db, d, pubs[1])
    monkeypatch.setattr(E, "blockers", lambda db_, deal, p: ["нет посадочной"] if p.id == b.id else [])

    def fake_issue(db_, deal, p, actor):
        p.erid, p.ord_status, p.ord_env = f"K{p.id}", "Active", "demo"
        return {"erid": p.erid, "status": "Active"}
    monkeypatch.setattr(E, "issue", fake_issue)
    monkeypatch.setattr(E, "refresh", lambda *a_, **k: {"status": "Active"})
    out = E.run_part(db)
    assert f"П{a.id}" in [x["set_id"] for x in out["issued"]]
    assert {"set_id": f"П{b.id}", "deal": d.code, "why": ["нет посадочной"]} in out["blocked"]


def test_cron_merges_prio_into_the_common_report(monkeypatch):
    part = {"issued": [{"set_id": "П1", "deal": "X"}], "pending": [], "blocked": [], "failed": [{"set_id": "П2", "deal": "Y", "error": "e"}],
            "checked": 3, "changed": [], "refresh_failed": [{"set_id": "П3", "error": "403"}]}
    monkeypatch.setattr(E, "run_part", lambda db, dry_run=False: part)
    issued = {"issued": [], "pending": [], "blocked": [], "failed": []}
    refreshed = {"checked": 1, "changed": [], "failed": []}
    erid_auto._merge_prio(None, issued, refreshed, False)
    assert issued["issued"] == part["issued"] and issued["failed"] == part["failed"]
    assert refreshed["checked"] == 4 and refreshed["failed"] == part["refresh_failed"]
    assert erid_auto.should_alert(None, {"issue": issued, "refresh": refreshed}), "сбой приоритезации не поднял тревогу"


def test_cron_part_crash_is_a_failure_not_silence(monkeypatch):
    def crash(db, dry_run=False):
        raise RuntimeError("упало")
    monkeypatch.setattr(E, "run_part", crash)
    db = SimpleNamespace(rollback=lambda: None)
    issued = {"issued": [], "pending": [], "blocked": [], "failed": []}
    erid_auto._merge_prio(db, issued, {"checked": 0, "changed": [], "failed": []}, False)
    assert issued["failed"] and "упало" in issued["failed"][0]["error"]


def test_status_is_asked_right_after_registration_without_one(env, monkeypatch):  # noqa: F811
    """ОРД отвечает на регистрацию без статуса — без него маркер не «готов», и «Запустить» ждал бы крона до получаса."""
    db, d, pubs = env
    p = _approved_no_erid(db, d, pubs[0])
    _no_network_ord(monkeypatch, db, {"id": "CR-2", "erid": "Kra2"})
    monkeypatch.setattr(ord_submit.client, "get", lambda path, params=None: {"erid": "Kra2", "status": "RegistrationRequired"})
    E.issue(db, d, p, None)
    assert p.ord_status == "RegistrationRequired" and readiness.erid_ready(p)


def test_ord_refusal_is_written_on_the_placement_and_not_resent_by_cron(env, monkeypatch):  # noqa: F811
    """Ревью 05.11.2026: отказ ОРД (4xx) уходил только в журнал попыток — строка площадки висела «выпускается…», а крон
    каждые полчаса слал тот же неверный запрос. Причина — на строке; повтор — после правки данных аккаунтом."""
    from app.ord.client import OrdError
    db, d, pubs = env
    p = _approved_no_erid(db, d, pubs[0])
    _no_network_ord(monkeypatch, db, {})

    def refuse(path, body):
        raise OrdError(400, "advertiserUrls: неверный адрес")
    monkeypatch.setattr(ord_submit.client, "post", refuse)
    with pytest.raises(S.PrioError):
        E.issue(db, d, p, None)
    assert p.ord_error and "неверный адрес" in p.ord_error
    called = []
    monkeypatch.setattr(E, "issue", lambda *a, **k: called.append(1) or {})
    monkeypatch.setattr(E, "refresh", lambda *a, **k: {"status": None})
    E.run_part(db)
    assert not called, "крон повторил отказанный запрос без правки данных"
    S.edit_placement(db, d, p.id, {"product_url": "https://shop.example/new"})
    assert p.ord_error is None, "правка посадочной снимает отказ — крон повторит выпуск"


def test_landing_and_product_are_frozen_once_the_erid_exists(env):  # noqa: F811
    """Ревью 05.11.2026: после выпуска ЕРИД посадочная и название товара менялись молча — креатив в ЕРИР расходился с запуском."""
    db, d, pubs = env
    p = _approved_no_erid(db, d, pubs[0])
    p.erid = "Kra-frozen"
    db.flush()
    with pytest.raises(S.PrioError):
        S.edit_placement(db, d, p.id, {"product_url": "https://shop.example/other"})
    with pytest.raises(S.PrioError):
        S.save_common(db, d, {"product_name": "Другой товар"}, None)


def test_registration_error_is_final_for_polling():
    assert "RegistrationError" in E.FINAL_STATUSES
