# -*- coding: utf-8 -*-
"""Операции над пакетом мастер-сделки на экране раскладки (дизайн 15.10.2026, design_handoff_master_layout §2–3, §7–8):
состав пакета (+ сделка / ×), стартовый № ДС, сохранение раскладки, прошлая раскладка по договору, закрепление после выпуска ДС.
К раскладке возвращаются и правят — пока ДС пакета не выпущен; после выпуска все мутации отказывают (изменить — через отзыв у юриста)."""
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.master_deal import layout as LY
from app.master_deal import service as MS
from app.master_deal.models import MasterDeal, MasterDealItem


def issued(db: Session, contract_id: int) -> list:
    """Выпущенные (подтверждённые) ДС договора: [{no, at}], по номеру."""
    rows = db.execute(text("""
        SELECT no, coalesce(confirmed_at, created_at) AS at FROM sales_annexes
         WHERE contract_id = :c AND no IS NOT NULL AND confirmed_at IS NOT NULL ORDER BY no"""), {"c": contract_id}).mappings().all()
    return [{"no": r["no"], "at": r["at"]} for r in rows]


def issued_ds(db: Session, m: MasterDeal) -> Optional[dict]:
    """Выпущенный ДС этого пакета — раскладка закреплена."""
    r = db.execute(text("""
        SELECT no, confirmed_at AS at FROM sales_annexes
         WHERE master_deal_id = :m AND confirmed_at IS NOT NULL ORDER BY confirmed_at LIMIT 1"""), {"m": m.id}).mappings().first()
    return dict(r) if r else None


def _editable(db: Session, m: MasterDeal) -> None:
    ds = issued_ds(db, m)
    if ds:
        raise MS.MasterError(409, f"ДС № {ds['no']} выпущен — раскладка закреплена; изменить — через отзыв ДС у юриста")


def check_start_no(db: Session, m: MasterDeal, no: int) -> dict:
    """Проверка «последнего актуального» №: ниже выпущенного — нельзя; выше — можно, номера между будут пропущены."""
    nums = [x["no"] for x in issued(db, m.contract_id)]
    last = max(nums) if nums else None
    if last is not None and no < last:
        at = next(x["at"] for x in issued(db, m.contract_id) if x["no"] == last)
        return {"ok": False, "last": last, "text": f"ДС № {last} уже выпущен {at:%d.%m}. Последний актуальный — № {last}."}
    if last is not None and no > last:
        skip = f"{last + 1}" if no == last + 1 else f"{last + 1}–{no}"
        return {"ok": True, "last": last, "warn": f"Номера {skip} будут пропущены"}
    return {"ok": True, "last": last}


def _draft_only(m: MasterDeal) -> None:
    """С черновиками ДС раскладка и номер закреплены снимком: правка разошлась бы с ним молча (ревью 21.10.2026)."""
    if m.status != "черновик":
        raise MS.MasterError(409, "ДС пакета уже созданы — сначала «Вернуть в раскладку»")


def set_start_no(db: Session, m: MasterDeal, no: int, user) -> dict:
    _editable(db, m)
    _draft_only(m)
    if no is None or no < 0:
        raise MS.MasterError(400, "№ ДС — целое число")
    chk = check_start_no(db, m, no)
    if not chk["ok"]:
        raise MS.MasterError(409, chk["text"])
    m.start_no, m.updated_at = no, datetime.utcnow()
    db.flush()
    return chk


def save_settings(db: Session, m: MasterDeal, st: dict, user) -> None:
    _editable(db, m)
    _draft_only(m)
    if st.get("bonus_addons") not in (None, "zero", "hide"):
        raise MS.MasterError(400, "Бонусные допы: строкой с нулём или не включать")
    for k in LY.KEYS:
        if k in st and st[k] is not None:
            setattr(m, k, list(st[k]) if k == "moved" else st[k])
    m.saved_by, m.updated_at = getattr(user, "id", None), datetime.utcnow()
    db.flush()


def candidates(db: Session, m: MasterDeal) -> list:
    """«+ сделка»: тот же договор и месяц, не в пакете."""
    rows = db.execute(text("""
        SELECT d.id, d.code, d.title, st.name AS stage FROM sales_deals d LEFT JOIN sales_stages st ON st.id = d.our_stage_id
         WHERE d.ord_final_contract_id = :c AND to_char(d.period_from, 'YYYY-MM') = :p AND coalesce(st.is_lost, false) = false
           AND NOT EXISTS (SELECT 1 FROM master_deal_items i WHERE i.deal_id = d.id) ORDER BY d.code"""),
        {"c": m.contract_id, "p": m.period}).mappings().all()
    return [dict(r) for r in rows]


def add_deal(db: Session, m: MasterDeal, deal, user) -> None:
    _editable(db, m)
    if deal.id not in {c["id"] for c in candidates(db, m)}:
        raise MS.MasterError(409, f"{deal.code}: другой договор или месяц, или уже в пакете")
    MS.attach(db, deal, m, user)


def remove_deal(db: Session, m: MasterDeal, deal_id: int) -> None:
    """× — убрать сделку из пакета; пакет можно опустошить до нуля. Сверка сделки не трогается."""
    _editable(db, m)
    it = db.query(MasterDealItem).filter(MasterDealItem.master_deal_id == m.id, MasterDealItem.deal_id == deal_id).first()
    if not it:
        raise MS.MasterError(404, "Сделки нет в пакете")
    db.delete(it)
    m.updated_at = datetime.utcnow()
    db.flush()


def prev(db: Session, m: MasterDeal) -> Optional[dict]:
    """Прошлая мастер-сделка по договору — «В YYYY-MM закрывали так»."""
    p = (db.query(MasterDeal).filter(MasterDeal.contract_id == m.contract_id, MasterDeal.period < m.period)
         .order_by(MasterDeal.period.desc(), MasterDeal.id.desc()).first())
    if not p:
        return None
    lay = LY.layout(db, p)
    return {"code": p.code, "period": p.period, "ds": len(lay["ds"]), "kits": lay["upd_count"], "settings": LY.settings_of(p)}
