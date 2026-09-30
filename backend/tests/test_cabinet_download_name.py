# -*- coding: utf-8 -*-
"""Имя архива креатива в кабинете паблишера (владелец 30.09.2026):
Рекламодатель-Бренд-площадка-период-услуга[-название].ext, всё латиницей; кода сделки нет —
паблишеру его не показываем."""
from datetime import date

from app.launch_prep.download_name import _period, build_name
from app.weborama.naming import has_cyrillic


def test_format_and_latin():
    n = build_name("Берлин-Хеми", "Эспумизан", "maksavit.ru", "2026-10", "еФарм",
                   "Осень баннер", "Баннер финал.ZIP")
    assert n.startswith("Berlin-Khemi-Espumizan-maksavit.ru-") and n.endswith(".zip")
    assert "-maksavit.ru-2026-10-" in n
    assert not has_cyrillic(n) and " " not in n


def test_title_is_optional():
    n = build_name("Adv", "Brand", "site.ru", "2026-09", "Polza", None, "x.zip")
    assert n == "Adv-Brand-site.ru-2026-09-Polza.zip"


def test_period_single_and_range():
    assert _period(date(2026, 10, 1), date(2026, 10, 31)) == "2026-10"
    assert _period(date(2026, 9, 15), date(2026, 10, 15)) == "2026-09_2026-10"
    assert _period(None, None) == ""
