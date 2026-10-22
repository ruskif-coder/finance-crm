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


# ── ДС (аудит 21.10.2026) ─────────────────────────────────────────────────────────────────────────
# Документ закрывает несколько сделок (разнесение выручки) или целый мастер-пакет. Правило — как у карточки мастер-сделки:
# ДС «свой», если свои ВСЕ его сделки (в нём суммы и реквизиты каждой); ДС без сделок — только автору.

def annex_owners(db: Session, annex_ids) -> dict:
    """{annex_id: [(продавец, аккаунт) каждой сделки]} — по разнесению и по составу мастер-пакета, одним запросом."""
    from sqlalchemy import text
    ids = [int(i) for i in annex_ids]
    out = {i: [] for i in ids}
    if not ids:
        return out
    for aid, rep, acc in db.execute(text("""
            SELECT x.annex_id, d.sales_rep_id, d.account_manager_id FROM (
                SELECT annex_id, deal_id FROM sales_deal_annex_allocation WHERE annex_id = ANY(:ids)
                UNION
                SELECT a.id, i.deal_id FROM sales_annexes a JOIN master_deal_items i ON i.master_deal_id = a.master_deal_id
                 WHERE a.id = ANY(:ids)
            ) x JOIN sales_deals d ON d.id = x.deal_id"""), {"ids": ids}).all():
        out[aid].append((rep, acc))
    return out


def annex_visible(owners, own, created_by, user_id) -> bool:
    if own is None:
        return True
    ids = set(own or ())
    if not owners:
        return created_by is not None and created_by == user_id
    return all(rep in ids or acc in ids for rep, acc in owners)


def annex_in_scope(db: Session, user, annex) -> None:
    """403, если ДС вне области «свои» пользователя. Для «все»/admin — без ограничения."""
    own = own_rep_ids_or_all(db, user, "sales_registry")
    if own is None:
        return
    if not annex_visible(annex_owners(db, [annex.id])[annex.id], own, getattr(annex, "created_by", None),
                         getattr(user, "id", None)):
        raise HTTPException(status_code=403, detail="Приложение вне вашей зоны видимости: в нём чужие сделки")
