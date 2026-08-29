# -*- coding: utf-8 -*-
"""
Шаг 2 импорта: грузит sales_import.json (выгрузку из «Дашборд по продажам.xlsm»)
в таблицы sales_*.

Запуск внутри контейнера:
    docker exec finance_backend python -m scripts.load_sales_from_xlsm --dry-run
    docker exec finance_backend python -m scripts.load_sales_from_xlsm

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

sys.path.insert(0, "/app")   # запуск через `python -m scripts.<имя>` это уже делает; строка оставлена для прямого вызова

from app.database import SessionLocal  # noqa: E402
# Импорт основных моделей обязателен: sales_advertisers и sales_deals ссылаются
# на counterparties и users, и без регистрации этих таблиц в Base.metadata
# SQLAlchemy падает при flush с NoReferencedTableError.
from app import models as core_models  # noqa: E402,F401
from app.sales.models import (SalesPipeline, SalesBitrixStageMap, SalesService,  # noqa: E402
                              SalesAdvertiser, SalesBrand, SalesRep, SalesDeal,
                              SalesBitrixRaw, SalesDealFieldOverride, SalesAgency)
from app.sales.normalize import normalize_name  # noqa: E402
from app.sales.sync import payload_hash  # noqa: E402

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

# Разделители списка — только ';', '|' и перевод строки.
# Запятая и слэш НЕ разделители: они встречаются внутри самих названий
# («AVVA Pharmaceuticals (АВВА Фармасьютикалс, Россия)»,
#  «Digital alliance / Диджитал Альянс»). Разбор по ним резал имена
# на фрагменты и плодил мусор в справочнике.
_SPLIT = re.compile(r"[;|\n\r]+")

# Рекламодатель-заглушка для сделок, где заполнен только бренд.
VIRTUAL_ADVERTISER = "(рекламодатель не указан)"

# «[L]ACINO (Ацино)» -> ('ACINO', 'Ацино'). Префикс [L] приходит из поля
# «Рекламодатель = Лид» в Битриксе и в названии не нужен.
_LEAD_PREFIX = re.compile(r"^\s*\[L\]\s*", re.IGNORECASE)
_EN_RU = re.compile(r"^(?P<en>[^(]+?)\s*\((?P<ru>[^)]*)\)?\s*$")
_CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def split_multi(raw):
    """Многозначные поля Битрикса приходят одной строкой через разделитель."""
    if not raw:
        return []
    return [p.strip() for p in _SPLIT.split(str(raw)) if p and p.strip()]


def parse_advertiser_name(raw):
    """Разбирает «[L]ACINO (Ацино)» на английское и русское названия.

    Возвращает (полное_имя_без_префикса, name_en, name_ru). Если разобрать
    не удалось — имя целиком кладётся в ту графу, которой соответствует
    его алфавит, а вторая остаётся пустой: выдумывать перевод нельзя."""
    name = _LEAD_PREFIX.sub("", str(raw or "")).strip()
    if not name:
        return "", None, None

    m = _EN_RU.match(name)
    if m:
        en, ru = m.group("en").strip(), m.group("ru").strip()
        # Скобка могла содержать не перевод, а уточнение («неизвестен РД»).
        # Считаем переводом только кириллический хвост при латинском начале.
        if en and ru and _CYRILLIC.search(ru) and not _CYRILLIC.search(en):
            return name, en, ru

    if _CYRILLIC.search(name):
        return name, None, name
    return name, name, None


def parse_dt(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v))
    except ValueError:
        return None


def parse_date(v):
    """Даты РК в Excel лежат вперемешку: часть настоящими датами, часть текстом.
    Без разбора текстовых форматов теряется ровно половина периодов размещения."""
    dt = parse_dt(v)
    if dt:
        return dt.date()
    s = str(v or "").strip()
    if not s:
        return None
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
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
        self.seed_named(SalesService, services)   # индекс не нужен: услуги ищутся по имени ниже

        # Рекламодатели: поле «Рекламодатель = Лид». Имя очищается от префикса [L]
        # и разбирается на английское/русское написание.
        adv_parsed = {}
        for d in deals:
            for raw in split_multi(d["advertiser"]):
                name, en, ru = parse_advertiser_name(raw)
                if name:
                    adv_parsed[normalize_name(name)] = (name, en, ru)

        adv_idx = self._index(SalesAdvertiser)

        # Виртуальный рекламодатель для строк, где заполнен только бренд.
        # Без него такие бренды теряются: advertiser_id у бренда NOT NULL.
        # Помечен явно, чтобы его было видно в справочнике и разобрать вручную.
        if normalize_name(VIRTUAL_ADVERTISER) not in adv_idx:
            self.bump("sales_advertisers")
            virt = SalesAdvertiser(name=VIRTUAL_ADVERTISER, name_ru=VIRTUAL_ADVERTISER,
                                   note="Создан автоматически: в сделке был бренд без рекламодателя")
            adv_idx[normalize_name(VIRTUAL_ADVERTISER)] = virt
            if not self.dry:
                self.db.add(virt)
                self.db.flush()
        for key, (name, en, ru) in sorted(adv_parsed.items()):
            if key in adv_idx:
                continue
            self.bump("sales_advertisers")
            obj = SalesAdvertiser(name=name, name_en=en, name_ru=ru)
            adv_idx[key] = obj
            if not self.dry:
                self.db.add(obj)
        if not self.dry:
            self.db.flush()

        # Продавец берётся из «Ответственный Sales за клиента» (CJ), запасной
        # источник — «Sales» (BH, заполнена лишь в 7% строк и является подмножеством CJ).
        # Аккаунт-менеджер — из «Ответственный КС» (BI).
        # Колонка «Ответственный» (L) как источник продавца НЕ годится: она заполнена
        # на 100%, но смешивает обе роли (Жанна Смирнова — аккаунт, 1002 сделки).
        # Агентства из поля «Рекламные агентства». Холдинг и юрлицо в исходнике
        # не размечены — заполняются вручную в справочнике.
        agencies = set()
        for d in deals:
            agencies |= set(split_multi(d.get("agencies")))
        agency_idx = self.seed_named(SalesAgency, agencies)

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

        # Контрагенты финмодуля — источник истины по плательщикам.
        # Сопоставление строгое, по нормализованному имени: никакого нечёткого матчинга.
        cp_idx = {normalize_name(c.name): c
                  for c in self.db.query(core_models.Counterparty).all()}

        deal_idx = {d.bitrix_id: d for d in self.db.query(SalesDeal).all()}

        # Карта защищённых полей: {deal_id: {'advertiser_id', 'period_from', ...}}
        overrides = {}
        for o in self.db.query(SalesDealFieldOverride).all():
            overrides.setdefault(o.deal_id, set()).add(o.field_name)
        raw_hashes = {(r.bitrix_id, r.payload_hash) for r in
                      self.db.query(SalesBitrixRaw).filter(SalesBitrixRaw.entity == "deal").all()}

        for d in deals:
            bid = str(d["bitrix_id"])
            adv = None
            adv_names = split_multi(d["advertiser"])
            if adv_names:
                clean, _, _ = parse_advertiser_name(adv_names[0])
                adv = adv_idx.get(normalize_name(clean))

            brand = None
            brand_names = split_multi(d["brands_list"]) or split_multi(d["brand_manuf"])
            # Бренд без рекламодателя вешаем на заглушку, а не теряем.
            if brand_names and adv is None:
                adv = adv_idx.get(normalize_name(VIRTUAL_ADVERTISER))
                self.bump("брендов_без_рекламодателя")
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

            agency_names = split_multi(d.get("agencies"))
            agency = agency_idx.get(normalize_name(agency_names[0])) if agency_names else None

            # «Компания» — плательщик: агентство при работе через агентство,
            # рекламодатель при прямом договоре. Связи проставляем только при
            # точном совпадении, всё остальное остаётся строкой для ручного разбора.
            payer = (str(d.get("company") or "")).strip() or None
            payer_key = normalize_name(payer) if payer else None
            payer_cp = cp_idx.get(payer_key) if payer_key else None
            if payer_key and agency is None:
                match = agency_idx.get(payer_key)
                if match is not None:
                    agency = match
                    self.bump("плательщик_опознан_как_агентство")

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
                agency_id=getattr(agency, "id", None),
                payer_name=payer,
                product=(str(d.get("products") or "").strip() or None),
                counterparty_id=getattr(payer_cp, "id", None),
                date_create=parse_dt(d["date_create"]),
                date_modify=parse_dt(d["date_modify"]),
                period_from=parse_date(d.get("rk_start")),
                period_to=parse_date(d.get("rk_end")),
            )

            existing = deal_idx.get(bid)
            if existing is None:
                self.bump("deals_created")
                if not self.dry:
                    self.db.add(SalesDeal(bitrix_id=bid, **values))
            else:
                self.bump("deals_updated")
                # Поля, заполненные человеком у нас, синхронизация не трогает.
                # Иначе ручная стандартизация пропадает на первом же прогоне.
                protected = overrides.get(existing.id, set())
                if protected:
                    self.bump("полей_защищено_от_затирания", len(protected))
                if not self.dry:
                    for k, v in values.items():
                        if k not in protected:
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
