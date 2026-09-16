"""Экран «Справочники → Добавить данные» (/directory/add).

Ручка здесь ровно одна, и она не пишет ничего. Экран **своих писателей не завёл**: он
оркеструет существующие (контрагенты, договоры, справочники видов), и каждая из тех ручек
спрашивает своё право. Второй писатель на те же таблицы означал бы вторые правила
проверки, а в этом проекте продублированные правила уже расходились.

Тогда зачем ручка вообще. Затем, что без неё секция `directory_add` была бы галочкой в
конструкторе ролей, которая ничего не открывает: сняли её — а экран по прямому адресу
всё равно работает. Ровно это и ловит `test_registry_and_usage_match`.

Здесь же кончается вторая нечестность. До 06.09.2026 экран решал, какие блоки ему
доступны, **сам** — читая права из localStorage. Клиентское решение о правах не решение:
оно снимается инструментами браузера. Теперь набор доступных блоков считает сервер, а
экран его показывает.

Права: миграция `2026-09-06_directory_add_permission.sql`.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (Contract, Counterparty, CounterpartyBankAccount, RolePermission,
                      User)
from ..permissions import require_permission

router = APIRouter()

# Блок экрана → секция, чьё право `edit` его открывает. Тот же состав, что в BLOCKS
# на фронте: если разойдётся, экран покажет блок, который не сохранится.
BLOCK_SECTIONS = {
    "agency": "dir_agencies",
    "advertiser": "dir_advertisers",
    "publisher": "dir_publishers",
    "cp": "counterparties",
    "contract": "contracts",
}


@router.get("/context")
def add_context(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("directory_add", "view")),
):
    """Что этому человеку можно завести с экрана.

    Возвращает по блоку `true/false` и имя права, которого не хватает, — экран пишет его
    прямо в погашенном блоке, чтобы человек знал, что просить, а не гадал.
    """
    if user.role.key == "admin":
        return {"blocks": {b: True for b in BLOCK_SECTIONS}, "sections": BLOCK_SECTIONS}

    rows = {
        r.section: r
        for r in db.query(RolePermission)
        .filter(
            RolePermission.role_id == user.role_id,
            RolePermission.section.in_(set(BLOCK_SECTIONS.values())),
        )
        .all()
    }
    return {
        "blocks": {b: bool(getattr(rows.get(s), "can_edit", 0)) for b, s in BLOCK_SECTIONS.items()},
        "sections": BLOCK_SECTIONS,
    }


@router.get("/counterparties")
def lookup_counterparties(
    q: Optional[str] = None,
    limit: int = Query(8, ge=1, le=30),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("directory_add", "view")),
):
    """Поиск юрлица, чтобы ПРИКРЕПИТЬ существующее вместо заведения второго.

    Зачем отдельная ручка, а не список из реестра контрагентов. Тот список кормит
    выпадашки полудюжины экранов и отдаёт ставки НДС со статьями по умолчанию — ему
    незачем знать про использование. А здесь вопрос ровно один: «это юрлицо у нас уже
    есть и где оно уже участвует». Замер 06.09.2026: у 211 контрагентов одно юрлицо
    стоит за несколькими объектами — это норма, и заводить второе с тем же ИНН, чтобы
    потом склеивать, дороже, чем прикрепить.

    Поиск по имени И ПО ИНН: юрлицо ищут по реквизиту чаще, чем по названию — названия
    у групп компаний почти одинаковы («ОККАМ ДИДЖИТАЛ», «ОККАМ МЕДИА», «ОККАМ ГРУПП»),
    а ИНН различает их сразу. Поиск только по имени и был причиной дублей.

    Счётчики использования считаются ОДНИМ запросом на каждую связь, а не по строке:
    восемь строк выдачи иначе дают два десятка запросов на каждое нажатие клавиши.

    Ручка только читает. Писателей у экрана нет и не будет — он оркеструет чужие
    (см. докстроку модуля).
    """
    text = (q or "").strip()
    if len(text) < 2:
        return {"items": []}

    like = f"%{text}%"
    rows = (db.query(Counterparty)
            .filter(or_(Counterparty.name.ilike(like), Counterparty.inn.ilike(like)))
            .order_by(Counterparty.name)
            .limit(limit).all())
    if not rows:
        return {"items": []}

    ids = [c.id for c in rows]
    contracts = dict(db.query(Contract.counterparty_id, func.count(Contract.id))
                     .filter(Contract.counterparty_id.in_(ids))
                     .group_by(Contract.counterparty_id).all())

    # Объекты справочников, за которыми стоит это юрлицо. Три связи — три таблицы,
    # общего представления над ними нет, и заводить его ради счётчика незачем.
    from app.sales.models import (SalesAdvertiserCounterparty, SalesAgencyCounterparty,
                                  SalesPublisherCounterparty)
    objects: dict = {}
    for model in (SalesAgencyCounterparty, SalesAdvertiserCounterparty,
                  SalesPublisherCounterparty):
        for cp_id, n in (db.query(model.counterparty_id, func.count(model.id))
                         .filter(model.counterparty_id.in_(ids))
                         .group_by(model.counterparty_id).all()):
            objects[cp_id] = objects.get(cp_id, 0) + n

    return {"items": [{
        "id": c.id, "name": c.name, "inn": c.inn or "",
        "objects": objects.get(c.id, 0),
        "contracts": contracts.get(c.id, 0),
        # Чем юрлицо УЖЕ заполнено — чтобы человек видел, что достаётся вместе с ним,
        # и что придётся дозаполнить. Подписант и счёт — те самые два поля, которых
        # 06.09.2026 не было у 209 контрагентов из 211.
        "has_signer": bool((c.signer_position or "").strip() and (c.signer_basis or "").strip()),
        "has_bank": bool(db.query(CounterpartyBankAccount.id)
                         .filter(CounterpartyBankAccount.counterparty_id == c.id).first()),
    } for c in rows]}
