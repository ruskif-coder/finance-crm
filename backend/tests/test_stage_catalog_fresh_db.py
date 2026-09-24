# -*- coding: utf-8 -*-
"""Разметка срыва и архива не зависит от нумерации стадий (аудит 23.09.2026, 7.6).

Миграция `2026-08-17_account_dashboard.sql` ставила «срыв», «терминальная» и SLA по
НОМЕРАМ стадий — сознательно: имена стадий меняются. Но номера верны только для базы,
на которой её писали. На свежей базе каталог засевается заново, и номер 4 там — «Бронь»,
а 9 — «Подготовка ДС»: миграция объявила бы их провалом сделки.

Теперь признаки на свежей базе ставит сам засев (он знает, что создаёт), а миграция
обновляет по номеру, только если под этим номером стоит та самая стадия.
"""
import io
import re
from pathlib import Path

import app.main as main
from app.sales.models import SalesStage, SalesStagePhase

MIG = (Path(__file__).resolve().parent.parent / "migrations"
       / "2026-08-17_account_dashboard.sql")


class _Q:
    def __init__(self, items):
        self.items = items

    def first(self):
        return None

    def filter(self, *a):
        return self

    def all(self):
        return self.items


class _Db:
    """Пустая база: засев идёт полным путём и складывает созданное сюда."""

    def __init__(self):
        self.added = []

    def query(self, model):
        return _Q([o for o in self.added if isinstance(o, SalesStagePhase)]
                  if model is SalesStagePhase else [])

    def add(self, obj):
        if isinstance(obj, SalesStagePhase):
            obj.id = len(self.added) + 1
        self.added.append(obj)

    def flush(self):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _seeded(monkeypatch):
    db = _Db()
    monkeypatch.setattr(main, "SessionLocal", lambda: db)
    main.seed_stage_catalog()
    return {s.name: s for s in db.added if isinstance(s, SalesStage)}


def test_a_fresh_catalog_knows_its_lost_and_terminal_stages(monkeypatch):
    st = _seeded(monkeypatch)
    lost = {n for n, s in st.items() if s.is_lost}
    assert lost == {"Сделка не случилась", "Сделка сорвалась"}, lost
    terminal = {n for n, s in st.items() if s.is_terminal}
    assert terminal == {"Сделка не случилась", "Сделка сорвалась",
                        "Архив успешных сделок"}, terminal


def test_a_fresh_catalog_carries_the_stage_sla(monkeypatch):
    st = _seeded(monkeypatch)
    assert st["МП Отправлено"].sla_days == 5
    assert st["В размещении"].sla_days == 0
    assert st["Итоговая сверка"].sla_days == 3
    assert st["Оплата"].sla_days == 0
    for n in ("Сделка не случилась", "Сделка сорвалась", "Архив успешных сделок"):
        assert st[n].sla_days == 0, n
    assert st["Бронь"].sla_days is None      # наследует срок этапа


def test_the_migration_updates_a_stage_by_number_only_if_it_is_that_stage():
    sql = io.open(MIG, encoding="utf-8").read()
    updates = re.findall(r"UPDATE sales_stages\b[^;]*;", sql)
    assert updates
    for u in updates:
        if re.search(r"\bid\s*(=|IN)", u):
            assert "name" in u, f"обновление по номеру без проверки имени: {u}"
