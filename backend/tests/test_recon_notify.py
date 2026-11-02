# -*- coding: utf-8 -*-
"""Сверка месяца — площадке почтой и в бот (владелец 02.11.2026).

Поломки: шаг сверки молчит (площадка узнаёт о сверке, только зайдя в кабинет — так было до 02.11); вид не помечен
`built` и `notify_publisher` падает; вид уходит в утренний дайджест и съедает день из двухдневного срока; в письмо
попадают деньги; событие не попадает в ленту кабинета.
"""
import inspect
from datetime import date

from app.cabinet import journal
from app.notify import recon as N
from app.notify.outward import kinds, send
from app.routers import publisher_recon as R


def test_kind_is_built_and_goes_out_at_once():
    k = kinds.by_key("сверка")
    assert k.built and k.schedule == "сразу" and k.needs_action
    assert send.JOURNAL_ACTION["сверка"] == "увед_сверка"
    assert "увед_сверка" in {a.key for a in journal.ACTIONS}


def test_new_recon_letter():
    title, body, facts = N.message("новая", "октябрь 2026", 1250000, None, date(2026, 11, 4))
    assert title == "Сверка за октябрь 2026"
    assert "до 04.11" in body
    assert facts == [("показов у нас", "1 250 000")]


def test_reply_carries_both_numbers_and_our_offer():
    _, body, facts = N.message("ответ", "октябрь 2026", 1250000, 1300000, date(2026, 11, 6), offer=1270000)
    assert facts == [("показов у нас", "1 250 000"), ("показов у вас", "1 300 000"), ("предлагаем", "1 270 000")]
    assert "до 06.11" in body


def test_closed_recon_says_the_total_and_asks_nothing():
    title, body, facts = N.message("итог", "октябрь 2026", 1250000, 1300000, None, agreed=1270000)
    assert title == "Сверка за октябрь 2026 закрыта" and "не требуется" in body
    assert facts == [("итог показов", "1 270 000")]


def test_no_money_in_the_letter():
    for why in N.WHY:
        title, body, facts = N.message(why, "октябрь 2026", 1, 2, date(2026, 11, 4), offer=3, agreed=4)
        text = " ".join([title, body] + [a + b for a, b in facts]).lower()
        assert "₽" not in text and "руб" not in text and "cpm" not in text and "сумм" not in text


def test_every_our_step_tells_the_site():
    """Отправка (по одной и все готовые), напоминание, наш ответ, итог — каждый шаг зовёт `to_site`."""
    for fn, why in ((R.send, '"новая"'), (R.send_all, '"новая"'), (R.remind, '"напоминание"'),
                    (R.reply, '"ответ"'), (R.agree, '"итог"')):
        src = inspect.getsource(fn)
        assert "N.to_site(" in src and why in src, fn.__name__
        assert src.index("db.commit()") < src.index("N.to_site("), f"{fn.__name__}: письмо до коммита"
