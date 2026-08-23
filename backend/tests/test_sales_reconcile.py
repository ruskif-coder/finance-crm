from app.sales.reconcile import (
    translit, name_tokens, score_names, build_buckets, plan_auto_link, TYPE_ID,
)


def test_typeid_mapping():
    assert TYPE_ID["agencies"] == "SUPPLIER"
    assert TYPE_ID["advertisers"] == "UC_S19G49"


def test_translit_cyrillic_to_latin():
    assert translit("Медиа") == "media"


def test_name_tokens_drops_legal_forms_and_case():
    assert name_tokens("ООО «Группа Медиа»") == {"media"}


def test_score_exact_match_is_one():
    assert score_names(["AG AGENCY"], "AG AGENCY") == 1.0


def test_score_translit_match_high():
    # «медиапул» латиницей == "mediapul"
    assert score_names(["Mediapul"], "Медиапул") >= 0.9


def test_score_no_overlap_is_zero():
    assert score_names(["Alpha"], "Bravo") == 0.0


def test_score_takes_best_variant():
    # совпадает только один из вариантов
    assert score_names(["xxx", "yyy", "zz"], "yyy") == 1.0


def test_build_buckets_splits_linked_and_candidates():
    our = [
        # мультипривязка: одна наша запись ← две компании Битрикса (50 и 51)
        {"id": 1, "name": "AG", "short_name": "AG", "name_en": "AG AGENCY", "name_ru": None,
         "bx_ids": ["50", "51"], "bx_master": "ours"},
        {"id": 2, "name": "Медиапул", "short_name": "Медиапул", "name_en": "Mediapul",
         "name_ru": None, "bx_ids": [], "bx_master": None},
        {"id": 3, "name": "Уникальная Наша", "short_name": "Уникальная Наша",
         "name_en": None, "name_ru": None, "bx_ids": [], "bx_master": None},
    ]
    bx = [
        {"id": "50", "title": "AG AGENCY"},
        {"id": "51", "title": "ОМД ОМ Групп"},
        {"id": "77", "title": "Медиапул"},
        {"id": "88", "title": "Только в Битриксе"},
    ]
    res = build_buckets(our, bx)
    assert [x["our_id"] for x in res["linked"]] == [1]
    assert {c["bx_id"] for c in res["linked"][0]["companies"]} == {"50", "51"}
    assert res["linked"][0]["our_full"] == "AG | AG AGENCY"
    cand_ids = {c["our_id"]: c["best"]["bx_id"] for c in res["candidates"]}
    assert cand_ids[2] == "77"
    assert {o["our_id"] for o in res["only_ours"]} == {3}
    assert {b["id"] for b in res["only_bitrix"]} == {"88"}
    assert {b["id"] for b in res["all_bitrix"]} == {"50", "51", "77", "88"}


def test_linked_company_not_offered_to_other_candidates():
    # Баг: привязанная компания продолжала предлагаться другим записям.
    our = [
        {"id": 1, "name": "Alpha", "short_name": "Alpha", "name_en": None, "name_ru": None,
         "bx_ids": ["10"], "bx_master": "ours"},
        {"id": 2, "name": "Alpha", "short_name": "Alpha", "name_en": None, "name_ru": None,
         "bx_ids": [], "bx_master": None},
    ]
    bx = [{"id": "10", "title": "Alpha"}, {"id": "11", "title": "Alpha Two"}]
    res = build_buckets(our, bx)
    cand2 = [c for c in res["candidates"] if c["our_id"] == 2][0]
    offered = {cand2["best"]["bx_id"]} | {a["bx_id"] for a in cand2["alternates"]}
    assert "10" not in offered            # привязанная к записи 1 — недоступна
    assert cand2["best"]["bx_id"] == "11"


def test_plan_auto_link_respects_threshold_and_dedup():
    candidates = [
        {"our_id": 1, "best": {"bx_id": "9", "score": 0.95}},
        {"our_id": 2, "best": {"bx_id": "9", "score": 0.70}},  # та же компания, ниже score
        {"our_id": 3, "best": {"bx_id": "5", "score": 0.50}},  # ниже порога
    ]
    res = plan_auto_link(candidates, threshold=0.80, taken_bx_ids=set())
    assert res["to_link"] == [{"our_id": 1, "bx_id": "9"}]
    skipped_ids = {s["our_id"] for s in res["skipped"]}
    assert skipped_ids == {2, 3}


def test_plan_auto_link_skips_already_taken_bx():
    candidates = [{"our_id": 1, "best": {"bx_id": "9", "score": 0.99}}]
    res = plan_auto_link(candidates, threshold=0.80, taken_bx_ids={"9"})
    assert res["to_link"] == []
    assert res["skipped"][0]["reason"] == "bx_id_taken"
