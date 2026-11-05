# -*- coding: utf-8 -*-
"""Лог РК — журнал заметок по кампании на дашборде трафика (владелец 05.11.2026, хендофф `docs/design_handoff_rk_log.zip`).

Каждая заметка — отдельная запись, новые сверху; править и удалять нельзя (ручек нет, правку запрещает триггер базы),
ошибку исправляют новой записью. Время ставит сервер. Пишут ответственные этой сделки — трафик и аккаунт — и админ;
читают все, кому видна РК. Площадке лог не уходит никогда: в кабинет, письма и бот не подключать.

Уведомления: «проблема» — аккаунту сделки, запись аккаунта — ответственному трафику (автору — никогда, это делает `emit`).
"""
from typing import List

from sqlalchemy.orm import Session

from app.ad.models import AdCampaignNote
from app.notify import emit
from app.sales.deal_label import deal_label
from app.sales.models import SalesRep
from app.timez import to_msk

KINDS = {"note": "заметка", "agreement": "договорённость", "problem": "проблема"}
MAX_TEXT = 2000


class NoteError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _user_of(db: Session, rep_id) -> int:
    rep = db.get(SalesRep, rep_id) if rep_id else None
    return rep.user_id if rep else None


def can_write(db: Session, deal, user) -> bool:
    if getattr(getattr(user, "role", None), "key", None) == "admin":
        return True
    uid = getattr(user, "id", None)
    return uid is not None and uid in (_user_of(db, deal.account_manager_id), _user_of(db, deal.traffic_manager_id))


def _out(n: AdCampaignNote) -> dict:
    """Дата и время — уже московские и отдельными полями: экран их показывает как есть, не разбирая строку."""
    msk = to_msk(n.created_at) if n.created_at else None
    return {"id": n.id, "at": f"{msk:%d.%m.%Y %H:%M}" if msk else "", "date": f"{msk:%d.%m.%Y}" if msk else "",
            "time": f"{msk:%H:%M}" if msk else "", "author_id": n.author_id, "author": n.author_name, "kind": n.kind, "text": n.text}


def list_for(db: Session, campaign_id: int) -> List[dict]:
    rows = (db.query(AdCampaignNote).filter(AdCampaignNote.campaign_id == campaign_id)
            .order_by(AdCampaignNote.created_at.desc(), AdCampaignNote.id.desc()).all())
    return [_out(n) for n in rows]


def count_for(db: Session, campaign_id: int) -> int:
    return db.query(AdCampaignNote.id).filter(AdCampaignNote.campaign_id == campaign_id).count()


def add(db: Session, campaign, deal, user, kind: str, body: str) -> dict:
    if not can_write(db, deal, user):
        raise NoteError(403, "Писать в лог могут трафик и аккаунт этой РК")
    if kind not in KINDS:
        raise NoteError(422, "Тип записи — заметка, договорённость или проблема")
    body = (body or "").strip()
    if not body:
        raise NoteError(422, "Пустую запись не добавить")
    if len(body) > MAX_TEXT:
        raise NoteError(422, f"Запись длиннее {MAX_TEXT} знаков")
    n = AdCampaignNote(campaign_id=campaign.id, author_id=getattr(user, "id", None),
                       author_name=getattr(user, "name", None) or "—", kind=kind, text=body)
    db.add(n)
    db.flush()
    db.refresh(n)
    _notify(db, deal, n, user)
    return _out(n)


def _notify(db: Session, deal, n: AdCampaignNote, user) -> None:
    head = f"{KINDS[n.kind].capitalize()} · {deal_label(deal)}"
    short = n.text if len(n.text) <= 200 else n.text[:197] + "…"
    link = f"/traffic/dashboard?open={deal.code}"        # дашборд раскрывает РК по коду сделки (`?open=`)
    if n.kind == "problem":
        emit(db, "rk_note_problem", title=f"Проблема в логе РК · {deal_label(deal)}", body=f"{n.author_name}: {short}",
             link=link, entity_type="sales_deal", entity_id=deal.id, actor=user, ctx={"deal": deal})
    if getattr(user, "id", None) is not None and user.id == _user_of(db, deal.account_manager_id):
        emit(db, "rk_note_from_account", title=f"Аккаунт написал в лог РК · {head}", body=short,
             link=link, entity_type="sales_deal", entity_id=deal.id, actor=user, ctx={"deal": deal})
