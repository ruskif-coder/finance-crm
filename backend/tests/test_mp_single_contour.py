# -*- coding: utf-8 -*-
"""У медиаплана нет своего состояния и одна точка записи.

До 30.08.2026 у плана было и то, и другое в двух экземплярах.

**Состояние.** Своя стейт-машина `draft → review → approved/rejected → archived` с правом
`media_plans:approve` жила рядом со стадией сделки и означала то же самое: где план и
можно ли его показывать. Стадию «МП согласование» убрали 17.08 как бюрократию, а план от
неё не отвязали. Замер в день уборки: 24 плана, ВСЕ `draft`, ни одного `decided_by` —
машиной не пользовались ни разу, но она продолжала определять, что видно в очереди
аккаунта и что можно править.

**Запись.** Путей было два: `PUT` перетирал текущую версию, `POST` с `group_id` заводил
новую, и выбирал между ними фронт по нажатой кнопке. То есть на вопрос «что считается
новой редакцией плана» отвечал человек, а не правило.

Приборы ниже держат обе границы. Они смотрят на устройство, а не на поведение, потому
что ломается здесь именно устройство: параллельное состояние заводится не злым умыслом,
а очередной кнопкой «а давайте план ещё и согласовывать».
"""
import inspect

import pytest

from app.database import SessionLocal
from app.models import User
from app.notify import registry
from app.ord import models as _ord_models   # noqa: F401  (маппер sales_deals → ord_*)
from app.permissions import SECTIONS
from app.routers import media_plans as mp
from app.sales.catalog import Catalog
from app.sales.models import SalesDeal, SalesMediaPlan

from tests.test_mp_ready_notice import env  # noqa: F401  (общий стенд: сделка + план)


# ── 1. Одна точка записи ─────────────────────────────────────────────────────

def _routes():
    return [(r.path, sorted(r.methods - {"HEAD", "OPTIONS"}), r.endpoint.__name__)
            for r in mp.router.routes]


def test_the_plan_has_exactly_one_write_entry_point():
    """Записывающий роут ровно один — POST «» (`save_media_plan`).

    PATCH из реестра сюда не считается: он правит подписи (название, ответственные) и
    строк плана не касается. Остальные POST/PUT — про привязку к сделке и бриф.
    """
    writers = [(p, m, n) for p, m, n in _routes()
               if {"POST", "PUT"} & set(m) and "deal" not in p and "brief" not in n]
    assert writers == [("", ["POST"], "save_media_plan")], writers


def test_the_status_endpoint_did_not_come_back():
    """`POST /{id}/status` — вход в снятую стейт-машину."""
    assert not [p for p, _m, _n in _routes() if p.endswith("/status")]


def test_the_approve_permission_is_gone_from_media_plans():
    """Право «согласование» у раздела медиапланов больше нечего гейтить.

    Ключ секции неизменяем (см. test_permissions_groups) — а вот набор действий менять
    можно и нужно: действие, за которым не стоит ни одного эндпоинта, в конструкторе
    ролей выглядит работающим переключателем.
    """
    sec = next(s for s in SECTIONS if s["key"] == "media_plans")
    assert "approve" not in sec["actions"], sec["actions"]


def test_no_event_speaks_about_approving_a_plan():
    """В реестре уведомлений не осталось событий про визу плана."""
    dead = [k for k in ("mp_submit", "mp_approved", "mp_rejected", "mp_archived",
                        "mp_recalled", "mp_status", "mp_stuck", "mp_rework")
            if registry.get(k) is not None]
    assert not dead, dead


def test_urgency_no_longer_reads_a_plan_state():
    """Функция срочности не знает о визе и отказе — только о стадии сделки.

    Это тот же контур с другой стороны: пока факты `mp_approved`/`mp_rejected`
    существуют, очередь аккаунта считает состояние плана отдельно от его сделки.
    """
    fields = set(inspect.signature(mp.__dict__["_advance_deal_after_verify"]).parameters)
    assert fields  # держим импорт осмысленным
    from app.sales.urgency import DealFacts
    assert not {"mp_approved", "mp_rejected"} & set(DealFacts.__dataclass_fields__)


# ── 2. Кто решает, что версия новая ──────────────────────────────────────────

def test_a_plan_without_a_deal_is_never_sealed(env):  # noqa: F811
    """Плану без сделки нечем запечататься: клиенту его никто не отдавал."""
    db = env.db
    plan = SalesMediaPlan(title='[тест] без сделки', version=1, group_id=None)
    assert mp._plan_is_sealed(db, plan) is False


def test_sealing_follows_the_deal_stage(env):  # noqa: F811
    """На первой стадии — правим на месте; ушла дальше — версия зафиксирована."""
    db, deal, plan = env.db, env.deal, env.plan
    assert mp._plan_is_sealed(db, plan) is False, 'сделка на первой стадии — печатать нечего'

    nxt = mp._mp_sent_stage(Catalog(db))
    deal.our_stage_id = nxt.id
    db.commit()
    assert mp._plan_is_sealed(db, plan) is True, 'план отдан клиенту, а версия всё ещё правится'


def test_saving_without_changes_still_moves_the_deal(env):  # noqa: F811
    """Сохранение БЕЗ правок отрабатывает отметку «Проверено».

    Это была дыра, а не мелочь: аккаунт открывает собранный конвейером план, соглашается
    с ним и жмёт «Сохранить», не тронув ни строки. Прежняя ветка «содержимое совпало»
    возвращала `unchanged` и выходила ДО отметки — сделка оставалась на первой стадии,
    и очередь продолжала требовать проверить уже проверенный план.
    """
    db, deal, plan = env.db, env.deal, env.plan
    first = Catalog(db).first()
    assert deal.our_stage_id == first.id

    same = mp.MpIn(group_id=plan.group_id, title=plan.title, verified=True)
    out = mp.save_media_plan(same, db, env.actor)

    assert out["unchanged"] is True, 'содержимое не менялось — версия плодиться не должна'
    db.refresh(deal)
    assert deal.our_stage_id == mp._mp_sent_stage(Catalog(db)).id, (
        'сохранение без правок не двинуло сделку — отметка «Проверено» потеряна')
    assert db.query(SalesMediaPlan).filter(
        SalesMediaPlan.group_id == plan.group_id).count() == 1, 'появилась лишняя версия'


def test_changes_to_a_sealed_plan_start_a_new_version(env):  # noqa: F811
    """Правка отданного клиенту плана рождает версию, а не затирает старую."""
    db, deal, plan = env.db, env.deal, env.plan
    deal.our_stage_id = mp._mp_sent_stage(Catalog(db)).id
    db.commit()

    changed = mp.MpIn(group_id=plan.group_id, title=plan.title + ' (правка)', verified=True)
    out = mp.save_media_plan(changed, db, env.actor)

    assert out["unchanged"] is False and out["version"] == 2, out
    versions = (db.query(SalesMediaPlan)
                .filter(SalesMediaPlan.group_id == plan.group_id).all())
    assert len(versions) == 2, 'версия перетёрлась вместо того, чтобы родиться'
    assert plan.title in [v.title for v in versions], 'старая редакция потеряна'


def test_a_new_version_keeps_the_deal(env):  # noqa: F811
    """Новая версия наследует сделку, даже если её нет в payload.

    Привязка — свойство группы версий: `link-deal` пишет её во все. Пока `deal_id`
    брался из формы, сохранение без этого поля отвязывало план молча — и вместе с
    сделкой у плана пропадало всё его состояние.
    """
    db, deal, plan = env.db, env.deal, env.plan
    deal.our_stage_id = mp._mp_sent_stage(Catalog(db)).id
    db.commit()

    out = mp.save_media_plan(
        mp.MpIn(group_id=plan.group_id, title=plan.title + ' (без deal_id)'),
        db, env.actor)
    fresh = db.query(SalesMediaPlan).filter(SalesMediaPlan.id == out["id"]).first()
    assert fresh.deal_id == deal.id, 'новая версия потеряла сделку'


def test_changes_before_the_client_stay_in_the_same_version(env):  # noqa: F811
    """Пока план не отдан, правки ложатся в ту же версию — иначе сборка плана
    оставляла бы по версии на каждое нажатие «Сохранить», а их всего три."""
    db, plan = env.db, env.plan
    changed = mp.MpIn(group_id=plan.group_id, title=plan.title + ' (черновая правка)')
    out = mp.save_media_plan(changed, db, env.actor)

    assert (out["version"], out["unchanged"]) == (1, False), out
    assert db.query(SalesMediaPlan).filter(
        SalesMediaPlan.group_id == plan.group_id).count() == 1


# Импорты, которыми пользуются только аннотации выше, но без которых прибор не соберётся.
_ = (SessionLocal, User, SalesDeal, pytest)
