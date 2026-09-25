# -*- coding: utf-8 -*-
"""Бот кабинета площадок: отдельный контур на общем протоколе.

Решение владельца 15.09.2026, и оба его половины проверяются здесь.

**Бот отдельный.** Свой токен, своё имя, свой вебхук, своя таблица привязок. Площадка
видит бота подрядчика, а не наш внутренний алёрт-бот, и обработчик `/start` не гадает,
чей перед ним код. Общий токен на два контура выглядел бы экономией ровно до первого
чужого кода.

**Бот подключает человек себе сам.** Почту включаем мы — галочкой «получает уведомления»
в карточке контакта; чат в телеграме за него завести нельзя в принципе. Отсюда следствие,
которое легко потерять при рефакторинге: получатели бота и получатели почты — РАЗНЫЕ
списки, и связывать их нельзя.
"""
import inspect

import pytest

from app.notify import telegram


def test_two_contours_never_share_a_token(monkeypatch):
    """Токены не смешиваются. Проверка на подстановке, а не на живом .env: на стенде
    задан в лучшем случае один из двух, и «оба пусты» доказывало бы только это."""
    monkeypatch.setenv(telegram.ENV_TOKEN_STAFF, "staff-token")
    monkeypatch.setenv(telegram.ENV_TOKEN_PUB, "pub-token")
    assert telegram.bot_token(telegram.STAFF) == "staff-token"
    assert telegram.bot_token(telegram.PUB) == "pub-token"

    # И наоборот: настроенность одного контура не делает настроенным другой.
    monkeypatch.delenv(telegram.ENV_TOKEN_PUB)
    assert telegram.configured(telegram.STAFF)
    assert not telegram.configured(telegram.PUB)


def test_default_contour_is_the_staff_one(monkeypatch):
    """Умолчание — внутренний контур. Тридцать с лишним вызовов `send_message` написаны
    без параметра, и смена умолчания увела бы всю внутреннюю рассылку в чужого бота."""
    monkeypatch.setenv(telegram.ENV_TOKEN_STAFF, "staff-token")
    monkeypatch.delenv(telegram.ENV_TOKEN_PUB, raising=False)
    assert telegram.bot_token() == "staff-token"
    assert telegram.configured() is True


def test_missing_token_names_the_variable(monkeypatch):
    """«Не задан TELEGRAM_PUB_BOT_TOKEN» лечится за минуту, «бот не настроен» — за час."""
    monkeypatch.delenv(telegram.ENV_TOKEN_PUB, raising=False)
    with pytest.raises(RuntimeError) as e:
        telegram.send_message("1", "проба", contour=telegram.PUB)
    assert telegram.ENV_TOKEN_PUB in str(e.value)


def test_pub_webhook_is_reachable_from_the_internet():
    """Вебхук НЕ под `/api/cabinet-gw/` — тот префикс Caddy закрывает 404 намеренно.

    Дефект был бы тихим ровно того сорта, который здесь уже ловили: локально всё зелено,
    а на проде апдейты Телеграма уходят в 404, привязка молчит, и человек читает это как
    «мне не приходит код».
    """
    from app.main import app
    paths = {r.path for r in app.routes}
    assert "/api/pub-bot/webhook/{secret}" in paths
    assert not any(p.startswith("/api/cabinet-gw") and "webhook" in p for p in paths), (
        'вебхук стоит за закрытым на Caddy префиксом')


def test_webhook_secrets_are_different_variables():
    """У каждого бота свой секрет вебхука.

    Общий означал бы, что апдейт одного бота принимается адресом другого: код привязки
    из кабинета сработал бы на внутреннем вебхуке и не нашёлся бы там, а человек увидел
    бы «код не найден» при верном коде.
    """
    from app.routers import cabinet_gateway as gw
    from app.routers import notify_settings as ns
    assert 'TELEGRAM_PUB_WEBHOOK_SECRET' in inspect.getsource(gw.cabinet_tg_webhook)
    assert 'TELEGRAM_WEBHOOK_SECRET' in inspect.getsource(ns.tg_webhook)


def test_webhook_takes_only_code_and_chat_id():
    """Апдейт приходит СНАРУЖИ и доверять ему нельзя. Разбор общий с внутренним контуром
    — и это правильно: два разбора недоверенного ввода разошлись бы."""
    code, chat = telegram.parse_start_command(
        {"message": {"text": "/start A1B2C3D4E5", "chat": {"id": 777},
                     "from": {"id": 1, "is_bot": False}, "entities": [{"type": "bot_command"}]}})
    assert (code, chat) == ("A1B2C3D4E5", "777")

    # Не команда — код не выдаётся, что бы в сообщении ни было написано.
    assert telegram.parse_start_command(
        {"message": {"text": "дайте код A1B2C3D4E5", "chat": {"id": 777}}})[0] is None


def test_relinking_drops_the_old_chat():
    """«Подключить заново» обязано сбрасывать прежний чат.

    Иначе сообщения продолжали бы идти туда, откуда человек ушёл, — а он бы считал, что
    отключился: на экране в этот момент показан новый код, то есть система выглядит
    непривязанной.
    """
    from app.routers import cabinet_gateway as gw
    src = inspect.getsource(gw.cabinet_tg_link)
    assert 'row.chat_id, row.verified_at = None, None' in src


def test_bot_recipients_are_not_the_mail_recipients():
    """Получателей бота ищем по ПРИВЯЗКАМ УЧЁТОК, а не по галочке контакта.

    Это разные множества по решению владельца: почта — наше включение, бот — личное.
    Соблазн переиспользовать `_recipients` здесь велик и ошибочен: письмо ушло бы тому,
    кто бота не подключал, а подключивший без галочки не получил бы ничего.
    """
    from app.notify.outward import send
    src = inspect.getsource(send._to_bot)
    assert 'cabinet_account_tg' in src
    assert '_recipients' not in src, 'бот адресуется по списку почты'
    assert 'verified_at IS NOT NULL' in src, 'пишем в неподтверждённый чат'


def test_bot_respects_quiet_hours():
    """Ночью бот молчит — снаружи мы не сотрудники друг другу.

    Отличие от почты: письмо ждёт утра в очереди, а сообщение бота не уходит вовсе,
    очереди у него пока нет. Потерей это не является — то же событие лежит в панели, —
    но написано это должно быть в коде, а не подразумеваться.
    """
    from app.notify.outward import send
    src = inspect.getsource(send._to_bot)
    assert 'in_quiet_hours' in src


def test_linking_is_written_to_the_feed():
    """Привязка и отвязка попадают в ленту.

    Через полгода «почему ему перестало приходить» должно иметь ответ в системе, а не в
    памяти того, кто нажимал кнопку.
    """
    from app.cabinet import journal
    from app.routers import cabinet_gateway as gw
    assert 'бот_привязан' in journal.BY_KEY and 'бот_отвязан' in journal.BY_KEY
    # Разбор апдейта вынесен из ручки в `handle_pub_update` 21.09.2026 — его зовут
    # и вебхук, и опрос (`app/notify/tg_poll.py`). Правило не изменилось, у него
    # сменился дом; прибор смотрит туда, где правило живёт теперь.
    assert 'бот_привязан' in inspect.getsource(gw.handle_pub_update)
    assert 'бот_отвязан' in inspect.getsource(gw.cabinet_tg_unlink)


def test_a_bare_code_is_accepted_too():
    """Человек присылает КОД, а не команду `/start`.

    В инструкции написано «отправьте код боту» — слова `/start` площадка в глаза не
    видела. До 18.09.2026 такое сообщение молча игнорировалось, и со стороны это
    выглядело как «бот не подключается»: пишешь — в ответ тишина.
    """
    from app.notify.telegram import parse_start_command as parse

    def upd(text):
        return {"message": {"text": text, "chat": {"id": 42}}}

    assert parse(upd("/start A1B2C3D4E5")) == ("A1B2C3D4E5", "42")   # диплинк, как было
    assert parse(upd("A1B2C3D4E5")) == ("A1B2C3D4E5", "42")          # голый код
    assert parse(upd("a1b2c3d4e5")) == ("A1B2C3D4E5", "42")          # регистр не важен
    assert parse(upd("  A1B2C3D4E5  ")) == ("A1B2C3D4E5", "42")      # с пробелами


def test_chatter_is_not_mistaken_for_a_code():
    """Кодом считаем только одиночное слово нужного вида: иначе чужая фраза однажды
    совпадёт с чьим-то кодом, и бот привяжется не к тому человеку."""
    from app.notify.telegram import parse_start_command as parse

    def upd(text):
        return {"message": {"text": text, "chat": {"id": 42}}}

    for text in ("привет", "A1B2C3D4E5 и ещё что-то", "ABCDEFG", "12345", "/help"):
        assert parse(upd(text))[0] is None, text
    # chat_id возвращаем всегда: на любое сообщение бот обязан ответить, а для ответа
    # нужен адрес. Молчание человек читает как поломку.
    assert parse(upd("привет"))[1] == "42"


def test_a_suspended_cabinet_gets_nothing_from_the_bot():
    """Аудит 23.09.2026, 5.M6. Приостановленный кабинет не видит ничего (`scope`), а бот
    продолжал писать его учёткам: приостановка останавливала экран, но не уведомления.
    Правило то же, что у видимости, — только активный кабинет."""
    from app.notify.outward import send
    src = inspect.getsource(send._to_bot)
    assert "state = 'активен'" in src, 'бот пишет учёткам приостановленного кабинета'
