# -*- coding: utf-8 -*-
"""Аудит v2.6.0→v2.7.0 (21.10.2026), пакет приоритезации: двойной запуск, потерянный camp_id, тихий ноль статистики,
уведомление, отравляющее сессию. Сделка стенда, транзакция откатывается; API подменён — наружу ничего не уходит."""
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.prio import launch as L
from app.prio import models as M
from app.prio import stats as ST
from app.prio.client import PrioApiError
from app.prio.service import PrioError
from tests.test_prio import FakeApi, _approved, env  # noqa: F401 — фикстура стенда


def test_second_launch_while_first_runs_is_refused(env):  # noqa: F811
    """Двойной клик «Запустить»: второй проход, пока первый держит замок, получает 409, а не вторую РК."""
    from app import ext_lock
    db, d, pubs = env
    api = FakeApi()
    p = _approved(db, d, pubs[0])
    with ext_lock.only_one(ext_lock.PRIO_LAUNCH, p.id, RuntimeError, "Запуск"):
        with pytest.raises(PrioError) as e:
            L.launch(db, d, p.id, client=api)
    assert e.value.status == 409 and api.created == 0


class _LostRead(FakeApi):
    """POST прошёл, а перечитка РК по camp_id ничего не нашла (сеть, задержка индекса)."""
    def campaigns(self, **f):
        return [] if f.get("camp_id") else super().campaigns(**f)


def test_created_campaign_is_kept_when_reread_fails(env):  # noqa: F811
    """РК в системе уже крутится — у нас она обязана остаться с camp_id и «идёт», иначе автостоп её не увидит."""
    db, d, pubs = env
    api = _LostRead()
    p = _approved(db, d, pubs[0])
    got = L.launch(db, d, p.id, client=api)
    assert p.camp_id and p.status == M.LIVE and api.created == 1
    assert got.check_warning and str(p.camp_id) in got.check_warning


class _StrSiteId(FakeApi):
    """API отдаёт site_id строкой."""
    def campaigns(self, **f):
        return [{**c, "site_id": str(c["site_id"])} for c in super().campaigns(**f)]


def test_retry_finds_campaign_when_api_returns_site_id_as_string(env):  # noqa: F811
    db, d, pubs = env
    api = _StrSiteId()
    p = _approved(db, d, pubs[0])
    api.create({**L.payload(db, d, p)})                     # первая попытка — ответ потерян
    L.launch(db, d, p.id, client=api)
    assert api.created == 1, "повтор завёл дубль: site_id сравнивается без приведения типа"


@pytest.mark.parametrize("body", [
    {"ok": True, "summary": [{"camp_id": 5, "impressions": 10}]},          # строки под незнакомым ключом
    {"ok": True, "stats": [{"id": 5, "impressions": 10}]},                  # без camp_id
])
def test_unparsed_non_empty_answer_is_an_error_not_zero(body):
    with pytest.raises(PrioApiError):
        ST.parse_strict(body)


def test_stats_as_dict_by_camp_id_is_understood():
    got = ST.parse_strict({"ok": True, "stats": {"5": {"impressions": 10, "clicks": 1}}})
    assert {k: (v["shows"], v["clicks"]) for k, v in got.items()} == {5: (10, 1)}


@pytest.mark.parametrize("body", [{"ok": True}, {"ok": True, "stats": []}, [], {"ok": True, "date_start": "2026-10-21", "total": 0, "stats": []}])
def test_really_empty_answer_is_fine(body):
    assert ST.parse_strict(body) == {}


def test_any_crash_of_the_cron_raises_the_alarm(monkeypatch):
    """Тревога — на любой сбой прогона, а не только на ошибку API: TypeError разбора тоже значит «автостоп не работает»."""
    from app.notify import prio as N
    seen = []
    monkeypatch.setattr(ST, "pull", lambda *a, **k: (_ for _ in ()).throw(TypeError("разбор")))
    monkeypatch.setattr(N, "stat_failed", lambda db, e: seen.append(str(e)))
    monkeypatch.setattr(ST, "last_ok", lambda db: True)
    monkeypatch.setattr(ST, "record", lambda db, ok: None)

    class _Db:
        def rollback(self):
            pass

        def close(self):
            pass

    code = ST.main(session=_Db(), client=object())
    assert code == 1 and seen and "разбор" in seen[0]


def test_failed_notification_does_not_poison_the_session(env, monkeypatch):  # noqa: F811
    """Упавший flush внутри уведомления не должен отравить транзакцию действия (`begin_nested`)."""
    import app.notify.bus as bus
    from app.notify import prio as N
    db, d, pubs = env

    def boom(db_, *a, **k):
        db_.execute(text("SELECT 1/0"))
    monkeypatch.setattr(bus, "emit", boom)
    N.goal_reached(db, d, {"publisher_id": pubs[0], "fact": 1, "limit": 1})
    assert db.execute(text("SELECT 1")).scalar() == 1, "сессия отравлена — действие откатится на commit"


def test_failed_outward_message_keeps_earlier_inward_ones(env, monkeypatch):  # noqa: F811
    """Сбой письма площадке не откатывает уже записанные внутренние уведомления (раньше — `db.rollback()`)."""
    import app.notify.outward as OUT
    from app.notify import prio as N
    db, d, pubs = env
    p = _approved(db, d, pubs[0])
    db.execute(text("CREATE TEMP TABLE _probe (x int) ON COMMIT DROP"))
    db.execute(text("INSERT INTO _probe VALUES (1)"))

    def boom(db_, *a, **k):
        db_.execute(text("SELECT 1/0"))
    monkeypatch.setattr(OUT, "notify_publisher", boom)
    assert N.live_to_site(db, d, p, False)["status"] == "error"
    assert db.execute(text("SELECT count(*) FROM _probe")).scalar() == 1, "откат унёс чужие записи транзакции"



def _statements(db):
    """Сбор SQL, который сессия отправляет в базу, — проверить, что строка берётся под замок."""
    from sqlalchemy import event
    seen = []
    conn = db.connection()
    event.listen(conn, "before_cursor_execute", lambda c, cur, stmt, *a: seen.append(" ".join(stmt.split())))
    return seen


def test_rebalance_locks_the_request_row(env):  # noqa: F811
    """Раскладка целей читает статусы всех площадок запроса — под замком запроса, иначе параллельный ответ площадки
    и добавление площадки раскладывают объём по разным снимкам (класс LBS2QH)."""
    from app.prio import service as S
    from tests.test_prio import _ready
    db, d, pubs = env
    _ready(db, d, pubs[0])
    seen = _statements(db)
    S.rebalance(db, d)
    assert any("FROM prio_requests" in q and "FOR UPDATE" in q for q in seen), seen


def test_verdict_locks_the_placement_row(env):  # noqa: F811
    """Двойной ответ площадки: проверка «запрос у вас» и запись — под замком строки площадки."""
    from app.prio import service as S
    from tests.test_prio import _sent
    db, d, pubs = env
    p = _sent(db, d, pubs[0])
    S.set_sku(db, p, "1234567")
    seen = _statements(db)
    S.verdict(db, p, "ок", None)
    assert any("FROM prio_placements" in q and "FOR UPDATE" in q for q in seen), seen


@pytest.mark.parametrize("prev,ok,alert", [(True, False, True), (None, False, True), (False, False, False), (False, True, False)])
def test_alarm_only_on_transition_to_failure(prev, ok, alert):
    """Каждую ночь одно и то же — не новость: иначе тревогу выключат, и настоящая поломка утонет в повторах (как у ЕРИД)."""
    assert ST.should_alert(prev, ok) is alert


def test_failing_again_tonight_stays_quiet(monkeypatch):
    from app.notify import prio as N
    seen, rec = [], []
    monkeypatch.setattr(ST, "pull", lambda *a, **k: (_ for _ in ()).throw(TypeError("разбор")))
    monkeypatch.setattr(N, "stat_failed", lambda db, e: seen.append(str(e)))
    monkeypatch.setattr(ST, "last_ok", lambda db: False)
    monkeypatch.setattr(ST, "record", lambda db, ok: rec.append(ok))

    class _Db:
        def rollback(self):
            pass

        def close(self):
            pass

    assert ST.main(session=_Db(), client=object()) == 1
    assert seen == [] and rec == [False]
