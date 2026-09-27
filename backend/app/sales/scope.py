"""Область видимости сделок: «свои» / «все».

Вынесено из `routers/sales_dashboard.py` 27.09.2026, когда появился второй потребитель —
глобальный поиск (`app/search`). Правило «что реестр показывает, то и поиск находит»
держится только если функция одна: две копии условия видимости расходятся молча.
Роутеры продолжают звать её под старыми именами `_own_rep_ids_or_all` / `_apply_own_scope`
— их ищут приборы `test_deal_scope` и `test_scope_defaults`.
"""
from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import User
from app.sales.models import SalesDeal, SalesRep


def own_rep_ids_or_all(db: Session, user: User, section: str = "sales_registry"):
    """Видимость сделок роли для конкретной страницы продаж. None — «все» (без
    ограничения). Список id — «только свои»: сделки, где пользователь сейлз или
    аккаунт (SalesRep.user_id). Пустой список у 'own' без привязки → ничего.
    section — какая страница спрашивает (у каждой свой deals_scope)."""
    if user.role.key == "admin":
        return None
    from app.models import RolePermission
    row = (db.query(RolePermission)
           .filter(RolePermission.role_id == user.role_id,
                   RolePermission.section == section).first())
    if row is None:
        # ⚠ АСИММЕТРИЯ УМОЛЧАНИЯ, из-за которой это и написано.
        #
        # ОТСУТСТВИЕ той же самой строки `role_permissions` означает в двух местах
        # ПРОТИВОПОЛОЖНОЕ: в `require_permission` — «запрещено», здесь — «все сделки».
        # То есть роль, которой выдали `creatives`, но не завели строку `sales_registry`,
        # получала доступ ко ВСЕМ чужим сделкам в сборке запуска — молча и по умолчанию
        # (F1-05 внешнего аудита 11.09.2026).
        #
        # Сегодня не стреляет: строка `sales_registry` есть у всех одиннадцати
        # неадминских ролей (замер 11.09.2026), а `own` встречается дважды и обе — у
        # годового плана. Но это свойство ДАННЫХ, а не кода: первая же новая роль,
        # заведённая без неё, откроет чужие сделки.
        #
        # Отказываем ВСЛУХ, а не сужаем до «своих»: сужение дало бы второй тихий отказ —
        # человек с правом видел бы пустой экран и не понимал почему. Текст говорит
        # администратору, что именно настроить.
        raise HTTPException(
            status_code=403,
            detail=(f"Для роли «{user.role.label}» не настроена видимость сделок в "
                    f"разделе «{section}». Пока её нет, показывать чужие сделки нельзя. "
                    f"Откройте Настройки → Роли и задайте область («свои» или «все»)."))
    if (row.deals_scope or "all") != "own":
        return None
    return [r.id for r in db.query(SalesRep.id).filter(SalesRep.user_id == user.id).all()]


def apply_own_scope(q, own_ids):
    """Ограничивает выборку своими сделками, если роль — 'own'."""
    if own_ids is None:
        return q
    ids = own_ids or [-1]   # нет привязки к сейлзу → пустая выдача, а не «все»
    return q.filter(or_(SalesDeal.sales_rep_id.in_(ids),
                        SalesDeal.account_manager_id.in_(ids)))
