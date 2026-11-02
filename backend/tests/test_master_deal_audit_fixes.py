# -*- coding: utf-8 -*-
"""Находки аудита 20.10.2026 — каждая красным тестом до правки."""
import inspect

import pytest

from app.master_deal import status as ST


class _M:
    def __init__(self, status="выставление", channel="бумага"):
        self.id, self.code, self.status, self.channel, self.updated_at = 1, "M-T", status, channel, None
        self.signed_by_us_at = self.signed_by_us_by = self.sent_at = self.sent_by = None
        self.track_no = self.docs_closed_at = self.docs_closed_by = None


class _U:
    id = 7
    role = type("R", (), {"key": "role_8", "is_master": False})()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(ST, "channel_of", lambda db, m: m.channel)


def test_scope_checked_before_every_write():
    """Каждая пишущая ручка мастер-сделки проверяет ВСЕ сделки пакета до записи (иначе запись проходит, а ответ — 403)."""
    from app.routers import master_deals as R
    for route in R.router.routes:
        if not (route.methods & {"PUT", "POST", "DELETE"}) or route.path.endswith("/preview") or route.path.startswith("/deal/"):
            continue
        src = inspect.getsource(route.endpoint)
        assert "_master_rw(" in src, f"{route.path}: пакет берётся без полной проверки области"


def test_scan_upload_only_for_paper_doc_already_at_client():
    """Скан подписанного — к бумажному документу, ушедшему клиенту (02.11.2026: по документу, а не по статусу пакета)."""
    from types import SimpleNamespace as NS
    from app.master_deal import files as F
    from app.master_deal.service import MasterError
    for st, ch in (("выпущен", None), ("согласован", None), ("подписан у нас", "бумага"), ("выставлен", "ЭДО")):
        with pytest.raises(MasterError) as e:
            F.check_upload_allowed(None, NS(sign_state=st, sign_channel=ch))
        assert e.value.status == 409
    F.check_upload_allowed(None, NS(sign_state="выставлен", sign_channel="бумага"))
    F.check_upload_allowed(None, NS(sign_state="подписан", sign_channel="бумага"))      # замена скана


def test_media_type_from_extension_not_client():
    from app.master_deal import files as F
    assert F.media_type("скан.PDF") == "application/pdf" and F.media_type("x.jpg") == "image/jpeg"


def test_bridge_updates_only_planned_and_isolates_failures():
    from app.master_deal import bridge as BR
    src = inspect.getsource(BR.sync_kit)
    assert "!= PLANNED" in src, "мост меняет только операцию в статусе «план поступлений» — правки бухгалтера не затирает"
    assert "begin_nested" in inspect.getsource(BR.sync_package), "сбой одного комплекта не должен ломать сессию"


def test_autostop_isolates_each_placement():
    from app.prio import autostop as AS
    src = inspect.getsource(AS.run)
    assert "begin_nested" in src or src.count("try:") >= 1 and "_deal_of" in src.split("try:")[1], \
        "сбой одной площадки (нет сделки, сверка упала) не роняет прогон"
