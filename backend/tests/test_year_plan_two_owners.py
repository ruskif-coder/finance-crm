# -*- coding: utf-8 -*-
"""Годовой план: у строки два владельца — продавец и ведущий аккаунт.

ЧТО СЛУЧИЛОСЬ (21.09.2026). Аккаунт завёл годовой план, сохранил — и план пропал. Не
из базы: он лёг в персональную корзину аккаунта. `sales_rep_id` у строки отвечал сразу
на два разных вопроса — «в чей дашборд считать деньги» и «кому показывать», — а при
сохранении туда писался тот, кто нажал кнопку. Пока планы заводили сейлзы себе, оба
ответа совпадали и расхождения не было видно вовсе.

Снаружи это выглядело как потеря данных. На деле план видел ровно один человек из
всех, кому он был нужен.

Теперь осей две, и приборы стоят на каждой ловушке, которую эта правка открывает:

* строку видит И продавец, И аккаунт — иначе чинить было незачем;
* владелец берётся из БРИФА, а не от сохраняющего: иначе чужое «Сохранить» молча
  переписывало бы владельца;
* сохранение удаляет только те строки, что человек ВИДЕЛ. Самое дорогое место:
  пропавшие из присланного строки удаляются вместе с откреплением сделок, и при двух
  осях набор прочитанный легко расходится с записываемым;
* сотрудник без профиля в справочнике ответственных не получает бесхозные строки —
  их видит только мастер.

Эндпоинты зовутся напрямую с фиктивным пользователем: тот же приём, что в
test_launch_prep_directories.py.
"""
from types import SimpleNamespace

import pytest

from app.database import SessionLocal
from app.models import User
from app.routers.year_plan import LineIn, SaveIn, get_year_plan, save_year_plan
from app.sales.models import SalesAdvertiser, SalesRep, SalesYearPlanLine

YEAR = 2098          # заведомо пустой год: чужих строк в выборке быть не может
MASTER = SimpleNamespace(role=SimpleNamespace(key="admin"), role_id=None, id=None,
                         email="master", name="мастер")


@pytest.fixture
def db():
    """Сессия + уборка за собой.

    Отката тут НЕ ХВАТАЕТ: `save_year_plan` коммитит сам, и строки года переживают
    `rollback()`. Первая редакция этого прибора на том и попалась — тесты начали
    падать друг о друга, а на стенде копились строки несуществующего года.
    """
    session = SessionLocal()
    _wipe(session)
    try:
        yield session
    finally:
        session.rollback()
        _wipe(session)
        session.close()


def _wipe(session):
    from app.sales.models import SalesYearPlan
    (session.query(SalesYearPlanLine)
     .filter(SalesYearPlanLine.year == YEAR).delete(synchronize_session=False))
    (session.query(SalesYearPlan)
     .filter(SalesYearPlan.year == YEAR).delete(synchronize_session=False))
    # Сперва отцепить справочник: тест назначает тестового сейлза ответственным за
    # ЖИВОГО рекламодателя, и без этого уборка падает на внешнем ключе. Сам
    # рекламодатель остаётся как был — тест возвращает ему прежнего сейлза.
    test_reps = [r.id for r in session.query(SalesRep)
                 .filter(SalesRep.name.like("ТЕСТ %")).all()]
    if test_reps:
        (session.query(SalesAdvertiser)
         .filter(SalesAdvertiser.sales_rep_id.in_(test_reps))
         .update({SalesAdvertiser.sales_rep_id: None}, synchronize_session=False))
        (session.query(SalesRep).filter(SalesRep.id.in_(test_reps))
         .delete(synchronize_session=False))
    session.commit()


@pytest.fixture(autouse=True)
def own_scope():
    """Мастерство — только у admin.

    Без этого рядовые роли стенда считались бы мастерами: `_is_master` при
    ОТСУТСТВИИ строки прав по секции возвращает True (умолчание 'all'), и проверка
    области «свои» выродилась бы в «всем всё видно».
    """
    from app.routers import year_plan as yp
    original = yp._is_master
    yp._is_master = lambda db_, user: user.role.key == "admin"
    yield
    yp._is_master = original


def _plain(u):
    return SimpleNamespace(role=SimpleNamespace(key="sales"), role_id=-777,
                           id=u.id, email=u.email, name=u.name)


@pytest.fixture
def stand(db):
    """Два профиля — продавец и аккаунт — на двух РАЗНЫХ живых учётках.

    Учётки настоящие: `_own_rep_ids` ищет профиль по `SalesRep.user_id`, и на
    выдуманном id проверка выродилась бы в «никто ничего не видит».
    """
    # Учётки БЕЗ профиля: у сотрудника их может быть несколько, а `_own_rep_ids`
    # отдаёт первый по порядку. Возьми занятую учётку — и сохранение припишет строку
    # её старому профилю, а прибор покажет расхождение, которого в коде нет.
    busy = {r.user_id for r in db.query(SalesRep).filter(SalesRep.user_id.isnot(None))}
    users = [u for u in db.query(User).filter(User.is_active == 1)
             .order_by(User.id).all() if u.id not in busy][:2]
    if len(users) < 2:
        pytest.skip("нужны две живые учётки без профиля в справочнике ответственных")
    seller = SalesRep(name="ТЕСТ продавец", user_id=users[0].id)
    manager = SalesRep(name="ТЕСТ аккаунт", user_id=users[1].id)
    db.add_all([seller, manager])
    db.flush()
    return SimpleNamespace(seller=seller, manager=manager,
                           seller_user=_plain(users[0]), manager_user=_plain(users[1]),
                           adv=db.query(SalesAdvertiser)
                               .order_by(SalesAdvertiser.id).first())


def _save(db, user, lines, rep_id=None, confirm_empty=False):
    return save_year_plan(SaveIn(year=YEAR, rep_id=rep_id, lines=lines,
                                 confirm_empty=confirm_empty),
                          db=db, current_user=user)


# В брифе ответственные хранятся УЧЁТКАМИ, а колонки владения ссылаются на профили
# справочника. Прибор специально кладёт сюда user_id: положи id профиля — и проверка
# «работает», притом что боевой экран присылает другое число.
def _line(brief=None, adv=None, amount=100.0, lid=None):
    return LineIn(id=lid, advertiser_id=(adv.id if adv else None),
                  plan_amount=amount, months_on=[1] + [0] * 11, brief=brief or {})


def _ids(db, user):
    return {l["id"] for l in get_year_plan(year=YEAR, db=db,
                                           current_user=user)["lines"]}


def _rows(db):
    return db.query(SalesYearPlanLine).filter(SalesYearPlanLine.year == YEAR)


# ── две оси владения ─────────────────────────────────────────────────────────
def test_account_plan_is_visible_to_the_seller(db, stand):
    """Тот самый случай: план завёл аккаунт, а видеть его должен и продавец."""
    _save(db, stand.manager_user, [_line(brief={"sales_rep_id": stand.seller.user_id})])
    db.flush()
    assert _ids(db, stand.seller_user), "продавец не видит план, заведённый аккаунтом"
    assert _ids(db, stand.manager_user), "аккаунт не видит свой же план"


def test_owner_comes_from_the_brief_not_from_who_saved(db, stand):
    """Продавец — из брифа. До правки им становился нажавший «Сохранить»."""
    _save(db, stand.manager_user, [_line(brief={"sales_rep_id": stand.seller.user_id})])
    db.flush()
    row = _rows(db).one()
    assert row.sales_rep_id == stand.seller.id
    assert row.account_manager_id == stand.manager.id


def test_empty_brief_falls_back_to_the_advertiser_rep(db, stand):
    """Бриф пуст → продавцом становится ответственный сейлз рекламодателя."""
    if stand.adv is None:
        pytest.skip("нужен рекламодатель в справочнике")
    was = stand.adv.sales_rep_id
    stand.adv.sales_rep_id = stand.seller.id
    db.flush()
    try:
        _save(db, stand.manager_user, [_line(adv=stand.adv)])
        db.flush()
        assert _rows(db).one().sales_rep_id == stand.seller.id
    finally:
        # Рекламодатель боевой — вернуть ему прежнего ответственного. Иначе прибор
        # тихо переназначает живую запись справочника.
        db.query(SalesAdvertiser).filter(SalesAdvertiser.id == stand.adv.id).update(
            {SalesAdvertiser.sales_rep_id: was}, synchronize_session=False)
        db.commit()


# ── самое дорогое место: удаление ────────────────────────────────────────────
def test_saving_never_deletes_lines_you_could_not_see(db, stand):
    """Сохранение своих строк не сносит чужие.

    Пропавшие из присланного строки удаляются вместе с откреплением сделок. Возьми
    набор для удаления шире, чем человек видел, — он потеряет чужую работу и не
    узнает об этом: на его экране этой строки не было.
    """
    alien = SalesRep(name="ТЕСТ чужой")
    db.add(alien)
    db.flush()
    db.add(SalesYearPlanLine(year=YEAR, sales_rep_id=alien.id,
                             account_manager_id=alien.id, plan_amount=42,
                             months_on=[0] * 12))
    db.flush()

    _save(db, stand.manager_user, [_line(brief={"sales_rep_id": stand.seller.user_id})])
    db.flush()

    left = _rows(db).filter(SalesYearPlanLine.sales_rep_id == alien.id).count()
    assert left == 1, "сохранение снесло строку, которой человек не видел"


def test_saving_still_deletes_your_own_dropped_lines(db, stand):
    """Обратная сторона: свои пропавшие строки удаляться ОБЯЗАНЫ.

    Без этой проверки предыдущую можно «починить», перестав удалять вовсе — и строки,
    убранные человеком с экрана, возвращались бы после перезагрузки.
    """
    _save(db, stand.manager_user, [_line(brief={"sales_rep_id": stand.seller.user_id})])
    db.flush()
    assert _rows(db).count() == 1
    # С 23.09.2026 пустой список принимается только с явным подтверждением: без него он
    # неотличим от «план не загрузился» (test_year_plan_save_guard.py). Экран шлёт флаг,
    # когда человек сам убрал все строки.
    _save(db, stand.manager_user, [], confirm_empty=True)
    db.flush()
    assert _rows(db).count() == 0


# ── бесхозные строки ─────────────────────────────────────────────────────────
def test_orphan_lines_are_not_handed_to_a_plain_employee(db, stand):
    """Строка без обоих владельцев — легаси. Мастеру показать можно, рядовому нет.

    Слить эти два случая в один «пустой список профилей» заманчиво: и там, и там
    показывать нечего. Но для мастера «нечего» значит «покажи бесхозное», а для
    сотрудника — «покажи пусто», и одинаковый ответ раздал бы чужое.
    """
    db.add(SalesYearPlanLine(year=YEAR, plan_amount=7, months_on=[0] * 12))
    db.flush()
    nobody = SimpleNamespace(role=SimpleNamespace(key="sales"), role_id=-778,
                             id=-999, email="none", name="без профиля")
    assert _ids(db, nobody) == set()
    assert _ids(db, MASTER), "мастер обязан видеть бесхозные строки"
