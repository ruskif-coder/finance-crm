# -*- coding: utf-8 -*-
"""Продление (владелец 21.10.2026): на сборку копию держит только виза медиаплана, остальные требования не запирают."""
from app.sales import stage_checks as sc
from app.sales import stage_move as SM


def _line(key, blocking, done):
    return sc.Line(key=key, title=key, hint="", is_blocking=blocking,
                   result=sc.Result(sc.OK if done else sc.NOT_YET, ""))


def test_only_mp_visa_blocks_prolonged_copy():
    lines = [_line("payer_set", True, False), _line("final_contract", True, False), _line("mp_verified", False, False)]
    out = SM._prolong_lines(lines)
    assert [ln.key for ln in sc.blockers(out)] == ["mp_verified"]
    assert len(out) == len(lines)                         # остальное остаётся на экране


def test_prolonged_copy_passes_once_visa_is_given():
    lines = [_line("payer_set", True, False), _line("mp_verified", False, True)]
    assert sc.blockers(SM._prolong_lines(lines)) == []
