# -*- coding: utf-8 -*-
"""Сверка паблишера за месяц (26.10.2026): статусы, срок, разнесение итога, полный проход, права.

Проход по базе идёт в одной транзакции и откатывается — на стенде не остаётся ни сверок, ни сообщений."""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.main import app
from app.publisher_recon import board as B
from app.publisher_recon import service as S
from app.publisher_requests import PublisherRequest
from app.routers.auth import get_current_user

MON = date(2026, 10, 26)


# ── чистые правила ──────────────────────────────────────────────────────────────────────────────────

def test_ready_only_when_every_placement_of_the_month_is_over():
    assert B.status_of(5, 5, None, MON) == (B.READY, False)
    assert B.status_of(5, 4, None, MON) == (B.WAIT, False)
    assert B.status_of(0, 0, None, MON) == (B.WAIT, False)          # нечего сверять — не «готово»


def test_turn_follows_the_last_non_system_message():
    assert B.status_of(1, 1, {"last_side": None, "due_at": MON}, MON) == (B.OUT, False)
    assert B.status_of(1, 1, {"last_side": "мы", "due_at": MON}, MON) == (B.OUT, False)
    assert B.status_of(1, 1, {"last_side": "площадка", "due_at": date(2026, 10, 1)}, MON) == (B.ANSWER, False)
    assert B.status_of(1, 1, {"last_side": "мы", "due_at": date(2026, 10, 23)}, MON) == (B.OUT, True)
    assert B.status_of(1, 1, {"verdict": "согласовано", "last_side": "площадка"}, MON) == (B.DONE, False)


def test_answer_term_is_two_working_days():
    assert S.add_workdays(date(2026, 10, 26), 2) == date(2026, 10, 28)   # пн → ср
    assert S.add_workdays(date(2026, 10, 30), 2) == date(2026, 11, 3)    # пт → вт, выходные не в счёт


def test_spread_keeps_the_total_and_follows_the_shares():
    out = S.spread(1000, {1: 1, 2: 1, 3: 1})
    assert sum(out.values()) == 1000 and sorted(out.values()) == [333, 333, 334]
    assert S.spread(150, {1: 100, 2: 200}) == {1: 50, 2: 100}
    assert sum(S.spread(7, {1: 0, 2: 0}).values()) == 7               # без факта — поровну
    assert S.spread(10, {}) == {}


def test_cabinet_and_manager_read_one_fact_view():
    """Факт площадки — одно представление: кабинет его только фильтрует (вторая копия формулы разошлась бы)."""
    db = SessionLocal()
    try:
        body = db.execute(text("SELECT pg_get_viewdef('pub.campaign_v1', true)")).scalar()
    finally:
        db.close()
    assert "publisher_placement_v" in body and "ad_campaign_stat" not in body


# ── проход в базе (откатывается) ────────────────────────────────────────────────────────────────────

class _U:
    def __init__(self, name="Менеджер тест", email="m@test"):
        self.name, self.email, self.id = name, email, None


@pytest.fixture
def ready():
    db = SessionLocal()
    rows = [r for r in B.month_rows(db, "2026-10") if r["status"] == B.READY and r["ours"] > 0]
    if not rows:
        db.close()
        pytest.skip("на стенде нет площадки, готовой к сверке за октябрь")
    yield db, rows[0]
    db.rollback()
    db.close()


def test_full_cycle_writes_three_numbers_and_spreads_the_total(ready):
    db, row = ready
    pid, today = row["publisher_id"], date(2026, 10, 26)
    req = S.send(db, pid, "2026-10", _U(), today)
    assert req.due_at == date(2026, 10, 28) and req.recon.our_volume == row["ours"]
    with pytest.raises(S.ReconError) as e:
        S.send(db, pid, "2026-10", _U(), today)
    assert e.value.status == 409                                       # одна сверка на площадку и месяц

    with pytest.raises(S.ReconError):
        S.publisher_answer(db, req, "Площадка", None, agree=False)     # расхождение без цифры не уходит
    S.publisher_answer(db, req, "Площадка", None, agree=False, volume=row["ours"] + 1000, body="у нас больше")
    st = next(r for r in B.month_rows(db, "2026-10", today) if r["publisher_id"] == pid)
    assert st["status"] == B.ANSWER and st["theirs"] == row["ours"] + 1000 and st["delta"] == 1000

    S.reply(db, req, _U(), "предлагаем", row["ours"] + 400, today=date(2026, 10, 27))
    assert req.due_at == date(2026, 10, 29)                            # наш ответ продлевает срок
    S.publisher_answer(db, req, "Площадка", None, agree=True)          # «Согласен» — с нашей цифрой, и это итог
    assert req.recon.their_volume == row["ours"] + 400

    lines = db.execute(text("SELECT sum(agreed_volume), sum(our_volume) FROM publisher_recon_line WHERE request_id = :r"),
                       {"r": req.id}).first()
    assert lines[0] == row["ours"] + 400 and lines[1] == req.recon.our_volume
    assert req.verdict == "согласовано" and req.recon.cpm is not None
    with pytest.raises(S.ReconError) as e:
        S.agree(db, req, _U(), 1)
    assert e.value.status == 409                                       # без возврата


def test_cannot_send_before_october_or_while_placements_run(ready):
    db, _row = ready
    with pytest.raises(S.ReconError):
        S.send(db, _row["publisher_id"], "2026-09", _U())
    waiting = [r for r in B.month_rows(db, "2026-10") if r["status"] == B.WAIT]
    if waiting:
        with pytest.raises(S.ReconError) as e:
            S.send(db, waiting[0]["publisher_id"], "2026-10", _U())
        assert e.value.status == 409


def test_remind_once_a_day(ready):
    db, row = ready
    req = S.send(db, row["publisher_id"], "2026-10", _U())
    S.remind(db, req)                                                  # «сегодня» — по времени записи строки
    with pytest.raises(S.ReconError):
        S.remind(db, req)


# ── права и ввод ────────────────────────────────────────────────────────────────────────────────────

class _Role:
    def __init__(self, key):
        self.key, self.id = key, None


class _User:
    def __init__(self, key):
        self.id, self.name, self.email = None, "test", "t@t"
        self.role, self.role_id, self.consent_accepted_at = _Role(key), None, True


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_screen_is_closed_without_the_right(client):
    app.dependency_overrides[get_current_user] = lambda: _User("role_13")      # трафик — права нет
    assert client.get("/api/publisher-recon/board?period=2026-10").status_code == 403
    assert client.post("/api/publisher-recon/send", json={"publisher_id": 1, "period": "2026-10"}).status_code == 403


def test_bad_period_is_4xx(client):
    app.dependency_overrides[get_current_user] = lambda: _User("admin")
    assert client.get("/api/publisher-recon/board?period=октябрь").status_code == 400
    assert client.get("/api/publisher-recon/board?period=2026-10").status_code == 200


def test_gateway_does_not_open_someone_elses_recon():
    from app.routers.cabinet_gateway_recon import _recon
    from fastapi import HTTPException
    db = SessionLocal()
    try:
        req = PublisherRequest(kind="сверка", publisher_id=1, period="2026-10")
        db.add(req)
        db.flush()
        with pytest.raises(HTTPException) as e:
            _recon(db, req.id, 2)
        assert e.value.status_code == 404
    finally:
        db.rollback()
        db.close()


# ── сценарии закрытия: любая комбинация услуг и РК (26.10.2026) ─────────────────────────────────────

def _pl(pid, tid, status="завершён", fact=100, service="еФарм", cpm=100):
    return {"publisher_id": pid, "placement_id": tid, "site": f"s{pid}", "status": status, "fact": fact,
            "cpm": cpm, "service": service}


def _rq(pid, rid=1, last=None, verdict=None, our=None, lines=None, due=date(2026, 10, 28)):
    return {"id": rid, "publisher_id": pid, "site": f"s{pid}", "cpm": 100, "due_at": due, "verdict": verdict,
            "last_side": last, "our_volume": our, "their_volume": None, "agreed_volume": our, "agreed_cpm": 100,
            "messages": 0, "unread": 0, "decided_at": None, "decided_by": None, "line_targets": lines}


def _row(rows, pid):
    return next(r for r in rows if r["publisher_id"] == pid)


def test_mixed_services_of_one_publisher_are_one_recon():
    """еФарм + Polza у одной площадки — одна сверка месяца: готова, только когда окончены ОБЕ."""
    ready = B.assemble("2026-10", [_pl(1, 10), _pl(1, 11, service="Polza", fact=0)], {}, MON)
    assert _row(ready, 1)["status"] == B.READY and _row(ready, 1)["total"] == 2 and _row(ready, 1)["ours"] == 100
    waiting = B.assemble("2026-10", [_pl(1, 10), _pl(1, 11, status="в размещении", service="Polza")], {}, MON)
    assert _row(waiting, 1)["status"] == B.WAIT


def test_not_started_and_paused_placements_keep_the_month_open():
    for st in ("ждёт старта", "ждёт согласования", "пауза", "в размещении"):
        rows = B.assemble("2026-10", [_pl(1, 10), _pl(1, 11, status=st, fact=0)], {}, MON)
        assert _row(rows, 1)["status"] == B.WAIT, st


def test_refusal_with_shows_is_paid_and_closed():
    """Открутила до отказа — показы оплачиваются и размещение окончено; отказ без показов в выборку не попадает."""
    rows = B.assemble("2026-10", [_pl(1, 10), _pl(1, 11, status="отказ", fact=40)], {}, MON)
    assert _row(rows, 1)["status"] == B.READY and _row(rows, 1)["ours"] == 140


def test_recon_without_placements_does_not_disappear():
    """Сделку перенесли в другой месяц после отправки — сверка остаётся на экране, а не теряется."""
    rows = B.assemble("2026-10", [], {7: _rq(7, last="мы")}, MON)
    r = _row(rows, 7)
    assert r["orphan"] and r["status"] == B.OUT and r["total"] == 0


def test_change_after_agreement_is_flagged():
    agreed = {1: _rq(1, verdict="согласовано", our=100, lines=[10])}
    same = B.assemble("2026-10", [_pl(1, 10)], agreed, MON)
    assert _row(same, 1)["status"] == B.DONE and not _row(same, 1)["changed"]
    late_stats = B.assemble("2026-10", [_pl(1, 10, fact=120)], agreed, MON)
    assert _row(late_stats, 1)["changed"] and _row(late_stats, 1)["ours"] == 100   # итог прежний, флаг — да
    new_deal = B.assemble("2026-10", [_pl(1, 10), _pl(1, 12, fact=0)], agreed, MON)
    assert _row(new_deal, 1)["changed"]


def test_turn_and_lateness_per_scenario():
    rows = B.assemble("2026-10", [_pl(1, 10), _pl(2, 20), _pl(3, 30)],
                      {1: _rq(1, 1, last="площадка"), 2: _rq(2, 2, last="мы", due=date(2026, 10, 23)), 3: _rq(3, 3)}, MON)
    assert (_row(rows, 1)["status"], _row(rows, 2)["late"], _row(rows, 3)["status"]) == (B.ANSWER, True, B.OUT)
    assert [r["publisher_id"] for r in rows][:2] == [1, 2]            # сначала «есть ответ», потом просроченные


# ── ревью безопасности перед v2.7.12 ────────────────────────────────────────────────────────────────

def test_no_file_after_agreement_and_files_do_not_overwrite(ready, tmp_path):
    db, row = ready
    req = S.send(db, row["publisher_id"], "2026-10", _U(), date(2026, 10, 26))
    S.publisher_answer(db, req, "Площадка", None, agree=False, volume=row["ours"] + 10, body="у нас больше")
    msg = db.execute(text("SELECT id FROM publisher_request_message WHERE request_id = :r AND side = 'площадка'"),
                     {"r": req.id}).scalar()
    from app.publisher_requests import PublisherRequestMessage
    m = db.get(PublisherRequestMessage, msg)
    a = S.save_file(db, m, "stat.xlsx", None, b"one", root=str(tmp_path))
    b = S.save_file(db, m, "stat.xlsx", None, b"two", root=str(tmp_path))
    assert a.path != b.path                                            # тот же файл дважды — две копии, не перезапись
    assert (tmp_path / a.path).read_bytes() == b"one"
    S.agree(db, req, _U(), row["ours"])
    with pytest.raises(S.ReconError) as e:
        S.save_file(db, m, "late.xlsx", None, b"x", root=str(tmp_path))
    assert e.value.status == 409                                       # после итога файлы не добавляются


def test_absurd_volume_is_4xx_not_500(ready):
    db, row = ready
    req = S.send(db, row["publisher_id"], "2026-10", _U(), date(2026, 10, 26))
    with pytest.raises(S.ReconError) as e:
        S.publisher_answer(db, req, "Площадка", None, agree=False, volume=10 ** 30, body="опечатка")
    assert e.value.status == 400


def test_amount_after_agreement_is_agreed_times_cpm():
    """Ревью 26.10.2026: «Сумма, ₽» доски после итога считалась от НАШЕЙ цифры, а «Сводная» — от согласованной."""
    agreed = {1: {**_rq(1, verdict="согласовано", our=100, lines=[10]), "agreed_volume": 150}}
    r = _row(B.assemble("2026-10", [_pl(1, 10)], agreed, MON), 1)
    assert r["agreed"] == 150 and r["amount"] == 15.0                 # 150 × 100 ₽ CPM / 1000


def test_stale_open_request_cannot_change_an_agreed_recon(ready):
    """Ревью 27.10.2026 (v2.7.0..): ответ площадки и наш ответ проверяли «сверка открыта» по устаревшей копии строки — ответ,
    начатый до «Согласовать», после него перезаписывал цифру площадки и двигал срок. Должны брать строку на замок и видеть итог."""
    db, row = ready
    req = S.send(db, row["publisher_id"], "2026-10", _U(), date(2026, 10, 26))
    db.flush()
    db.execute(text("UPDATE publisher_request SET verdict = 'согласовано' WHERE id = :r"), {"r": req.id})   # итог из другой сессии
    with pytest.raises(S.ReconError) as e:
        S.publisher_answer(db, req, "Площадка", None, agree=False, volume=5, body="поздно")
    assert e.value.status == 409
    with pytest.raises(S.ReconError):
        S.reply(db, req, _U(), "ещё", None, today=date(2026, 10, 27))


def test_agree_takes_our_last_offered_figure_not_a_text_reply(ready):
    """Ревью 27.10.2026: «Согласен» брал объём ПОСЛЕДНЕГО нашего сообщения, даже если в нём только текст — тогда согласие
    записывалось не с той цифрой, что мы предлагали. Берётся последнее наше сообщение С ЦИФРОЙ."""
    db, row = ready
    req = S.send(db, row["publisher_id"], "2026-10", _U(), date(2026, 10, 26))
    S.reply(db, req, _U(), "предлагаем", row["ours"] + 400, today=date(2026, 10, 27))
    S.reply(db, req, _U(), "и ещё вопрос по датам", None, today=date(2026, 10, 27))
    S.publisher_answer(db, req, "Площадка", None, agree=True)
    assert req.recon.their_volume == row["ours"] + 400


def test_publisher_agreeing_without_dispute_fixes_the_total(ready):
    """Владелец 29.10.2026: «если у площадки не возникло разногласий, то они последние, кто утверждает сверку». «Согласен»
    с нашей цифрой сразу фиксирует итог — разаллокация доступна площадке без ожидания менеджера. Сломать: убрать
    вызов `agree` из `publisher_answer` — сверка останется открытой, verdict пустой."""
    db, row = ready
    req = S.send(db, row["publisher_id"], "2026-10", _U(), date(2026, 10, 26))
    S.publisher_answer(db, req, "Иванова", "i@pub.test", agree=True)
    assert req.verdict == "согласовано" and req.decided_by == "Иванова" and req.decided_email == "i@pub.test"
    assert req.recon.agreed_volume == row["ours"] and req.recon.cpm is not None
    total = db.execute(text("SELECT sum(agreed_volume) FROM publisher_recon_line WHERE request_id = :r"), {"r": req.id}).scalar()
    assert total == row["ours"]
    with pytest.raises(S.ReconError) as e:
        S.publisher_answer(db, req, "Иванова", None, agree=True)
    assert e.value.status == 409


def test_dispute_still_waits_for_our_manager(ready):
    db, row = ready
    req = S.send(db, row["publisher_id"], "2026-10", _U(), date(2026, 10, 26))
    S.publisher_answer(db, req, "Площадка", None, agree=False, volume=row["ours"] + 1000, body="у нас больше")
    assert req.verdict is None


def test_cabinet_shows_the_same_figure_that_agreement_locks(ready):
    """Ревью 29.10.2026: мы предложили N, потом ответили текстом без цифры — бэкенд при «Согласен» берёт N (последнее
    наше сообщение С ЦИФРОЙ), а витрина кабинета брала последнее сообщение целиком и показывала нашу цифру вместо N.
    С 29.10 «Согласен» — это итог, поэтому кнопка обязана показывать ровно то, что зафиксируется."""
    db, row = ready
    pid, offer = row["publisher_id"], row["ours"] + 400
    req = S.send(db, pid, "2026-10", _U(), date(2026, 10, 26))
    S.publisher_answer(db, req, "Площадка", None, agree=False, volume=row["ours"] + 1000, body="у нас больше")
    S.reply(db, req, _U(), "предлагаем", offer, today=date(2026, 10, 27))
    S.reply(db, req, _U(), "смотрим ещё", None, today=date(2026, 10, 27))
    db.execute(text("SELECT set_config('app.publisher_ids', :p, true)"), {"p": str(pid)})
    shown = db.execute(text("SELECT offer FROM pub.recon_v1 WHERE request_id = :r"), {"r": req.id}).scalar()
    S.publisher_answer(db, req, "Площадка", None, agree=True)
    assert shown == offer == req.recon.agreed_volume


def test_agreed_month_numbers_in_the_cabinet_no_longer_change(ready):
    """Владелец 29.10.2026: «после сверки с площадкой цифры должны фиксироваться и больше не меняться». Кабинет брал
    показы живыми из статистики и CPM — текущий из реестра: досчиталась статистика или поменяли CPM — у площадки
    поменялись цифры согласованного месяца. Теперь у согласованного месяца показы — из разнесения итога по
    размещениям, CPM — зафиксированный при согласовании. Сломать: вернуть `fact`/`cpm` из publisher_placement_v."""
    db, row = ready
    pid = row["publisher_id"]
    req = S.send(db, pid, "2026-10", _U(), date(2026, 10, 26))
    S.publisher_answer(db, req, "Площадка", None, agree=True)
    tid, frozen_cpm = db.execute(text("""SELECT l.target_id, r.cpm FROM publisher_recon_line l
                                         JOIN publisher_recon r ON r.request_id = l.request_id
                                         WHERE l.request_id = :r ORDER BY l.target_id LIMIT 1"""), {"r": req.id}).first()
    # «Потом»: статистика досчиталась иначе, чем разнесено, и CPM площадки в реестре поменяли.
    db.execute(text("UPDATE publisher_recon_line SET agreed_volume = 777 WHERE request_id = :r AND target_id = :t"),
               {"r": req.id, "t": tid})
    db.execute(text("UPDATE sales_publishers SET cpm_contract = coalesce(cpm_contract, 0) + 999 WHERE id = :p"), {"p": pid})
    db.execute(text("SELECT set_config('app.publisher_ids', :p, true)"), {"p": str(pid)})
    fact, cpm = db.execute(text("SELECT fact, cpm FROM pub.campaign_v1 WHERE placement_id = :t"), {"t": tid}).first()
    assert fact == 777 and cpm == frozen_cpm


def test_vat_is_fixed_at_agreement_and_razaloc_keeps_it(ready):
    """Владелец 29.10.2026: цифры сверки после согласования не меняются — и НДС разаллокации тоже. Ставка записывается в
    итог при согласовании; поменяли ставку у юрлица площадки потом — файл считается по прежней. Сломать: читать ставку
    в `razaloc.of_request` живой (`publisher_vat`), а не из `publisher_recon.vat_rate`."""
    from app.publisher_recon import razaloc as R
    db, row = ready
    pid = row["publisher_id"]
    db.execute(text("""UPDATE counterparties SET vat_rate_expense = 5 WHERE id IN (
        SELECT k.counterparty_id FROM sales_publisher_contracts pc JOIN contracts k ON k.id = pc.contract_id
         WHERE pc.publisher_id = :p AND pc.role = 'с площадкой' AND NOT pc.is_archived)"""), {"p": pid})
    if R.publisher_vat(db, pid) is None:
        pytest.skip("у готовой площадки нет договора «с площадкой»")
    req = S.send(db, pid, "2026-10", _U(), date(2026, 10, 26))
    S.publisher_answer(db, req, "Площадка", None, agree=True)
    stored = db.execute(text("SELECT vat_rate FROM publisher_recon WHERE request_id = :r"), {"r": req.id}).scalar()
    assert stored == 5
    db.execute(text("""UPDATE counterparties SET vat_rate_expense = 22 WHERE id IN (
        SELECT k.counterparty_id FROM sales_publisher_contracts pc JOIN contracts k ON k.id = pc.contract_id
         WHERE pc.publisher_id = :p AND pc.role = 'с площадкой')"""), {"p": pid})
    rows = R.of_request(db, req)["rows"]
    assert rows and {r["НДС,%"] for r in rows} == {0.05}


def test_placement_outside_the_agreed_total_does_not_add_shows_to_a_closed_month(ready):
    """Ревью 29.10.2026: размещение, которого не было в разнесении итога (отказ с нулём на момент согласования, позже
    согласованное новым креативом; добавленное задним числом), оставалось живым — и его показы ложились поверх
    зафиксированного итога месяца. Согласованный месяц закрыт целиком: такое размещение показывает 0. Сломать: брать
    живой факт, когда строки разнесения нет."""
    db, row = ready
    pid = row["publisher_id"]
    req = S.send(db, pid, "2026-10", _U(), date(2026, 10, 26))
    S.publisher_answer(db, req, "Площадка", None, agree=True)
    tid = db.execute(text("""SELECT l.target_id FROM publisher_recon_line l JOIN launch_prep_target t ON t.id = l.target_id
                              WHERE l.request_id = :r ORDER BY l.our_volume DESC LIMIT 1"""), {"r": req.id}).scalar()
    db.execute(text("DELETE FROM publisher_recon_line WHERE request_id = :r AND target_id = :t"), {"r": req.id, "t": tid})
    db.execute(text("SELECT set_config('app.publisher_ids', :p, true)"), {"p": str(pid)})
    assert db.execute(text("SELECT fact FROM pub.campaign_v1 WHERE placement_id = :t"), {"t": tid}).scalar() == 0


def test_archived_placement_of_an_agreed_month_stays_in_the_cabinet(ready):
    """Владелец 29.10.2026: кампания согласованного месяца не пропадает из кабинета, когда уходит в архив. Архив
    наступает после сдачи в ОРД (`launch_prep_target.archived_at`) — то есть ровно после закрытия месяца, и витрина,
    отбрасывавшая архивные, разом убрала бы закрытые месяцы, а сумма месяца перестала бы равняться итогу."""
    db, row = ready
    pid = row["publisher_id"]
    req = S.send(db, pid, "2026-10", _U(), date(2026, 10, 26))
    S.publisher_answer(db, req, "Площадка", None, agree=True)
    tid, vol = db.execute(text("""SELECT target_id, agreed_volume FROM publisher_recon_line WHERE request_id = :r
                                  ORDER BY agreed_volume DESC LIMIT 1"""), {"r": req.id}).first()
    db.execute(text("UPDATE launch_prep_target SET archived_at = now() WHERE id = :t"), {"t": tid})
    db.execute(text("SELECT set_config('app.publisher_ids', :p, true)"), {"p": str(pid)})
    assert db.execute(text("SELECT fact FROM pub.campaign_v1 WHERE placement_id = :t"), {"t": tid}).scalar() == vol
    total = db.execute(text("""SELECT sum(fact) FROM pub.campaign_v1
                               WHERE publisher_id = :p AND to_char(date_from, 'YYYY-MM') = '2026-10'"""), {"p": pid}).scalar()
    assert total == req.recon.agreed_volume
