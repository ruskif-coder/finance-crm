"""Линтер как тест.

Отдельной команды `lint` в проекте нет и заводить её некуда: CI отсутствует, а
единственное, что запускается перед выкладкой руками, — pytest. Поэтому статический
анализ живёт здесь: `docker exec finance_backend pytest` остаётся одной командой,
которая проверяет всё.

Набор правил и причины, по которым он такой узкий, — в backend/ruff.toml.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent          # /app
TARGETS = ["app", "tests", "scripts"]


@pytest.mark.skipif(shutil.which("ruff") is None,
                    reason="ruff не установлен (см. requirements.txt)")
def test_ruff_is_clean():
    res = subprocess.run(
        ["ruff", "check", "--output-format", "concise", *TARGETS],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert res.returncode == 0, "\n" + (res.stdout or res.stderr)
