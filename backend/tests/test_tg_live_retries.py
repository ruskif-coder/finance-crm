# -*- coding: utf-8 -*-
"""Живая проверка Телеграма (`system.status.check_telegram_live`) — с повторными попытками (18.11.2026).

Повод: обходной прокси примерно раз в час не отвечает с первой попытки; проверка с одной попыткой давала «Отказ: Телеграм:
связь» → через 10 мин «Вернулось в норму» почти каждый час, хотя за сутки дошло 113 сообщений из 114.

Поломки, которые ловит набор:
- одна неудачная попытка снова даёт «Отказ» (возврат к одной попытке);
- отказ, когда не ответили все попытки, пропал (повторы спрятали реальный обрыв);
- ответ не с первой попытки не виден в подписи — нестабильность прокси прячется."""
import httpx
import pytest

from app.notify import telegram as TG
from app.system import status as ST


class _Resp:
    status_code = 200

    def json(self):
        return {"result": {"pending_update_count": 0}}


@pytest.fixture
def tg(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(ST, "_sleep", lambda sec: None)
    calls = {"n": 0}

    def run(fail_first: int):
        def fake_get(*a, **k):
            calls["n"] += 1
            if calls["n"] <= fail_first:
                raise httpx.ConnectTimeout("proxy did not answer")
            return _Resp()
        monkeypatch.setattr(httpx, "get", fake_get)
        return ST.check_telegram_live(), calls["n"]
    return run


def test_one_failed_attempt_is_not_a_failure(tg):
    c, n = tg(1)
    assert c["tone"] == "ok" and n == 2
    assert "со 2-й попытки" in c["value"]


def test_first_attempt_ok_has_no_note(tg):
    c, n = tg(0)
    assert c["tone"] == "ok" and n == 1 and "попытки" not in c["value"]


def test_all_attempts_failed_is_a_failure_with_reason(tg):
    c, n = tg(TG.ATTEMPTS)
    assert c["tone"] == "bad" and n == TG.ATTEMPTS
    assert "ConnectTimeout" in (c.get("note") or "")


def test_failure_alert_carries_a_check_button(monkeypatch):
    """«Отказ» уходит со ссылкой-действием, в Телеграме это кнопка «Проверить», а не строка адреса (18.11.2026).
    Поломка: ссылка без ?check=1, или кнопка не доехала до sendMessage, или адрес остался строкой в тексте."""
    from app.system import alerts as AL
    sent = {}
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("DOMAIN", "example.test")

    class _Ok:
        status_code = 200

    def fake_post(url, json=None, **k):
        sent.update(json or {})
        return _Ok()
    monkeypatch.setattr(httpx, "post", fake_post)
    TG.send_message("1", "Отказ: Телеграм: связь", link=AL.LINK_CHECK)
    assert sent["reply_markup"]["inline_keyboard"][0][0] == {"text": "Проверить", "url": "https://example.test/settings/system?check=1"}
    assert "https://" not in sent["text"]
    sent.clear()
    TG.send_message("1", "Вернулось в норму", link=AL.LINK)
    assert "reply_markup" not in sent and sent["text"].endswith("https://example.test/settings/system")
