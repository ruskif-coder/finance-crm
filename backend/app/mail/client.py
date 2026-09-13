# -*- coding: utf-8 -*-
"""Отправка письма по SMTP. Транспорт и ничего больше.

ЕДИНСТВЕННАЯ ТОЧКА ОТПРАВКИ. Причина та же, по которой в проекте один клиент на ОРД,
один на DSP и один на Weborama: у отправки наружу есть правила, которые нельзя соблюдать
«в каждом месте по-своему» — адрес отправителя, обратный адрес, кодировка русского имени,
журнал. Второй `smtplib.SMTP` в коде означает второй набор этих правил, и они разойдутся.

КОНФИГУРАЦИЯ — ТОЛЬКО ИЗ ОКРУЖЕНИЯ, как у бота и коннекторов. Пароль почтового ящика
кладёт владелец, из переписки он не переносится. Не настроено — канал считается
ненастроенным ЧЕСТНО: `configured()` отдаёт False, письмо не теряется, а ложится в
очередь; молча проглатывать отправку нельзя.

ОТ ЧЬЕГО ИМЕНИ. Решение владельца 13.09.2026: письмо уходит ОТ СИСТЕМЫ, а `Reply-To`
ставится на сотрудника, который его инициировал. Площадка отвечает живому человеку, а
отправка при этом идёт одним каналом с одним журналом. Ящики сотрудников нам для этого
не нужны — их пароли мы не трогаем вовсе.

ПОЧЕМУ НЕ БИБЛИОТЕКА. `smtplib` и `email.message` в стандартной библиотеке умеют всё, что
здесь нужно, включая правильную кодировку русских имён в заголовках. Зависимость ради
двадцати строк — это ещё одна вещь, которую придётся обновлять.
"""
from __future__ import annotations

import logging
import os
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr
from typing import Callable, Iterable, Optional

log = logging.getLogger("finance.mail")

ENV_HOST = "MAIL_SMTP_HOST"
ENV_PORT = "MAIL_SMTP_PORT"
ENV_USER = "MAIL_SMTP_USER"
ENV_PASSWORD = "MAIL_SMTP_PASSWORD"
ENV_FROM = "MAIL_FROM"
ENV_FROM_NAME = "MAIL_FROM_NAME"
ENV_SSL = "MAIL_SMTP_SSL"          # ssl (465, по умолчанию) | starttls (587)

TIMEOUT = 30.0

# Отправка пачкой держит ОДНО соединение: почтовые провайдеры считают частые новые
# сессии подозрительными, а на дайджесте писем будет сразу много.
BATCH_RECONNECT_AFTER = 50

_ADDR_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}$")


class MailError(RuntimeError):
    """Письмо не ушло, и причина называется человеку."""


class MailNotConfigured(MailError):
    """Почта не настроена. Отдельным типом: это НЕ сбой отправки.

    Разница важна для журнала: «не настроено» означает «положить в очередь и ждать
    настройки», а сбой — «попытка была, вот ошибка». Слить их в один тип значит потом
    не отличить ненастроенный гейт от отбитого письма.
    """


def valid_address(addr: str) -> bool:
    """Адрес похож на адрес. Проверка НАМЕРЕННО грубая.

    Точную проверку почтового адреса регуляркой сделать нельзя, а строгая отсекает
    законные адреса. Задача здесь другая: не дать уйти в SMTP строке с пробелом, запятой
    или угловой скобкой — на таких сервер отвечает отказом по всей пачке, и из-за одного
    кривого адреса не уходит ничего.
    """
    return bool(_ADDR_RE.match((addr or "").strip()))


@dataclass
class MailConfig:
    host: str
    port: int
    user: str
    password: str
    sender: str
    sender_name: str
    mode: str            # ssl | starttls

    @property
    def ok(self) -> bool:
        return bool(self.host and self.sender)


def config() -> MailConfig:
    """Настройки из окружения. Пустая строка = не задано.

    Именно пустая строка, а не отсутствие ключа: compose подставляет умолчание, и
    переменная в процессе есть всегда ([[env-not-reaching-container]] — готча, на которой
    в этом проекте уже спотыкались трижды).
    """
    raw_port = (os.getenv(ENV_PORT) or "").strip()
    mode = (os.getenv(ENV_SSL) or "ssl").strip().lower()
    try:
        port = int(raw_port) if raw_port else (587 if mode == "starttls" else 465)
    except ValueError:
        port = 587 if mode == "starttls" else 465
    return MailConfig(
        host=(os.getenv(ENV_HOST) or "").strip(),
        port=port,
        user=(os.getenv(ENV_USER) or "").strip(),
        password=os.getenv(ENV_PASSWORD) or "",
        sender=(os.getenv(ENV_FROM) or "").strip(),
        sender_name=(os.getenv(ENV_FROM_NAME) or "").strip(),
        mode="starttls" if mode == "starttls" else "ssl",
    )


def configured() -> bool:
    return config().ok


def build_message(*, to: str, subject: str, body: str, cfg: Optional[MailConfig] = None,
                  reply_to: Optional[str] = None, to_name: Optional[str] = None,
                  html: Optional[str] = None) -> EmailMessage:
    """Собрать письмо. Отдельной функцией — чтобы проверять БЕЗ отправки.

    Русские имена в заголовках кодирует `formataddr`; собирать заголовок строкой нельзя —
    «Иван Петров <i@x.ru>» уедет как набор знаков вопроса у части получателей.
    """
    cfg = cfg or config()
    if not valid_address(to):
        raise MailError(f"Это не почтовый адрес: {to!r}")
    msg = EmailMessage()
    msg["From"] = formataddr((cfg.sender_name or None, cfg.sender))
    msg["To"] = formataddr((to_name or None, to.strip()))
    msg["Subject"] = subject.strip()
    # Ответ уходит СОТРУДНИКУ, а не в ящик системы (решение владельца 13.09.2026).
    # Некорректный адрес сотрудника не должен ронять письмо: без Reply-To оно всё равно
    # полезно, а вот неотправленное — нет.
    if reply_to and valid_address(reply_to):
        msg["Reply-To"] = reply_to.strip()
    elif reply_to:
        log.warning("Reply-To %r не похож на адрес — письмо уйдёт без него", reply_to)
    # Свой Message-ID с доменом отправителя: без него его подставляет сервер, и в цепочке
    # писем ответ площадки может не склеиться с исходным.
    domain = (parseaddr(cfg.sender)[1].split("@") + [""])[1]
    msg["Message-ID"] = make_msgid(domain=domain or None)
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def _connect(cfg: MailConfig):
    if cfg.mode == "starttls":
        srv = smtplib.SMTP(cfg.host, cfg.port, timeout=TIMEOUT)
        srv.ehlo()
        srv.starttls(context=ssl.create_default_context())
        srv.ehlo()
    else:
        srv = smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=TIMEOUT,
                               context=ssl.create_default_context())
    if cfg.user:
        srv.login(cfg.user, cfg.password)
    return srv


def send(*, to: str, subject: str, body: str, reply_to: Optional[str] = None,
         to_name: Optional[str] = None, html: Optional[str] = None,
         transport: Optional[Callable[[EmailMessage], None]] = None) -> str:
    """Отправить одно письмо. Возвращает Message-ID.

    `transport` подменяется в тестах — тот же приём, что у клиентов DSP, ОРД и Weborama:
    подменный транспорт описывает ВЕСЬ обмен, и приборы работают без сети и без ящика.
    """
    cfg = config()
    if not cfg.ok:
        raise MailNotConfigured(
            f"Почта не настроена: нужны {ENV_HOST} и {ENV_FROM} в .env")
    msg = build_message(to=to, subject=subject, body=body, cfg=cfg,
                        reply_to=reply_to, to_name=to_name, html=html)
    if transport is not None:
        transport(msg)
        return msg["Message-ID"]
    try:
        srv = _connect(cfg)
    except (smtplib.SMTPException, OSError, ssl.SSLError) as e:
        raise MailError(f"Почтовый сервер недоступен: {e!r}") from e
    try:
        srv.send_message(msg)
    except smtplib.SMTPException as e:
        raise MailError(f"Письмо не принято: {e!r}") from e
    finally:
        try:
            srv.quit()
        except Exception:                                  # noqa: BLE001
            pass
    log.info("Письмо отправлено: %s -> %s", subject[:60], to)
    return msg["Message-ID"]


def send_many(items: Iterable[dict], *,
              transport: Optional[Callable[[EmailMessage], None]] = None) -> list:
    """Пачка писем ОДНИМ соединением.

    Каждое письмо считается отдельно: отказ по одному адресу не отменяет остальных.
    Иначе одна опечатка в адресе останавливала бы всю рассылку — та же причина, по
    которой выгрузка креативов в DSP идёт по одному и не падает целиком.
    """
    cfg = config()
    if not cfg.ok:
        raise MailNotConfigured(
            f"Почта не настроена: нужны {ENV_HOST} и {ENV_FROM} в .env")
    out, srv, sent = [], None, 0
    try:
        for it in items:
            try:
                msg = build_message(to=it["to"], subject=it["subject"], body=it["body"],
                                    cfg=cfg, reply_to=it.get("reply_to"),
                                    to_name=it.get("to_name"), html=it.get("html"))
                if transport is not None:
                    transport(msg)
                else:
                    if srv is None or sent >= BATCH_RECONNECT_AFTER:
                        if srv is not None:
                            try:
                                srv.quit()
                            except Exception:              # noqa: BLE001
                                pass
                        srv, sent = _connect(cfg), 0
                    srv.send_message(msg)
                    sent += 1
                out.append({"to": it["to"], "ok": True, "id": msg["Message-ID"]})
            except (MailError, smtplib.SMTPException, OSError, KeyError) as e:
                out.append({"to": it.get("to"), "ok": False, "error": repr(e)[:300]})
    finally:
        if srv is not None:
            try:
                srv.quit()
            except Exception:                              # noqa: BLE001
                pass
    return out


__all__ = ["send", "send_many", "build_message", "config", "configured",
           "valid_address", "MailError", "MailNotConfigured", "MailConfig"]
