# -*- coding: utf-8 -*-
"""Раскладка мастер-сделки по ДС и комплектам УПД — по дизайну docs/мастер сделка.zip (design_handoff_master_layout, 15.10.2026).

Один расчёт для экрана, предпросмотра черновика и конструктора ДС. Строки — те же, что идут в таблицу ДС (`annex.plan_rows`);
сумма базовой услуги — из итоговой сверки сделки (пин суммы ДС), строки базовой услуги масштабируются под неё.

Правила (ТЗ §4–6):
- допы отдельным ДС (`n-01`) — только платные; ДС допов без платных строк не создаётся, бонусные нули уходят в основной;
- у допов услуга не делит ни группы, ни комплекты — доп относится к бренду;
- точечный перенос платного допа в основной ДС (`moved`) живёт поверх общего правила;
- комплект = счёт + УПД + отчёт, только из позиций со стоимостью; № УПД сквозной по пакету;
- НДС — по строкам, как в счёте-фактуре и УПД (владелец 22.10.2026): НДС ДС и комплекта — сумма НДС строк (`final_recon.money`).
  Строки базовой услуги складываются ровно в сумму сверки: остаток копеек — последней строке."""
from typing import Optional

from sqlalchemy.orm import Session

from app.final_recon import closing as CL
from app.final_recon import money as M
from app.master_deal.models import MasterDeal, MasterDealItem

KEYS = ("addons_separate", "bonus_addons", "ds_by_brand", "ds_by_service", "upd_by_brand", "upd_by_service", "moved")


_r2 = M.r2      # одно округление на сверку, раскладку и ДС (аудит 2.7.0, п. 2.5)


def settings_of(m: MasterDeal) -> dict:
    return {k: (list(getattr(m, k) or []) if k == "moved" else getattr(m, k)) for k in KEYS}


def lines(db: Session, m: MasterDeal) -> list:
    """Все строки пакета: базовая услуга (сумма по пину сверки) и допы — с брендом, услугой, сделкой и устойчивым id."""
    from app.sales import annex as annex_mod
    from app.sales.models import SalesDeal, SalesService
    out = []
    for it in db.query(MasterDealItem).filter(MasterDealItem.master_deal_id == m.id).order_by(MasterDealItem.id):
        d = db.get(SalesDeal, it.deal_id)
        st = CL.compute(db, d)
        svc = db.get(SalesService, d.service_id).name if d.service_id else "—"
        brand = annex_mod.deal_brand(db, [d.id]) or "без бренда"
        rows = annex_mod.plan_rows(db, [d.id])
        base = [r for r in rows if r.get("kind") != "extra"]
        # Строки — пропорционально МП, в сумме ровно сумма сверки (аудит 2.7.0, п. 2.3): остаток копеек — последней строке.
        nets = M.scale_to([r["amount"] or 0 for r in base], st["base_ds_net"] or 0)
        vol_sum = sum((r["volume"] or 0) for r in base)
        kv = (st["ds_volume"] / vol_sum) if (st.get("ds_volume") and vol_sum) else 1.0
        sk = st["sk"]
        disc = float(sk["percent"] or 0) if sk["mode"] == "скидка в счёт" else 0.0
        common = {"deal_id": d.id, "deal": d.code, "brand": brand, "service": svc, "sk_pct": disc}
        for i, r in enumerate(base):
            out.append({**common, "id": f"b:{d.id}:{i}", "kind": "base",
                        "position": " · ".join(x for x in (r.get("position"), r.get("device")) if x),
                        "model": r.get("model"), "volume": round((r.get("volume") or 0) * kv) or None,
                        "unit_price": r.get("unit_price"), "net": nets[i], "src": r})
        for i, r in enumerate(x for x in rows if x.get("kind") == "extra"):
            bonus = bool(r.get("bonus"))
            out.append({**common, "id": f"e:{d.id}:{i}", "kind": "bonus" if bonus else "extra",
                        "position": r.get("position"), "model": r.get("model"), "volume": None,
                        "unit_price": None if bonus else r.get("unit_price"), "net": 0.0 if bonus else _r2(r["amount"]), "src": r})
    return out


def _discounts(rows: list) -> list:
    """Скидка СК «в счёт» (владелец 15.10.2026): по каждой сделке — строка с минусом от суммы её строк В ЭТОМ ДС, чтобы сумма
    пакета совпадала с суммой сделок «к закрытию». Бренд и услуга — как у базовой строки сделки: скидка идёт в тот же комплект."""
    out = []
    for deal_id in dict.fromkeys(r["deal_id"] for r in rows):
        mine = [r for r in rows if r["deal_id"] == deal_id]
        pct = mine[0].get("sk_pct") or 0
        base = sum(r["net"] for r in mine)
        if pct <= 0 or base <= 0:
            continue
        r0 = next((r for r in mine if r["kind"] == "base"), mine[0])
        # в ДС допов услуга не делит — скидка там относится только к бренду, как сами допы
        svc = r0["service"] if r0["kind"] == "base" else None
        out.append({**{k: r0[k] for k in ("deal_id", "deal", "brand", "sk_pct")}, "service": svc,
                    "id": f"sk:{deal_id}:{len(out)}", "kind": "discount", "position": f"Скидка СК {pct:g} %",
                    "model": "Скидка в счёт", "volume": None, "unit_price": None, "net": -_r2(base * pct / 100.0)})
    return out


def _key(r: dict, by_brand: bool, by_service: bool) -> tuple:
    # у допов услуга не делит — доп относится к бренду (ТЗ §4)
    svc = by_service and (r["kind"] == "base" or (r["kind"] == "discount" and r["service"]))
    return ((r["brand"] if by_brand else None), (r["service"] if svc else None))


def _contract_of(db: Session, m):
    from app.models import Contract
    return db.get(Contract, m.contract_id)


def _vat(db: Session, m, ls: list) -> Optional[float]:
    """Ставка пакета — та же, что у ДС: нашего юрлица на дату документа (`vat.for_document`, владелец 21.10.2026).
    Раньше — ставка медиаплана первой сделки, и при расхождении ставок ДС, УПД и операция показывали три суммы."""
    if not ls:
        return None
    from datetime import date as _date
    from app import vat
    from app.sales.annex import annex_date
    y, mo = (int(x) for x in m.period.split("-"))
    return vat.for_document(db, _contract_of(db, m), annex_date(_date(y, mo, 1)))


def layout(db: Session, m: MasterDeal, settings: Optional[dict] = None, *, with_src: bool = False) -> dict:
    """ДС пакета (группы строк) и комплекты УПД с № и разбивкой по сделкам. `settings` — черновик раскладки (предпросмотр);
    без него — сохранённая. Только расчёт — ничего не пишет."""
    st = {**settings_of(m), **{k: v for k, v in (settings or {}).items() if k in KEYS}}
    ls = [x for x in lines(db, m) if not (x["kind"] == "bonus" and st["bonus_addons"] == "hide")]
    moved = set(st.get("moved") or [])
    paid_extras = [x for x in ls if x["kind"] == "extra"]
    sep = bool(st["addons_separate"]) and bool(paid_extras)
    addons_paid = [x for x in paid_extras if x["id"] not in moved] if sep else []
    if sep and addons_paid:
        main = [x for x in ls if x["kind"] == "base" or x["id"] in moved]
        addons = addons_paid + [x for x in ls if x["kind"] == "bonus"]
        parts = [("main", "основные услуги", main), ("addons", "доп. услуги", addons)]
    else:                                    # ДС допов без платных строк не создаётся — всё в основной
        parts = [("all" if paid_extras else "main", "основные и допы" if paid_extras else "основные услуги", ls)]

    vat = _vat(db, m, ls)
    base_no = (m.start_no + 1) if m.start_no is not None else None
    ds_list, upd_no = [], 0
    for kind, title, rows in parts:
        if not rows:
            continue
        rows = rows + _discounts(rows)
        no = (f"{base_no}-01" if kind == "addons" else str(base_no)) if base_no else ("n-01" if kind == "addons" else "n")
        groups: dict = {}
        for r in rows:
            groups.setdefault(_key(r, st["ds_by_brand"], st["ds_by_service"]), []).append(r)
        kits: dict = {}
        for r in rows:
            if r["net"] != 0:                # позиции с нулём комплект не образуют; скидка идёт в комплект своей сделки
                kits.setdefault(_key(r, st["upd_by_brand"], st["upd_by_service"]), []).append(r)
        upds = []
        for (br, sv), rs in kits.items():
            upd_no += 1
            net, vat_k = _r2(sum(x["net"] for x in rs)), M.doc_vat([x["net"] for x in rs], vat)
            by_deal: dict = {}
            for x in rs:
                by_deal.setdefault(x["deal"], []).append(x["net"])
            upds.append({"upd_no": upd_no, "brand": br, "service": sv, "net": net, "vat": vat_k, "gross": _r2(net + vat_k),
                         "deals": sorted(by_deal), "lines": [x["id"] for x in rs],
                         "by_deal": [{"deal": k, "net": _r2(sum(v)), "gross": _r2(sum(v) + M.doc_vat(v, vat))}
                                     for k, v in sorted(by_deal.items())]})
        net, vat_ds = _r2(sum(x["net"] for x in rows)), M.doc_vat([x["net"] for x in rows], vat)
        ds_list.append({
            "kind": kind, "no": no, "title": title, "net": net, "vat": vat_ds, "gross": _r2(net + vat_ds),
            "groups": [{"brand": br, "service": sv, "net": _r2(sum(x["net"] for x in rs)),
                        "rows": [{k: v for k, v in x.items() if k != "src"} for x in rs], "_src": rs} for (br, sv), rs in groups.items()],
            "upds": upds, "no_kits": not upds,
        })
    if not with_src:                         # исходные строки МП нужны только снимку ДС (to_annex), наружу их не отдаём
        for ds in ds_list:
            for g in ds["groups"]:
                g.pop("_src", None)
    total = _r2(sum(ds["net"] for ds in ds_list))
    return {"vat_rate": vat, "ds": ds_list, "total_net": total, "total_gross": _r2(sum(ds["gross"] for ds in ds_list)),
            "upd_count": upd_no, "lines": len(ls), "has_paid_extras": bool(paid_extras), "settings": st}
