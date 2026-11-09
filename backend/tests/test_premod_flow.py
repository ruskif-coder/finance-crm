# -*- coding: utf-8 -*-
"""Премодерация SSP: забор очереди, пакеты, решения, экран, права (07.11.2026, экран по макету 08.11).

Решения владельца, которые здесь держатся:
- одна картинка на разных площадках — ОДИН пакет, смотрим её один раз;
- новая заявка к уже решённому пакету сама не одобряется — ждёт клика, с подсказкой и отметкой
  `followed_package` (статистика для будущего автоодобрения);
- «Одобрить чистые» одобряет только пакеты без нарушений — сервер проверяет сам, фронту не верит;
- в SSP ничего не отправляется — `sent_at` пуст.

Тесты пишут только свои строки (uuid `zz-premod-…`, роли `zz_pm_*`) и убирают их вместе с журналом.
Кабинет SSP и песочница — подменные.
"""
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.main as main
from app.database import SessionLocal
from app.models import Role, RolePermission, User
from app.premod import board as B
from app.premod import service, sync as S
from app.premod.models import PremodAdvertiser, PremodDecision, PremodPackage, PremodRequest
from app.routers import auth
from tests.test_premod_markup import creative

TEST_INN = "7700000000"   # ИНН из образца разметки; на стенде такого заказчика нет


class Ssp:
    """Подменный кабинет: список заявок и разметка по ссылке предпросмотра."""

    def __init__(self):
        self.items, self.markup, self.fetched, self.stashed = [], {}, [], []

    def add(self, uuid_, erid, html, updated="2026-11-07 10:00:00", publishers=(1,)):
        self.items = [i for i in self.items if i["uuid"] != uuid_]
        url = f"https://preview.example/{uuid_}/{updated}"
        self.items.append({"uuid": uuid_, "erid": erid, "crid": "cr-" + uuid_, "status": 0, "updated_at": updated,
                           "moderated_by": "", "preview_url": url, "publishers": list(publishers)})
        self.markup[url] = html

    def run(self, db, recheck=False):
        def fetch_markup(url):
            self.fetched.append(url)
            return self.markup[url]

        def stash(root, html):
            self.stashed.append(html)
            return "zz-token-" + uuid.uuid4().hex[:8], "index.html"

        return S.sync(db, fetch_list=lambda: list(self.items), fetch_markup=fetch_markup, stash=stash,
                      recheck=recheck)


@pytest.fixture
def db():
    s = SessionLocal()
    tag = "zz-premod-" + uuid.uuid4().hex[:8]
    yield s, tag
    s.rollback()
    ids = [r[0] for r in s.execute(text("SELECT id FROM premod_request WHERE ssp_uuid LIKE :t"), {"t": tag + "%"})]
    s.execute(text("DELETE FROM premod_decision WHERE request_id = ANY(:i)"), {"i": ids or [0]})
    s.execute(text("DELETE FROM premod_request WHERE id = ANY(:i)"), {"i": ids or [0]})
    # Пакеты — по токену подменного снимка: заявка, переехавшая в новый пакет, старый уже не называет.
    pkgs = [r[0] for r in s.execute(text("SELECT id FROM premod_package WHERE snapshot_token LIKE 'zz-token-%'"))]
    orphans = """p.id = ANY(:p) AND NOT EXISTS (SELECT 1 FROM premod_request r WHERE r.package_id = p.id)"""
    s.execute(text(f"UPDATE premod_package p SET prev_package_id = NULL WHERE {orphans}"), {"p": pkgs or [0]})
    s.execute(text(f"DELETE FROM premod_package p WHERE {orphans}"), {"p": pkgs or [0]})
    s.execute(text("""DELETE FROM premod_advertiser a WHERE a.inn = :inn
                       AND NOT EXISTS (SELECT 1 FROM premod_package p WHERE p.advertiser_inn = a.inn)"""),
              {"inn": TEST_INN})
    s.execute(text("DELETE FROM audit_log WHERE entity_type = 'premod_package' AND entity_id = ANY(:p)"),
              {"p": pkgs or [0]})
    s.commit()
    s.close()


def _banner(tag, n=1):
    """Свой баннер на тест: хеш пакета не должен совпасть с живыми данными стенда."""
    return f"https://cdn.example/{tag}/{n}.gif"


def _any_user(db):
    return db.query(User).filter(User.is_active == 1).order_by(User.id).first()


def _pkg_of(s, uuid_):
    return s.query(PremodRequest).filter(PremodRequest.ssp_uuid == uuid_).one().package_id


def _view(s, pkg_id):
    return next(p for p in B.board(s, True, [])["packages"] if p["id"] == pkg_id)


def test_one_picture_on_two_publishers_is_one_package_and_snapshot_has_no_pixels(db):
    s, tag = db
    ssp = Ssp()
    ssp.add(tag + "-a", "2Waaa", creative(erid="2Waaa", trk="T1", domain="one", img=_banner(tag)), publishers=(1,))
    ssp.add(tag + "-b", "2Wbbb", creative(erid="2Wbbb", trk="T2", domain="two", img=_banner(tag)), publishers=(2,))
    ssp.run(s)
    reqs = s.query(PremodRequest).filter(PremodRequest.ssp_uuid.like(tag + "%")).all()
    assert len(reqs) == 2 and len({r.package_id for r in reqs}) == 1
    assert len(ssp.stashed) == 1                                   # снимок один на пакет
    assert "display:none" not in ssp.stashed[0] and "viewability" not in ssp.stashed[0]
    assert {c["key"]: c["state"] for c in reqs[0].checks}["erid"] == "ok"
    assert reqs[0].landing.startswith("https://shop.example/promo")


def test_sync_fills_package_checks_and_advertiser_directory(db):
    """Сломает: не сводить проверки по пакету при заборе — у экрана не будет ни одной проверки."""
    s, tag = db
    ssp = Ssp()
    ssp.add(tag + "-a", "2Waaa", creative(erid="2Waaa", img=_banner(tag)))
    ssp.add(tag + "-b", "2Wbad", creative(erid="2Wzzz", trk="T2", img=_banner(tag)))   # ЕРИД разметки чужой
    ssp.run(s)
    pkg = s.get(PremodPackage, _pkg_of(s, tag + "-a"))
    by = {c["key"]: c for c in pkg.checks}
    assert pkg.kind == "статика" and pkg.text is None
    assert by["mark"]["state"] == "warn"                           # статика — смотрит человек
    assert by["erid"]["state"] == "bad" and by["erid"]["short"] == "не совпадает у 1 из 2"
    adv = s.get(PremodAdvertiser, TEST_INN)
    assert adv is not None and adv.short_name == "Ромашка" and adv.category is None


def test_html5_text_comes_from_markup(db):
    s, tag = db
    html = creative(erid="2Waaa", img=_banner(tag)).replace(
        "</body>", "<canvas></canvas><div>Летайте с нами. Реклама. ООО «Ромашка», ИНН 7700000000</div></body>")
    ssp = Ssp()
    ssp.add(tag + "-a", "2Waaa", html)
    ssp.run(s)
    pkg = s.get(PremodPackage, _pkg_of(s, tag + "-a"))
    assert pkg.kind == "HTML5" and pkg.text == "Летайте с нами. Реклама. ООО «Ромашка», ИНН 7700000000"
    by = {c["key"]: c["state"] for c in pkg.checks}
    assert by["mark"] == "ok" and by["adv"] == "ok"


def test_unchanged_request_is_not_refetched_but_recheck_refetches(db):
    s, tag = db
    ssp = Ssp()
    ssp.add(tag + "-a", "2Waaa", creative(erid="2Waaa", img=_banner(tag)))
    ssp.run(s)
    ssp.run(s)
    assert len(ssp.fetched) == 1
    ssp.run(s, recheck=True)
    assert len(ssp.fetched) == 2


def test_decision_per_version_hint_and_followed_package(db):
    s, tag = db
    user = _any_user(s)
    ssp = Ssp()
    ssp.add(tag + "-a", "2Waaa", creative(erid="2Waaa", trk="T1", img=_banner(tag)))
    ssp.run(s)
    pkg_id = _pkg_of(s, tag + "-a")
    assert _view(s, pkg_id)["status"] == "wait"

    first = service.decide(s, user, pkg_id, "одобрено")
    s.commit()
    assert first[0].followed_package is None and first[0].sent_at is None   # в SSP не отправляем
    assert _view(s, pkg_id)["status"] == "approved"

    # Через две недели — тот же баннер на другую площадку: ждёт клика, с подсказкой.
    ssp.add(tag + "-b", "2Wbbb", creative(erid="2Wbbb", trk="T2", img=_banner(tag)))
    ssp.run(s)
    v = _view(s, pkg_id)
    assert v["status"] == "wait" and v["same_creative"]["by"] == user.name
    assert len(v["decisions"]) == 1 and len(v["decisions"][0]["request_ids"]) == 1
    second = service.decide(s, user, pkg_id, "одобрено")
    s.commit()
    assert len(second) == 1 and second[0].followed_package is True


def test_changed_markup_moves_request_to_new_package_and_waits_again(db):
    s, tag = db
    user = _any_user(s)
    ssp = Ssp()
    ssp.add(tag + "-a", "2Waaa", creative(erid="2Waaa", img=_banner(tag, 1)))
    ssp.run(s)
    old = _pkg_of(s, tag + "-a")
    service.decide(s, user, old, "одобрено")
    s.commit()
    decided = service.waiting_count(s)

    ssp.add(tag + "-a", "2Waaa", creative(erid="2Waaa", img=_banner(tag, 2)), updated="2026-11-08 09:00:00")
    ssp.run(s)
    assert service.waiting_count(s) == decided + 1           # индикатор видит, что креатив снова ждёт
    new = _pkg_of(s, tag + "-a")
    assert new != old and s.get(PremodPackage, new).prev_package_id == old
    v = _view(s, new)
    assert v["status"] == "changed" and v["decisions"] == []          # прежнее решение — не по этой версии
    assert v["prev"]["version"] == old and v["prev"]["decided_by"] == user.name
    assert v["prev"]["changes"] == [{"label": "креатив", "from": "", "to": "изменилась картинка или разметка",
                                     "kind": "same"}]


def test_decline_needs_reason_and_foreign_request_is_refused(db):
    s, tag = db
    user = _any_user(s)
    ssp = Ssp()
    ssp.add(tag + "-a", "2Waaa", creative(erid="2Waaa", img=_banner(tag, 1)))
    ssp.add(tag + "-b", "2Wbbb", creative(erid="2Wbbb", img=_banner(tag, 2)))
    ssp.run(s)
    a, b = (s.query(PremodRequest).filter(PremodRequest.ssp_uuid == tag + x).one() for x in ("-a", "-b"))
    with pytest.raises(service.DecisionError):
        service.decide(s, user, a.package_id, "отклонено")
    with pytest.raises(service.DecisionError):
        service.decide(s, user, a.package_id, "одобрено", request_ids=[b.id])


def test_waiting_count_counts_packages_not_requests(db):
    s, tag = db
    before = service.waiting_count(s)
    ssp = Ssp()
    ssp.add(tag + "-a", "2Waaa", creative(erid="2Waaa", trk="T1", img=_banner(tag)))
    ssp.add(tag + "-b", "2Wbbb", creative(erid="2Wbbb", trk="T2", img=_banner(tag)))
    ssp.run(s)
    assert service.waiting_count(s) == before + 1


def test_bulk_approve_takes_only_clean_packages(db):
    """Сломает: убрать серверную проверку чистоты — фронт с устаревшими данными одобрит нарушение."""
    s, tag = db
    user = _any_user(s)
    ssp = Ssp()
    ssp.add(tag + "-a", "2Waaa", creative(erid="2Waaa", img=_banner(tag, 1)))
    ssp.add(tag + "-b", "2Wbad", creative(erid="2Wzzz", img=_banner(tag, 2)))      # ЕРИД не совпадает
    ssp.run(s)
    clean, dirty = _pkg_of(s, tag + "-a"), _pkg_of(s, tag + "-b")
    with pytest.raises(service.NotClean) as e:
        service.bulk_approve(s, user, [clean, dirty])
    assert e.value.missing == [dirty]
    s.rollback()
    made = service.bulk_approve(s, user, [clean])
    s.commit()
    assert [d.bulk for d in made[0]] == [True]
    assert _view(s, clean)["decisions"][0]["bulk"] is True
    assert s.query(PremodDecision).join(PremodRequest).filter(PremodRequest.package_id == dirty).count() == 0


# ------------------------------ права и ручки ------------------------------

@pytest.fixture
def people():
    s = SessionLocal()
    made = []

    def make(perms):
        role = Role(key=f"zz_pm_{uuid.uuid4().hex[:8]}", label="zz премодерация")
        s.add(role)
        s.flush()
        if perms:
            s.add(RolePermission(role_id=role.id, section="traffic_premod",
                                 can_view=int("view" in perms), can_edit=int("edit" in perms)))
        u = User(name="zz", email=f"zz-pm-{uuid.uuid4().hex[:10]}@example.test", hashed_password="x",
                 is_active=1, role_id=role.id, consent_accepted_at=datetime.utcnow())
        s.add(u)
        s.commit()
        made.append(u)
        return u

    yield make
    s.rollback()
    for u in made:
        s.execute(text("DELETE FROM premod_decision WHERE decided_by = :u"), {"u": u.id})
        s.execute(text("DELETE FROM audit_log WHERE user_id = :u"), {"u": u.id})
        s.execute(text("DELETE FROM users WHERE id = :u"), {"u": u.id})
        s.execute(text("DELETE FROM role_permissions WHERE role_id = :r"), {"r": u.role_id})
        s.execute(text("DELETE FROM roles WHERE id = :r"), {"r": u.role_id})
    s.commit()
    s.close()


def _headers(user):
    s = SessionLocal()
    try:
        return {"Authorization": "Bearer " + auth.create_access_token(auth.token_claims(s.get(User, user.id)))}
    finally:
        s.close()


def test_rights_view_and_decide_are_separate(db, people, monkeypatch):
    monkeypatch.setattr("app.routers.premod._reason_tree", lambda: [])    # кабинет SSP не зовём
    s, tag = db
    ssp = Ssp()
    ssp.add(tag + "-a", "2Waaa", creative(erid="2Waaa", img=_banner(tag)))
    ssp.run(s)
    req = s.query(PremodRequest).filter(PremodRequest.ssp_uuid == tag + "-a").one()
    api = TestClient(main.app, raise_server_exceptions=False)
    nobody, viewer, editor = people(set()), people({"view"}), people({"view", "edit"})
    assert api.get("/api/premod/count", headers=_headers(nobody)).status_code == 403
    seen = api.get("/api/premod/board", headers=_headers(viewer))
    assert seen.status_code == 200 and seen.json()["can_decide"] is False
    assert api.get("/api/premod/board", headers=_headers(editor)).json()["can_decide"] is True
    body = {"verdict": "approved", "request_ids": [req.id]}
    url = f"/api/premod/packages/{req.package_id}/decision"
    assert api.post(url, json=body, headers=_headers(viewer)).status_code == 403
    r = api.post(url, json=body, headers=_headers(editor))
    assert r.status_code == 200 and r.json()["verdict"] == "approved" and r.json()["request_ids"] == [req.id]
    assert _view(s, req.package_id)["status"] == "approved"


def test_bulk_endpoint_answers_409_with_dirty_packages(db, people):
    s, tag = db
    ssp = Ssp()
    ssp.add(tag + "-b", "2Wbad", creative(erid="2Wzzz", img=_banner(tag, 2)))
    ssp.run(s)
    dirty = _pkg_of(s, tag + "-b")
    api = TestClient(main.app, raise_server_exceptions=False)
    r = api.post("/api/premod/bulk-approve", json={"package_ids": [dirty]}, headers=_headers(people({"view", "edit"})))
    assert r.status_code == 409 and r.json()["missing"] == [dirty]


def test_category_change_recomputes_warning_check(db):
    """Сломает: сохранить категорию без пересчёта — у лекарств предупреждение так и останется «не требуется»."""
    s, tag = db
    ssp = Ssp()
    ssp.add(tag + "-a", "2Waaa", creative(erid="2Waaa", img=_banner(tag)))
    ssp.run(s)
    pkg_id = _pkg_of(s, tag + "-a")

    def warning():
        s.expire_all()
        return {c["key"]: c["state"] for c in s.get(PremodPackage, pkg_id).checks}["warning"]

    assert warning() == "na"
    service.set_category(s, TEST_INN, "лекарства")
    s.commit()
    assert warning() == "warn" and s.get(PremodAdvertiser, TEST_INN).category == "лекарства"
    assert "лекарства" in B.board(s, True, [])["categories"]
    service.set_category(s, TEST_INN, "  ")
    s.commit()
    assert warning() == "na" and s.get(PremodAdvertiser, TEST_INN).category is None


def test_category_endpoint_needs_edit_right(db, people):
    s, tag = db
    ssp = Ssp()
    ssp.add(tag + "-a", "2Waaa", creative(erid="2Waaa", img=_banner(tag)))
    ssp.run(s)
    api = TestClient(main.app, raise_server_exceptions=False)
    url, body = f"/api/premod/advertisers/{TEST_INN}", {"category": "БАД"}
    assert api.patch(url, json=body, headers=_headers(people({"view"}))).status_code == 403
    assert api.patch(url, json=body, headers=_headers(people({"view", "edit"}))).status_code == 200
    s.expire_all()
    assert s.get(PremodAdvertiser, TEST_INN).category == "БАД"
    assert api.patch("/api/premod/advertisers/0000000000", json=body,
                     headers=_headers(people({"view", "edit"}))).status_code == 404
