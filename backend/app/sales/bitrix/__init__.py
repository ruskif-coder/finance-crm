"""
================================================================================
  МОДУЛЬ ИНТЕГРАЦИИ С БИТРИКС24  (app.sales.bitrix)
================================================================================
ПРАВИЛО ПРОЕКТА: любое взаимодействие с Битриксом складывается СЮДА. Новый
коннектор/правило/маппинг — файл в этом пакете, а не разрозненно по проекту.

Ниже — МАНИФЕСТ реализованного функционала (обновлять при добавлении!), чтобы
перед деплоем в прод прицельно гонять нужные тесты. Транспорт READWRITE — часть
операций ПИШЕТ в живой Битрикс, поэтому тесты обязательны.

--------------------------------------------------------------------------------
РЕАЛИЗОВАНО (на 2026-07-28)
--------------------------------------------------------------------------------
1. ТРАНСПОРТ  → transport.py                              [tests: test_bitrix_api.py]
   - vibecode_get / vibecode_patch (httpx, ключ из env|/app/vibecode.key)
   - _get_paged_with_retry (пагинация 500 + ретрай; hasMore у БХ всегда True → стоп по total)
   - list_bitrix_companies(typeId)  [ЧТЕНИЕ]
   - list_bitrix_users(active_only) [ЧТЕНИЕ]
   - list_deal_ids_for_company / all_deal_company_ids [ЧТЕНИЕ]
   - list_bitrix_pipelines() /deal-categories (+кат.0) / list_bitrix_stages(cat) /statuses [ЧТЕНИЕ]
   - list_bitrix_services() смарт-процесс 1050 «Продукты Simb-ad» [ЧТЕНИЕ]

2. ИМПОРТ СДЕЛОК  → deal_import.py                        [tests: test_deal_import.py]
   - parse_money / parse_bx_date / map_deal (чистые правила; None = неотслеж. воронка)
   - reference_maps / max_bitrix_id
   - import_new_deals(db, commit)  [ЧТЕНИЕ БХ + ЗАПИСЬ В НАШУ БД]
     инкремент по id>max, только отслеживаемые воронки (sales_pipelines), дедуп по bitrix_id.

3. СВЕРКА СПРАВОЧНИКОВ (матчинг, чистая логика) → app/sales/reconcile.py
                                                         [tests: test_sales_reconcile.py]
   - translit / name_tokens / score_names / build_buckets / plan_auto_link / standard_name

4. ЭНДПОЙНТЫ КОННЕКТОРА → app/routers/sales_reconcile.py  [tests: test_reconcile_http.py]
   - GET /{kind}, /{kind}/deal-counts                       [ЧТЕНИЕ]
   - POST /{kind}/link|unlink|import|flag-create|set-master|auto-link  [ЗАПИСЬ В НАШУ БД]
   - POST /{kind}/consolidate/preview                       [ЧТЕНИЕ]
   - POST /{kind}/consolidate  *** ПИШЕТ В ПРОД-БИТРИКС ***  (переброс сделок + переименование)
   - POST /import-deals                                     [ЧТЕНИЕ БХ + ЗАПИСЬ В НАШУ БД]

5. ПРАВИЛА СИНХРОНА (чистые) → app/sales/sync.py           [tests: test_sales_sync.py]
   - should_import_deal (надгробия) / should_store_version / plan_counterparty_match
   - diff_bitrix_pipelines (сверка воронок/стадий) / plan_directory_match

6. ПРИВЯЗКА ЮЗЕРОВ → app/routers/users.py  (GET /users/bitrix-directory; User.bitrix_user_id)

7. СИНХРОН СПРАВОЧНИКОВ ВОРОНОК/УСЛУГ → app/routers/sales_directories.py
   - POST /pipelines/refresh  (воронки+стадии из Битрикса; новые воронки is_tracked=False) [ЗАПИСЬ В НАШУ БД]
   - POST /services/refresh   (услуги из СП 1050; добавляет новые по имени)                [ЗАПИСЬ В НАШУ БД]
   - PUT  /services/{id}/use  (галочка «использовать» = is_active)

ЛЕГАСИ (НЕ использовать): app/sales/bitrix_client.py — классический вебхук, заменён VibeCode.

--------------------------------------------------------------------------------
ПРОГОН ТЕСТОВ ПЕРЕД ПРОДОМ:
  docker exec finance_backend python -m pytest \\
    tests/test_bitrix_api.py tests/test_deal_import.py \\
    tests/test_sales_reconcile.py tests/test_reconcile_http.py tests/test_sales_sync.py -v
--------------------------------------------------------------------------------
"""
from app.sales.bitrix.transport import (  # noqa: F401
    vibecode_get, vibecode_patch, vibecode_post,
    list_bitrix_companies, list_bitrix_users,
    list_deal_ids_for_company, all_deal_company_ids,
    list_bitrix_pipelines, list_bitrix_stages, list_bitrix_services,
)
from app.sales.bitrix.deal_import import (  # noqa: F401
    import_new_deals, map_deal, parse_money, parse_bx_date, reference_maps, max_bitrix_id,
)

__all__ = [
    "vibecode_get", "vibecode_patch", "list_bitrix_companies", "list_bitrix_users",
    "list_deal_ids_for_company", "all_deal_company_ids",
    "import_new_deals", "map_deal", "parse_money", "parse_bx_date",
    "reference_maps", "max_bitrix_id",
]
