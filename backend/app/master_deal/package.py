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
    """Выпущенный ДС этого пакета — раскладка закреплена. Стартовый пакет на закрытии: ДС старта раскладку не держит — он
    пересобирается по факту или остаётся как подписан (02.11.2026)."""
    from app.master_deal import start as SP
    skip_primary = bool(getattr(m, "issued_at_start", False)) and SP.closing_started(db, m)
    r = db.execute(text("""
        SELECT no, confirmed_at AS at FROM sales_annexes
         WHERE master_deal_id = :m AND confirmed_at IS NOT NULL AND NOT (:skip AND issue_kind = 'primary')
         ORDER BY confirmed_at LIMIT 1"""), {"m": m.id, "skip": skip_primary}).mappings().first()
    return dict(r) if r else None


def _editable(db: Session, m: MasterDeal) -> None:
    ds = issued_ds(db, m)
    if ds:
        raise MS.MasterError(409, f"ДС № {ds['no']} выпущен — раскладка закреплена; изменить — через отзыв ДС у юриста")


def _contract_start(db: Session, contract_id: int):
    """«ДС с» договора — номера по него выданы вне системы (`contracts.annex_start_no`)."""
    return db.execute(text("SELECT annex_start_no FROM contracts WHERE id = :c"), {"c": contract_id}).scalar()


def _packages_on(db: Session, m: MasterDeal, n: int) -> list:
    """Другие пакеты договора, чей неподтверждённый основной ДС получит тот же № n."""
    rows = db.execute(text("""
        SELECT m.code FROM master_deals m
         WHERE m.contract_id = :c AND m.id <> :me AND m.start_no + 1 = :n
           AND NOT EXISTS (SELECT 1 FROM sales_annexes a WHERE a.master_deal_id = m.id AND a.no IS NOT NULL
                                                          AND coalesce(a.kind, '') <> 'addons')"""),
                      {"c": m.contract_id, "me": m.id, "n": n}).all()
    return [r[0] for r in rows]


def effective_start_no(db: Session, m: MasterDeal) -> Optional[int]:
    """«Последний актуальный №» пакета: заданный руками — он; не задан — последний известный по договору (владелец 13.11.2026,
    M-0026: по договору выпущено 13 ДС № 83–95, а пакет просил указать номер). Известный = наибольший из «ДС с» договора,
    выпущенных ДС и номеров, которые уже ждут другие пакеты договора (их ДС ещё не выпущены). None — нумерация договора
    неизвестна, номер спрашиваем. Закрепляется в пакете при создании ДС (`to_annex.create`)."""
    if m.start_no is not None:
        return m.start_no
    waiting = db.execute(text("""
        SELECT max(m.start_no + 1) FROM master_deals m
         WHERE m.contract_id = :c AND m.id <> :me AND m.start_no IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM sales_annexes a WHERE a.master_deal_id = m.id AND a.no IS NOT NULL
                                                          AND coalesce(a.kind, '') <> 'addons')"""),
                         {"c": m.contract_id, "me": m.id}).scalar()
    known = [x["no"] for x in issued(db, m.contract_id)] + [_contract_start(db, m.contract_id), waiting]
    known = [n for n in known if n is not None]
    return max(known) if known else None


def check_start_no(db: Session, m: MasterDeal, no: int) -> dict:
    """Проверка «последнего актуального» №. ДС пакета получит № no + 1 (допы — с суффиксом того же номера).

    Ниже выпущенного — можно (владелец 05.11.2026: внешние ДС за прошлые месяцы подписаны с номерами меньше наших, у АПР
    Евразии октябрьский № 28 при выпущенных № 30 и № 31), но не на выпущенный нами номер. Выше — можно, номера между
    будут пропущены."""
    start = _contract_start(db, m.contract_id)
    if start and no + 1 <= start:
        return {"ok": False, "last": start, "text": f"По договору номера по № {start} выданы вне системы («ДС с») — ДС пакета получил бы № {no + 1}."}
    same = _packages_on(db, m, no + 1)
    if same:
        return {"ok": False, "last": None, "text": f"№ {no + 1} уже ждёт пакет {', '.join(same)} этого договора — выберите другой номер."}
    rows = issued(db, m.contract_id)
    nums = [x["no"] for x in rows]
    last = max(nums) if nums else None
    taken = next((x for x in rows if x["no"] == no + 1), None)
    if taken is not None:
        return {"ok": False, "last": last, "text": f"ДС № {no + 1} уже выпущен {taken['at']:%d.%m} — ДС пакета получил бы тот же номер."}
    if last is not None and no < last:
        return {"ok": True, "last": last, "warn": f"ДС пакета получит № {no + 1} — ниже уже выпущенного № {last}"}
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
