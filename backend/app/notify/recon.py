# -*- coding: utf-8 -*-
"""Уведомление площадке о сверке месяца — почта и бот (владелец 02.11.2026: «нужно новое уведомление почта и тг —
сверка месяца»).

До этого сверка жила только в кабинете: площадка узнавала о ней, зайдя туда сама, а срок ответа — два рабочих дня.
Устроено как запрос приоритезации: один вид («сверка»), сообщение СРАЗУ на каждом нашем шаге — отправка, «Напомнить»,
наш ответ, согласованный итог. Ответ площадки ей самой не пишем: она его и отправила.

Денег здесь нет (правило «деньги площадке не показываем»): только показы — наши, её и итог. Сбой письма не отменяет
действие: сверка отправлена и видна в кабинете независимо от почты.
"""
import logging
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.publisher_recon.service import _num   # тот же формат числа, что в переписке сверки

log = logging.getLogger("finance.publisher_recon")

KIND = "сверка"
WHY = ("новая", "напоминание", "ответ", "итог", "отозвана")


def message(why: str, month: str, ours: Optional[int], theirs: Optional[int], due: Optional[date],
            offer: Optional[int] = None, agreed: Optional[int] = None):
    """(заголовок, текст, плашки) письма. Чистая функция — её зовёт прибор."""
    if why not in WHY:
        raise ValueError(f"неизвестный шаг сверки: {why}")
    until = f" до {due.strftime('%d.%m')}" if due else ""
    title, body = {
        "новая": (f"Сверка за {month}",
                  f"Мы подвели итоги месяца. Проверьте число показов и ответьте{until}: "
                  "согласитесь или пришлите свою цифру со статистикой."),
        "напоминание": (f"Напоминание: сверка за {month} ждёт ответа",
                        f"Сверка ещё без вашего ответа. Ответьте{until}."),
        "ответ": (f"Сверка за {month}: мы ответили",
                  f"Мы ответили в переписке по сверке. Посмотрите и ответьте{until}."),
        "итог": (f"Сверка за {month} закрыта",
                 "Итог согласован. Действий не требуется."),
        # Отзыв «на корявые пальцы» (владелец 06.11.2026): сверка стёрта, придёт исправленная.
        "отозвана": (f"Сверка за {month} отозвана",
                     "Мы отозвали эту сверку, чтобы поправить данные. Отвечать на неё не нужно — исправленная придёт отдельно."),
    }[why]
    facts = []
    if why == "отозвана":
        pass
    elif why == "итог":
        facts.append(("итог показов", _num(agreed or 0)))
    else:
        if ours is not None:
            facts.append(("показов у нас", _num(ours)))
        if theirs is not None:
            facts.append(("показов у вас", _num(theirs)))
        if offer is not None and why == "ответ":
            facts.append(("предлагаем", _num(offer)))
    return title, body, facts


def to_site(db: Session, req, why: str, offer: Optional[int] = None) -> dict:
    """Сообщить площадке о шаге сверки. Зовёт ручка ПОСЛЕ коммита: рассылка фиксирует базу сама."""
    from app import periods
    from app.notify.outward import notify_publisher
    from app.sales.models import SalesPublisher
    pub = db.get(SalesPublisher, req.publisher_id)
    if pub is None:
        return {"status": "skip"}
    rc = req.recon
    month = periods.month_label(req.period)
    title, body, facts = message(why, month, rc.our_volume if rc else None, rc.their_volume if rc else None,
                                 req.due_at, offer=offer, agreed=rc.agreed_volume if rc else None)
    # Savepoint без `with` (06.11.2026, `safe.outward`): с `with db.begin_nested()` коммит отправителя ронял всё после ленты.
    from app.notify.safe import outward
    return outward(db, f"{KIND} · {why} · площадка {pub.id}", lambda: notify_publisher(
        db, KIND, pub.id, title=title, body=body, facts=facts,
        context=" · ".join(x for x in ((pub.domain or pub.name), month) if x),
        link="/", entity_type="publisher_request", entity_id=req.id, values={"период": month}))
