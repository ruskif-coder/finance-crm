# -*- coding: utf-8 -*-
"""Приборы реестра проверок для разметки стадий (`app/sales/stage_checks.py`).

Стерегут не расчёты, а КОНТРАКТ — те решения, нарушение которых не падает и не краснеет:

· «неизвестно» не запирает движение (иначе недостроенный мост заморозит конвейер);
· ноль применимых у веерной проверки — не «выполнено», а «неприменимо»;
· неизвестный ключ применимости НЕ расширяет её до «всегда»;
· демо-строки не считаются фактом (иначе стенд зелёный, а прод пустой);
· у каждой проверки есть человеческая подпись и подсказка.
"""
import pytest
from sqlalchemy import text

from app.database import SessionLocal
from app.sales import stage_checks as sc


# ── 1. Контракт исходов ──────────────────────────────────────────────────────

def test_only_not_yet_blocks():
    """Запирает движение ТОЛЬКО «не сделано».

    Это главное решение всего механизма. Если запирать начнёт и «неизвестно», три
    проверки, которым сегодня нечем считать (Диадок, акты ОРД, оплата), намертво
    закроют последние стадии — и сделку станет невозможно закрыть вообще.
    """
    assert sc.Result(sc.NOT_YET).blocks is True
    for state in (sc.OK, sc.UNKNOWN, sc.NA):
        assert sc.Result(state).blocks is False, f"{state} не должен запирать"


def test_blockers_needs_both_flag_and_verdict():
    """В список мешающих попадает только пересечение: «запрет» И «не сделано»."""
    mk = lambda blocking, state: sc.Line(  # noqa: E731
        key="k", title="t", hint="h", is_blocking=blocking, result=sc.Result(state))
    lines = [mk(True, sc.NOT_YET), mk(False, sc.NOT_YET),
             mk(True, sc.UNKNOWN), mk(True, sc.OK)]
    assert len(sc.blockers(lines)) == 1


def test_unknown_always_carries_a_reason():
    """«Неизвестно» без причины неотличимо от недоделанной проверки.

    На карточке человек видит строку без ответа на вопрос «почему» и идёт выяснять к
    нам — вместо того чтобы прочитать «моста сделка→операция нет».
    """
    ctx = object()
    for key in ("edo_sent", "ord_acts_sent", "payment_received"):
        r = sc.REGISTRY[key].fn(ctx)
        assert r.state == sc.UNKNOWN
        assert r.detail.strip(), f"{key}: «неизвестно» без причины"


# ── 2. Веер ──────────────────────────────────────────────────────────────────

def test_fan_with_nothing_applicable_is_not_done():
    """Ноль применимых — «неприменимо», а не «выполнено».

    Сказать «согласовано 0 из 0» значит объявить сделанным то, чего не существует:
    сделка без площадок проехала бы проверку согласования насквозь.
    """
    assert sc._fan(0, 0, [], "площадок").state == sc.NA


def test_fan_reports_who_blocks():
    """Веер обязан называть мешающих: «не согласовано» без имён нечего делать."""
    r = sc._fan(3, 5, ["Икс", "Игрек"], "пар")
    assert r.state == sc.NOT_YET and r.detail == "3 из 5"
    assert r.blockers == ("Икс", "Игрек")


def test_fan_done_when_all_pass():
    assert sc._fan(2, 2, [], "комплектов").state == sc.OK


# ── 3. Применимость ──────────────────────────────────────────────────────────

class _Deal:
    def __init__(self, service_id=None, is_self_promo=False):
        self.service_id = service_id
        self.is_self_promo = is_self_promo


def test_empty_scope_applies_always():
    assert sc.scope_matches(None, _Deal()) is True
    assert sc.scope_matches({}, _Deal()) is True


def test_scope_matches_service_and_flag():
    d = _Deal(service_id=7, is_self_promo=True)
    assert sc.scope_matches({"service_id": 7}, d) is True
    assert sc.scope_matches({"service_id": 8}, d) is False
    assert sc.scope_matches({"self_promo": True}, d) is True
    assert sc.scope_matches({"service_id": 7, "self_promo": False}, d) is False


def test_unknown_scope_key_does_not_widen():
    """Опечатка в ключе НЕ должна означать «применимо всегда».

    Иначе `{"servise": 7}` тихо расползлось бы на все услуги: требование сработало бы
    там, где его не задумывали, и заметить это было бы нечем.
    """
    d = _Deal(service_id=7)
    assert sc.scope_matches({"servise": 7}, d) is False
    assert sc.unknown_scope_keys({"servise": 7, "service_id": 7}) == ["servise"]


def test_self_promo_lifts_only_the_initial_contract():
    """Самореклама снимает ТОЛЬКО изначальный договор ОРД.

    ЕРИД она не снимает: он обязан быть в любом случае, отличается лишь способ
    получения. Требование, снятое флагом, дало бы сделки без ЕРИД — и узнали бы мы об
    этом от регулятора.
    """
    class _Ctx:
        deal = _Deal(is_self_promo=True)
        sets = []
    assert sc.REGISTRY["ord_initial_contract"].fn(_Ctx()).state == sc.NA

    # ЕРИД проверяем С КОМПЛЕКТОМ: без комплектов он «неприменим» по их отсутствию,
    # и такой ответ ничего не сказал бы про флаг саморекламы.
    class _Set:
        no, erid = 1, None

    class _Ctx2(_Ctx):
        sets = [_Set()]
    assert sc.REGISTRY["erid_issued"].fn(_Ctx2()).state == sc.NOT_YET, (
        "самореклама сняла требование ЕРИД — так нельзя, он обязан быть всегда")


def test_there_is_no_freshness_rule():
    """Правила «по свежести сделки» в механизме НЕТ — и это решение, а не пропуск.

    Владелец 13.09.2026: «я могу создавать сделки с МП за прошлые периоды и переводить их
    в архив успешных, не надо никаких правил по свежести сделки вообще».

    До этого правило было дважды: сперва движущейся границей от текущего месяца (сделка
    теряла требования первого числа, без события), потом фиксированной датой. Обе
    редакции оказались лишними: при ВХОДНОЙ адресации сделка, заведённая задним числом и
    отправленная сразу в архив, встречает требования только архива — устройство уже
    решает задачу, а дата добавляла границу, которая рано или поздно поедет.

    Прибор стережёт, чтобы такое условие не вернулось третий раз.
    """
    assert "backfilled" not in sc.SCOPE_KEYS
    assert "past_period" not in sc.SCOPE_KEYS
    assert not hasattr(sc, "is_backfilled")
    assert not hasattr(sc, "is_past_period")
    assert not hasattr(sc, "BACKFILL_BEFORE")

    # Сделка с периодом годовой давности не отличается от свежей: условия смотрят на
    # услугу и флаги, а не на даты.
    from datetime import date

    class D:
        service_id = 28
        is_self_promo = False
        period_to = date(2025, 5, 31)
    old = D()
    fresh = D()
    fresh.period_to = date(2026, 12, 31)
    assert sc.scope_matches({"service_id": 28}, old) is True
    assert sc.scope_matches({"service_id": 28}, fresh) is True


# ── 4. Реестр как таковой ────────────────────────────────────────────────────

def test_every_check_has_a_human_title_and_hint():
    """Подпись и подсказка обязательны: строка разметки показывается человеку, и
    служебный ключ вида `ord_acts_sent` на карточке читается как мусор."""
    for key, chk in sc.REGISTRY.items():
        assert chk.title.strip() and chk.title != key, f"{key}: нет подписи"
        assert chk.hint.strip(), f"{key}: нет подсказки «что сделать»"


def test_broken_scope_does_not_crash_the_whole_list():
    """Испорченное условие применимости не роняет список и не молчит.

    Колонка `applies_when` — jsonb, она примет строку, число и массив. До 13.09.2026
    такое значение роняло весь расчёт (`'str' object has no attribute 'items'`), то есть
    ОДНА испорченная строка разметки выключала карточку сделки целиком. Найдено прогоном
    краевых значений, а не тестом на поведение.

    Требование при этом не применяется — но говорит об этом отдельной строкой: тихо
    снятое требование выглядит как рабочая разметка, которая ничего не проверяет.
    """
    for bad in ("строка", [1, 2], 42):
        assert sc.valid_scope(bad) is False
        assert sc.scope_matches(bad, _Deal()) is False
        assert sc.unknown_scope_keys(bad)

    class _Row:
        check_key, applies_when, is_blocking, hint = "payer_set", "мусор", True, None
    lines = sc.evaluate(None, _Deal(), [_Row()])
    assert len(lines) == 1
    assert lines[0].result.state == sc.UNKNOWN
    assert "испорчено" in lines[0].result.detail
    assert lines[0].result.blocks is False, "испорченная разметка не должна запирать"


def test_every_check_says_where_it_is_fixed():
    """У каждой проверки есть МЕСТО, где её чинят.

    Список «чего не хватает» без ответа «куда идти» заставляет человека спрашивать нас —
    и тогда экран не экономит время, а тратит чужое.
    """
    for key, chk in sc.REGISTRY.items():
        assert chk.where.strip(), f"{key}: не сказано, где это чинится"


def test_places_table_has_no_orphans():
    """Таблица мест и реестр не расходятся в обе стороны.

    Лишняя строка означает проверку, которую удалили и забыли убрать отсюда; недостающая
    — проверку без места, которую поймает тест выше.
    """
    assert set(sc.PLACES) == set(sc.REGISTRY), (
        "PLACES и REGISTRY разошлись: "
        f"лишние {sorted(set(sc.PLACES) - set(sc.REGISTRY))}, "
        f"без места {sorted(set(sc.REGISTRY) - set(sc.PLACES))}")


def test_unknown_check_key_is_reported_not_skipped():
    """Разметку завели, функцию не написали — строка обязана сказать об этом.

    Молчаливый пропуск означал бы требование, которое никто не проверяет и о котором
    никто не знает: ровно тот хвост в никуда, которого механизм и должен избегать.
    """
    class _Row:
        check_key, applies_when, is_blocking, hint = "нет_такой", None, True, None
    lines = sc.evaluate(None, _Deal(), [_Row()])
    assert len(lines) == 1
    assert lines[0].result.state == sc.UNKNOWN
    assert "реестре" in lines[0].result.detail


def test_scope_filters_out_before_running_the_check():
    """Неприменимую проверку не зовём вовсе — иначе она полезет в базу без нужды."""
    class _Row:
        check_key, applies_when, is_blocking, hint = "payer_set", {"service_id": 99}, True, None
    assert sc.evaluate(None, _Deal(service_id=1), [_Row()]) == []


# ── 5. Живьём: демо не считается фактом ──────────────────────────────────────

@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


def test_demo_only_fact_is_unknown_not_done(db):
    """Главный прибор против тихого вранья на стенде.

    Демо-строки лежат в `ad_campaign_stat` вместе с боевыми и входят в `OWN` — иначе
    дашборд стенда был бы пустым. Без разделения проверка «факт собран» была бы зелёной
    здесь и пустой на проде, то есть соврала бы ровно там, где её принимают.
    """
    row = db.execute(text("""
        SELECT c.deal_id FROM ad_campaign c
         WHERE EXISTS (SELECT 1 FROM ad_campaign_stat s
                        WHERE s.campaign_id = c.id AND s.source = 'demo')
         LIMIT 1""")).first()
    if not row:
        pytest.skip("на стенде нет РК с демо-фактом")
    from app.sales.models import SalesDeal
    deal = db.query(SalesDeal).filter(SalesDeal.id == row[0]).first()
    r = sc.REGISTRY["fact_collected"].fn(sc.Ctx(db, deal))
    assert r.state == sc.UNKNOWN, f"демо принято за факт: {r.state} / {r.detail}"
    assert "демо" in r.detail


def test_checks_run_on_a_real_deal_without_exploding(db):
    """Все девятнадцать проверок отрабатывают на живой сделке.

    Дешёвый, но не бессмысленный прибор: половина проверок ходит в чужие модули, и
    переименование колонки там ловится здесь, а не на карточке у аккаунта.
    """
    from app.sales.models import SalesDeal
    deal = db.query(SalesDeal).filter(SalesDeal.our_stage_id.isnot(None)).first()
    if not deal:
        pytest.skip("на стенде нет сделок со стадией")
    ctx = sc.Ctx(db, deal)
    for key, chk in sc.REGISTRY.items():
        r = chk.fn(ctx)
        assert r.state in (sc.OK, sc.NOT_YET, sc.UNKNOWN, sc.NA), f"{key}: {r.state}"
