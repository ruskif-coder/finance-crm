# -*- coding: utf-8 -*-
"""Бэклог отладки: ссылка-источник не принимает чужую схему (аудит 23.09.2026, 9.8 / 6.M10).

`source_link` сохранялся как есть и рисуется кликабельным: `javascript:` в нём исполнился
бы у того, кто открыл запись. Правило то же, что у ссылок площадок (`links.safe_url`).
"""
import pytest
from pydantic import ValidationError

from app.routers.backlog import BacklogIn, BacklogUpdate


@pytest.mark.parametrize("model", [BacklogIn, BacklogUpdate])
def test_foreign_scheme_is_refused(model):
    base = {} if model is BacklogUpdate else {"title": "т", "signal_bad": "с",
                                               "watch_until": "2026-12-31"}
    with pytest.raises(ValidationError):
        model(**base, source_link="javascript:alert(1)")
    assert model(**base, source_link="https://x.example/a").source_link == "https://x.example/a"
    assert model(**base, source_link="операции, фильтр по банку").source_link


@pytest.mark.parametrize("sneaky", ["\x01javascript:alert(1)", "java\tscript:alert(1)",
                                    "java\nscript:alert(1)", " \x00 javascript:alert(1)"])
def test_control_characters_do_not_hide_a_scheme(sneaky):
    """Браузер выбрасывает ведущие управляющие символы и табы/переводы строк внутри
    адреса — `java\tscript:` становится `javascript:` (ревью 24.09.2026)."""
    from app.links import safe_url
    with pytest.raises(ValueError):
        safe_url(sneaky)
