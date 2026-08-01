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


def diff_bitrix_pipelines(stored: list, fetched: list) -> dict:
    """Сверяет воронки и их стадии в Битриксе с нашим справочником.

    Обе стороны — простые списки словарей (без БД, чтобы правило тестировалось
    отдельно от инфраструктуры):
        {"bitrix_category_id": int, "name": str,
         "stages": [{"status_id": str, "name": str}, ...]}

    Воронки сопоставляются по bitrix_category_id (в портале переименовывают,
    id стабилен), стадии — по status_id внутри воронки.

    Возвращает отчёт об изменениях. Само по себе правило НИЧЕГО не применяет и
    не решает про is_tracked: новые воронки вызывающий код обязан заводить
    ВЫКЛЮЧЕННЫМИ (парсинг включает человек). Переименование стадии особенно важно
    — карта светофора ключуется по имени стадии, и переименование в Битриксе
    молча отвязывает стадию от слоя денег; такие случаи и есть повод для
    уведомления «нужно внимание»."""
    def stages_of(p):
        return {str(s["status_id"]): s for s in (p.get("stages") or [])}

    stored_by_cat = {p["bitrix_category_id"]: p for p in stored
                     if p.get("bitrix_category_id") is not None}
    fetched_by_cat = {p["bitrix_category_id"]: p for p in fetched
                      if p.get("bitrix_category_id") is not None}

    report = {"new_pipelines": [], "renamed_pipelines": [], "missing_pipelines": [],
              "new_stages": [], "renamed_stages": [], "missing_stages": []}

    for cid, fp in fetched_by_cat.items():
        sp = stored_by_cat.get(cid)
        if sp is None:
            report["new_pipelines"].append({"bitrix_category_id": cid, "name": fp["name"]})
            for st in (fp.get("stages") or []):
                report["new_stages"].append({"pipeline": fp["name"],
                                             "status_id": str(st["status_id"]),
                                             "name": st["name"]})
            continue
        if sp["name"] != fp["name"]:
            report["renamed_pipelines"].append({"bitrix_category_id": cid,
                                                "from": sp["name"], "to": fp["name"]})
        s_stages, f_stages = stages_of(sp), stages_of(fp)
        for sid, fst in f_stages.items():
            sst = s_stages.get(sid)
            if sst is None:
                report["new_stages"].append({"pipeline": fp["name"], "status_id": sid,
                                             "name": fst["name"]})
            elif sst["name"] != fst["name"]:
                report["renamed_stages"].append({"pipeline": fp["name"], "status_id": sid,
                                                 "from": sst["name"], "to": fst["name"]})
        for sid, sst in s_stages.items():
            if sid not in f_stages:
                report["missing_stages"].append({"pipeline": sp["name"], "status_id": sid,
                                                 "name": sst["name"]})

    for cid, sp in stored_by_cat.items():
        if cid not in fetched_by_cat:
            report["missing_pipelines"].append({"bitrix_category_id": cid, "name": sp["name"]})

    report["has_changes"] = any(report[k] for k in report)
    return report


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
