"""Дашборд трафика: видимость, словари статусов, право.

Расчёты (флайт, прогноз, недокрут, распределение) переехали 04.09.2026 в `app/ad/flight.py`
и проверяются там — `tests/test_ad_flight.py`. Держать здесь их вторую копию значило бы
получить два набора порогов, которые разъедутся при первой правке.

Здесь остаётся то, что принадлежит именно роутеру: что видимость взята из очереди, а не
переписана заново, что словари закрыты, и что право зарегистрировано.
"""
from types import SimpleNamespace

import pytest

import app.launch_prep.models  # noqa: F401
import app.models  # noqa: F401
from app.ad import flight
from app.database import SessionLocal
from app.routers import traffic, traffic_dashboard as td
from app.sales.models import SalesRep


def test_visibility_rule_is_reused_not_copied():
    """Правило видимости — то же, что в очереди: один источник, иначе разойдутся."""
    assert td._apply_scope is traffic._apply_scope
    assert td._is_master is traffic._is_master


def test_calculations_come_from_the_core_not_from_the_router():
    """Роутер НЕ считает сам. Своя `forecast()` здесь была до 04.09.2026 и звала `pace`
    показами в день — при том, что в ядре `pace` это доля выполнения. Прибор держит
    именно отсутствие второго калькулятора."""
    assert not hasattr(td, 'forecast'), 'в роутере снова появился свой расчёт'
    assert td.progress is flight.progress
    assert td.distribute is flight.distribute


def test_status_vocabularies_are_closed():
    """Семь статусов РК и семь — площадки (04.09.2026, расширено 18.09.2026).

    Площадочные разделены на те, что ставит конвейер согласования, и те, что выбирает
    трафик: экран не должен предлагать в поповере статус, который человек не ставит.
    """
    assert "запущена" in td.CAMPAIGN_STATUSES and "чепуха" not in td.CAMPAIGN_STATUSES
    assert set(td.RUNNING) <= set(td.CAMPAIGN_STATUSES)

    # Семь с 18.09.2026: в начало добавлено «ждёт сборки» — площадка есть, креативов
    # по ней нет.
    assert td.PLACEMENT_STATUSES == ('ждёт сборки', 'у трафика', 'у площадки',
                                     'ждёт запуска', 'запущен', 'пауза', 'завершена')
    assert set(td.PLACEMENT_MANUAL) < set(td.PLACEMENT_STATUSES)
    assert set(td.PLACEMENT_RUNNING) <= set(td.PLACEMENT_MANUAL), (
        'крутит только то, что включил человек'
    )
    # Прежние три слова ушли целиком — их не должно остаться ни в одном наборе.
    assert not ({'вкл', 'выкл'} & set(td.PLACEMENT_STATUSES))


def test_permission_key_is_own_and_registered():
    from app.permissions import SECTIONS
    s = [x for x in SECTIONS if x["key"] == "traffic_dashboard"]
    assert s and s[0]["group"] == "Трафики"
    assert set(s[0]["actions"]) == {"view", "edit"}


# ── стена дней ───────────────────────────────────────────────────────────────

def test_day_wall_separates_no_data_from_zero():
    """Клетка без замера — None, клетка с нулём — 0. Это разные утверждения.

    «Ещё не отчитано» и «отчитали ноль» на стене выглядят одинаково серым, если их
    склеить, — и провал становится неотличим от отсутствия связи с коннектором.
    Отдельно проверяется `ahead`: дни впереди сегодняшнего не красятся вовсе.
    """
    from datetime import date
    rows = [{"id": 1, "deal_code": "AAA111", "date_start": date(2026, 9, 1),
             "date_end": date(2026, 9, 4), "plan_show": 400, "done_pct": 25.0}]
    stat = {1: {date(2026, 9, 1): (200, 2), date(2026, 9, 2): (0, 0)}}
    wall = td._day_wall(rows, stat, today=date(2026, 9, 3))
    cells = wall[0]["cells"]

    assert len(cells) == 4, 'клетка на каждый день флайта'
    assert cells[0]["ratio"] == 2.0, '200 при нужных 100 — двойной темп'
    assert cells[1]["ratio"] == 0.0, 'отчитанный ноль это ноль, а не «нет данных»'
    assert cells[2]["shows"] is None and cells[2]["ratio"] is None, 'замера нет'
    assert [c["ahead"] for c in cells] == [False, False, False, True]


def test_day_wall_puts_the_worst_on_top_and_caps_the_list():
    """Сверху то, что идёт хуже всех; длина ограничена — стена в 57 рядов нечитаема."""
    from datetime import date
    rows = [{"id": i, "deal_code": f"C{i}", "date_start": date(2026, 9, 1),
             "date_end": date(2026, 9, 10), "plan_show": 100, "done_pct": pct}
            for i, pct in enumerate([90.0, 10.0, 50.0], start=1)]
    wall = td._day_wall(rows, {}, today=date(2026, 9, 5))
    assert [w["done_pct"] for w in wall] == [10.0, 50.0, 90.0]
    assert len(td._day_wall(rows * 40, {}, today=date(2026, 9, 5))) == td.WALL_LIMIT


def test_day_wall_skips_campaigns_without_a_flight_or_plan():
    """Без дат или без плана нужного темпа не существует — строки на стене тоже."""
    from datetime import date
    rows = [{"id": 1, "deal_code": "A", "date_start": None, "date_end": None,
             "plan_show": 100, "done_pct": None},
            {"id": 2, "deal_code": "B", "date_start": date(2026, 9, 1),
             "date_end": date(2026, 9, 5), "plan_show": 0, "done_pct": None}]
    assert td._day_wall(rows, {}, today=date(2026, 9, 3)) == []


# ── переключатель «чьи РК» ───────────────────────────────────────────────────
#
# Тихая часть экрана: неверная область не роняет ничего, а показывает не тот список.
# Оба провала выглядят как правда — пустой экран читается как «работы нет», полный как
# «всё моё», — поэтому обе стороны прибиты отдельно.

def _u(key, is_master, uid):
    """Пользователь в той форме, в какой его читают `_is_master` и `_scope_for`."""
    return SimpleNamespace(id=uid, name='тест',
                           role=SimpleNamespace(key=key, is_master=is_master))


@pytest.fixture
def db():
    d = SessionLocal()
    yield d
    d.close()


def test_default_scope_is_mine_for_a_rank_and_file_and_all_for_a_master(db):
    """Умолчание считает сервер (владелец 04.09.2026): рядовому — свои, мастеру — все.

    Считать его на фронте нельзя: роль приезжает тем же ответом, что и строки, и экран
    успел бы показать чужой список до того, как узнал, чей он.
    """
    rep = db.query(SalesRep).filter(SalesRep.user_id.isnot(None)).first()
    if not rep:
        pytest.skip('нужен хотя бы один представитель с учёткой')

    assert td._scope_for(db, _u('role_120', False, rep.user_id), None) == (rep.id, 'mine')
    assert td._scope_for(db, _u('role_121', True, rep.user_id), None) == (None, 'all')
    assert td._scope_for(db, _u('admin', False, rep.user_id), None) == (None, 'all')


def test_account_without_a_profile_gets_an_empty_list_not_everything(db):
    """Учётка без профиля ответственного → `-1`, то есть ПУСТО, а не «всё».

    Ловушка в `_apply_scope`: без `rep_id` он не фильтрует ничего. Вернуть отсюда `None`
    для человека, которому профиль ещё не заводили, значило бы показать ему все чужие РК
    под подписью «Мои» — и это не выглядело бы ошибкой ни на экране, ни в логах.
    Профиль есть не у всех по устройству справочника (см. `app/sales/reps.py`).
    """
    nobody, other = 10 ** 9, 10 ** 9 + 1
    assert td._scope_for(db, _u('role_120', False, nobody), 'mine') == (-1, 'mine')
    # То же и когда такого выбрали в списке — с чужой стороны.
    assert td._scope_for(db, _u('admin', False, None), str(other)) == (-1, str(other))
    # Свой id, выбранный явно, — это «Мои», а не отдельный фильтр: иначе у одного и того
    # же среза два имени, и подпись на экране зависит от того, как в него попали.
    assert td._scope_for(db, _u('role_120', False, nobody), str(nobody)) == (-1, 'mine')


def test_scope_takes_an_account_not_a_rep_profile(db):
    """Фильтр приходит УЧЁТКОЙ и переводится в профиль здесь.

    Выбор строится на учётках, потому что список по профилям неполон — ровно тот же
    корень, из-за которого кандидаты в трафики были пустым списком.
    """
    rep = db.query(SalesRep).filter(SalesRep.user_id.isnot(None)).first()
    if not rep:
        pytest.skip('нужен хотя бы один представитель с учёткой')
    assert td._scope_for(db, _u('admin', False, None), str(rep.user_id)) == (rep.id, str(rep.user_id))
    assert td._scope_for(db, _u('admin', False, None), 'all') == (None, 'all')
    # Мусор в параметре не должен превращаться в чужую область: падаем в «все».
    assert td._scope_for(db, _u('admin', False, None), 'ерунда') == (None, 'all')


def test_unassigned_is_a_filter_by_absence_not_by_a_person(db):
    """«Не распределено» — РК без ответственного, а не чей-то срез.

    Профиля у этого пункта нет и быть не может, поэтому `_scope_for` не должен пытаться
    его резолвить: `-1` здесь означал бы «человек без профиля» и дал бы пусто вместо
    списка неразобранного. Сам фильтр накладывается в реестре по `IS NULL`.
    """
    from app.models import User as U
    assert td._scope_for(db, _u('role_120', False, 1), 'none') == (None, 'none')
    assert td._scope_for(db, _u('admin', False, None), 'none') == (None, 'none')

    u = db.query(U).filter(U.is_active == 1).first()
    if not u:
        pytest.skip('нужна хотя бы одна активная учётка')
    me = _u('admin', False, u.id)
    free = td.dashboard(db=db, user=me, scope='none')['rows']
    everything = td.dashboard(db=db, user=me, scope='all')['rows']
    assert len(free) <= len(everything)
    ids = {r['id'] for r in free}
    # Ни одна РК из «не распределено» не должна попадать в чей-либо именной срез.
    for rep in td.staff_users(db, 'traffic'):
        named = td.dashboard(db=db, user=me, scope=str(rep['user_id']))['rows']
        assert not (ids & {r['id'] for r in named}), (
            f'РК без ответственного попала в срез {rep["name"]}'
        )


def test_the_picker_lists_accounts_and_marks_masters():
    """Список для переключателя — учётки трафика, мастера первыми и с флагом.

    Звёздочку рисует фронт, но признак обязан приезжать с сервера: определять мастера
    по имени роли на клиенте — это второй экземпляр правила.
    """
    from app.sales.reps import staff_users
    assert td.staff_users is staff_users, 'список сотрудников снова свой, а не общий'
    assert not hasattr(td, 'traffic_reps'), (
        'вернулся список по sales_reps — он неполон, в нём нет тех, кого ещё не назначали'
    )


def test_portfolio_plan_and_fact_count_only_launched_campaigns(db):
    """План и факт в шапке — по ЗАПУЩЕННЫМ РК (владелец 04.09.2026).

    Тихая ошибка: сложить портфель по всему видимому срезу — значит подмешать в план
    кампании будущих месяцев и те, что ещё собирают. Число выглядит правдоподобно, а
    «выполнение» под ним занижено на всё, что ещё не начиналось.

    Проверяется РАВЕНСТВО сумме по строкам того же ответа, а не константа: данные на
    стенде меняются, а связь «шапка = сумма запущенных строк» обязана держаться.
    """
    from app.models import User as U
    u = db.query(U).join(U.role).filter(U.is_active == 1).first()
    if not u:
        pytest.skip('нужна хотя бы одна активная учётка')
    d = td.dashboard(db=db, user=_u('admin', False, u.id))
    live = [r for r in d['rows'] if r['status'] in td.RUNNING]

    assert d['kpi']['plan_campaigns'] == len(live)
    assert d['kpi']['plan_show'] == sum(r['plan_show'] or 0 for r in live)
    assert d['kpi']['fact_shows'] == sum(
        r['fact_shows'] for r in live if r['fact_shows'] is not None)
    assert td.RUNNING == ('запущена', 'пауза'), (
        'пауза остаётся в счёте: приостановка не отменяет обязательство'
    )
    # «Требует внимания» и дыры считаются по ВСЕМУ срезу: РК без плана нужно увидеть
    # до старта, а не после — сужение до запущенных выключило бы эту плитку.
    assert d['kpi']['no_plan'] == sum(1 for r in d['rows'] if not r['plan_show'])


# ── каскад решений по РК на площадки ─────────────────────────────────────────

def test_campaign_decision_cascades_to_its_placements():
    """Решение над РК спускается на площадки (владелец 04.09.2026).

    До каскада «Стоп» менял только статус РК, и строка получалась противоречивой:
    «остановлена» и рядом «крутит 19 из 19». На стенде это была правда, а не только
    картинка — площадки оставались запущенными, и после подключения коннектора
    остановленная РК продолжала бы тратить.

    Значения не назначены заново, а взяты из смысла статуса площадки: пауза сохраняет
    долю, отключение выводит из распределения.
    """
    assert td.CASCADE_TO_PLACEMENT == {
        'пауза': 'пауза',
        'остановлена': 'завершена',
        'окончена': 'завершена',
        'архив': 'завершена',
    }
    # «Запущена» каскадом НЕ поднимает: включить чужое отключение молча нельзя, для
    # этого есть отдельный `with_placements` со спросом у человека.
    assert 'запущена' not in td.CASCADE_TO_PLACEMENT
    # Каскадить можно только то, что человек ставит руками: значения цепочки
    # согласования сюда попасть не должны.
    assert set(td.CASCADE_TO_PLACEMENT.values()) <= set(td.PLACEMENT_MANUAL)
    assert not (set(td.CASCADE_TO_PLACEMENT) & set(td.PLACEMENT_CHAIN))


def test_cascade_covers_every_manual_campaign_status_that_stops_delivery():
    """Ни один ручной статус РК не остаётся без ответа на вопрос «а площадки?».

    Прибор ловит добавление нового ручного статуса: он либо каскадится, либо это
    осознанное исключение — и тогда его надо назвать здесь.
    """
    from app.ad.flight import CAMPAIGN_MANUAL
    assert set(td.CASCADE_TO_PLACEMENT) == set(CAMPAIGN_MANUAL), (
        'появился ручной статус РК без правила для площадок'
    )


def test_pips_speak_the_same_language_as_the_bar():
    """Пипс несёт СВОЁ выполнение, а не «включено ли» (владелец 05.09.2026).

    Раньше в одной строке жили две шкалы про один процесс: пипсы отвечали «крутит», а
    полоса рядом — «идёт по темпу». Жёлтый означал в них разное, и сложить строку в одну
    мысль было нельзя. Прибор держит контракт пипса: состояние + процент, а цвет считает
    экран той же функцией, что для полосы.
    """
    rows = [
        {"weight": 5, "status": "запущен", "done_pct": 12.0, "domain": "a.ru"},
        {"weight": 9, "status": "ждёт запуска", "done_pct": None, "domain": "b.ru"},
        {"weight": 1, "status": "у площадки", "done_pct": None, "domain": "c.ru"},
    ]
    pips = td._pips(rows)
    # Порядок — по весу: первые несут основной объём, и просадка одной из них тянет РК.
    assert [p["domain"] for p in pips] == ["b.ru", "a.ru", "c.ru"]
    assert [p["s"] for p in pips] == ["ready", "run", "idle"]
    assert pips[1]["pct"] == 12.0
    # Согласованная, но не включённая — НЕ «крутит»: у неё мяч у трафика, а не у
    # площадки, и красить её шкалой открутки нечем.
    assert pips[0]["pct"] is None

    # Больше восьми в колонке 110 px сливаются в полосу — счётчик рядом точнее.
    assert len(td._pips([{"weight": i, "status": "запущен"} for i in range(20)])) == td.PIPS_MAX
