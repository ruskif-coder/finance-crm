# -*- coding: utf-8 -*-
"""«Прямой рекламодатель»: изначальный договор = доходный (владелец 02.10.2026).
Главное — отсутствие изначального договора не запирает стадию."""
import inspect
from types import SimpleNamespace

import app.main  # noqa: F401
from app.sales import stage_checks as sc


def _ctx(**deal):
    d = dict(is_self_promo=False, ord_initial_contract_id=None, ord_direct_advertiser=False)
    d.update(deal)
    return SimpleNamespace(deal=SimpleNamespace(**d))


def test_direct_advertiser_does_not_lock_the_stage():
    fn = sc._ord_initial_contract
    locked = fn(_ctx())
    free = fn(_ctx(ord_direct_advertiser=True))
    assert locked != free
    assert "прям" in str(free).lower()


def test_model_and_label_and_assembly_know_the_flag():
    from app.sales.models import SalesDeal
    from app.dsp import provision
    from app.routers import ord as ordr
    assert hasattr(SalesDeal, "ord_direct_advertiser")
    assert "ord_direct_advertiser" in inspect.getsource(provision.ad_label)
    assert "ord_direct_advertiser" in inspect.getsource(ordr)
    assert "/deal/{deal_id}/direct-advertiser" in inspect.getsource(ordr)


def test_prolongation_keeps_the_flag_and_label_uses_resolved_payer():
    from app.routers import launch_prep
    from app.dsp import provision
    from app.sales import stage_scope
    assert "ord_direct_advertiser=src.ord_direct_advertiser" in inspect.getsource(launch_prep)
    assert "resolve_final(" in inspect.getsource(provision.ad_label), \
        "метка — тем же плательщиком, что сборка ОРД (по метке имени тоже)"
    assert "ord_direct_advertiser" in inspect.getsource(stage_scope)
