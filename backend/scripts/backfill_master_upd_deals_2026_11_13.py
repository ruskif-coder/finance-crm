# -*- coding: utf-8 -*-
"""Разово: разбивка комплектов закрывающих по сделкам (`master_deal_upds.deals`) для пакетов, созданных до 13.11.2026.

Раскладка мастер-сделки считает, из каких сделок собран комплект, но до 13.11 это не записывалось. Здесь:
  · пакет из ОДНОЙ сделки — комплект целиком её (доля = сумма комплекта);
  · из нескольких — берём комплект раскладки с тем же номером и пишем, только если его сумма до НДС совпала с суммой
    комплекта (±0,02); не совпала — НЕ угадываем, называем пакет и комплект.

    docker exec finance_backend python -m scripts.backfill_master_upd_deals_2026_11_13            # показать
    docker exec finance_backend python -m scripts.backfill_master_upd_deals_2026_11_13 --apply    # записать
"""
import sys

import app.model_registry  # noqa: F401 — все таблицы для внешних ключей
from app.database import SessionLocal
from app.master_deal import layout as LY
from app.master_deal import to_annex as TA
from app.master_deal.models import MasterDeal, MasterDealItem, MasterDealUpd
from app.sales.models import SalesDeal


def _plan(db, m, kits) -> tuple:
    items = db.query(MasterDealItem).filter_by(master_deal_id=m.id).all()
    if len(items) == 1:
        d = db.get(SalesDeal, items[0].deal_id)
        return {k.id: [{"deal_id": d.id, "code": d.code, "net": round(k.net or 0, 2), "gross": round(k.gross or 0, 2)}]
                for k in kits}, []
    lay_kits = {u["upd_no"]: u for ds in LY.layout(db, m)["ds"] for u in ds["upds"]}
    out, bad = {}, []
    for k in kits:
        u = lay_kits.get(k.upd_no)
        if u is None or abs((u["net"] or 0) - (k.net or 0)) > 0.02:
            bad.append(f"{m.code} комплект {k.upd_no}: в раскладке {u['net'] if u else 'нет'} ≠ {k.net}")
            continue
        out[k.id] = TA.kit_deals(u)
    return out, bad


def main(apply: bool) -> int:
    db = SessionLocal()
    try:
        done, skipped = 0, []
        for m in db.query(MasterDeal).order_by(MasterDeal.id):
            kits = db.query(MasterDealUpd).filter(MasterDealUpd.master_deal_id == m.id, MasterDealUpd.deals.is_(None)).all()
            if not kits:
                continue
            plan, bad = _plan(db, m, kits)
            skipped += bad
            for k in kits:
                if k.id in plan:
                    k.deals = plan[k.id]
                    done += 1
                    print(f"{m.code} комплект {k.upd_no}: {', '.join(x['code'] for x in plan[k.id])}")
        for s in skipped:
            print("НЕ ТРОНУТ:", s)
        print(f"итого комплектов: {done}, не тронуто: {len(skipped)}" + ("" if apply else " (без --apply ничего не записано)"))
        db.commit() if apply else db.rollback()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
