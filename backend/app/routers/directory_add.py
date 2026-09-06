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

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import RolePermission, User
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
