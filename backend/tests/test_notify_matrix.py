# -*- coding: utf-8 -*-
"""Уведомления аккаунтам — по матрице услуг и стадий (владелец 14.11.2026, все пять пунктов: «ок, включи всем»).

1. «Период закрыт, закрывающих нет» аккаунту больше не уходит: закрывающие делает бухгалтер в 1С, дальше финансы (100 сработок
   в день по стадиям ДО на копии прода).
2. «Дольше нормы» не шлётся на итоговой сверке (там своё «3 дня на сверке») и на стадиях, которые ведёт пакет; у полного цикла с
   несобранным фактом напоминание о сверке — трафику, не аккаунту.
3. События креативов — только где матрица требует креативы (то же правило, что дашборд: `account_turn.external_launch`).
4. «Документы пакета без подписи» — финансам, не собравшему пакет.
5. Новое: «Период кончился — завершите запуск» аккаунту внешнего запуска; включено всем аккаунтам (профили `account` и
   `account_master`)."""
from datetime import date, timedelta
from types import SimpleNamespace

import app.model_registry  # noqa: F401
from app.notify import registry as R
from app.notify import scanner as S
from app.notify import seed_profiles as SP
from app.sales import stage_slots as SS


def test_closing_docs_reminder_is_gone_from_accounts():
    assert "act_missing" not in R.EVENTS and "act_missing" not in S.RULES


def test_stuck_is_not_sent_on_recon_and_on_pack_stages():
    for name in (SS.RECON, SS.DS_PREP, SS.DS_AGREE, SS.CLOSING, SS.EDO, SS.ORD, SS.PAY):
        assert S.stuck_applies(name) is False, name
    for name in (SS.MP_SENT, SS.BOOKING, SS.PREP):
        assert S.stuck_applies(name) is True, name


def test_recon_overdue_goes_to_traffic_while_fact_is_not_collected():
    from app.notify.closing import recon_route
    assert recon_route("полный цикл", "not_yet") == "traffic"
    assert recon_route("полный цикл", "ok") == "account"
    assert recon_route("полный цикл", "n/a") == "account"          # размещений нет — подтверждает аккаунт
    assert recon_route("контур аккаунта", "not_yet") == "account"
    ev = R.get("recon_fact_overdue")
    assert ev and ev.direction == "traffic" and ev.scan and "recon_fact_overdue" in S.RULES
    assert {"type": "resolver", "value": "traffic_manager"} in ev.recipients
    assert "recon_fact_overdue" in SP.PLAN["traffic"]


def test_creative_events_follow_the_matrix():
    from app.notify import matrix_gate as G
    assert G.allowed_for("creative_silence", "контур аккаунта", {"payer_set"}) is False
    assert G.allowed_for("creative_verdict", "контур аккаунта", {"payer_set", "creatives_accepted"}) is True
    assert G.allowed_for("creative_silence", "полный цикл", set()) is True
    assert G.allowed_for("creative_erid_issued", "приоритезация", set()) is True
    assert G.allowed_for("recon_overdue", "контур аккаунта", set()) is True       # не событие креативов
    assert {"creative_set_sent", "creative_verdict", "traffic_rework", "creative_silence", "traffic_silence",
            "creative_erid_failed", "creative_erid_issued"} <= G.CREATIVE_EVENTS


def test_unsigned_pack_documents_go_to_finance():
    ev = R.get("master_scans_overdue")
    assert {"type": "role", "value": "manager"} in ev.recipients
    assert not any(r.get("value") == "master_collector" for r in ev.recipients)
    assert "master_scans_overdue" in SP.PLAN["fin"]


def test_external_launch_finish_is_a_new_account_event_on_for_all_accounts():
    ev = R.get("account_launch_finish")
    assert ev and ev.direction == "account" and ev.scan and "account_launch_finish" in S.RULES
    assert ev.recipients == [{"type": "resolver", "value": "account_manager"}]
    for prof in ("account", "account_master"):
        assert set(SP.PLAN[prof]["account_launch_finish"]) == {"app", "tg"}, prof
    today = date(2026, 11, 14)
    live = SimpleNamespace(name=SS.LIVE)
    assert S.finish_due("контур аккаунта", live, today - timedelta(days=1), today) is True
    assert S.finish_due("приоритезация", live, today - timedelta(days=1), today) is True
    assert S.finish_due("контур аккаунта", live, today, today) is False          # период ещё идёт сегодня
    assert S.finish_due("полный цикл", live, today - timedelta(days=1), today) is False   # РК завершает трафик
    assert S.finish_due("контур аккаунта", SimpleNamespace(name=SS.RECON), today - timedelta(days=3), today) is False


def test_matrix_is_read_once_per_session():
    """Аудит 13.11.2026: матрица требований читалась на каждое событие и каждую сработку сканера. Сломать: убрать кеш."""
    from app.database import SessionLocal
    from app.notify import matrix_gate as G
    db = SessionLocal()
    try:
        assert G._matrix(db) is G._matrix(db)
    finally:
        db.close()
