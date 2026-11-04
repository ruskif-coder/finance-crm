# -*- coding: utf-8 -*-
"""Переписка по площадке запроса на приоритезацию (владелец 04.11.2026).

Поломка, которую ловит: замечание площадки и ответ аккаунта в одном поле `comment` — ответ затирал замечание, и на экранах
оставалось только последнее. Теперь каждый ход — строка `prio_placement_messages`, по порядку, с автором.
"""
from app.prio import models as M
from app.prio import service as S
from tests.test_prio import _U, _ready, env  # noqa: F401 — фикстура


def test_every_move_is_kept_in_order_and_remark_survives_the_reply(env):  # noqa: F811
    db, d, pubs = env
    p = _ready(db, d, pubs[0])
    S.edit_placement(db, d, p.id, {"product_url": "https://maksavit.ru/p/1"})
    S.send(db, d, p.id, _U())
    S.verdict(db, p, "вернуть", "у нас это 10 мг, не 5", author_name="Иванова", author_email="iv@site.example")
    S.reply(db, d, p.id, "поправили на 10 мг", _U())
    S.remind(db, d, p.id, _U())
    S.verdict(db, p, "отказ", "товара нет в ассортименте", author_name="Иванова")
    talk = S.messages(db, p.id)
    assert [(m["side"], m["kind"]) for m in talk] == [
        ("мы", "отправка"), ("площадка", "замечание"), ("мы", "ответ"), ("мы", "напоминание"), ("площадка", "отказ")]
    assert talk[1]["body"] == "у нас это 10 мг, не 5" and talk[1]["author"] == "Иванова", "замечание площадки затёрто"
    assert talk[2]["body"] == "поправили на 10 мг"
    assert p.comment == "товара нет в ассортименте", "последнее сообщение для уведомлений и кабинета — последний текст"
    row = db.query(M.PrioMessage).filter(M.PrioMessage.placement_id == p.id, M.PrioMessage.kind == "замечание").one()
    assert row.author_email == "iv@site.example"
    view = [x for x in S.view(db, d)["placements"] if x["id"] == p.id][0]
    assert [m["kind"] for m in view["messages"]] == [m["kind"] for m in talk]


def test_approval_is_a_move_too(env):  # noqa: F811
    db, d, pubs = env
    p = _ready(db, d, pubs[0])
    S.edit_placement(db, d, p.id, {"product_url": "https://maksavit.ru/p/1"})
    S.send(db, d, p.id, _U())
    S.set_sku(db, p, "1234567")
    S.verdict(db, p, "ок", None, author_name="Петров")
    assert [(m["side"], m["kind"], m["author"]) for m in S.messages(db, p.id)][-1] == ("площадка", "согласование", "Петров")
    assert p.comment is None, "согласование без текста не должно подменять последнее сообщение"
