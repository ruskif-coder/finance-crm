# -*- coding: utf-8 -*-
"""Шапка и суммы медиаплана → сделка (владелец 08.09.2026).

Аккаунты жаловались: правишь медиаплан, а сделка остаётся прежней. Разбор показал, что
это не поломка — из плана в сделку ехало ровно одно поле, имя. Рекламодатель, агентство,
бренд, плательщик, период и сумма не ехали никогда. Замер на проде: из 39 пар
план↔сделка сумма расходилась во ВСЕХ 39, бренд в 9, рекламодатель в 3, агентство в 1.

Спор «кто хозяин поля» снят отдельно: Битрикс больше не источник, источник — наша
система. Отсюда четыре свойства, которые держит этот прибор:

1. заполненное поле плана переезжает в сделку;
2. ПУСТОЕ поле плана сделку не чистит — «стёр в плане» и «убери из сделки» разные
   намерения, а второе руками не вернуть;
3. занятого ответственного не перезаписываем: от `account_manager_id` зависит область
   видимости «свои», и молчаливая замена выдернула бы сделку из чужого списка;
4. записанное поле помечается строкой override — иначе ручная кнопка «⟳ Обновить из
   Битрикса» (осталась за владельцем) вернёт битриксовые значения поверх наших.
"""
from datetime import date
from types import SimpleNamespace

import pytest

import app.ad.models           # noqa: F401
import app.launch_prep.models  # noqa: F401
import app.ord.models          # noqa: F401  — мапперы, готча ORM (см. test_mp_deal_title)
from app.database import SessionLocal
from app.routers import media_plans as mp
from app.sales.models import (SalesDeal, SalesDealFieldOverride, SalesMediaPlan,
                              SalesRep)

PREFIX = 'MPFIELDStest'
_USER = SimpleNamespace(id=None, name='тест',
                        role=SimpleNamespace(key='admin', is_master=True))


def _clean(s):
    # Журнал чистим тоже: перенос ПИШЕТ строку действия, и без этой уборки каждый прогон
    # оставлял бы в «Журнале действий» записи о сделках, которых уже нет (28 таких
    # накопилось за один день, пока строки не было).
    from app.models import AuditLog
    for d in s.query(SalesDeal).filter(SalesDeal.bitrix_id.like(f'{PREFIX}%')).all():
        s.query(AuditLog).filter(AuditLog.entity_type == 'sales_deal',
                                 AuditLog.entity_id == d.id).delete(synchronize_session=False)
        s.query(SalesMediaPlan).filter(SalesMediaPlan.deal_id == d.id).delete(
            synchronize_session=False)
        s.query(SalesDealFieldOverride).filter(
            SalesDealFieldOverride.deal_id == d.id).delete(synchronize_session=False)
        s.delete(d)
    s.commit()


@pytest.fixture
def db():
    s = SessionLocal()
    # Чистим И до, И после: упавший прогон иначе оставит мусор, на котором следующий
    # посчитает не то.
    _clean(s)
    yield s
    _clean(s)
    s.close()


_seq = [0]


def _pair(db, deal_kw=None, plan_kw=None):
    _seq[0] += 1
    d = SalesDeal(bitrix_id=f'{PREFIX}-{_seq[0]}', title='сделка', **(deal_kw or {}))
    db.add(d)
    db.flush()
    p = SalesMediaPlan(version=1, title='план', deal_id=d.id, **(plan_kw or {}))
    db.add(p)
    db.flush()
    p.group_id = p.id
    db.commit()
    return d, p


def _some_ids(db):
    """Реальные id справочников со стенда — FK не позволяют выдумать числа."""
    row = (db.query(SalesDeal.advertiser_id, SalesDeal.brand_id, SalesDeal.agency_id)
           .filter(SalesDeal.advertiser_id.isnot(None), SalesDeal.brand_id.isnot(None),
                   SalesDeal.agency_id.isnot(None)).first())
    if not row:
        pytest.skip('на стенде нет сделки с заполненными справочниками')
    return row


def test_header_and_amounts_reach_the_deal(db):
    """Ровно то, на что жаловались аккаунты: сохранили план — сделка изменилась."""
    adv, brand, agency = _some_ids(db)
    deal, plan = _pair(db, plan_kw={'advertiser_id': adv, 'brand_id': brand,
                                    'agency_id': agency, 'period': '2026-09',
                                    'amount_net': 850000.0, 'amount_gross': 1037000.0})
    mp._sync_deal_from_plan(db, plan, _USER)
    db.commit()
    db.refresh(deal)
    assert (deal.advertiser_id, deal.brand_id, deal.agency_id) == (adv, brand, agency)
    assert deal.amount == 850000.0 and deal.amount_with_vat == 1037000.0
    assert deal.period_from == date(2026, 9, 1), 'период месяца не стал стартом РК'


def test_empty_plan_field_does_not_clear_the_deal(db):
    """Пустое в плане — не команда «очисти сделку»."""
    adv, brand, _ = _some_ids(db)
    deal, plan = _pair(db, deal_kw={'advertiser_id': adv, 'brand_id': brand})
    mp._sync_deal_from_plan(db, plan, _USER)
    db.commit()
    db.refresh(deal)
    assert (deal.advertiser_id, deal.brand_id) == (adv, brand), \
        'сделку вычистили пустым планом'


def test_busy_account_manager_is_not_overwritten(db):
    """Занятого ответственного не трогаем — за ним стоит область видимости «свои»."""
    rep = db.query(SalesRep).filter(SalesRep.user_id.isnot(None)).first()
    if not rep:
        pytest.skip('на стенде нет профиля ответственного с учёткой')
    other = db.query(SalesRep).filter(SalesRep.id != rep.id).first()
    if not other:
        pytest.skip('нужен второй профиль ответственного')
    deal, plan = _pair(db, deal_kw={'account_manager_id': other.id},
                       plan_kw={'account_manager_id': rep.user_id})
    mp._sync_deal_from_plan(db, plan, _USER)
    db.commit()
    db.refresh(deal)
    assert deal.account_manager_id == other.id, 'ответственный сделки перезаписан планом'


def test_written_fields_are_shielded_from_the_bitrix_button(db):
    """Каждое записанное поле, которое трогает синхронизация, закрыто строкой override.

    Без этого один клик по «⟳ Обновить из Битрикса» вернёт битриксовые значения поверх
    наших — и жалоба «изменения не сохраняются» вернётся вместе с ними.
    """
    adv, brand, _ = _some_ids(db)
    deal, plan = _pair(db, plan_kw={'advertiser_id': adv, 'brand_id': brand,
                                    'amount_net': 100.0, 'amount_gross': 122.0})
    mp._sync_deal_from_plan(db, plan, _USER)
    db.commit()
    shielded = {o.field_name for o in db.query(SalesDealFieldOverride)
                .filter(SalesDealFieldOverride.deal_id == deal.id).all()}
    assert {'advertiser_id', 'brand_id', 'amount', 'amount_with_vat'} <= shielded, \
        f'поля не закрыты от кнопки синхронизации: {shielded}'


def test_repeat_call_changes_nothing(db):
    """Идемпотентность: функция зовётся на КАЖДОМ сохранении плана."""
    adv, brand, _ = _some_ids(db)
    deal, plan = _pair(db, plan_kw={'advertiser_id': adv, 'brand_id': brand,
                                    'amount_net': 100.0, 'amount_gross': 122.0})
    mp._sync_deal_from_plan(db, plan, _USER)
    db.commit()
    before = (deal.advertiser_id, deal.brand_id, deal.amount, deal.title)
    mp._sync_deal_from_plan(db, plan, _USER)
    db.commit()
    db.refresh(deal)
    assert (deal.advertiser_id, deal.brand_id, deal.amount, deal.title) == before


def test_a_plan_calculated_to_zero_reaches_the_deal(db):
    """Ноль — это цена, а не отсутствие цены.

    Условие переноса было «истинно», и посчитанный в ноль план (услуга со стопроцентной
    скидкой) сделку не трогал: в базе оставалась сумма Битрикса. Жалоба владельца
    15.09.2026 по сделке MHNZUT — 372 000 при нулевом плане. Пара к этому прибору —
    `test_mp_amounts.test_a_calculated_plan_worth_zero_wins_over_bitrix`, там то же
    различие на стороне показа.
    """
    deal, plan = _pair(db, deal_kw={'amount': 372000.0, 'amount_with_vat': 453840.0},
                       plan_kw={'amount_net': 0.0, 'amount_gross': 0.0})
    mp._sync_deal_from_plan(db, plan, _USER)
    db.commit()
    db.refresh(deal)
    assert deal.amount == 0.0, 'нулевой план не доехал — сделка осталась с суммой Битрикса'
    assert deal.amount_with_vat == 0.0


def test_an_uncalculated_plan_still_does_not_touch_the_amount(db):
    """Обратный край: суммы у плана НЕТ (NULL) — сделку не трогаем.
    «Не посчитан» и «посчитан в ноль» это разные состояния."""
    deal, plan = _pair(db, deal_kw={'amount': 372000.0},
                       plan_kw={'amount_net': None, 'amount_gross': None})
    mp._sync_deal_from_plan(db, plan, _USER)
    db.commit()
    db.refresh(deal)
    assert deal.amount == 372000.0


def test_inline_edit_from_the_registry_also_reaches_the_deal():
    """Правка МП из реестра (PATCH) обязана доезжать до сделки.

    Половина жалобы «медиаплан не всегда обновляет сделку»: `patch_media_plan` менял
    ровно те поля, которые перенос и возит, — рекламодателя, бренд, агентство,
    плательщика, период, название, — и переноса не звал. Со стороны аккаунта: одно
    и то же поле, исправленное в конструкторе, доходит, а в реестре — нет.

    Прибор смотрит на ИСХОДНИК, а не на поведение: поднять реальный PATCH здесь значит
    втащить право, own-scope и сессию запроса, а вопрос ровно один — зовётся ли перенос.
    """
    import inspect
    src = inspect.getsource(mp.patch_media_plan)
    assert "_sync_deal_from_plan" in src, (
        "правка МП из реестра не доезжает до сделки")
    assert src.index("_sync_deal_from_plan") < src.index("db.commit()"), (
        "перенос зовётся после коммита — его записи не сохранятся")


def test_the_resync_script_has_a_real_dry_run():
    """Сухой прогон разового переноса обязан быть сухим.

    Готча, на которой скрипт уже соврал 15.09.2026: перенос в конце зовёт `log_action`,
    а тот делает СВОЙ `db.commit()`. Схема «позвать и в конце откатить» на этом не
    работает — к моменту отката всё записано, и «сухой прогон» оказывается боевым
    (на стенде так и вышло: 19 сделок доехали до состояния плана без команды).

    Настоящий откат делается снаружи: сессия внутри внешней транзакции с
    `join_transaction_mode="create_savepoint"`, тогда внутренний commit закрывает
    только savepoint.
    """
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "scripts" / "2026-09-15_resync_deals_from_plans.py").read_text(encoding="utf-8")
    assert 'join_transaction_mode="create_savepoint"' in src, (
        "у скрипта нет настоящего отката — его сухой прогон пишет в базу")
    assert "db.rollback()" not in src, (
        "откат сессии здесь бесполезен: log_action уже сделал commit")
