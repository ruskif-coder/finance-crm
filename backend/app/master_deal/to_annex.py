# -*- coding: utf-8 -*-
"""Раскладка мастер-сделки → черновики ДС в конструкторе ДС (владелец 15.10.2026, docs/ПЛАН_конструктор_ДС_из_мастер-сделки.md).

«В конструктор ДС →» создаёт по черновику на каждый ДС раскладки. Строки ДС — СНИМОК раскладки (`sales_annexes.rows`): пин сверки,
скидка СК, переносы, группы — ровно как на экране; поздняя статистика или правка МП ДС больше не меняют. Распределение по сделкам —
по строкам каждой сделки в этом ДС. Комплекты УПД пишутся в `master_deal_upds`. Номер: основной — `start_no + 1`, допы — с суффиксом
«01»; занимается при подтверждении в конструкторе ДС.

«Вернуть в раскладку» — пока ни один ДС пакета не подтверждён и нет открытых заявок юристу: черновики удаляются, пакет снова на сборке."""
import calendar
from typing import Optional
from datetime import date, datetime

from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.annex_tpl import doc_kind as DK
from app.final_recon import closing as CL
from app.master_deal import layout as LY
from app.master_deal import package as PK
from app.master_deal import primary as PR
from app.master_deal import service as MS
from app.master_deal.models import MasterDeal, MasterDealUpd

SUB_ADDONS = "01"


def _bounds(period: str) -> tuple:
    y, mth = (int(x) for x in period.split("-"))
    return date(y, mth, 1), date(y, mth, calendar.monthrange(y, mth)[1])


def number_label(no, sub_no, kind: str = "дс") -> str:
    """Номер ДС мастер-сделки — тем же словом, что его документ («синхронизировать», 31.10.2026).

    Прежде здесь было «ДС № N» сокращением, и черновик в реестре назывался не так, как его
    живой документ («Доп. соглашение № N»). Полной формой — потому что номер печатается
    в документе; «ДС» остаётся на экранах и в сообщениях. По умолчанию «дс»: мастер-сделка —
    доп. соглашение (решение владельца 15.10.2026), пока тумблер договора не сказал иное.
    """
    return DK.number_text(kind, f"{no}-{sub_no}" if sub_no else no)


def _snapshot(ds: dict) -> list:
    """Строки ДС для документа: исходная строка МП с суммой и объёмом по раскладке; строка скидки — своя. Заголовок группы
    документа (`brand`) — подпись группы раскладки (бренд · услуга)."""
    from app.sales.annex import PLACEMENT_NETWORK
    out = []
    for g in ds["groups"]:
        label = " · ".join(x for x in (g["brand"], g["service"]) if x) or None
        for r in g["_src"]:
            src = r.get("src") or {}
            row = {**src, "deal_id": r["deal_id"], "brand": label, "kind": "extra" if r["kind"] in ("extra", "bonus") else r["kind"],
                   "volume": r["volume"], "amount": r["net"] if r["net"] else None, "bonus": r["kind"] == "bonus"}
            if r["kind"] == "discount":
                row.update({"network": PLACEMENT_NETWORK, "position": r["position"], "doc_position": None, "geo": None, "format": None,
                            "device": None, "rotation": None, "model": "Скидка в счёт", "unit_price": None,
                            "date_from": None, "date_to": None})
            out.append(row)
    return jsonable_encoder(out)


def ready(db: Session, m: MasterDeal) -> list:
    """Почему нельзя в конструктор ДС — список причин (пусто — можно)."""
    lay = LY.layout(db, m)
    deals_total = sum((CL.compute(db, d)["total_net"] or 0) for d in _deals(db, m))
    why = []
    if m.status != "черновик":
        why.append("ДС пакета уже созданы")
    if not lay["lines"]:
        why.append("нет позиций")
    try:
        prim = PR.primary_of(db, m)
    except MS.MasterError as e:
        why.append(e.message)
        prim = None
    if m.start_no is None and prim is None:      # с первичным ДС номер уже занят на старте
        why.append("не задан номер ДС")
    if abs(lay["total_net"] - deals_total) >= 0.05:
        why.append("сумма не сходится с суммой сделок")
    g = MS.gate(db, m)
    if not g["ok"]:
        why.append("сверка не завершена у всех сделок")
    return why


def _deals(db: Session, m: MasterDeal) -> list:
    from app.master_deal.models import MasterDealItem
    from app.sales.models import SalesDeal
    return [db.get(SalesDeal, i.deal_id) for i in db.query(MasterDealItem).filter(MasterDealItem.master_deal_id == m.id)]


def create(db: Session, m: MasterDeal, user) -> list:
    """Создать черновики ДС пакета из СОХРАНЁННОЙ раскладки. Возвращает [{id, kind, number}]."""
    from app.annex_tpl import document as tpl_doc
    from app.models import Contract
    from app.sales.annex import annex_date
    from app.sales.models import SalesAnnex, SalesDealAnnexAllocation
    PK._editable(db, m)
    why = ready(db, m)
    if why:
        raise MS.MasterError(409, "В конструктор ДС нельзя: " + ", ".join(why))
    c = db.get(Contract, m.contract_id)
    version, reason = tpl_doc.resolve(db, c)
    if version is None:
        raise MS.MasterError(409, reason or "У договора не определён шаблон ДС")
    pf, pt = _bounds(m.period)
    lay = LY.layout(db, m, with_src=True)
    prim = PR.primary_of(db, m)
    if prim is not None:
        from app.sales import annex_signed
        if annex_signed.signed_state(db, prim)["signed"]:        # подпись — перепроверка прямо сейчас
            return _close_on_signed(db, m, prim, lay)
    made = []
    for ds in lay["ds"]:
        sub = SUB_ADDONS if ds["kind"] == "addons" else None
        if prim is not None and ds["kind"] != "addons":
            # Первичный не подписан — важен только номер: этот же ДС пересобирается по факту (номер и дата прежние).
            a = prim
            # Вид остаётся «первичный» (так видно происхождение), снимок строк — по факту: у подписанного первичного снимка нет.
            a.rows, a.kind, a.master_deal_id, a.sub_no = _snapshot(ds), ds["kind"], m.id, None
            a.vat_rate = lay["vat_rate"]
            db.query(SalesDealAnnexAllocation).filter(SalesDealAnnexAllocation.annex_id == a.id).delete(synchronize_session=False)
        else:
            a = SalesAnnex(contract_id=c.id, period_from=pf, period_to=pt, date=annex_date(pf), total_amount=ds["gross"],
                           vat_rate=lay["vat_rate"], status="черновик", template_version_id=version.id,
                           created_by=getattr(user, "id", None), master_deal_id=m.id, kind=ds["kind"], sub_no=sub, rows=_snapshot(ds),
                           issue_kind="fact")
            db.add(a)
        db.flush()
        by_deal: dict = {}
        for g in ds["groups"]:
            for r in g["rows"]:
                by_deal[r["deal_id"]] = by_deal.get(r["deal_id"], 0.0) + r["net"]
        rate = (lay["vat_rate"] or 0) / 100.0
        for deal_id, net in by_deal.items():
            db.add(SalesDealAnnexAllocation(deal_id=deal_id, annex_id=a.id, amount=round(net * (1 + rate), 2)))
        for k in ds["upds"]:
            db.add(MasterDealUpd(master_deal_id=m.id, upd_no=k["upd_no"], annex_id=a.id, brand=k["brand"], service=k["service"],
                                 net=k["net"], vat=k["vat"], gross=k["gross"]))
        base = prim.no if (prim is not None and prim.no is not None) else (m.start_no or 0) + 1
        made.append({"id": a.id, "kind": ds["kind"],
                     "number": number_label(base, sub, DK.resolve(None, getattr(c, "annex_word", None), is_master=True)),
                     "deal_ids": list(by_deal),
                     "rebuilt": a is prim})
    db.flush()
    # Сумма документа — как её соберёт конструктор (НДС по строкам): иначе подтверждение отказало бы на копейке.
    for x in made:
        a = db.get(SalesAnnex, x["id"])
        model = tpl_doc.live(db, c, version, a, x.pop("deal_ids"))
        a.total_amount = model["amount"]
        if x.get("rebuilt") and a.no is not None:      # подтверждённый первичный — перезаморозить с тем же номером и датой
            from app.routers.annexes import rebuild_frozen
            try:
                rebuild_frozen(db, a, c)
            except Exception as e:                     # HTTPException сборки — понятным отказом пакета
                raise MS.MasterError(getattr(e, "status_code", 409), f"Первичный ДС не пересобрался: {getattr(e, 'detail', e)}")
    m.status, m.updated_at = "согласование", datetime.utcnow()
    db.flush()
    return made


def _close_on_signed(db: Session, m: MasterDeal, prim, lay: dict) -> list:
    """Первичный ДС подписан: ДС не трогаем, комплекты УПД по факту привязываем к нему. Закрытие больше ДС — нельзя (сверх — бонус)."""
    total = sum(ds["gross"] for ds in lay["ds"])
    if total > float(prim.total_amount or 0) + 0.01:
        raise MS.MasterError(409, f"Закрываем {total:,.2f} — больше подписанного ДС {float(prim.total_amount or 0):,.2f}; сверх ДС — бонус"
                             .replace(",", " "))
    for ds in lay["ds"]:
        for k in ds["upds"]:
            db.add(MasterDealUpd(master_deal_id=m.id, upd_no=k["upd_no"], annex_id=prim.id, brand=k["brand"], service=k["service"],
                                 net=k["net"], vat=k["vat"], gross=k["gross"]))
    prim.master_deal_id = m.id                          # ДС остаётся первичным, без снимка строк — печатается как был подписан
    m.status, m.updated_at = "согласование", datetime.utcnow()
    db.flush()
    return [{"id": prim.id, "kind": "primary_signed", "number": prim.number or "первичный ДС"}]


def revert(db: Session, m: MasterDeal) -> int:
    """«Вернуть в раскладку»: удалить черновики ДС пакета. Нельзя, если ДС подтверждён или по нему открыта заявка юристу."""
    from app.sales.models import SalesAnnex
    PK._editable(db, m)
    rows = db.query(SalesAnnex).filter(SalesAnnex.master_deal_id == m.id).all()
    # Первичный ДС пакета: подписанный (без снимка строк) — только отвязать; пересобранный по факту (со снимком) — назад нельзя.
    prim = [a for a in rows if a.issue_kind == "primary"]
    if any(a.rows is not None for a in prim):
        raise MS.MasterError(409, "Первичный ДС уже пересобран по факту — вернуть в раскладку нельзя, правьте ДС в конструкторе")
    if any(a.no is not None for a in rows if a not in prim):
        raise MS.MasterError(409, "ДС пакета уже подтверждён — изменить раскладку можно только через отзыв ДС у юриста")
    # Заявки юристу — история правок ДС: черновик с заявкой (даже закрытой) не удаляем, чтобы не терять её.
    legal = db.execute(text("SELECT count(*) FROM legal_requests WHERE annex_id = ANY(:a)"),
                       {"a": [a.id for a in rows if a not in prim] or [0]}).scalar()
    if legal:
        raise MS.MasterError(409, "По ДС пакета есть заявки юристу — вернуть в раскладку нельзя, правьте ДС в конструкторе")
    db.query(MasterDealUpd).filter(MasterDealUpd.master_deal_id == m.id).delete(synchronize_session=False)
    for a in rows:
        if a in prim:
            a.master_deal_id = None
        else:
            db.delete(a)
    m.status, m.updated_at = "черновик", datetime.utcnow()
    db.flush()
    return len(rows)


def annexes_of(db: Session, m: MasterDeal) -> list:
    from app.models import Contract
    from app.sales.models import SalesAnnex
    rows = db.query(SalesAnnex).filter(SalesAnnex.master_deal_id == m.id).order_by(SalesAnnex.id).all()
    base = (m.start_no or 0) + 1
    main_no = next((a.no for a in rows if a.no is not None and not a.sub_no), None)
    word = getattr(db.get(Contract, m.contract_id), "annex_word", None)
    # Номер черновика — тем же словом, что его документ: зафиксированный вид, иначе тумблер договора.
    return [{"id": a.id, "kind": a.kind,
             "number": a.number or number_label(main_no or base, a.sub_no, DK.resolve(a.doc_kind, word, is_master=True)),
             "confirmed": a.no is not None,
             "status": a.status, "gross": a.total_amount, "primary": a.issue_kind == "primary"} for a in rows]


def upds_of(db: Session, m: MasterDeal) -> list:
    """Комплекты УПД пакета с основанием: своё (правленое) или по умолчанию — по модели своего ДС (номер, дата, договор, период)."""
    from app.annex_tpl import document as tpl_doc
    from app.models import Contract
    from app.sales.models import SalesAnnex
    rows = db.query(MasterDealUpd).filter(MasterDealUpd.master_deal_id == m.id).order_by(MasterDealUpd.upd_no).all()
    if not rows:
        return []
    c = db.get(Contract, m.contract_id)
    models: dict = {}
    out = []
    for k in rows:
        if k.annex_id not in models:
            a = db.get(SalesAnnex, k.annex_id)
            deal_ids = [r[0] for r in db.execute(text("SELECT deal_id FROM sales_deal_annex_allocation WHERE annex_id = :a"), {"a": a.id})]
            models[k.annex_id] = (a, (tpl_doc.model_of(db, a, c, deal_ids) or {}).get("model") or {})
        a, model = models[k.annex_id]
        cl = tpl_doc.upd_closing(model, k, a.rows) if model else {"text": "", "template": "", "edited": False, "inherited_from": None}
        out.append({"upd_no": k.upd_no, "annex_id": k.annex_id, "annex_number": a.number or model.get("number"),
                    "brand": k.brand, "service": k.service, "gross": k.gross,
                    "basis": cl["text"], "basis_template": cl["template"], "basis_custom": bool(k.basis_text),
                    "basis_inherited_from": cl.get("inherited_from"), "values": {**(model.get("values") or {}), **(
                        {"бренд_название": k.brand.split(" / ")[-1].strip()} if k.brand else {})}})
    return out


def set_basis(db: Session, m: MasterDeal, upd_no: int, text_: Optional[str]) -> None:
    """Основание УПД: свой текст или пусто — «по умолчанию». Правится до отправки в 1С (после — сумма и основание у 1С)."""
    k = db.query(MasterDealUpd).filter_by(master_deal_id=m.id, upd_no=upd_no).first()
    if not k:
        raise MS.MasterError(404, f"УПД № {upd_no} в пакете нет")
    if k.onec_at:
        raise MS.MasterError(409, "Комплект уже ушёл в 1С — основание не правится")
    t = (text_ or "").strip() or None
    if t:                                               # та же проверка, что у основания в конструкторе ДС: подстановки известные
        from app.annex_tpl.assemble import CLOSING_KEY, validate_edit
        err = validate_edit([], CLOSING_KEY, t)
        if err:
            raise MS.MasterError(400, err)
    k.basis_text = t
    db.flush()
