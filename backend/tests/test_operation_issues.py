# -*- coding: utf-8 -*-
"""Проблемные операции и правило «комплект уходит → что с операцией» (владелец 20.11.2026).

Оплаченную операцию не удаляем — помечаем и уведомляем; неоплаченный план удаляется вместе с комплектом. Переделка помечает
операцию, повторное внесение снимает пометку; оплаченная, которую мост не обновляет, при новых цифрах 1С получает
«расхождение с 1С». Живой пакет стенда, транзакция откатывается."""
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app import operation_issues as OI
from app.master_deal import bridge as BR
from tests._untouched_kit import untouched_kit


@pytest.fixture
def env(monkeypatch):
    from app.database import SessionLocal
    from app.master_deal.models import MasterDeal
    from app.notify import closing as CN
    from app.sales.models import SalesAnnex
    db = SessionLocal()
    k = untouched_kit(db)
    if k is None:
        pytest.skip("на стенде нет комплектов УПД")
    a = db.get(SalesAnnex, k.annex_id)
    if a is not None and not a.number:
        a.number = "ДС № 2"
    sent = []
    monkeypatch.setattr(CN, "operation_issue", lambda db_, op, kind, text_, user=None: sent.append((op.id, kind)))
    try:
        yield db, db.get(MasterDeal, k.master_deal_id), k, sent
    finally:
        db.rollback()
        db.close()


def _entered(db, m, k, inv="1247", gross=None):
    """Бухгалтер внесла ответ 1С — мост делает операцию."""
    k.onec_invoice_no, k.onec_invoice_date = inv, date(2026, 10, 31)
    k.onec_gross = float(k.gross) if gross is None else gross
    k.onec_state, k.onec_at = "внесён", datetime.utcnow()
    return BR.sync_kit(db, m, k)


def _issues(db, op_id, open_only=True):
    q = "SELECT kind, text FROM operation_issues WHERE operation_id = :o" + (" AND resolved_at IS NULL" if open_only else "")
    return db.execute(text(q + " ORDER BY id"), {"o": op_id}).all()


def _pay(db, op):
    db.execute(text("UPDATE operations SET status = 'ОПЛАЧЕНО', date = '2026-11-10' WHERE id = :i"), {"i": op.id})
    db.expire(op)


# ── переделка ─────────────────────────────────────────────────────────────────────────────────────

def test_redo_marks_operation_and_reentry_clears_it(env):
    """Ломается, если переделка не помечает операцию или повторное внесение не снимает пометку."""
    from app.master_deal import revert as RV
    db, m, k, sent = env
    op = _entered(db, m, k)
    RV.redo_kit(db, m, k, None, "не тот номер договора")
    rows = _issues(db, op.id)
    assert [r.kind for r in rows] == ["на переделке"] and "не тот номер договора" in rows[0].text
    assert not sent, "«на переделке» — рабочее состояние, не уведомляем"
    _entered(db, m, k)
    assert not _issues(db, op.id), "внесли заново — пометка снята сама"


# ── повторное внесение при оплаченной ─────────────────────────────────────────────────────────────

def test_paid_operation_with_new_1c_numbers_gets_mismatch(env):
    """Оплаченную мост не меняет; новые сумма и № счёта — проблема с «было → стало» и уведомление, один раз."""
    db, m, k, sent = env
    op = _entered(db, m, k, inv="1247")
    _pay(db, op)
    paid = float(op.income)
    _entered(db, m, k, inv="1300", gross=paid + 1000)
    rows = _issues(db, op.id)
    assert [r.kind for r in rows] == ["расхождение с 1С"]
    assert "1247 → 1300" in rows[0].text and "сумма" in rows[0].text
    db.refresh(op)
    assert op.invoice == "1247" and abs(op.income - paid) < 0.01, "оплаченную операцию мост не трогает"
    _entered(db, m, k, inv="1300", gross=paid + 1000)
    assert len(_issues(db, op.id)) == 1 and sent == [(op.id, "расхождение с 1С")], "то же расхождение — без второй строки и звонка"


def test_paid_operation_with_same_numbers_is_not_a_problem(env):
    db, m, k, sent = env
    op = _entered(db, m, k)
    _pay(db, op)
    _entered(db, m, k)
    assert not _issues(db, op.id) and not sent


def test_partially_paid_plan_is_not_overwritten(env):
    """Материнская с частью оплаты хранит остаток: перезапись полной суммой задвоила бы деньги. Сумма сверяется по цепочке."""
    from app.models import Operation
    db, m, k, sent = env
    op = _entered(db, m, k)
    full = float(op.income)
    part = Operation(date=date(2026, 11, 5), status="ОПЛАЧЕНО", income=1000.0, expense=0.0, period=op.period,
                     parent_operation_id=op.id, counterparty_id=op.counterparty_id, article_id=op.article_id)
    db.add(part)
    op.income = full - 1000.0
    db.flush()
    _entered(db, m, k)                          # те же цифры: цепочка (остаток + часть) = сумма 1С — не проблема
    db.refresh(op)
    assert abs(op.income - (full - 1000.0)) < 0.01, "остаток материнской мост не перезаписывает"
    assert not _issues(db, op.id)
    _entered(db, m, k, gross=full + 500)
    assert [r.kind for r in _issues(db, op.id)] == ["расхождение с 1С"]


# ── комплект уходит ───────────────────────────────────────────────────────────────────────────────

def test_unpaid_plan_is_deleted_with_its_kit(env):
    db, m, k, sent = env
    op = _entered(db, m, k)
    out = OI.retire_kits(db, m, [k.id], None, "проверка")
    assert out == {"deleted": [op.id], "kept": []}
    assert not db.execute(text("SELECT 1 FROM operations WHERE id = :i"), {"i": op.id}).first()
    assert db.execute(text("SELECT 1 FROM audit_log WHERE action = 'delete_operation' AND entity_id = :i"), {"i": op.id}).first(), \
        "удаление вместе с комплектом — в журнале"
    assert not sent


def test_paid_operation_survives_kit_removal_with_problem(env):
    """Владелец 20.11.2026: оплаченную не удалять — уведомлять. Ссылку на комплект снимаем сами, проблема держит его id."""
    db, m, k, sent = env
    op = _entered(db, m, k)
    _pay(db, op)
    out = OI.retire_kits(db, m, [k.id], None, "проверка")
    assert out == {"deleted": [], "kept": [op.id]}
    db.refresh(op)
    assert op.master_deal_upd_id is None
    rows = db.execute(text("SELECT kind, master_deal_upd_id, text FROM operation_issues WHERE operation_id = :o"), {"o": op.id}).all()
    assert [(r.kind, r.master_deal_upd_id) for r in rows] == [("пакет удалён", k.id)] and m.code in rows[0].text
    assert sent == [(op.id, "пакет удалён")]


def test_plan_with_attached_scan_is_kept(env):
    """Скан к операции прикладывал человек — это уже не «нетронутый план», молча не удаляем."""
    db, m, k, sent = env
    op = _entered(db, m, k)
    db.execute(text("INSERT INTO operation_files (operation_id, path, original_name) VALUES (:o, 'x', 'скан.pdf')"),
               {"o": op.id})
    assert OI.retire_kits(db, m, [k.id], None)["kept"] == [op.id]


def test_signed_start_revert_retires_operations_before_kits_go(env):
    """«Вернуть в раскладку» стартового пакета удаляла комплекты без проверки стадии — внесённые в 1С тоже. Операции решаются
    до удаления, а не остаются сиротами с пустой ссылкой (найдено 20.11.2026)."""
    from app.master_deal import to_annex as TA
    db, m, k, sent = env
    op = _entered(db, m, k)
    _pay(db, op)
    TA._revert_signed_start(db, m, None)
    assert not db.execute(text("SELECT 1 FROM master_deal_upds WHERE id = :k"), {"k": k.id}).first()
    db.refresh(op)
    assert op.master_deal_upd_id is None and [r.kind for r in _issues(db, op.id)] == ["пакет удалён"]


def test_every_kit_deletion_goes_through_the_rule():
    """Храповик: файл, удаляющий комплекты УПД, обязан звать `retire_` — иначе вернётся сирота и дубль в дебиторке."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    strays = []
    for p in app_dir.rglob("*.py"):
        s = p.read_text(encoding="utf-8")
        if "MasterDealUpd.master_deal_id == m.id).delete(" in s and "retire_" not in s:
            strays.append(str(p.relative_to(app_dir)))
    assert not strays, f"комплекты удаляются мимо правила: {strays}"


# ── закрытие руками, реестр ───────────────────────────────────────────────────────────────────────

def test_resolve_needs_a_comment_and_leaves_the_filter(env):
    from app.models import Operation
    db, m, k, sent = env
    op = _entered(db, m, k)
    row = OI.raise_issue(db, op, OI.MISMATCH, "проверка")
    assert db.query(Operation.id).filter(Operation.id == op.id, OI.open_cond()).first(), "открытая — в плитке «Проблемные»"
    with pytest.raises(OI.IssueError) as e:
        OI.resolve(db, row.id, "  ", None)
    assert e.value.status == 400
    OI.resolve(db, row.id, "поправил сумму", None)
    assert not db.query(Operation.id).filter(Operation.id == op.id, OI.open_cond()).first()
    assert OI.open_by_op(db, [op.id]) == {}
    with pytest.raises(OI.IssueError):
        OI.resolve(db, row.id, "ещё раз", None)


def test_event_goes_to_owner_by_tg_and_mail_and_accountant_by_choice():
    """Владелец 20.11.2026: «мне в тг и почту», бухгалтеру — опцией. Каналов по умолчанию нет — без подписки не звонит никому."""
    from app.notify import registry, seed_profiles
    ev = registry.get("operation_issue")
    assert ev is not None and ev.direction == "fin"
    assert {"type": "role", "value": "admin"} in ev.recipients
    assert {"type": "resolver", "value": "onec_desk_editors"} in ev.recipients
    assert not any(ev.channels.values()), "по умолчанию — никому: бухгалтеру включают в профиле"
    assert set(seed_profiles.PLAN["admin"]["operation_issue"]) >= {"tg", "mail"}
    assert "operation_issue" not in seed_profiles.PLAN["fin"]
