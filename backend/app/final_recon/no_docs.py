# -*- coding: utf-8 -*-
"""«Закрыть без документов» (владелец 19.10.2026): бонусное размещение — сумма медиаплана 0 ₽ (база и платные допы: МП целиком
бонусный или со скидкой 100 %). Сверка замораживается так же, как при «Отправить в ДО»; в мастер-сделку, ДС и 1С сделка не попадает и сразу
уходит в «Архив успешных сделок». Требования документооборота к ней не применяются — документов по ней нет по смыслу;
в истории стадий — причина перехода."""
from datetime import datetime

from sqlalchemy.orm import Session

from app.final_recon import closing as CL
from app.final_recon.checks import RECON_STAGE

ARCHIVE = "Архив успешных сделок"
REASON = "Закрыто без документов: бонусное размещение (сумма МП 0 ₽)"


def close(db: Session, deal, user) -> dict:
    from app.master_deal import service as MS
    from app.sales import stage_move
    from app.sales.catalog import Catalog

    st = CL.compute(db, deal)
    if st["no_docs"]["closed_at"]:
        raise CL.ClosingError(409, "Сделка уже закрыта без документов")
    if not st["no_docs"]["eligible"]:
        raise CL.ClosingError(409, "Без документов закрывается только бонусное размещение — сумма медиаплана 0 ₽")
    if MS.item_of(db, deal.id):
        raise CL.ClosingError(409, "Сделка уже в мастер-сделке — закрывается через документы")
    cat = Catalog(db)
    cur = cat.by_id.get(deal.our_stage_id)
    if not cur or cur.name != RECON_STAGE:
        raise CL.ClosingError(409, f"«Закрыть без документов» — со стадии «{RECON_STAGE}», а сделка на «{cur.name if cur else '—'}»")
    target = next((x for x in cat.by_id.values() if x.name == ARCHIVE), None)
    if target is None:
        raise CL.ClosingError(409, f"Нет стадии «{ARCHIVE}» — проверьте каталог стадий")
    rec = CL._rec(db, deal.id)
    rec.ds_mode = "plan"          # сумма МП = 0 ₽; «По факту» без факта не посчиталась бы, и заморозка отказала
    db.flush()
    CL.freeze(db, deal, user)
    rec.closed_no_docs_at, rec.closed_no_docs_by = datetime.utcnow(), getattr(user, "id", None)
    db.flush()
    res = stage_move.apply_move(db, deal, target, user, reason=REASON, catalog=cat)
    return {**CL.compute(db, deal, rec=rec), "moved_to": target.name if res.get("moved") else None}
