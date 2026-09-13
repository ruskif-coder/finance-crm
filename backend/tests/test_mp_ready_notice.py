# -*- coding: utf-8 -*-
"""Проверенный медиаплан двигает сделку — и говорит об этом сейлзу.

Два правила, и каждое однажды было неверным молча.

ПЕРВОЕ — КУДА двигать. Код брал «следующую стадию за первой». Тогда следующей была
«МП согласование», и переход читался как «план ушёл на визу». 17.08.2026 стадию убрали
из каталога как бюрократию, а этот код не тронули: следующей стала «МП Отправлено», и
проверка плана начала молча объявлять его отправленным клиенту. Такая ошибка не падает
и в данных не видна — сделка просто оказывается на стадию дальше, чем заслужила.

ВТОРОЕ — КТО об этом узнаёт. Отправляет план клиенту сейлз, а событие происходит у
аккаунта. Переход был бесшумным: сделка меняла стадию, сейлз мог заметить это, только
сам зайдя в реестр.

Приборы держат оба: цель перехода определяется ТРЕБОВАНИЕМ плана, а не порядком стадий,
и уведомление уходит ровно один раз — на переходе, а не на каждом сохранении.
"""
from types import SimpleNamespace

import pytest

from app.database import SessionLocal
from app.models import AuditLog, Notification, User
from app.notify.models import NotificationDelivery
# Модели ОРД импортируются ради маппера: у `sales_deals` есть внешний ключ на
# `ord_initial_contracts`, и без их регистрации в метаданных первый же запрос к
# сделке падает на NoReferencedTableError — к правилу отношения не имеющей.
from app.ord import models as _ord_models   # noqa: F401
from app.routers import media_plans as mp
from app.sales.catalog import Catalog
from app.sales.models import SalesDeal, SalesDealStageHistory, SalesMediaPlan, SalesRep

BX = 'test-mp-ready'          # префикс bitrix_id подставных сделок
TITLE = '[тест] mp_ready'     # заголовок подставных планов


# ── 1. Цель перехода: правило, а не порядок ──────────────────────────────────

class _Stage:
    def __init__(self, sid, name, requires):
        self.id, self.name, self.requires_media_plan = sid, name, requires


class _Cat:
    """Каталог, каким он был до 17.08.2026 — с промежуточной «МП согласование»."""
    def __init__(self, stages):
        self.by_id = {s.id: s for s in stages}
        self.flow = [s.id for s in stages]

    def next_of(self, sid):
        return self.by_id[self.flow[self.flow.index(sid) + 1]]


def test_inserted_stage_does_not_capture_the_deal():
    """Вернут промежуточную стадию — сделка всё равно встанет туда, где план обязателен.

    Обе строки ниже про один и тот же каталог: первая показывает, куда двигал старый
    код, вторая — куда двигает правило. Разошлись они ровно в тот день, когда стадию
    убрали, и разойдутся снова, если её вернут.
    """
    cat = _Cat([_Stage(1, 'МП Подготовка', False),
                _Stage(2, 'МП согласование', False),
                _Stage(3, 'МП Отправлено', True)])
    assert cat.next_of(1).name == 'МП согласование'          # как двигал старый код
    assert mp._mp_sent_stage(cat).name == 'МП Отправлено'    # как двигает правило


def test_live_catalog_has_a_target_and_it_lies_ahead():
    """На живом каталоге цель существует, требует план и стоит ПОСЛЕ первой стадии."""
    db = SessionLocal()
    try:
        cat = Catalog(db)
        first, tgt = cat.first(), mp._mp_sent_stage(cat)
        assert tgt is not None, 'в каталоге нет ни одной стадии, требующей медиаплан'
        assert tgt.requires_media_plan
        assert cat.is_before(first.id, tgt.id), (
            f'цель «{tgt.name}» не позже первой стадии «{first.name}» — двигать некуда')
    finally:
        db.close()


# ── 2. Живой прогон: движение и уведомление ──────────────────────────────────

def _purge(db):
    """Убирает своё — и до теста тоже: до ловит мусор упавшего прогона.

    Уборка обязана быть явной: `_advance_deal_on_link` коммитит по дороге
    (через `log_action`), поэтому откатом транзакции следы не убрать.
    """
    db.rollback()
    deals = db.query(SalesDeal).filter(SalesDeal.bitrix_id.like(f'{BX}%')).all()
    dids = [d.id for d in deals]
    # Ищем планы И по сделке, И по заголовку: новая версия наследует сделку, а вот
    # первая редакция этой уборки искала только по `deal_id` — и оставляла в базе
    # версии, у которых он оказывался пустым. Восемь таких строк нашлись в реестре
    # глазами, а не тестом (30.08.2026).
    q = db.query(SalesMediaPlan).filter(SalesMediaPlan.title.like(f'{TITLE}%'))
    if dids:
        from sqlalchemy import or_
        q = db.query(SalesMediaPlan).filter(or_(SalesMediaPlan.deal_id.in_(dids),
                                                SalesMediaPlan.title.like(f'{TITLE}%')))
    plans = q.all()
    pids = [p.id for p in plans]
    if pids:
        db.query(Notification).filter(
            Notification.entity_type == 'media_plan',
            Notification.entity_id.in_(pids)).delete(synchronize_session=False)
        db.query(NotificationDelivery).filter(
            NotificationDelivery.entity_type == 'media_plan',
            NotificationDelivery.entity_id.in_(pids)).delete(synchronize_session=False)
        db.query(AuditLog).filter(
            AuditLog.entity_type == 'media_plan',
            AuditLog.entity_id.in_(pids)).delete(synchronize_session=False)
    if dids:
        db.query(SalesDealStageHistory).filter(
            SalesDealStageHistory.deal_id.in_(dids)).delete(synchronize_session=False)
        db.query(AuditLog).filter(
            AuditLog.entity_type == 'sales_deal',
            AuditLog.entity_id.in_(dids)).delete(synchronize_session=False)
    for p in plans:
        db.delete(p)
    for d in deals:
        db.delete(d)
    db.commit()


@pytest.fixture()
def env():
    """Своя сделка на первой стадии со своим планом. Живые данные не трогаем: настоящую
    сделку двигать нельзя — это её история стадий и чужая работа."""
    db = SessionLocal()
    _purge(db)
    rep = (db.query(SalesRep).join(User, User.id == SalesRep.user_id)
           .filter(User.is_active == 1).first())
    first = Catalog(db).first()
    actor = (db.query(User).filter(User.is_active == 1,
                                   User.id != (rep.user_id if rep else 0)).first())
    if not (rep and first and actor):
        db.close()
        pytest.skip('нужен активный сейлз с учёткой, второй пользователь и каталог стадий')

    def _mk(suffix, sales_rep_id):
        d = SalesDeal(bitrix_id=f'{BX}-{suffix}', currency='RUB', title=f'{TITLE} {suffix}',
                      sales_rep_id=sales_rep_id, our_stage_id=first.id)
        db.add(d)
        db.flush()
        p = SalesMediaPlan(title=f'{TITLE} {suffix}', status='draft', version=1,
                           deal_id=d.id, amount_net=250000, created_by=actor.id)
        db.add(p)
        db.flush()
        p.group_id = p.id
        return d, p

    deal, plan = _mk('rep', rep.id)
    orphan, orphan_plan = _mk('norep', None)   # сделка без сейлза
    db.commit()
    try:
        yield SimpleNamespace(db=db, deal=deal, plan=plan, orphan=orphan,
                              orphan_plan=orphan_plan, rep=rep, actor=actor,
                              first=first, target=mp._mp_sent_stage(Catalog(db)))
    finally:
        _purge(db)
        db.close()


def _notices(db, plan_id):
    return (db.query(Notification)
            .filter(Notification.kind == 'mp_ready',
                    Notification.entity_type == 'media_plan',
                    Notification.entity_id == plan_id).all())


def test_linking_moves_the_deal_and_tells_the_sales_rep(env):
    """Прикрепление плана уводит сделку на стадию, где план обязателен, и пишет сейлзу."""
    db = env.db
    mp._advance_deal_on_link(db, env.actor, env.plan)
    db.commit()
    db.refresh(env.deal)

    assert env.deal.our_stage_id == env.target.id, 'сделка не встала на стадию с требованием плана'
    hist = (db.query(SalesDealStageHistory)
            .filter(SalesDealStageHistory.deal_id == env.deal.id).all())
    assert len(hist) == 1 and hist[0].to_stage_id == env.target.id, (
        'переход без записи в историю: «сколько сделка стоит на стадии» '
        'считалось бы от неизвестной даты')

    notes = _notices(db, env.plan.id)
    assert len(notes) == 1, f'сейлзу ушло уведомлений: {len(notes)} (ждали одно)'
    assert notes[0].user_id == env.rep.user_id, 'уведомление ушло не сейлзу сделки'
    assert notes[0].link == f'/accounts/mp/{env.plan.id}'


def test_relinking_the_same_plan_says_nothing(env):
    """Повторное прикрепление того же плана сделку не двигает и второй раз не пишет.

    Это и есть «событие на переход»: без этой границы сейлз получал бы письмо на каждое
    сохранение чужого плана — верный способ приучить его не читать уведомления.
    """
    db = env.db
    mp._advance_deal_on_link(db, env.actor, env.plan)
    db.commit()
    mp._advance_deal_on_link(db, env.actor, env.plan)
    db.commit()
    db.refresh(env.deal)

    assert env.deal.our_stage_id == env.target.id, 'повторный вызов перепрыгнул стадию вперёд'
    assert len(_notices(db, env.plan.id)) == 1, 'второе уведомление на то же событие'


def test_a_deal_without_a_sales_rep_still_moves(env):
    """Некому написать — не повод не двигать: движение сделки не зависит от адресата."""
    db = env.db
    mp._advance_deal_on_link(db, env.actor, env.orphan_plan)
    db.commit()
    db.refresh(env.orphan)

    assert env.orphan.our_stage_id == env.target.id
    assert _notices(db, env.orphan_plan.id) == []
