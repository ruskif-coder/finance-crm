"""
Тесты правил синхронизации.

Две вещи, которые ломаются молча и потому покрыты тестом:
1) append-only слой сырья не должен плодить версии при неизменных данных;
2) сопоставление без нечёткого матчинга — 0 или >1 кандидатов означает
   ручную очередь, а не догадку.
"""
from app.sales.sync import (should_store_version, plan_counterparty_match,
                            plan_directory_match, should_import_deal,
                            diff_bitrix_pipelines)


def test_deleted_deal_is_not_reimported():
    tomb = {"6668", "6660"}
    assert should_import_deal("6668", tomb) is False
    assert should_import_deal(6660, tomb) is False   # число тоже
    assert should_import_deal("9999", tomb) is True


def test_no_tombstones_imports_everything():
    assert should_import_deal("123", set()) is True
    assert should_import_deal("123", None) is True


def test_first_version_is_always_stored():
    assert should_store_version(None, "abc") is True


def test_unchanged_payload_is_not_stored_again():
    assert should_store_version("abc", "abc") is False


def test_changed_payload_is_stored():
    assert should_store_version("abc", "def") is True


def test_exactly_one_candidate_is_matched():
    assert plan_counterparty_match("7707083893", [101]) == (101, "matched")


def test_no_candidates_goes_to_queue():
    assert plan_counterparty_match("7707083893", []) == (None, "not_found")


def test_several_candidates_go_to_queue_without_guessing():
    assert plan_counterparty_match("7707083893", [101, 102]) == (None, "ambiguous")


def test_missing_inn_goes_to_queue():
    assert plan_counterparty_match(None, [101]) == (None, "no_inn")


def test_directory_value_matched_by_normalized_name():
    index = {"in-app": 7}
    assert plan_directory_match("IN-APP", index) == (7, "matched")


def test_directory_spelling_variants_collapse_to_one_entry():
    # В исходных данных услуга пишется четырьмя способами
    index = {"in app": 7}
    assert plan_directory_match("in  app", index) == (7, "matched")
    assert plan_directory_match("  In App ", index) == (7, "matched")


def test_unknown_directory_value_is_not_created_silently():
    assert plan_directory_match("новая услуга", {"web": 1}) == (None, "not_found")


def test_empty_directory_value_goes_to_queue():
    assert plan_directory_match("", {"web": 1}) == (None, "not_found")
    assert plan_directory_match(None, {"web": 1}) == (None, "not_found")


# ---- Сверка воронок/стадий с Битриксом (актуальность справочника) ----

def _pipe(cid, name, stages):
    return {"bitrix_category_id": cid, "name": name,
            "stages": [{"status_id": s, "name": n} for s, n in stages]}


def test_identical_pipelines_report_no_changes():
    stored = [_pipe(1, "Общая", [("C1:NEW", "Медиаплан"), ("C1:WON", "Закрытие")])]
    r = diff_bitrix_pipelines(stored, stored)
    assert r["has_changes"] is False
    assert r["new_pipelines"] == [] and r["missing_pipelines"] == []


def test_new_pipeline_and_its_stages_detected():
    stored = [_pipe(1, "Общая", [("C1:NEW", "Медиаплан")])]
    fetched = stored + [_pipe(2, "ДО", [("C2:NEW", "Сбор запуска")])]
    r = diff_bitrix_pipelines(stored, fetched)
    assert r["new_pipelines"] == [{"bitrix_category_id": 2, "name": "ДО"}]
    assert {"pipeline": "ДО", "status_id": "C2:NEW", "name": "Сбор запуска"} in r["new_stages"]
    assert r["has_changes"] is True


def test_renamed_pipeline_matched_by_category_id():
    stored = [_pipe(1, "Общая", [("C1:NEW", "Медиаплан")])]
    fetched = [_pipe(1, "Общая воронка", [("C1:NEW", "Медиаплан")])]
    r = diff_bitrix_pipelines(stored, fetched)
    assert r["renamed_pipelines"] == [{"bitrix_category_id": 1,
                                       "from": "Общая", "to": "Общая воронка"}]


def test_renamed_stage_is_flagged_because_it_breaks_the_map():
    # Карта светофора ключуется по имени стадии — переименование её отвязывает.
    stored = [_pipe(1, "Общая", [("C1:WON", "Закрытие")])]
    fetched = [_pipe(1, "Общая", [("C1:WON", "Закрытие | Мария")])]
    r = diff_bitrix_pipelines(stored, fetched)
    assert r["renamed_stages"] == [{"pipeline": "Общая", "status_id": "C1:WON",
                                    "from": "Закрытие", "to": "Закрытие | Мария"}]


def test_missing_pipeline_and_stage_detected():
    stored = [_pipe(1, "Общая", [("C1:NEW", "Медиаплан"), ("C1:OLD", "Старая стадия")]),
              _pipe(9, "Удалённая", [("C9:X", "Что-то")])]
    fetched = [_pipe(1, "Общая", [("C1:NEW", "Медиаплан")])]
    r = diff_bitrix_pipelines(stored, fetched)
    assert {"bitrix_category_id": 9, "name": "Удалённая"} in r["missing_pipelines"]
    assert {"pipeline": "Общая", "status_id": "C1:OLD",
            "name": "Старая стадия"} in r["missing_stages"]
