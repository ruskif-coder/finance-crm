# -*- coding: utf-8 -*-
"""Область видимости кабинета — ОДНО правило на чтение и на запись.

Вопрос «какие площадки относятся к этой учётке» до 30.08.2026 имел в системе два разных
ответа, и они жили в разных местах:

  · **чтение** — представление `pub.account_publisher_v1`: площадки берутся от КАБИНЕТА
    (или все, если кабинет служебный);
  · **запись** — шлюз проверял `cabinet_account_publisher`, прямую связь «человек ↔
    площадка».

Пока обе таблицы заполнены согласованно, расхождения не видно. Стоит начать раздавать
площадки по кабинетам — и учётка сможет ВИДЕТЬ площадку, но получить 404 при попытке
что-то по ней сделать. Причём `CabinetAccountPublisher` был помечен замороженным ещё
28.08 («не читается: видимость считается от кабинета») — читать его снова начал код
выключателей уведомлений, написанный позже и не знавший об этом.

Решение владельца 30.08.2026: личный список не нужен, дробить доступ внутри кабинета
незачем. Правило остаётся одно — от кабинета, — и живёт здесь.

**Близнец в SQL остаётся.** Кабинет ходит в базу отдельной ролью, у которой нет доступа
к `public`, поэтому чтение обязано идти через представление, и то же правило записано в
нём ещё раз. Свести их в один текст нельзя; вместо этого их сводит прибор
`tests/test_cabinet_scope.py` — он спрашивает у обоих про каждую пару и требует
одинакового ответа.
"""
from typing import Optional, Set

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cabinet.models import Cabinet, CabinetAccount


def visible_publisher_ids(db: Session, cabinet: Optional[Cabinet]) -> Optional[Set[int]]:
    """Площадки кабинета. `None` — «все» (служебный кабинет).

    Именно `None`, а не множество всех: служебный кабинет связей НЕ ХРАНИТ, и подмена
    его на список из 41 идентификатора означала бы, что новая площадка в нём не появится
    сама. Вызывающий обязан различать эти два случая — поэтому и тип такой.
    """
    if cabinet is None:
        return set()
    if cabinet.kind == 'служебный':
        return None
    return {i for (i,) in db.execute(text(
        "SELECT publisher_id FROM cabinet_publisher WHERE cabinet_id = :c"),
        {"c": cabinet.id})}


def account_sees_publisher(db: Session, account: CabinetAccount,
                           publisher_id: int) -> bool:
    """Видит ли эта учётка эту площадку. Правило то же, что у представления.

    Состояние кабинета учитывается: у приостановленного не видно ничего, и это не
    формальность — приостановка означает «люди кабинета сразу перестают видеть задания»,
    а проверка записи, не знающая о ней, оставила бы им возможность отвечать.
    """
    if account is None or not account.cabinet_id:
        return False
    cab = db.query(Cabinet).filter(Cabinet.id == account.cabinet_id).first()
    if cab is None or cab.state != 'активен':
        return False
    ids = visible_publisher_ids(db, cab)
    return True if ids is None else publisher_id in ids
