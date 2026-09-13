# -*- coding: utf-8 -*-
"""Реестр именованных проверок для разметки стадий.

Строка `sales_stage_checks` ссылается не на ПОЛЕ, а на имя проверки отсюда. Причина —
проверяемое бывает трёх пород: колонка сделки (плательщик), документ (УПД), состояние в
чужом модуле (ЕРИД выпущен). Если бы в строке стояло имя поля, код обрастал бы
разветвлением на каждую породу. Здесь новый случай — строка в базе, новая порода — ещё
одна функция; ветвление не растёт ни от того, ни от другого.

## Четыре исхода, а не да/нет

`OK` — сошлось. `NOT_YET` — проверено и не выполнено: ЕДИНСТВЕННЫЙ исход, запирающий
движение. `UNKNOWN` — проверить нечем (нет интеграции или связи): показываем, но
пропускаем. `NA` — неприменимо: на карточке не показываем вовсе.

Разделение UNKNOWN и NOT_YET не теоретическое. Правило оплаты в очереди аккаунта уже
выключали ровно потому, что «не знаю» было неотличимо от «не оплачено» — и каждая
закрытая сделка выглядела просроченной. Если UNKNOWN начнёт запирать, недостроенный мост
заморозит конвейер.

## Веерные проверки

Часть условий — свойство не сделки, а площадки или комплекта: у одной сделки пять
площадок, три согласовали, две нет. Ответа «да/нет» на уровне сделки тут не существует,
поэтому веерная проверка возвращает «3 из 5» и ИМЕНА мешающих. Без имён на карточке
получится «не согласовано» без ответа на вопрос «у кого».

Веер сам решает, к кому условие применимо, и пропускает остальных. Пример: если условие
касается только площадок с нашим кодом, проверка обходит их сама — выразить это
сделочным условием `applies_when` нельзя, там нет такого уровня.
"""
from dataclasses import dataclass, field
from typing import Callable, Optional

from sqlalchemy import text

from app.ad.stat_sources import OWN

# ── Исходы ───────────────────────────────────────────────────────────────────
OK = "ok"
NOT_YET = "not_yet"
UNKNOWN = "unknown"
NA = "n/a"


@dataclass
class Result:
    state: str
    detail: str = ""
    blockers: tuple = ()

    @property
    def blocks(self) -> bool:
        """Запирает движение только «не сделано» — см. шапку файла."""
        return self.state == NOT_YET


def _ok(detail: str = "") -> Result:
    return Result(OK, detail)


def _not_yet(detail: str = "", blockers=()) -> Result:
    return Result(NOT_YET, detail, tuple(blockers))


def _unknown(why: str) -> Result:
    """`why` обязателен: «неизвестно» без причины неотличимо от недоделанной проверки."""
    return Result(UNKNOWN, why)


def _na(why: str = "") -> Result:
    return Result(NA, why)


def _fan(done: int, total: int, blockers, noun: str) -> Result:
    """Общий ответ веерной проверки. Ноль применимых — НЕ «выполнено», а «неприменимо»:
    сказать «согласовано 0 из 0» значит объявить сделанным то, чего не существует."""
    if total == 0:
        return _na(f"{noun} нет")
    if done >= total:
        return _ok(f"{done} из {total}")
    return _not_yet(f"{done} из {total}", blockers)


# ── Окружение сделки ─────────────────────────────────────────────────────────

class Ctx:
    """Загруженное ОДИН РАЗ окружение сделки: проверок два десятка, и каждая своим
    запросом дала бы N+1 на карточке и тем более в очереди."""

    def __init__(self, db, deal):
        self.db = db
        self.deal = deal
        self._cache: dict = {}

    def _once(self, key: str, fn: Callable):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    @property
    def file_kinds(self) -> set:
        def load():
            from app.sales.models import SalesDealFile
            return {k for (k,) in self.db.query(SalesDealFile.kind)
                    .filter(SalesDealFile.deal_id == self.deal.id).all()}
        return self._once("file_kinds", load)

    @property
    def plan(self):
        """Последний НЕ ОТКЛОНЁННЫЙ план сделки.

        Фильтр `status <> 'rejected'` — не украшение: так план сделки выбирают ещё
        ЧЕТЫРЕ места (`ad/build.py`, `routers/annexes.py`, `sales/annex.py`,
        `sales/row_context.py`), и у `ad/build.py` на это есть отдельный тест, требующий
        не заводить пятую копию условия. Без фильтра гейт «план привязан» пропустил бы
        сделку по отклонённому плану, а объём и цели по нему же не посчитались бы —
        расхождение выглядело бы ошибкой расчёта, а не двумя разными выборками."""
        def load():
            from app.sales.models import SalesMediaPlan
            return (self.db.query(SalesMediaPlan)
                    .filter(SalesMediaPlan.deal_id == self.deal.id,
                            SalesMediaPlan.status != "rejected")
                    .order_by(SalesMediaPlan.version.desc()).first())
        return self._once("plan", load)

    @property
    def sets(self) -> list:
        def load():
            from app.launch_prep.models import LaunchPrepCreativeSet
            return (self.db.query(LaunchPrepCreativeSet)
                    .filter(LaunchPrepCreativeSet.deal_id == self.deal.id).all())
        return self._once("sets", load)

    @property
    def pairs(self) -> list:
        """Пары «комплект × площадка» этой сделки, с именем площадки для списка мешающих."""
        def load():
            if not self.sets:
                return []
            return self.db.execute(text("""
                SELECT p.id, p.agreed_at, coalesce(pub.name, 'без имени') AS publisher
                  FROM launch_prep_pair p
                  JOIN launch_prep_target t ON t.id = p.target_id
                  LEFT JOIN sales_publishers pub ON pub.id = t.publisher_id
                 WHERE p.set_id = ANY(:s)
            """), {"s": [s.id for s in self.sets]}).mappings().all()
        return self._once("pairs", load)

    @property
    def campaign(self):
        def load():
            from app.ad.models import AdCampaign
            return (self.db.query(AdCampaign)
                    .filter(AdCampaign.deal_id == self.deal.id)
                    .order_by(AdCampaign.month.desc()).first())
        return self._once("campaign", load)

    @property
    def placements(self) -> list:
        def load():
            if not self.campaign:
                return []
            return self.db.execute(text("""
                SELECT pl.id, coalesce(pub.name, 'без имени') AS publisher,
                       pub.our_code
                  FROM ad_campaign_placement pl
                  LEFT JOIN sales_publishers pub ON pub.id = pl.publisher_id
                 WHERE pl.campaign_id = :c
            """), {"c": self.campaign.id}).mappings().all()
        return self._once("placements", load)

    @property
    def fact_by_placement(self) -> dict:
        """Показы НАШЕГО счётчика по размещениям, отдельно демо и отдельно боевое.

        Демо считается отдельно намеренно: на стенде это единственный факт, он лежит в
        той же таблице и входит в `OWN`, поэтому проверка «факт собран» без такого
        разделения была бы зелёной на стенде и пустой на проде — то есть соврала бы
        ровно там, где её принимают."""
        def load():
            if not self.campaign:
                return {}
            rows = self.db.execute(text("""
                SELECT placement_id, source, sum(shows) AS shows
                  FROM ad_campaign_stat
                 WHERE campaign_id = :c AND source = ANY(:src)
                 GROUP BY placement_id, source
            """), {"c": self.campaign.id, "src": list(OWN)}).mappings().all()
            out: dict = {}
            for r in rows:
                slot = out.setdefault(r["placement_id"], {"real": 0, "demo": 0})
                slot["demo" if r["source"] == "demo" else "real"] += int(r["shows"] or 0)
            return out
        return self._once("fact", load)


# ── Реестр ───────────────────────────────────────────────────────────────────

@dataclass
class Check:
    key: str
    title: str          # подпись в разметке и на карточке
    hint: str           # что человеку сделать
    fn: Callable        # (Ctx) -> Result
    fan: bool = False   # веерная: ответ вида «3 из 5»
    where: str = ""     # человеческое название места, где это чинится
    link: str = ""      # адрес; «#секция» — блок на этой же карточке сделки


REGISTRY: dict = {}

# ГДЕ каждое требование чинится. Отдельной таблицей, а не аргументом у каждой проверки:
# так все ответы «куда идти» видны разом, и сразу заметно, что четыре документа ведут в
# один блок карточки, а услуга с периодом — в медиаплан, потому что растут оттуда.
#
# Без места «не выполнено» бесполезно: человек узнаёт, чего не хватает, и идёт
# спрашивать, куда идти. «#секция» — блок на этой же карточке сделки.
PLACES = {
    "mp_linked":            ("Конструктор медиапланов", "/accounts/mp"),
    "service_set":          ("Медиаплан — первая строка размещения", "/accounts/mp"),
    "period_set":           ("Медиаплан — период размещения", "/accounts/mp"),
    "realization_pipeline": ("Здесь же, в диалоге движения", ""),
    "payer_set":            ("Карточка сделки — шапка", "#head"),
    "final_contract":       ("Карточка сделки — блок «ОРД»", "#ord"),
    "ord_initial_contract": ("Карточка сделки — блок «ОРД»", "#ord"),
    "creatives_accepted":   ("Карточка сделки — блок «Креативы»", "#creatives"),
    "placements_approved":  ("Трафик — очередь согласования", "/traffic/queue"),
    "erid_issued":          ("Карточка сделки — блок «ОРД»", "#ord"),
    "campaign_ready":       ("Трафик — дашборд кампаний", "/traffic/dashboard"),
    "fact_collected":       ("Трафик — дашборд кампаний", "/traffic/dashboard"),
    "annex_generated":      ("Справочники — Приложения к договорам", "/directory/annexes"),
    "signatory_filled":     ("Справочники — Контрагенты", "/directory/counterparties"),
    "ds_signed":            ("Карточка сделки — Документы", "#docs"),
    "invoice_issued":       ("Карточка сделки — Документы", "#docs"),
    "upd_issued":           ("Карточка сделки — Документы", "#docs"),
    "report_attached":      ("Карточка сделки — Документы", "#docs"),
    "edo_sent":             ("Финансы — Документы Диадока", "/finance/import"),
    "ord_acts_sent":        ("Аккаунты — ОРД", "/accounts/ord"),
    "payment_received":     ("Финансы — Дебиторка", "/finance/receivables"),
}


def register(key: str, title: str, hint: str, fan: bool = False):
    def deco(fn: Callable):
        if key in REGISTRY:
            raise RuntimeError(f"проверка {key} уже зарегистрирована")
        where, link = PLACES.get(key, ("", ""))
        REGISTRY[key] = Check(key=key, title=title, hint=hint, fn=fn, fan=fan,
                              where=where, link=link)
        return fn
    return deco


# ── Песочница ────────────────────────────────────────────────────────────────

@register("mp_linked", "Медиаплан привязан к сделке",
          "Привяжите план в конструкторе или создайте сделку из плана")
def _mp_linked(c: Ctx) -> Result:
    if c.plan:
        return _ok(f"версия {c.plan.version}")
    if "mp" in c.file_kinds:
        return _ok("файлом из Битрикса")
    return _not_yet("плана нет")


@register("service_set", "Услуга сделки определена",
          "Привяжите медиаплан — услуга берётся из его первой строки")
def _service_set(c: Ctx) -> Result:
    """Услуга, период и сам план — три части одной записи, и все три РАСТУТ ИЗ ПЛАНА
    (владелец 13.09.2026). Проверяются они по отдельности потому, что расходятся по
    отдельности: у `product` было пять писателей, а перенос план→сделка услугу не вёз
    вовсе, и сделка оставалась на услуге, которой в плане уже нет.

    Условий применимости у неё НЕТ и быть не может: привязать её к услуге значило бы,
    что у сделки без услуги она никогда не сработает — ровно в том случае, ради которого
    заводится."""
    return _ok() if c.deal.service_id else _not_yet("услуга не определена")


@register("period_set", "Период размещения задан",
          "Привяжите медиаплан — период берётся из него")
def _period_set(c: Ctx) -> Result:
    miss = [n for n, v in (("начало", c.deal.period_from), ("конец", c.deal.period_to))
            if v is None]
    return _ok() if not miss else _not_yet("нет: " + ", ".join(miss))


# ── Бронь ────────────────────────────────────────────────────────────────────

@register("realization_pipeline", "Воронка реализации выбрана",
          "Выберите воронку под продукт в диалоге движения")
def _realization_pipeline(c: Ctx) -> Result:
    return _ok() if c.deal.realization_pipeline_id else _not_yet("не выбрана")


@register("payer_set", "Плательщик определён",
          "Укажите плательщика в шапке сделки")
def _payer_set(c: Ctx) -> Result:
    return _ok() if c.deal.payer_counterparty_id else _not_yet("не определён")


@register("final_contract", "Доходный договор выбран",
          "Выберите договор в блоке ОРД")
def _final_contract(c: Ctx) -> Result:
    return _ok() if c.deal.ord_final_contract_id else _not_yet("не выбран")


@register("ord_initial_contract", "Изначальный договор в цепочке ОРД",
          "Выберите или заведите изначальный договор в блоке ОРД")
def _ord_initial_contract(c: Ctx) -> Result:
    if getattr(c.deal, "is_self_promo", False):
        # Саморекламный договор через API ОРД не создаётся — требовать его нечем.
        return _na("самореклама")
    return _ok() if c.deal.ord_initial_contract_id else _not_yet("не выбран")


# ── Сбор запуска ─────────────────────────────────────────────────────────────

@register("creatives_accepted", "Комплект прошёл первичную проверку трафика",
          "Отправьте материал на проверку и дождитесь вердикта трафика")
def _creatives_accepted(c: Ctx) -> Result:
    # Эта проверка ВЛАДЕЕТ отсутствием комплектов и одна о нём говорит. Соседние
    # (`erid_issued`, `placements_approved`) при нуле комплектов молчат «неприменимо» —
    # иначе на карточке было бы три красных строки об одной и той же причине, и найти
    # среди них корень стало бы труднее, чем при одной.
    if not c.sets:
        return _not_yet("комплектов нет")
    rows = c.db.execute(text("""
        SELECT set_id, verdict FROM launch_prep_review
         WHERE kind = 'первичная_тт' AND pair_id IS NULL AND set_id = ANY(:s)
    """), {"s": [s.id for s in c.sets]}).mappings().all()
    passed = {r["set_id"] for r in rows if r["verdict"] == "ок"}
    bad = [f"№{s.no}" for s in c.sets if s.id not in passed]
    return _fan(len(passed), len(c.sets), bad, "комплектов")


@register("placements_approved", "Площадки согласовали баннер",
          "Дождитесь согласования площадок или разберите отказы", fan=True)
def _placements_approved(c: Ctx) -> Result:
    pairs = c.pairs
    done = [p for p in pairs if p["agreed_at"]]
    bad = sorted({p["publisher"] for p in pairs if not p["agreed_at"]})
    return _fan(len(done), len(pairs), bad, "пар креатив×площадка")


@register("erid_issued", "ЕРИД выпущен",
          "Выпустите ЕРИД в блоке ОРД; при саморекламе внесите полученный вручную",
          fan=True)
def _erid_issued(c: Ctx) -> Result:
    """Веер по КОМПЛЕКТАМ, а не по площадкам: ЕРИД живёт на комплекте креативов.

    Самореклама условий применимости не снимает — ЕРИД обязан быть в любом случае,
    отличается только способ получения (`erid_source`), а это забота модуля ОРД."""
    sets_ = c.sets
    done = [s for s in sets_ if (getattr(s, "erid", "") or "").strip()]
    bad = [f"№{s.no}" for s in sets_ if not (getattr(s, "erid", "") or "").strip()]
    return _fan(len(done), len(sets_), bad, "комплектов")


@register("campaign_ready", "РК заведена и получила идентификатор в DSP",
          "Соберите кампанию в разделе трафика")
def _campaign_ready(c: Ctx) -> Result:
    if not c.campaign:
        return _not_yet("РК не заведена")
    if not (c.campaign.ms_campaign_xxhash or "").strip():
        return _not_yet("РК есть, но в DSP не создана")
    return _ok()


# ── Сверка ───────────────────────────────────────────────────────────────────

@register("fact_collected", "Факт собран по размещениям",
          "Дождитесь съёма статистики или загрузите факт вручную", fan=True)
def _fact_collected(c: Ctx) -> Result:
    """Демо-строки фактом НЕ считаются.

    Они лежат в той же таблице и входят в `OWN` (иначе на стенде дашборд был бы пустым),
    поэтому без этого разделения проверка была бы зелёной на стенде и пустой на проде.
    Когда весь факт демовый, честный ответ — «неизвестно», а не «выполнено»."""
    places = c.placements
    if not places:
        return _na("размещений нет")
    fact = c.fact_by_placement
    real = [p for p in places if fact.get(p["id"], {}).get("real", 0) > 0]
    demo_only = [p for p in places
                 if fact.get(p["id"], {}).get("real", 0) == 0
                 and fact.get(p["id"], {}).get("demo", 0) > 0]
    if not real and demo_only:
        return _unknown("в базе только демо-данные — боевого съёма ещё нет")
    bad = sorted({p["publisher"] for p in places if p not in real})
    return _fan(len(real), len(places), bad, "размещений")


# ── Документооборот ──────────────────────────────────────────────────────────

@register("annex_generated", "Приложение сформировано конструктором",
          "Соберите ДС в конструкторе приложений")
def _annex_generated(c: Ctx) -> Result:
    return _ok() if c.deal.annex_id else _not_yet("приложения нет")


@register("signatory_filled", "Реквизиты подписанта заполнены",
          "Дозаполните карточку плательщика в реестре контрагентов")
def _signatory_filled(c: Ctx) -> Result:
    """Переиспользует проверку конструктора ДС (`annex.party`), а не повторяет её.

    Своя вторая проверка того же дала бы два расходящихся ответа на один вопрос: здесь
    «всё заполнено», а при выгрузке документа — отказ со списком недостающего."""
    from app.models import Counterparty
    from app.sales.annex import party
    cp_id = c.deal.payer_counterparty_id or c.deal.counterparty_id
    if not cp_id:
        return _not_yet("плательщик не определён")
    cp = c.db.query(Counterparty).filter(Counterparty.id == cp_id).first()
    miss = party(cp).get("missing") or []
    return _ok() if not miss else _not_yet(", ".join(miss))


def _file_check(kind: str, what: str):
    def fn(c: Ctx) -> Result:
        return _ok() if kind in c.file_kinds else _not_yet(f"{what} нет")
    return fn


register("ds_signed", "Подписанное ДС в системе",
         "Приложите подписанный документ к сделке")(_file_check("ds", "файла ДС"))
register("invoice_issued", "Счёт выставлен",
         "Приложите счёт к сделке")(_file_check("invoice", "счёта"))
register("upd_issued", "УПД выставлен",
         "Приложите УПД к сделке")(_file_check("upd", "УПД"))
register("report_attached", "Отчёт по РК приложен",
         "Приложите отчёт к сделке")(_file_check("report", "отчёта"))


# ── Проверить нечем: заявлено, но не реализуемо сегодня ──────────────────────
# Эти три НЕ заглушки «на потом»: они честно отвечают «неизвестно» с причиной, и
# причина видна человеку на карточке. Молчаливое отсутствие было бы хуже — требование
# просто не показывалось бы, и никто не знал бы, что его никто не проверяет.

@register("edo_sent", "Документы ушли в Диадок",
          "Отправьте документы через Диадок")
def _edo_sent(c: Ctx) -> Result:
    return _unknown("связи документа Диадока со сделкой в системе нет")


@register("ord_acts_sent", "Акты поданы в ЕРИР",
          "Подайте акты в ОРД")
def _ord_acts_sent(c: Ctx) -> Result:
    return _unknown("подача актов в ОРД не построена")


@register("payment_received", "Оплата поступила",
          "Проверьте поступление в дебиторке")
def _payment_received(c: Ctx) -> Result:
    return _unknown("моста «сделка → операция» нет, оплата на уровне сделки не читается")


# ── Сделочная применимость ───────────────────────────────────────────────────
# Ключи `applies_when`. Список закрытый и проверяется при СОХРАНЕНИИ разметки: опечатка
# `{"servise": 7}` иначе означала бы «применимо всегда», и требование тихо расползлось бы
# на все услуги. Тот же порядок, что у подстановок в почтовых шаблонах.

SCOPE_KEYS = ("service_id", "self_promo")

# Правила «по свежести сделки» здесь НЕТ и не должно быть (владелец 13.09.2026: «я могу
# создавать сделки с МП за прошлые периоды и переводить их в архив успешных, не надо
# никаких правил по свежести сделки вообще»).
#
# Оно и не нужно: при ВХОДНОЙ адресации сделка, которую заводят задним числом и сразу
# отправляют в «Архив успешных сделок», встречает требования ТОЛЬКО архива — план,
# услугу и период. Стадии, через которые она не проходила, ничего не спрашивают, потому
# что в них не входили. Дата в условии применимости лишь дублировала бы это устройство
# и добавляла границу, которая рано или поздно поедет.


def valid_scope(applies_when) -> bool:
    """Условие применимости обязано быть ОБЪЕКТОМ либо пустым.

    Колонка `applies_when` — jsonb, и она примет строку, число и массив. Прилететь такое
    может ручной правкой в базе или будущим экраном настройки; до 13.09.2026 это роняло
    весь список требований целиком (`'str' object has no attribute 'items'`), то есть
    одна испорченная строка разметки выключала карточку сделки."""
    return applies_when is None or isinstance(applies_when, dict)


def scope_matches(applies_when: Optional[dict], deal) -> bool:
    """Пусто — применимо всегда. Несколько ключей — И (все должны сойтись).

    Испорченное условие (не объект) НЕ применяется — но и не молчит: `evaluate` показывает
    такую строку отдельным исходом «неизвестно» с причиной. Тихо снять требование было бы
    хуже: разметка выглядела бы рабочей, а проверка не срабатывала."""
    if not valid_scope(applies_when):
        return False
    if not applies_when:
        return True
    for key, want in applies_when.items():
        if key not in SCOPE_KEYS:
            # Неизвестный ключ НЕ игнорируем: иначе опечатка расширила бы применимость.
            return False
        if key == "service_id" and (deal.service_id or None) != want:
            return False
        if key == "self_promo" and bool(getattr(deal, "is_self_promo", False)) != bool(want):
            return False
    return True


def unknown_scope_keys(applies_when: Optional[dict]) -> list:
    """Для проверки разметки при сохранении."""
    if not valid_scope(applies_when):
        return ["<условие не объект>"]
    return [k for k in (applies_when or {}) if k not in SCOPE_KEYS]


# ── Прогон ───────────────────────────────────────────────────────────────────

@dataclass
class Line:
    """Одна строка списка на карточке."""
    key: str
    title: str
    hint: str
    is_blocking: bool
    where: str = ""
    link: str = ""
    result: Result = field(default_factory=lambda: Result(UNKNOWN, ""))


def evaluate(db, deal, rows) -> list:
    """Считает требования `rows` (строки sales_stage_checks) для сделки.

    Неприменимые по `applies_when` отсеиваются здесь и до проверки не доходят вовсе —
    их функции незачем звать. Неизвестный `check_key` (разметку завели, функцию не
    написали) отдаётся как «неизвестно» с причиной, а не пропускается молча."""
    ctx = Ctx(db, deal)
    out = []
    for r in rows:
        if not valid_scope(r.applies_when):
            # Не пропускаем молча: испорченное условие означает, что требование не
            # проверяется, и узнать об этом надо на экране, а не по отсутствию отказа.
            out.append(Line(key=r.check_key, title=r.check_key, hint="",
                            is_blocking=False,
                            result=_unknown("условие применимости испорчено — не объект")))
            continue
        if not scope_matches(r.applies_when, deal):
            continue
        chk = REGISTRY.get(r.check_key)
        if chk is None:
            out.append(Line(key=r.check_key, title=r.check_key,
                            hint="", is_blocking=False,
                            result=_unknown("проверки с таким именем нет в реестре")))
            continue
        out.append(Line(key=chk.key, title=chk.title, hint=r.hint or chk.hint,
                        is_blocking=bool(r.is_blocking),
                        where=chk.where, link=chk.link, result=chk.fn(ctx)))
    return out


def blockers(lines) -> list:
    """Строки, запирающие переход. Только `is_blocking` И исход «не сделано»."""
    return [ln for ln in lines if ln.is_blocking and ln.result.blocks]
