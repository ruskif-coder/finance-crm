# -*- coding: utf-8 -*-
"""Прибор: сохранение годового плана не стирает строки из-за сбоя загрузки (аудит 23.09, 7.H1).

Экран глотал ошибку загрузки (`.catch(() => setGroups([]))`) и показывал пустой план без
предупреждения. Сохранение удаляет всё, чего нет в присланном списке, — то есть «пустой
план → Сохранить» стирал все строки сейлза за год и отвязывал от них сделки. Гонка
переключения сейлза давала то же с другой стороны: строки A сохранялись в корзину B,
строки B удалялись.

Экран теперь блокирует сохранение сам, но последняя линия — сервер: он не принимает
пустой список при непустом плане и строки с id, которых в этой корзине нет.
"""
import pytest
from fastapi import HTTPException

import app.ad.models           # noqa: F401
import app.launch_prep.models  # noqa: F401
import app.notify.models       # noqa: F401
import app.ord.models          # noqa: F401
from app.database import SessionLocal
from app.models import User
from app.routers import year_plan as yp
from app.sales.models import SalesYearPlanLine


@pytest.fixture
def db():
    s = SessionLocal()
    s.commit = s.flush
    try:
        yield s
    finally:
        s.rollback()
        s.close()


YEAR = 2099          # свой год: строки стенда в прогоне не участвуют


@pytest.fixture
def world(db):
    """Своё хозяйство в транзакции: админ с ДВУМЯ профилями ответственного (так бывает —
    один человек и продаёт, и ведёт аккаунт), третий сейлз и по строке на каждого.

    До 23.09.2026 тест брал строки стенда, а на стенде у всех пяти строк один и тот же
    сейлз — проверка чужой корзины пропускалась при каждом прогоне (ревью 23.09.2026)."""
    from app.sales.models import SalesAdvertiser, SalesRep
    admin = db.query(User).filter(User.is_active == 1, User.role.has(key="admin")).first()
    adv = db.query(SalesAdvertiser).first()
    if admin is None or adv is None:
        pytest.skip("нужны админ и рекламодатель")
    reps = [SalesRep(name=f"прибор профиль {k}", user_id=uid)
            for k, uid in (("А", admin.id), ("Б", admin.id), ("чужой", None))]
    db.add_all(reps)
    db.flush()
    lines = [SalesYearPlanLine(year=YEAR, advertiser_id=adv.id, sales_rep_id=r.id,
                               months_on=[0] * 12, plan_amount=0) for r in reps]
    db.add_all(lines)
    db.flush()
    return admin, reps, lines


def _count(db, rep):
    return db.query(SalesYearPlanLine).filter(SalesYearPlanLine.year == YEAR,
                                              SalesYearPlanLine.sales_rep_id == rep).count()


def _line_in(line):
    return yp.LineIn(id=line.id, advertiser_id=line.advertiser_id, months_on=[0] * 12)


def test_empty_list_does_not_wipe_a_plan(db, world):
    admin, reps, _ = world
    with pytest.raises(HTTPException) as e:
        yp.save_year_plan(yp.SaveIn(year=YEAR, rep_id=reps[0].id, lines=[]),
                          db=db, current_user=admin)
    assert e.value.status_code == 409
    assert _count(db, reps[0].id) == 1


def test_lines_of_another_bucket_are_refused(db, world):
    admin, reps, lines = world
    with pytest.raises(HTTPException) as e:
        yp.save_year_plan(yp.SaveIn(year=YEAR, rep_id=reps[0].id,
                                    lines=[_line_in(lines[0]), _line_in(lines[2])]),
                          db=db, current_user=admin)
    assert e.value.status_code == 409
    assert "другого плана" in e.value.detail
    assert _count(db, reps[0].id) == 1 and _count(db, reps[2].id) == 1


def test_master_with_two_profiles_saves_what_the_screen_showed(db, world):
    """Экран «свои» грузит план БЕЗ `rep_id` — это строки обоих профилей. Сохранение
    с тем же `rep_id` (пустым) принимает обе; с `rep_id` первого профиля строка второго
    была «чужой», и мастер с двумя профилями не мог сохранить план вовсе (ревью 23.09.2026:
    экран слал `own_rep_id`, теперь шлёт то же, с чем грузил)."""
    admin, reps, lines = world
    shown = yp.get_year_plan(year=YEAR, rep_id=None, db=db, current_user=admin)
    shown_ids = {ln["id"] for ln in shown["lines"]}
    assert shown_ids == {lines[0].id, lines[1].id}
    out = yp.save_year_plan(yp.SaveIn(year=YEAR, rep_id=None,
                                      lines=[_line_in(lines[0]), _line_in(lines[1])]),
                            db=db, current_user=admin)
    assert {ln["id"] for ln in out["lines"]} == shown_ids
    assert _count(db, reps[2].id) == 1                 # чужую строку не тронули
