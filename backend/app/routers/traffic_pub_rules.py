"""Админка трафика → «Особенности площадок» (владелец 27–29.09.2026).

По каждой поверхности площадки: канал размещения (DSP / Adfox / вне контура), ссылки в
app (веб / обе), доп. код Adfox для `%user6%`. Право — своё, `traffic_publisher_rules`
(«трафик админ»): без бэкфилла, выдаёт владелец. Применение правил — app/launch_prep/pub_rules.py.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.launch_prep import pub_rules
from app.models import User
from app.permissions import require_permission
from app.sales.models import SalesPublisher, SalesPublisherSurface

router = APIRouter()
VIEW = require_permission("traffic_publisher_rules", "view")
EDIT = require_permission("traffic_publisher_rules", "edit")
CODE_MAX = 8000


@router.get("/publisher-rules")
def list_rules(db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    pubs = {p.id: p for p in db.query(SalesPublisher).filter(SalesPublisher.status != "АРХИВ")}
    rows = (db.query(SalesPublisherSurface)
            .filter(SalesPublisherSurface.publisher_id.in_(pubs or [0])).all())
    items = [{"surface_id": s.id, "publisher_id": s.publisher_id,
              "publisher": pubs[s.publisher_id].name, "kind": s.kind,
              "placement_channel": s.placement_channel, "app_links": s.app_links,
              "adfox_extra_code": s.adfox_extra_code,
              "problem": (pub_rules.pair_problem(pub_rules.rule_of(s), "x", "x"))}
             for s in rows]
    items.sort(key=lambda x: (x["publisher"].lower(), x["kind"] != "web"))
    return {"items": items, "channels": pub_rules.CHANNELS, "app_links": pub_rules.APP_LINKS}


class RuleIn(BaseModel):
    placement_channel: Optional[str] = None
    app_links: Optional[str] = None
    adfox_extra_code: Optional[str] = None


@router.put("/publisher-rules/{surface_id}")
def update_rule(surface_id: int, payload: RuleIn, db: Session = Depends(get_db),
                current_user: User = Depends(EDIT)):
    s = db.query(SalesPublisherSurface).filter(SalesPublisherSurface.id == surface_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Поверхность площадки не найдена")
    ch = payload.placement_channel or None
    if ch and ch not in pub_rules.CHANNELS:
        raise HTTPException(status_code=400, detail="Канал: dsp, adfox или outside")
    links = pub_rules.normalize_app_links(payload.app_links)
    if links and links not in pub_rules.APP_LINKS:
        raise HTTPException(status_code=400, detail="Ссылки для app: both или sdk "
                            "(режим «веб» снят 05.10.2026 — DSP требует макрос в ссылке)")
    if links and s.kind != "app":
        raise HTTPException(status_code=400, detail="Режим ссылок задаётся только у app-поверхности")
    code = (payload.adfox_extra_code or "").strip() or None
    if code and len(code) > CODE_MAX:
        raise HTTPException(status_code=400, detail=f"Доп. код длиннее {CODE_MAX} символов")
    before = (s.placement_channel, s.app_links, bool(s.adfox_extra_code))
    s.placement_channel, s.app_links, s.adfox_extra_code = ch, links, code
    db.commit()
    pub = db.query(SalesPublisher).get(s.publisher_id)
    log_action(db, current_user, "publisher_rules_update", "sales_publisher", s.publisher_id,
               f"{pub.name if pub else s.publisher_id} {s.kind}: канал {before[0]}→{ch}, "
               f"ссылки {before[1]}→{links}, доп. код {'есть' if code else 'нет'}")
    return {"surface_id": s.id, "placement_channel": ch, "app_links": links,
            "adfox_extra_code": code, "problem": pub_rules.pair_problem(pub_rules.rule_of(s), "x", "x")}
