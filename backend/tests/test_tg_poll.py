# -*- coding: utf-8 -*-
"""Опрос Телеграма: приём сообщений без входящих соединений.

Прибор стоит на трёх местах, где ошибка тихая:

  · **разбор общий с вебхуком.** Две копии разошлись бы молча: привязка по опросу
    сработала бы иначе, чем по вебхуку, и заметили бы это по жалобе площадки;
  · **смещение двигается после КАЖДОГО апдейта, включая сбойный.** Иначе одно кривое
    сообщение встаёт поперёк очереди навсегда и хоронит все следующие;
  · **вебхук и опрос несовместимы**: пока вебхук стоит, Телеграм отвечает на getUpdates
    отказом 409. Это должно читаться как инструкция, а не как «связь оборвалась».

Сети в тестах нет — транспорт подменяется, как в тестах коннекторов ОРД и DSP.
"""


import pytest

import app.notify.models  # noqa: F401
import app.ord.models  # noqa: F401
from app.database import SessionLocal
from app.notify import tg_poll


def _purge(session):
    """Опрос хранит ДВА ключа — смещение и отметку живости. Фикстура сперва чистила
    только смещение, и отметка оседала на стенде (поймано прогоном 21.09.2026)."""
    from sqlalchemy import text as _t
    session.execute(_t("delete from company_settings where key like 'tg_poll_%тест%'"))
    session.commit()


@pytest.fixture
def db():
    session = SessionLocal()
    _purge(session)
    try:
        yield session
    finally:
        session.rollback()
        _purge(session)
        session.close()


def _patch_transport(monkeypatch, fn):
    """Подменить единственный выход в сеть.

    С 21.09.2026 запрос идёт через `opener.open` (появился прокси), а не через
    `urllib.request.urlopen` напрямую — шов переехал, поведение прежнее.
    """
    class _Opener:
        handlers = []

        def open(self, req, timeout=None):
            return fn(req, timeout)

    monkeypatch.setattr(tg_poll, '_opener', lambda: _Opener())


def _msg(update_id, text_='/start ABC123', chat=777):
    return {"update_id": update_id,
            "message": {"chat": {"id": chat}, "text": text_}}


def test_handler_is_shared_with_the_webhook():
    """Опрос обязан звать ТОТ ЖЕ разбор, что и ручка вебхука."""
    import inspect
    src = inspect.getsource(tg_poll._handle_pub)
    assert 'handle_pub_update' in src, (
        'опрос перестал звать общий разбор — появится вторая реализация привязки')

    from app.routers import cabinet_gateway as gw
    web = inspect.getsource(gw.cabinet_tg_webhook)
    assert 'handle_pub_update' in web, (
        'вебхук перестал звать общий разбор — две копии разойдутся молча')


def test_offset_moves_even_when_an_update_breaks(db, monkeypatch):
    """Сбой на одном сообщении не хоронит следующие."""
    seen = []

    def _boom(_db, u):
        seen.append(u["update_id"])
        if u["update_id"] == 11:
            raise RuntimeError('кривой апдейт')

    monkeypatch.setattr(tg_poll.telegram, 'bot_token', lambda c=None: 'токен')
    monkeypatch.setattr(tg_poll, '_call',
                        lambda *a, **k: {"result": [_msg(10), _msg(11), _msg(12)]})
    saved = []
    monkeypatch.setattr(tg_poll, '_save_offset',
                        lambda _db, c, v: saved.append(v))

    n = tg_poll.poll_once(db, 'тест', _boom)
    assert n == 3
    assert seen == [10, 11, 12], 'после сбоя разбор следующих сообщений прекратился'
    assert saved == [11, 12, 13], 'смещение не подтвердило сбойный апдейт — он вернётся вечно'


def test_conflict_409_is_explained_not_swallowed(db, monkeypatch, caplog):
    """409 значит «вебхук ещё стоит» — человек должен прочитать именно это."""
    import urllib.error

    monkeypatch.setattr(tg_poll.telegram, 'bot_token', lambda c=None: 'токен')

    def _conflict(*a, **k):
        raise urllib.error.HTTPError('u', 409, 'Conflict', {}, None)

    monkeypatch.setattr(tg_poll, '_call', _conflict)
    with caplog.at_level('ERROR'):
        assert tg_poll.poll_once(db, 'тест', lambda *_: None) == 0
    assert any('вебхук' in r.message or 'вебхук' in str(r.args) for r in caplog.records), \
        'отказ 409 записан как безликая ошибка связи'


def test_missing_token_is_not_an_error(db, monkeypatch):
    """Контур без токена — не настроен, а не сломан: молча пропускаем."""
    monkeypatch.setattr(tg_poll.telegram, 'bot_token', lambda c=None: None)
    assert tg_poll.poll_once(db, 'тест', lambda *_: None) == 0


def test_offset_survives_a_broken_value(db, monkeypatch):
    """Испорченное значение в настройках не должно останавливать приём."""
    from sqlalchemy import text as _t
    db.execute(_t("insert into company_settings (key, value) values "
                  "('tg_poll_offset_тест', 'не число') "
                  "on conflict (key) do update set value = excluded.value"))
    db.commit()
    assert tg_poll._offset(db, 'тест') == 0
    db.execute(_t("delete from company_settings where key = 'tg_poll_offset_тест'"))
    db.commit()


def test_drop_webhook_keeps_pending_updates():
    """Снимая вебхук, нельзя выбрасывать накопленное: там живые «Старт»."""
    calls = []
    import types
    fake = types.SimpleNamespace(bot_token=lambda c=None: 'токен',
                                 token_var=lambda c=None: 'TELEGRAM_PUB_BOT_TOKEN')
    real_tg, real_call = tg_poll.telegram, tg_poll._call
    tg_poll.telegram = fake
    tg_poll._call = lambda tok, method, params=None, timeout=None: (
        calls.append((method, params or {})) or {"ok": True})
    try:
        tg_poll.drop_webhook('тест')
    finally:
        tg_poll.telegram, tg_poll._call = real_tg, real_call
    assert calls and calls[0][0] == 'deleteWebhook'
    assert 'drop_pending_updates' not in calls[0][1], (
        'снятие вебхука начало выбрасывать висящие апдейты — это сообщения людей, '
        'которые уже нажали «Старт»')


def test_only_messages_are_requested(db, monkeypatch):
    """Просим только сообщения: остальные типы апдейтов нам не нужны и не должны
    занимать очередь."""
    captured = {}

    monkeypatch.setattr(tg_poll.telegram, 'bot_token', lambda c=None: 'токен')

    def _grab(token, method, params=None, timeout=None):
        captured.update(params or {})
        return {"result": []}

    monkeypatch.setattr(tg_poll, '_call', _grab)
    tg_poll.poll_once(db, 'тест', lambda *_: None)
    assert 'message' in (captured.get('allowed_updates') or '')
    assert captured.get('timeout') == tg_poll.LONG_POLL_SECONDS


def test_poll_interval_cannot_outlast_the_cron_minute():
    """Длинный запрос короче минуты: перехлёст двух запусков даёт 409 и тишину."""
    assert tg_poll.LONG_POLL_SECONDS < 60


def test_network_failure_is_retried(db, monkeypatch):
    """Рваная связь лечится повтором — без него молчит каждый четвёртый опрос.

    Замер 21.09.2026: жив один адрес Телеграма из восьми, и он отвечает примерно в трёх
    случаях из четырёх. Прибор на то, чтобы повтор не сняли «за ненадобностью».
    """
    tries = {'n': 0}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"result": []}'

    def _flaky(*a, **k):
        tries['n'] += 1
        if tries['n'] < 3:
            raise TimeoutError('таймаут')
        return _Resp()

    monkeypatch.setattr(tg_poll.telegram, 'bot_token', lambda c=None: 'токен')
    _patch_transport(monkeypatch, _flaky)
    # _call сам повторяет — poll_once об этом знать не должен
    assert tg_poll.poll_once(db, 'тест', lambda *_: None) == 0
    assert tries['n'] == 3, 'повтор сетевого отказа пропал'


def test_telegram_error_code_is_not_retried(db, monkeypatch):
    """Отказ Телеграма кодом повторять нельзя: 409 и 400 от повтора не изменятся."""
    import urllib.error
    tries = {'n': 0}

    def _refuse(*a, **k):
        tries['n'] += 1
        raise urllib.error.HTTPError('u', 409, 'Conflict', {}, None)

    monkeypatch.setattr(tg_poll.telegram, 'bot_token', lambda c=None: 'токен')
    _patch_transport(monkeypatch, _refuse)
    assert tg_poll.poll_once(db, 'тест', lambda *_: None) == 0
    assert tries['n'] == 1, 'отказ кодом ушёл в повтор — так 409 превратится в тишину'


def test_second_run_does_not_re_read_the_same_messages(db, monkeypatch):
    """Повторный запуск не разбирает уже разобранное.

    Смещение — единственная защита от этого: Телеграм отдаёт апдейт снова и снова,
    пока его не подтвердили. Без подтверждения площадка получала бы «Готово» каждую
    минуту, а мы — бесконечную переобработку одного сообщения.
    """
    from sqlalchemy import text as _t
    calls = []
    handled = []

    monkeypatch.setattr(tg_poll.telegram, 'bot_token', lambda c=None: 'токен')

    def _fake(token, method, params=None, timeout=None):
        calls.append(dict(params or {}))
        # Телеграм отдаёт сообщения только пока они не подтверждены смещением
        return {"result": [] if (params or {}).get('offset') else [_msg(500)]}

    monkeypatch.setattr(tg_poll, '_call', _fake)
    try:
        assert tg_poll.poll_once(db, 'тест', lambda _d, u: handled.append(u['update_id'])) == 1
        assert tg_poll.poll_once(db, 'тест', lambda _d, u: handled.append(u['update_id'])) == 0
        assert handled == [500], 'сообщение разобрано дважды'
        assert 'offset' not in calls[0], 'первый заход не должен слать смещение'
        assert calls[1].get('offset') == 501, 'второй заход не подтвердил прочитанное'
    finally:
        db.execute(_t("delete from company_settings where key = 'tg_poll_offset_тест'"))
        db.commit()


def test_retry_count_has_one_home():
    """Число попыток — одно на весь контур Телеграма.

    21.09.2026 оно на час оказалось записано дважды: литералом в `send_message` и
    константой в опросе. Обоснование у них было одно и то же, а правка тронула бы
    только одно место — классическое расхождение, которое не падает, а тихо меняет
    поведение половины контура.
    """
    from app.notify import telegram
    assert tg_poll.ATTEMPTS is telegram.ATTEMPTS
    assert tg_poll.API is telegram.API, 'адрес API снова объявлен отдельно'


# ПРО КРОН ПРИБОРА ЗДЕСЬ НЕТ, И ЭТО НАЗВАНО ВСЛУХ. Тест, который читал бы
# `docs/CRON_после_релиза.md`, внутри контейнера всегда пропускался бы: docs/ в образ не
# кладут (проверено 21.09.2026), а контейнер — единственное место, где гоняются гейты.
# Пропускающийся тест хуже отсутствующего: он выглядит защитой и ничего не держит.
#
# Пропавшую строку крона ловит проверка ниже: пока опрос не отработал ни разу, экран
# состояния показывает красное с текстом «крон не поставлен».


def test_status_screen_watches_the_poll():
    """Экран состояния обязан видеть мёртвый опрос.

    Соседняя проверка `check_telegram_live` судит по очереди у Телеграма, а у бота
    площадок вебхук снят — очередь всегда пуста, и мёртвый крон выглядел бы здоровым.
    Прибор на то, чтобы проверку не убрали «как дублирующую».
    """
    from app.system import status
    assert hasattr(status, 'check_pub_bot_poll')
    import inspect
    src = inspect.getsource(status.status_report if hasattr(status, 'status_report')
                            else status)
    assert 'check_pub_bot_poll' in src, 'проверка опроса больше не собирается в отчёт'


# ── прокси до Телеграма ──────────────────────────────────────────────────────

def test_proxy_is_read_from_one_place():
    """Адрес прокси читается в одном месте — `telegram.proxy`.

    Четыре точки выхода в Телеграм (отправка, getMe, опрос, проверка состояния) обязаны
    ходить одним путём: проверка, ходящая мимо прокси, отчиталась бы о связи, которой
    приложение не пользуется.
    """
    import inspect
    from app.notify import telegram
    from app.system import status

    assert telegram.proxy() is None or isinstance(telegram.proxy(), str)
    assert 'proxy=proxy()' in inspect.getsource(telegram.send_message), \
        'отправка перестала передавать прокси'
    assert 'telegram.proxy()' in inspect.getsource(tg_poll._opener), \
        'опрос берёт прокси не из общего места'
    assert '_tg.proxy()' in inspect.getsource(status.check_telegram_live), \
        'живая проверка Телеграма ходит мимо прокси'


def test_poll_goes_through_the_proxy_when_set(db, monkeypatch):
    """Задан прокси — запрос уходит через него, а не напрямую."""
    monkeypatch.setenv('TELEGRAM_PROXY_URL', 'http://user:pass@proxy.invalid:3128')
    opener = tg_poll._opener()
    handlers = {type(h).__name__: h for h in opener.handlers}
    assert 'ProxyHandler' in handlers
    assert handlers['ProxyHandler'].proxies.get('https') == 'http://user:pass@proxy.invalid:3128'


def test_no_proxy_means_direct(db, monkeypatch):
    """Пустая переменная — ходим напрямую. Это рабочее состояние, а не поломка."""
    monkeypatch.delenv('TELEGRAM_PROXY_URL', raising=False)
    opener = tg_poll._opener()
    proxies = [h for h in opener.handlers
               if type(h).__name__ == 'ProxyHandler' and getattr(h, 'proxies', None)]
    assert not proxies, 'без переменной запрос всё равно пошёл через прокси'


# ── оба контура ──────────────────────────────────────────────────────────────

def test_both_bots_are_polled():
    """Внутренний бот тоже на опросе.

    21.09.2026 на опрос перевели только бота площадок, и через десять минут стало
    видно, чего это стоит: пять сообщений внутреннему боту зависли у Телеграма
    недоставленными, а человек видел тишину. Болезнь у ботов одна.
    """
    from app.notify import telegram
    assert set(tg_poll.HANDLERS) == {telegram.PUB, telegram.STAFF}


def test_staff_handler_is_shared_with_its_webhook():
    """Опрос внутреннего бота зовёт ТОТ ЖЕ разбор, что и его ручка."""
    import inspect
    from app.routers import notify_settings as ns
    assert 'handle_staff_update' in inspect.getsource(tg_poll._handle_staff)
    assert 'handle_staff_update' in inspect.getsource(ns.tg_webhook), \
        'ручка внутреннего бота перестала звать общий разбор'


def test_one_cron_line_covers_every_contour(monkeypatch):
    """Без аргумента обходим ВСЕ контуры — одна строка крона на всех.

    Вторая строка крона была бы вторым местом, где помнят список ботов, и новый бот
    однажды остался бы без приёма молча.
    """
    seen = []
    monkeypatch.setattr(tg_poll, 'poll_once',
                        lambda db, c, h: seen.append(c) or 0)
    monkeypatch.setattr(tg_poll, 'SessionLocal', lambda: _FakeSession())
    assert tg_poll.main([]) == 0
    assert set(seen) == set(tg_poll.HANDLERS), 'опрос обошёл не все контуры'


class _FakeSession:
    def close(self):
        pass


def test_unknown_contour_is_refused(monkeypatch):
    monkeypatch.setattr(tg_poll, 'SessionLocal', lambda: _FakeSession())
    assert tg_poll.main(['--contour', 'нетакого']) == 2


def test_token_cannot_reach_the_log_through_httpx(monkeypatch, capsys):
    """Токен лежит в адресе запроса, а httpx на уровне INFO печатает адрес целиком.

    Поймано 21.09.2026 на первом боевом запуске: вывод разового прогона показал
    `api.telegram.org/bot<ТОКЕН>/sendMessage`. В файлы тогда не попало, но следующий
    прогон крона записал бы. Прибор на то, чтобы шумные логгеры не расшумелись снова.
    """
    import logging
    for noisy in ('httpx', 'httpcore', 'urllib3'):
        logging.getLogger(noisy).setLevel(logging.NOTSET)

    monkeypatch.setattr(tg_poll, 'SessionLocal', lambda: _FakeSession())
    monkeypatch.setattr(tg_poll, 'poll_once', lambda db, c, h: 0)
    tg_poll.main([])

    for noisy in ('httpx', 'httpcore', 'urllib3'):
        lvl = logging.getLogger(noisy).level
        assert lvl >= logging.WARNING, (
            f'логгер {noisy} снова печатает адреса запросов — токен уедет в лог крона')
