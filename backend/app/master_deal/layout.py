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


def service_label(svc: str, device=None) -> str:
    """Услуга строки пакета в разбиении документов: название услуги и площадка строки МП («еФарм · WEB», «еФарм · APP»). Web и app одной
    услуги — разные сделки (владелец 30.09.2026), и комплект закрывающих — под каждую отдельно (28.10.2026: у Сандоза на проде пакет
    M-0001 при «УПД по услугам» дал одну УПД «еФарм» на обе площадки). Площадки нет — только название."""
    d = (device or "").strip()
    return f"{svc} · {d}" if d else svc


def settings_of(m: MasterDeal) -> dict:
    return {k: (list(getattr(m, k) or []) if k == "moved" else getattr(m, k)) for k in KEYS}


def lines(db: Session, m: MasterDeal) -> list:
    """Все строки пакета: базовая услуга (сумма по пину сверки) и допы — с брендом, услугой, сделкой и устойчивым id."""
    from app.sales import annex as annex_mod
    from app.sales.models import SalesDeal, SalesService
    from app.master_deal import start as SP
    plan_only = SP.in_start_phase(db, m)          # ДС на старте — на план: факта и сверки ещё нет (02.11.2026)
    out = []
    for it in db.query(MasterDealItem).filter(MasterDealItem.master_deal_id == m.id).order_by(MasterDealItem.id):
        d = db.get(SalesDeal, it.deal_id)
        st = CL.compute(db, d, plan_only=plan_only)
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
            out.append({**common, "service": service_label(svc, r.get("device")), "id": f"b:{d.id}:{i}", "kind": "base",
                        "position": " · ".join(x for x in (r.get("position"), r.get("device")) if x),
                        "model": r.get("model"), "volume": row_volume(r, nets[i], kv),
                        "unit_price": r.get("unit_price"), "net": nets[i], "src": r})
        for i, r in enumerate(x for x in rows if x.get("kind") == "extra"):
            bonus = bool(r.get("bonus"))
            out.append({**common, "id": f"e:{d.id}:{i}", "kind": "bonus" if bonus else "extra",
                        "position": r.get("position"), "model": r.get("model"), "volume": None,
                        "unit_price": None if bonus else r.get("unit_price"), "net": 0.0 if bonus else _r2(r["amount"]), "src": r})
    return out


def _fold_discounts(rows: list) -> list:
    """Скидка СК «в счёт» — через цену единицы закупки (владелец 11.11.2026, со слов бухгалтера). Прежде (15.10) — строка
    «Скидка СК» с минусом; заявка бухгалтеру её не видела, и счета M-0032…35 ушли в 1С без скидки. Строки размещения сделки
    уменьшаются на её % СК: сумма — до той же суммы «к закрытию» (база − скидка, остаток копеек последней строке), цена единицы
    × (1 − %), объём закупки прежний. Допы СК не облагаются (07.11.2026). Новые строки — входные не меняются."""
    out = list(rows)
    for deal_id in dict.fromkeys(r["deal_id"] for r in rows):
        idx = [i for i, r in enumerate(rows) if r["deal_id"] == deal_id and r["kind"] == "base"]
        pct = float(rows[idx[0]].get("sk_pct") or 0) if idx else 0.0
        base = sum(rows[i]["net"] for i in idx)
        if pct <= 0 or base <= 0:
            continue
        # Доли — от сумм МП (src), как у сверки (`closing._money`): двойное масштабирование сдвигало копейку между строками.
        weights = [((rows[i].get("src") or {}).get("amount") or rows[i]["net"]) for i in idx]
        nets = M.scale_to(weights, _r2(_r2(base) - _r2(base * pct / 100.0)))
        for i, net in zip(idx, nets):
            up = rows[i].get("unit_price")
            out[i] = {**rows[i], "net": net, "unit_price": _r2(float(up) * (1 - pct / 100.0)) if up else up}
    return out


def sk_in_invoice(rows: list) -> list:
    """Сделки пакета со скидкой в счёт — для плашки «документы со скидкой в счёт» (только для сведения, 11.11.2026)."""
    seen: dict = {}
    for r in rows:
        if r["kind"] == "base" and (r.get("sk_pct") or 0) > 0:
            seen.setdefault(r["deal"], float(r["sk_pct"]))
    return [{"deal": d, "pct": p} for d, p in seen.items()]


def _key(r: dict, by_brand: bool, by_service: bool) -> tuple:
    # у допов услуга не делит — доп относится к бренду (ТЗ §4)
    svc = by_service and r["kind"] == "base"
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
    # На старте одна сделка — один ДС (владелец 02.11.2026): два первичных уронили бы закрытие на «разные первичные ДС».
    from app.master_deal import start as SP
    sep = bool(st["addons_separate"]) and bool(paid_extras) and not SP.in_start_phase(db, m)
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
        rows = _fold_discounts(rows)
        no = (f"{base_no}-01" if kind == "addons" else str(base_no)) if base_no else ("n-01" if kind == "addons" else "n")
        groups: dict = {}
        for r in rows:
            groups.setdefault(_key(r, st["ds_by_brand"], st["ds_by_service"]), []).append(r)
        kits: dict = {}
        for r in rows:
            if r["net"] != 0:                # позиции с нулём комплект не образуют
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
            "upd_count": upd_no, "lines": len(ls), "has_paid_extras": bool(paid_extras), "settings": st,
            "sk_in_invoice": sk_in_invoice(ls)}


def row_volume(r: dict, net: float, kv: float):
    """Объём строки ДС в единицах закупки её модели (07.11.2026). CPM — показы: объём МП × коэффициент сверки (показы сверки ÷
    объём МП). Остальные (CPC — клики, Фикс/Пакет — штуки) — сумма строки ÷ цена за единицу: коэффициент там в показах и
    превращал 2 567 кликов в 548 082 «клика». Цены нет — объём МП как есть."""
    from app.sales import mp_row
    vol = r.get("volume") or 0
    if mp_row.is_cpm(r.get("model")):
        return round(vol * kv) or None
    price = float(r.get("unit_price") or 0)
    return (round(float(net or 0) / price) if price else round(vol)) or None
