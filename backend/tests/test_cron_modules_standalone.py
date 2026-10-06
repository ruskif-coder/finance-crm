# -*- coding: utf-8 -*-
"""Каждый крон запускается ОТДЕЛЬНЫМ процессом (`python -m ...`), а не внутри приложения.

06.10.2026: дайджест площадкам (`app.notify.outward.digest`) неделю падал на каждом
запуске — `mail_log.publisher_id` ссылается на `sales_publishers`, а при отдельном запуске
модель площадок никто не импортировал. В приложении и в pytest её подтягивает `app.main`,
поэтому тесты были зелёными, а письма площадкам не уходили с 02.10.

Прибор повторяет условия сервера: новый процесс, импорт только модуля крона, затем
разрешение всех внешних ключей метаданных — ровно то, на чём падала запись в журнал писем.
Список — строки crontab из docs/CRON_после_релиза.md.
"""
import subprocess
import sys

import pytest

CRON_MODULES = [
    "app.notify.outward.digest",
    "app.notify.digest",
    "app.notify.dispatch",
    "app.notify.scanner",
    "app.notify.lifecycle",
    "app.mail.flush",
    "app.weborama.daily",
    "app.ad.daily_shares",
    "app.launch_prep.erid_auto",
    "app.dsp.stat_daily",
]

PROBE = (
    "import importlib, sys\n"
    "importlib.import_module(sys.argv[1])\n"
    "from app.database import Base\n"
    "bad = []\n"
    "for t in Base.metadata.tables.values():\n"
    "    for fk in t.foreign_keys:\n"
    "        try:\n"
    "            fk.column\n"
    "        except Exception as e:\n"
    "            bad.append(f'{t.name}.{fk.parent.name}: {type(e).__name__}')\n"
    "print('\\n'.join(bad))\n"
    "sys.exit(1 if bad else 0)\n"
)


@pytest.mark.parametrize("module", CRON_MODULES)
def test_cron_module_resolves_all_foreign_keys_on_its_own(module):
    r = subprocess.run([sys.executable, "-c", PROBE, module], cwd="/app",
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"{module}: не находятся таблицы по ссылкам —\n{r.stdout}{r.stderr[-800:]}"
