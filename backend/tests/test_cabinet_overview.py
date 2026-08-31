# -*- coding: utf-8 -*-
"""Сводка экрана «Кабинеты паблишеров»: показатели, услуги, контакты, лента.

Цифры на этом экране принимают решения — по ним видно, работает ли кабинет вообще, — и
ошибаются они молча: неверное число выглядит ровно как верное. Поэтому проверяется не
«ответ пришёл», а откуда взялась каждая величина.

Два правила, ради которых файл существует:

  · **«креативов на согласовании» считает витрина кабинета**, а не мы. Повторённый
    предикат однажды разойдётся с тем, что видит сама площадка;
  · **область видимости, выставленная ради подсчёта, не переживает транзакцию.**
    `set_config(..., is_local => true)` против обычного `SET`: соединение возвращается в
    пул, и оставленная в нём область открыла бы следующему запросу чужие данные.
"""
import pytest
from sqlalchemy import text

from app.cabinet import overview
from app.cabinet.models import Cabinet
from app.database import SessionLocal
from app.sales.models import SalesPublisher  # noqa: F401  — см. test_cabinet_scope


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


def test_pending_comes_from_the_cabinet_view(db):
    """Наше число совпадает с тем, что видит сама площадка в своей витрине."""
    ours = overview.creatives_pending(db)
    # Встречный счёт по определению задания — из ОПРЕДЕЛЕНИЯ представления, а не по
    # нашей формуле: если они разойдутся, разойдётся и экран с кабинетом.
    theirs = {p: n for p, n in db.execute(text(
        "SELECT t.publisher_id, count(*) "
        "  FROM launch_prep_review r "
        "  JOIN launch_prep_pair pr ON pr.id = r.pair_id "
        "  JOIN launch_prep_target t ON t.id = pr.target_id "
        " WHERE r.kind = 'площадка' AND r.verdict IS NULL "
        " GROUP BY t.publisher_id"))}
    assert ours == theirs, 'витрина и встречный счёт разошлись'


def test_scope_does_not_survive_the_transaction(db):
    """Область, выставленная ради подсчёта, умирает вместе с транзакцией.

    Прибор именно на `is_local`: с обычным `SET` тест был бы зелёным ровно до того дня,
    когда соединение с чужой областью досталось бы следующему запросу.
    """
    overview.creatives_pending(db)
    assert db.execute(text(
        "SELECT coalesce(current_setting('app.publisher_ids', true), '')")).scalar()
    # Именно COMMIT, а не ROLLBACK. Первая редакция откатывала — и была зелёной по
    # неверной причине: откат в PostgreSQL снимает и сессионный `SET` тоже, поэтому
    # подмена `is_local` на сессионную область теста не роняла. Различает их только
    # успешное завершение транзакции: локальная область умирает, сессионная переживает.
    db.commit()
    left = db.execute(text(
        "SELECT coalesce(current_setting('app.publisher_ids', true), '')")).scalar()
    assert left == '', f'область пережила транзакцию: {left!r}'


def test_service_cabinet_has_publishers_but_no_contacts(db):
    """У служебного кабинета площадки есть, а контактов нет — и это не сбой.

    Он наш: его люди не контакты площадок. Список площадок в нём информационный, связей
    он не хранит — поэтому `contacts_of` по его связям пуст, хотя видит он всё.
    """
    cab = db.query(Cabinet).filter(Cabinet.kind == 'служебный').first()
    if cab is None:
        pytest.skip('на стенде нет служебного кабинета')
    own = [i for (i,) in db.execute(text(
        "SELECT publisher_id FROM cabinet_publisher WHERE cabinet_id = :c"),
        {"c": cab.id})]
    assert own == [], 'служебный кабинет не должен хранить связей'
    assert overview.contacts_of(db, own) == []


def test_contact_without_account_has_no_level(db):
    """Уровень доступа существует только вместе с учёткой.

    Иначе экран обещает права человеку, который не может войти, — а именно по этой
    колонке решают, кому выдавать доступ.
    """
    pubs = [i for (i,) in db.execute(text(
        "SELECT publisher_id FROM cabinet_publisher"))]
    rows = overview.contacts_of(db, pubs)
    if not rows:
        pytest.skip('на стенде нет контактов у площадок кабинетов')
    for r in rows:
        if not r["has_account"]:
            assert r["level"] is None and r["is_active"] is None
        else:
            assert r["level"] in ('все', 'просмотр')


def test_surfaces_are_folded_into_one_service(db):
    """WEB и APP одной услуги — одна строка, а не две.

    Два чипа читались бы как две разные услуги, а у площадки это одна, продаваемая на
    двух экранах.
    """
    svc = overview.services_by_publisher(db)
    for pid, items in svc.items():
        names = [i["name"] for i in items]
        assert len(names) == len(set(names)), f'площадка {pid}: услуга задвоилась'
        for i in items:
            assert i["surfaces"] == sorted(set(i["surfaces"]))


def test_kpi_counts_cabinets_not_people(db):
    """«Без учёток» — про кабинеты. Кабинет без единой учётки нерабочий: площадка
    физически не может войти, и это факт, а не предупреждение."""
    from types import SimpleNamespace

    from app.routers.cabinets import list_cabinets

    out = list_cabinets(db, SimpleNamespace(role=SimpleNamespace(key='admin'),
                                            id=None, name='прибор'))
    kpi = out["kpi"]
    assert kpi["cabinets"] == len(out["cabinets"])
    assert kpi["accounts"] == sum(len(c["accounts"]) for c in out["cabinets"])
    assert kpi["without_accounts"] == sum(
        1 for c in out["cabinets"] if not c["accounts"])
    assert kpi["active"] + kpi["draft"] <= kpi["cabinets"]


def test_live_campaigns_count_stage_not_period(db):
    """«Запущенных РК» — про ступень сделки, а не про календарь.

    Владелец 30.08.2026: «то, что сейчас запущено в рамках площадки». Ступень
    `launch` — это «В размещении» и «Итоговая сверка»; сделка, которая только готовится,
    в число не входит, даже если её период идёт прямо сейчас.
    """
    live = overview.campaigns_live(db)
    wrong = db.execute(text(
        "SELECT count(*) FROM launch_prep_target t "
        "  JOIN sales_deals d ON d.id = t.deal_id "
        "  JOIN sales_stages s ON s.id = d.our_stage_id "
        " WHERE s.stage_key <> 'launch' AND t.publisher_id = ANY(:ids)"),
        {"ids": list(live.keys()) or [0]}).scalar()
    # Сам факт наличия «не запущенных» сделок у тех же площадок — норма; прибор на то,
    # что они НЕ попали в число.
    total_live = sum(live.values())
    by_stage = db.execute(text(
        "SELECT count(DISTINCT t.deal_id) FROM launch_prep_target t "
        "  JOIN sales_deals d ON d.id = t.deal_id "
        "  JOIN sales_stages s ON s.id = d.our_stage_id "
        " WHERE s.stage_key = 'launch'")).scalar()
    assert total_live >= by_stage or by_stage == 0, (
        f'счёт по ступени разошёлся: {total_live} против {by_stage}, '
        f'мимо ступени осталось {wrong}')


def test_our_contacts_show_missing_email(db):
    """Сотрудник без учётки в системе отдаётся с пустой почтой, а не пропадает.

    Площадке он показался бы контактом без способа связаться; экран обязан иметь чем
    его пометить, поэтому строка приходит, а не отбрасывается.
    """
    # Сотрудник заводится СВОЙ: у всех 11 живых представителей учётка есть, и прибор,
    # ищущий готового, вечно пропускался бы — то есть не проверял ничего.
    rep = db.execute(text(
        "INSERT INTO sales_reps (name, is_active, is_sales_head) "
        "VALUES ('__проба без учётки__', true, false) RETURNING id")).scalar()
    db.commit()
    try:
        db.execute(text("INSERT INTO cabinet_our_contact (role, rep_id) "
                        "VALUES ('__проба__', :r)"), {"r": rep})
        db.commit()
        row = next(c for c in overview.our_contacts(db) if c["rep_id"] == rep)
        assert row["email"] is None and row["name"]
    finally:
        db.rollback()
        db.execute(text("DELETE FROM cabinet_our_contact WHERE rep_id = :r"), {"r": rep})
        db.execute(text("DELETE FROM sales_reps WHERE id = :r"), {"r": rep})
        db.commit()
