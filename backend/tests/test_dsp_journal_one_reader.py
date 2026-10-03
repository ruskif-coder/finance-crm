# -*- coding: utf-8 -*-
"""Журнал обмена с DSP читается только функциями модуля DSP (аудит интеграций 02.10.2026).

До правки `dsp_send_log` читали прямым SQL роутер демо-экрана, лента «Логи» и экран
«Статус системы» — три копии условий по контуру. Прибор: вне `app/dsp/` таблицу никто
не называет.
"""
import pathlib

APP = pathlib.Path(__file__).resolve().parents[1] / "app"


def test_journal_table_named_only_inside_dsp_module():
    offenders = []
    for p in APP.rglob("*.py"):
        if "dsp" in p.relative_to(APP).parts[:1]:
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "FROM dsp_send_log" in line or "UPDATE dsp_send_log" in line:
                offenders.append(f"{p.relative_to(APP)}:{i}")
    assert offenders == []
