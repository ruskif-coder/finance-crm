# -*- coding: utf-8 -*-
"""Пересобрать выпущенные ДС пакетов со скидкой СК «в счёт» по новому правилу (владелец 11.11.2026): скидка — в цене единицы
строк размещения, строки «Скидка СК» с минусом в ДС нет. По старому правилу заявка бухгалтеру строку с минусом не видела,
и счета ушли в 1С без скидки. ДС клиентам ещё не уходили (слово владельца) — пересобираем с прежними номером и датой.

Что меняется у каждого пакета: снимок строк ДС, разнесение по сделкам, сумма и замороженный текст ДС (`rebuild_frozen`, как
кнопка «Пересоздать»). Комплект УПД, его файлы, черновик и переписка с бухгалтером — не трогаются; сумма комплекта сверяется
с новой раскладкой (итог не меняется — скидка та же, меняется только её вид).

    docker exec finance_backend python -m scripts.2026-11-11_sk_discount_rebuild M-0032 M-0033            # показать
    docker exec finance_backend python -m scripts.2026-11-11_sk_discount_rebuild M-0032 M-0033 --apply    # записать
"""
import json
import sys

import app.model_registry  # noqa: F401
from app.annex_tpl import document as tpl_doc
from app.audit import log_action
from app.database import SessionLocal
from app.master_deal import layout as LY
from app.master_deal import to_annex as TA
from app.master_deal.models import MasterDeal, MasterDealUpd
from app.models import Contract
from app.routers.annexes import rebuild_frozen
from app.sales.models import SalesAnnex


def _has_minus_row(rows) -> bool:
    return any((r or {}).get("kind") == "discount" for r in rows or [])


def rebuild(db, code: str) -> dict:
    m = db.query(MasterDeal).filter(MasterDeal.code == code).one()
    annexes = db.query(SalesAnnex).filter(SalesAnnex.master_deal_id == m.id).all()
    kits = db.query(MasterDealUpd).filter(MasterDealUpd.master_deal_id == m.id).order_by(MasterDealUpd.upd_no).all()
    if len(annexes) != 1 or annexes[0].no is None:
        raise SystemExit(f"{code}: ожидался один выпущенный ДС, есть {[(a.id, a.no) for a in annexes]}")
    a = annexes[0]
    if not _has_minus_row(a.rows):
        raise SystemExit(f"{code}: в ДС нет строки «Скидка СК» — пересобирать нечего")
    if any(k.onec_state == "внесён" for k in kits):
        raise SystemExit(f"{code}: комплект уже внесён бухгалтером — сначала разобраться с 1С")
    if getattr(a, "sign_state", None) not in (None, "выпущен"):
        raise SystemExit(f"{code}: ДС в круге подписи «{a.sign_state}» — владелец сказал, что клиентам не уходили; проверить")
    lay = LY.layout(db, m, with_src=True)
    if len(lay["ds"]) != 1 or [u["upd_no"] for u in lay["ds"][0]["upds"]] != [k.upd_no for k in kits]:
        raise SystemExit(f"{code}: раскладка разошлась с выпущенным ДС — руками")
    ds = lay["ds"][0]
    for u, k in zip(ds["upds"], kits):
        if abs(u["gross"] - float(k.gross)) > 0.05:
            raise SystemExit(f"{code}: сумма комплекта УПД {k.upd_no} меняется {k.gross} → {u['gross']} — руками")
    c = db.get(Contract, m.contract_id)
    before = {"total": float(a.total_amount), "rows": len(a.rows or []), "no": a.no, "date": str(a.date)}
    a.rows = TA._snapshot(ds)
    deal_ids = TA.allocate(db, a, ds, lay["vat_rate"])
    db.flush()
    version, reason = tpl_doc.resolve(db, c)
    if version is None:
        raise SystemExit(f"{code}: {reason}")
    a.total_amount = tpl_doc.live(db, c, version, a, deal_ids)["amount"]
    rebuild_frozen(db, a, c)
    for u, k in zip(ds["upds"], kits):
        k.net, k.vat, k.gross = u["net"], u["vat"], u["gross"]
    db.flush()
    text_ = json.dumps(a.blocks, ensure_ascii=False)
    after = {"total": float(a.total_amount), "rows": len(a.rows), "no": a.no, "date": str(a.date),
             "minus_row_left": "Скидка СК" in text_ or _has_minus_row(a.rows),
             "kits": [(k.upd_no, float(k.gross)) for k in kits],
             "lines": [(r.get("position"), r.get("unit_price"), r.get("amount")) for r in a.rows if r.get("kind") == "base"]}
    if after["minus_row_left"] or after["no"] != before["no"] or after["date"] != before["date"]:
        raise SystemExit(f"{code}: проверка после пересборки не прошла: {after}")
    if abs(after["total"] - sum(g for _, g in after["kits"])) > 0.05:
        raise SystemExit(f"{code}: сумма ДС {after['total']} ≠ сумме комплектов {after['kits']}")
    return {"code": code, "annex_id": a.id, "number": a.number, "before": before, "after": after}


def main(argv: list) -> None:
    apply = "--apply" in argv
    codes = [x for x in argv if x.startswith("M-")]
    if not codes:
        raise SystemExit("укажите коды пакетов: M-0032 M-0033 …")
    db = SessionLocal()
    try:
        out = [rebuild(db, c) for c in codes]
        for r in out:
            print(json.dumps(r, ensure_ascii=False, default=str))
        if apply:
            for r in out:
                m = db.query(MasterDeal).filter(MasterDeal.code == r["code"]).one()
                log_action(db, None, "update_master_deal", "master_deal", m.id,
                           f"{r['code']}: {r['number']} пересобран по слову владельца 11.11.2026 — скидка СК в счёт в цене единицы, "
                           "строки «Скидка СК» нет (номер, дата и сумма прежние)")
            db.commit()
            print("APPLIED")
        else:
            db.rollback()
            print("DRY RUN")
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1:])
