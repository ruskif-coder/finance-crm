# -*- coding: utf-8 -*-
"""Наше название сделки площадке не уходит (аудит 23.09.2026, 5.L10).

Название сделки — внутренняя единица: в нём бывает всё, от рабочих пометок до имени
клиента-посредника. Площадке уходят бренд и период. Утечка шла двумя путями: подстановка
`{сделка}` в письме-запросе ссылки брала `deal.title`, и «бренд» без бренда откатывался
к тому же `deal.title` — а этой функцией собирается контекст ВСЕХ писем площадке.
"""
import io
from pathlib import Path
from types import SimpleNamespace

from app.routers import launch_prep as lp

TITLE = "ВНУТР · Клиент через посредника · не показывать"


class _Db:
    def __init__(self, brand=None, adv=("Рекламодатель", None)):
        self.brand, self.adv = brand, adv

    def query(self, *cols):
        brand, adv = self.brand, self.adv
        name = str(cols[0])

        def first():
            if "Brand" in name:
                return (brand,) if brand else None
            return adv
        return SimpleNamespace(filter=lambda *a: SimpleNamespace(first=first))


def _deal(**kw):
    base = dict(title=TITLE, brand_id=None, advertiser_id=5,
                period_from=None, period_to=None)
    return SimpleNamespace(**{**base, **kw})


def test_brand_fallback_never_returns_our_deal_title():
    got = lp._deal_brand_name(_Db(), _deal())
    assert TITLE not in got
    assert got == "Рекламодатель"


def test_url_request_values_carry_no_deal_title():
    vals = lp._url_request_values(_Db(brand="Бренд"), _deal(brand_id=1),
                                  SimpleNamespace(name="Сайт", domain="site.test"),
                                  SimpleNamespace(full_name="Трафик", email=None), "текст")
    assert not any(TITLE in str(v) for v in vals.values()), vals


def test_fallback_subject_does_not_name_the_deal():
    src = io.open(Path(lp.__file__), encoding="utf-8").read()
    assert "values['сделка']" not in src
