"""
Тесты системы уведомлений (app/notify).

Проверяется то, что ломается молча: реестр, ссылающийся на несуществующий резолвер
(событие просто никому не уйдёт), и правила выбора каналов — в частности, что событие
с locked=True нельзя оставить совсем без доставки и что автор действия не получает
уведомление о собственном действии.
"""
import pytest

from app.notify import registry
from app.notify.bus import emit
from app.notify.recipients import RESOLVERS


# ---- целостность реестра ----

def test_every_recipient_spec_is_resolvable():
    for ev in registry.EVENTS.values():
        for spec in ev.recipients:
            assert spec["type"] in ("resolver", "role", "user"), (ev.key, spec)
            if spec["type"] == "resolver":
                assert spec["value"] in RESOLVERS, f"{ev.key}: нет резолвера {spec['value']}"


def test_directions_and_channels_are_known():
    dirs = {k for k, _ in registry.DIRECTIONS}
    for ev in registry.EVENTS.values():
        assert ev.direction in dirs, ev.key
        assert ev.tone in ("danger", "warning", "success", "info"), ev.key
        for ch in ev.channels:
            assert ch in registry.CHANNELS, (ev.key, ch)


def test_mp_events_registered():
    """Четыре живых события МП должны существовать под теми же ключами, что и раньше —
    иначе строки в notifications, созданные до переезда, потеряют оформление."""
    for key in ("mp_submit", "mp_approved", "mp_rejected", "mp_archived", "mp_recalled"):
        assert registry.get(key) is not None, key


# ---- emit ----

class FakeSession:
    """Минимальная замена сессии: emit при переданных user_ids ходит только в add/flush."""
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = len(self.added)


class Actor:
    def __init__(self, uid):
        self.id = uid


def test_unknown_event_raises():
    with pytest.raises(ValueError):
        emit(FakeSession(), "no_such_event", title="x", user_ids=[1])


def test_actor_does_not_notify_himself(monkeypatch):
    monkeypatch.setattr("app.notify.bus._channels_for", lambda db, uid, ev: ["app"])
    db = FakeSession()
    got = emit(db, "mp_approved", title="МП согласован", user_ids=[7, 9], actor=Actor(7))
    assert got == [9]


def test_disabled_subscription_is_logged_not_silent(monkeypatch):
    """Отключённое событие должно оставлять след в журнале отправок: иначе спор
    «мне не приходило» неразрешим."""
    monkeypatch.setattr("app.notify.bus._channels_for", lambda db, uid, ev: [])
    db = FakeSession()
    got = emit(db, "mp_archived", title="МП в архиве", user_ids=[5])
    assert got == []
    row = db.added[-1]
    assert row.status == "suppressed" and row.suppress_reason == "disabled"


def test_pending_channels_are_queued(monkeypatch):
    """Ненастроенный канал не теряет сообщение: без TELEGRAM_BOT_TOKEN строка
    обязана лечь в журнал как queued и уйти позже (app/notify/dispatch.py)."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr("app.notify.bus._channels_for", lambda db, uid, ev: ["app", "tg"])
    db = FakeSession()
    emit(db, "mp_submit", title="Новый МП", user_ids=[3])
    statuses = {(r.channel, r.status) for r in db.added if hasattr(r, "status")}
    assert ("app", "sent") in statuses
    assert ("tg", "queued") in statuses
    tg = [r for r in db.added if getattr(r, "channel", None) == "tg"][0]
    assert tg.suppress_reason == "no_channel"


# ---- каденция сканера ----
# Главное свойство: повтор считается от ФАКТА последней отправки, а не по календарю,
# иначе пропущенный прогон = потерянное напоминание.

from datetime import datetime, timedelta
from app.notify.scanner import Hit, _should_send


class St:
    def __init__(self, last_sent_at=None, stage=None):
        self.last_sent_at, self.stage = last_sent_at, stage


NOW = datetime(2026, 8, 15, 9, 0)


def _hit(stage="due"):
    return Hit("operation", 1, stage, "тест")


def test_first_time_always_sends():
    assert _should_send(St(), _hit(), 10, NOW) is True


def test_interval_not_passed_is_skipped():
    assert _should_send(St(NOW - timedelta(days=9), "due"), _hit(), 10, NOW) is False


def test_missed_run_is_caught_up():
    """Сканер не отработал вовремя — на следующем прогоне прошло 11 дней, шлём."""
    assert _should_send(St(NOW - timedelta(days=11), "due"), _hit(), 10, NOW) is True


def test_stage_change_sends_immediately():
    """Переход «срок наступил» → «просрочено» не ждёт конца интервала."""
    assert _should_send(St(NOW - timedelta(days=1), "due"), _hit("overdue"), 10, NOW) is True


def test_scanner_rules_are_registered():
    """Функция сканера без записи в реестре не запустится — и наоборот."""
    from app.notify.scanner import RULES
    for key in RULES:
        ev = registry.get(key)
        assert ev is not None, f"правило {key} не объявлено в реестре"
        assert ev.scan is True, f"{key}: в реестре не помечено как сканерное"


# ---- тихие часы ----

from app.notify.bus import _quiet_now


class Ch:
    def __init__(self, quiet_from=None, quiet_to=None, mute_until=None):
        self.quiet_from, self.quiet_to, self.mute_until = quiet_from, quiet_to, mute_until


def test_quiet_hours_none_means_always_allowed():
    assert _quiet_now(Ch(), registry.get("mp_submit")) is False
    assert _quiet_now(None, registry.get("mp_submit")) is False


def test_locked_event_ignores_quiet_hours():
    """Отказ по МП и просрочка не ждут утра — на то они и «нельзя отключить»."""
    ev = registry.get("mp_rejected")
    assert ev.locked is True
    assert _quiet_now(Ch(0, 23), ev) is False


def test_mute_until_blocks(monkeypatch):
    from datetime import date, timedelta
    assert _quiet_now(Ch(mute_until=date.today() + timedelta(days=1)),
                      registry.get("mp_submit")) is True
    assert _quiet_now(Ch(mute_until=date.today() - timedelta(days=1)),
                      registry.get("mp_submit")) is False


# ---- разбор апдейта вебхука (недоверенный вход) ----

from app.notify.telegram import parse_start_command


def test_parse_start_extracts_code_and_chat():
    code, chat = parse_start_command({"message": {"text": "/start a1b2c3", "chat": {"id": 42}}})
    assert (code, chat) == ("A1B2C3", "42")


def test_parse_ignores_everything_but_start():
    """Из апдейта берём только два поля и только в ожидаемом формате: тело приходит
    снаружи и командой для нас не является."""
    code, chat = parse_start_command({"message": {"text": "удали всё", "chat": {"id": 42}}})
    assert code is None and chat == "42"
    assert parse_start_command({}) == (None, None)
    assert parse_start_command({"message": {"text": "/start", "chat": {"id": 7}}}) == (None, "7")


# ---- кнопка «перейти в бота» ----

def test_bot_name_is_normalised_from_any_spelling():
    """@name, name и целая ссылка должны давать один и тот же юзернейм.

    Имя вписывают в .env руками, и три написания встречаются вперемешку. Без
    нормализации получается адрес t.me/@name — кнопка ведёт в никуда, а выглядит
    рабочей.
    """
    from app.notify.telegram import _clean_name
    for raw in ('SimbAD_alert_bot', '@SimbAD_alert_bot', 'https://t.me/SimbAD_alert_bot',
                'https://t.me/SimbAD_alert_bot/', '  @SimbAD_alert_bot  ',
                'https://t.me/SimbAD_alert_bot?start=X'):
        assert _clean_name(raw) == 'SimbAD_alert_bot', raw
    assert _clean_name('') is None and _clean_name('@') is None


def test_link_code_fits_telegram_deeplink_payload():
    """Код уезжает в ?start=<код>, а Telegram принимает там только A-Z a-z 0-9 _ -.

    Гейт стоит на генераторе кода: если его когда-нибудь заменят на base64 или
    добавят разделитель, ручная отправка «/start КОД» продолжит работать, а кнопка
    молча перестанет — ровно тот отказ, который никто не связывает с генератором.
    """
    import re
    from app.notify.telegram import new_link_code
    for _ in range(50):
        code, _exp = new_link_code()
        assert re.fullmatch(r'[A-Za-z0-9_-]{1,64}', code), code


def test_username_comes_from_telegram_not_from_env(monkeypatch):
    """getMe важнее .env: юзернейм — свойство токена, а не строки, набранной руками."""
    import app.notify.telegram as T
    T._USERNAME_CACHE.clear()
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'tok-1')
    monkeypatch.setenv('TELEGRAM_BOT_NAME', 'старое_имя')

    class _R:
        status_code = 200

        @staticmethod
        def json():
            return {'ok': True, 'result': {'username': 'SimbAD_alert_bot'}}

    monkeypatch.setattr(T.httpx, 'get', lambda *a, **k: _R())
    assert T.bot_username() == 'SimbAD_alert_bot'
    assert T.link_url('A1B2C3') == 'https://t.me/SimbAD_alert_bot?start=A1B2C3'


def test_username_falls_back_to_env_when_telegram_unreachable(monkeypatch):
    """Сеть недоступна — привязка не ломается, просто берём то, что записано."""
    import app.notify.telegram as T
    T._USERNAME_CACHE.clear()
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'tok-2')
    monkeypatch.setenv('TELEGRAM_BOT_NAME', '@SimbAD_alert_bot')

    def _boom(*a, **k):
        raise RuntimeError('нет сети')

    monkeypatch.setattr(T.httpx, 'get', _boom)
    assert T.bot_username() == 'SimbAD_alert_bot'


def test_no_bot_name_means_no_button_not_a_broken_one(monkeypatch):
    """Имя неизвестно — ссылки нет вовсе. Экран покажет код, а не мёртвую кнопку."""
    import app.notify.telegram as T
    T._USERNAME_CACHE.clear()
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN', raising=False)
    monkeypatch.delenv('TELEGRAM_BOT_NAME', raising=False)
    assert T.bot_username() is None
    assert T.link_url('A1B2C3') is None


# ---- сейлзовые события ----

def test_sales_events_registered():
    """Шесть событий сейлзового направления. Ключ события — то, что записано в подписках
    у живых людей: переименование молча отнимет у них настройку."""
    keys = {"deal_booked", "deal_lost", "deal_done",
            "plan_deals_generated", "plan_month_empty", "mp_draft_stale"}
    assert keys <= set(registry.EVENTS)
    for k in keys:
        assert registry.get(k).direction == "sales", k


def test_move_event_key_lost_wins_over_terminal():
    """Стадия срыва тоже терминальная — без проверки is_lost первым срыв уехал бы
    в «сделка доведена», то есть в поздравление."""
    from app.routers.sales_dashboard import move_event_key
    assert move_event_key(None, True, True, None) == "deal_lost"
    assert move_event_key("closing_fact", False, True, "archive") == "deal_done"


def test_move_event_key_booking_only_on_entry():
    from app.routers.sales_dashboard import move_event_key
    assert move_event_key("media_plan", False, False, "booking") == "deal_booked"
    # перестановка внутри брони (у неё две стадии) — не «ушла в бронь» второй раз
    assert move_event_key("booking", False, False, "booking") is None
    assert move_event_key("booking", False, False, "launch") is None


def test_plan_month_stage_window():
    """Окно напоминания про пустую ячейку плана: рано — молчим, месяц начался —
    просрочено, слишком давно — снова молчим (это разбор истории, а не работа)."""
    from app.notify.scanner import plan_month_stage
    from datetime import date
    today = date(2026, 8, 22)
    assert plan_month_stage(date(2026, 10, 1), today, 14) is None      # ещё рано
    assert plan_month_stage(date(2026, 9, 1), today, 14) == "soon"     # старт близко
    assert plan_month_stage(date(2026, 8, 1), today, 14) == "overdue"  # месяц идёт
    assert plan_month_stage(date(2026, 5, 1), today, 14) is None       # за горизонтом
