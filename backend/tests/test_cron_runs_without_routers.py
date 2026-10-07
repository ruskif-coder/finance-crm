# -*- coding: utf-8 -*-
"""Кроны во время работы не подтягивают роутеры (слой HTTP) — иначе процесс раздувается.

ЗАЧЕМ. Процесс крона — отдельный python с моделями (около 65 МБ). Но `notify.scanner` во время работы лениво
подтягивал 7 роутеров (`reports`, `year_plan`, `traffic_dashboard` → `traffic` → `launch_prep` →
`sales_dashboard`) и вырастал до 101 МБ (замер 07.10.2026), хотя роутерам там делать нечего: нужны были 8 мелких
функций (сроки оплаты, плановые месяцы, три выборки статистики). В начале часа крон соседствует с другими
процессами в одном контейнере, и именно такие процессы однажды вместе выбили его по памяти.

Прибор прогоняет крон в режиме `--dry-run` (в нём ничего не отправляется и не пишется) и смотрит, какие роутеры
оказались в памяти. Допустим только `auth`: его тянут `permissions` и `audit` на верхнем уровне, это лёгкий модуль.
Новый крон или новая зависимость крона от роутера роняет этот тест — функцию надо вынести в сервисный модуль.
"""
import json
import subprocess
import sys

import pytest

CRONS = ["app.notify.scanner", "app.notify.digest", "app.notify.dispatch", "app.notify.lifecycle",
         "app.notify.outward.digest", "app.mail.flush"]
ALLOWED = {"auth"}

CODE = ("import sys, runpy, json\nsys.argv = [sys.argv[1], '--dry-run']\n"
        "try:\n    runpy.run_module(sys.argv[0], run_name='__main__')\nexcept SystemExit:\n    pass\n"
        "print('ROUTERS', json.dumps(sorted(m.split('.')[-1] for m in sys.modules if m.startswith('app.routers.'))))\n")


@pytest.mark.parametrize("module", CRONS)
def test_cron_does_not_pull_routers_while_it_works(module):
    r = subprocess.run([sys.executable, "-c", CODE, module], capture_output=True, text=True, cwd="/app", timeout=240)
    line = [x for x in r.stdout.splitlines() if x.startswith("ROUTERS")]
    assert line, f"{module}: прогон не дошёл до конца\n{r.stderr[-600:]}"
    loaded = set(json.loads(line[0].split(" ", 1)[1])) - ALLOWED
    assert not loaded, f"{module} подтянул роутеры {sorted(loaded)}: вынесите нужные функции в сервисный модуль"
