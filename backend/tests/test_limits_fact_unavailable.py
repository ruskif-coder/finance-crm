# -*- coding: utf-8 -*-
"""Лимиты креативов при недоступной аналитике (ревью 27.10.2026, v2.7.0..).

С 24.10 лимит креатива — свой факт + доля остатка площадки. Когда аналитика DSP не читается, `creative_fact.totals` тихо
отдавал только Adfox, раскладка считала факт нулём и делила план поровну — и ночная синхронизация ОТПРАВЛЯЛА это в DSP:
план 1000, креатив А открутил 900, Б новый → А 500, Б 500, итог до 1400. Поломка, которую ловит тест: при сбое чтения
факта синхронизация шлёт лимиты. Правильно — не трогать лимиты РК (креативы крутят по прежним) и сказать об этом в отчёте."""
from types import SimpleNamespace

import pytest

import app.model_registry  # noqa: F401
from app.ad import creative_fact
from app.dsp import limits


class _Db:
    def execute(self, *a, **k):
        return SimpleNamespace(all=lambda: [])


def test_strict_totals_raise_when_analytics_fails(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("аналитика недоступна")
    monkeypatch.setattr(creative_fact, "dsp_days", boom)
    camp = SimpleNamespace(id=1, ms_campaign_xxhash="x")
    assert creative_fact.totals(_Db(), camp, dsp_db=object()) == {}          # мягкий режим — как раньше
    with pytest.raises(creative_fact.FactUnavailable):
        creative_fact.totals(_Db(), camp, dsp_db=object(), strict=True)


def test_sync_limits_sends_nothing_when_fact_is_unavailable(monkeypatch):
    def unavailable(db, camp, **k):
        raise creative_fact.FactUnavailable("нет")
    monkeypatch.setattr(limits, "creative_plans", unavailable)
    sent = []
    client = SimpleNamespace(creative_edit=lambda *a, **k: sent.append(a), last_sent_show_limit=lambda ref: None)
    got = limits.sync_limits(None, SimpleNamespace(id=5), client)
    assert sent == [] and got["updated"] == 0 and got.get("skipped")
