# -*- coding: utf-8 -*-
"""Комплекты УПД пакетов у бухгалтерии — по ТЕКУЩЕЙ раскладке (владелец 06.11.2026: «при релизе да, и в целом проверь, что
пересчитаются документы все у буха»).

Зачем: комплекты УПД записываются, когда пакет собирает ДС (`to_annex.create`), и дальше не пересчитываются. M-0001 собран 27.10 —
до v2.7.14 (28.10), с которой «УПД по услугам» разводит «еФарм · WEB» и «еФарм · APP», — и у бухгалтера одна заявка вместо двух.

Что делает: для каждого пакета в «ждём 1С» и дальше (до архива) сравнивает записанные комплекты (№, бренд, услуга, сумма с НДС) с
раскладкой сейчас. Расходится — пересобирает комплекты, ДС не трогает. Только если по комплектам пакета ничего не сделано: нет
ответа 1С, файлов к УПД, подписи УПД, операции по счёту, событий бухгалтерии; иначе — в отчёт «руками».

    docker exec finance_backend python -m scripts.rebuild_stale_kits_2026_11_06            # сухой прогон
    docker exec finance_backend python -m scripts.rebuild_stale_kits_2026_11_06 --apply    # записать
"""
import sys

from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.master_deal import layout as L
from app.master_deal.models import MasterDeal, MasterDealUpd
from app.onec_desk.service import OPEN


def _sig(rows) -> list:
    return [(r["upd_no"], r["brand"], r["service"], round(float(r["gross"]), 2)) for r in rows]


def wanted(db, m) -> list:
    out = []
    for d in L.layout(db, m)["ds"]:
        out += [{**u, "ds_kind": d["kind"]} for u in d["upds"]]
    return out


def saved(db, m) -> list:
    ks = db.query(MasterDealUpd).filter_by(master_deal_id=m.id).order_by(MasterDealUpd.upd_no).all()
    return [{"upd_no": k.upd_no, "brand": k.brand, "service": k.service, "gross": k.gross, "annex_id": k.annex_id, "obj": k} for k in ks]


def blockers(db, m, kits) -> list:
    """Что уже сделано по комплектам — тогда пересобирать нельзя."""
    ids = [k["obj"].id for k in kits] or [0]
    why = []
    if any(k["obj"].onec_state or k["obj"].onec_at or k["obj"].onec_invoice_no or k["obj"].onec_draft for k in kits):
        why.append("бухгалтер уже вносил или начал черновик")
    if any(k["obj"].sign_state for k in kits):
        why.append("УПД уже в подписи")
    q = {"ids": ids, "m": m.id}
    if db.execute(text("SELECT 1 FROM master_deal_files WHERE master_deal_id = :m AND upd_no IS NOT NULL LIMIT 1"), q).first():
        why.append("к УПД приложены файлы")
    if db.execute(text("SELECT 1 FROM operations WHERE master_deal_upd_id = ANY(:ids) LIMIT 1"), q).first():
        why.append("по счёту есть операция")
    if db.execute(text("SELECT 1 FROM onec_desk_events WHERE upd_id = ANY(:ids) LIMIT 1"), q).first():
        why.append("есть переписка/возврат бухгалтерии")
    if db.execute(text("SELECT 1 FROM doc_sign_events WHERE upd_id = ANY(:ids) LIMIT 1"), q).first():
        why.append("есть история подписи УПД")
    return why


def annex_for(kits_saved: list, ds_kind: str, db, m):
    """ДС комплекта: был один ДС на все УПД — он же; иначе ДС допов — с sub_no, основной — без."""
    ids = sorted({k["annex_id"] for k in kits_saved if k["annex_id"]})
    if len(ids) == 1:
        return ids[0]
    from app.sales.models import SalesAnnex
    cands = [a.id for a in db.query(SalesAnnex).filter(SalesAnnex.id.in_(ids or [0]))
             if (a.sub_no is not None) == (ds_kind == "addons")]
    return cands[0] if len(cands) == 1 else None


def check(db) -> list:
    out = []
    for m in db.query(MasterDeal).filter(MasterDeal.status.in_(list(OPEN))).order_by(MasterDeal.code):
        have, want = saved(db, m), wanted(db, m)
        if _sig(have) == _sig(want):
            continue
        why = blockers(db, m, have)
        ann = {w["upd_no"]: annex_for(have, w["ds_kind"], db, m) for w in want}
        if any(v is None for v in ann.values()):
            why.append("не понять, к какому ДС отнести новые УПД")
        out.append({"m": m, "have": have, "want": want, "annex": ann, "blocked": why})
    return out


def rebuild(db, item) -> None:
    m = item["m"]
    for k in item["have"]:
        db.delete(k["obj"])
    db.flush()
    for w in item["want"]:
        db.add(MasterDealUpd(master_deal_id=m.id, upd_no=w["upd_no"], annex_id=item["annex"][w["upd_no"]], brand=w["brand"],
                             service=w["service"], net=w["net"], vat=w["vat"], gross=w["gross"]))
    db.flush()


def main(apply: bool) -> int:
    from app.database import SessionLocal
    db = SessionLocal()
    found = check(db)
    n = db.query(MasterDeal).filter(MasterDeal.status.in_(list(OPEN))).count()
    print(f"Пакетов у бухгалтерии: {n}; комплекты расходятся с раскладкой: {len(found)}")
    for it in found:
        m = it["m"]
        print(f"\n{m.code} ({m.status})")
        print("  записано:", "; ".join(f"УПД {r['upd_no']} {r['service'] or '—'} {float(r['gross']):,.2f}" for r in it["have"]).replace(",", " "))
        print("  по раскладке:", "; ".join(f"УПД {r['upd_no']} {r['service'] or '—'} {float(r['gross']):,.2f}" for r in it["want"]).replace(",", " "))
        if it["blocked"]:
            print("  НЕ ПЕРЕСОБИРАЮ — руками:", "; ".join(it["blocked"]))
        elif apply:
            rebuild(db, it)
            print("  пересобрано")
    if apply:
        db.commit()
    else:
        db.rollback()
        print("\nСухой прогон — ничего не записано. Записать: --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
