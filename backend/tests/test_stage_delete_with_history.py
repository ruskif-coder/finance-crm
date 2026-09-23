# -*- coding: utf-8 -*-
"""Прибор: стадию, через которую сделки уже проходили, удалить нельзя — и без 500 (аудит 3.L7).

История переходов ссылается на стадию внешним ключом без каскада: удаление падало с 500.
Историю не стираем — она ответ на «как сделка шла», — отказываем с объяснением.
"""
import pytest
from fastapi import HTTPException

import app.ad.models           # noqa: F401
import app.launch_prep.models  # noqa: F401
import app.notify.models       # noqa: F401
import app.ord.models          # noqa: F401
from app.database import SessionLocal
from app.models import User
from app.routers import sales_directories as sdir
from app.sales.models import SalesDeal, SalesDealStageHistory, SalesStage, SalesStagePhase


def test_stage_with_history_is_refused_not_500():
    db = SessionLocal()
    db.commit = db.flush
    try:
        admin = db.query(User).filter(User.is_active == 1, User.role.has(key="admin")).first()
        phase = db.query(SalesStagePhase).order_by(SalesStagePhase.sort_order).first()
        # Своя стадия в первом этапе, через неё проходила сделка (история), но сейчас на ней
        # никто не стоит — ровно тот случай, что падал с 500.
        st = SalesStage(phase_id=phase.id, name="прибор истории", sort_order=999)
        db.add(st)
        db.flush()
        deal = db.query(SalesDeal).filter(SalesDeal.our_stage_id.isnot(None)).first()
        if admin is None or phase is None or deal is None:
            pytest.skip("нужны админ, этап и сделка со стадией")
        db.add(SalesDealStageHistory(deal_id=deal.id, from_stage_id=st.id,
                                     to_stage_id=deal.our_stage_id))
        db.flush()
        phases = []
        for ph in db.query(SalesStagePhase).order_by(SalesStagePhase.sort_order).all():
            stages = [sdir.StageIn(id=s.id, name=s.name, stage_key=s.stage_key,
                                   is_terminal=bool(s.is_terminal),
                                   bitrix_pipeline_id=s.bitrix_pipeline_id,
                                   bitrix_status_id=s.bitrix_status_id)
                      for s in sorted(ph.stages, key=lambda x: (x.sort_order, x.id))
                      if s.id != st.id]
            phases.append(sdir.PhaseIn(id=ph.id, name=ph.name, stages=stages))
        with pytest.raises(HTTPException) as e:
            sdir.save_stage_catalog(sdir.StageCatalogIn(phases=phases), db=db, current_user=admin)
        assert e.value.status_code == 409 and "прибор истории" in e.value.detail
    finally:
        db.rollback()
        db.close()
