# -*- coding: utf-8 -*-
"""Сроки хранения журналов — три месяца, почте и доставкам уведомлений одинаково.

Решение владельца 14.09.2026. Проверяется не «работает ли удаление» (это SQL), а
ГРАНИЦА и ИСКЛЮЧЕНИЯ: ошибка в границе стирает сообщения раньше обещанного, а ошибка в
исключениях стирает очередь — то есть работу, которую система ещё должна сделать.

Замер на стенде 14.09.2026, ради масштаба: 15 строк почтового журнала против 40 505
строк журнала доставок. Одно событие даёт строку на каждый канал каждому получателю,
поэтому второй растёт на порядок быстрее, и срок ему нужнее.
"""
import importlib
import inspect
from datetime import date, datetime

from app import retention

SWEEP = importlib.import_module("scripts.2026-09-14_journals_sweep")


def test_three_months_back_is_the_same_day():
    """14 сентября → 14 июня. Человек, которому обещали три месяца, отсчитывает их по
    календарю: 90 дней от 14 сентября — это 16 июня, и обещание уже нарушено."""
    assert retention.JOURNAL_MONTHS == 3
    assert retention.cutoff(date(2026, 9, 14)) == datetime(2026, 6, 14)


def test_year_rolls_over():
    """Январь → октябрь предыдущего года. Вычитание месяцев без переноса года дало бы
    месяц −2, граница уехала бы в будущее — и уборка снесла бы всё."""
    assert retention.cutoff(date(2026, 1, 15)) == datetime(2025, 10, 15)
    assert retention.cutoff(date(2026, 2, 1)) == datetime(2025, 11, 1)
    assert retention.cutoff(date(2026, 3, 31)) == datetime(2025, 12, 31)


def test_day_is_clamped_to_the_short_month():
    """31 мая → 28 февраля, а не 31-е, которого не существует.

    Без зажима это `ValueError` в `datetime`, то есть уборка падает раз в несколько
    месяцев и молча не делается. Такое замечают, когда кончается диск.
    """
    assert retention.cutoff(date(2026, 5, 31)) == datetime(2026, 2, 28)
    assert retention.cutoff(date(2028, 5, 31)) == datetime(2028, 2, 29)   # високосный
    assert retention.cutoff(date(2026, 7, 31)) == datetime(2026, 4, 30)


def test_cutoff_is_always_in_the_past():
    """Граница не оказывается впереди сегодняшнего дня ни при каком дне года."""
    for m in range(1, 13):
        for d in (1, 15, 28, 30, 31):
            try:
                today = date(2026, m, d)
            except ValueError:
                continue
            assert retention.cutoff(today).date() < today


def test_queue_is_never_swept():
    """Очередь не убирается никогда, каким бы старым ни был возраст строки.

    В почтовом журнале `queued` — отложенное письмо, в журнале доставок — очередь
    дайджеста. И то и другое работа, а не история.
    """
    assert retention.KEEP_STATUSES == ("queued",)


def test_both_journals_are_covered_and_the_panel_is_not():
    """Под уборкой ровно два журнала. Строки панели (`notifications`) — не журнал, а
    СОСТОЯНИЕ объекта: оно гаснет само, когда исчезает причина, и удалять его по
    возрасту значило бы убрать с глаз живую задачу."""
    tables = {model.__tablename__ for _, model, _, _ in SWEEP.JOURNALS}
    assert tables == {"mail_log", "notification_deliveries"}


def test_sweeper_reads_the_rule_and_does_not_repeat_it():
    """Скрипт берёт срок и исключения из модуля правил, а не хранит свои.

    Два места с числом «3» разошлись бы молча: уборка пошла бы по своему сроку, а экран
    продолжал бы обещать пользователю другой.
    """
    src = inspect.getsource(SWEEP)
    assert "retention.cutoff()" in src
    assert "retention.KEEP_STATUSES" in src
    assert "JOURNAL_MONTHS = " not in src, "скрипт завёл свою копию срока"


def test_sweeper_is_dry_by_default():
    """Без `--apply` не удаляется ничего: уборка необратима, а письмо — то, на что
    ссылаются в споре с площадкой."""
    assert inspect.signature(SWEEP.sweep).parameters["apply"].default is False


def test_screen_gets_the_same_number_it_promises():
    """Срок на экране журнала приходит из того же модуля, что и уборка.

    Пока экран писал «3 месяца» своей строкой, ничто не мешало уборке жить по другому
    сроку — и разошлись бы они молча.
    """
    src = inspect.getsource(__import__("app.routers.mail_admin", fromlist=["x"]))
    assert "retention.JOURNAL_MONTHS" in src
