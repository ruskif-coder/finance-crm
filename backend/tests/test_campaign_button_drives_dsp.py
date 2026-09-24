# -*- coding: utf-8 -*-
"""Кнопки дашборда трафика управляют кампанией в DSP (владелец 23.09.2026, аудит 4.M5).

До этого «Запустить» меняла только наш статус: кампания в DSP оставалась остановленной,
какой её завели, изменения плана туда не доезжали, а экран писал «крутится». Крона нет
и не будет (решение владельца): план и статус уходят в DSP в момент нажатия.

DSP следует нашему ИТОГОВОМУ статусу РК — тому, что показывает экран, а не нажатой
кнопке: «запущена» у нас это ФАКТ (крутит хоть одна площадка), и кнопка «Запустить» без
запущенных площадок оставляет РК «готовой». Послать тогда LAUNCHED значило бы снова
развести экран и DSP, только в другую сторону (ревью 23.09.2026).

  · итоговое «запущена»             → полный план (`Campaign.edit`) + LAUNCHED;
  · «готова», «ожидает сборки»,
    «пауза», «остановлена»           → STOPPED — у нас обратимо, в DSP тоже;
  · «окончена», «архив»              → ARCHIVE — назад не включается ни там, ни у нас.

Сбой DSP — отказ, изменения откатываются: экран не должен говорить о кампании то,
чего в DSP нет.
"""
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.dsp import campaigns as dc
from app.dsp.client import MsError
from app.routers import traffic_dashboard as td

XX = "AC71A89189EDD994"


class FakeMs:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def campaign_edit(self, xxhash, params, local_ref=None):
        self.calls.append(("edit", xxhash, params["limits"]["show"]["total"]))

    def campaign_set_status(self, xxhash, status, local_ref=None):
        if self.fail:
            raise MsError("Campaign.setStatus: обрыв")
        self.calls.append(("status", xxhash, status))


class _Db:
    def __init__(self, placement=None):
        self.deal = SimpleNamespace(id=1, code="HCLA6E", title="Сделка")
        self.placement = placement
        self.commits = self.rollbacks = 0

    def query(self, model):
        deal, pl = self.deal, self.placement
        return SimpleNamespace(get=lambda i: pl if pl is not None and i == pl.id else deal,
                               filter_by=lambda **kw: SimpleNamespace(all=lambda: []))

    def flush(self):
        pass

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _camp(xx=XX, status="готова"):
    return SimpleNamespace(id=5, deal_id=1, status=status, ms_campaign_xxhash=xx,
                           month=date(2026, 10, 1), date_start=date(2026, 10, 1),
                           date_end=date(2026, 10, 31), plan_show=120000, plan_click=0,
                           plan_budget=0, ms_synced_at=None)


@pytest.fixture
def press(monkeypatch):
    state = {"camp": _camp(), "ms": FakeMs(), "chain": "запущена", "db": _Db()}
    monkeypatch.setattr(td, "_campaign_in_scope",
                        lambda db, cid, u: (state["camp"], SimpleNamespace(id=1, our_stage_id=None)))
    monkeypatch.setattr(td, "log_action", lambda *a, **kw: None)
    monkeypatch.setattr(td, "_tell_publishers_started", lambda db, c: None)
    monkeypatch.setattr(td, "_campaign_chain", lambda db, c: state["chain"])
    monkeypatch.setattr(dc, "MsClient", lambda *a, **kw: state["ms"])

    def go(status):
        return td.set_campaign_status(5, td.StatusIn(status=status), state["db"],
                                      SimpleNamespace(id=1))
    state["go"] = go
    return state


def test_launch_sends_the_plan_and_starts_the_campaign(press):
    out = press["go"]("запущена")
    assert press["ms"].calls == [("edit", XX, 120000), ("status", XX, "LAUNCHED")], (
        "план должен уйти ДО запуска, иначе кампания стартует со старым")
    assert out["dsp_status"] == "LAUNCHED"


def test_launch_with_nothing_running_keeps_dsp_stopped(press):
    """«Запустить» без запущенных площадок: экран покажет «готова» — и DSP стоит."""
    press["chain"] = "готова"
    press["go"]("запущена")
    assert press["ms"].calls == [("status", XX, "STOPPED")]


@pytest.mark.parametrize("ours,theirs", [("пауза", "STOPPED"), ("остановлена", "STOPPED"),
                                         ("окончена", "ARCHIVE"), ("архив", "ARCHIVE")])
def test_stopping_reaches_dsp(press, ours, theirs):
    press["camp"].status = "запущена"
    press["go"](ours)
    assert press["ms"].calls == [("status", XX, theirs)]


def test_dsp_failure_rolls_our_change_back(press):
    press["ms"] = FakeMs(fail=True)
    with pytest.raises(HTTPException) as e:
        press["go"]("запущена")
    assert e.value.status_code == 502
    assert press["db"].rollbacks and not press["db"].commits, (
        "экран скажет «крутится», а в DSP стоит")


def test_campaign_not_in_dsp_changes_only_our_status(press):
    press["camp"] = _camp(xx=None)
    press["go"]("запущена")
    assert press["ms"].calls == []
    assert press["camp"].status == "запущена"


def test_an_archived_campaign_is_not_relaunched(press):
    """ARCHIVE в DSP назад не включается: вместо вечного 502 — понятный отказ сразу."""
    press["camp"].status = "архив"
    with pytest.raises(HTTPException) as e:
        press["go"]("запущена")
    assert e.value.status_code == 400
    assert press["ms"].calls == []


def test_finish_archives_the_dsp_campaign(press, monkeypatch):
    """«Завершить РК» — тоже кнопка: без неё кампания в DSP крутила бы дальше."""
    from app.sales import catalog
    monkeypatch.setattr(catalog, "Catalog",
                        lambda db: SimpleNamespace(stages=[], by_id={}))
    press["camp"].status = "запущена"
    td.finish_campaign(5, press["db"], SimpleNamespace(id=1))
    assert press["ms"].calls == [("status", XX, "ARCHIVE")]


def test_placement_launch_makes_dsp_follow(press, monkeypatch):
    """Площадка запущена — РК стала «запущена» по факту, и DSP это видит."""
    pl = SimpleNamespace(id=9, campaign_id=5, status="ждёт запуска", publisher_id=3)
    press["db"] = _Db(placement=pl)
    monkeypatch.setattr(td, "_creatives_of", lambda db, cid: {9: [{"status": "согласован"}]})
    monkeypatch.setattr(td.build, "recompute_shares", lambda db, cid: None)
    monkeypatch.setattr(td.build, "mark_target_placed", lambda db, p: 0)
    td.set_placement_status(9, td.StatusIn(status="запущен"), press["db"],
                            SimpleNamespace(id=1))
    assert ("status", XX, "LAUNCHED") in press["ms"].calls
