"""Импорт сделок из Битрикса в наш реестр — правила маппинга + оркестровка.

Принципы:
- Якорь инкремента: `id > нашего максимума bitrix_id` (id Битрикса монотонен по дате
  создания; `createdTime` в списочном ответе не приходит — не полагаемся на него).
- Берём ТОЛЬКО сделки из отслеживаемых воронок (есть в sales_pipelines). Остальное
  (напр. cat16 «Премии», cat24) — пропускаем, не плодим мусор.
- Дедуп по bitrix_id (у нас UNIQUE). Рекламодатель/продавец не мапим (нет явного
  поля / SalesRep не привязан) — заполним позже.
"""
import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.sales.bitrix.transport import _get_paged_with_retry
from app.sales.sync import should_import_deal

# Коды полей сделки в Битриксе (см. memory bitrix-work-structure / bitrix-api-vibecode).
AMOUNT_FIELD = "ufCrm_1690138678699"      # «Клиентская стоимость до НДС», формат "1500000|RUB" (НЕ opportunity!)
PERIOD_FROM_FIELD = "ufCrm_1723639172"    # Старт РК (date)
PERIOD_TO_FIELD = "ufCrm_1723639189"      # Конец РК (date)
BRAND_FIELD = "ufCrm_64BD76BC5BC45"       # «Бренд» (текст) — НЕ услуга! (пока не мапим в brand_id)
# «Продукты Simb-ad» (услуга) приходит смарт-процессом: поле сделки parentId1050 = id элемента СП 1050.
PRODUCT_SP_PARENT = "parentId1050"
PRODUCT_SP_ID = "1050"


def parse_money(v):
    """'1500000|RUB' → (1500000.0, 'RUB'); '' / None → (None, 'RUB')."""
    if not v:
        return None, "RUB"
    s = str(v)
    if "|" in s:
        a, c = s.split("|", 1)
        try:
            return float(a), (c or "RUB")
        except ValueError:
            return None, (c or "RUB")
    try:
        return float(s), "RUB"
    except ValueError:
        return None, "RUB"


def parse_bx_date(v):
    if not v:
        return None
    try:
        return datetime.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def map_deal(raw: dict, pipelines: dict, stages: dict, agency_links: dict, products: dict):
    """Сырая сделка Битрикса → поля SalesDeal. None, если воронка не отслеживается.
    `products` — карта id элемента СП 1050 → название («Продукты Simb-ad»/услуга)."""
    cat = raw.get("categoryId")
    if cat not in pipelines:
        return None
    amount, currency = parse_money(raw.get(AMOUNT_FIELD) or raw.get("opportunity"))
    prod_ref = raw.get(PRODUCT_SP_PARENT)
    product = products.get(str(prod_ref)) if prod_ref not in (None, 0, "0") else None
    return dict(
        bitrix_id=str(raw.get("id")),
        title=raw.get("title"),
        pipeline=pipelines[cat],
        bitrix_stage=stages.get((cat, raw.get("stageId")), raw.get("stageId")),
        amount=amount,
        currency=currency or "RUB",
        agency_id=agency_links.get(str(raw.get("companyId"))),
        product=product,
        period_from=parse_bx_date(raw.get(PERIOD_FROM_FIELD)),
        period_to=parse_bx_date(raw.get(PERIOD_TO_FIELD)),
    )


def product_map() -> dict:
    """Словарь «Продукты Simb-ad»: id элемента смарт-процесса 1050 → название (услуга)."""
    items = _get_paged_with_retry(f"/items/{PRODUCT_SP_ID}", {})
    return {str(x.get("id")): x.get("title") for x in items if x.get("id")}


def reference_maps(db: Session):
    """Справочники для резолва: воронки (categoryId→имя), стадии ((cat,код)→имя),
    агентства (bx company id→наш id через sales_bitrix_links).

    Только ОТСЛЕЖИВАЕМЫЕ воронки (is_tracked): заведённые refresh_pipelines
    с is_tracked=False в импорт не попадают — иначе тянется мусор из чужих воронок."""
    pipelines = {r[0]: r[1] for r in db.execute(
        text("SELECT bitrix_category_id, name FROM sales_pipelines WHERE is_tracked")).all()}
    stages = {(r[0], r[1]): r[2] for r in db.execute(
        text("SELECT bitrix_category_id, status_id, name FROM sales_pipeline_stages")).all()}
    agency_links = {r[0]: r[1] for r in db.execute(
        text("SELECT bx_id, our_id FROM sales_bitrix_links WHERE kind='agencies'")).all()}
    return pipelines, stages, agency_links


def max_bitrix_id(db: Session) -> int:
    ids = [r[0] for r in db.execute(text("SELECT bitrix_id FROM sales_deals")).all()]
    return max((int(x) for x in ids if x and str(x).isdigit()), default=0)


def _default_fetch(after: int) -> list:
    return _get_paged_with_retry("/deals", {"filter[>id]": str(after)})


def select_new_deals(raw_rows, existing, tombstoned, pipelines, stages, agency_links, products):
    """Чистый отбор сделок к вставке (без БД — тестируется изолированно).

    Порядок отсева: уже есть у нас (дедуп) → удалена вручную (надгробие, не
    воскрешаем) → неотслеживаемая/неизвестная воронка (map_deal вернул None).
    Возвращает (список смапленных, счётчики отсева)."""
    exist = {str(x) for x in (existing or ())}
    mapped, skipped_untracked, skipped_existing, skipped_tombstoned = [], 0, 0, 0
    for raw in raw_rows:
        bid = str(raw.get("id"))
        if bid in exist:
            skipped_existing += 1
            continue
        if not should_import_deal(bid, tombstoned):
            skipped_tombstoned += 1
            continue
        d = map_deal(raw, pipelines, stages, agency_links, products)
        if d is None:
            skipped_untracked += 1
            continue
        mapped.append(d)
    return mapped, {"skipped_untracked": skipped_untracked,
                    "skipped_existing": skipped_existing,
                    "skipped_tombstoned": skipped_tombstoned}


def import_new_deals(db: Session, commit: bool = False, fetch=None) -> dict:
    """Инкрементальный импорт: тянет сделки с id > нашего максимума, отсекает
    удалённые вручную (надгробия), неотслеживаемые воронки и дубли, маппит, при
    commit=True — пишет. Возвращает отчёт.
    `fetch(after)->list` инъектируется в тестах (по умолчанию — живой Битрикс)."""
    fetch = fetch or _default_fetch
    pipelines, stages, agency_links = reference_maps(db)
    products = product_map()
    anchor = max_bitrix_id(db)
    existing = {r[0] for r in db.execute(text("SELECT bitrix_id FROM sales_deals")).all()}
    tombstoned = {r[0] for r in db.execute(text("SELECT bitrix_id FROM sales_deleted_deals")).all()}

    raw_rows = fetch(anchor)
    mapped, counts = select_new_deals(raw_rows, existing, tombstoned,
                                      pipelines, stages, agency_links, products)

    report = {
        "anchor_bitrix_id": anchor,
        "fetched": len(raw_rows),
        "to_insert": len(mapped),
        "skipped_untracked": counts["skipped_untracked"],
        "skipped_existing": counts["skipped_existing"],
        "skipped_tombstoned": counts["skipped_tombstoned"],
        "inserted": 0,
        "items": [{
            "bitrix_id": d["bitrix_id"], "title": d["title"], "pipeline": d["pipeline"],
            "bitrix_stage": d["bitrix_stage"], "amount": d["amount"], "agency_id": d["agency_id"],
            "period_from": d["period_from"].isoformat() if d["period_from"] else None,
            "product": d["product"],
        } for d in mapped],
    }

    if commit and mapped:
        from app.sales.models import SalesDeal
        # date_create = момент попадания сделки в нашу БД (время импорта). Служит
        # и для сортировки «сначала новые», и для подсветки свежих сделок 3 суток.
        imported_at = datetime.datetime.utcnow()
        for d in mapped:
            db.add(SalesDeal(**d, date_create=imported_at))
        db.commit()
        report["inserted"] = len(mapped)
    return report
