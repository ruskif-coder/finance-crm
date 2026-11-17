# -*- coding: utf-8 -*-
"""Реестр медиапланов v2 (хендофф 17.11.2026): признаки строки, которых нет в самом плане.

Реестр показывает у каждой строки:

* **этап сделки** — одну из восьми групп («без сделки», «МП подготовка», «МП отправлено», «Бронь», «Сборка», «В
  размещении», «Закрытие», «Архив · срывы»). Владелец 17.11.2026 выбрал группы, а не пятнадцать стадий справочника:
  чипы стадий над таблицей должны помещаться в одну строку. В самой строке стадия остаётся точной (`deal_stage`);
* **замок** — `''` (правится из реестра), `'sent'` (план отдан клиенту — правка из реестра переписала бы версию, сервер
  отвечает 409 всем), `'fixed'` (сделка на «Сборке» и дальше — открыто только администратору и мастер-аккаунту).
  Правило ровно серверное: `media_plans._plan_is_sealed` и `plan_lock.stage_locks_plan`. Экран показывает замок ДО клика,
  а не `alert` с 409 после него;
* **виза** — то же условие, что плашка «Требуется виза» на карточке сделки (владелец 17.11.2026: «как на карточке»): у
  плана нет `verified_at`, и сделка не в терминальной стадии;
* **кто обновил** — последнее действие с этой версией в журнале. Своей колонки «кем обновлён» у плана нет (схему не
  трогаем); у планов, которые создала система (годовой план, продление), записи о них в журнале нет вовсе — они
  подписываются «система · годовой план» / «система · продление»;
* **мой** — тот же признак «свой», что у области `own` (`media_plans._plan_owned`).

Всё — пачкой на весь реестр, без запроса на строку.
"""
from __future__ import annotations

from typing import Dict, Iterable, Optional

from sqlalchemy import text as sa_text

# Порядок = порядок чипов над таблицей и сортировки «Сделка · стадия» по группе.
BUCKETS = (
    ("none", "без сделки"),
    ("prep", "МП подготовка"),
    ("sent", "МП отправлено"),
    ("booking", "Бронь"),
    ("assembly", "Сборка"),
    ("launch", "В размещении"),
    ("closing", "Закрытие"),
    ("done", "Архив · срывы"),
)
BUCKET_LABEL = dict(BUCKETS)

# Ключ стадии справочника → группа реестра. Первая стадия цепочки — «МП подготовка» — отличается от «МП отправлено» не
# ключом (у обеих `media_plan`), а местом: её распознаёт `bucket_of` по `first_id`.
_KEY_BUCKET = {
    "media_plan": "sent",
    "booking": "booking",
    "launch_prep": "assembly",
    "launch": "launch",
    "closing": "closing",
    "closing_fact": "closing",
    "archive": "done",
}

# Что считается «обновлением» плана в журнале. Удаление — нет: удалённая версия в реестр не попадает.
_TOUCH_ACTIONS = ("create_media_plan", "update_media_plan", "patch_media_plan", "media_plan_verified",
                  "verify_media_plan", "media_plan_change_note", "media_plan_locked_edit",
                  "link_deal_media_plan", "save_deal_brief_mp")

SYSTEM_YEAR = "система · годовой план"
SYSTEM_PROLONG = "система · продление"


def bucket_of(stage, first_id: Optional[int]) -> str:
    """Группа реестра для стадии сделки плана. Нет сделки — «без сделки»; терминальная — «Архив · срывы»."""
    if stage is None:
        return "none"
    if stage.is_terminal:
        return "done"
    if first_id is not None and stage.id == first_id:
        return "prep"
    # Незнакомый ключ (новая стадия без ключа) — к «МП отправлено» не относим: ставим в «Закрытие» только то, что
    # им размечено, остальное — по месту в цепочке ниже, в `registry_extras`.
    return _KEY_BUCKET.get(stage.stage_key or "", "")


def lock_of(stage, first_id: Optional[int], locks: bool) -> str:
    """Замок строки: '' — правится из реестра, 'sent' — отдан клиенту, 'fixed' — зафиксирован на «Сборке» и дальше."""
    if stage is None:
        return ""
    if locks:
        return "fixed"
    if first_id is not None and stage.id != first_id:
        return "sent"
    return ""


def needs_visa(verified_at, stage) -> bool:
    """«Нужна виза» — как на карточке сделки: нет визы, и сделка не в терминальной стадии."""
    return verified_at is None and not (stage is not None and stage.is_terminal)


def _last_touch(db, plan_ids: Iterable[int]) -> Dict[int, str]:
    """Кто последним трогал версию — по журналу. Имя из журнала (`user_name`), а не из `users`: удалённый пользователь
    в журнале остаётся подписанным."""
    ids = list(plan_ids)
    if not ids:
        return {}
    rows = db.execute(sa_text(
        "SELECT DISTINCT ON (entity_id) entity_id, user_name FROM audit_log "
        "WHERE entity_type = 'media_plan' AND entity_id = ANY(:i) AND action = ANY(:a) "
        "ORDER BY entity_id, created_at DESC, id DESC"),
        {"i": ids, "a": list(_TOUCH_ACTIONS)}).all()
    return {pid: name for pid, name in rows if name}


def _origin(year_plan_line_id, prolonged_from_id) -> Optional[str]:
    """Кем рождён план без записи в журнале: конвейером годового плана или продлением. Иначе — неизвестно."""
    if year_plan_line_id:
        return SYSTEM_YEAR
    if prolonged_from_id:
        return SYSTEM_PROLONG
    return None


def registry_extras(db, plans, user, owned) -> Dict[int, dict]:
    """Признаки строк реестра для списка последних версий `plans`. `owned(plan, user)` — правило «свой» из роутера."""
    from app.sales.catalog import Catalog
    from app.sales import plan_lock
    from app.sales.models import SalesDeal

    cat = Catalog(db)
    first = cat.first()
    first_id = first.id if first else None
    pos = {s.id: i for i, s in enumerate(cat.stages)}

    deal_ids = {p.deal_id for p in plans if p.deal_id}
    deals = {}
    if deal_ids:
        for did, sid, yline, prolong in (db.query(SalesDeal.id, SalesDeal.our_stage_id, SalesDeal.year_plan_line_id,
                                                   SalesDeal.prolonged_from_id)
                                         .filter(SalesDeal.id.in_(deal_ids)).all()):
            deals[did] = (cat.by_id.get(sid), _origin(yline, prolong))

    touched = _last_touch(db, (p.id for p in plans))
    out = {}
    for p in plans:
        stage, origin = deals.get(p.deal_id, (None, None)) if p.deal_id else (None, None)
        bucket = bucket_of(stage, first_id)
        if not bucket:
            # Стадия без знакомого ключа: до «Сборки» — «МП отправлено», после — «Закрытие».
            bucket = "closing" if plan_lock.stage_locks_plan(cat, stage.id) else "sent"
        who = touched.get(p.id)
        out[p.id] = {
            "stage_bucket": bucket,
            "stage_pos": pos.get(stage.id) if stage is not None else -1,
            "lock": lock_of(stage, first_id, bool(stage) and plan_lock.stage_locks_plan(cat, stage.id)),
            "verified": p.verified_at is not None,
            "needs_visa": needs_visa(p.verified_at, stage),
            # Нет записи в журнале и сделка не системная — план старше журнала: «кто» не знаем и не выдумываем.
            "updated_by": who or origin,
            "updated_by_system": who is None and origin is not None,
            "mine": bool(owned(p, user)),
        }
    return out
