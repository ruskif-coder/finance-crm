# -*- coding: utf-8 -*-
"""Почтовая рассылка площадке: режим, дайджест и кто чем распоряжается.

Три вещи появились 15.09.2026 по макету v2, и каждая ломается молча по-своему.

**Режим — свойство КАНАЛА, а не события.** «По событию» или «пачкой в такой-то час»
выбирается один раз для почты целиком; в матрице выбирают ЧТО присылать, а не как.

**Срочное идёт мимо дайджеста** — решение владельца: «наше сразу не понижается». Вид,
объявленный нами срочным, площадка в пачку увести не может; обратное она может.

**Дайджест собирается, а не придерживается.** До этого дня слово «дайджест» в каталоге
означало на деле «письмо подождёт до девяти утра», по отдельному письму на событие:
`digest_html` был написан и не вызывался никем. Прибор `test_digest_html_has_a_caller`
стоит именно на этом — он ловит возврат в прежнее состояние.
"""
import inspect
from types import SimpleNamespace

import pytest

from sqlalchemy import text

from app.database import SessionLocal
from app.notify.outward import digest, prefs, send
from app.notify.outward.kinds import KINDS


def test_the_digest_hour_has_no_setting_anywhere():
    """Час пачки — константа 09:00 по времени площадки, а не настройка.

    Решение владельца 15.09.2026. Первая редакция держала его в `cabinet_account_mail`
    с выбором 09/12/18; таблица умерла в день написания. Прибор следит, чтобы она не
    вернулась незаметно: настройка, которую никто не задаёт, но которая хранится, —
    это ровно тот хвост, по которому потом невозможно понять, почему у двух площадок
    пачка приходит в разное время.
    """
    from app.database import SessionLocal
    from app.notify.outward import schedule

    assert schedule.DIGEST_HOUR == 9
    db = SessionLocal()
    try:
        assert db.execute(text("SELECT to_regclass('cabinet_account_mail')")).scalar() is None, (
            'таблица часа вернулась — час снова хранится, хотя его никто не выбирает')
    finally:
        db.close()
    assert not hasattr(prefs, 'HOURS') and not hasattr(prefs, 'digest_hour'), (
        'в предпочтениях остался час — второй ответ на тот же вопрос')


def test_the_hour_is_counted_in_the_publishers_own_time():
    """09:00 — по времени ПЛОЩАДКИ, и смещение берётся из её карточки.

    Для площадки за Уралом наши девять утра — это её полдень или два часа дня. Замер
    14.09.2026: смещение равно нулю у всех 41 площадки, то есть сегодня разницы нет — и
    она появится молча, как только поле заполнят.
    """
    from datetime import datetime, timedelta

    from app.notify.outward import schedule

    # База выбрана ДО девяти утра у обеих: 00:00 UTC это 03:00 в Москве и 08:00 в
    # Иркутске. Возьми я 04:00 UTC — у Иркутска девять уже прошла бы, пачка уехала на
    # завтра, и разность считалась бы между разными сутками. На этом первая редакция
    # прибора и упала: он был прав, а неверна была подстановка.
    base = datetime(2026, 9, 15, 0, 0)
    msk = schedule.next_hour_at(base, 0, schedule.DIGEST_HOUR)
    irk = schedule.next_hour_at(base, 5, schedule.DIGEST_HOUR)   # Иркутск: +5 к Москве
    assert msk - irk == timedelta(hours=5), (
        'час не пересчитывается по смещению площадки')


def test_defaults_come_from_the_catalog_not_a_second_list():
    """Умолчание клетки выводится из расписания вида, а не из отдельного списка.

    Срочный вид по умолчанию приходит письмом сразу, обычный — пачкой. Это уже записано
    в каталоге (`kind.schedule`), и второй список умолчаний разошёлся бы с первым молча:
    на экране стояла бы галочка, а письмо уходило бы иначе.
    """
    for k in KINDS:
        urgent = k.schedule == 'сразу'
        assert prefs.default_on(k, prefs.BOT) is True
        assert prefs.default_on(k, prefs.MAIL) is urgent
        assert prefs.default_on(k, prefs.DIGEST) is (not urgent)


def test_a_value_equal_to_the_default_is_not_stored():
    """Клетка, совпавшая с умолчанием, строки не оставляет.

    Иначе «Вернуть по умолчанию» перестало бы значить что-либо: строка, повторяющая
    умолчание, неотличима от решения человека, и через полгода нельзя сказать, кто это
    выбрал — он или мы.
    """
    import inspect

    from app.routers import cabinet_gateway as gw
    src = inspect.getsource(gw.cabinet_notify_cell)
    assert 'value == prefs.default_on(kind, channel)' in src
    assert 'DELETE FROM cabinet_account_notify' in src


def test_digest_html_has_a_caller():
    """У сборщика пачки есть вызывающий.

    `mail/render.py::digest_html` пролежал без единого вызова с 13 по 15 сентября:
    рисовать пачку было чем, собирать нечем. Пункт, которого никто не зовёт, невозможно
    отличить от «не работает», и он копится годами — тот же урок, что с правилами
    сканера без подписчиков.
    """
    assert 'digest_html' in inspect.getsource(digest.run)


def test_urgent_never_goes_into_the_digest():
    """Срочное уходит письмом сразу даже при выбранном дайджесте.

    Решение владельца 15.09.2026. Проверяется на ФОРМЕ кода: живая отправка потребовала
    бы почты, контактов и часа суток, а вопрос ровно один — стоит ли `not urgent` в
    условии складывания в очередь.
    """
    # Запрет стоит ДВАЖДЫ и намеренно: на записи (ручка не даёт поставить галочку) и на
    # отправке (даже со стоящей галочкой срочное не уйдёт в пачку). Экран — не защита, а
    # старая сборка экрана тем более.
    src = inspect.getsource(send.notify_publisher)
    i = src.index('if in_digest')
    assert 'not urgent' in src[i:i + 80], (
        'срочный вид может уехать в пачку — «наше сразу не понижается» нарушено')

    from app.routers import cabinet_gateway as gw
    gwsrc = inspect.getsource(gw.cabinet_notify_cell)
    assert 'kind.schedule == "сразу"' in gwsrc, (
        'галочку дайджеста можно поставить срочному виду')


def test_the_panel_is_not_a_channel_at_all():
    """Панели среди способов доставки нет.

    Правка владельца 15.09.2026: «в панели нету уведомлений у паблишеров». Первая
    редакция экрана рисовала её колонкой «всегда» — то есть обещала канал, которого не
    существует, ровно как выключатель у вида без отправителя, который в этом же контуре
    лечили признаком `built`.

    Лента кабинета при этом осталась: это журнал наших с площадкой действий, а не канал,
    и выключателя у неё нет по той же причине, по какой его нет у истории переписки.
    """
    from app.routers import cabinet_gateway as gw

    assert 'панель' not in prefs.CHANNELS
    assert set(prefs.CHANNELS) == {prefs.BOT, prefs.MAIL, prefs.DIGEST}
    src = inspect.getsource(gw.cabinet_notify_cell)
    assert 'payload.channel not in prefs.CHANNELS' in src, (
        'способ не сверяется со списком — записать можно любой')
    assert 'status_code=400' in src


def test_the_two_mail_ways_are_mutually_exclusive():
    """Письмо приходит либо сразу, либо в пачке — «и то и то» это два письма об одном.

    Снимается парная колонка на ЗАПИСИ, а не на экране: экран может быть старой сборкой,
    а правило одно.
    """
    from app.routers import cabinet_gateway as gw
    assert set(prefs.MAIL_WAYS) == {prefs.MAIL, prefs.DIGEST}
    src = inspect.getsource(gw.cabinet_notify_cell)
    assert 'payload.channel in prefs.MAIL_WAYS' in src
    assert '_set(other, False)' in src


def test_mail_switch_writes_the_contact_flag_and_nothing_else():
    """«Почта включена» хранится ОДНИМ местом — галочкой контакта.

    По ней уходят письма. Заведи мы рядом своё поле — экран показывал бы одно, а рассылка
    шла по другому, и разошлись бы они молча.
    """
    from app.routers import cabinet_gateway as gw
    src = inspect.getsource(gw.cabinet_mail_settings)
    assert 'UPDATE sales_publisher_contacts SET notify' in src
    # И БОЛЬШЕ НИЧЕГО: своей таблицы у почтовых настроек нет вовсе — час константа,
    # способ доставки живёт в матрице. Ручка, начавшая писать что-то ещё, заводит
    # второй источник правды.
    assert 'INSERT INTO' not in src
    state = inspect.getsource(gw._contact_mail)
    assert 'sales_publisher_contacts' in state


def test_queue_keeps_content_not_a_rendered_letter():
    """В очереди лежит СОДЕРЖИМОЕ события, а не готовое письмо.

    Пачка собирается из карточек: сохранённый HTML одного письма в неё не складывается.
    Ошибка была бы не видна до первого дайджеста из двух событий.
    """
    db = SessionLocal()
    try:
        cols = {r[0] for r in db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            " WHERE table_name = 'cabinet_digest_queue'")).all()}
    finally:
        db.close()
    assert {'title', 'body', 'facts', 'tone', 'context'} <= cols
    assert 'html' not in cols


def test_digest_groups_by_address_not_by_publisher():
    """Пачка одна на ЧЕЛОВЕКА, а не на площадку.

    Один контакт ведёт несколько площадок, и три письма в девять утра — ровно то, от чего
    дайджест спасает. Площадка не теряется: она стоит в контексте карточки.
    """
    src = inspect.getsource(digest.run)
    assert 'by_addr[r.email]' in src, 'группировка не по адресу'


def test_sent_rows_are_never_collected_twice():
    """Отправленное помечается и во вторую пачку не попадает.

    Без отметки вчерашние события приезжали бы каждый день заново, и чем дольше молчит
    почта, тем длиннее письмо. Пометка ставится и при ОТКАЗЕ доставки: письмо уже лежит в
    журнале почты со своим статусом, разбирается неудача там.
    """
    src = inspect.getsource(digest.run)
    assert 'sent_at IS NULL' in src
    assert 'SET sent_at = now()' in src


def test_digest_hour_is_outside_quiet_hours():
    """Час пачки не попадает в тихие часы площадки.

    03:00 означало бы дайджест, который не уйдёт никогда: письмо ждало бы конца тихих
    часов, а очередь к тому времени уже считала бы его отправленным.
    """
    from app.notify.outward import schedule
    h = schedule.DIGEST_HOUR
    assert not (h >= schedule.QUIET_FROM or h < schedule.QUIET_TO), f'час {h} тихий'


def test_every_built_kind_declares_its_schedule():
    """У построенного вида объявлено, срочный он или дайджестовый.

    Поле со значением по умолчанию легко не заметить, а именно оно решает, разбудит ли
    письмо человека отдельным заходом или ляжет в пачку.
    """
    bad = [k.key for k in KINDS if k.built and k.schedule not in ('сразу', 'дайджест')]
    assert not bad, 'непонятное расписание: ' + ', '.join(bad)


def test_next_hour_at_moves_to_tomorrow_after_the_hour():
    """Час уже прошёл — пачка едет на завтра, а не в прошлое.

    Ошибка знака здесь даёт `due_at` в прошлом, и событие уходит немедленно отдельным
    письмом: дайджест внешне «не работает», а причина в одной строке арифметики.
    """
    from datetime import datetime, timedelta

    from app.notify.outward import schedule

    # 07:00 по времени площадки: девятичасовая пачка ещё сегодня.
    base = datetime(2026, 9, 15, 4, 0)             # UTC, площадка = МСК
    assert schedule.next_hour_at(base, 0, 9) - base == timedelta(hours=2)
    # 10:00 по времени площадки: девятичасовая — уже завтра.
    base = datetime(2026, 9, 15, 7, 0)
    assert schedule.next_hour_at(base, 0, 9) - base == timedelta(hours=23)


def test_the_digest_hour_cannot_be_set_inside_quiet_hours():
    """Час дайджеста внутри тишины не сохраняется.

    Поломка была бы ТИХОЙ: экран показал бы сохранённые числа, а площадка просто
    перестала бы получать дайджесты — письмо ждало бы конца тишины, а очередь к тому
    времени уже считала бы его отправленным. Поэтому запрет стоит на записи, а не
    подсказкой рядом с полем.
    """
    from fastapi import HTTPException

    from app.database import SessionLocal
    from app.routers.cabinets import NotifyHoursIn, set_notify_hours

    user = SimpleNamespace(role=SimpleNamespace(key='admin'), id=None, name='прибор')
    db = SessionLocal()
    try:
        with pytest.raises(HTTPException) as e:
            set_notify_hours(NotifyHoursIn(digest=3, quiet_from=21, quiet_to=9), db, user)
        assert e.value.status_code == 400
        assert 'не уйдёт никогда' in e.value.detail

        # А час вне тишины проходит — и возвращается тем же ответом.
        out = set_notify_hours(NotifyHoursIn(digest=12, quiet_from=21, quiet_to=9), db, user)
        assert out['digest'] == 12
    finally:
        db.execute(text("DELETE FROM company_settings WHERE key = 'cabinet_notify_hours'"))
        db.commit()
        db.close()


def test_saved_hours_reach_the_sender():
    """Настройка доезжает до отправки, а не остаётся числом на экране.

    Проверяется связка целиком: сохранили 12:00 — расписание отдаёт 12, и срок ближайшей
    пачки считается от него. Без этого прибора «поменял час, ничего не изменилось» было
    бы неотличимо от «не сохранилось».
    """
    from datetime import datetime

    from app.database import SessionLocal
    from app.notify.outward import schedule
    from app.routers.cabinets import NotifyHoursIn, set_notify_hours

    user = SimpleNamespace(role=SimpleNamespace(key='admin'), id=None, name='прибор')
    db = SessionLocal()
    try:
        set_notify_hours(NotifyHoursIn(digest=12, quiet_from=22, quiet_to=8), db, user)
        assert schedule.hours(db) == (12, 22, 8)
        # 05:00 UTC = 08:00 МСК: тишина уже кончилась, ближайшая пачка сегодня в 12.
        base = datetime(2026, 9, 15, 5, 0)
        assert schedule.next_hour_at(base, 0, schedule.hours(db)[0]).hour == 9  # 12:00 МСК
        assert not schedule.in_quiet_hours(schedule.publisher_now(base, 0), 22, 8)
    finally:
        db.execute(text("DELETE FROM company_settings WHERE key = 'cabinet_notify_hours'"))
        db.commit()
        db.close()
        assert schedule.hours(None) == (9, 21, 9), 'умолчание сдвинулось'
