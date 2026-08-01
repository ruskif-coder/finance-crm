"""СОВМЕСТИМОСТЬ: модуль переехал в app.sales.bitrix.deal_import.
Реэкспорт, чтобы не ломать старые импорты. Новый код — из пакета app.sales.bitrix.
"""
from app.sales.bitrix.deal_import import (  # noqa: F401
    import_new_deals, map_deal, parse_money, parse_bx_date, reference_maps, max_bitrix_id,
    product_map, AMOUNT_FIELD, PERIOD_FROM_FIELD, PERIOD_TO_FIELD, BRAND_FIELD,
)
