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
    # Добавлено 30.08.2026: поверхность размещения. Карточка кабинета печатала её с
    # самого начала, витрина не отдавала — площадка не видела, веб это или приложение.
    'surface_kind',
    # Письмо о правах на изображения (2026-09-07): площадка видит его вместе с креативом.
    # Отдаётся имя и размер, НЕ путь — файл доставляется через ядро под авторизацией
    # кабинета, у его контейнера тома `uploads` нет.
    'rights_letter_name',
    'rights_letter_size',
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
    запрос действительно не проходил. Схема `public` закрыта
    на уровне USAGE — с 31.08.2026 это правда. До того здесь стояла та же фраза, но
    она была неверной: замер показал `has_schema_privilege('cabinet','public',
    'USAGE') = true`, потому что USAGE и CREATE выданы псевдороли `PUBLIC`, а
    `REVOKE … FROM cabinet` такое не снимает. Изоляция держалась на отсутствии
    табличных грантов — то есть на сегодняшнем списке таблиц, при том что ядро
    заводит новые при каждом старте. Закрыто миграцией
    `2026-08-31_close_public_schema.sql`."""
    for table in ('sales_deals', 'sales_publishers', 'cabinet_account', 'operations'):
        with pytest.raises(Exception) as e:
            cab.execute(text(f"SELECT 1 FROM public.{table} LIMIT 1"))
        assert 'permission denied' in str(e.value).lower(), table
        cab.rollback()
        cab.execute(text("SET LOCAL ROLE cabinet"))


def test_every_pub_view_is_a_security_barrier(cab):
    """Каждое представление внешнего контура — барьер безопасности.

    `security_barrier` запрещает планировщику протаскивать пользовательское условие ПОД
    фильтр `allowed_publisher_ids()`. Без него чужая строка сперва проверяется условием
    внешней стороны и только потом отсекается: наружу она не попадёт, но по времени
    ответа или по тексту ошибки её существование подтверждается.

    Прибор нужен потому, что опция теряется МОЛЧА — `CREATE OR REPLACE VIEW` сбрасывает
    `reloptions`, представление продолжает работать, состав колонок прежний. Именно так
    30.08.2026 она слетела с `task_v1` и `profile_v1`; заметили при подготовке выкладки
    замером, а не приборами.
    """
    rows = cab.execute(text(
        "SELECT c.relname, coalesce(c.reloptions, '{}') FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'pub' AND c.relkind = 'v'")).all()
    assert rows, 'в схеме pub нет ни одного представления — контур не накатан'
    naked = sorted(name for name, opts in rows
                   if 'security_barrier=true' not in (opts or []))
    assert not naked, f'без security_barrier: {naked}'


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
    """Забытая установка области — самый вероятный сбой, и он обязан быть безопасным.

    Список витрин НЕ перечисляется руками, а спрашивается у базы: перечисленный однажды
    он устаревает молча — новая витрина просто не попадёт в проверку, и узнать об этом
    можно будет только от того, кому она показала лишнее. За 30.08.2026 таких добавилось
    четыре (услуги, юрлица, договоры, команда).

    Исключения — витрины, которые по смыслу НЕ зависят от площадки: список видов
    уведомлений и общие контакты с нашей стороны одинаковы для всех.

    ОТДЕЛЬНО и НЕ как «так и надо» — две витрины, через которые область только
    ВЫЧИСЛЯЕТСЯ, и потому сами ею ограничены быть не могут:

      · `account_v1` читается на входе, когда область ещё неизвестна. Сегодня она
        отдаёт ВСЕ учётки вместе с хешами паролей, а кабинет фильтрует их запросом по
        адресу. Роли `cabinet` этого больше, чем нужно: проверить пароль можно и не имея
        доступа к чужим хешам. Чинится тем же приёмом, что счётчик блокировок, —
        функцией `pub.find_account(email)` с SECURITY DEFINER, отдающей одну строку;
      · `account_publisher_v1` отвечает на вопрос «какие площадки у этой учётки», то есть
        и есть источник области. Ограничить её областью — замкнуть круг.

    Записано здесь, а не в задачнике: список исключений — единственное место, где это
    видно тому, кто придёт следующим.
    """
    GLOBAL = {'mute_v1', 'reason_v1', 'account_v1', 'account_publisher_v1'}
    views = [v for (v,) in cab.execute(text(
        "SELECT viewname FROM pg_views WHERE schemaname = 'pub' ORDER BY viewname"))]
    assert len(views) >= 10, f'витрин подозрительно мало: {views}'

    cab.execute(text("SELECT set_config('app.publisher_ids', '', true)"))
    leaked = []
    for view in views:
        if view in GLOBAL:
            continue
        n = cab.execute(text(f"SELECT count(*) FROM pub.{view}")).scalar()
        if n:
            leaked.append(f'{view}: {n}')
    assert not leaked, ('витрина отдаёт строки без установленной области: '
                        + ', '.join(leaked))


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
    # До 31.08.2026 отказ звучал как «permission denied for table»: гранта на
    # таблицу не было, но схема `public` оставалась видна роли через права
    # PUBLIC. После `2026-08-31_close_public_schema.sql` схема закрыта, и
    # неквалифицированное имя не разрешается вовсе — «relation does not exist».
    # Это СИЛЬНЕЕ прежнего: снаружи не подтверждается даже существование
    # таблицы. Принимаем оба ответа, чтобы прибор пережил и откат миграции.
    why = str(e.value).lower()
    assert 'permission denied' in why or 'does not exist' in why, why


def test_the_counter_lives_in_the_core_table(probe):
    """Счётчик ведётся в таблице ядра, а не в своей копии.

    Если однажды кабинету заведут свою таблицу, этот прибор упадёт: значение, записанное
    через `pub.*`, перестанет быть видно в `login_attempts`. Две реализации одного
    правила разъезжаются молча, и увидеть это иначе нечем.
    """
    probe.execute(text("SELECT pub.register_failed_login(:e)"), {"e": PROBE})
    probe.commit()
    n = probe.execute(text("SELECT failed_count FROM login_attempts WHERE email=:k"),
                      {"k": 'cabinet:' + PROBE}).scalar()
    assert n == 1, "запись через pub.* не попала в login_attempts ядра"


def test_the_outside_cannot_lock_an_inside_account(probe):
    """Перебор на кабинете НЕ закрывает вход сотруднику с той же почтой.

    До 31.08.2026 закрывал. Кабинет считает попытки по ЛЮБОМУ введённому адресу — так
    задумано, иначе «этот заблокирован, а этот нет» отвечает на вопрос о существовании
    учётки. Но строка счётчика была общей с ядром, и получалось следующее: человек из
    интернета берёт рабочую почту нашего сотрудника, пять раз ошибается паролем на
    `lk.simb-ad.com`, и сотрудник на 15 минут не входит в основную систему. Без всякой
    авторизации и сколько угодно раз подряд.

    Проверяем на почте ЖИВОГО пользователя ядра — на выдуманной дыры не видно.
    """
    email = probe.execute(text("SELECT email FROM users WHERE is_active = 1 "
                               "ORDER BY id LIMIT 1")).scalar()
    if not email:
        pytest.skip('в базе нет активного пользователя ядра')

    q = text("SELECT locked_until FROM login_attempts WHERE lower(email) = lower(:e)")
    before = probe.execute(q, {"e": email}).scalar()
    try:
        for _ in range(6):
            probe.execute(text("SELECT pub.register_failed_login(:e)"), {"e": email})
        probe.commit()

        # Строка ядра не изменилась. Сравниваем именно `locked_until`: закрывает вход
        # она, а не счётчик — счётчик лишь ведёт к ней.
        assert probe.execute(q, {"e": email}).scalar() == before, (
            f'перебор на кабинете закрыл вход сотруднику {email} в ядро')
        assert probe.execute(text("SELECT pub.login_lock_minutes(:e)"),
                             {"e": email}).scalar() > 0, 'кабинет при этом не заблокировался'
    finally:
        probe.execute(text("SELECT pub.clear_login_attempts(:e)"), {"e": email})
        probe.commit()


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


# ── «ваша команда» ──────────────────────────────────────────────────────────
def test_team_comes_from_the_setting_not_from_deals(cab):
    """Команду площадка видит ту, что назначили мы, а не участников её сделок.

    Было наоборот: `pub.team_v1` собирал `account_manager_id` и `traffic_manager_id`
    сделок, касающихся площадки. Владелец 30.08.2026: «у тебя сделки разных аккаунтов, а
    ты показываешь общие контакты без привязки к сделке» — то есть площадка видела
    произвольного из нескольких, и по строке нельзя было понять, по какой он сделке.
    Теперь состав задаётся явно, `cabinet_our_contact`.

    Прибор — на ИСТОЧНИК, а не на содержимое: он читает определение представления. Иначе
    на пустом справочнике (контакты ещё не назначены) он был бы зелёным при любой
    реализации, включая прежнюю.
    """
    src = cab.execute(text(
        "SELECT pg_get_viewdef('pub.team_v1'::regclass, true)")).scalar()
    assert 'cabinet_our_contact' in src, 'команда снова собирается не из настройки'
    for gone in ('account_manager_id', 'traffic_manager_id', 'launch_prep_target'):
        assert gone not in src, (
            f'в составе команды вернулся участник сделки ({gone}); '
            f'показывать их — отдельное решение владельца, оно не принято')


def test_profile_carries_the_extra_channels(cab):
    """Доп. каналы связи доезжают до площадки.

    Поле заполняется в карточке паблишера и до 30.08.2026 наружу не отдавалось: площадка
    не видела то, о чём мы с ней сами договорились — запасной чат на случай блокировок.
    """
    cols = {c for (c,) in cab.execute(text(
        "SELECT column_name FROM information_schema.columns "
        " WHERE table_schema = 'pub' AND table_name = 'profile_v1'"))}
    assert 'messenger_note' in cols
