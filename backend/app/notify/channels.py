# -*- coding: utf-8 -*-
"""Каналы доставки: как сообщение доходит до человека.

Вынесено из шины 14.09.2026 по решению владельца «собрать уведомления одним модулем».
Разделение простое и держится за него весь модуль:

    ШИНА решает КОМУ и ЧТО     (`bus.py` — подписки, профили, резолверы)
    КАНАЛЫ решают КАК          (этот файл — колокольчик, бот, почта)

Пока они жили вместе, любая правка доставки означала правку шины, а любая правка правил
адресации задевала отправку. Внешний контур (`outward/`) при этом сочинял третий ответ на
тот же вопрос, потому что дотянуться до этих функций не мог — они были приватными внутри
шины.

СТАТУС возвращается строкой `"состояние|причина"`. Причина обязательна: «не ушло» без
неё разбирается заново каждый раз, а состояний у недоставки три — не настроен канал,
тихие часы, отказ отправки, — и лечатся они по-разному.
"""
from __future__ import annotations

import os
from typing import Optional

from sqlalchemy.orm import Session

from app.models import User
from app.notify import registry, telegram
from app.notify import tone as tone_of
from app.notify.models import UserNotificationChannels
from app.mail import client as mail
from app.mail import render
from app.mail import templates as tpl
from app.mail.models import MailTemplate
from app import timez

TEMPLATE_KEY = "notify"     # шаблон письма-уведомления; правится на «Настройки → Почта»


def notify_template(db: Session):
    """Шаблон, которым уходит письмо сотруднику. Может не существовать: заводится он
    при первом открытии экрана почты, а не миграцией. Тогда письмо собирается как
    раньше — молчать об этом нельзя, но и падать не из-за чего.
    """
    return (db.query(MailTemplate)
            .filter(MailTemplate.key == TEMPLATE_KEY,
                    MailTemplate.is_active.is_(True)).first())


def deliver_digest(*, to: str, to_name: Optional[str], subject: str,
                   text: str, html: str) -> str:
    """Отправка СОБРАННОЙ пачки. Возвращает статус строкой, как остальные каналы.

    Сборка живёт в `notify/digest.py` — это правила «кому и когда», — а доставка здесь,
    потому что доставка вся здесь. Прибор `test_delivery_is_not_duplicated_by_the_contours`
    стоит ровно на этом и поймал первую редакцию сборщика, звавшую гейт напрямую.

    Тихие часы НЕ проверяются: час пачки человек задал сам, и он же назначил, когда его
    можно трогать. Проверка здесь означала бы, что письмо, назначенное на 09:30,
    отменяется тихими часами до 10:00 — и не уходит уже никогда.
    """
    if not mail.configured():
        return "queued|no_channel"
    if not mail.valid_address(to or ""):
        return "queued|no_channel"
    try:
        mail.send(to=to, subject=subject[:200], body=text, html=html, to_name=to_name)
        return "sent|"
    except mail.MailNotConfigured:
        return "queued|no_channel"
    except Exception as e:              # noqa: BLE001 — в журнал уходит любая причина
        return f"failed|{str(e)[:200]}"


def quiet_now(ch: Optional[UserNotificationChannels], ev: registry.Event) -> bool:
    """Тихие часы и «не беспокоить до». Событие с locked=True проходит сквозь них:
    отказ по сделке и просрочка не ждут утра."""
    if ch is None or ev.locked:
        return False
    # Час и день — МОСКОВСКИЕ. Контейнер живёт в UTC, и `datetime.now().hour` давал
    # сдвиг на три часа: заданные человеком тихие часы 22:00–08:00 работали как
    # 01:00–11:00. Тот же дефект, что нашёлся у тихих часов площадок 14.09.2026.
    now = timez.msk_now()
    if ch.mute_until and ch.mute_until >= now.date():
        return True
    a, b = ch.quiet_from, ch.quiet_to
    if a is None or b is None:
        return False
    h = now.hour
    return (a <= h < b) if a < b else (h >= a or h < b)   # интервал через полночь


def tg_text(title: str, body, facts=None) -> str:
    """Сообщение телеграма. Один сборщик на живую отправку и на досылку.

    Плашек в телеграме нет, поэтому факты склеиваются в строку «ключ: значение»
    — но числа те же, что в панели и в письме. Досылка обязана звать эту же
    функцию: пока она собирала текст сама, отложенное сообщение приходило одним
    заголовком без тела и без чисел.
    """
    text = title if not body else f"{title}\n{body}"
    line = render.facts_line(facts)
    return text + ("\n" + line if line else "")


def deliver_tg(db: Session, uid: int, ev: registry.Event, title: str, body: Optional[str],
                link: Optional[str], entity_type, entity_id,
                facts: Optional[list] = None) -> str:
    """Отправка в Telegram. Возвращает статус для журнала.
    Ничего не теряем: не настроен бот или не привязан чат — строка ложится в queued."""
    if not telegram.configured():       # проверяем ДО обращения к базе: бот не настроен —
        return "queued|no_channel"      # ходить за привязками незачем
    ch = (db.query(UserNotificationChannels)
          .filter(UserNotificationChannels.user_id == uid).first())
    if ch is None or not ch.tg_chat_id or not ch.tg_verified_at:
        return "queued|no_channel"
    if quiet_now(ch, ev):
        return "queued|quiet_hours"
    text = tg_text(title, body, facts)
    try:
        telegram.send_message(ch.tg_chat_id, text, link=link)
        return "sent|"
    except Exception as e:
        return f"failed|{str(e)[:200]}"


def deliver_mail(db: Session, uid: int, ev: registry.Event, title: str,
                  body: Optional[str], link: Optional[str],
                  facts: Optional[list] = None, code: Optional[str] = None) -> str:
    """Отправка письма сотруднику. Возвращает статус для журнала.

    Симметрично телеграму, и по той же причине: ничего не теряем. Почта не настроена,
    у человека нет адреса, тихие часы — строка ложится в `queued` и уходит досылкой,
    а не исчезает.

    Адрес берётся из учётки (`users.email`): в этой системе он же логин, второго
    хранилища адреса сотрудника нет и заводить его незачем.
    """
    if not mail.configured():           # проверяем ДО обращения к базе, как у бота
        return "queued|no_channel"
    u = db.query(User).filter(User.id == uid).first()
    if u is None or not mail.valid_address(u.email or ""):
        return "queued|no_channel"
    ch = (db.query(UserNotificationChannels)
          .filter(UserNotificationChannels.user_id == uid).first())
    if quiet_now(ch, ev):
        return "queued|quiet_hours"
    # Ссылку даём абсолютной: в письме относительный адрес никуда не ведёт, а
    # открывают письмо не в нашей вкладке.
    link_abs = render.abs_url(link)
    facts = list(facts or [])
    # ТЕМА И СЛОВЕСНАЯ ЧАСТЬ — ИЗ ШАБЛОНА, вёрстка остаётся кодовой. До 16.09.2026
    # шаблон `notify` лежал на экране, был доступен к правке и не влиял ни на что:
    # письмо собиралось здесь целиком. Правка текста молча ничего не меняла — худший
    # вид неработающей настройки, потому что выглядит работающей.
    subject, text = tpl.apply(
        db, TEMPLATE_KEY,
        {"заголовок": title, "текст": body or "", "ссылка": link_abs or "",
         "факты": render.facts_line(facts)},
        subject_default=title,
        text_default=render.text_body(title, body, link_abs, facts))
    # Разметка вторым куском, текст первым: письмо уходит `multipart/alternative`, и
    # получатель без картинок читает ту же правду, что и получатель с ними.
    html = render.notification_html(
        # Время в шапке — московское. `datetime.now()` внутри контейнера это UTC, и
        # получатель видел время на три часа в прошлом: правдоподобно и потому незаметно.
        when=timez.msk_now(),
        title=title, body=body, link_abs=link_abs,
        tone=tone_of.norm(getattr(ev, "tone", None)),
        tag=getattr(ev, "group", "") or "", facts=facts, code=code or "",
        action=getattr(ev, "action", "") or "Открыть",
        brand=(os.getenv("MAIL_FROM_NAME") or "SIMB-AD").strip(),
        logo_url=render.abs_url(render.LOGO_PATH),
        settings_url=render.abs_url(render.SETTINGS_PATH))
    try:
        mail.send(to=u.email, subject=subject[:200], body=text, html=html,
                  to_name=getattr(u, "name", None))
        return "sent|"
    except mail.MailNotConfigured:
        return "queued|no_channel"
    except Exception as e:              # noqa: BLE001 — в журнал уходит любая причина
        return f"failed|{str(e)[:200]}"
