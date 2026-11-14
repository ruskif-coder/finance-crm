# -*- coding: utf-8 -*-
"""ДЕМО на локальном стенде (владелец 14.11.2026): в каждой стадии «Моих сделок» — хотя бы одна сделка каждой услуги.

Стадии: МП Подготовка, МП Отправлено, Бронь, Готовятся к старту, В размещении, Итоговая сверка. Для пустого сочетания
«стадия × услуга» создаётся копия реальной сделки той же услуги со стенда (рекламодатель, бренд, агентство, ответственные, договоры,
сумма); у услуги без сделок (Спецпроект) — копия сделки Альфарм-Таргета с заменой услуги. Период: песочница и бронь — следующий
месяц, сборка и размещение — текущий, сверка — прошлый. Название начинается с «ДЕМО ·».

Метка созданного — `bitrix_id` вида `demo-fill-…`: `--undo` удаляет ровно эти сделки (история стадий уходит каскадом).
Только для стенда: на проде не запускать.

    docker exec -e STAND=1 finance_backend python -m scripts.demo_stage_service_fill_2026_11_14            # план, без записи
    docker exec -e STAND=1 finance_backend python -m scripts.demo_stage_service_fill_2026_11_14 --apply
    docker exec -e STAND=1 finance_backend python -m scripts.demo_stage_service_fill_2026_11_14 --mp --apply   # МП демо-сделкам без плана
    docker exec -e STAND=1 finance_backend python -m scripts.demo_stage_service_fill_2026_11_14 --undo
"""
import calendar
import sys
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.final_recon.flow import service_pipeline
from app.sales.deal_code import assign_code
from app.sales.models import SalesDeal, SalesDealStageHistory
from scripts._stand_guard import require_stand

MARK = "demo-fill-"
STAGES = ["МП Подготовка", "МП Отправлено", "Бронь", "Готовятся к старту", "В размещении", "Итоговая сверка"]
FALLBACK_SERVICE = "Альфарм-Таргет"          # образец для услуги, у которой на стенде нет ни одной сделки


def _month(d: date, shift: int):
    y, m = d.year, d.month + shift
    while m > 12:
        y, m = y + 1, m - 12
    while m < 1:
        y, m = y - 1, m + 1
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def _period(stage: str, today: date):
    if stage in ("МП Подготовка", "МП Отправлено", "Бронь"):
        return _month(today, 1)
    if stage == "Итоговая сверка":
        return _month(today, -1)
    return _month(today, 0)


def _missing(db):
    return db.execute(text("""
        SELECT st.id AS stage_id, st.name AS stage, sv.id AS service_id, sv.name AS service
          FROM sales_stages st CROSS JOIN sales_services sv
         WHERE st.name = ANY(:st)
           AND NOT EXISTS (SELECT 1 FROM sales_deals d WHERE d.our_stage_id = st.id AND d.service_id = sv.id)
         ORDER BY array_position(:st, st.name::text), sv.id"""), {"st": STAGES}).mappings().all()


def _template(db, service_id: int):
    # Образец — с медиапланом (строки МП нужны сверке, сборке и плиткам), потом — с рекламодателем и плательщиком.
    tid = db.execute(text(f"""SELECT id FROM sales_deals WHERE service_id = :s AND bitrix_id NOT LIKE :m
                              ORDER BY {HAS_MP} DESC, (advertiser_id IS NOT NULL AND payer_counterparty_id IS NOT NULL) DESC, id DESC LIMIT 1"""),
                     {"s": service_id, "m": MARK + "%"}).scalar()
    if tid is None:
        tid = db.execute(text("""SELECT d.id FROM sales_deals d JOIN sales_services s ON s.id = d.service_id
                                  WHERE s.name = :n AND d.bitrix_id NOT LIKE :m ORDER BY d.id DESC LIMIT 1"""),
                         {"n": FALLBACK_SERVICE, "m": MARK + "%"}).scalar()
    return db.get(SalesDeal, tid) if tid else None


HAS_MP = "EXISTS (SELECT 1 FROM sales_media_plans mp JOIN sales_media_plan_rows r ON r.plan_id = mp.id WHERE mp.deal_id = sales_deals.id AND mp.status <> 'rejected')"
PLAN_COLS = ("version, status, title, advertiser_id, brand_id, agency_id, payer_counterparty_id, period, geo_id, date_from, date_to, "
             "targeting, goals, sales_rep_id, account_manager_id, traffic_manager_id, amount_net, amount_gross, vat_rate, verified_at, verified_by")
ROW_COLS = "sort_order, position, format, model, inventory, volume, unit_price, discount, forecast"


def _copy_mp(db, src_id: int, deal: SalesDeal) -> bool:
    """Действующий медиаплан образца со строками — демо-сделке, своей группой версий (не версия плана образца)."""
    pid = db.execute(text("SELECT id FROM sales_media_plans WHERE deal_id = :d AND status <> 'rejected' ORDER BY version DESC, id DESC LIMIT 1"),
                     {"d": src_id}).scalar()
    if pid is None:
        return False
    new_pid = db.execute(text(f"""INSERT INTO sales_media_plans (deal_id, date_from, date_to, {PLAN_COLS.replace('date_from, date_to, ', '')})
        SELECT :deal, :f, :t, {PLAN_COLS.replace('date_from, date_to, ', '')} FROM sales_media_plans WHERE id = :p RETURNING id"""),
                         {"deal": deal.id, "f": deal.period_from, "t": deal.period_to, "p": pid}).scalar()
    # Период МП — месяц сделки, а не образца: иначе перенос сделки двигал МП от чужого месяца (test_sales_status, 14.11.2026).
    db.execute(text("UPDATE sales_media_plans SET group_id = id, period = :per WHERE id = :p"),
               {"p": new_pid, "per": deal.period_from.strftime("%Y-%m") if deal.period_from else None})
    db.execute(text(f"INSERT INTO sales_media_plan_rows (plan_id, {ROW_COLS}) SELECT :n, {ROW_COLS} FROM sales_media_plan_rows WHERE plan_id = :p"),
               {"n": new_pid, "p": pid})
    return True


def _copy(db, src: SalesDeal, cell, today: date) -> SalesDeal:
    pf, pt = _period(cell["stage"], today)
    realization = cell["stage"] in ("Бронь", "Готовятся к старту", "В размещении", "Итоговая сверка")
    new = SalesDeal(
        bitrix_id=MARK + uuid.uuid4().hex,
        title=f"ДЕМО · {cell['service']} · {cell['stage']}", pipeline=src.pipeline, bitrix_stage=src.bitrix_stage,
        amount=src.amount, amount_with_vat=src.amount_with_vat, currency=src.currency,
        counterparty_id=src.counterparty_id, payer_counterparty_id=src.payer_counterparty_id, payer_name=src.payer_name,
        advertiser_id=src.advertiser_id, brand_id=src.brand_id, agency_id=src.agency_id,
        product=cell["service"], service_id=cell["service_id"],
        sales_rep_id=src.sales_rep_id, account_manager_id=src.account_manager_id, traffic_manager_id=src.traffic_manager_id,
        is_self_promo=src.is_self_promo,
        ord_initial_contract_id=src.ord_initial_contract_id, ord_final_contract_id=src.ord_final_contract_id,
        ord_direct_advertiser=src.ord_direct_advertiser,
        realization_pipeline_id=service_pipeline(db, cell["service_id"]) if realization else None,
        our_stage_id=cell["stage_id"], period_from=pf, period_to=pt,
        date_create=datetime.utcnow() - timedelta(days=3),
    )
    assign_code(db, new)
    db.add(new)
    db.flush()
    db.add(SalesDealStageHistory(deal_id=new.id, from_stage_id=None, to_stage_id=cell["stage_id"], user_id=None,
                                 reason="демо на стенде: заполнение стадий «Моих сделок» (14.11.2026)"))
    _copy_mp(db, src.id, new)
    return new


def main():
    require_stand("демо: стадии × услуги")      # демо-данные — только на стенде (tests/test_demo_scripts_stand_only.py)
    apply, undo, mp = "--apply" in sys.argv, "--undo" in sys.argv, "--mp" in sys.argv
    db = SessionLocal()
    try:
        if undo:
            ids = "SELECT id FROM sales_deals WHERE bitrix_id LIKE :m"
            db.execute(text(f"DELETE FROM sales_media_plan_rows WHERE plan_id IN (SELECT id FROM sales_media_plans WHERE deal_id IN ({ids}))"),
                       {"m": MARK + "%"})
            db.execute(text(f"DELETE FROM sales_media_plans WHERE deal_id IN ({ids})"), {"m": MARK + "%"})
            n = db.execute(text("DELETE FROM sales_deals WHERE bitrix_id LIKE :m"), {"m": MARK + "%"}).rowcount
            db.commit()
            print(f"снято демо-сделок: {n}")
            return
        if mp:
            # Демо-сделкам без медиаплана — план образца той же услуги (созданы до 14.11, когда МП не копировался).
            ids = db.execute(text(f"SELECT id FROM sales_deals WHERE bitrix_id LIKE :m AND NOT {HAS_MP} ORDER BY id"),
                             {"m": MARK + "%"}).scalars().all()
            bare = [db.get(SalesDeal, i) for i in ids]
            done = []
            for d in bare:
                src = _template(db, d.service_id)
                if src is not None and _copy_mp(db, src.id, d):
                    done.append(f"{d.code}←{src.code}")
            if apply:
                db.commit()
                print(f"медиаплан скопирован: {len(done)} — {', '.join(done)}")
            else:
                db.rollback()
                print(f"медиаплан будет скопирован: {len(done)} — {', '.join(done)}; запись — с --apply")
            return
        today = date.today()
        cells = _missing(db)
        print(f"пустых сочетаний «стадия × услуга»: {len(cells)}")
        made = []
        for c in cells:
            src = _template(db, c["service_id"])
            if src is None:
                print(f"  ! нет образца для {c['service']} — пропуск")
                continue
            print(f"  {c['stage']:<20} {c['service']:<16} ← копия {src.code}")
            if apply:
                made.append(_copy(db, src, c, today).code)
        if apply:
            db.commit()
            print(f"создано: {len(made)} — {', '.join(made)}")
        else:
            db.rollback()
            print("план без записи; запись — с --apply")
    finally:
        db.close()


if __name__ == "__main__":
    main()
