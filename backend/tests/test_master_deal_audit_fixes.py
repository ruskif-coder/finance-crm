# -*- coding: utf-8 -*-
"""Находки аудита 20.10.2026 — каждая красным тестом до правки."""
import inspect
from datetime import datetime

import pytest

from app.master_deal import issue as IS
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
    for mod in (ST, IS):
        monkeypatch.setattr(mod, "channel_of", lambda db, m: m.channel)
    monkeypatch.setattr(IS, "missing_scans", lambda db, m: ["ДС № 2"])
    monkeypatch.setattr(ST, "_missing", lambda db, m: ["ДС № 2"])


def test_paper_signed_then_contract_switched_to_edo_does_not_close_docs():
    """Подписали бумагой, у договора поставили ЭДО, нажали «Отправлено» — документы НЕ закрыты: пакет бумажный, ждёт сканов."""
    m = _M()
    IS.signed_by_us(None, m, _U())
    m.channel = "ЭДО"
    IS.sent(None, m, _U(), None)
    assert m.docs_closed_at is None and m.status == "ждём оплату"
    m.status = "ждём сканы"
    with pytest.raises(ST.StatusError):
        ST.move(None, m, "архив", type("A", (), {"id": 1, "role": type("R", (), {"key": "admin", "is_master": True})()})())


def test_scope_checked_before_every_write():
    """Каждая пишущая ручка мастер-сделки проверяет ВСЕ сделки пакета до записи (иначе запись проходит, а ответ — 403)."""
    from app.routers import master_deals as R
    for route in R.router.routes:
        if not (route.methods & {"PUT", "POST", "DELETE"}) or route.path.endswith("/preview") or route.path.startswith("/deal/"):
            continue
        src = inspect.getsource(route.endpoint)
        assert "_master_rw(" in src or "_issue_act(" in src, f"{route.path}: пакет берётся без полной проверки области"
    assert "_master_rw(" in inspect.getsource(R._issue_act)


def test_track_no_longer_than_column_is_400_not_500():
    from pydantic import ValidationError

    from app.routers import master_deals as R
    with pytest.raises(ValidationError):
        R.SentIn(track_no="R" * 65)


def test_scan_upload_only_where_scans_are_needed():
    from app.master_deal import files as F
    from app.master_deal.service import MasterError
    for status in ("черновик", "выставление", "архив"):
        with pytest.raises(MasterError) as e:
            F.check_upload_allowed(None, _M(status=status))
        assert e.value.status == 409
    m = _M(status="ждём сканы")
    m.signed_by_us_at = m.sent_at = datetime.utcnow()       # бумага — после «подписано у нас»
    F.check_upload_allowed(None, m)
    with pytest.raises(MasterError):
        F.check_upload_allowed(None, _M(status="ждём оплату", channel="ЭДО"))


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
