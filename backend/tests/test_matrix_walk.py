# -*- coding: utf-8 -*-
"""Прогон всех активных услуг по матрице до «Архива успешных сделок» (владелец 14.10.2026): синтетическая сделка каждой услуги шагает
по цепочке стадий; на каждом переходе требования, которые считает система (plan_move), должны совпасть со строками матрицы; обычный шаг
вперёд не блокируется правилом ручного перевода; у контура аккаунта кнопки «Запустить/Завершить» — на своих стадиях. Всё с откатом."""
from types import SimpleNamespace

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.final_recon import flow, launch
from app.sales import stage_checks as SC, stage_move as SM
from app.sales.catalog import Catalog
from app.sales.models import SalesDeal, SalesService, SalesStageCheck


def test_every_service_walks_to_archive_by_the_matrix():
    db = SessionLocal()
    cat = Catalog(db)
    chain = [s for s in sorted(cat.by_id.values(), key=lambda s: cat.flow.index(s.id) if s.id in cat.flow else 999) if s.id in cat.flow]
    acc_user = SimpleNamespace(role=SimpleNamespace(key="account", is_master=False))
    rows = db.query(SalesStageCheck).all()
    problems, summary = [], []
    for svc in db.query(SalesService).filter(SalesService.is_active).order_by(SalesService.sort_order):
        d = SalesDeal(bitrix_id=f"local-walk-{svc.id}", title=f"[прогон] {svc.name}", pipeline="", bitrix_stage="",
                      service_id=svc.id, our_stage_id=chain[0].id)
        db.add(d)
        db.flush()
        fl = flow.of_deal(db, d)
        steps = []
        for i in range(len(chain) - 1):
            cur, nxt = chain[i], chain[i + 1]
            d.our_stage_id = cur.id
            db.flush()
            real_next = SM.next_stage(db, d, cat)
            if real_next is None or real_next.id != nxt.id:
                problems.append(f"{svc.name}: со стадии «{cur.name}» следующая {real_next.name if real_next else '—'}, ожидалась «{nxt.name}»")
            g = SM.manual_guard(db, d, nxt, acc_user, cat)
            if g:
                problems.append(f"{svc.name}: шаг «{cur.name}» → «{nxt.name}» заблокирован правилом ручного перевода: {g}")
            plan = SM.plan_move(db, d, nxt, cat)
            got = {(ln.key, bool(ln.is_blocking)) for ln in plan.lines if ln.key in SC.REGISTRY}
            exp = {(r.check_key, SC.blocking_for(r, d)) for r in rows if r.stage_id == nxt.id and SC.scope_matches(r.applies_when, d)}
            if got != exp:
                problems.append(f"{svc.name}: «{nxt.name}» — система {sorted(got - exp)} / матрица {sorted(exp - got)}")
            act = launch.available(db, d, cat)
            want = {"Готовятся к старту": "launch", "В размещении": "finish"}.get(cur.name) if fl == flow.ACCOUNT else None
            if act != want:
                problems.append(f"{svc.name}: на «{cur.name}» кнопка {act!r}, ожидалась {want!r}")
            steps.append(f"{nxt.name}: " + (", ".join(f"{k}{'■' if b else '○'}" for k, b in sorted(exp)) or "—"))
        arch = next(s for s in cat.by_id.values() if s.name == "Архив успешных сделок")
        d.our_stage_id = chain[-1].id
        db.flush()
        plan = SM.plan_move(db, d, arch, cat)
        got = {(ln.key, bool(ln.is_blocking)) for ln in plan.lines if ln.key in SC.REGISTRY}
        exp = {(r.check_key, SC.blocking_for(r, d)) for r in rows if r.stage_id == arch.id and SC.scope_matches(r.applies_when, d)}
        if got != exp:
            problems.append(f"{svc.name}: «Архив» — система {sorted(got - exp)} / матрица {sorted(exp - got)}")
        g = SM.manual_guard(db, d, arch, acc_user, cat)
        if g:
            problems.append(f"{svc.name}: «Оплата» → «Архив» заблокирован правилом ручного перевода: {g}")
        steps.append("Архив успешных сделок: " + ", ".join(f"{k}{'■' if b else '○'}" for k, b in sorted(exp)))
        summary.append((svc.name, fl, steps))
    db.rollback()
    db.close()
    assert not problems, "; ".join(problems)
