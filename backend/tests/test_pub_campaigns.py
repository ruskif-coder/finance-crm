# -*- coding: utf-8 -*-
"""«Актуальные кампании» в кабинете: витрина размещений.

Блок вернулся 15.09.2026 по хендоффу `docs/актуальные кампании.zip` и впервые собирается
из настоящих данных: до этого он лежал в `cabinet-frontend/lib/demo.js` под флагом
`SHOW_MONEY = false` — выключенная выдумка вместо блока.

Проверяется то, что ломается МОЛЧА и в пользу неверного числа: показы чужих площадок,
унаследованный ЕРИД и состояние, которого нет в справочнике.
"""
import pytest
from sqlalchemy import text

from app.database import SessionLocal

# Шесть состояний из хендоффа. Список здесь ПОВТОРЁН намеренно: он же записан в SQL
# витрины, и прибор должен ловить расхождение, а не читать ту же строку дважды.
SIX = {'ждёт согласования', 'ждёт старта', 'в размещении', 'пауза', 'завершён', 'отказ'}


@pytest.fixture
def db():
    s = SessionLocal()
    # Область обязательна: без неё `pub.allowed_publisher_ids()` пуст, и витрина честно
    # отдаёт ноль строк. Ставим все площадки — `is_local => true` умирает с транзакцией.
    ids = [str(i) for (i,) in s.execute(text("SELECT id FROM sales_publishers"))]
    s.execute(text("SELECT set_config('app.publisher_ids', :v, true)"),
              {"v": ",".join(ids)})
    yield s
    s.close()


def test_status_never_leaves_the_catalogue(db):
    """У размещения ровно одно из шести состояний.

    Седьмое значение нарисуется в таблице пустым чипом: компонент берёт цвет из словаря
    `RK_STATUS[c.status]` по ключу, и незнакомый ключ роняет строку целиком.
    """
    seen = {r[0] for r in db.execute(text("SELECT DISTINCT status FROM pub.campaign_v1"))}
    assert seen <= SIX, f'состояния вне справочника: {seen - SIX}'


def test_fact_is_counted_per_placement_not_per_campaign():
    """Факт показов считается ПО СВОЕЙ строке размещения.

    Самая дорогая ошибка этой витрины и притом незаметная: `ad_campaign_stat` лежит на
    кампании, и join без `placement_id` показал бы площадке открутку ВСЕЙ кампании,
    включая чужие сайты. Число выглядело бы правдоподобно — просто кратно больше
    настоящего, — и обнаружилось бы на сверке, когда счёт уже выставлен.
    """
    db = SessionLocal()
    try:
        sql = db.execute(text(
            "SELECT pg_get_viewdef('pub.campaign_v1'::regclass, true)")).scalar()
    finally:
        db.close()
    assert 's.placement_id = pl.id' in sql.replace('\n', ' '), (
        'факт берётся без привязки к размещению — площадка увидит чужие показы')


def test_the_view_gives_dates_not_a_ready_period():
    """Витрина отдаёт ДАТЫ, а период считает экран.

    Требование хендоффа, и оно про реальный дефект: пока период хранился отдельным полем,
    пара «период ↔ срок РК» расходилась — декабрьский флайт лежал в сентябрьском периоде.
    Отдай мы готовый период, у экрана снова стало бы два источника одного числа.
    """
    db = SessionLocal()
    try:
        cols = {r[0] for r in db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            " WHERE table_schema = 'pub' AND table_name = 'campaign_v1'"))}
    finally:
        db.close()
    assert {'date_from', 'date_to'} <= cols
    assert 'period' not in cols, 'период отдаётся готовым — он разойдётся со сроком РК'


def test_erid_belongs_to_the_placement_not_to_the_brand():
    """ЕРИД берётся по паре «сделка × площадка».

    Ключ по бренду означал бы, что второй флайт того же бренда наследует чужой номер, —
    дефект, проверенный на макете («Ферон · Виферон» дважды получал один ЕРИД). В
    маркировке чужой номер это не косметика.
    """
    db = SessionLocal()
    try:
        sql = ' '.join(db.execute(text(
            "SELECT pg_get_viewdef('pub.campaign_v1'::regclass, true)")).scalar().split())
    finally:
        db.close()
    assert 'cs.deal_id = t.deal_id AND cs.publisher_id = t.publisher_id' in sql


def test_scope_closes_when_it_is_not_set():
    """Без установленной области витрина отдаёт НИЧЕГО, а не всё.

    Тот же инвариант, что у остальных представлений схемы `pub`: забытая установка должна
    показывать пустоту, а не чужие площадки. Защита закрывается, а не открывается.
    """
    s = SessionLocal()
    try:
        n = s.execute(text("SELECT count(*) FROM pub.campaign_v1")).scalar()
    finally:
        s.close()
    assert n == 0, 'витрина отдаёт строки без установленной области видимости'


def test_archived_placements_are_not_shown(db):
    """Снятое с площадки размещение в блок не попадает.

    `archived_at` — это «мы это отменили»; показывать его наравне с живыми значило бы
    предлагать площадке считать деньги по тому, чего не будет.
    """
    sql = ' '.join(db.execute(text(
        "SELECT pg_get_viewdef('pub.campaign_v1'::regclass, true)")).scalar().split())
    assert 't.archived_at IS NULL' in sql


def test_every_row_has_what_the_component_needs(db):
    """Контракт с компонентом: девять колонок берут из этих полей и ничего не додумывают.

    Компонент вставлен из хендоффа дословно и на отсутствующее поле не проверяет —
    `RK_STATUS[c.status]` на `undefined` уронит строку. Поэтому полнота проверяется здесь.
    """
    rows = db.execute(text(
        "SELECT brand, service, surface, cpm, status, site FROM pub.campaign_v1 LIMIT 200")).all()
    if not rows:
        pytest.skip('на стенде нет размещений')
    for r in rows:
        assert r.brand and r.brand.strip(), 'пустое имя кампании'
        assert r.site and r.site.strip(), 'пустая площадка'
        assert r.surface in ('web', 'app'), f'поверхность «{r.surface}» вне пары web/app'
        assert r.status in SIX
        assert r.cpm is not None


# ПРЕЖНИЙ ПРИБОР «сверка убирает период из блока» ЗАМЕНЁН на пару ниже
# (`test_reconciliation_is_a_flag_not_a_filter` и `test_a_closed_period_stays_visible_in_
# the_archive`). Поведение сменилось осознанно 15.09.2026: сверка больше не выкидывает
# строку из витрины, а ПОМЕЧАЕТ её — иначе разделу «Кампании» нечего было бы показывать,
# и площадка теряла бы историю ровно за те периоды, по которым с ней рассчитались.
# Отбор переехал к читателю: дашборд берёт `!reconciled`, архив — всё.

# ПРО ЗАГОЛОВКИ КЕША КАБИНЕТА прибора здесь нет по той же причине, что и про КПЭ:
# `Caddyfile` в бэкенд-контейнер не смонтирован, и тест, который всегда пропускается,
# создаёт видимость проверки.
#
# История, ради которой это записано. 15.09.2026 площадка сообщила: «кабинет откатился на
# прошлую версию, актуальные кампании пропали». Кода это не касалось. 13.09 заголовки кеша
# завели на главном контуре, а блок кабинета в `Caddyfile` пропустили: без `Cache-Control`
# браузер решает по своим эвристикам и держит старую разметку, а старая разметка ссылается
# на чанки, которых после пересборки уже нет — дашборд грузится лениво, его чанк сменил
# имя, и по старой ссылке приходит 404. Со стороны это неотличимо от отката версии.
#
# Симптом дословно описан в комментарии соседнего контура, написанном за два дня до этого.
# Проверка после правки: `curl -skI https://lk.localhost` → `Cache-Control: no-cache`,
# `/api/*` → `no-store`, `/_next/static/*` → `immutable` (не задето).


def test_the_demo_seeder_refuses_anywhere_but_the_stand():
    """Скрипт демо-размещений не запускается нигде, кроме стенда, и закрывается при
    сомнении.

    Владелец 15.09.2026: «демо потом не должно в прод уехать». Опасность не в том, что
    кто-то запустит скрипт на проде нарочно, а в том, что проверка окажется МЯГКОЙ: в
    этом проекте трижды случалось, что значение есть в `.env`, а до процесса не доходит
    (готча `env-not-reaching-container`). Пустой `DOMAIN` на боевом сервере мягкая
    проверка приняла бы за стенд, и поддельные сделки оказались бы в кабинете настоящей
    площадки.

    Поэтому пропускается только ЯВНОЕ `localhost`, и прибор стоит именно на этом.
    """
    import importlib

    mod = importlib.import_module('scripts.2026-09-15_demo_publisher_campaigns')

    import os as _os
    was = _os.environ.get('DOMAIN')
    try:
        for value, allowed in ((None, False), ('', False), ('  ', False),
                               ('timon.simbad.pro', False), ('localhost', True)):
            if value is None:
                _os.environ.pop('DOMAIN', None)
            else:
                _os.environ['DOMAIN'] = value
            assert mod._stand_only() is allowed, (
                f'DOMAIN={value!r}: скрипт {"не " if allowed else ""}должен работать')
    finally:
        if was is None:
            _os.environ.pop('DOMAIN', None)
        else:
            _os.environ['DOMAIN'] = was


def test_demo_rows_are_marked_and_removable():
    """У демо-сделок есть метка и есть чем их снять.

    Данные без метки отличаются от настоящих только в памяти того, кто их лил, — и живут
    годами. Метка невидима площадке (`bitrix_id` в кабинете не показывается), но
    однозначна для нас, а `--undo` убирает всё заведённое, включая строки факта.
    """
    import importlib

    mod = importlib.import_module('scripts.2026-09-15_demo_publisher_campaigns')
    assert mod.BX_BASE >= 8_000_000, 'диапазон метки пересекается с настоящими сделками'
    assert callable(mod.undo)
    src = __import__('inspect').getsource(mod.undo)
    # УДАЛЕНИЕ ТОЧНОЕ, а не по шаблону. `bitrix_id` — строка, и на стенде лежит настоящая
    # сделка с номером `888`: шаблон `LIKE '88000%'` её не задевает, а `880001234` задел
    # бы. Ошибка такого сорта не проявляется, пока не станет дорогой, поэтому прибор
    # требует адресного списка и второго признака — метки в названии.
    assert 'bitrix_id = ANY(' in src, '`--undo` адресует сделки шаблоном, а не списком'
    assert 'title LIKE' in src, 'у удаления один признак вместо двух'
    assert 'LIKE :b' not in src
    for table in ('ad_campaign_stat', 'ad_campaign_placement', 'ad_campaign',
                  'launch_prep_review', 'launch_prep_pair', 'launch_prep_creative_set',
                  'launch_prep_target', 'sales_deals'):
        assert table in src, f'`--undo` не убирает {table} — останутся сироты'


def test_reconciliation_is_a_flag_not_a_filter(db):
    """Сверка — ПРИЗНАК в витрине, а не отбор внутри неё.

    Читателей у витрины двое, и им нужно противоположное: блок «Актуальные кампании» на
    дашборде показывает только несверенное (размещение висит там до сверки), а раздел
    «Кампании» — всё, включая закрытые периоды.

    Два представления с почти одинаковым SQL разошлись бы на первой же правке, и
    разошлись бы МОЛЧА: строка перестала бы появляться на одном экране и осталась на
    другом. Поэтому определение одно, а отбор — у того, кто читает.
    """
    cols = {r[0] for r in db.execute(text(
        "SELECT column_name FROM information_schema.columns "
        " WHERE table_schema = 'pub' AND table_name = 'campaign_v1'"))}
    assert 'reconciled' in cols, 'признака сверки нет — отбор снова зашит в витрину'

    sql = ' '.join(db.execute(text(
        "SELECT pg_get_viewdef('pub.campaign_v1'::regclass, true)")).scalar().split())
    # Условие сверки должно стоять в СПИСКЕ ВЫБОРКИ — то есть ДО главного `FROM`, а не
    # после него в отборе. Делить по первому `WHERE` нельзя: их несколько, они есть
    # внутри боковых подзапросов, и первый принадлежит не отбору витрины.
    main_from = sql.index('FROM launch_prep_target')
    assert sql.index("kind = 'сверка'") < main_from, (
        'сверка снова отсекает строки, а не помечает их')


def test_a_closed_period_stays_visible_in_the_archive(db):
    """Сверенное размещение остаётся в витрине и помечено, а не исчезает.

    Владелец 15.09.2026: «проекты, прошедшие сверку, пропадают отсюда» — то есть с
    ДАШБОРДА, но не из системы: для них и заводится раздел «Кампании» с архивом. Если бы
    сверка удаляла строку из витрины, архив показывать было бы нечего, а площадка
    потеряла бы историю ровно за те периоды, по которым с ней рассчитались.
    """
    row = db.execute(text(
        "SELECT publisher_id, to_char(date_from, 'YYYY-MM') AS p FROM pub.campaign_v1 "
        " WHERE date_from IS NOT NULL LIMIT 1")).first()
    if not row:
        pytest.skip('на стенде нет размещений с датой флайта')

    def state():
        ids = [str(i) for (i,) in db.execute(text("SELECT id FROM sales_publishers"))]
        db.execute(text("SELECT set_config('app.publisher_ids', :v, true)"),
                   {"v": ",".join(ids)})
        return db.execute(text(
            "SELECT count(*) FILTER (WHERE reconciled), count(*) FROM pub.campaign_v1 "
            " WHERE publisher_id = :p AND to_char(date_from, 'YYYY-MM') = :m"),
            {"p": row.publisher_id, "m": row.p}).first()

    was_flagged, was_total = state()
    db.execute(text(
        "INSERT INTO publisher_request (kind, publisher_id, period, verdict, decided_at) "
        "VALUES ('сверка', :p, :m, 'ок', now())"), {"p": row.publisher_id, "m": row.p})
    db.commit()
    try:
        flagged, total = state()
        assert total == was_total, 'сверка убрала строки из витрины — архиву нечего показать'
        assert flagged == total and flagged > was_flagged, 'признак сверки не проставился'
    finally:
        db.execute(text("DELETE FROM publisher_request "
                        " WHERE kind = 'сверка' AND publisher_id = :p AND period = :m"),
                   {"p": row.publisher_id, "m": row.p})
        db.commit()
