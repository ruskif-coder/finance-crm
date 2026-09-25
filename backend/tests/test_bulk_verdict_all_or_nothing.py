# -*- coding: utf-8 -*-
"""Массовый вердикт трафика: всё или ничего, письма — после записи (аудит 23.09.2026, 5.M2).

Письмо площадке уходило ВНУТРИ цикла, а отправка фиксирует базу сама. Отказ на паре K
(чужая или несуществующая — 403/404 вне перехвата) оставлял вердикты 1…K-1 записанными,
письма ушедшими, а журнал действий и событие «трафик вернул» — невыполненными: человек
видел ошибку при наполовину сделанном действии.

База подменена: проверяется порядок — проверка всех пар, запись, и только потом письма.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import traffic as T


class _Db:
    def __init__(self, trail):
        self.trail = trail

    def commit(self):
        self.trail.append("commit")


@pytest.fixture
def wired(monkeypatch):
    trail = []

    def in_scope(db, pid, user):
        if pid == 3:
            raise HTTPException(status_code=404, detail="Задание не найдено")
        return (SimpleNamespace(id=pid), SimpleNamespace(id=11, no=1), None,
                SimpleNamespace(id=7), SimpleNamespace(id=1, code="X"))

    def apply(db, pair, s, target, pub, deal, verdict, reason, user):
        trail.append(f"verdict{pair.id}")
        return True

    monkeypatch.setattr(T, "_pair_in_scope", in_scope)
    monkeypatch.setattr(T, "_apply_verdict", apply)
    monkeypatch.setattr(T, "_tell_publisher",
                        lambda db, pair, *a: trail.append(f"letter{pair.id}"))
    monkeypatch.setattr(T, "log_action", lambda *a, **kw: trail.append("log"))
    monkeypatch.setattr(T, "emit", lambda *a, **kw: trail.append("emit"))
    # Остановка нацеливания после вердикта ходит в DSP — здесь только отмечаем её.
    monkeypatch.setattr(T, "_stop_targeting", lambda ids, db: trail.append("stop"))
    return SimpleNamespace(trail=trail, db=_Db(trail), user=SimpleNamespace(name="т"))


def test_a_foreign_pair_stops_everything_before_any_write(wired):
    with pytest.raises(HTTPException):
        T.bulk_verdict(T.BulkVerdictIn(pair_ids=[1, 2, 3], verdict="ок"),
                       wired.db, wired.user)
    assert not [x for x in wired.trail if x.startswith(("verdict", "letter"))], (
        f"первые пары записаны и письма ушли, а запрос отклонён: {wired.trail}")


def test_letters_go_only_after_the_verdicts_are_saved(wired):
    T.bulk_verdict(T.BulkVerdictIn(pair_ids=[1, 2], verdict="ок"), wired.db, wired.user)
    t = wired.trail
    assert "log" in t
    first_letter = next(i for i, x in enumerate(t) if x.startswith("letter"))
    assert "commit" in t[:first_letter], f"письмо ушло до записи вердиктов: {t}"
