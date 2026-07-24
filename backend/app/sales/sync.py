"""
Правила синхронизации с Битрикс24.

Слой сырья append-only: версия пишется, только если изменился хеш полезной
нагрузки. Это не микрооптимизация — суммы в сделке правятся на фактические
в момент закрытия, и без истории версий план-факт с прогнозом невозможен:
сравнивать будет не с чем.

Сопоставление — без нечёткого матчинга. Ноль кандидатов или больше одного
означает строку в sales_match_queue, а не догадку. Та же философия, что
в scripts/link_contracts_to_counterparties.py.

Здесь только чистые правила, без обращений к БД и сети: они тестируются
без инфраструктуры, как остальные модули app/sales.
"""

# Причины, по которым сущность уходит в очередь ручного сопоставления.
# Различаются намеренно: «не найдено» и «несколько кандидатов» требуют
# разных действий оператора.
MATCH_MATCHED = "matched"
MATCH_NO_INN = "no_inn"
MATCH_NOT_FOUND = "not_found"
MATCH_AMBIGUOUS = "ambiguous"


def should_import_deal(bitrix_id, tombstoned_ids) -> bool:
    """False, если сделка удалена вручную (её bitrix_id в надгробиях).

    Синхронизация ОБЯЗАНА вызывать это перед созданием/обновлением сделки:
    иначе удалённые из реестра сделки воскреснут, т.к. в Битриксе они живы.
    tombstoned_ids — множество bitrix_id из sales_deleted_deals."""
    return str(bitrix_id) not in {str(x) for x in (tombstoned_ids or ())}


def should_store_version(latest_hash: str | None, new_hash: str) -> bool:
    """True, если полезную нагрузку нужно записать новой версией в sales_bitrix_raw.

    Первая встреча сущности (latest_hash is None) записывается всегда."""
    return latest_hash != new_hash


def plan_counterparty_match(inn, candidate_ids) -> tuple:
    """Решает, привязывать ли контрагента к сделке.

    Возвращает (id или None, причина). Причина попадает в sales_match_queue
    и показывается оператору."""
    if not inn:
        return None, MATCH_NO_INN
    candidates = list(candidate_ids or [])
    if len(candidates) == 1:
        return candidates[0], MATCH_MATCHED
    if not candidates:
        return None, MATCH_NOT_FOUND
    return None, MATCH_AMBIGUOUS


def plan_directory_match(raw_value, normalized_index: dict) -> tuple:
    """То же для справочных значений (услуга, бренд, рекламодатель).

    normalized_index — {нормализованное имя: id}. Значения, отличающиеся только
    регистром и пробелами, схлопываются в одну запись: в исходных данных одна
    и та же услуга встречается как "web", "in-app", "inapp", "in app".

    Отсутствующее значение НЕ создаётся молча — иначе справочник за месяц
    обрастёт дублями с разными пробелами."""
    from app.sales.normalize import normalize_name

    key = normalize_name(raw_value)
    if not key:
        return None, MATCH_NOT_FOUND
    found = normalized_index.get(key)
    if found is None:
        return None, MATCH_NOT_FOUND
    return found, MATCH_MATCHED
