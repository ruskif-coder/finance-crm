# -*- coding: utf-8 -*-
"""Состояние строки — про ЭТОТ материал, а не про площадку вообще.

Найдено на живой сделке 54ZYCH 17.09.2026. Согласовали третий комплект по Maksavit.ru —
и первый с вторым, которые этой площадке НИ РАЗУ НЕ ОТПРАВЛЯЛИ (ноль пар), загорелись
тем же зелёным.

Причина — разное зерно. `launch_prep_target.state` описывает пару «сделка × площадка»:
он один на все комплекты этой площадки. Строка внутри комплекта описывает пару
«комплект × площадка». Пока состояние отдавалось как есть, экран утверждал, что
согласован каждый материал, хотя согласован был один.

Цена ошибки прямая: аккаунт видит зелёное и считает работу сделанной.
"""
from app.routers.launch_prep import AFTER_AGREEMENT_STATES, _recipient_out


class _T:
    id = 65
    publisher_id = 65
    surface_kind = "web"
    advertiser_url = "https://example.test/"
    url_requested_at = None
    url_request_text = None

    def __init__(self, state):
        self.state = state


class _Pair:
    id = 1
    code = "54ZYCH-MXV-01"
    sent_at = None


class _Review:
    def __init__(self, verdict):
        self.verdict = verdict
        self.reason = None
        self.decided_by = None


def test_a_set_never_sent_does_not_inherit_the_publisher_state():
    """Ровно случай 54ZYCH: у комплекта нет пары, а площадка уже в размещении."""
    out = _recipient_out(_T("в размещении"), None)
    assert out["state"] == "согласование", (
        "комплект без пары показывает состояние площадки из другого комплекта")
    # Состояние площадки в кампании при этом не потеряно — оно рядом, своим полем.
    assert out["campaign_state"] == "в размещении"


def test_a_pair_without_a_verdict_does_not_inherit_it_either():
    """Отправили, но площадка ещё не ответила — это «ждём», а не «согласовано»."""
    out = _recipient_out(_T("ерид получен"), None, _Pair(), None)
    assert out["state"] == "согласование"


def test_an_agreed_pair_shows_the_real_state():
    """Обратная половина: у согласованного материала состояние показывается как есть.

    Без неё прибор доказывал бы только то, что мы всё погасили.
    """
    out = _recipient_out(_T("ерид получен"), None, _Pair(), _Review("ок"))
    assert out["state"] == "ерид получен"


def test_a_refusal_stays_campaign_wide():
    """Отказ площадки — боковой выход из кампании: новая версия материала ей уже не
    поможет, и гасить его в соседних комплектах нельзя."""
    out = _recipient_out(_T("отказ площадки"), None)
    assert out["state"] == "отказ площадки"
    assert "отказ площадки" not in AFTER_AGREEMENT_STATES
