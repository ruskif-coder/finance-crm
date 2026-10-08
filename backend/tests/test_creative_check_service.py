# -*- coding: utf-8 -*-
"""Страница «Проверка креатива»: права, чужие проверки, нацеливание, срок жизни (07.10.2026).

Правила владельца: проверка видна автору; через 48 часов нацеливание останавливается, файлы и строка
удаляются; строка исчезает только после подтверждённой остановки (удалить креатив в DSP нечем).

Тесты пишут только свои строки (роль `zz_cc_*`, почты `zz-cc-…@example.test`, проверки с названием
`zz …`) и убирают их; файлы — во временный каталог, DSP — подменный клиент, журнал действий чистится.
"""
import struct
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.main as main
from app.creative_check import service
from app.creative_check.models import CreativeCheck
from app.database import SessionLocal
from app.dsp import check_creative
from app.dsp import targeting_creative as tc
from app.models import Role, RolePermission, User
from app.routers import auth
from tests.test_dsp_targeting_creative import FakeClient


def _png(w=300, h=250):
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", w, h)
            + b"\x08\x06\x00\x00\x00" + b"\x00" * 8)


@pytest.fixture
def stand(tmp_path, monkeypatch):
    """Хранилище во временном каталоге, кабинет нацеливания и загрузчик — подменные."""
    monkeypatch.setattr(service, "UPLOADS_ROOT", str(tmp_path))
    monkeypatch.setattr(tc, "UPLOADS_ROOT", str(tmp_path))
    monkeypatch.setattr("app.dsp.config.targeting_cabinet", lambda db: ("PARTNER000000001", "CAMPAIGN00000001"))
    monkeypatch.setattr("app.dsp.config.viewability_src", lambda db: "")
    monkeypatch.setattr("app.dsp.creatives.upload_zip",
                        lambda c, data, filename="x.zip", local_ref=None, timeout=60.0:
                        {"html": "<div>баннер</div>", "size": "300x250"})
    return tmp_path


def _make_user(db, perms):
    role = Role(key=f"zz_cc_{uuid.uuid4().hex[:8]}", label="zz проверка креатива")
    db.add(role)
    db.flush()
    if perms is not None:
        db.add(RolePermission(role_id=role.id, section="creative_check",
                              can_view=int("view" in perms), can_edit=int("edit" in perms),
                              can_delete=int("delete" in perms)))
    user = User(name="zz", email=f"zz-cc-{uuid.uuid4().hex[:10]}@example.test",
                hashed_password="x", is_active=1, role_id=role.id,
                consent_accepted_at=datetime.utcnow())
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def people():
    db = SessionLocal()
    made = []

    def make(perms):
        u = _make_user(db, perms)
        made.append(u)
        return u

    yield make
    db.rollback()
    for u in made:
        uid, rid = u.id, u.role_id
        for chk in db.query(CreativeCheck).filter(CreativeCheck.created_by == uid).all():
            service.remove_files(chk)
        db.execute(text("DELETE FROM creative_check WHERE created_by = :u"), {"u": uid})
        db.execute(text("DELETE FROM audit_log WHERE user_id = :u"), {"u": uid})
        db.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
        db.execute(text("DELETE FROM role_permissions WHERE role_id = :r"), {"r": rid})
        db.execute(text("DELETE FROM roles WHERE id = :r"), {"r": rid})
    db.commit()
    db.close()


def _headers(user):
    db = SessionLocal()
    try:
        u = db.get(User, user.id)
        return {"Authorization": "Bearer " + auth.create_access_token(auth.token_claims(u))}
    finally:
        db.close()


@pytest.fixture
def api():
    return TestClient(main.app, raise_server_exceptions=False)


def _upload(api, user, name="zz баннер", url="example.ru", filename="b.png", data=None):
    return api.post("/api/creative-check", headers=_headers(user),
                    data={"title": name, "url": url},
                    files={"file": (filename, data if data is not None else _png(), "application/octet-stream")})


# ── права и чужие проверки ──────────────────────────────────────────────────

def test_rights_view_edit_delete_are_separate(stand, people, api):
    nobody, viewer, editor = people(None), people({"view"}), people({"view", "edit"})
    assert api.get("/api/creative-check", headers=_headers(nobody)).status_code == 403
    assert api.get("/api/creative-check", headers=_headers(viewer)).status_code == 200
    assert _upload(api, viewer).status_code == 403
    assert _upload(api, editor).status_code == 200


def test_delete_needs_its_own_right_and_other_peoples_checks_are_invisible(stand, people, api, monkeypatch):
    monkeypatch.setattr(check_creative, "stop", lambda db, chk, client=None: True)
    editor, deleter, stranger = people({"view", "edit"}), people({"view", "delete"}), people({"view", "edit", "delete"})
    cid = _upload(api, editor).json()["id"]
    assert api.delete(f"/api/creative-check/{cid}", headers=_headers(editor)).status_code == 403   # нет права
    # чужая проверка: ни в списке, ни по номеру (404), даже с правом удаления
    assert api.get("/api/creative-check", headers=_headers(stranger)).json() == []
    assert api.delete(f"/api/creative-check/{cid}", headers=_headers(stranger)).status_code == 404
    assert api.post(f"/api/creative-check/{cid}/targeting-link", headers=_headers(stranger)).status_code == 404
    assert [x["id"] for x in api.get("/api/creative-check", headers=_headers(editor)).json()] == [cid]
    assert deleter  # право без автора тоже не даёт чужую проверку — проверено строкой выше


# ── загрузка ────────────────────────────────────────────────────────────────

def test_upload_returns_the_card_with_default_publishers_and_remarks(stand, people, api):
    editor = people({"view", "edit"})
    r = _upload(api, editor, name="zz карточка", url="https://Example.RU/", data=_png() + b"\x00" * (400 * 1024))
    assert r.status_code == 200, r.text
    card = r.json()
    assert card["title"] == "zz карточка" and card["info"]["size"] == "300x250"
    assert any("КБ" in w for w in card["warnings"])
    assert card["advertiser_url"].startswith("https://")
    expected = {p["id"] for p in service.default_publishers(SessionLocal())}
    assert {p["id"] for p in card["publishers"]} == expected
    assert (stand / "creative_check").is_dir()


def test_default_publishers_are_ours_and_web_and_not_archived():
    db = SessionLocal()
    try:
        got = {p["id"] for p in service.default_publishers(db)}
        sql = {r[0] for r in db.execute(text(
            "SELECT p.id FROM sales_publishers p JOIN sales_publisher_surfaces s ON s.publisher_id = p.id AND s.kind = 'web' "
            "WHERE p.our_code AND p.status <> 'АРХИВ'"))}
        assert got == sql
    finally:
        db.close()


@pytest.mark.parametrize("kwargs,fragment", [
    ({"name": "   "}, "название"),
    ({"url": "not a domain"}, "Домен"),
    ({"filename": "a.exe", "data": b"MZ"}, "тип файла"),
    ({"filename": "a.zip", "data": b"PK\x03\x04 broken"}, "архив"),
])
def test_bad_input_is_a_400_with_the_reason(stand, people, api, kwargs, fragment):
    editor = people({"view", "edit"})
    r = _upload(api, editor, **kwargs)
    assert r.status_code == 400 and fragment.lower() in r.json()["detail"].lower(), r.text


def test_domain_is_optional_but_the_name_is_required(stand, people, api):
    """Домен можно не вводить (дизайн 07.10.2026); название — обязательно (владелец, поверх макета)."""
    editor = people({"view", "edit"})
    r = _upload(api, editor, name="zz без домена", url="")
    assert r.status_code == 200, r.text
    assert r.json()["advertiser_url"] == ""
    assert _upload(api, editor, name="  ", url="").status_code == 400


def test_an_empty_domain_falls_back_to_our_site_in_the_dsp_copy(stand, people, api):
    editor = people({"view", "edit"})
    cid = _upload(api, editor, url="").json()["id"]
    db, c = SessionLocal(), FakeClient(info_html=None)
    try:
        check_creative.ensure_live(db, db.get(CreativeCheck, cid), client=c)
        assert c.added[0]["link"] == tc.FALLBACK_LINK
    finally:
        db.close()


def test_a_failed_upload_leaves_no_row_and_no_file(stand, people, api):
    editor = people({"view", "edit"})
    _upload(api, editor, filename="a.zip", data=b"PK\x03\x04 broken")
    db = SessionLocal()
    try:
        assert db.query(CreativeCheck).filter(CreativeCheck.created_by == editor.id).count() == 0
    finally:
        db.close()


# ── нацеливание ─────────────────────────────────────────────────────────────

def _fresh_check(people, api):
    editor = people({"view", "edit", "delete"})
    cid = _upload(api, editor).json()["id"]
    return editor, cid


def test_targeting_creates_one_demo_copy_with_the_placeholder_marker(stand, people, api):
    editor, cid = _fresh_check(people, api)
    db, c = SessionLocal(), FakeClient(info_html=None)    # объекта в кабинете ещё нет
    try:
        chk = db.get(CreativeCheck, cid)
        live = check_creative.ensure_live(db, chk, client=c)
        added = [k for k in c.calls if k[0] == "add"]
        assert len(added) == 1 and added[0][3] == f"chk{cid}" and f"проверка {cid}" in added[0][2]
        assert c.added[0]["erid"] == tc.TEST_ERID and c.added[0]["link"] == chk.advertiser_url
        assert live["xxhash"] == "NEWHASH000000001" and chk.dsp_state == "live"
        # повтор по тому же номеру не заводит второй креатив
        c.info_html = "<div>баннер</div>"
        check_creative.ensure_live(db, chk, client=c)
        assert len([k for k in c.calls if k[0] == "add"]) == 1
    finally:
        db.close()


def test_the_endpoint_answers_with_the_link_and_does_not_confirm_the_banner(stand, people, api, monkeypatch):
    editor, cid = _fresh_check(people, api)
    from app.dsp import targeting_link
    monkeypatch.setattr(check_creative, "ensure_live", lambda db, chk, client=None: {
        "xxhash": "H1", "active": False, "reason": "кампания остановлена", "creative_status": "STOPPED",
        "campaign_status": "STOPPED", "restarted": True})
    monkeypatch.setattr(targeting_link, "issue", lambda crid: targeting_link.TargetingLink(
        crid=crid, url="https://dsp.example/t?x=1", expires_at=None))
    r = api.post(f"/api/creative-check/{cid}/targeting-link", headers=_headers(editor))
    assert r.status_code == 200 and r.json()["url"].startswith("https://") and r.json()["active"] is False


def test_targeting_failure_is_a_400_not_a_500(stand, people, api, monkeypatch):
    editor, cid = _fresh_check(people, api)

    def boom(db, chk, client=None):
        raise tc.TargetingCreativeError("Не задан кабинет")
    monkeypatch.setattr(check_creative, "ensure_live", boom)
    r = api.post(f"/api/creative-check/{cid}/targeting-link", headers=_headers(editor))
    assert r.status_code == 400 and "Не задан кабинет" in r.json()["detail"]


# ── удаление и срок жизни ───────────────────────────────────────────────────

def test_stop_marks_the_copy_and_is_a_noop_without_one(stand, people, api):
    editor, cid = _fresh_check(people, api)
    db, c = SessionLocal(), FakeClient()
    try:
        chk = db.get(CreativeCheck, cid)
        assert check_creative.stop(db, chk, client=c) is True and c.calls == []   # заводить не успели
        chk.dsp_xxhash, chk.dsp_state = "H1", "live"
        assert check_creative.stop(db, chk, client=c) is True
        assert ("creative_status", "H1", tc.STOPPED) in c.calls and chk.dsp_state == "stopped"
    finally:
        db.close()


def test_delete_keeps_the_row_when_the_dsp_does_not_stop(stand, people, api, monkeypatch):
    editor, cid = _fresh_check(people, api)

    def boom(db, chk, client=None):
        raise tc.TargetingCreativeError("креатив нацеливания не остановлен")
    monkeypatch.setattr(check_creative, "stop", boom)
    r = api.delete(f"/api/creative-check/{cid}", headers=_headers(editor))
    assert r.status_code == 502
    assert len(api.get("/api/creative-check", headers=_headers(editor)).json()) == 1


def test_delete_stops_then_wipes_files_and_row(stand, people, api, monkeypatch):
    editor, cid = _fresh_check(people, api)
    stopped = []
    monkeypatch.setattr(check_creative, "stop", lambda db, chk, client=None: stopped.append(chk.id) or True)
    assert api.delete(f"/api/creative-check/{cid}", headers=_headers(editor)).status_code == 200
    assert stopped == [cid]
    assert api.get("/api/creative-check", headers=_headers(editor)).json() == []
    assert not (stand / "creative_check" / f"chk{cid}.zip").exists()


def test_expired_checks_are_removed_after_a_confirmed_stop_and_kept_otherwise(stand, people, api, monkeypatch):
    editor = people({"view", "edit", "delete"})
    ids = [_upload(api, editor, name=f"zz срок {i}").json()["id"] for i in range(3)]
    db = SessionLocal()
    try:
        past = datetime.utcnow() - timedelta(hours=1)
        for cid in ids[:2]:
            db.get(CreativeCheck, cid).expires_at = past
        db.commit()

        def stop(db_, chk, client=None):
            if chk.id == ids[1]:
                raise tc.TargetingCreativeError("DSP не ответил")
            return True
        monkeypatch.setattr(check_creative, "stop", stop)
        out = service.cleanup_expired(db)
        left = {r[0] for r in db.execute(text("SELECT id FROM creative_check WHERE id = ANY(:i)"), {"i": ids})}
        assert out["removed"] == 1 and left == {ids[1], ids[2]}      # просроченная без остановки осталась
        assert len(out["kept"]) == 1 and "DSP не ответил" in out["kept"][0]
    finally:
        db.close()


def test_an_expired_check_is_not_shown_and_cannot_be_targeted(stand, people, api):
    editor, cid = _fresh_check(people, api)
    db = SessionLocal()
    try:
        db.get(CreativeCheck, cid).expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()
    assert api.get("/api/creative-check", headers=_headers(editor)).json() == []
    assert api.post(f"/api/creative-check/{cid}/targeting-link", headers=_headers(editor)).status_code == 404


def test_admin_sees_and_opens_every_check_others_only_their_own(stand, people):
    """Владелец 08.10.2026: «я должен видеть все». Автор и метка «мой/чужой» приходят в карточке."""
    import types
    from app.routers import creative_check as R
    db = SessionLocal()
    try:
        author = people({"view", "edit"})
        chk = service.create(db, author, "zz чужая", "example.ru", "b.png", _png())
        admin = types.SimpleNamespace(id=-1, role=types.SimpleNamespace(key="admin"))
        other = types.SimpleNamespace(id=-2, role=types.SimpleNamespace(key="x"))
        mine = [c for c in R.my_checks(db=db, current_user=admin) if c["id"] == chk.id]
        assert mine and mine[0]["mine"] is False and mine[0]["author"]
        assert all(c["id"] != chk.id for c in R.my_checks(db=db, current_user=other))
        assert R._mine(db, chk.id, admin).id == chk.id
        with pytest.raises(Exception):
            R._mine(db, chk.id, other)
    finally:
        db.close()
