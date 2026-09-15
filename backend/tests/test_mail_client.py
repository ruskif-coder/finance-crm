# -*- coding: utf-8 -*-
"""Приборы на почтовый гейт. Без сети и без почтового ящика.

Проверяется то, что ломается тихо: кодировка русского имени в заголовке, обратный адрес,
поведение при ненастроенной почте и живучесть пачки при одном плохом адресе.
"""
from email.header import decode_header

import pytest

from app.mail import client as M

ENV = {
    M.ENV_HOST: "smtp.example.test",
    M.ENV_PORT: "465",
    M.ENV_USER: "robot@example.test",
    M.ENV_PASSWORD: "x",
    M.ENV_FROM: "robot@example.test",
    M.ENV_FROM_NAME: "Симб-ЭД",
    M.ENV_SSL: "ssl",
}


@pytest.fixture
def cfg(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    return M.config()


def _box():
    sent = []
    return sent, (lambda msg: sent.append(msg))


def test_not_configured_is_its_own_error(monkeypatch):
    """«Не настроено» и «не ушло» — РАЗНЫЕ вещи.

    Первое означает «положить в очередь и ждать настройки», второе — «попытка была».
    Один тип на оба случая не дал бы отличить ненастроенный гейт от отбитого письма.
    """
    for k in ENV:
        monkeypatch.delenv(k, raising=False)
    assert not M.configured()
    with pytest.raises(M.MailNotConfigured):
        M.send(to="a@b.ru", subject="тема", body="текст")
    assert issubclass(M.MailNotConfigured, M.MailError)


def test_russian_sender_name_is_encoded(cfg):
    """Русское имя в заголовке собирается кодировщиком, а не склейкой строк.

    Склеенное «Симб-ЭД <robot@…>» у части получателей приезжает вопросительными знаками.
    """
    msg = M.build_message(to="a@b.ru", subject="Запрос ссылки", body="текст", cfg=cfg)
    raw = msg["From"]
    decoded = "".join(
        (p.decode(enc or "utf-8") if isinstance(p, bytes) else p)
        for p, enc in decode_header(raw))
    assert "Симб-ЭД" in decoded
    assert "robot@example.test" in decoded


def test_reply_to_points_at_the_person(cfg):
    """Решение владельца: письмо от системы, ответ — сотруднику."""
    msg = M.build_message(to="pub@site.ru", subject="t", body="b", cfg=cfg,
                          reply_to="manager@simb-ad.com")
    assert msg["Reply-To"] == "manager@simb-ad.com"
    assert "robot@example.test" in msg["From"]


def test_broken_reply_to_does_not_kill_the_letter(cfg):
    """Кривой адрес сотрудника — не повод не отправить письмо площадке."""
    msg = M.build_message(to="pub@site.ru", subject="t", body="b", cfg=cfg,
                          reply_to="это не адрес")
    assert msg["Reply-To"] is None
    assert msg["To"]


def test_bad_recipient_is_refused_before_smtp(cfg):
    """Адрес с пробелом или запятой сервер отвергает ВСЕЙ пачкой.

    Поэтому проверка стоит до соединения: из-за одного кривого адреса не должно не уйти
    ничего.
    """
    for bad in ("нет собаки", "a b@c.ru", "a@b.ru, c@d.ru", "<a@b.ru>", ""):
        assert not M.valid_address(bad)
    for good in ("a@b.ru", "ivan.petrov@simb-ad.com", "x_1@sub.domain.рф".replace("рф", "ru")):
        assert M.valid_address(good)
    with pytest.raises(M.MailError):
        M.build_message(to="нет собаки", subject="t", body="b", cfg=cfg)


def test_message_id_carries_our_domain(cfg):
    """Свой Message-ID: без него его ставит сервер, и ответ может не склеиться с письмом."""
    msg = M.build_message(to="a@b.ru", subject="t", body="b", cfg=cfg)
    assert msg["Message-ID"].endswith("@example.test>")


def test_send_uses_the_substituted_transport(cfg):
    sent, tr = _box()
    mid = M.send(to="a@b.ru", subject="тема", body="тело", transport=tr)
    assert len(sent) == 1
    assert sent[0]["Message-ID"] == mid
    assert sent[0].get_content().strip() == "тело"


def test_batch_survives_one_bad_address(cfg):
    """Отказ по одному адресу НЕ отменяет остальных — как у выгрузки креативов в DSP."""
    sent, tr = _box()
    out = M.send_many([
        {"to": "ok1@b.ru", "subject": "t", "body": "b"},
        {"to": "сломано", "subject": "t", "body": "b"},
        {"to": "ok2@b.ru", "subject": "t", "body": "b"},
    ], transport=tr)
    assert [r["ok"] for r in out] == [True, False, True]
    assert len(sent) == 2
    assert "error" in out[1]


def test_port_defaults_follow_the_mode(monkeypatch):
    """Порт по умолчанию зависит от режима: 465 у ssl, 587 у starttls.

    Перепутанная пара «порт × режим» даёт зависание на соединении, а не внятный отказ.
    """
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv(M.ENV_PORT, raising=False)
    monkeypatch.setenv(M.ENV_SSL, "starttls")
    assert M.config().port == 587
    monkeypatch.setenv(M.ENV_SSL, "ssl")
    assert M.config().port == 465
    monkeypatch.setenv(M.ENV_PORT, "не число")
    assert M.config().port == 465          # мусор в переменной не роняет конфигурацию


def test_empty_string_is_not_configured(monkeypatch):
    """Пустая строка ≠ незаданная переменная.

    compose подставляет умолчание, и переменная в процессе есть всегда. Проверка на
    присутствие ключа показала бы настроенную почту там, где значений нет.
    """
    for k in ENV:
        monkeypatch.setenv(k, "")
    assert not M.configured()


def test_sender_must_be_an_address_not_a_signature(monkeypatch):
    """«Настроено» означает «адрес похож на адрес», а не «строка непуста».

    Замер на проде 14.09.2026: в MAIL_FROM лежало «Уведомления SIMB-AD» — подпись вместо
    адреса. Канал числился настроенным, экран состояния показывал зелёное, а отправка
    падала в `smtplib` с «'ascii' codec can't encode characters in position 0-10»:
    конверт обязан быть ASCII. По такой ошибке причину не найти — она не называет ни
    поля, ни значения, и ушёл на это целый разбор.
    """
    from app.mail import client as mail

    monkeypatch.setenv("MAIL_SMTP_HOST", "smtp.mail.ru")
    monkeypatch.setenv("MAIL_FROM", "Уведомления SIMB-AD")
    monkeypatch.setenv("MAIL_FROM_NAME", "Уведомления SIMB-AD")
    cfg = mail.config()
    assert cfg.ok is False, "подпись вместо адреса прошла как рабочая настройка"
    assert "MAIL_FROM" in (cfg.problem or ""), "причина не называет поле"
    assert "Уведомления" in (cfg.problem or ""), "причина не называет значение"

    with pytest.raises(mail.MailNotConfigured):
        mail.build_message(to="a@b.ru", subject="тема", body="текст")

    monkeypatch.setenv("MAIL_FROM", "notify@simb-ad.com")
    cfg = mail.config()
    assert cfg.ok is True and cfg.problem is None


def test_batch_does_not_die_on_one_bad_letter(cfg):
    """Отказ по одному письму не отменяет остальные — как и обещает `send_many`.

    Обещание было в описании, но не в коде: ловился перечень из четырёх типов, а
    `smtplib` на кириллическом адресе конверта бросает `UnicodeEncodeError`. Замер
    14.09.2026 на проде: пачка из 25 писем оборвалась на первом, остальные 24 даже не
    собрались. Тип ошибки не имеет отношения к тому, должны ли уйти остальные.
    """
    sent = []

    def transport(msg):
        if "плохое" in (msg["Subject"] or ""):
            raise UnicodeEncodeError("ascii", "х", 0, 1, "нарочно")
        sent.append(msg["To"])

    res = M.send_many([
        {"to": "a@b.ru", "subject": "плохое", "body": "x"},
        {"to": "c@d.ru", "subject": "хорошее", "body": "y"},
    ], transport=transport)

    assert [r["ok"] for r in res] == [False, True], "пачка оборвалась на первом отказе"
    assert len(sent) == 1
