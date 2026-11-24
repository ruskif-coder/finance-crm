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


def _owners_ok(owners, own) -> bool:
    """Одно правило «свои ВСЕ сделки пакета» для обоих путей: по одному пакету и пачкой.

    Две копии условия разошлись бы молча — вкладка реестра и счётчик в меню считали бы разное."""
    from app.routers.sales_dashboard import _deal_owned
    return own is None or all(_deal_owned(rep, acc, own) for rep, acc in owners)


def all_in_scope(db: Session, m, own) -> bool:
    """Строгое правило — как у карточки и архива: свои ВСЕ сделки пакета. Реестр, кандидаты на присоединение (аудит 21.10.2026)."""
    return _owners_ok(package_owners(db, m), own)


def ids_all_in_scope(db: Session, ids, own) -> list:
    """Какие из пакетов целиком в области «свои» — одним запросом владельцев, без чтения пакета по одному.

    Нужно счётчику в меню (24.11.2026): он опрашивается с каждой страницы раз в минуту, и повторять
    `all_in_scope` на каждый пакет значило бы N запросов на каждый опрос. Правило то же — `_owners_ok`;
    поэтому число в меню и вкладка реестра считают одно и то же."""
    ids = list(ids)
    if own is None or not ids:
        return ids if own is None else []
    rows = db.execute(text(
        "SELECT i.master_deal_id, d.sales_rep_id, d.account_manager_id FROM master_deal_items i "
        "JOIN sales_deals d ON d.id = i.deal_id WHERE i.master_deal_id = ANY(:ids)"), {"ids": ids}).all()
    owners = {}
    for mid, rep, acc in rows:
        owners.setdefault(mid, []).append((rep, acc))
    return [i for i in ids if _owners_ok(owners.get(i, []), own)]


def can_special(db: Session, user) -> bool:
    """Право вкладки «Спец. условия» (`sk_special`) — с ним в эффективности видна ещё «маржа с доп. СК» (владелец 27.10.2026)."""
    from app.permissions import get_permissions_for_user
    try:
        return bool(get_permissions_for_user(db, user).get("sk_special", {}).get("view"))
    except AttributeError:
        return False


def can_finance(db: Session, user) -> bool:
    """Право «Эффективность мастер-сделок» — прибыль и маржа отдаются только с ним (админ — всегда)."""
    from app.permissions import get_permissions_for_user
    try:
        return bool(get_permissions_for_user(db, user).get("master_deals_finance", {}).get("view"))
    except AttributeError:          # служебный вызов без пользователя
        return False
