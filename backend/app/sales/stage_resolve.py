"""Резолвер НАШЕЙ стадии (our_stage) по битрикс-позиции сделки.

our_stage — мастер слоя денег (read-side флип 2026-08-12, см. docs/PLAN_stage_master_flip.md).
Каждая сделка ОБЯЗАНА иметь our_stage_id, иначе выпадает в «Без группы». Импорт и
разовый сид проставляют его так:
  1) явная привязка нашей стадии к паре (bitrix_pipeline, bitrix_status) — приоритет
     (SalesStage.bitrix_pipeline_id + bitrix_status_id);
  2) легаси-мост по stage_key через SalesBitrixStageMap: пара (pipeline, bitrix_stage) →
     stage_key → первая наша стадия с этим stage_key.

Тай-брейк «одна битрикс-стадия → несколько наших» (наша лестница мельче): берём ПЕРВУЮ
по (этап.sort_order, стадия.sort_order) — точку входа, дальше двигают вручную.
Не сматчилось → None: our_stage_id остаётся NULL («требует разбора»).
"""
from app.sales.models import (SalesStage, SalesStagePhase, SalesPipeline,
                              SalesPipelineStage, SalesBitrixStageMap)


class OurStageResolver:
    """Строит индексы один раз — для сида/импорта пачкой без N+1."""

    def __init__(self, db):
        stages = (db.query(SalesStage)
                  .join(SalesStagePhase, SalesStagePhase.id == SalesStage.phase_id)
                  .order_by(SalesStagePhase.sort_order, SalesStage.sort_order, SalesStage.id)
                  .all())
        # Первая наша стадия по каждому stage_key (порядок каталога = приоритет входа).
        self._by_key = {}
        for s in stages:
            if s.stage_key and s.stage_key not in self._by_key:
                self._by_key[s.stage_key] = s.id
        # Явные привязки: (имя воронки, имя стадии Битрикса) → our_stage_id (первая).
        pipe_name = {p.id: p.name for p in db.query(SalesPipeline).all()}
        pstage_name = {(ps.pipeline_id, ps.status_id): ps.name
                       for ps in db.query(SalesPipelineStage).all()}
        self._by_binding = {}
        for s in stages:
            if s.bitrix_pipeline_id and s.bitrix_status_id:
                k = (pipe_name.get(s.bitrix_pipeline_id),
                     pstage_name.get((s.bitrix_pipeline_id, s.bitrix_status_id)))
                if all(k) and k not in self._by_binding:
                    self._by_binding[k] = s.id
        # Легаси-мост по stage_key (переходный fallback, пока привязки не заполнены).
        self._pair_key = {(m.pipeline, m.bitrix_stage): m.stage_key
                          for m in db.query(SalesBitrixStageMap)
                          .filter(SalesBitrixStageMap.is_active.is_(True)).all()}

    def resolve(self, pipeline, bitrix_stage):
        sid = self._by_binding.get((pipeline, bitrix_stage))
        if sid:
            return sid
        key = self._pair_key.get((pipeline, bitrix_stage))
        if key:
            return self._by_key.get(key)
        return None
