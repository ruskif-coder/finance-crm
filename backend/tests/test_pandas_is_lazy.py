# -*- coding: utf-8 -*-
"""`pandas` грузится при разборе Excel, а не при старте приложения.

ЗАЧЕМ. `pandas` стоит около 57 МБ, а нужен только импорту Excel (`routers/operations.py`, `ord/importer.py`).
Он был подключён на верхнем уровне, поэтому сидел в памяти процесса uvicorn всегда (замер 07.10.2026: полный
импорт приложения 176 МБ, из них pandas около 45–57). Владелец одобрил ленивый импорт 07.10.2026.

Что стережёт этот файл: (1) после `import app.main` модуля `pandas` в памяти нет; (2) разбор Excel при этом
работает — `pandas` подгружается при первом обращении.
"""
import subprocess
import sys


def _run(code: str) -> str:
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd="/app", timeout=180)
    assert r.returncode == 0, r.stderr[-600:]
    return r.stdout.strip().splitlines()[-1]


def test_starting_the_app_does_not_load_pandas():
    out = _run("import sys, app.main\nprint('pandas' in sys.modules)")
    assert out == "False", "pandas загружен при старте приложения: ~50 МБ памяти процесса зря"


def test_excel_parsing_still_works_and_loads_pandas_on_demand():
    code = (
        "import io, sys, app.main\n"
        "from openpyxl import Workbook\n"
        "from app.routers import operations as ops\n"
        "from app.ord import importer\n"
        "assert 'pandas' not in sys.modules\n"
        "assert ops._clean_inn('7712345678.0') == '7712345678'\n"          # первое обращение подгружает pandas
        "assert 'pandas' in sys.modules\n"
        "assert ops._clean_inn(float('nan')) is None\n"
        "wb = Workbook(); ws = wb.active; ws.title = 'Лист'\n"
        "ws.append(['a', 'b']); ws.append([1, 2])\n"
        "buf = io.BytesIO(); wb.save(buf)\n"
        "df = importer._sheet(buf.getvalue(), 'Лист')\n"
        "assert list(df.columns) == ['a', 'b'] and int(df.iloc[0]['a']) == 1\n"
        "assert importer._text(float('nan')) is None and importer._amount(float('nan')) is None\n"
        "print('ok')\n")
    assert _run(code) == "ok"
