# -*- coding: utf-8 -*-
"""Храповик: копейки — правилом `final_recon.money.r2` (половина вверх), а не встроенным `round(float(x), 2)`
(половина к чётному: round(2.675, 2) = 2.67, r2 — 2.68). Аудит 13.11.2026: в приложении 30 строк `round(float(…), 2)` против
13 вызовов `r2`, и релиз 2.7.52 добавил ещё четыре. Чинить все разом — не сейчас (часть — коэффициенты, а не деньги); храповик
не даёт числу расти. Сломать: добавить `round(float(x), 2)` в новом коде — тест назовёт файл. Починили место — опустите число."""
import pathlib
import re

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
CEILING = 26          # 14.11.2026 после перевода четырёх мест 2.7.52 на r2; только уменьшать


def test_round_float_two_does_not_grow():
    pat = re.compile(r"round\(float\(.*,\s*2\)")
    hits = [f"{f.relative_to(APP).as_posix()}:{i}" for f in APP.rglob("*.py") if f.name != "money.py"
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1) if pat.search(line)]
    assert len(hits) <= CEILING, f"round(float(…), 2) вне money.py: {len(hits)} > {CEILING} — используйте money.r2:\n" + "\n".join(hits)
