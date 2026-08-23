from app.sales.bitrix.deal_import import parse_money, parse_bx_date, map_deal, select_new_deals


def test_parse_money_pipe():
    assert parse_money("1500000|RUB") == (1500000.0, "RUB")


def test_parse_money_empty():
    assert parse_money(None) == (None, "RUB")
    assert parse_money("") == (None, "RUB")


def test_parse_money_plain_number():
    assert parse_money("500") == (500.0, "RUB")


def test_parse_bx_date():
    import datetime
    assert parse_bx_date("2026-09-01T03:00:00+03:00") == datetime.date(2026, 9, 1)
    assert parse_bx_date(None) is None
    assert parse_bx_date("нет") is None


PIPELINES = {0: "Общая", 8: "Pharm"}
STAGES = {(8, "C8:WON"): "Архив"}
AGENCY_LINKS = {"1796": 13}
PRODUCTS = {"2": "еФарм", "10": "Клик-аут"}   # карта СП 1050


def test_map_deal_tracked_pipeline():
    raw = {
        "id": 6760, "title": "Бренд_Клиент_g4m", "categoryId": 8, "stageId": "C8:WON",
        "companyId": 1796, "ufCrm_1690138678699": "1500000|RUB",
        "ufCrm_1723639172": "2026-09-01T03:00:00+03:00",
        "ufCrm_64BD76BC5BC45": "Бренд",   # это БРЕНД — в услугу попасть НЕ должен
        "parentId1050": 2,                    # «Продукты Simb-ad» = еФарм
    }
    d = map_deal(raw, PIPELINES, STAGES, AGENCY_LINKS, PRODUCTS)
    assert d["bitrix_id"] == "6760"
    assert d["pipeline"] == "Pharm"
    assert d["bitrix_stage"] == "Архив"        # код резолвится в имя
    assert d["amount"] == 1500000.0
    assert d["agency_id"] == 13                 # companyId → наш id через links
    assert d["product"] == "еФарм"              # услуга из parentId1050, НЕ бренд из заголовка
    assert d["period_from"].isoformat() == "2026-09-01"


def test_map_deal_no_product_is_none():
    raw = {"id": 1, "title": "x", "categoryId": 0, "stageId": "C8:WON", "parentId1050": 0}
    assert map_deal(raw, PIPELINES, STAGES, AGENCY_LINKS, PRODUCTS)["product"] is None


def test_map_deal_untracked_pipeline_is_skipped():
    raw = {"id": 6808, "title": "Премия", "categoryId": 16, "stageId": "C16:PREPARATION"}
    assert map_deal(raw, PIPELINES, STAGES, AGENCY_LINKS, PRODUCTS) is None


def test_map_deal_unknown_stage_keeps_code():
    raw = {"id": 1, "title": "x", "categoryId": 0, "stageId": "UC_ZZZ", "companyId": "999"}
    d = map_deal(raw, PIPELINES, STAGES, AGENCY_LINKS, PRODUCTS)
    assert d["bitrix_stage"] == "UC_ZZZ"        # нет в карте → оставляем код
    assert d["agency_id"] is None               # компания не привязана


# ── select_new_deals: отсев дублей / надгробий / неотслеживаемых воронок ──

def _raw(deal_id, cat=0, stage="C8:WON"):
    return {"id": deal_id, "title": f"D{deal_id}", "categoryId": cat, "stageId": stage,
            "companyId": 1796, "ufCrm_1690138678699": "1000000|RUB", "parentId1050": 2}


def test_select_maps_good_deal():
    mapped, c = select_new_deals([_raw(102)], set(), set(),
                                 PIPELINES, STAGES, AGENCY_LINKS, PRODUCTS)
    assert [d["bitrix_id"] for d in mapped] == ["102"]
    assert c == {"skipped_untracked": 0, "skipped_existing": 0, "skipped_tombstoned": 0}


def test_select_skips_existing():
    mapped, c = select_new_deals([_raw(100)], {"100"}, set(),
                                 PIPELINES, STAGES, AGENCY_LINKS, PRODUCTS)
    assert mapped == [] and c["skipped_existing"] == 1


def test_select_skips_tombstoned():
    # удалённая вручную сделка НЕ воскресает, даже если валидна и её нет у нас
    mapped, c = select_new_deals([_raw(100)], set(), {"100"},
                                 PIPELINES, STAGES, AGENCY_LINKS, PRODUCTS)
    assert mapped == [] and c["skipped_tombstoned"] == 1


def test_select_skips_untracked_pipeline():
    mapped, c = select_new_deals([_raw(101, cat=16)], set(), set(),
                                 PIPELINES, STAGES, AGENCY_LINKS, PRODUCTS)
    assert mapped == [] and c["skipped_untracked"] == 1


def test_select_existing_takes_precedence_over_tombstone():
    mapped, c = select_new_deals([_raw(100)], {"100"}, {"100"},
                                 PIPELINES, STAGES, AGENCY_LINKS, PRODUCTS)
    assert c["skipped_existing"] == 1 and c["skipped_tombstoned"] == 0


def test_every_deal_creation_path_assigns_a_code():
    """Сделка не может появиться без метки — по какому бы пути её ни создали.

    Метка (SalesDeal.code) стоит в интерфейсе и в ссылках вместо bitrix_id, и
    путей создания три: ручное из дашборда, генератор годового плана и импорт из
    Битрикса. Импорт про метку не знал, поэтому каждая приехавшая из Битрикса
    сделка получалась с пустым кодом — в реестре на её месте прочерк. Проверка
    статическая нарочно: она ловит именно забытый путь, а не поведение одного из них.
    """
    import pathlib
    import re

    app_dir = pathlib.Path(__file__).resolve().parent.parent / "app"
    offenders = []
    for path in app_dir.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        # Конструирование новой сделки, а не объявление класса и не аннотация типа.
        if not re.search(r"(?<!class )\bSalesDeal\(", src):
            continue
        if "assign_code" not in src:
            offenders.append(path.name)
    assert offenders == [], f"создают сделку без метки: {offenders}"
