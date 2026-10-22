# -*- coding: utf-8 -*-
"""Сделки пакета идут за его статусом (владелец 19.10.2026).

Пока пакет на «выставлении», его сделки стоят на «Подготовке ДС» (туда их переводит «Отправить в ДО»). Дальше:
«ждём оплату» → «Оплата», «архив» → «Архив успешных сделок»; откат пакета ведёт сделки тем же путём назад.
Двигаем только сделку, которая стоит там, где её оставил пакет: увели руками — не трогаем и называем её в ответе,
чтобы расхождение было видно, а не исчезло молча. Ранние статусы (черновик…ждём 1С) стадий не двигают."""
from sqlalchemy.orm import Session

from app.master_deal.status import ARCHIVE, ISSUE, WAIT_PAY, WAIT_SCANS

STAGE = {ISSUE: "Подготовка ДС", WAIT_PAY: "Оплата", WAIT_SCANS: "Оплата", ARCHIVE: "Архив успешных сделок"}   # «ждём сканы» — деньги пришли, сделки остаются на «Оплате» до архива
REASON = "мастер-сделка {code}: {status}"


def follow(db: Session, m, was: str, user) -> dict:
    from app.master_deal.models import MasterDealItem
    from app.sales import stage_move
    from app.sales.catalog import Catalog
    from app.sales.models import SalesDeal
    out = {"moved": [], "skipped": []}
    if was not in STAGE or m.status not in STAGE or was == m.status:
        return out
    cat = Catalog(db)
    by_name = {x.name: x for x in cat.by_id.values()}
    src, dst = by_name.get(STAGE[was]), by_name.get(STAGE[m.status])
    if src is None or dst is None:
        out["skipped"].append(f"нет стадии «{STAGE[was] if src is None else STAGE[m.status]}» в каталоге")
        return out
    for it in db.query(MasterDealItem).filter(MasterDealItem.master_deal_id == m.id).order_by(MasterDealItem.id):
        d = db.get(SalesDeal, it.deal_id)
        if d.our_stage_id != src.id:
            cur = cat.by_id.get(d.our_stage_id)
            out["skipped"].append(f"{d.code} на «{cur.name if cur else '—'}», а не на «{src.name}»")
            continue
        stage_move.apply_move(db, d, dst, user, reason=REASON.format(code=m.code, status=m.status), catalog=cat)
        out["moved"].append(d.code)
    db.flush()
    return out


def journal_tail(out: dict, status: str) -> str:
    """Хвост строки журнала о переходе пакета: какие сделки куда переехали и какие не тронуты."""
    parts = ([f"сделки → «{STAGE[status]}»: {', '.join(out['moved'])}"] if out["moved"] else []) + \
            ([f"не тронуты: {'; '.join(out['skipped'])}"] if out["skipped"] else [])
    return ("; " + "; ".join(parts)) if parts else ""
