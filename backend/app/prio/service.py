# -*- coding: utf-8 -*-
"""Приоритезация — сборка запроса и переходы статусов (владелец 19.10.2026; раскладка — правки аккаунтов по живому процессу).

Собирает аккаунт: общая часть одна на сделку (название, конкуренты, МНН, ключевые слова, период, данные рекламодателя);
по площадке — цель, ЕРИД и **посадочная (даём мы)**. Площадка вписывает только **SKU** и отвечает: согласовать / вернуть
с замечанием / отказать. Запуск — кнопкой «Запустить» (заведение РК в системе приоритезации — `app.prio.launch`).

Статусы площадки: черновик → у площадки → правки → у площадки … → согласовано → идёт ⇄ остановлено; отказ — конечный."""
import calendar
import re
from datetime import date, datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.prio import models as M

SKU_RE = re.compile(r"^\d{4,}$")
URL_RE = re.compile(r"^https?://\S+$", re.I)
PIPELINE = (M.DRAFT, M.AT_SITE, M.REWORK, M.APPROVED, M.LIVE)


class PrioError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def split_list(s: Optional[str]) -> list:
    """Список «через запятую и пробел» → пункты без пустых и повторов, порядок сохраняется."""
    seen, out = set(), []
    for x in (s or "").replace("\n", ",").split(","):
        x = x.strip()
        if x and x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)
    return out


def join_list(s: Optional[str]) -> Optional[str]:
    """Как ждёт API: разделитель — запятая и пробел."""
    items = split_list(s)
    return ", ".join(items) if items else None


# ── значения по умолчанию из сделки (ничего не пишет) ─────────────────────────────────────────────

def _period(db: Session, deal) -> tuple:
    """Период РК: даты РК сделки, иначе финансовый месяц сделки."""
    row = db.execute(text("SELECT date_start, date_end FROM ad_campaign WHERE deal_id = :d ORDER BY id LIMIT 1"),
                     {"d": deal.id}).first()
    if row and row[0] and row[1]:
        return row[0], row[1]
    if deal.period_from:
        end = deal.period_to or date(deal.period_from.year, deal.period_from.month,
                                     calendar.monthrange(deal.period_from.year, deal.period_from.month)[1])
        return deal.period_from, end
    return None, None


def _defaults(db: Session, deal) -> dict:
    brand = db.execute(text("SELECT name FROM sales_brands WHERE id = :b"), {"b": deal.brand_id}).scalar() if deal.brand_id else None
    adv = db.execute(text("""
        SELECT cp.name, cp.inn FROM sales_advertiser_counterparties ac JOIN counterparties cp ON cp.id = ac.counterparty_id
         WHERE ac.advertiser_id = :a ORDER BY ac.id LIMIT 1"""), {"a": deal.advertiser_id}).first() if deal.advertiser_id else None
    start, end = _period(db, deal)
    return {"product_name": brand, "date_start": start, "date_end": end,
            "erid_meta": f"{adv[0]}, ИНН {adv[1]}" if adv and adv[1] else (adv[0] if adv else None)}


def request_of(db: Session, deal) -> Optional[M.PrioRequest]:
    return db.query(M.PrioRequest).filter(M.PrioRequest.deal_id == deal.id).first()


def _ensure_request(db: Session, deal, user) -> M.PrioRequest:
    r = request_of(db, deal)
    if r is None:
        d = _defaults(db, deal)
        r = M.PrioRequest(deal_id=deal.id, product_name=d["product_name"], date_start=d["date_start"],
                          date_end=d["date_end"], erid_meta=d["erid_meta"], updated_by=getattr(user, "id", None))
        db.add(r)
        db.flush()
    return r


# ── раскладка цели по расчётному индексу площадки ─────────────────────────────────────────────────
# Владелец 19.10.2026: «вес учитывай по площадкам в приоритезации — индекс расчётный». Цель площадки = объём сделки ×
# индекс площадки / сумма индексов площадок запроса. Индекс площадки — сумма её `index_auto` по поверхностям
# (`publisher_balance_index`, считает балансировщик). Отказавшие не участвуют; запущенные держат свою цель (РК в системе
# не меняется под ногами), остаток делят незапущенные. Нет индекса ни у кого — поровну.

FIXED = (M.LIVE, M.STOPPED)


def plan_volume(db: Session, deal) -> int:
    """Объём для раскладки — тот же план, что видит итоговая сверка: план РК сделки, иначе показы CPM-строк МП."""
    from app.final_recon import closing as CL
    from app.sales import annex as annex_mod
    from app.sales import mp_row
    plan_rk, _ = CL._facts(db, deal)
    if plan_rk:
        return int(plan_rk)
    rows = annex_mod.plan_rows(db, [deal.id])
    return int(sum((r.get("volume") or 0) for r in rows if r.get("kind") != "extra" and mp_row.is_cpm(r.get("model"))))


def _index(db: Session, publisher_ids: list) -> dict:
    if not publisher_ids:
        return {}
    rows = db.execute(text("""SELECT publisher_id, sum(coalesce(index_auto, 0)) FROM publisher_balance_index
                               WHERE publisher_id = ANY(:p) GROUP BY publisher_id"""), {"p": publisher_ids}).all()
    got = {r[0]: float(r[1] or 0) for r in rows}
    return {p: got.get(p, 0.0) for p in publisher_ids}


def rebalance(db: Session, deal) -> None:
    r = request_of(db, deal)
    if r is None:
        return
    pls = db.query(M.PrioPlacement).filter(M.PrioPlacement.request_id == r.id).all()
    live = [p for p in pls if p.status != M.REJECTED]
    free = [p for p in live if p.status not in FIXED]
    for p in pls:
        if p.status == M.REJECTED:
            p.goal_imp = 0
    if not free:
        db.flush()
        return
    rest = max(plan_volume(db, deal) - sum(int(p.goal_imp or 0) for p in live if p.status in FIXED), 0)
    idx = _index(db, [p.publisher_id for p in free])
    total = sum(idx.values())
    weights = {p.id: (idx[p.publisher_id] / total if total else 1 / len(free)) for p in free}
    given = 0
    for i, p in enumerate(sorted(free, key=lambda x: x.id)):
        g = rest - given if i == len(free) - 1 else int(round(rest * weights[p.id]))   # последней — остаток: сумма ровно
        p.goal_imp, given = max(g, 0), given + max(g, 0)
    db.flush()


# ── вид для карточки сделки ───────────────────────────────────────────────────────────────────────

def missing(p: M.PrioPlacement, site_id: Optional[int]) -> list:
    """Чего не хватает, чтобы отправить площадке."""
    out = []
    if not site_id:
        out.append("site_id")
    if not (p.erid or "").strip():
        out.append("ЕРИД")
    if not (p.product_url or "").strip():
        out.append("посадочной")
    if not p.goal_imp:
        out.append("цели (нулевой индекс)")
    return out


def _user_name(db: Session, uid: Optional[int]) -> Optional[str]:
    return db.execute(text("SELECT coalesce(name, email) FROM users WHERE id = :u"), {"u": uid}).scalar() if uid else None


def view(db: Session, deal) -> dict:
    r = request_of(db, deal)
    d = _defaults(db, deal)
    common = {
        "product_name": (r.product_name if r else d["product_name"]) or "",
        "date_start": (r.date_start if r else d["date_start"]),
        "date_end": (r.date_end if r else d["date_end"]),
        "erid_meta": (r.erid_meta if r else d["erid_meta"]) or "",
        "target_competitors": (r.target_competitors if r else "") or "",
        "target_mnn": (r.target_mnn if r else "") or "",
        "target_meta": (r.target_meta if r else "") or "",
        "saved_by": _user_name(db, r.updated_by) if r else None,
        "saved_at": r.updated_at.isoformat(timespec="seconds") if r and r.updated_at else None,
    }
    rows = []
    idx = {}
    fact = {}
    if r:
        from app.prio.autostop import facts
        fact = facts(db, [x[0] for x in db.execute(text("SELECT camp_id FROM prio_placements WHERE request_id = :r AND camp_id IS NOT NULL"),
                                                    {"r": r.id})])
        idx = _index(db, [x[0] for x in db.execute(text("SELECT publisher_id FROM prio_placements WHERE request_id = :r AND status <> :rej"),
                                                    {"r": r.id, "rej": M.REJECTED})])
        for p, name, site in db.execute(text("""
                SELECT pp.id, sp.name, sp.prio_site_id FROM prio_placements pp JOIN sales_publishers sp ON sp.id = pp.publisher_id
                 WHERE pp.request_id = :r ORDER BY sp.name"""), {"r": r.id}).all():
            pl = db.get(M.PrioPlacement, p)
            rows.append({"id": pl.id, "publisher_id": pl.publisher_id, "name": name, "site_id": site,
                         "goal_imp": pl.goal_imp, "index": idx.get(pl.publisher_id), "erid": pl.erid, "product_url": pl.product_url, "product_id": pl.product_id,
                         "status": pl.status, "camp_id": pl.camp_id, "toggle_on": pl.toggle_on,
                         "fact_imp": fact.get(pl.camp_id) if pl.camp_id else None,
                         "goal_reached_at": pl.goal_reached_at.isoformat(timespec="seconds") if pl.goal_reached_at else None,
                         "missing": missing(pl, site) if pl.status == M.DRAFT else [],
                         "remark": ({"text": pl.comment, "at": pl.comment_at.isoformat(timespec="seconds") if pl.comment_at else None,
                                     "by": _user_name(db, pl.comment_by)} if pl.comment else None),
                         "reminded_at": pl.reminded_at.isoformat(timespec="seconds") if pl.reminded_at else None})
    tot = sum(idx.values())
    for x in rows:
        x["weight_pct"] = (round(x["index"] / tot * 100, 1) if tot else (round(100 / len(idx), 1) if idx else None)) if x["index"] is not None else None
    counts = {s: 0 for s in PIPELINE}
    for x in rows:
        k = M.LIVE if x["status"] == M.STOPPED else x["status"]
        if k in counts:
            counts[k] += 1
    return {"deal_id": deal.id, "deal_code": deal.code, "exists": r is not None, "common": common, "placements": rows,
            "plan_volume": plan_volume(db, deal), "no_index": bool(idx) and not tot,
            "pipeline": [{"status": s, "count": counts[s]} for s in PIPELINE],
            "ready_to_send": sum(1 for x in rows if x["status"] == M.DRAFT and not x["missing"]),
            "ready_to_launch": sum(1 for x in rows if x["status"] == M.APPROVED)}


# ── правки аккаунта ───────────────────────────────────────────────────────────────────────────────

COMMON_FIELDS = ("product_name", "erid_meta", "target_competitors", "target_mnn", "target_meta")


def save_common(db: Session, deal, data: dict, user) -> M.PrioRequest:
    r = _ensure_request(db, deal, user)
    for k in COMMON_FIELDS:
        if k in data:
            v = data[k]
            v = join_list(v) if k.startswith("target_") else ((v or "").strip() or None)
            if k == "product_name" and not v:
                raise PrioError(400, "Название товара не может быть пустым")
            setattr(r, k, v)
    r.updated_by, r.updated_at = getattr(user, "id", None), datetime.utcnow()
    db.flush()
    return r


def placement(db: Session, deal, pid: int) -> M.PrioPlacement:
    r = request_of(db, deal)
    p = db.get(M.PrioPlacement, pid) if r else None
    if p is None or p.request_id != r.id:
        raise PrioError(404, "Площадка запроса не найдена")
    return p


def add_placement(db: Session, deal, publisher_id: int, user) -> M.PrioPlacement:
    """Площадка в запрос; цель раскладывается по расчётному индексу (`rebalance`), руками не задаётся."""
    if not db.execute(text("SELECT 1 FROM sales_publishers WHERE id = :p"), {"p": publisher_id}).first():
        raise PrioError(404, "Площадка не найдена")
    r = _ensure_request(db, deal, user)
    if db.query(M.PrioPlacement).filter_by(request_id=r.id, publisher_id=publisher_id).first():
        raise PrioError(409, "Эта площадка уже в запросе")
    p = M.PrioPlacement(request_id=r.id, publisher_id=publisher_id, status=M.DRAFT)
    db.add(p)
    db.flush()
    rebalance(db, deal)
    return p


def remove_placement(db: Session, deal, pid: int) -> None:
    p = placement(db, deal, pid)
    if p.status != M.DRAFT:
        raise PrioError(409, "Убрать можно только черновик — площадке запрос уже ушёл")
    db.delete(p)
    db.flush()
    rebalance(db, deal)


EDITABLE = (M.DRAFT, M.REWORK, M.AT_SITE, M.APPROVED)


def edit_placement(db: Session, deal, pid: int, data: dict) -> M.PrioPlacement:
    """Посадочная, ЕРИД, цель — аккаунт. После запуска — через «Стоп» (правка уходит в систему приоритезации отдельно)."""
    p = placement(db, deal, pid)
    if p.status not in EDITABLE:
        raise PrioError(409, f"Площадка в статусе «{p.status}» — правки закрыты")
    if "product_url" in data:
        u = (data["product_url"] or "").strip()
        if u and not URL_RE.match(u):
            raise PrioError(400, "Посадочная — ссылка вида https://…")
        p.product_url = u or None
    if "erid" in data:
        p.erid = (data["erid"] or "").strip() or None
    if "goal_imp" in data:
        raise PrioError(400, "Цель площадки не правится руками: она раскладывается по расчётному индексу площадки")
    p.updated_at = datetime.utcnow()
    db.flush()
    return p


def _site(db: Session, p: M.PrioPlacement) -> Optional[int]:
    return db.execute(text("SELECT prio_site_id FROM sales_publishers WHERE id = :p"), {"p": p.publisher_id}).scalar()


def send(db: Session, deal, pid: int, user) -> M.PrioPlacement:
    p = placement(db, deal, pid)
    if p.status != M.DRAFT:
        raise PrioError(409, f"Отправить можно черновик, а площадка «{p.status}»")
    miss = missing(p, _site(db, p))
    if miss:
        raise PrioError(409, "Не хватает: " + ", ".join(miss))
    r = request_of(db, deal)
    if not (r.product_name and r.date_start and r.date_end):
        raise PrioError(409, "Заполните общую часть: название товара и период")
    p.status, p.sent_at, p.updated_at = M.AT_SITE, datetime.utcnow(), datetime.utcnow()
    db.flush()
    return p


def remind(db: Session, deal, pid: int, user) -> M.PrioPlacement:
    p = placement(db, deal, pid)
    if p.status != M.AT_SITE:
        raise PrioError(409, "Напомнить можно, пока запрос у площадки")
    p.reminded_at = datetime.utcnow()
    db.flush()
    return p


def reply(db: Session, deal, pid: int, text_: str, user) -> M.PrioPlacement:
    """Ответ аккаунта на замечание площадки → снова у площадки."""
    p = placement(db, deal, pid)
    if p.status != M.REWORK:
        raise PrioError(409, "Ответить можно на замечание площадки (статус «правки»)")
    if not (text_ or "").strip():
        raise PrioError(400, "Напишите ответ площадке")
    p.comment, p.comment_by, p.comment_at = text_.strip(), getattr(user, "id", None), datetime.utcnow()
    p.status, p.updated_at = M.AT_SITE, datetime.utcnow()
    db.flush()
    return p


# ── ответы площадки (через шлюз кабинета) ─────────────────────────────────────────────────────────

def set_sku(db: Session, p: M.PrioPlacement, sku: str) -> M.PrioPlacement:
    sku = (sku or "").strip()
    if not SKU_RE.match(sku):
        raise PrioError(400, "SKU — только цифры, не короче 4 знаков")
    if p.status not in (M.AT_SITE, M.APPROVED):
        raise PrioError(409, "SKU вписывается, пока запрос у вас")
    p.product_id, p.updated_at = sku, datetime.utcnow()
    db.flush()
    return p


def verdict(db: Session, p: M.PrioPlacement, verdict_: str, reason: Optional[str], by_user_id: Optional[int] = None) -> M.PrioPlacement:
    """Площадка: «ок» — согласовать (нужен SKU), «вернуть» — замечание аккаунту, «отказ» — причина, РК в архив."""
    if p.status != M.AT_SITE:
        raise PrioError(409, "Ответить можно на запрос, который у вас")
    reason = (reason or "").strip()
    now = datetime.utcnow()
    if verdict_ == "ок":
        if not SKU_RE.match(p.product_id or ""):
            raise PrioError(409, "Сначала укажите SKU товара")
        p.status, p.approved_at = M.APPROVED, now
    elif verdict_ in ("вернуть", "отказ"):
        if not reason:
            raise PrioError(400, "Напишите замечание" if verdict_ == "вернуть" else "Укажите причину отказа")
        p.comment, p.comment_by, p.comment_at = reason, by_user_id, now
        if verdict_ == "вернуть":
            p.status = M.REWORK
        else:
            p.status, p.rejected_at = M.REJECTED, now
            deal = db.execute(text("SELECT d.* FROM sales_deals d JOIN prio_requests r ON r.deal_id = d.id WHERE r.id = :r"),
                              {"r": p.request_id}).first()
            if deal is not None:
                from app.sales.models import SalesDeal
                db.flush()
                rebalance(db, db.get(SalesDeal, deal.id))        # доля отказавшей переходит остальным
    else:
        raise PrioError(400, "Ответ: ок / вернуть / отказ")
    p.updated_at = now
    db.flush()
    return p
