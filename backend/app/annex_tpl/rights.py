# -*- coding: utf-8 -*-
"""Право на «Заголовок» и «Место и дату» ДС в шаблоне (владелец 05.11.2026: мастер аккаунт и админ; из карточки ДС убрано вечером).

Отдельного раздела не заводили: это ромб «согласование» у «Мастер-сделок» (`master_deals.approve`) — тот же, что даёт менять
даты РК во внешнем ДС. Одна функция на всех, кто спрашивает: роутер шаблонов и форма внешнего ДС (даты РК).
"""
from fastapi import HTTPException

HEAD_PLACE = ("head", "place")


def may_edit_head(db, user) -> bool:
    from app.permissions import get_permissions_for_user
    return bool((get_permissions_for_user(db, user).get("master_deals") or {}).get("approve"))


def _texts(blocks) -> dict:
    return {b["sys"]: (b.get("text") or "").strip() for b in blocks or [] if b.get("sys") in HEAD_PLACE}


def assert_head_place_unchanged_or_allowed(db, user, old_blocks, new_blocks) -> None:
    """Текст заголовка и места в шаблоне поменялся — нужно право; без изменений шаблон сохраняет любой, кто правит шаблоны."""
    if _texts(old_blocks) != _texts(new_blocks) and not may_edit_head(db, user):
        raise HTTPException(403, "Заголовок и «место и дату» правит мастер аккаунт или админ (право «Мастер-сделки · согласование»)")
