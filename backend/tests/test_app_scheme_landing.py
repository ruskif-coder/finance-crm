# -*- coding: utf-8 -*-
"""Посадочная приложения площадки своей схемой — `storefront://product_selection/4846`
у kuper (владелец 06.10.2026: «ссылки должны приниматься и в таком варианте»).

Принимается только для app-поверхности. Наружу, где нужен веб-адрес (DSP link/adomain,
ОРД), такая ссылка не уходит: `web_url` даёт None. Опасные схемы — отказ всегда.
"""
import pytest

from app.launch_prep import pub_rules as R

KUPER = "storefront://product_selection/4846"


def test_app_scheme_accepted_in_app_field():
    """С 06.10.2026 ссылка в приложении — своё поле; веб-поле — только http(s)."""
    assert R.validate_app_link(KUPER) == KUPER
    assert R.validate_app_link("ozerki://catalog/1") == "ozerki://catalog/1"
    with pytest.raises(ValueError):
        R.validate_landing(KUPER, "app")


def test_app_scheme_refused_for_web():
    with pytest.raises(ValueError):
        R.validate_landing(KUPER, "web")


@pytest.mark.parametrize("bad", ["javascript://alert(1)", "data://text/html,x", "file:///etc/passwd",
                                 "vbscript://x", "storefront://", "storefront:// пробел"])
def test_dangerous_or_empty_schemes_refused(bad):
    with pytest.raises(ValueError):
        R.validate_app_link(bad)


def test_app_scheme_is_not_a_web_address():
    assert R.web_url(KUPER) is None
    assert R.web_url("https://web.kuper.ru/x") == "https://web.kuper.ru/x"


def test_http_still_works():
    assert R.validate_landing("https://site.ru/a", "web") == "https://site.ru/a"
