# -*- coding: utf-8 -*-
"""Подзаголовок письма площадке по признаку «ждёт действия площадки», а не по цвету
карточки (владелец 06.10.2026): письмо с баннерами на согласование говорило «Все — к
сведению, действий не требуется», потому что карточка «новый креатив» информационная."""
from app.mail import editor
from app.notify.outward import digest as D
from app.notify.outward import kinds as K

NEEDS = {"новый креатив", "старт близко", "запрос ссылки", "техтребования", "сверка",
         "документы не подписаны", "реквизиты устарели"}


def test_action_kinds_are_marked():
    marked = {k.key for k in K.KINDS if k.needs_action}
    assert marked == NEEDS


class _Row:
    def __init__(self, kind, tone="info"):
        self.kind, self.tone = kind, tone
        self.title, self.body, self.link_abs, self.tag, self.context = "t", "b", None, "", None
        self.created_at, self.facts = None, []


def test_new_creative_digest_asks_for_action():
    cards = [D._card(_Row("новый креатив")), D._card(_Row("новый креатив"))]
    assert editor.computed(cards)["срочное"] == "Все требуют действия сегодня."


def test_info_only_digest_still_says_no_action():
    cards = [D._card(_Row("ерид выпущен", "ok")), D._card(_Row("финиш рк"))]
    assert "не требуется" in editor.computed(cards)["срочное"]


def test_mixed_digest_counts_action_cards():
    cards = [D._card(_Row("новый креатив")), D._card(_Row("ерид выпущен", "ok"))]
    assert editor.computed(cards)["срочное"].startswith("1 требует действия")


def test_staff_cards_without_flag_keep_tone_rule():
    """У писем сотрудникам признака нет — там по-прежнему считается по цвету."""
    assert "не требуется" not in editor.computed([{"tone": "bad"}])["срочное"]


def test_status_flags_stuck_publisher_digest():
    """06.10.2026: очередь писем площадкам стояла 4 дня, и экран состояния этого не видел."""
    from app.system import status as S

    class _Res:
        def __init__(self, v):
            self.v = v

        def first(self):
            return self.v

    class _Db:
        def __init__(self, v):
            self.v = v

        def execute(self, *a, **k):
            return _Res(self.v)

    from datetime import datetime, timedelta
    old = datetime.utcnow() - timedelta(days=4)
    assert S.check_outward_digest(_Db((37, old)))["tone"] == "bad"
    assert S.check_outward_digest(_Db((0, None)))["tone"] == "ok"
