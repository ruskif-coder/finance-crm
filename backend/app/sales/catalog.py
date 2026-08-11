"""Наш каталог стадий (E1/E2): порядок, следующая/предыдущая, сериализация.

Порядок движения = стадии по (этап.sort_order, стадия.sort_order). Терминальные
(«не случилась»/«сорвалась») не входят в основную цепочку — это ветвящиеся исходы.
"""
from app.sales.models import SalesStagePhase, SalesStage
from app.sales.stages import STAGE_BY_KEY


class Catalog:
    """Загруженный один раз каталог для O(1) next/prev и сериализации (без N+1)."""
    def __init__(self, db):
        phases = (db.query(SalesStagePhase)
                  .order_by(SalesStagePhase.sort_order, SalesStagePhase.id).all())
        self.stages = []
        for ph in phases:
            for s in sorted(ph.stages, key=lambda x: (x.sort_order, x.id)):
                self.stages.append(s)
        self.by_id = {s.id: s for s in self.stages}
        self.flow = [s.id for s in self.stages if not s.is_terminal]   # основная цепочка
        self.terminals = [s for s in self.stages if s.is_terminal]

    def first(self):
        return self.by_id[self.flow[0]] if self.flow else None

    def next_of(self, stage_id):
        if stage_id in self.flow:
            i = self.flow.index(stage_id)
            return self.by_id[self.flow[i + 1]] if i + 1 < len(self.flow) else None
        return self.first()   # текущей нет в цепочке (терминал/пусто) → первая

    def prev_of(self, stage_id):
        if stage_id in self.flow:
            i = self.flow.index(stage_id)
            return self.by_id[self.flow[i - 1]] if i > 0 else None
        return None

    def is_before(self, a_id, b_id):
        """a раньше b в основной цепочке?"""
        if a_id in self.flow and b_id in self.flow:
            return self.flow.index(a_id) < self.flow.index(b_id)
        return False


def stage_public(s):
    """Публичное представление стадии для API."""
    if not s:
        return None
    cat = STAGE_BY_KEY.get(s.stage_key)
    return {
        "id": s.id, "name": s.name,
        "phase_id": s.phase_id,
        "phase": s.phase.name if s.phase else None,
        "is_realization_phase": bool(s.phase.is_realization) if s.phase else False,
        "stage_key": s.stage_key,
        "money_layer": cat["money_layer"] if cat else s.money_layer,
        "is_terminal": bool(s.is_terminal),
        "requires_media_plan": bool(s.requires_media_plan),
    }
