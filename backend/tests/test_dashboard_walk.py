# -*- coding: utf-8 -*-
"""Прогон «Моих сделок» по каждой услуге до мастер-сделки (владелец 14.11.2026: «цепочку по каждой услуге до мастер-сделки —
что по мере сборки всё ровно двигается»).

Синтетическая сделка каждой активной услуги шагает по стадиям; на каждой — то, что видит аккаунт: контур и колонка (по слоту),
шаг расхлопа, «чей ход», кнопка строки, блок сборки. Потом пакет ведёт сделку по статусам ДО, и сделка уходит из контуров
сделок в контур «Документы». Требования переходов сверяет `test_matrix_walk`, настоящий путь «Отправить в ДО» —
`test_closing_path_by_service`; здесь — согласованность экрана. Всё с откатом.

Поломки, которые ловит: колонка и шаг расхлопа разошлись; у контура аккаунта на сборке появились шаги креативов или нет
«Подтвердить запуск»; у полного цикла пропали шаги сборки; ход «ваш» без кнопки; пакет не двигает сделку или сделка в ДО
осталась в «В работе»; ход по пакету после «ждём 1С» снова у аккаунта."""
from datetime import date
from types import SimpleNamespace

from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.final_recon import flow, launch
from app.master_deal import deal_stages as DS
from app.master_deal import service as MS
from app.master_deal import status as ST
from app.master_deal.models import MasterDealItem
from app.sales import account_now, queue_state
from app.sales import stage_move as SM
from app.sales.catalog import Catalog
from app.sales.models import SalesDeal, SalesService

TODAY = date(2026, 11, 14)
CHAIN = ["МП Подготовка", "МП Отправлено", "Бронь", "Готовятся к старту", "В размещении", "Итоговая сверка"]
# стадия → (контур «Моих сделок», шаг расхлопа) — `contours.js` и `account_now.SLOT_STEP`
SEEN = {"МП Подготовка": ("sandbox", 0), "МП Отправлено": ("sandbox", 1), "Бронь": ("work", 0),
        "Готовятся к старту": ("work", 1), "В размещении": ("work", 2), "Итоговая сверка": ("work", 3)}
SANDBOX, WORK = {"mp_prep", "mp_sent"}, {"booking", "prep", "live", "recon", "unmapped"}
FULL_STEPS = ["creatives", "check", "sites", "erid", "rk"]
ACCOUNT_PACK = {ST.DRAFT, ST.AGREE}        # дальше пакет ведут бухгалтер и финансы (владелец 13.11.2026)
# статус пакета → стадия сделки — литералом по матрице (13.11.2026), не из `deal_stages.STAGE`: иначе сравнение с самим собой
PACK_STAGE = [(ST.DRAFT, "Подготовка ДС"), (ST.AGREE, "Согласование ДС"), (ST.WAIT_1C, "Подготовка закрывающих"),
              (ST.ISSUE, "ЭДО"), (ST.WAIT_PAY, "Оплата"), (ST.ARCHIVE, "Архив успешных сделок")]


def _contour(slot):
    return "sandbox" if slot in SANDBOX else "work" if slot in WORK else None


def _walk_service(db, cat, by, svc, tpl, user, problems):
    d = SalesDeal(bitrix_id=f"local-dwalk-{svc.id}", title=f"[прогон] {svc.name}", pipeline="", bitrix_stage="",
                  service_id=svc.id, our_stage_id=by[CHAIN[0]].id, counterparty_id=tpl.counterparty_id,
                  payer_counterparty_id=tpl.payer_counterparty_id, ord_final_contract_id=tpl.ord_final_contract_id,
                  brand_id=tpl.brand_id, advertiser_id=tpl.advertiser_id,
                  period_from=date(2026, 11, 20), period_to=date(2026, 12, 19))
    db.add(d)
    db.flush()
    fl = flow.of_deal(db, d)
    bad = lambda where, msg: problems.append(f"{svc.name} ({fl}) · {where}: {msg}")  # noqa: E731
    for name in CHAIN:
        d.our_stage_id = by[name].id
        db.flush()
        row = queue_state.build(db, [d], {}, TODAY)[d.id]
        now = account_now.now(db, d, TODAY)
        want_c, want_at = SEEN[name]
        if _contour(row["slot"]) != want_c or now["at"] != want_at:
            bad(name, f"контур {_contour(row['slot'])}, шаг {now['at']} — ждали {want_c}, {want_at}")
        t = row["turn"]
        if not t["mine"] and not t["who"]:
            bad(name, "«ждём», а кого — не сказано")
        # Сборку строка ведёт переходом (`GO_ON` на экране) — на остальных стадиях ваш ход обязан иметь кнопку
        if t["mine"] and not row["action"] and row["slot"] != "prep":
            bad(name, f"ваш ход без кнопки (подпись «{row['note']}»)")
        if row["slot"] == "prep":
            keys = [r["key"] for r in now["assembly"]]
            if fl == flow.ACCOUNT and (keys or not now["external_launch"] or launch.available(db, d, cat) != "launch"):
                bad(name, f"контур аккаунта: шаги {keys}, внешний запуск {now['external_launch']}")
            if fl == flow.FULL and [k for k in keys if k in FULL_STEPS] != FULL_STEPS:
                bad(name, f"полный цикл: шаги сборки {keys}")
            if fl == flow.PRIO and launch.available(db, d, cat) != "launch":
                bad(name, "приоритезация: нет кнопки «Запустить»")
    # ДО: «Отправить в ДО» уводит на следующую стадию, дальше сделку ведёт пакет
    m = MS.create(db, d, user)
    db.add(MasterDealItem(master_deal_id=m.id, deal_id=d.id))
    d.our_stage_id = SM.next_stage(db, d, cat).id
    db.flush()
    for stt, want in PACK_STAGE:
        m.status = stt
        db.flush()
        DS.align(db, m, user)
        at = cat.by_id[d.our_stage_id].name
        if at != want:
            bad(f"пакет «{stt}»", f"сделка на «{at}», ждали «{want}»")
        slot = queue_state.build(db, [d], {}, TODAY)[d.id]["slot"]
        if _contour(slot) is not None:
            bad(f"пакет «{stt}»", f"сделка в ДО осталась в контуре {_contour(slot)}")
        td = ST.todo(db, m)
        if stt not in ACCOUNT_PACK and td and td["who"] == "аккаунт":
            bad(f"пакет «{stt}»", f"ход у аккаунта: {td['text']}")


def test_every_service_moves_through_my_deals_to_the_master_deal():
    db = SessionLocal()
    try:
        cat = Catalog(db)
        by = {s.name: s for s in cat.by_id.values()}
        tid = db.execute(text("""SELECT id FROM sales_deals WHERE ord_final_contract_id IS NOT NULL
                                  AND payer_counterparty_id IS NOT NULL AND brand_id IS NOT NULL ORDER BY id DESC LIMIT 1""")).scalar()
        assert tid, "на стенде нет сделки с договором, плательщиком и брендом — не из чего собрать прогон"
        tpl = db.get(SalesDeal, tid)
        user = SimpleNamespace(id=None, name="прогон", email="walk@test", role=SimpleNamespace(key="admin", is_master=True))
        problems = []
        services = db.query(SalesService).filter(SalesService.is_active).order_by(SalesService.sort_order).all()
        for svc in services:
            _walk_service(db, cat, by, svc, tpl, user, problems)
        assert services and not problems, "\n".join(problems)
    finally:
        db.rollback()
        db.close()
