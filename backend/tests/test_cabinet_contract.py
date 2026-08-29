"""Граница внешнего контура. Пять утверждений, ни одно из которых не видно глазами.

Кабинет паблишера — единственное место системы, куда ходит НЕ наш сотрудник. Изоляция
там держится не на коде приложения, а на двух вещах в базе: роль без прав в `public` и
view вместо таблиц. Обе молчаливые: сломанные, они не падают, а просто начинают отдавать
больше, чем должны, — и узнать об этом можно только от того, кому это показали.

Приборы работают ОТ РОЛИ `cabinet` (`SET LOCAL ROLE`), а не от нашей: проверять границу
привилегиями, которых у внешнего контура нет, значит проверять что-то другое.
"""
import pytest
from sqlalchemy import text

from app.database import SessionLocal

# То и только то, что видит паблишер. Сравнение СТРОГОЕ: лишняя колонка здесь — это не
# «расширили выдачу», а «показали клиенту то, чего он видеть не должен», и заметить это
# постфактум нельзя. Состав согласован владельцем 28.08.2026: бренд, рекламодатель, срок
# старта, услуга; бюджетов и плана показов нет.
TASK_COLUMNS = {
    'task_id', 'publisher_id', 'publisher_name', 'publisher_domain', 'tech_requirements',
    'creative_id', 'creative_no', 'creative_title', 'form',
    'advertiser', 'brand', 'service',
    'period_from', 'period_to', 'advertiser_url', 'asked_at',
    # Добавлены 2026-08-28 вторым слоем (вердикт наружу и запрос ссылки):
    # `target_id` — по нему ядро понимает, чью посадочную страницу прислали, а запрос
    # ссылки нужен целиком, вместе с текстом: без него площадка видит поле, но не
    # понимает, чего от неё хотят.
    'target_id', 'url_requested_at', 'url_request_text',
}

# Поля, которых в контракте кабинета быть не может. Проверяются по именам колонок всех
# view схемы `pub` — так ловится не только сегодняшняя ошибка, но и завтрашнее «добавлю
# поле, пригодится».
#
# Список ЦЕЛЫХ ИМЁН, а не подстрок, и это исправление от 28.08.2026. Подстроки казались
# надёжнее, но `network` — сеть площадки, к которой она принадлежит, — содержит `net`, и
# прибор упал на честном поле. Ложное срабатывание опаснее пропуска: его начинают
# обходить, и однажды обойдут вместе с настоящим.
#
# Что запрещено — это деньги КЛИЕНТА и наша внутренняя кухня: сумма сделки, наш
# закупочный CPM, агентство, сейлз, бриф, план показов. Деньги, которые мы должны САМОЙ
# площадке, запретом не покрыты (решение владельца 28.08.2026: показываем, считаем от
# CPM). Когда они появятся, поле добавляется сюда в исключения осознанно, а не
# просачивается потому, что подстрока не совпала.
FORBIDDEN = {
    'amount', 'amount_with_vat', 'cpm_contract', 'agency_id', 'agency',
    'sales_rep_id', 'brief', 'net', 'gross', 'margin', 'unit_price', 'price',
    'volume', 'cost', 'plan_volume',
}


@pytest.fixture
def cab():
    """Сессия, превращённая в роль `cabinet` на время транзакции.

    `SET LOCAL ROLE` — именно local: обычный `SET ROLE` пережил бы тест и достался
    следующему через пул соединений. Ровно та же готча, что убивает контур в бою.
    """
    db = SessionLocal()
    db.execute(text("SET LOCAL ROLE cabinet"))
    yield db
    db.rollback()
    db.close()


def test_cabinet_has_zero_privileges_in_public(cab):
    """ГЛАВНЫЙ прибор. Он ловит не сегодняшнюю ошибку, а завтрашнюю: `create_all` ядра
    заводит новые таблицы при каждом запуске, и любая из них не должна становиться
    видимой снаружи сама собой."""
    n = cab.execute(text(
        "SELECT count(*) FROM information_schema.role_table_grants "
        "WHERE grantee = 'cabinet' AND table_schema = 'public'")).scalar()
    assert n == 0, f"у роли cabinet появилось {n} привилегий в public"


def test_cabinet_cannot_read_core_tables(cab):
    """Функциональная проверка поверх структурной: мало не иметь гранта — надо, чтобы
    запрос действительно не проходил. Схема `public` закрыта на уровне USAGE."""
    for table in ('sales_deals', 'sales_publishers', 'cabinet_account', 'operations'):
        with pytest.raises(Exception) as e:
            cab.execute(text(f"SELECT 1 FROM public.{table} LIMIT 1"))
        assert 'permission denied' in str(e.value).lower(), table
        cab.rollback()
        cab.execute(text("SET LOCAL ROLE cabinet"))


def test_task_contract_columns_are_pinned(cab):
    got = {c for (c,) in cab.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'pub' AND table_name = 'task_v1'"))}
    assert got == TASK_COLUMNS, (
        f"лишние: {got - TASK_COLUMNS}; пропали: {TASK_COLUMNS - got}")


def test_no_money_words_in_the_contract(cab):
    """Ни одна колонка ни одного view кабинета не должна быть полем чужих денег.

    Проверка по имени, а не по значению, намеренно: она срабатывает в момент, когда поле
    ДОБАВИЛИ, а не когда по нему что-то посчитали и показали площадке.
    """
    rows = cab.execute(text(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'pub'")).all()
    bad = [f"{t}.{c}" for t, c in rows if c.lower() in FORBIDDEN]
    assert not bad, f"в контракте кабинета появились денежные поля: {bad}"


def test_scope_does_not_leak_between_queries(cab):
    """Изоляция сессии — то, ради чего этот файл написан.

    Соединение живёт в пуле и достаётся следующему запросу, уже другого паблишера.
    Ошибка `SET` вместо `SET LOCAL` даёт ровно это: второй запрос видит область первого.
    Глазами она не ловится и в одно лицо не воспроизводится.

    Проверяем не «список поменялся», а что смена области ПОЛНОСТЬЮ переопределяет
    выдачу: после второй установки в ответе не остаётся ни одной строки первой площадки.
    """
    # Площадку с заданием ищем через сам контракт: сначала открываем область настежь.
    everyone = ",".join(str(i) for i in range(1, 2001))
    cab.execute(text("SELECT set_config('app.publisher_ids', :v, true)"), {"v": everyone})
    first = cab.execute(text("SELECT publisher_id FROM pub.task_v1 LIMIT 1")).scalar()
    if first is None:
        pytest.skip("нет ни одного задания на согласовании — изоляцию не на чем показать")

    cab.execute(text("SELECT set_config('app.publisher_ids', :v, true)"), {"v": str(first)})
    mine = cab.execute(text("SELECT count(*) FROM pub.task_v1")).scalar()
    assert mine > 0

    # Другая площадка: заведомо не та, что нашлась.
    other = str(first + 1 if first != 1 else 2)
    cab.execute(text("SELECT set_config('app.publisher_ids', :v, true)"), {"v": other})
    leaked = cab.execute(text(
        "SELECT count(*) FROM pub.task_v1 WHERE publisher_id = :p"), {"p": first}).scalar()
    assert leaked == 0, (
        f"после смены области видны {leaked} заданий площадки {first} — область утекла")


def test_empty_scope_shows_nothing(cab):
    """Забытая установка области — самый вероятный сбой, и он обязан быть безопасным."""
    cab.execute(text("SELECT set_config('app.publisher_ids', '', true)"))
    for view in ('task_v1', 'task_file_v1'):
        n = cab.execute(text(f"SELECT count(*) FROM pub.{view}")).scalar()
        assert n == 0, f"{view} отдал {n} строк без установленной области"


# ── блокировка входа (30.08.2026) ────────────────────────────────────────────
#
# От ПЕРЕЧИСЛЕНИЯ учёток кабинет был защищён с самого начала: одинаковый ответ и прогон
# bcrypt даже для несуществующего адреса. От ПЕРЕБОРА пароля — нет, и для внешнего
# контура это опаснее: туда ходят не наши сотрудники, адрес входа известен площадке, а
# учётка у кабинета обычно одна.
#
# Своей таблицы попыток НЕ заводили. Правило (5 попыток, 15 минут) уже стоит в ядре на
# `login_attempts`; кабинет получил доступ к ТОМУ ЖЕ счётчику через три функции `pub.*`
# с SECURITY DEFINER — как и `pub.touch_login`. Проверяем именно это: функции доступны,
# а таблица под ними — нет.

PROBE = 'lockout_probe@cabinet.test'


@pytest.fixture
def probe():
    """Чистый счётчик до и после. Своя строка, чужие не трогаем."""
    db = SessionLocal()
    db.execute(text("SELECT pub.clear_login_attempts(:e)"), {"e": PROBE})
    db.commit()
    yield db
    db.execute(text("SELECT pub.clear_login_attempts(:e)"), {"e": PROBE})
    db.commit()
    db.close()


def test_five_failures_lock_the_account(probe):
    """Пятая неудача закрывает вход, четвёртая — ещё нет.

    Граница проверяется с обеих сторон: прибор, который щупает только «после пяти»,
    зелен и при блокировке с первой попытки.
    """
    for _ in range(4):
        probe.execute(text("SELECT pub.register_failed_login(:e)"), {"e": PROBE})
    probe.commit()
    assert probe.execute(text("SELECT pub.login_lock_minutes(:e)"),
                         {"e": PROBE}).scalar() == 0, "четыре неудачи блокировать не должны"

    probe.execute(text("SELECT pub.register_failed_login(:e)"), {"e": PROBE})
    probe.commit()
    left = probe.execute(text("SELECT pub.login_lock_minutes(:e)"), {"e": PROBE}).scalar()
    assert 0 < left <= 15, f"после пятой неудачи ждём блокировку до 15 мин, получили {left}"


def test_success_clears_the_counter(probe):
    """Удачный вход обнуляет счётчик — иначе редкие опечатки копятся месяцами."""
    for _ in range(3):
        probe.execute(text("SELECT pub.register_failed_login(:e)"), {"e": PROBE})
    probe.commit()
    probe.execute(text("SELECT pub.clear_login_attempts(:e)"), {"e": PROBE})
    probe.commit()
    for _ in range(4):
        probe.execute(text("SELECT pub.register_failed_login(:e)"), {"e": PROBE})
    probe.commit()
    assert probe.execute(text("SELECT pub.login_lock_minutes(:e)"), {"e": PROBE}).scalar() == 0, (
        "счётчик не обнулился: три старые неудачи сложились с четырьмя новыми"
    )


def test_cabinet_may_call_the_counter_but_not_read_it(cab):
    """Функции доступны, таблица под ними — нет.

    Это и есть смысл `SECURITY DEFINER`: кабинет пользуется правилом ядра, не получая
    доступа к его данным. Прямое чтение `login_attempts` показало бы, у кого сколько
    неудачных попыток, — то есть перечисление учёток обоих контуров.
    """
    assert cab.execute(text("SELECT pub.login_lock_minutes(:e)"),
                       {"e": PROBE}).scalar() == 0
    with pytest.raises(Exception) as e:
        cab.execute(text("SELECT count(*) FROM login_attempts"))
    assert 'permission denied' in str(e.value).lower() or 'denied' in str(e.value).lower()


def test_counter_is_shared_with_the_core(probe):
    """Счётчик ОДИН на оба контура — таблица ядра, а не копия.

    Если однажды кабинету заведут свою таблицу, этот прибор упадёт: значение, записанное
    через `pub.*`, перестанет быть видно в `login_attempts`. Две реализации одного
    правила разъезжаются молча, и увидеть это иначе нечем.
    """
    probe.execute(text("SELECT pub.register_failed_login(:e)"), {"e": PROBE})
    probe.commit()
    n = probe.execute(text("SELECT failed_count FROM login_attempts WHERE lower(email)=:e"),
                      {"e": PROBE}).scalar()
    assert n == 1, "запись через pub.* не попала в login_attempts ядра"


def test_lock_is_case_insensitive(probe):
    """Регистр почты не открывает второй счётчик.

    Иначе перебор идёт по `Ivan@…`, `IVAN@…`, `iVaN@…` — пять попыток на каждое
    написание, и блокировки фактически нет.
    """
    for _ in range(5):
        probe.execute(text("SELECT pub.register_failed_login(:e)"), {"e": PROBE.upper()})
    probe.commit()
    assert probe.execute(text("SELECT pub.login_lock_minutes(:e)"),
                         {"e": PROBE}).scalar() > 0, "заглавные буквы обошли блокировку"


# ── сводка доступа по двум контурам ──────────────────────────────────────────

def test_access_overview_covers_both_contours_and_flags_overlap():
    """Обе таблицы учёток в одном ответе, и пересечение почт названо отдельно.

    Учётки паблишеров хранятся отдельно и объединены быть не могут: роль БД кабинета не
    имеет прав на `public`. Сведена ВИДИМОСТЬ, не хранение — эта ручка ничего не меняет.

    Одна почта в обоих контурах означает человека, заведённого и внутрь, и наружу: либо
    ошибка, либо решение, которое принимают осознанно. Молчать о ней нельзя.
    """
    import app.backlog_models  # noqa: F401  разрешает внешние ключи User
    import app.notify.models   # noqa: F401
    from app.models import User
    from app.routers.users import access_overview

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.role_id == 1).first()
        if admin is None:
            pytest.skip('нет администратора для вызова ручки')
        out = access_overview(db, admin)
        assert out['core'] > 0 and out['outer'] > 0, 'один из контуров не попал в сводку'
        assert len(out['rows']) == out['core'] + out['outer']
        assert {r['contour'] for r in out['rows']} == {'ядро', 'кабинет'}

        core_mails = {r['email'].lower() for r in out['rows'] if r['contour'] == 'ядро'}
        outer_mails = {r['email'].lower() for r in out['rows'] if r['contour'] == 'кабинет'}
        assert set(out['shared_emails']) == {m for m in outer_mails if m in core_mails}, (
            'пересечение почт посчитано неверно'
        )
    finally:
        db.close()


def test_admin_scope_is_not_a_number():
    """У администратора проверок прав нет вообще — число разделов здесь солгало бы.

    `admin` обходит `require_permission` безусловно и не имеет строк в
    `role_permissions`. Написать ему «0 разделов» значит показать обратное правде.
    """
    import app.backlog_models  # noqa: F401
    import app.notify.models   # noqa: F401
    from app.models import User
    from app.routers.users import access_overview

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.role_id == 1).first()
        if admin is None:
            pytest.skip('нет администратора для вызова ручки')
        rows = access_overview(db, admin)['rows']
        admins = [r for r in rows if r['contour'] == 'ядро' and r['email'] == admin.email]
        assert admins and 'проверки не проходит' in admins[0]['scope']
    finally:
        db.close()
