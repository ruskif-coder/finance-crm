# -*- coding: utf-8 -*-
"""Сделки пакета идут за его статусом (владелец 19.10.2026; 13.11.2026 — «засинхронить мастер-сделку со сделками»).

Каждому статусу пакета — своя стадия сделок (`STAGE`): черновик → Подготовка ДС, согласование → Согласование ДС, ждём 1С →
Подготовка закрывающих, выставление → ЭДО (и у бумаги: «документы у клиента»), ждём оплату / ждём сканы → Оплата, архив →
Архив успешных сделок. «Отчёты в ОРД» пакет проскакивает — статуса для неё нет (акты подаются отчётом за месяц). Откат пакета
ведёт сделки тем же путём назад. «Ждём закрытия» стадий не двигает: это стартовый пакет, РК ещё идёт.

Двигаем только сделку, стоящую на одной из стадий ДО, которыми управляет пакет (`OWNED`): увели руками за пределы ДО — не
трогаем и называем её в ответе, чтобы расхождение было видно, а не исчезло молча. Сделка не обязана стоять ровно на стадии
прежнего статуса: `align` догоняет отставшие (сделки пакетов, созданных до 13.11.2026, стояли на «Подготовке ДС»)."""
from sqlalchemy.orm import Session

from app.sales import stage_slots as SS
from app.master_deal.status import AGREE, ARCHIVE, DRAFT, ISSUE, WAIT_1C, WAIT_PAY, WAIT_SCANS

STAGE = {DRAFT: SS.DS_PREP, AGREE: SS.DS_AGREE, WAIT_1C: SS.CLOSING, ISSUE: SS.EDO,
         WAIT_PAY: SS.PAY, WAIT_SCANS: SS.PAY, ARCHIVE: SS.ARCHIVE}
OWNED = set(STAGE.values())          # стадии ДО, на которых сделкой управляет пакет
REASON = "мастер-сделка {code}: {status}"


def align(db: Session, m, user) -> dict:
    """Поставить сделки пакета на стадию его текущего статуса. → {moved: [коды], skipped: [почему]}. Повтор — без движений."""
    from app.master_deal import start as SP
    from app.master_deal.models import MasterDealItem
    from app.sales import stage_move
    from app.sales.catalog import Catalog
    from app.sales.models import SalesDeal
    out = {"moved": [], "skipped": []}
    if m.status not in STAGE or SP.in_start_phase(db, m):
        return out
    cat = Catalog(db)
    by_name = {x.name: x for x in cat.by_id.values()}
    dst = by_name.get(STAGE[m.status])
    if dst is None:
        out["skipped"].append(f"нет стадии «{STAGE[m.status]}» в каталоге")
        return out
    for it in db.query(MasterDealItem).filter(MasterDealItem.master_deal_id == m.id).order_by(MasterDealItem.id):
        d = db.get(SalesDeal, it.deal_id)
        cur = cat.by_id.get(d.our_stage_id)
        if d.our_stage_id == dst.id:
            continue
        if cur is None or cur.name not in OWNED:
            out["skipped"].append(f"{d.code} на «{cur.name if cur else '—'}» — вне стадий пакета")
            continue
        stage_move.apply_move(db, d, dst, user, reason=REASON.format(code=m.code, status=m.status), catalog=cat)
        out["moved"].append(d.code)
    db.flush()
    return out


def follow(db: Session, m, was: str, user) -> dict:
    """Пакет сменил статус `was` → `m.status`: сделки — за ним (`align`)."""
    if was == m.status:
        return {"moved": [], "skipped": []}
    return align(db, m, user)


def journal_tail(out: dict, status: str) -> str:
    """Хвост строки журнала о переходе пакета: какие сделки куда переехали и какие не тронуты."""
    parts = ([f"сделки → «{STAGE[status]}»: {', '.join(out['moved'])}"] if out["moved"] else []) + \
            ([f"не тронуты: {'; '.join(out['skipped'])}"] if out["skipped"] else [])
    return ("; " + "; ".join(parts)) if parts else ""
