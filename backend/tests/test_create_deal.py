import datetime
from app.routers.sales_dashboard import (
    _period_bounds, _pick_scope_section, _brand_orphaned, _deal_owned,
)


def test_period_bounds_regular_month():
    assert _period_bounds("2026-02") == (datetime.date(2026, 2, 1), datetime.date(2026, 2, 28))


def test_period_bounds_december():
    assert _period_bounds("2026-12") == (datetime.date(2026, 12, 1), datetime.date(2026, 12, 31))


def test_period_bounds_leap_february():
    assert _period_bounds("2028-02") == (datetime.date(2028, 2, 1), datetime.date(2028, 2, 29))


def test_period_bounds_bad():
    assert _period_bounds("2026") is None
    assert _period_bounds("") is None
    assert _period_bounds("2026-13") is None


# ── #3: безопасный резолв секции own-scope (защита от подстановки чужой секции) ──

def test_pick_scope_uses_requested_when_viewable():
    # запрошенную секцию применяем только если она реально доступна пользователю
    assert _pick_scope_section("sales_analytics",
                               {"sales_analytics": "all", "sales_registry": "own"}) == "sales_analytics"


def test_pick_scope_rejects_unviewable_section():
    # секция, которой у пользователя нет, НЕ должна расширять видимость →
    # берём самую строгую из доступных (own приоритетнее all)
    assert _pick_scope_section("sales_analytics", {"sales_registry": "own"}) == "sales_registry"


def test_pick_scope_prefers_own_over_all():
    assert _pick_scope_section("нет_такой",
                               {"sales_analytics": "all", "sales_registry": "own"}) == "sales_registry"


def test_pick_scope_empty_defaults_registry():
    assert _pick_scope_section("sales_analytics", {}) == "sales_registry"


# ── #7: сброс осиротевшего бренда при смене рекламодателя ──

def test_brand_orphaned_true_when_advertiser_changes():
    assert _brand_orphaned(5, 7) is True
    assert _brand_orphaned(5, None) is True   # сняли рекламодателя — бренд осиротел


def test_brand_orphaned_false_when_same_or_no_brand():
    assert _brand_orphaned(5, 5) is False
    assert _brand_orphaned(None, 7) is False   # бренда нет — нечего сбрасывать


# ── #6: own-scope на мутациях — предикат владения сделкой ──

def test_deal_owned_by_sales_rep():
    assert _deal_owned(10, None, {10, 11}) is True


def test_deal_owned_by_account_manager():
    assert _deal_owned(None, 11, {10, 11}) is True


def test_deal_not_owned():
    assert _deal_owned(99, 98, {10, 11}) is False
    assert _deal_owned(None, None, {10, 11}) is False
    assert _deal_owned(10, None, set()) is False   # нет привязки — ничего не своё
