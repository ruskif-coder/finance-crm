# -*- coding: utf-8 -*-
"""Правка правил СК и спец. условий, справочники выпадающих списков и дерево вкладок «Агентства» / «Рекламодатели».
Подбор правила — `agency_terms.rules`; расчёт и закрытый месяц — `agency_terms.calc`."""
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.agency_terms import rules as R
from app.agency_terms.models import SkAccrual, SkRule, SkSpecialTerm, SkWorkTerm

RULE_FIELDS = R.FEATURES + ("kind", "recipient_id", "mode", "percent", "valid_from", "valid_to", "note")
SCOPES = ("договор", "агентство", "рекламодатель", "бренд")


class TermsError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def rule_dict(r: SkRule) -> dict:
    return {**{k: getattr(r, k) for k in RULE_FIELDS}, "id": r.id,
            "percent": float(r.percent) if r.percent is not None else None}


def all_rules(db: Session) -> List[dict]:
    return [rule_dict(r) for r in db.query(SkRule).order_by(SkRule.id).all()]


# Ввод проверяется до базы (ревью 27.10.2026): иначе переполнение numeric и чужой ключ давали 500 вместо понятного 400
MAX_SUM = 1e12                       # numeric(14,2)
REF_TABLES = {"contract_id": ("contracts", "договор"), "agency_id": ("sales_agencies", "агентство"),
              "advertiser_id": ("sales_advertisers", "рекламодатель"), "brand_id": ("sales_brands", "бренд"),
              "service_id": ("sales_services", "услуга"), "recipient_id": ("counterparties", "получатель")}
SCOPE_REF = {"договор": "contract_id", "агентство": "agency_id", "рекламодатель": "advertiser_id", "бренд": "brand_id"}


def _check_refs(db: Session, data: dict) -> None:
    for k, (table, label) in REF_TABLES.items():
        v = data.get(k)
        if v is None:
            continue
        if not (0 < int(v) < 2 ** 31) or db.execute(text(f"SELECT 1 FROM {table} WHERE id = :i"), {"i": int(v)}).first() is None:
            raise TermsError(400, f"Не найден {label} №{v} — выберите из списка")


def _check_sum(v, label: str) -> None:
    if v is not None and not (0 <= float(v) < MAX_SUM):
        raise TermsError(400, f"{label} — от 0 до {MAX_SUM:,.0f} ₽".replace(",", " "))


def _clean(payload: dict) -> dict:
    out = {k: payload.get(k) for k in RULE_FIELDS}
    for k in ("valid_from", "valid_to"):
        v = out.get(k)
        if isinstance(v, str):
            try:
                out[k] = date.fromisoformat(v) if v else None
            except ValueError:
                raise TermsError(400, "Дата — ГГГГ-ММ-ДД")
    try:
        out["percent"] = float(out["percent"]) if out.get("percent") not in (None, "") else None
    except (TypeError, ValueError):
        raise TermsError(400, "Процент СК — число")
    if out.get("kind") == R.MAIN:
        out["recipient_id"] = None          # у основной получатель — контрагент договора
    out["note"] = (out.get("note") or "").strip() or None
    return out


def save_rule(db: Session, payload: dict, user, rule_id: Optional[int] = None) -> SkRule:
    """Новое или правка: проверка ввода, затем спор с действующими правилами. → правило (flush, без коммита)."""
    data = _clean(payload)
    try:
        R.validate(data)
    except R.RuleError as e:
        raise TermsError(400, str(e))
    _check_refs(db, data)
    row = db.get(SkRule, rule_id) if rule_id else SkRule(created_by=getattr(user, "id", None))
    if rule_id and row is None:
        raise TermsError(404, "Правило не найдено")
    others = [rule_dict(r) for r in db.query(SkRule).filter(SkRule.kind == data["kind"]).all()]
    hit = R.conflict({**data, "id": rule_id}, others)
    if hit:
        raise TermsError(409, f"Есть правило той же точности на те же сделки и даты (№{hit['id']}, {hit['percent']:g} %): "
                              "уточните признаки или закройте старое датой «по»")
    for k, v in data.items():
        setattr(row, k, v)
    if rule_id:
        row.updated_at, row.updated_by = datetime.utcnow(), getattr(user, "id", None)
    db.add(row)
    db.flush()
    db.info.pop("sk_rules", None)          # кэш правил запроса (`final_recon.sk._rules`) — правка видна сразу
    return row


def delete_rule(db: Session, rule_id: int) -> None:
    """Удалить можно правило, которое ещё не попало в закрытый месяц; попавшее — закрыть датой «по» (история расчёта)."""
    row = db.get(SkRule, rule_id)
    if row is None:
        raise TermsError(404, "Правило не найдено")
    if db.query(SkAccrual.id).filter(SkAccrual.rule_id == rule_id).first():
        raise TermsError(409, "Правило уже в закрытом месяце — удалить нельзя, закройте его датой «по»")
    db.delete(row)
    db.flush()
    db.info.pop("sk_rules", None)


# ── спец. условия ───────────────────────────────────────────────────────────────────────────────────

def special_dict(s: SkSpecialTerm) -> dict:
    return {"id": s.id, "scope_kind": s.scope_kind, "scope_id": s.scope_id, "title": s.title,
            "percent": float(s.percent) if s.percent is not None else None,
            "amount": float(s.amount) if s.amount is not None else None,
            "threshold": float(s.threshold) if s.threshold is not None else None,
            "valid_from": s.valid_from, "valid_to": s.valid_to, "note": s.note}


def save_special(db: Session, payload: dict, user, sid: Optional[int] = None) -> SkSpecialTerm:
    if payload.get("scope_kind") not in SCOPES:
        raise TermsError(400, f"Привязка — {', '.join(SCOPES)}")
    if not payload.get("scope_id"):
        raise TermsError(400, "Выберите, к чему относится условие")
    _check_refs(db, {SCOPE_REF[payload["scope_kind"]]: payload["scope_id"]})
    title = (payload.get("title") or "").strip()
    if not title:
        raise TermsError(400, "Опишите условие")
    data = _clean({**payload, "kind": None})
    if data["percent"] is None and payload.get("amount") in (None, ""):
        raise TermsError(400, "Укажите процент или сумму")
    if not data.get("valid_from"):
        raise TermsError(400, "Укажите, с какой даты действует условие")
    if data.get("valid_to") and data["valid_to"] < data["valid_from"]:
        raise TermsError(400, "Дата окончания раньше даты начала")
    fix = data["percent"] is None
    if fix and not data.get("valid_to"):
        raise TermsError(400, "Фикс делится по месяцам срока — укажите дату «по»")
    thr = payload.get("threshold")
    try:
        thr = float(thr) if thr not in (None, "") else None
    except (TypeError, ValueError):
        raise TermsError(400, "Порог — сумма в рублях")
    if thr is not None and (fix or thr <= 0):
        raise TermsError(400, "Порог задаётся только у процента и больше нуля")
    if data["percent"] is not None and not (0 <= data["percent"] <= 100):
        raise TermsError(400, "Процент — от 0 до 100")
    _check_sum(thr, "Порог")
    if payload.get("amount") not in (None, ""):
        try:
            _check_sum(float(payload["amount"]), "Сумма")
        except (TypeError, ValueError):
            raise TermsError(400, "Сумма — число в рублях")
    row = db.get(SkSpecialTerm, sid) if sid else SkSpecialTerm(created_by=getattr(user, "id", None))
    if sid and row is None:
        raise TermsError(404, "Условие не найдено")
    row.scope_kind, row.scope_id, row.title = payload["scope_kind"], int(payload["scope_id"]), title
    row.percent = data["percent"]
    row.amount = float(payload["amount"]) if payload.get("amount") not in (None, "") else None
    row.valid_from, row.valid_to, row.note = data["valid_from"], data["valid_to"], data["note"]
    row.threshold = thr
    if sid:
        row.updated_at, row.updated_by = datetime.utcnow(), getattr(user, "id", None)
    db.add(row)
    db.flush()
    return row


# ── справочники и дерево ────────────────────────────────────────────────────────────────────────────

def options(db: Session) -> dict:
    """Всё для выпадающих списков конструктора и фильтров одним ответом."""
    q = lambda sql: [dict(r) for r in db.execute(text(sql)).mappings().all()]   # noqa: E731
    return {
        "agencies": q("SELECT id, coalesce(short_name, name) AS name FROM sales_agencies WHERE is_active ORDER BY 2"),
        "advertisers": q("SELECT id, coalesce(short_name, name) AS name FROM sales_advertisers WHERE is_active ORDER BY 2"),
        "brands": q("SELECT id, name, advertiser_id FROM sales_brands WHERE is_active ORDER BY name"),
        "services": q("SELECT id, name FROM sales_services WHERE is_active ORDER BY name"),
        "contracts": q("""SELECT c.id, c.contract_number AS number, c.contract_date AS date, c.counterparty_id,
                                 coalesce(cp.name, c.counterparty_name) AS counterparty
                            FROM contracts c LEFT JOIN counterparties cp ON cp.id = c.counterparty_id
                           WHERE c.counterparty_id IS NOT NULL ORDER BY 5, 2"""),
        "counterparties": q("SELECT id, name FROM counterparties WHERE coalesce(is_own_company, false) = false ORDER BY name"),
        "agency_counterparties": q("SELECT agency_id, counterparty_id FROM sales_agency_counterparties"),
        "advertiser_counterparties": q("SELECT advertiser_id, counterparty_id FROM sales_advertiser_counterparties"),
    }


def tree(db: Session, side: str) -> List[dict]:
    """Вкладка «Агентства» (`side=agency`) или «Рекламодатели» (`advertiser`): сторона → юрлица → договоры → правила.
    Юрлица — связанные со стороной в справочнике И те, на чьи договоры у её сделок выбран договор закрытия: связь в
    справочнике бывает не проставлена, а договор уже работает."""
    if side not in ("agency", "advertiser"):
        raise TermsError(400, "Вкладка — agency или advertiser")
    col = "agency_id" if side == "agency" else "advertiser_id"
    link = "sales_agency_counterparties" if side == "agency" else "sales_advertiser_counterparties"
    owners = db.execute(text(f"""SELECT id, coalesce(short_name, name) AS name FROM {'sales_agencies' if side == 'agency'
                                  else 'sales_advertisers'} WHERE is_active ORDER BY 2""")).mappings().all()
    pairs = db.execute(text(f"""
        SELECT {col} AS owner_id, c.id AS contract_id FROM {link} l JOIN contracts c ON c.counterparty_id = l.counterparty_id
        UNION
        SELECT d.{col}, d.ord_final_contract_id FROM sales_deals d
         WHERE d.{col} IS NOT NULL AND d.ord_final_contract_id IS NOT NULL
           {'AND d.agency_id IS NULL' if side == 'advertiser' else ''}""")).all()
    opts = options(db)
    contracts = {r["id"]: dict(r) for r in opts["contracts"]}
    rules = all_rules(db)
    by_owner: dict = {}
    for oid, cid in pairs:
        if cid in contracts:
            by_owner.setdefault(oid, set()).add(cid)
    out = []
    for o in owners:
        own_rules = [r for r in rules if r.get(col) == o["id"] and r["kind"] == R.MAIN]
        cps: dict = {}
        for cid in sorted(by_owner.get(o["id"], ())):
            c = contracts[cid]
            cps.setdefault(c["counterparty_id"], {"id": c["counterparty_id"], "name": c["counterparty"], "contracts": []})
            cps[c["counterparty_id"]]["contracts"].append(
                {**c, "rules": [r for r in own_rules if r["contract_id"] == cid and r["kind"] == R.MAIN]})
        # Партнёрская — во вкладке «Спец. условия» (хендофф 27.10.2026), в дереве основной СК её нет
        if cps or own_rules:
            out.append({"id": o["id"], "name": o["name"], "entities": list(cps.values()),
                        "no_rule": sum(1 for e in cps.values() for c in e["contracts"] if not c["rules"])})
    return out


# ── «Условия работы» (владелец 27.10.2026): договорённости для аккаунта при сборке медиаплана ─────────────────────

WORK_FIELDS = R.FEATURES + ("body", "mail_subject", "commit_net", "comment", "valid_from", "valid_to",
                            "creatives_bonus", "creatives_bonus_note", "reports_bonus", "reports_bonus_note")
BONUSES = ("creatives_bonus", "reports_bonus")      # креативы / отчёты бонусом (владелец 27.10.2026)


def work_dict(w: SkWorkTerm) -> dict:
    return {**{k: getattr(w, k) for k in WORK_FIELDS}, "id": w.id,
            "commit_net": float(w.commit_net) if w.commit_net is not None else None}


def save_work(db: Session, payload: dict, user, wid: Optional[int] = None) -> SkWorkTerm:
    """Новое или правка. Признаки необязательны, хотя бы один (иначе условие показывалось бы в каждом МП); текст обязателен."""
    data = {k: payload.get(k) for k in WORK_FIELDS}
    for k in ("valid_from", "valid_to"):
        if isinstance(data.get(k), str):
            try:
                data[k] = date.fromisoformat(data[k]) if data[k] else None
            except ValueError:
                raise TermsError(400, "Дата — ГГГГ-ММ-ДД")
    if not any(data.get(k) is not None for k in R.FEATURES):
        raise TermsError(400, "Укажите хотя бы один признак: агентство, рекламодатель, бренд, услуга или договор")
    _check_refs(db, data)
    data["body"] = (data.get("body") or "").strip()
    if not data["body"]:
        raise TermsError(400, "Опишите условие")
    if data.get("commit_net") not in (None, ""):
        try:
            data["commit_net"] = float(data["commit_net"])
        except (TypeError, ValueError):
            raise TermsError(400, "Коммит — сумма в рублях")
        _check_sum(data["commit_net"], "Коммит")
    else:
        data["commit_net"] = None
    if not data.get("valid_from"):
        raise TermsError(400, "Укажите, с какой даты действует условие")
    if data.get("valid_to") and data["valid_to"] < data["valid_from"]:
        raise TermsError(400, "Дата окончания раньше даты начала")
    for k in ("mail_subject", "comment"):
        data[k] = (data.get(k) or "").strip() or None
    for k in BONUSES:          # комментарий живёт только при флажке — иначе плашка в МП показала бы бонус, которого нет
        data[k] = bool(data.get(k))
        data[f"{k}_note"] = ((data.get(f"{k}_note") or "").strip() or None) if data[k] else None
    row = db.get(SkWorkTerm, wid) if wid else SkWorkTerm(created_by=getattr(user, "id", None))
    if wid and row is None:
        raise TermsError(404, "Условие не найдено")
    for k, v in data.items():
        setattr(row, k, v)
    if wid:
        row.updated_at, row.updated_by = datetime.utcnow(), getattr(user, "id", None)
    db.add(row)
    db.flush()
    return row


def all_work(db: Session) -> List[dict]:
    """Условия с названиями признаков — плашке МП и вкладке не нужны справочники, чтобы подписать условие."""
    q = lambda sql: dict(db.execute(text(sql)).all())   # noqa: E731
    names = {"agency_id": q("SELECT id, coalesce(short_name, name) FROM sales_agencies"),
             "advertiser_id": q("SELECT id, coalesce(short_name, name) FROM sales_advertisers"),
             "brand_id": q("SELECT id, name FROM sales_brands"), "service_id": q("SELECT id, name FROM sales_services"),
             "contract_id": q("SELECT id, contract_number FROM contracts")}
    out = []
    for w in db.query(SkWorkTerm).order_by(SkWorkTerm.id).all():
        d = work_dict(w)
        d["names"] = {k.replace("_id", ""): names[k].get(d[k]) for k in R.FEATURES if d.get(k) is not None}
        out.append(d)
    return out

