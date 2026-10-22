# -*- coding: utf-8 -*-
"""Кто что видит в мастер-сделке: область «свои» и право на эффективность. Отдельно от роутера — ими пользуются карточка,
реестр и проверки ручек; ответ здесь — да/нет, отказ HTTP формирует роутер."""
from sqlalchemy import text
from sqlalchemy.orm import Session


def package_owners(db: Session, m) -> list:
    """(продавец, аккаунт) каждой сделки пакета — для проверки области «свои»."""
    return db.execute(text(
        "SELECT d.sales_rep_id, d.account_manager_id FROM master_deal_items i "
        "JOIN sales_deals d ON d.id = i.deal_id WHERE i.master_deal_id = :m"), {"m": m.id}).all()


def own_reps(db: Session, user):
    """id «своих» продавцов/аккаунтов пользователя; None — видит всё. Область — от реестра сделок (16.10.2026)."""
    from app.routers.sales_dashboard import _own_rep_ids_or_all
    return _own_rep_ids_or_all(db, user, "sales_registry")


def in_scope(db: Session, m, own) -> bool:
    """Пакет ищется по коду, мимо `SalesDeal`: роль «свои» видит его, если в нём есть хоть одна её сделка."""
    from app.routers.sales_dashboard import _deal_owned
    return own is None or any(_deal_owned(rep, acc, own) for rep, acc in package_owners(db, m))


def all_in_scope(db: Session, m, own) -> bool:
    """Строгое правило — как у карточки и архива: свои ВСЕ сделки пакета. Реестр, кандидаты на присоединение (аудит 21.10.2026)."""
    from app.routers.sales_dashboard import _deal_owned
    return own is None or all(_deal_owned(rep, acc, own) for rep, acc in package_owners(db, m))


def can_finance(db: Session, user) -> bool:
    """Право «Эффективность мастер-сделок» — прибыль и маржа отдаются только с ним (админ — всегда)."""
    from app.permissions import get_permissions_for_user
    try:
        return bool(get_permissions_for_user(db, user).get("master_deals_finance", {}).get("view"))
    except AttributeError:          # служебный вызов без пользователя
        return False
