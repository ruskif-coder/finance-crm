# -*- coding: utf-8 -*-
"""ЕРИД площадки приоритезации — выпускает наш ОРД сам, когда площадка согласовала запрос (владелец 04.11.2026: «ерид
выпускается после того как площадка окнет, автоматом»; «повторить все инструкции как у креативов с адаптацией под то, что
у нас текст, а не баннер»).

Повторяет выпуск комплекта креативов (`launch_prep/erid_service`, `launch_prep/erid_auto`) теми же частями, а не копией:
  * договорная цепочка ОРД сделки — `erid_service._ord_chain`, ККТУ — бренд (`payloads._kktu`);
  * регистрация, журнал попыток, потерянный ответ, опрос — `ord/submit.issue_prio_marker` / `refresh_creative_status`;
  * «готов» — `ord/readiness.erid_ready`: «Запустить» пускает площадку только с готовым маркером;
  * повтор и опрос — тот же крон автовыпуска ЕРИД (`erid_auto.run` зовёт `run_part`), с его отчётом и тревогой.
Отличие — материал: форма ОРД `Text`, без файла (`payloads.prio_creative`). Свой ЕРИД у каждой площадки.

Порога согласовавших, как у комплекта, нет: креатив свой у каждой площадки, и её «ок» и есть согласование материала.
"""
import logging

from sqlalchemy.orm import Session

from app.audit import log_action
from app.notify import emit
from app.ord import client as ord_client
from app.ord import readiness
from app.ord import submit as ord_submit
from app.ord.client import OrdError
from app.ord.payloads import OrdPayloadError, prio_creative
from app.prio import models as M
from app.prio.service import PrioError, request_of
from app.sales.deal_label import deal_label
from app.sales.models import SalesBrand, SalesDeal

log = logging.getLogger("finance.ord")

# Статусы площадки, которым нужен маркер: согласована и дальше. Отказ и черновик — нет.
NEEDS_ERID = (M.APPROVED, M.LIVE, M.STOPPED)
# RegistrationError — тоже итог: опрос его не меняет, а бесконечный опрос засорял отчёт крона (ревью 05.11.2026).
FINAL_STATUSES = ("Active", "Deleted", "Hidden", "RegistrationError")


def _brand(db: Session, deal):
    return db.query(SalesBrand).filter(SalesBrand.id == deal.brand_id).first() if deal.brand_id else None


def blockers(db: Session, deal, p: M.PrioPlacement) -> list:
    """Чего не хватает до выпуска — то же, что у комплекта (цепочка, ККТУ), плюс текст и посадочная креатива."""
    from app.launch_prep.erid_service import _ord_chain
    out = []
    final_ord_id, _ = _ord_chain(db, deal)
    if not final_ord_id:
        out.append("не собрана договорная цепочка ОРД")
    brand = _brand(db, deal)
    if not (brand and brand.kktu_code):
        out.append("не заполнен код ККТУ у бренда")
    r = request_of(db, deal)
    if not (r and (r.product_name or "").strip()):
        out.append("нет названия товара в общей части")
    if not (p.product_url or "").strip():
        out.append("нет посадочной")
    return out


def issue(db: Session, deal, p: M.PrioPlacement, actor) -> dict:
    """Выпустить ЕРИД площадки — или опросить, если креатив уже заведён. Отказ — `PrioError` с текстом для человека."""
    from app.launch_prep.erid_service import _ord_chain
    if p.status not in NEEDS_ERID:
        raise PrioError(409, f"ЕРИД выпускается после согласования площадкой, а площадка «{p.status}»")
    final_ord_id, initial_ord_id = _ord_chain(db, deal)
    was_ready = readiness.erid_ready(p)
    try:
        body = prio_creative(p, request_of(db, deal), deal, _brand(db, deal), final_ord_id, initial_ord_id)
        out = ord_submit.issue_prio_marker(db, p, body, actor)
    except (ord_submit.OrdSubmitRefused, OrdPayloadError, OrdError) as e:
        # Причина — на строке площадки (ревью 05.11.2026): иначе она «выпускается…» без конца, а крон шлёт тот же запрос.
        msg = getattr(e, "message", None) or str(e)
        p.ord_error = msg[:1000]
        db.commit()
        raise PrioError(400, msg)
    # ОРД отвечает на регистрацию id и маркером, но без статуса (демо 04.11.2026: `status` в ответе нет) — без статуса
    # маркер не «готов», и «Запустить» ждал бы опроса кроном до получаса. Спросить статус сразу; не ответил — спросит крон.
    if (p.erid or "").strip() and not p.ord_status:
        try:
            out = {**out, **ord_submit.refresh_creative_status(db, p, kind=ord_submit.PRIO_CREATIVE)}
        except Exception as e:  # noqa: BLE001 — маркер уже выдан и записан; статус догонит крон
            log.warning("приоритезация: статус ЕРИД площадки %s сразу не получен: %s", p.id, e)
    _after(db, deal, p, actor, out, was_ready)
    return out


def refresh(db: Session, deal, p: M.PrioPlacement, actor) -> dict:
    """Опросить статус регистрации — как «обновить статус» у комплекта."""
    was_ready = readiness.erid_ready(p)
    try:
        out = ord_submit.refresh_creative_status(db, p, kind=ord_submit.PRIO_CREATIVE)
    except ord_submit.OrdSubmitRefused as e:
        raise PrioError(400, str(e))
    except OrdError as e:
        raise PrioError(400, e.message)
    _after(db, deal, p, actor, out, was_ready)
    return out


def _after(db: Session, deal, p, actor, out: dict, was_ready: bool) -> None:
    """Журнал; маркер стал готов — уведомление аккаунту (`creative_erid_issued`, как у комплекта): можно запускать."""
    who = "" if actor else " — автовыпуск"
    if not readiness.erid_ready(p):
        db.commit()
        what = (readiness.waiting_text(p) if (p.erid or "").strip()
                else f"зарегистрирован, маркер ещё не выдан (статус {out.get('status')})")
        log_action(db, actor, "issue_erid", "sales_deal", deal.id, f"приоритезация, площадка №{p.id}: {what}{who}")
        return
    if was_ready:
        db.commit()
        return
    log_action(db, actor, "issue_erid", "sales_deal", deal.id, f"приоритезация, площадка №{p.id}: ЕРИД {p.erid}{who}")
    emit(db, "creative_erid_issued",
         title=f"ЕРИД выпущен · {deal_label(deal)}",
         body=f"Приоритезация, площадка №{p.id}: {p.erid}. Статус регистрации: {p.ord_status}. Можно запускать.",
         link=f"/sales/deals/{deal.code or deal.id}",
         entity_type="sales_deal", entity_id=deal.id, actor=actor, ctx={"deal": deal})
    db.commit()


def _deal(db: Session, p: M.PrioPlacement):
    r = db.get(M.PrioRequest, p.request_id)
    return db.get(SalesDeal, r.deal_id) if r else None


def issue_after_verdict(db: Session, placement_id: int) -> None:
    """Сразу после «ок» площадки — выпустить её ЕРИД. Не вышло — согласование остаётся, повторит крон автовыпуска:
    площадка своё сделала, и сбой ОРД не должен отменять её ответ."""
    p = db.get(M.PrioPlacement, placement_id)
    if p is None or p.status != M.APPROVED or (p.erid or "").strip():
        return
    deal = _deal(db, p)
    if deal is None:
        return
    if blockers(db, deal, p):
        return                       # причину назовёт строка площадки и отчёт крона
    try:
        issue(db, deal, p, None)
    except Exception as e:  # noqa: BLE001 — ответ площадки уже записан, выпуск повторит крон
        db.rollback()
        log.warning("приоритезация: ЕРИД площадки %s после «ок» не выпущен: %s", placement_id, e)


def _deal_is_closed(db: Session, deal) -> bool:
    from app.launch_prep.erid_auto import _deal_is_closed as closed
    return closed(db, deal)


def run_part(db: Session, dry_run: bool = False) -> dict:
    """Доля крона автовыпуска ЕРИД (`erid_auto.run`): выпуск площадкам без маркера и опрос незавершённых регистраций.
    Записи — в форме, которую крон уже складывает в отчёт, журнал прогона и тревогу (`set_id` = «П<id>»)."""
    env = ord_client.env()
    issued, pending, blocked, failed = [], [], [], []
    todo = (db.query(M.PrioPlacement)
            .filter(M.PrioPlacement.status.in_(NEEDS_ERID), M.PrioPlacement.erid.is_(None),
                    M.PrioPlacement.ord_error.is_(None))      # отказанный ОРД — ждёт правки данных, не повторяется вслепую
            .order_by(M.PrioPlacement.id).all())
    for p in todo:
        deal = _deal(db, p)
        if deal is None or _deal_is_closed(db, deal):
            continue
        tag = {"set_id": f"П{p.id}", "deal": deal.code}
        why = blockers(db, deal, p)
        if why:
            blocked.append({**tag, "why": why})
            continue
        if dry_run:
            issued.append({**tag, "dry_run": True})
            continue
        try:
            out = issue(db, deal, p, None)
        except Exception as e:  # noqa: BLE001 — отчёт прогона, дальше следующая площадка
            db.rollback()
            failed.append({**tag, "error": str(getattr(e, "message", None) or e)})
            continue
        (issued if out.get("erid") else pending).append({**tag, "erid": out.get("erid"), "status": out.get("status")})

    polled = (db.query(M.PrioPlacement)
              .filter(M.PrioPlacement.erid.isnot(None), M.PrioPlacement.ord_env == env,
                      (M.PrioPlacement.ord_status.is_(None)) | (~M.PrioPlacement.ord_status.in_(FINAL_STATUSES)))
              .order_by(M.PrioPlacement.id).all())
    changed, refresh_failed = [], []
    for p in polled:
        if dry_run:
            continue
        before = p.ord_status
        try:
            out = refresh(db, _deal(db, p), p, None)
        except Exception as e:  # noqa: BLE001
            db.rollback()
            refresh_failed.append({"set_id": f"П{p.id}", "error": str(getattr(e, "message", None) or e)})
            continue
        if out.get("status") != before:
            changed.append({"set_id": f"П{p.id}", "from": before, "to": out.get("status")})
    return {"issued": issued, "pending": pending, "blocked": blocked, "failed": failed,
            "checked": len(polled), "changed": changed, "refresh_failed": refresh_failed}
