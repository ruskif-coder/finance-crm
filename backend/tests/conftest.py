# -*- coding: utf-8 -*-
"""Общая обвязка прогона: тест убирает за собой следы в журналах.

## Зачем

Набор ходит по НАСТОЯЩИМ ручкам, а те пишут в журналы — в `audit_log` через
`log_action`, в `notification_deliveries` и `notifications` через `emit`. Фикстура
откатывает свою сделку, а запись о действии над ней остаётся: она коммитится отдельно и
переживает откат. Строка о том, чего больше нет.

Замер 14.09.2026, после пятнадцати прогонов за день:

    audit_log                  45 115 строк, из них 39 136 машинным темпом
    notification_deliveries    41 292 строки, из них 40 650 машинным темпом
    notifications              38 143 строки, ВСЕ непогашенные

Последнее хуже прочего: `notifications` — это колокольчик. Тридцать восемь тысяч
тестовых строк делают панель нечитаемой, а бейдж — бессмысленным. То есть набор сломал
ровно тот экран, который сам же и проверяет.

## Как чинится

Перед тестом запоминается `max(id)` трёх таблиц, после — удаляется всё, что появилось
между. Не по имени действия и не по времени: `id` — единственный признак, который точно
отделяет «это сделал вот этот тест» от «это было раньше».

Шесть тестов чистили журнал сами, по именам своих действий. Эти уборки оставлены: они
снимают и то, что было создано ДО снимка (например, при отладке руками), и трогают
таблицы, которых здесь нет.

## Четвёртый журнал появился 15.09.2026

`cabinet_log` попал сюда вместе с ПАНЕЛЬЮ кабинета: панель — третий канал доставки, и
каждое отправленное площадке уведомление теперь оставляет в журнале строку. Прогон ходит
по настоящей передаче креатива, поэтому за один прогон набежало 17 строк вида «Креатив
передан на согласование · maksavit.ru · Дексалгин · 09.2026».

Отличить их от настоящих ПО СОДЕРЖИМОМУ нельзя — оно у них правдоподобное и настоящее,
— и это делает уборку по `id` не удобством, а единственным способом. Копились бы они в
ленте, которую читает сама площадка: тот же урок, что с колокольчиком, только наружу.

## Чего фикстура НЕ делает

Не трогает ничего, кроме четырёх журналов. Сделки, площадки, медиапланы убирают свои
фикстуры — у них есть состояние, которое проверяется, и централизованная уборка по `id`
снесла бы засев, нужный соседнему тесту.

Не работает на проде: там набор не гоняется вовсе, а `DELETE` по журналу — последнее,
что стоит уметь тестовой обвязке. Проверка — в `_stand_only`.
"""
import os

import pytest
from sqlalchemy import text

from app.database import engine

# Журналы, следы в которых убираются за каждым тестом. Только те, где строка — ЗАПИСЬ
# О СОБЫТИИ, а не состояние объекта, которое кто-то мог засеять нарочно.
JOURNALS = ("audit_log", "notification_deliveries", "notifications", "cabinet_log")


def _stand_only() -> bool:
    """Уборка журналов допустима только на стенде.

    На проде набор не запускается, но если однажды запустится — пусть не удаляет
    записи о работе людей. Признак тот же, что у скрипта уборки шума: боевой домен.
    """
    return (os.getenv("DOMAIN") or "").strip() in ("", "localhost")


@pytest.fixture(autouse=True)
def journals_stay_clean():
    """Снять за тестом строки, которые он оставил в журналах.

    `autouse` намеренно: подключать уборку в каждом тесте руками — значит забыть её в
    том единственном, который потом и насорит. Стоимость — по дешёвому запросу на журнал
    до и после; на пустом диапазоне `DELETE ... WHERE id > max` не делает ничего.
    """
    if not _stand_only():
        yield
        return

    with engine.connect() as c:
        before = {t: (c.execute(text(f"SELECT coalesce(max(id), 0) FROM {t}")).scalar()
                      or 0) for t in JOURNALS}
    try:
        yield
    finally:
        with engine.begin() as c:
            for t in JOURNALS:
                c.execute(text(f"DELETE FROM {t} WHERE id > :b"), {"b": before[t]})


# ── Наружу из теста не уходит ничего ────────────────────────────────────────────────────
#
# Ревью 23.09.2026: `test_mp_deal_scope` при сломанной проверке области видимости дошёл бы
# до `vibecode_patch` и записал бриф в НАСТОЯЩУЮ сделку Битрикса (ключ на стенде задан), а
# соседний тест — до `emit` → Telegram. Откат транзакции не возвращает ни то, ни другое:
# фикстура `db` с `commit = flush` защищает базу, а сеть — нет.
#
# Заслон стоит на уровне транспорта, а не отдельных функций: `from x import f` в модуле
# обходит подмену `x.f`, а `httpx.get` и `httpx.Client.send` ищутся в момент вызова. Внутренние
# адреса стенда (сайдкар PDF, соседние контейнеры) и `TestClient` (`testserver`) пропускаются;
# клиент с подменным транспортом (`httpx.MockTransport`) — тоже: это и есть проверка обмена.
# Тест, которому сеть действительно нужна, подменяет вызов сам — его `monkeypatch` ляжет
# поверх этого.

import smtplib                      # noqa: E402
from urllib.parse import urlsplit   # noqa: E402

import httpx                        # noqa: E402

INTERNAL_HOSTS = {"testserver", "localhost", "127.0.0.1", "pdf", "backend", "db",
                  "finance_backend", "finance_db", "cabinet_backend", "finance_pdf"}


class NetworkInTest(RuntimeError):
    """Тест пытался выйти во внешнюю систему."""


def _guard(url) -> None:
    host = urlsplit(str(url)).hostname or ""
    if host not in INTERNAL_HOSTS:
        raise NetworkInTest(f"тест пытался выйти наружу: {url} — подмените вызов в тесте")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    for name in ("get", "post", "put", "patch", "delete", "request"):
        orig = getattr(httpx, name)

        def blocked(*a, _orig=orig, _name=name, **k):
            url = (a[1] if _name == "request" and len(a) > 1 else a[0] if a else
                   k.get("url"))
            _guard(url)
            return _orig(*a, **k)
        monkeypatch.setattr(httpx, name, blocked)

    orig_send = httpx.Client.send

    def send(self, request, *a, **k):
        if not isinstance(getattr(self, "_transport", None), httpx.MockTransport):
            _guard(request.url)
        return orig_send(self, request, *a, **k)
    monkeypatch.setattr(httpx.Client, "send", send)

    def no_smtp(*a, **k):
        raise NetworkInTest("тест пытался открыть SMTP — подмените отправку в тесте")
    monkeypatch.setattr(smtplib, "SMTP", no_smtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", no_smtp)
    yield
