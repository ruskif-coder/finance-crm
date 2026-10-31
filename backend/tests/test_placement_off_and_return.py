# -*- coding: utf-8 -*-
"""Отключить площадку и вернуть её в распределение (владелец 31.10.2026).

Площадку вне нашей DSP нужно уметь вывести из РК: её галочка «заведён и запущен» снималась
только в паузу, а пауза долю держит — площадка продолжала забирать объём. Отключение — тот же
статус «завершена», что у кнопки площадки нашей DSP.

Вернуть отключённую — НЕ запуск: «креатив — это ЕРИД, в обход этого мы не можем двигаться».
Площадка возвращается туда, где её держит согласование креативов, и дальше идёт обычным путём:
запуск — только с согласованным креативом.
"""
from types import SimpleNamespace

import pytest

from app.ad import flight
from app.routers import traffic_dashboard as td
from tests.test_campaign_button_drives_dsp import (_Db, _no_share_lock, _no_volume_guard,  # noqa: F401
                                                    press)


@pytest.fixture
def row(press, monkeypatch):  # noqa: F811  (press — фикстура из импорта)
    """Площадка РК 5 с заданными креативами; пересчёт долей записывается, а не считается."""
    from app.launch_prep import pub_rules
    monkeypatch.setattr(pub_rules, "placement_modes",
                        lambda db, keys: {k: {"mode": pub_rules.MODE_EXTERNAL} for k in keys})
    monkeypatch.setattr(td.build, "mark_target_placed", lambda db, p: 0)
    seen = {"recompute": 0}
    monkeypatch.setattr(td.build, "recompute_shares",
                        lambda db, cid: seen.__setitem__("recompute", seen["recompute"] + 1))

    def make(status, creatives):
        pl = SimpleNamespace(id=9, campaign_id=5, status=status, publisher_id=3)
        press["db"] = _Db(placement=pl)
        monkeypatch.setattr(td, "_creatives_of",
                            lambda db, cid: {9: [{"status": s} for s in creatives]})
        return pl

    def go(pl, status):
        return td.set_placement_status(pl.id, td.StatusIn(status=status), press["db"], SimpleNamespace(id=1))

    return SimpleNamespace(make=make, go=go, seen=seen)


def test_external_placement_is_turned_off_before_launch(row):
    """Отключить можно и до запуска: в удержание долей площадку в работе делят все, и иначе её не вывести."""
    pl = row.make("у площадки", ["у площадки"])
    row.go(pl, flight.PLACEMENT_OFF)
    assert pl.status == "завершена" and row.seen["recompute"] == 1


@pytest.mark.parametrize("creatives, back", [
    (["согласован"], "ждёт запуска"),
    (["у площадки", "у трафика"], "у площадки"),
    (["запущен"], "ждёт запуска"),          # креатив запускали руками — он согласован
    (["пауза", "отклонён"], "ждёт запуска"),
    (["отклонён"], "ждёт сборки"),
    ([], "ждёт сборки"),
])
def test_return_puts_the_placement_where_its_creatives_hold_it(row, creatives, back):
    pl = row.make("завершена", creatives)
    row.go(pl, flight.PLACEMENT_RETURN)
    assert pl.status == back, "вернуть — не запустить: статус по согласованию креативов"
    assert row.seen["recompute"] == 1, "без пересчёта доля не вернулась бы до ночи"


def test_only_a_turned_off_placement_is_returned(row):
    pl = row.make("пауза", ["согласован"])
    with pytest.raises(td.HTTPException) as e:
        row.go(pl, flight.PLACEMENT_RETURN)
    assert e.value.status_code == 400 and pl.status == "пауза"


def test_returned_status_survives_the_screen_and_the_sync():
    """Возвращённую площадку экран и синк считают тем же правилом: креатив, запущенный руками,
    в шкале площадки — согласованный. Иначе экран показал бы «ждёт сборки» у площадки, чей
    креатив уже крутился."""
    assert flight.as_placement_scale("запущен") == flight.PLACEMENT_READY
    assert flight.as_placement_scale("пауза") == flight.PLACEMENT_READY
    assert flight.best_chain_status([flight.as_placement_scale("отклонён")]) == flight.PLACEMENT_WAIT


def test_return_rechecks_the_status_after_waiting_for_the_lock(row, monkeypatch):
    """Два «Вернуть» подряд: второй прошёл проверку статуса, пока ждал замок, а площадку за это время
    запустили. Проверка ДО замка пропустила бы его, и «запущен» затёрся бы статусом цепочки
    (ревью 31.10.2026). Проверять — после замка, по перечитанной строке."""
    pl = row.make("завершена", ["согласован"])

    def someone_started_it_meanwhile(db, cid):
        pl.status = "запущен"
    monkeypatch.setattr(td, "_lock_shares", someone_started_it_meanwhile)

    with pytest.raises(td.HTTPException) as e:
        row.go(pl, flight.PLACEMENT_RETURN)
    assert e.value.status_code == 400 and pl.status == "запущен"
