"""Глобальный поиск: какие типы искать, с какой видимостью, в каком порядке.

Спецификация — docs/SPEC_глобальный_поиск.md (решения владельца 27.09.2026).

Скрытый тип и «ничего не нашлось» неотличимы: в ответ попадают только группы, где есть
строки, и слов «нет доступа» в нём не бывает (`test_search_hidden_is_silent`). Иначе
поиск стал бы оракулом «есть ли у нас такая сделка».

В журнал действий поиск не пишет (решение 8), в лог приложения — только длительность
медленного запроса, без его текста.
"""
import logging
import threading
import time
from collections import deque

from fastapi import HTTPException
from sqlalchemy import text

from app.permissions import get_permissions_for_user
from app.search import types as T
from app.search.classify import classify

log = logging.getLogger(__name__)

# Тип → (раздел права `view`, искатель). Порядок словаря — порядок групп в выдаче
# (решение 9), за вычетом типа, на который указал шаблон: тот идёт первым.
SEARCHERS = {
    "deal": ("sales_registry", T.deals),
    "counterparty": ("counterparties", T.counterparties),
    "contract": ("contracts", T.contracts),
    "publisher": ("dir_publishers", T.publishers),
    "advertiser": ("dir_advertisers", T.advertisers),
    "agency": ("dir_agencies", T.agencies),
    "brand": ("dir_advertisers", T.brands),
    "media_plan": ("media_plans", T.media_plans),
    "ord_contract": ("ord", T.ord_contracts),
    "erid": ("ord", T.erids),
}

Q_MIN, Q_MAX = 2, 100
STATEMENT_TIMEOUT_MS = 500
SLOW_MS = 300

# ── частота: 5 запросов в секунду на пользователя ─────────────────────────────────
RATE_PER_SEC = 5
_hits: dict = {}
_hits_lock = threading.Lock()


def reset_rate_limit():
    with _hits_lock:
        _hits.clear()


def check_rate_limit(user_id: int):
    now = time.monotonic()
    with _hits_lock:
        dq = _hits.setdefault(user_id, deque())
        while dq and now - dq[0] >= 1.0:
            dq.popleft()
        if len(dq) >= RATE_PER_SEC:
            raise HTTPException(429, "Слишком частые запросы поиска — подождите секунду")
        dq.append(now)
        if len(_hits) > 5000:          # не копить пустые очереди ушедших пользователей
            for uid in [u for u, d in _hits.items() if not d]:
                _hits.pop(uid, None)


def check_query(q: str) -> str:
    q = (q or "").strip()
    if len(q) < Q_MIN:
        raise HTTPException(400, f"Введите хотя бы {Q_MIN} символа")
    if len(q) > Q_MAX:
        raise HTTPException(400, f"Запрос длиннее {Q_MAX} символов — сократите его")
    return q


# ── видимость ───────────────────────────────────────────────────────────────────

def deal_scope(db, user):
    """Область сделок для поиска. Та же функция, что у реестра, но с ЖЁСТКИМ умолчанием:
    нет строки права — пустой список («ничего»), а не отказ и не «все». Реестр в этом
    случае отвечает 403 с подсказкой администратору; поиску подсказывать некому, а
    оракул «такая сделка есть» дороже удобства (F1-05 аудита 11.09.2026)."""
    from app.sales.scope import own_rep_ids_or_all
    try:
        return own_rep_ids_or_all(db, user, "sales_registry")
    except HTTPException:
        return []


# ЕРИД показывает код сделки и ведёт на её карточку: кроме права на ОРД нужен и просмотр
# реестра сделок. Область «свои/все» проверяет только `deals_scope`, не `view`, — без этой
# строки роль с ОРД и выключенным реестром сделок видела бы коды чужих сделок (ревью 27.09).
ALSO_NEEDS = {"erid": "sales_registry"}


def allowed_types(perms: dict):
    def can(section):
        return bool(perms.get(section, {}).get("view"))
    return [t for t, (section, _) in SEARCHERS.items()
            if can(section) and (t not in ALSO_NEEDS or can(ALSO_NEEDS[t]))]


def context(db, user):
    from app.routers.media_plans import _mp_own_only
    return {"user": user, "deals": deal_scope(db, user),
            "mp_own": _mp_own_only(db, user, "media_plans")}


def _plan(q, types, allowed):
    """Какие типы и в каком порядке искать."""
    kind = classify(q)
    wanted = [t for t in (types or []) if t in SEARCHERS] if types else None
    order = [t for t in SEARCHERS if t in allowed and (wanted is None or t in wanted)]
    if kind["types"]:
        hinted = [t for t in kind["types"] if t in order]
        return kind, hinted, order
    return kind, order, order


def run(db, user, q, types=None, per_type=5, offset=0, perms=None):
    started = time.monotonic()
    q = check_query(q)
    if perms is None:
        perms = get_permissions_for_user(db, user)
    kind, first, full = _plan(q, types, set(allowed_types(perms)))
    if not full:
        return {"groups": []}
    db.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))
    ctx = context(db, user)
    one_type = bool(types) and len(full) == 1
    off = offset if one_type else 0

    def collect(order):
        out = []
        for t in order:
            rows = SEARCHERS[t][1](db, q, per_type + 1, off, ctx)
            if rows:
                out.append({"type": t, "items": rows[:per_type], "more": len(rows) > per_type})
        return out

    from sqlalchemy.exc import OperationalError
    try:
        groups = collect(first)
        # Шаблон — догадка: шесть заглавных могут быть словом («PFIZER»), десять цифр —
        # не ИНН, а номером договора. Если среди ВИДИМОГО по подсказанным типам пусто —
        # ищем как текст по всем разрешённым. Проверка по видимым, а не по всем: иначе
        # разница в ответе выдала бы, что чужой объект с таким кодом существует.
        if not groups and first != full:
            groups = collect([t for t in full if t not in first])
    except OperationalError as e:
        # Предел времени запроса — пустой частичный ответ, а не 500 (аудит 01.10.2026,
        # С-12): строка поиска набирается по букве, следующая буква спросит снова.
        # Только отмена по пределу (57014): потерянная связь — настоящая ошибка.
        if getattr(e.orig, "pgcode", None) != "57014":
            raise
        db.rollback()
        log.warning("поиск: превышен предел %s мс", STATEMENT_TIMEOUT_MS)
        return {"groups": [], "partial": True}

    ms = (time.monotonic() - started) * 1000
    if ms > SLOW_MS:
        log.warning("поиск: медленный запрос %.0f мс, типов %d", ms, len(full))
    return {"groups": groups}
