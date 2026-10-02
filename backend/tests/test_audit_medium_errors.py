# -*- coding: utf-8 -*-
"""Средние находки аудита 01.10.2026, группа «ошибки 500 и сбои после записи»:
предсказуемый ввод и сбой соседнего шага не превращаются в 500, когда главное уже
сделано или когда виноват один ряд из файла."""
import io
import os
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

import app.main  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_c1_broken_click_pixel_script_is_gone():
    """Скрипт звал удалённый `click_link` и вернул бы в DSP кликовый счётчик (v2.6.63
    сделал `link` посадочной). Запуск его теперь — вред, поэтому его нет."""
    assert not os.path.exists(os.path.join(ROOT, "scripts", "2026-10-01_dsp_click_pixel.py"))


def test_c2_targeting_failure_is_a_report_not_a_500(monkeypatch):
    from app.dsp import provision as P
    from app.dsp import targeting as tg
    monkeypatch.setattr(tg, "enabled", lambda db: True)
    monkeypatch.setattr(P, "_rows", lambda db, camp: [])

    def boom(db, camp, rows):
        raise ValueError("freq не число")
    monkeypatch.setattr(tg, "plan_for", boom)
    rolled = []
    out = P._apply_targeting(SimpleNamespace(rollback=lambda: rolled.append(1)),
                             SimpleNamespace(id=1), None, "H")
    assert "freq не число" in out["error"] and rolled, "после сбоя — откат сессии"


def test_c3_wake_failure_after_commit_is_quiet(monkeypatch):
    from app.routers import traffic_dashboard as td
    monkeypatch.setattr(td, "wake_targeting", lambda db, d: (_ for _ in ()).throw(RuntimeError("сеть")))
    out = td._wake_quietly(SimpleNamespace(rollback=lambda: None), 1)
    assert out["woken"] == 0 and "сеть" in out["errors"][0]


def test_c11_bad_publisher_id_cell_is_skipped_not_500(monkeypatch):
    import openpyxl
    from app.routers import traffic_balancer as tb
    monkeypatch.setattr(tb, "log_action", lambda *a, **k: None)
    monkeypatch.setattr(tb, "_push_to_campaigns", lambda db: 0)
    monkeypatch.setattr(tb.balance, "rows", lambda db: [])
    BALANCE_COLS = tb.BALANCE_COLS
    wb = openpyxl.Workbook()
    ws = wb.active
    titles = dict(BALANCE_COLS)
    ws.append([titles["publisher_id"], titles["scope"]])
    for bad in ("abc", "inf", "12.7", "0", "-5", "999999999"):
        ws.append([bad, "web"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    db = SimpleNamespace(commit=lambda: None,
                         execute=lambda *a, **k: [(1,), (2,)])
    out = tb.balancer_import(SimpleNamespace(file=buf), db=db, user=SimpleNamespace(id=1))
    assert out["skipped"] == 6 and out["applied"] == 0


def test_c12_slow_search_is_partial_not_500(monkeypatch):
    from app.search import engine as E
    monkeypatch.setattr(E, "_plan", lambda q, types, allowed: ("text", ["deal"], ["deal"]))
    monkeypatch.setattr(E, "context", lambda db, u: {})

    class Canceled(Exception):
        pgcode = "57014"

    def slow(*a):
        raise OperationalError("SELECT", {}, Canceled("canceling statement due to statement timeout"))
    monkeypatch.setitem(E.SEARCHERS, "deal", (E.SEARCHERS["deal"][0], slow))
    rolled = []
    db = SimpleNamespace(execute=lambda *a, **k: None, rollback=lambda: rolled.append(1))
    out = E.run(db, SimpleNamespace(id=1), "магне", perms={})
    assert out["groups"] == [] and out.get("partial") is True and rolled


def test_c14_network_failure_finding_ad_space_is_provision_error():
    from app.weborama import provision as WP
    from app.weborama.client import WcmError

    class C:
        def ad_spaces_all(self):
            raise WcmError("обрыв")
    with pytest.raises(WP.ProvisionError):
        WP._our_space(None, C())



def test_c12_timeout_in_fallback_pass_is_partial_too(monkeypatch):
    """Второй проход (по остальным типам) тоже может упереться в предел."""
    from app.search import engine as E
    monkeypatch.setattr(E, "_plan", lambda q, types, allowed: ("code", ["deal"], ["deal", "counterparty"]))
    monkeypatch.setattr(E, "context", lambda db, u: {})

    class Canceled(Exception):
        pgcode = "57014"

    def slow(*a):
        raise OperationalError("SELECT", {}, Canceled("timeout"))
    monkeypatch.setitem(E.SEARCHERS, "deal", (E.SEARCHERS["deal"][0], lambda *a: []))
    monkeypatch.setitem(E.SEARCHERS, "counterparty", (E.SEARCHERS["counterparty"][0], slow))
    db = SimpleNamespace(execute=lambda *a, **k: None, rollback=lambda: None)
    assert E.run(db, SimpleNamespace(id=1), "PFIZER", perms={})["partial"] is True


def test_c12_lost_connection_is_not_hidden(monkeypatch):
    from app.search import engine as E
    monkeypatch.setattr(E, "_plan", lambda q, types, allowed: ("text", ["deal"], ["deal"]))
    monkeypatch.setattr(E, "context", lambda db, u: {})

    def lost(*a):
        raise OperationalError("SELECT", {}, Exception("server closed the connection"))
    monkeypatch.setitem(E.SEARCHERS, "deal", (E.SEARCHERS["deal"][0], lost))
    db = SimpleNamespace(execute=lambda *a, **k: None, rollback=lambda: None)
    with pytest.raises(OperationalError):
        E.run(db, SimpleNamespace(id=1), "магне", perms={})


def test_n5_zip_bomb_is_refused_before_reading():
    """Н-5: подготовка архива к DSP (демо-экран, выгрузка) проверяет объявленный размер
    распаковки до чтения — как песочница."""
    import zipfile
    from app.launch_prep import sandbox
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("index.html", "<html></html>")
        z.writestr("big.bin", b"\0" * (sandbox.MAX_SINGLE_BYTES + 1))
    with pytest.raises(sandbox.SandboxError):
        sandbox.prepare_for_dsp(buf.getvalue())
