# -*- coding: utf-8 -*-
"""Приборы на две таблицы разметки, которые сутки простояли без единого читателя.

`sales_stage_services` (применимость стадии к услуге) и `sales_stage_blocks` (видимость
блоков карточки) были созданы миграцией 13.09.2026 вместе с моделями — и НЕ ЧИТАЛИСЬ
ниоткуда. Пустая таблица при этом неотличима от «механизм есть, разметки пока нет», и
обнаружил это обход агентом, а не экран и не тест.

Поэтому здесь проверяется в первую очередь то, что механизм ВООБЩЕ ПОДКЛЮЧЁН: разметка
меняет результат. Если однажды чтение снова отвалится, эти тесты покраснеют, а не
промолчат.
"""
import pytest
from sqlalchemy import text

from app.database import SessionLocal
from app.sales import stage_scope
from app.sales.catalog import Catalog


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


class _Deal:
    def __init__(self, stage_id=None, service_id=None):
        self.id = -1
        self.our_stage_id = stage_id
        self.service_id = service_id
        self.ord_initial_contract_id = None
        self.ord_final_contract_id = None
        self.traffic_brief = None


# ── Применимость стадии к услуге ─────────────────────────────────────────────

def test_no_rows_means_every_service_passes():
    """Нет разметки — стадия применима ко всем. Накат миграции не должен молча
    выкинуть половину лестницы у всех услуг сразу."""
    assert stage_scope.stage_applies(1, _Deal(service_id=7), {}) is True


def test_markup_actually_filters():
    """Главный прибор: разметка МЕНЯЕТ результат.

    Если чтение таблицы снова отвалится, этот тест покраснеет — в отличие от пустой
    таблицы, которая молчит одинаково и когда механизм работает, и когда его нет.
    """
    marks = {5: {28}}
    assert stage_scope.stage_applies(5, _Deal(service_id=28), marks) is True
    assert stage_scope.stage_applies(5, _Deal(service_id=99), marks) is False
    assert stage_scope.stage_applies(6, _Deal(service_id=99), marks) is True


def test_deal_without_a_service_passes_every_stage():
    """Сделка без услуги идёт полной лестницей.

    «Услуга не определена» — это незнание, а не основание выкинуть сделку из части пути:
    таких на 13.09.2026 двести семнадцать, и молчаливая потеря стадий у них выглядела бы
    как сломанный каталог."""
    assert stage_scope.stage_applies(5, _Deal(service_id=None), {5: {28}}) is True


def test_next_skips_a_stage_that_is_not_for_this_service(db):
    """Неприменимая стадия ПРОСКАКИВАЕТСЯ, а не запирает лестницу."""
    cat = Catalog(db)
    if len(cat.flow) < 3:
        pytest.skip("каталог короче трёх стадий")
    first, second, third = cat.flow[0], cat.flow[1], cat.flow[2]
    deal = _Deal(stage_id=first, service_id=28)

    assert stage_scope.next_for(deal, cat, {}).id == second
    # вторая стадия «только для чужой услуги» → следующей становится третья
    assert stage_scope.next_for(deal, cat, {second: {99}}).id == third


# ── Видимость блоков карточки ────────────────────────────────────────────────

def test_unmarked_block_is_always_visible(db):
    """Блок без разметки виден всегда: новый блок не должен пропасть оттого, что его
    забыли разметить."""
    cat = Catalog(db)
    vis = stage_scope.visible_blocks(db, _Deal(stage_id=cat.flow[0]), cat)
    assert vis["head"] is True
    assert set(vis) == set(stage_scope.BLOCK_KEYS), "выдача обязана быть ПОЛНОЙ"


def test_block_appears_from_its_stage_and_never_disappears(db):
    """Появился — больше не исчезает.

    Иначе движение вперёд прятало бы уже заполненное, и это читается как «данные
    потерялись», а не как «блок не для этой стадии»."""
    cat = Catalog(db)
    marked = db.execute(text(
        "SELECT stage_id, block_key FROM sales_stage_blocks LIMIT 1")).first()
    if not marked:
        pytest.skip("разметка блоков не засеяна")
    stage_id, key = marked
    order = {s.id: i for i, s in enumerate(cat.stages)}
    pos = order[stage_id]

    earlier = next((s.id for s in cat.stages if order[s.id] < pos), None)
    later = next((s.id for s in cat.stages if order[s.id] > pos), None)

    if earlier is not None:
        assert stage_scope.visible_blocks(db, _Deal(stage_id=earlier), cat)[key] is False, (
            "блок виден раньше своей стадии — разметка не читается")
    assert stage_scope.visible_blocks(db, _Deal(stage_id=stage_id), cat)[key] is True
    if later is not None:
        assert stage_scope.visible_blocks(db, _Deal(stage_id=later), cat)[key] is True, (
            "блок исчез после своей стадии")


def test_a_block_with_content_is_never_hidden(db):
    """Непустое не прячем НИКОГДА.

    Спрятанные данные не просто невидимы — их невозможно найти: человек считает, что их
    нет, и заводит второй раз. Берём живую сделку с файлами и ставим её на самую раннюю
    стадию: блок документов обязан остаться видимым.
    """
    from app.sales.models import SalesDeal
    cat = Catalog(db)
    row = db.execute(text("""
        SELECT deal_id FROM sales_deal_files GROUP BY deal_id LIMIT 1""")).first()
    if not row:
        pytest.skip("на стенде нет сделок с файлами")
    deal = db.query(SalesDeal).filter(SalesDeal.id == row[0]).first()
    deal.our_stage_id = cat.flow[0]          # откатываем в начало лестницы (без commit)
    vis = stage_scope.visible_blocks(db, deal, cat)
    assert vis["docs"] is True, "блок с документами спрятан — данные стали недостижимы"


def test_docs_counts_plan_and_released_annex_not_only_files(db):
    """«Непустое» у документов — это НЕ только загруженные файлы.

    Блок собирает три разных вещи: файлы, медиаплан и ДС. Причём у выпущенной ДС файла
    нет вовсе — она считается готовой по номеру приложения. Пока непустота мерилась одной
    таблицей `sales_deal_files`, сделка с планом и выпущенной ДС числилась пустой, и
    правило «непустое не прячем» её не защищало: спрятанным оказывалось ровно то, что уже
    собрано. Прибор берёт такую сделку — с планом, но БЕЗ файлов — и требует блок видимым.
    """
    from app.sales.models import SalesDeal
    cat = Catalog(db)
    row = db.execute(text("""
        SELECT p.deal_id FROM sales_media_plans p
         WHERE p.deal_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM sales_deal_files f WHERE f.deal_id = p.deal_id)
           AND EXISTS (SELECT 1 FROM sales_deals d WHERE d.id = p.deal_id)
         LIMIT 1""")).first()
    if not row:
        pytest.skip("на стенде нет сделки с планом и без файлов")
    deal = db.query(SalesDeal).filter(SalesDeal.id == row[0]).first()
    deal.our_stage_id = cat.flow[0]
    # Разметка на ПОСЛЕДНЮЮ стадию: без правила «непустое не прячем» блок был бы скрыт.
    db.execute(text("INSERT INTO sales_stage_blocks (stage_id, block_key) VALUES (:s, 'docs')"
                    " ON CONFLICT DO NOTHING"), {"s": cat.flow[-1]})
    assert stage_scope.visible_blocks(db, deal, cat)["docs"] is True, (
        "сделка с медиапланом сочтена пустой — непустота меряется одними файлами")


def test_blocks_markup_is_one_row_per_block(db):
    """Экран настройки показывает ДЕЙСТВУЮЩЕЕ правило, а не содержимое таблицы.

    Строк на блок может быть несколько, но читается самая ранняя — остальные не значат
    ничего. Если бы экран показывал их все, человек правил бы строки без эффекта.
    """
    cat = Catalog(db)
    if len(cat.stages) < 2:
        pytest.skip("в каталоге меньше двух стадий")
    early, late = cat.stages[0].id, cat.stages[-1].id
    db.execute(text("DELETE FROM sales_stage_blocks WHERE block_key = 'campaign'"))
    for sid in (late, early):
        db.execute(text("INSERT INTO sales_stage_blocks (stage_id, block_key)"
                        " VALUES (:s, 'campaign')"), {"s": sid})

    out = stage_scope.blocks_markup(db, cat)
    assert [b["key"] for b in out] == list(stage_scope.BLOCK_KEYS), "выдача обязана быть полной"
    row = next(b for b in out if b["key"] == "campaign")
    assert row["stage_id"] == early, "показана не та стадия, по которой блок реально виден"
    assert row["label"], "блок без подписи — экран покажет служебный ключ"


def test_save_blocks_markup_replaces_and_none_means_always(db):
    """Сохранение переписывает разметку целиком, а пустая стадия означает «виден всегда».

    Разница важна: строка со стадией и отсутствие строки — разные утверждения, и второе
    обязано получаться именно очисткой, а не записью какой-нибудь нулевой стадии.
    """
    cat = Catalog(db)
    stage_scope.save_blocks_markup(db, {"ord": cat.stages[0].id, "docs": None})
    out = {b["key"]: b["stage_id"] for b in stage_scope.blocks_markup(db, cat)}
    assert out["ord"] == cat.stages[0].id
    assert out["docs"] is None
    assert out["creatives"] is None, "прежняя разметка не была переписана"
    assert stage_scope.visible_blocks(db, _Deal(stage_id=cat.stages[0].id), cat)["docs"] is True
