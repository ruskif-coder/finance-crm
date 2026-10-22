# -*- coding: utf-8 -*-
"""Матрица «что требует учёта — по услугам» (владелец 14.10.2026): все требования стадий с условием `{"service_ids": [...]}` — для каких
услуг пункт действует. Экран — вкладка в «Справочниках → Услугах». Блокирует или предупреждает — у самого пункта, одинаково для всех
услуг. Условие цикла (`closing_flow`) хранится рядом и не настраивается здесь: пункт действует, если услуга в списке И цикл совпадает.

Новая услуга получает пункты, обязательные для ВСЕХ прежних активных услуг (общие: воронка, плательщик, договор, документы…) —
`add_service`, зовётся при создании услуги; пункты отдельных услуг (креативы, ЕРИД у еФарма) ей не достаются."""
import json

from sqlalchemy import text

from app.sales import stage_checks as SC

# Смысловые блоки экрана — тот же порядок, что в docs/Учёт_по_услугам.html. Ключ не в списке — блок «Прочее».
BLOCKS = [
    ("Сделка и медиаплан", "аккаунт", "Основа сделки: что продаём, на какой период и по какой воронке.",
     ["mp_linked", "mp_verified", "service_set", "period_set", "mp_one_surface", "realization_pipeline"]),
    ("Стороны и договоры", "аккаунт", "Кто платит и по какому договору — основа ДС, счетов и закрывающих.",
     ["payer_set", "final_contract", "ord_initial_contract"]),
    ("Креативы и площадки", "аккаунт → трафик → площадки", "Баннеры и согласование с площадками.",
     ["creatives_accepted", "placements_approved", "one_pair_ready"]),
    ("Маркировка и ОРД", "аккаунт / система", "ЕРИД на креатив и отчётность в ОРД.", ["erid_issued", "ord_acts_sent"]),
    ("РК, статистика и завершение", "трафик / аккаунт", "Рекламная кампания и её завершение: трафиком или кнопками аккаунта.",
     ["campaign_ready", "weborama_pixel", "campaign_finished", "fact_collected", "account_finished"]),
    ("Документы", "аккаунт / юрист / бухгалтерия", "ДС, подписи, счёт, УПД, отчёт и ЭДО.",
     ["annex_generated", "signatory_filled", "ds_signed", "invoice_issued", "upd_issued", "report_attached", "edo_sent"]),
    ("Деньги", "финансы", "Оплата клиента.", ["payment_received"]),
]


class AssemblyError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _rows(db):
    return db.execute(text("""
        SELECT c.id, c.check_key, c.is_blocking, c.applies_when, st.name AS stage
          FROM sales_stage_checks c JOIN sales_stages st ON st.id = c.stage_id
          JOIN sales_stage_phases ph ON ph.id = st.phase_id
         ORDER BY ph.sort_order, st.sort_order, c.sort_order, c.id""")).mappings().all()


def matrix(db) -> dict:
    """Пункты, сгруппированные по смысловым блокам. Один пункт (ключ проверки) может стоять на нескольких стадиях — строка одна,
    а `rows` хранит id каждой стадийной записи: переключение услуги меняет их все разом."""
    by_key: dict = {}
    for r in _rows(db):
        aw = r["applies_when"] or {}
        it = by_key.setdefault(r["check_key"], {"key": r["check_key"], "stages": [], "rows": [], "service_ids": set(),
                                                 "blocking_ids": set(), "flow": aw.get("closing_flow"), "pixel": bool(aw.get("weborama_pixel"))})
        it["stages"].append(r["stage"])
        it["rows"].append(r["id"])
        ids = set(aw.get("service_ids") or [])
        it["service_ids"] |= ids
        blk = aw.get("blocking_service_ids")
        it["blocking_ids"] |= set(blk) if isinstance(blk, list) else (ids if r["is_blocking"] else set())
    blocks, seen = [], set()
    for title, who, desc, keys in BLOCKS + [("Прочее", "—", "Пункты без смыслового блока.", [k for k in by_key if k not in
                                                                                            {x for b in BLOCKS for x in b[3]}])]:
        items = []
        for k in keys:
            it = by_key.get(k)
            if not it or k in seen:
                continue
            seen.add(k)
            chk = SC.REGISTRY.get(k)
            # Состояние клетки по услуге: off — не требуется, warn — уведомляет, block — требуется (запирает переход).
            state = {sid: ("block" if sid in it["blocking_ids"] else "warn") for sid in it["service_ids"]}
            items.append({**it, "service_ids": sorted(it["service_ids"]), "blocking_ids": sorted(it["blocking_ids"]), "state": state,
                          "stages": list(dict.fromkeys(it["stages"])),
                          "title": chk.title if chk else k, "hint": chk.hint if chk else "", "where": SC.PLACES.get(k, ("", ""))[0]})
        if items:
            blocks.append({"title": title, "who": who, "desc": desc, "items": items})
    return {"blocks": blocks}


STATES = ("off", "warn", "block")


def set_state(db, key: str, service_id: int, state: str) -> None:
    """Состояние пункта для услуги на ВСЕХ его стадийных записях: off — не требуется, warn — уведомляет, block — требуется."""
    if state not in STATES:
        raise AssemblyError(400, "Состояние: не требуется / уведомляет / требуется")
    rows = db.execute(text("SELECT id, applies_when FROM sales_stage_checks WHERE check_key = :k"), {"k": key}).fetchall()
    if not rows:
        raise AssemblyError(404, "Пункт не найден")
    for rid, aw in rows:
        aw = dict(aw or {})
        ids = [i for i in (aw.get("service_ids") or []) if i != service_id] + ([service_id] if state != "off" else [])
        blk = [i for i in (aw.get("blocking_service_ids") or []) if i != service_id] + ([service_id] if state == "block" else [])
        aw["service_ids"], aw["blocking_service_ids"] = ids, blk
        db.execute(text("UPDATE sales_stage_checks SET applies_when = CAST(:a AS jsonb) WHERE id = :i"), {"a": json.dumps(aw), "i": rid})


def toggle(db, key: str, service_id: int, on: bool) -> None:
    """Прежний вызов «вкл/выкл» — включение ставит «уведомляет»."""
    set_state(db, key, service_id, "warn" if on else "off")


def add_service(db, service_id: int) -> int:
    """Новая услуга — в пункты, обязательные для всех прежних активных услуг. Возвращает число затронутых записей."""
    active = {r[0] for r in db.execute(text("SELECT id FROM sales_services WHERE is_active AND id <> :s"), {"s": service_id})}
    n = 0
    for rid, aw in db.execute(text("SELECT id, applies_when FROM sales_stage_checks")).fetchall():
        aw = dict(aw or {})
        ids = aw.get("service_ids")
        if isinstance(ids, list) and active and active <= set(ids) and service_id not in ids:
            aw["service_ids"] = ids + [service_id]
            blk = aw.get("blocking_service_ids")
            if isinstance(blk, list) and active <= set(blk):      # запирает у всех прежних — запирает и у новой
                aw["blocking_service_ids"] = blk + [service_id]
            db.execute(text("UPDATE sales_stage_checks SET applies_when = CAST(:a AS jsonb) WHERE id = :i"), {"a": json.dumps(aw), "i": rid})
            n += 1
    return n
