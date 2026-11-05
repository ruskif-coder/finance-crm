"""Заголовок и «место и дата» ДС правятся ТОЛЬКО в шаблоне (владелец 05.11.2026: «из карточки ДС убери»).

Падает, если правка в карточке ДС (своя или унаследованная от прошлого ДС договора) снова начнёт
перекрывать текст шаблона, или если ручка правки блока ДС снова примет заголовок/место.
"""
import inspect

from app.annex_tpl.assemble import HEAD_DEFAULT, _sys_text


def test_card_edit_does_not_override_template_head():
    # правок карточки функция больше не принимает вовсе — источник один, шаблон
    assert "edits" not in inspect.signature(_sys_text).parameters
    out = _sys_text(HEAD_DEFAULT, {}, "текст шаблона")
    assert out["template"] == "текст шаблона"
    assert out["edited"] is False and out["inherited_from"] is None


def test_no_template_text_falls_back_to_standard_sample():
    out = _sys_text("{место} | {дата_дс_полностью}", {}, "")
    assert out["template"] == "{место} | {дата_дс_полностью}"
    assert out["custom"] is False


def test_annex_block_edit_route_refuses_head_and_place():
    from app.routers import annexes
    src = inspect.getsource(annexes)
    assert "_may_change_rk(db, user)" not in src.split("key = payload.key", 1)[1].split("if payload.text is not None", 1)[0], \
        "заголовок/место в карточке ДС не правятся никем — отказ без проверки права"
