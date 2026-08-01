"""СОВМЕСТИМОСТЬ: транспорт Битрикса переехал в app.sales.bitrix.transport.
Оставлено как реэкспорт, чтобы не ломать существующие импорты `from app.bitrix_api import ...`.
Новый код импортировать из пакета app.sales.bitrix.
"""
from app.sales.bitrix.transport import (  # noqa: F401
    VIBECODE_BASE,
    vibecode_get,
    vibecode_patch,
    list_bitrix_companies,
    list_bitrix_users,
    list_deal_ids_for_company,
    all_deal_company_ids,
    _get_paged_with_retry,
)
