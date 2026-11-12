# -*- coding: utf-8 -*-
"""Отметки отправки клиенту в реестре v3 (хендофф 12.11.2026): у каждого ДС и комплекта своя отметка, главная кнопка полосы
отмечает все оставшиеся разом, «отменить» снимает ошибочную отметку, пока пакет на «выставлении».

Поломки, которые ловит набор:
- «отменить» оставляет документ «выставленным» или уводит его не туда (ЭДО-ДС → не «согласован», УПД → не пусто, бумага →
  не «подписан у нас»);
- отмена разрешена после «ждём оплату» — пакет уже ушёл дальше по последней отметке;
- «отметить все» трогает уже отправленные (второе событие «выставлен» сдвигает срок ожидания подписанных);
- после отметки всех пакет не уходит в «ждём оплату»."""
from types import SimpleNamespace

import pytest

from app.master_deal import doc_sign as DS
from app.master_deal import issue as IS


def _ds(state, id_=1, channel="ЭДО"):
    return SimpleNamespace(__tablename__="sales_annexes", id=id_, no=4, sign_state=state, sign_channel=channel,
                           master_deal_id=10, contract_id=3, number=f"ДС № {id_}")


def _upd(state, upd_no=1, channel="ЭДО"):
    return SimpleNamespace(__tablename__="master_deal_upds", id=100 + upd_no, sign_state=state, sign_channel=channel,
                           master_deal_id=10, upd_no=upd_no)


U = SimpleNamespace(id=7)


@pytest.fixture
def env(monkeypatch):
    st = {"channel": "ЭДО", "events": []}
    monkeypatch.setattr(DS, "_contract_channel", lambda db, doc: st["channel"])
    monkeypatch.setattr(DS, "_scan_id", lambda db, doc: None)
    monkeypatch.setattr(DS, "_write_event", lambda db, doc, **kw: st["events"].append(kw))
    return st


@pytest.mark.parametrize("doc, back", [
    (_ds("выставлен"), "согласован"),
    (_upd("выставлен"), None),
    (_ds("выставлен", channel="бумага"), "подписан у нас"),
    (_upd("выставлен", channel="бумага"), "подписан у нас"),
])
def test_unsend_returns_the_doc_one_step_back(env, doc, back):
    DS.unsend(None, doc, U)
    assert doc.sign_state == back
    assert env["events"][-1]["state"] == "отправка снята"


@pytest.mark.parametrize("state", ["согласован", "подписан", "отклонён", None])
def test_only_a_sent_doc_can_be_unsent(env, state):
    with pytest.raises(DS.SignError) as e:
        DS.unsend(None, _ds(state), U)
    assert e.value.status == 409


class _Db:
    def flush(self):
        pass


def _pack(status="выставление"):
    return SimpleNamespace(id=10, status=status, updated_at=None)


@pytest.fixture
def pack(monkeypatch, env):
    box = {"docs": []}
    monkeypatch.setattr(IS, "docs", lambda db, m: box["docs"])
    return box


def test_send_all_marks_only_the_rest_and_moves_the_pack(pack, env):
    a, k1, k2 = _ds("выставлен"), _upd(None, 1), _upd(None, 2)
    pack["docs"] = [a, k1, k2]
    m = _pack()
    moved = IS.send_docs(_Db(), m, [a, k1, k2], True, U)
    assert [e["state"] for e in env["events"]] == ["выставлен", "выставлен"]       # ДС уже был отправлен — не трогаем
    assert (k1.sign_state, k2.sign_state) == ("выставлен", "выставлен")
    assert moved is True and m.status == "ждём оплату"


def test_send_some_keeps_the_pack_on_issue(pack, env):
    a, k1 = _ds("согласован"), _upd(None, 1)
    pack["docs"] = [a, k1]
    m = _pack()
    assert IS.send_docs(_Db(), m, [a], True, U) is False
    assert m.status == "выставление" and a.sign_state == "выставлен" and k1.sign_state is None


def test_unsend_only_while_the_pack_is_on_issue(pack, env):
    a = _ds("выставлен")
    pack["docs"] = [a]
    with pytest.raises(DS.SignError) as e:
        IS.send_docs(_Db(), _pack("ждём оплату"), [a], False, U)
    assert e.value.status == 409 and a.sign_state == "выставлен"
    IS.send_docs(_Db(), _pack(), [a], False, U)
    assert a.sign_state == "согласован"


def test_paper_signed_by_us_for_all_does_not_move_the_pack(pack, env):
    env["channel"] = "бумага"
    a, k1 = _ds("согласован", channel=None), _upd(None, 1, channel=None)
    pack["docs"] = [a, k1]
    m = _pack()
    assert IS.send_docs(_Db(), m, [a, k1], True, U, state="подписан у нас") is False
    assert (a.sign_state, k1.sign_state) == ("подписан у нас", "подписан у нас") and m.status == "выставление"


def test_view_says_when_and_who_sent(monkeypatch, env):
    monkeypatch.setattr(DS, "_last_sent", lambda db, doc: ("2026-11-12T15:30:00", "Валерия"))
    v = DS.view(None, _ds("выставлен"))
    assert (v["sent_at"], v["sent_by"]) == ("2026-11-12T15:30:00", "Валерия")
    v = DS.view(None, _ds("согласован"))
    assert v["sent_at"] is None and v["sent_by"] is None


def test_edo_send_of_an_issued_ds_passes_agreed_in_history(pack, env):
    """В v3 у ЭДО нет шага «согласован клиентом»: подписание в Диадоке и есть согласие. Выпущенный ДС уходит клиенту, а в
    истории остаются оба события — «согласован» и «выставлен»."""
    a = _ds("выпущен")
    pack["docs"] = [a]
    IS.send_docs(_Db(), _pack(), [a], True, U)
    assert a.sign_state == "выставлен"
    assert [e["state"] for e in env["events"]] == ["согласован", "выставлен"]


def test_paper_signed_by_us_of_an_issued_ds_passes_agreed_too(pack, env):
    env["channel"] = "бумага"
    a = _ds("выпущен", channel=None)
    pack["docs"] = [a]
    IS.send_docs(_Db(), _pack(), [a], True, U, state="подписан у нас")
    assert [e["state"] for e in env["events"]] == ["согласован", "подписан у нас"]
