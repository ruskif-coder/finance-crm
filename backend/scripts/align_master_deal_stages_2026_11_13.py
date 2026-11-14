# -*- coding: utf-8 -*-
"""Разово: поставить сделки мастер-сделок на стадии их статуса (владелец 13.11.2026: «засинхронить мастер-сделку со сделками»).

До 13.11 сделки пакета стояли на «Подготовке ДС» и в «согласовании», и в «ждём 1С», и на «выставлении» — со стадиями
сделок синхронизировались только «ждём оплату» и «архив». Новое соответствие — `app/master_deal/deal_stages.STAGE`;
скрипт прогоняет `align` по всем пакетам, кроме архивных.

    docker exec finance_backend python -m scripts.align_master_deal_stages_2026_11_13            # показать, ничего не писать
    docker exec finance_backend python -m scripts.align_master_deal_stages_2026_11_13 --apply    # записать
"""
import sys

import app.model_registry  # noqa: F401 — все таблицы для внешних ключей
from app.database import SessionLocal
from app.master_deal import deal_stages as DST
from app.master_deal import status as ST
from app.master_deal.models import MasterDeal


class _System:
    id = None
    name = "система (синхронизация стадий 13.11.2026)"


def main(apply: bool) -> int:
    db = SessionLocal()
    try:
        moved = 0
        for m in db.query(MasterDeal).filter(MasterDeal.status != ST.ARCHIVE).order_by(MasterDeal.id):
            out = DST.align(db, m, _System())
            if out["moved"] or out["skipped"]:
                print(f"{m.code} «{m.status}» → «{DST.STAGE.get(m.status, '—')}»: сдвинуты {out['moved'] or '—'}"
                      + (f"; не тронуты: {'; '.join(out['skipped'])}" if out["skipped"] else ""))
            moved += len(out["moved"])
        print(f"итого сделок к переводу: {moved}" + ("" if apply else " (без --apply ничего не записано)"))
        if apply:
            db.commit()
        else:
            db.rollback()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
