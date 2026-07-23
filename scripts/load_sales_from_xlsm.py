# -*- coding: utf-8 -*-
"""
Шаг 2 импорта: грузит sales_import.json (выгрузку из «Дашборд по продажам.xlsm»)
в таблицы sales_*.

Запуск внутри контейнера:
    docker exec finance_backend python /app/scripts/load_sales_from_xlsm.py --dry-run
    docker exec finance_backend python /app/scripts/load_sales_from_xlsm.py

Идемпотентен: повторный запуск не создаёт дублей. Сделки сопоставляются
по bitrix_id, справочные значения — по нормализованному имени, поэтому
"web", "in-app", "inapp", "in app" схлопываются в одну запись.

Маппинг стадий восстановлен из GetCWValue_Fast (modFillinClearData.bas) и
расширен на все воронки по решению заказчика 2026-07-23: берём все данные,
раскладку по слоям правим потом строками в таблице.
"""
import argparse
import json
import re
import sys
from datetime import datetime

sys.path.insert(0, "/app")

from app.database import SessionLocal  # noqa: E402
# Импорт основных моделей обязателен: sales_advertisers и sales_deals ссылаются
# на counterparties и users, и без регистрации этих таблиц в Base.metadata
# SQLAlchemy падает при flush с NoReferencedTableError.
from app import models as core_models  # noqa: E402,F401
from app.sales.models import (SalesPipeline, SalesBitrixStageMap, SalesService,  # noqa: E402
                              SalesAdvertiser, SalesBrand, SalesRep, SalesDeal,
                              SalesBitrixRaw)
from app.sales.normalize import normalize_name  # noqa: E402
from app.sales.bitrix_client import payload_hash  # noqa: E402

JSON_PATH = "/app/scripts/sales_import.json"

# (воронка, стадия) -> (stage_key, money_layer, is_active)
# is_active=False: строка видна в справочнике, но в слои не попадает —
# так решение «не считать» зафиксировано явно, а не спрятано в пропуске.
STAGE_MAP = [
    ("Общая", "Подготовка МП", "media_plan", "планируемые", True),
    ("Общая", "Медиаплан отправлен", "media_plan", "планируемые", True),
    ("Общая", "Бронь подтверждена", "booking", "планируемые", True),
    ("Общая", "Архив", "archive", "фактические", True),
    ("Pharm", "Все брони на год", "booking", "планируемые", True),
    ("Pharm", "Готовятся к старту (траффик)", "launch_prep", "реализуемые", True),
    ("Pharm", "В размещении", "launch", "реализуемые", True),
    ("Pharm", "Предварительная сверка", "launch", "реализуемые", True),
    ("Pharm", "Архив", "archive", "фактические", True),
    ("Other", "Все брони", "booking", "планируемые", True),
    ("Other", "В размещении", "launch", "реализуемые", True),
    ("Other", "Предварительная сверка", "launch", "реализуемые", True),
    ("Other", "Архив", "archive", "фактические", True),
    ("ДО", "Подготовка и согласование ДС (задача на Наде)", "closing", "фактические", True),
    ("ДО", "Согласование ДС", "closing", "фактические", True),
    ("ДО", "Закрывающие документы | Мария", "closing", "фактические", True),
    ("ДО", "Выставить в ЭДО | Денис", "closing", "фактические", True),
    ("ДО", "Отчеты в ОРД", "closing", "фактические", True),
    ("ДО", "Повторные сделки", "archive", "фактические", True),
    ("ДО", "Архив", "archive", "фактические", True),
    ("СК (премии)", "Подготовка ДС", "closing", "фактические", True),
    ("СК (премии)", "Выставление в ЭДО", "closing", "фактические", True),
    ("СК (премии)", "Вопрос закрыт", "archive", "фактические", True),
    ("Сверка_сайты", "Счет в ЭДО", "closing", "фактические", True),
    ("Сверка_сайты", "Вопрос закрыт", "archive", "фактические", True),
    ("Сверка_сайты", "Архив", "archive", "фактические", True),
    # Не считаются деньгами ни в каком слое
    ("Other", "Сделка провалена", "lost", "планируемые", False),
    ("Pharm", "Сделка провалена", "lost", "планируемые", False),
    ("ДО", "Сделка провалена", "lost", "планируемые", False),
    ("Сверка_сайты", "Сделка провалена", "lost", "планируемые", False),
    ("БЕЗ СДЕЛКИ", "удалить", "deleted", "планируемые", False),
]

_SPLIT = re.compile(r"[;,/|]| и ")


def split_multi(raw):
    """Многозначные поля Битрикса приходят одной строкой через разделитель."""
    if not raw:
        return []
    return [p.strip() for p in _SPLIT.split(str(raw)) if p and p.strip()]


def parse_dt(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v))
    except ValueError:
        return None


def parse_num(v):
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


class Loader:
    def __init__(self, db, dry):
        self.db, self.dry = db, dry
        self.stats = {}

    def bump(self, key, n=1):
        self.stats[key] = self.stats.get(key, 0) + n

    def _index(self, model):
        return {normalize_name(o.name): o for o in self.db.query(model).all()}

    def seed_pipelines(self, deals):
        existing = self._index(SalesPipeline)
        for name in sorted({d["pipeline"] for d in deals if d["pipeline"]}):
            if normalize_name(name) in existing:
                continue
            self.bump("pipelines")
            if not self.dry:
                obj = SalesPipeline(name=name)
                self.db.add(obj)
                existing[normalize_name(name)] = obj
        if not self.dry:
            self.db.flush()

    def seed_stage_map(self):
        have = {(r.pipeline, r.bitrix_stage)
                for r in self.db.query(SalesBitrixStageMap).all()}
        for i, (pipe, stage, key, layer, active) in enumerate(STAGE_MAP):
            if (pipe, stage) in have:
                continue
            self.bump("stage_map")
            if not self.dry:
                self.db.add(SalesBitrixStageMap(
                    pipeline=pipe, bitrix_stage=stage, stage_key=key,
                    money_layer=layer, sort_order=i, is_active=active))
        if not self.dry:
            self.db.flush()

    def seed_named(self, model, names, **extra):
        """Создаёт отсутствующие записи справочника по нормализованному имени."""
        index = self._index(model)
        for name in sorted(names):
            key = normalize_name(name)
            if not key or key in index:
                continue
            self.bump(model.__tablename__)
            obj = model(name=name, **extra)
            index[key] = obj
            if not self.dry:
                self.db.add(obj)
        if not self.dry:
            self.db.flush()
        return index

    def run(self, data):
        deals = data["deals"]

        self.seed_pipelines(deals)
        self.seed_stage_map()

        # Услуги: лист Products + лист Directory + значения «Продукты Simb-ad» в сделках
        services = {p["name"] for p in data["products"]}
        services |= set(data["directory_services"])
        for d in deals:
            services |= set(split_multi(d["products"]))
        svc_idx = self.seed_named(SalesService, services)

        # Рекламодатели: поле «Рекламодатель = Лид», иначе «Компания»
        advertisers = set()
        for d in deals:
            advertisers |= set(split_multi(d["advertiser"]))
        adv_idx = self.seed_named(SalesAdvertiser, advertisers)

        # Продавец берётся из «Ответственный Sales за клиента» (CJ), запасной
        # источник — «Sales» (BH, заполнена лишь в 7% строк и является подмножеством CJ).
        # Аккаунт-менеджер — из «Ответственный КС» (BI).
        # Колонка «Ответственный» (L) как источник продавца НЕ годится: она заполнена
        # на 100%, но смешивает обе роли (Жанна Смирнова — аккаунт, 1002 сделки).
        reps = set()
        for d in deals:
            reps |= set(split_multi(d.get("sales_client")))
            reps |= set(split_multi(d.get("sales")))
            reps |= set(split_multi(d.get("account_mgr")))
        rep_idx = self.seed_named(SalesRep, reps)

        # Бренды принадлежат рекламодателю — создаём в паре
        brand_idx = {(b.advertiser_id, normalize_name(b.name)): b
                     for b in self.db.query(SalesBrand).all()}
        if not self.dry:
            self.db.flush()

        deal_idx = {d.bitrix_id: d for d in self.db.query(SalesDeal).all()}
        raw_hashes = {(r.bitrix_id, r.payload_hash) for r in
                      self.db.query(SalesBitrixRaw).filter(SalesBitrixRaw.entity == "deal").all()}

        for d in deals:
            bid = str(d["bitrix_id"])
            adv = None
            adv_names = split_multi(d["advertiser"])
            if adv_names:
                adv = adv_idx.get(normalize_name(adv_names[0]))

            brand = None
            brand_names = split_multi(d["brands_list"]) or split_multi(d["brand_manuf"])
            if brand_names and adv is not None and not self.dry:
                bkey = (adv.id, normalize_name(brand_names[0]))
                brand = brand_idx.get(bkey)
                if brand is None:
                    brand = SalesBrand(name=brand_names[0], advertiser_id=adv.id)
                    self.db.add(brand)
                    self.db.flush()
                    brand_idx[bkey] = brand
                    self.bump("sales_brands")
            elif brand_names:
                self.bump("sales_brands")

            rep_names = split_multi(d.get("sales_client")) or split_multi(d.get("sales"))
            rep = rep_idx.get(normalize_name(rep_names[0])) if rep_names else None

            acct_names = split_multi(d.get("account_mgr"))
            acct = rep_idx.get(normalize_name(acct_names[0])) if acct_names else None

            values = dict(
                title=d["title"],
                pipeline=d["pipeline"],
                bitrix_stage=d["stage"],
                amount=parse_num(d["amount"]) or parse_num(d["client_sum"]),
                currency=(d["currency"] or "RUB"),
                advertiser_id=getattr(adv, "id", None),
                brand_id=getattr(brand, "id", None),
                sales_rep_id=getattr(rep, "id", None),
                account_manager_id=getattr(acct, "id", None),
                date_create=parse_dt(d["date_create"]),
                date_modify=parse_dt(d["date_modify"]),
            )

            existing = deal_idx.get(bid)
            if existing is None:
                self.bump("deals_created")
                if not self.dry:
                    self.db.add(SalesDeal(bitrix_id=bid, **values))
            else:
                self.bump("deals_updated")
                if not self.dry:
                    for k, v in values.items():
                        setattr(existing, k, v)

            # Append-only слой сырья: версия пишется только при смене хеша
            h = payload_hash(d)
            if (bid, h) not in raw_hashes:
                self.bump("raw_versions")
                if not self.dry:
                    self.db.add(SalesBitrixRaw(entity="deal", bitrix_id=bid,
                                               payload=d, payload_hash=h))
                raw_hashes.add((bid, h))

        # Dry-run всё равно доходит до flush и откатывается: иначе путь записи
        # не проверяется вообще и «сухой прогон» даёт ложную уверенность
        # (именно так пропустили NoReferencedTableError на первом запуске).
        self.db.flush()
        if self.dry:
            self.db.rollback()
        else:
            self.db.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", default=JSON_PATH)
    args = ap.parse_args()

    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)

    db = SessionLocal()
    try:
        loader = Loader(db, args.dry_run)
        loader.run(data)
        print("РЕЖИМ:", "dry-run (ничего не записано)" if args.dry_run else "запись выполнена")
        for k in sorted(loader.stats):
            print(f"  {k}: {loader.stats[k]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
