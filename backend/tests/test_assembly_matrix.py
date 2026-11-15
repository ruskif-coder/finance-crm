# -*- coding: utf-8 -*-
"""Матрица «что требует учёта — по услугам» (владелец 14.10.2026): все пункты стадий по блокам; новая услуга получает общие пункты."""
import pytest

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.final_recon import assembly as A
from app.models import User
from app.routers import sales_directories as R
from app.sales.models import SalesService


@pytest.fixture
def db():
    s = SessionLocal()
    real = s.commit
    s.commit = s.flush                        # ничего не оставляем на стенде
    yield s
    s.commit = real
    s.rollback()
    s.close()


def test_every_check_key_is_in_the_matrix(db):
    keys = {r[0] for r in db.execute(A.text("SELECT DISTINCT check_key FROM sales_stage_checks"))}
    shown = {it["key"] for b in A.matrix(db)["blocks"] for it in b["items"]}
    assert keys == shown


def test_new_service_gets_common_items_only_and_toggle_works(db, monkeypatch):
    monkeypatch.setattr(R, "log_action", lambda *a, **k: None)
    u = db.query(User).first()
    out = R.create_service(R.ServiceIn(name="[тест] услуга матрицы"), db, u)
    sid = out["id"]
    items = {it["key"]: it for b in A.matrix(db)["blocks"] for it in b["items"]}
    assert sid in items["final_contract"]["service_ids"] and sid in items["invoice_issued"]["service_ids"]   # общие — да
    # Пункт отдельных услуг (список — часть активных) новой услуге не достаётся. До 15.11.2026 тут стоял `erid_issued`
    # как «только еФарм», но на проде миграции 14.10 не накатаны и у него списка нет — он для всех; берём любой узкий.
    active = {r[0] for r in db.execute(A.text("SELECT id FROM sales_services WHERE is_active AND id <> :s"), {"s": sid})}
    narrow = next((k for k, it in sorted(items.items()) if it["service_ids"] and not active <= set(it["service_ids"])), None)
    if narrow is None:
        pytest.skip("на стенде нет пункта отдельных услуг")
    assert sid not in items[narrow]["service_ids"]
    A.toggle(db, narrow, sid, True)
    items = {it["key"]: it for b in A.matrix(db)["blocks"] for it in b["items"]}
    assert sid in items[narrow]["service_ids"]
    A.toggle(db, narrow, sid, False)
    assert db.get(SalesService, sid) is not None


def test_switching_one_service_off_keeps_an_all_services_item_for_the_rest(db):
    """Пункт без списка услуг действует для ВСЕХ (так его читает `stage_checks`). Выключение одной услуги не должно
    превращать «все» в «ни одной/только эта» — до 15.11.2026 первое переключение молча снимало пункт с остальных услуг.
    Сломать: вернуть в `set_state` чтение `service_ids or []` вместо `_scope`."""
    from types import SimpleNamespace
    from app.sales import stage_checks as SC
    active = [r[0] for r in db.execute(A.text("SELECT id FROM sales_services WHERE is_active ORDER BY id"))]
    if len(active) < 2:
        pytest.skip("нужно две активные услуги")
    db.execute(A.text("UPDATE sales_stage_checks SET applies_when = NULL WHERE check_key = 'invoice_issued'"))
    off, keep = active[0], active[1]
    it = next(i for b in A.matrix(db)["blocks"] for i in b["items"] if i["key"] == "invoice_issued")
    assert set(active) <= set(it["service_ids"]), "пустое условие = все услуги, как у проверки"
    A.set_state(db, "invoice_issued", off, "off")
    row = db.execute(A.text("SELECT applies_when FROM sales_stage_checks WHERE check_key = 'invoice_issued' LIMIT 1")).scalar()
    assert SC.scope_matches(row, SimpleNamespace(service_id=keep)) is True, "у остальных услуг пункт остался"
    assert SC.scope_matches(row, SimpleNamespace(service_id=off)) is False


def test_three_states_per_service(db):
    """Владелец 14.10.2026: клетка — не требуется / уведомляет / требуется, у каждой услуги своё."""
    from types import SimpleNamespace
    from app.sales import stage_checks as SC
    sid = 24
    for state, on, blk in (("block", True, True), ("warn", True, False), ("off", False, False)):
        A.set_state(db, "erid_issued", sid, state)
        it = next(i for b in A.matrix(db)["blocks"] for i in b["items"] if i["key"] == "erid_issued")
        assert (sid in it["service_ids"], sid in it["blocking_ids"]) == (on, blk)
        row = db.execute(A.text("SELECT applies_when, is_blocking FROM sales_stage_checks WHERE check_key='erid_issued' LIMIT 1")).first()
        deal = SimpleNamespace(service_id=sid)
        assert SC.blocking_for(SimpleNamespace(applies_when=row[0], is_blocking=row[1]), deal) is blk
    with pytest.raises(A.AssemblyError):
        A.set_state(db, "erid_issued", sid, "maybe")
