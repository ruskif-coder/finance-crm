# -*- coding: utf-8 -*-
"""Лента кабинета: запись о том, что мы площадке отправили.

Появилась 15.09.2026. До неё в кабинете не было ни ленты, ни способа увидеть, что мы
вообще что-то отправляли: журнал `cabinet_log` с самого начала объявлен «журналом с двумя
читателями — админом и самой площадкой», и второй читатель полтора месяца не имел к нему
доступа.

**Лента — НЕ КАНАЛ ДОСТАВКИ.** В первой редакции экрана она стояла колонкой «Панель ·
всегда», и владелец это снял: «в панели нету уведомлений у паблишеров». Выключателя у неё
нет по той же причине, по какой его нет у истории переписки, — это журнал, а не рассылка.

Главный прибор файла от этого не изменился: **у каждого построенного вида рассылки есть
событие ленты**. Разойдись пара — в журнале осталась бы дыра ровно там, где нужен ответ
на вопрос «а отправляли ли вообще»: отправку видно было бы только в почтовом логе, и
только если почта настроена.
"""
import inspect

from app.cabinet import journal
from app.notify.outward import send
from app.notify.outward.kinds import KINDS


def test_every_built_kind_lands_in_the_feed():
    """Построенный вид обязан оставлять след в ленте.

    Иначе «мы вам писали» / «нам не приходило» упирается в то, что записи нет ни у кого.
    """
    missing = [k.key for k in KINDS if k.built and k.key not in send.JOURNAL_ACTION]
    assert not missing, (
        'вид отправляется, а в панели его нет: ' + ', '.join(missing))


def test_panel_actions_exist_in_the_dictionary():
    """Ключ события ленты — не свободная строка: `journal.write` отказывает неизвестному,
    и опечатка здесь уронила бы отправку целиком, а не только строку панели."""
    unknown = [v for v in send.JOURNAL_ACTION.values() if v not in journal.BY_KEY]
    assert not unknown, 'нет в словаре журнала: ' + ', '.join(unknown)


def test_feed_is_written_before_the_mail_gates():
    """Лента пишется ДО проверок почты, и это главное в порядке вызовов.

    Ненастроенная почта не означает, что события не было. Стой запись после
    `mailc.configured()`, стенд без почты не показывал бы площадке ничего — и выглядело
    бы это как «уведомления не работают», хотя не работает один канал из двух.

    Прибор смотрит на ИСХОДНИК: поднимать здесь живую отправку значит тащить контакты,
    кабинет и SMTP, а вопрос ровно один — что раньше в тексте функции.
    """
    src = inspect.getsource(send.notify_publisher)
    assert '_to_panel' in src, 'панель не вызывается вовсе'
    assert src.index('_to_panel') < src.index('mailc.configured'), (
        'панель пишется после проверки почты — на стенде без почты ленты не будет')


def test_only_our_own_switch_silences_the_feed():
    """Единственная ветка, где лента молчит, — вид выключен НАМИ.

    Выключатели площадки на ленту не действуют: она не канал, а журнал. Окажись чтение
    матрицы выше записи, площадка своей галочкой стирала бы историю — и «нам не
    приходило» стало бы неотличимо от «мы не отправляли».
    """
    src = inspect.getsource(send.notify_publisher)
    assert src.index('_enabled(db, kind_key)') < src.index('_to_panel')
    assert src.index('_to_panel') < src.index('prefs.matrix')


def test_feed_view_keeps_rows_without_a_publisher():
    """Лента отдаётся по КАБИНЕТУ, а не по площадке, и это не придирка.

    У «Выдан пароль» и «Вход в кабинет» `publisher_id` пуст по смыслу — они про учётку,
    а не про сайт. Фильтр по одному `publisher_id` выбросил бы их, и площадка видела бы
    половину своей же истории, не зная, что вторая есть.
    """
    from app.database import SessionLocal
    from sqlalchemy import text
    db = SessionLocal()
    try:
        sql = db.execute(text(
            "SELECT pg_get_viewdef('pub.log_v1'::regclass, true)")).scalar()
    finally:
        db.close()
    assert 'cabinet_publisher' in sql, 'лента ограничена не через кабинет'
    assert 'l.publisher_id = ANY' not in sql.replace(' ', ' '), (
        'строки без площадки выпадут из ленты')


def test_chat_id_never_leaves_the_core():
    """`chat_id` наружу не отдаётся ни одной ручкой кабинета.

    Площадке он не нужен ни для чего, а утёкший идентификатор чата — чужая точка входа:
    зная его, посторонний бот пишет человеку от нашего имени.
    """
    from app.routers import cabinet_gateway as gw
    src = inspect.getsource(gw._tg_state)
    assert 'chat_id' not in src, 'состояние привязки отдаёт номер чата'
