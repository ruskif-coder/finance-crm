"""Сделка конвейера обязана совпадать со своей строкой плана, а строка — со своим планом.

Проверка на боевых данных, а не на выдуманных: оба расхождения ниже уже случились, и ни
одно не проявилось как ошибка — всё работало, просто показывало чужое.

ЧТО СЛУЧИЛОСЬ (26.08.2026). Строку плана переназначили с одного рекламодателя на другого
уже после того, как конвейер сделал из неё сделки. Повторный прогон переписал этим сделкам
НАЗВАНИЕ по новой строке, но не переписал advertiser_id/brand_id — в ветке `if existing:`
их просто не было среди обновляемых полей. Получилась сделка, которая называется одним, а
ссылается на другое; карточка и реестр показывают имя по ссылке, то есть чужого
рекламодателя. Нашёл это человек глазами, спустя двенадцать дней.

Вторым слоем: сама строка лежала в плане ДРУГОГО рекламодателя. Экран годового
планирования группирует по рекламодателю СТРОКИ, поэтому расхождение заголовка плана со
своей же строкой на экране не видно вообще никак.

ПОЧЕМУ ЭТО ТЕСТ, А НЕ ПРОВЕРКА ПРИ ЗАПИСИ. Запись чинится в одном месте (year_plan.py уже
починен), но испортить связь можно и разовым скриптом, и правкой руками в psql, и будущим
импортом. Тест смотрит на результат, а не на путь, и потому переживает появление новых
путей записи.

У одного рекламодателя МОЖЕТ быть несколько планов на год — это предусмотрено (см.
year_plan.py, выбор заголовка «только если план один»). Чего не может быть, так это
строки, живущей в плане чужого рекламодателя.
"""
import pytest

from app.database import SessionLocal
from app.sales.models import SalesDeal, SalesYearPlan, SalesYearPlanLine


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_generated_deal_matches_its_plan_line(db):
    """Сделка конвейера ссылается на того же рекламодателя и бренд, что её строка.

    Название сделки собирается из строки плана, поэтому расхождение означает буквально
    «называется одним, ссылается на другое» — и увидеть это можно только сверив две
    записи, чего никто не делает.
    """
    rows = (db.query(SalesDeal.id, SalesDeal.code,
                     SalesDeal.advertiser_id, SalesYearPlanLine.advertiser_id.label('la'),
                     SalesDeal.brand_id, SalesYearPlanLine.brand_id.label('lb'))
              .join(SalesYearPlanLine, SalesYearPlanLine.id == SalesDeal.year_plan_line_id)
              .all())
    assert rows, "нет сделок, порождённых конвейером — проверять нечего, но и молчать нельзя"

    bad = [f"{r.code or r.id}: рекламодатель {r.advertiser_id}≠{r.la}, бренд {r.brand_id}≠{r.lb}"
           for r in rows if r.advertiser_id != r.la or r.brand_id != r.lb]
    assert not bad, (
        "сделка конвейера разошлась со своей строкой плана — её название собрано из "
        "строки, а ссылки остались от прежней:\n  " + "\n  ".join(bad)
    )


def test_plan_line_belongs_to_its_own_plan_advertiser(db):
    """Строка плана лежит в плане своего же рекламодателя.

    Несколько планов у одного рекламодателя — норма. Строка в чужом плане — нет: экран
    группирует по рекламодателю строки, и заголовок чужого плана прилипает к ним молча.
    """
    rows = (db.query(SalesYearPlanLine.id, SalesYearPlanLine.advertiser_id,
                     SalesYearPlan.id.label('pid'), SalesYearPlan.advertiser_id.label('pa'))
              .join(SalesYearPlan, SalesYearPlan.id == SalesYearPlanLine.plan_id)
              .all())

    bad = [f"строка {r.id} ({r.advertiser_id}) лежит в плане {r.pid} ({r.pa})"
           for r in rows if r.advertiser_id != r.pa]
    assert not bad, (
        "строка плана принадлежит чужому рекламодателю:\n  " + "\n  ".join(bad)
    )


# ── дошедшая сделка не обновляется конвейером ────────────────────────────────
def test_frozen_reasons_cover_orange_green_and_lost():
    """Правило владельца 27.08.2026: ушла со стадии планирования — план ей не хозяин.

    Заморозка ВЫЧИСЛЯЕТСЯ из стадии, а не хранится: ручной замок `locks` висит на паре
    «строка × месяц», а в пяти ячейках из тринадцати лежит по две сделки — заморозив
    месяц, остановили бы и ту, что ещё плановая.
    """
    from types import SimpleNamespace
    from app.routers.year_plan import _deal_frozen

    def stage(**kw):
        base = dict(money_layer=None, is_lost=False, is_terminal=False)
        base.update(kw)
        return SimpleNamespace(**base)

    stages = {
        1: stage(money_layer='планируемые'),
        2: stage(money_layer='реализуемые'),
        3: stage(money_layer='фактические'),
        4: stage(is_lost=True),
        5: stage(is_terminal=True, money_layer='фактические'),
    }
    d = lambda sid: SimpleNamespace(our_stage_id=sid)

    assert _deal_frozen(d(1), stages) is None, "плановая сделка обновляется — в этом смысл конвейера"
    assert _deal_frozen(d(2), stages) == 'в работе'
    assert _deal_frozen(d(3), stages) == 'в работе'
    assert _deal_frozen(d(4), stages) == 'сделка не случилась', (
        "провал — тоже заморозка: пустая ячейка приглашает пересобрать её заново")
    assert _deal_frozen(d(5), stages) == 'в работе'
    assert _deal_frozen(SimpleNamespace(our_stage_id=None), stages) is None


def test_conveyor_checks_the_stage_before_rewriting():
    """Пин на саму проверку: ветка обновления обязана спрашивать заморозку ДО перезаписи.

    Она не только правит поля, но и УДАЛЯЕТ медиапланы сделки (`db.delete(mp)`), пересобирая
    их заново. Пропусти она сделку в работе — исчезли бы ручные правки медиаплана, и
    заметил бы это аккаунт, открыв сделку, а не тест.
    """
    import inspect
    from app.routers import year_plan

    src = inspect.getsource(year_plan.create_deals)
    assert '_deal_frozen' in src, "конвейер пишет по существующей сделке без проверки стадии"
    before_delete = src.index('_deal_frozen') < src.index('db.delete(mp)')
    assert before_delete, "проверка обязана стоять ДО удаления медиапланов"

    preview = inspect.getsource(year_plan.create_deals_preview)
    assert '_deal_frozen' in preview, (
        "диф обязан показывать «в работе» отдельно: иначе человек жмёт «создать», "
        "ожидая пересборки, и не получает её без объяснения")
