# -*- coding: utf-8 -*-
"""Вебхук Telegram не отправляет сообщение внутри запроса.

ПРОИСШЕСТВИЕ 08.09.2026. Люди присылали боту код привязки и не получали ничего. Диагноз:
связь с Telegram рваная по причине вне нашего кода — адрес из DNS с сервера недостижим
вовсе, рабочий закреплён через `extra_hosts`, и он сам отвечает пять раз из шести.

Код превращал редкий сетевой сбой в поломку функции: обработчик слал ответ ПРЯМО В
ЗАПРОСЕ с таймаутом 10 с, на неудачной попытке висел, Telegram не дожидался ответа и
считал доставку неуспешной. Накопилось 13 неотданных обновлений. Тихо — потому что
исходящие уведомления при этом шли нормально, и в журнале доставок всё было `sent`.

Два прибора: ответ уходит в ФОН, и обрыв соединения повторяется один раз.
"""
import httpx
import pytest

import app.ad.models           # noqa: F401
import app.launch_prep.models  # noqa: F401
import app.ord.models          # noqa: F401
from app.notify import telegram
from app.routers import notify_settings as ns


class FakeBG:
    """Подмена FastAPI BackgroundTasks: запоминает, что поставили в очередь."""

    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *a, **kw):
        self.tasks.append((fn, a, kw))


def test_reply_is_queued_not_sent_inside_request(monkeypatch):
    """Внутри запроса НИ ОДНОЙ отправки — иначе рваная связь снова уронит вебхук.

    Прибор держит саму причину происшествия: не «работает ли привязка», а «не ходит ли
    обработчик в сеть до того, как ответил Telegram».
    """
    sent = []
    monkeypatch.setattr(telegram, "send_message",
                        lambda *a, **kw: sent.append(a))
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")

    bg = FakeBG()
    # Кода в базе нет — ветка «код не найден», она тоже отвечала пользователю в запросе.
    out = ns.tg_webhook("s3cret", {"message": {"chat": {"id": "42"},
                                               "text": "/start НЕТ-КОДА"}},
                        bg, db=_DummyDB())

    assert out == {"ok": True}
    assert sent == [], "обработчик сходил в сеть внутри запроса — ровно это и ломалось"
    assert len(bg.tasks) == 1, "ответ пользователю должен уходить фоновой задачей"


def test_wrong_secret_is_404_and_touches_nothing(monkeypatch):
    """Чужой секрет — 404 и ни одной фоновой задачи. Эндпоинт публичный, и это
    единственное, что закрывает его от посторонних."""
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    bg = FakeBG()
    with pytest.raises(Exception):
        ns.tg_webhook("не-тот", {"message": {"chat": {"id": "1"}, "text": "/start x"}},
                      bg, db=_DummyDB())
    assert bg.tasks == []


def test_send_message_retries_once_on_transport_error(monkeypatch):
    """Обрыв соединения повторяется ОДИН раз.

    Отказ раз в шесть при повторе становится примерно раз в тридцать шесть. Повторяем
    только обрыв: 403 «бот не запущен» и 400 «чат не найден» от повтора не изменятся.
    """
    calls = []

    class R:
        status_code = 200

    def flaky(*a, **kw):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectTimeout("timed out")
        return R()

    monkeypatch.setattr(telegram.httpx, "post", flaky)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    telegram.send_message("42", "привет")
    assert len(calls) == 2, "первая попытка оборвалась — должна быть вторая"


def test_send_message_does_not_retry_a_refusal(monkeypatch):
    """Ответ с кодом ошибки НЕ повторяется: он не изменится, а время съест."""
    calls = []

    class R:
        status_code = 403
        text = "bot was blocked by the user"

    def refuse(*a, **kw):
        calls.append(1)
        return R()

    monkeypatch.setattr(telegram.httpx, "post", refuse)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    with pytest.raises(RuntimeError):
        telegram.send_message("42", "привет")
    assert len(calls) == 1


class _DummyDB:
    """Минимальная заглушка сессии: вебхук в этих ветках только ищет строку."""

    def query(self, *a, **kw):
        return self

    def filter(self, *a, **kw):
        return self

    def first(self):
        return None
