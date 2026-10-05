"""Отчёт клиенту по РК — выгрузка Excel (владелец 05.10.2026; данные — app/ad/client_report,
вид — app/ad/client_report_xlsx).

Кнопка — в раскрытой строке очереди аккаунта перед «Карточкой». Права: дашборд аккаунта или
дашборд трафика (+ админ). Аккаунт видит отчёт только по сделке из своей зоны видимости;
трафик — по любой РК, как на своём дашборде. У сделки одна РК (замер прода 05.10.2026: 139 из
139), отчёт строится по ней. В файле два комплекта листов: факт и модель SIMB ID.
"""
import re
from datetime import date
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.permissions import get_permissions_for_user, require_any_permission

router = APIRouter()
VIEW = require_any_permission(("accounts_dashboard", "traffic_dashboard"), "view")


def _day(v: Optional[str], what: str) -> Optional[date]:
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{what}: дата в виде ГГГГ-ММ-ДД")


@router.get("/deal/{deal_id}.xlsx")
def deal_report(deal_id: int, date_from: Optional[str] = None, date_to: Optional[str] = None,
                db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    from app.ad import client_report, client_report_xlsx
    from app.ad.models import AdCampaign
    from app.sales.models import SalesDeal

    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    perms = get_permissions_for_user(db, current_user)
    traffic = current_user.role.key == "admin" or (perms.get("traffic_dashboard") or {}).get("view")
    if not traffic:
        from app.routers.sales_dashboard import _assert_deal_in_scope
        _assert_deal_in_scope(db, current_user, deal)
    camp = (db.query(AdCampaign).filter(AdCampaign.deal_id == deal.id)
            .order_by(AdCampaign.id.desc()).first())
    if camp is None:
        raise HTTPException(status_code=404, detail="У сделки нет РК — отчёт строить не по чему")
    if client_report.last_data_day(db, camp.id) is None:
        raise HTTPException(status_code=409, detail="Статистики по РК ещё нет — отчёт появится "
                                                    "после первого дня с показами")
    d1, d2 = _day(date_from, "Начало периода"), _day(date_to, "Конец периода")
    if d1 and d2 and d1 > d2:
        raise HTTPException(status_code=400, detail="Начало периода позже конца")

    dsp_db = None
    try:
        from app.dsp.db import DspSessionLocal
        dsp_db = DspSessionLocal() if DspSessionLocal else None
        rep = client_report.build(db, camp.id, d1, d2, dsp_db=dsp_db)
        rep_m = client_report.build(db, camp.id, d1, d2, dsp_db=dsp_db, model=True)
    finally:
        if dsp_db is not None:
            dsp_db.close()
    h = rep.head
    if not h["period_from"] or not h["period_to"] or h["period_from"] > h["period_to"] \
            or not rep.totals["shows"]:
        raise HTTPException(status_code=409, detail="За выбранный период данных нет — "
                                                    "пустой отчёт клиенту не отдаём")
    body = client_report_xlsx.to_xlsx(rep, rep_m)
    code = re.sub(r"[^\w-]", "", deal.code or str(deal.id))
    human = f"Отчёт_РК_{code}_{date.today():%d.%m.%Y}.xlsx"
    return Response(content=body, media_type=(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"), headers={
        "Content-Disposition": f"attachment; filename=\"report_{code}.xlsx\"; "
                               f"filename*=UTF-8''{quote(human)}"})
