# -*- coding: utf-8 -*-
"""Карточка договора (владелец 28.10.2026): шапка договора и блоки всего, что к нему привязано.

Карточку открывает право «Договоры → просмотр»; каждый блок отдаётся, только если у пользователя есть право просмотра СВОЕГО раздела
(`BLOCKS`): нет права — ключа блока в ответе нет, экран его не рисует. Сделки и мастер-сделки — ещё и в области «свои», как в их реестрах.
Связи с договором (перепись 28.10.2026): ДС, шаблоны ДС, мастер-сделки — по `contract_id`; сделки — через ДС, пакеты закрытия и итоговый
договор ОРД; правила СК и условия работы — по `contract_id`; ОРД — изначальные договоры; площадки — `sales_publisher_contracts`. Деньги
к договору не привязаны (операции знают только контрагента и номер ДС текстом) — блок денег показывает контрагента договора и так и
подписан."""
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.permissions import get_permissions_for_user

LIMIT = 200


def head(db: Session, c) -> dict:
    from app.routers.contracts import _serialize
    out = _serialize(c)
    cp, own = c.counterparty, c.own_company
    out["counterparty"] = {"id": cp.id, "name": cp.name} if cp else None
    out["own_company_name"] = own.name if own else None
    # Эти колонки есть в таблице, но не в модели `Contract` — читаем таблицу напрямую.
    extra = db.execute(text("SELECT edo_status, edo_signed_at, doc_type, own_legal_role, nds FROM contracts WHERE id = :c"),
                       {"c": c.id}).mappings().first()
    out.update(dict(extra or {}))
    return out


def parties(db: Session, c) -> list:
    """Стороны договора: реквизиты юрлица, подписант договора (или по умолчанию), из кого выбирать, чего не хватает для ДС —
    той же проверкой, что у конструктора ДС (`signers.party_of` → `sales.annex.party`)."""
    from datetime import date
    from app.signers import service as SG
    out = []
    for side in SG.SIDES:
        cp = SG.side_counterparty(db, c, side)
        signer, source = SG.for_side(db, c, side)
        p = SG.party_of(db, cp, c, side, on=date.today()) if cp else {"missing": ["юрлицо не указано"]}
        out.append({"side": side, "source": source, "missing": p.get("missing") or [],
                    "counterparty": {"id": cp.id, "name": cp.name, "inn": cp.inn, "kpp": cp.kpp, "ogrn": cp.ogrn,
                                     "address": cp.address} if cp else None,
                    "signer_id": signer.id if signer else None,
                    "options": [{"id": s.id, "director_name": s.director_name, "signer_position": s.signer_position,
                                 "signer_basis": s.signer_basis, "valid_until": s.valid_until, "is_default": bool(s.is_default)}
                                for s in (SG.list_of(db, cp.id) if cp else [])]})
    return out


def _at_lawyer(db: Session, annex_ids) -> set:
    ids = list(annex_ids) or [0]
    return {a for (a,) in db.execute(text(
        "SELECT DISTINCT annex_id FROM legal_requests WHERE annex_id = ANY(:a) AND status IN ('открыта', 'в работе')"), {"a": ids}).all()}


def annexes(db: Session, c, user) -> dict:
    """ДС договора — тем же реестром приложений (с его областью «свои»), плюс нумерация и состояние: черновик / у юриста / подтверждён."""
    from app.routers.annexes import list_annexes
    from app.sales import annex as annex_build
    items = list_annexes(db=db, user=user, contract_id=c.id)["items"]
    lawyer = _at_lawyer(db, [a["id"] for a in items])
    keep = ("id", "no", "number", "date", "period_from", "period_to", "total_amount", "status", "is_draft", "template", "deals")
    out = [{**{k: a.get(k) for k in keep},
            "state": "у юриста" if a["id"] in lawyer else "черновик" if a.get("is_draft") else "подтверждён"} for a in items]
    return {"items": out, "start_no": c.annex_start_no, "next_no": annex_build.next_no(db, c)}


def templates(db: Session, c) -> list:
    """Шаблоны договора и базовый формата; у каждого — сколько ДС договора по нему собрано и когда последний."""
    from app.annex_tpl import service as S
    use = S.usage_by_contract(db, c.id)
    out = []
    for t in S.choices(db, c):
        v, u = S.current(db, t.id), use.get(t.id)
        out.append({"id": t.id, "title": t.title, "scope": t.scope, "is_main": bool(t.is_main), "version": v.version if v else None,
                    "updated_at": v.created_at if v else None, "annexes": u["n"] if u else 0, "last_date": u["last"] if u else None})
    return out


def masters(db: Session, c, user) -> list:
    """Пакеты закрытия по договору — в области «свои», как в реестре мастер-сделок (свои ВСЕ сделки пакета)."""
    from app.master_deal import scope as MSC
    from app.master_deal import status as MST
    from app.master_deal.models import MasterDeal
    own = MSC.own_reps(db, user)
    rows = db.query(MasterDeal).filter(MasterDeal.contract_id == c.id).order_by(MasterDeal.period.desc(), MasterDeal.id.desc()).all()
    return [{"code": m.code, "period": m.period, "status": m.status, "status_label": MST.label(db, m),
             "sent_at": m.sent_at, "docs_closed_at": m.docs_closed_at}
            for m in rows if MSC.all_in_scope(db, m, own)]


_DEALS = text("""
    SELECT d.id, d.code, d.title, coalesce(nullif(btrim(a.short_name), ''), a.name) AS advertiser, d.period_from, d.period_to,
           d.amount, d.sales_rep_id, d.account_manager_id,
           d.id IN (SELECT x.deal_id FROM sales_deal_annex_allocation x JOIN sales_annexes s ON s.id = x.annex_id
                     WHERE s.contract_id = :c) AS by_annex,
           d.id IN (SELECT i.deal_id FROM master_deal_items i JOIN master_deals m ON m.id = i.master_deal_id
                     WHERE m.contract_id = :c) AS by_master,
           d.ord_final_contract_id = :c AS by_ord
      FROM sales_deals d LEFT JOIN sales_advertisers a ON a.id = d.advertiser_id
     WHERE d.id IN (SELECT x.deal_id FROM sales_deal_annex_allocation x JOIN sales_annexes s ON s.id = x.annex_id WHERE s.contract_id = :c)
        OR d.id IN (SELECT i.deal_id FROM master_deal_items i JOIN master_deals m ON m.id = i.master_deal_id WHERE m.contract_id = :c)
        OR d.ord_final_contract_id = :c
     ORDER BY d.period_from DESC NULLS LAST, d.id DESC
     LIMIT :lim
""")


def deals(db: Session, c, user) -> list:
    """Сделки договора: закрытые его ДС, вошедшие в его пакеты закрытия, или с ним как итоговым договором в ОРД. Область «свои»."""
    from app.routers.sales_dashboard import _deal_owned, _own_rep_ids_or_all
    own = _own_rep_ids_or_all(db, user, "sales_registry")
    out = []
    for r in db.execute(_DEALS, {"c": c.id, "lim": LIMIT}).mappings().all():
        if own is not None and not _deal_owned(r["sales_rep_id"], r["account_manager_id"], own):
            continue
        via = [w for w, on in (("ДС", r["by_annex"]), ("закрытие", r["by_master"]), ("ОРД", r["by_ord"])) if on]
        out.append({"id": r["id"], "code": r["code"], "title": r["title"], "advertiser": r["advertiser"],
                    "period_from": r["period_from"], "period_to": r["period_to"], "amount": r["amount"], "via": via})
    return out


def sk(db: Session, c) -> dict:
    """Правила СК и условия работы, заведённые именно на этот договор (самый конкретный признак правила)."""
    rules = db.execute(text("""
        SELECT r.id, r.kind, r.mode, r.percent, r.valid_from, r.valid_to, b.name AS brand, s.name AS service,
               ag.name AS agency, coalesce(nullif(btrim(adv.short_name), ''), adv.name) AS advertiser
          FROM sk_rules r LEFT JOIN sales_brands b ON b.id = r.brand_id LEFT JOIN sales_services s ON s.id = r.service_id
          LEFT JOIN sales_agencies ag ON ag.id = r.agency_id LEFT JOIN sales_advertisers adv ON adv.id = r.advertiser_id
         WHERE r.contract_id = :c ORDER BY r.valid_from DESC NULLS LAST, r.id"""), {"c": c.id}).mappings().all()
    work = db.execute(text("""
        SELECT w.id, w.body, w.valid_from, w.valid_to, w.creatives_bonus, w.reports_bonus
          FROM sk_work_terms w WHERE w.contract_id = :c ORDER BY w.valid_from DESC NULLS LAST, w.id"""), {"c": c.id}).mappings().all()
    return {"rules": [dict(r) for r in rules], "work": [dict(w) for w in work]}


def ord_block(db: Session, c) -> dict:
    initial = db.execute(text("""
        SELECT ic.id, ic.number, ic.date, ic.contractor_name, ic.status
          FROM ord_initial_final_links l JOIN ord_initial_contracts ic ON ic.id = l.initial_contract_id
         WHERE l.contract_id = :c ORDER BY ic.date DESC NULLS LAST, ic.id"""), {"c": c.id}).mappings().all()
    final_deals = db.execute(text("SELECT count(*) FROM sales_deals WHERE ord_final_contract_id = :c"), {"c": c.id}).scalar()
    return {"contract_id": c.ord_contract_id, "kind": c.ord_kind, "status": c.ord_status, "env": c.ord_env, "synced_at": c.ord_synced_at,
            "initial": [dict(r) for r in initial], "final_deals": final_deals}


def publishers(db: Session, c) -> list:
    rows = db.execute(text("""
        SELECT p.id, p.name, pc.role, pc.number_raw, pc.is_archived
          FROM sales_publisher_contracts pc JOIN sales_publishers p ON p.id = pc.publisher_id
         WHERE pc.contract_id = :c ORDER BY pc.is_archived, p.name"""), {"c": c.id}).mappings().all()
    return [dict(r) for r in rows]


def legal(db: Session, c) -> list:
    rows = db.execute(text("""
        SELECT l.id, l.annex_id, l.status, l.text, l.created_at, l.closed_at, s.number AS annex_number
          FROM legal_requests l LEFT JOIN sales_annexes s ON s.id = l.annex_id
         WHERE l.contract_id = :c ORDER BY l.id DESC LIMIT :lim"""), {"c": c.id, "lim": LIMIT}).mappings().all()
    return [dict(r) for r in rows]


def money(db: Session, c) -> dict:
    """Операции КОНТРАГЕНТА договора: к самому договору операции не привязаны (номер ДС в них — текст), поэтому блок так и подписан."""
    if not c.counterparty_id:
        return {"counterparty": False}
    r = db.execute(text("""
        SELECT count(*) AS op_count,
               coalesce(sum(income) FILTER (WHERE status = 'ОПЛАЧЕНО'), 0) AS income_paid,
               coalesce(sum(income) FILTER (WHERE status = 'ПЛАН ПОСТУПЛЕНИЙ'), 0) AS receivable,
               coalesce(sum(expense) FILTER (WHERE status = 'ОПЛАЧЕНО'), 0) AS expense_paid,
               coalesce(sum(expense) FILTER (WHERE status = 'ПЛАН ОПЛАТ'), 0) AS payable,
               max(date) AS last_op_date
          FROM operations WHERE counterparty_id = :cp"""), {"cp": c.counterparty_id}).mappings().first()
    year = date.today().year
    others = db.execute(text("""
        SELECT k.id, k.contract_number, k.contract_date, k.cooperation_format, k.end_date_text, k.ord_kind,
               coalesce((SELECT sum(a.total_amount) FROM sales_annexes a WHERE a.contract_id = k.id AND a.no IS NOT NULL
                          AND extract(year FROM a.date) = :y), 0) AS ds_year
          FROM contracts k WHERE k.counterparty_id = :cp ORDER BY k.contract_date DESC NULLS LAST, k.id DESC"""),
        {"cp": c.counterparty_id, "y": year}).mappings().all()
    return {"counterparty": True, **dict(r), "year": year, "contracts": [{**dict(o), "current": o["id"] == c.id} for o in others]}


def audit(db: Session, c) -> list:
    rows = db.execute(text("""
        SELECT id, user_name, action, details, created_at FROM audit_log
         WHERE entity_type = 'contract' AND entity_id = :c ORDER BY id DESC LIMIT 50"""), {"c": c.id}).mappings().all()
    return [dict(r) for r in rows]


# блок → (раздел права, сборщик). Сборщик получает (db, договор, пользователь).
BLOCKS = {
    "annexes": ("annexes", annexes),
    "templates": ("annex_templates", lambda db, c, u: templates(db, c)),
    "masters": ("master_deals", masters),
    "deals": ("sales_registry", deals),
    "sk": ("sk_terms", lambda db, c, u: sk(db, c)),
    "ord": ("ord", lambda db, c, u: ord_block(db, c)),
    "publishers": ("dir_publishers", lambda db, c, u: publishers(db, c)),
    "legal": ("legal_requests", lambda db, c, u: legal(db, c)),
    "money": ("operations", lambda db, c, u: money(db, c)),
    "audit": ("settings_audit", lambda db, c, u: audit(db, c)),
}


def _sk_keys(db: Session, c) -> tuple:
    """Агентства юрлица договора и рекламодатели его сделок — признаки, по которым к договору подбирается правило СК."""
    ag = [a for (a,) in db.execute(text("SELECT agency_id FROM sales_agency_counterparties WHERE counterparty_id = :cp"),
                                    {"cp": c.counterparty_id or 0}).all()]
    adv = [v for (v,) in db.execute(text(
        "SELECT DISTINCT d.advertiser_id FROM sales_deals d WHERE d.advertiser_id IS NOT NULL AND d.id IN ("
        " SELECT x.deal_id FROM sales_deal_annex_allocation x JOIN sales_annexes s ON s.id = x.annex_id WHERE s.contract_id = :c"
        " UNION SELECT i.deal_id FROM master_deal_items i JOIN master_deals m ON m.id = i.master_deal_id WHERE m.contract_id = :c"
        " UNION SELECT id FROM sales_deals WHERE ord_final_contract_id = :c)"), {"c": c.id}).all()]
    return ag, adv


def sk_of(db: Session, c, on: date):
    from app.agency_terms.service import all_rules
    from app.contract_card.readiness import sk_summary
    ag, adv = _sk_keys(db, c)
    s = sk_summary(all_rules(db), c.id, ag, adv, on)
    if s:                                 # к чему привязано правило — названием (владелец 28.10.2026: «указывай к какому агентству»)
        s["agency"] = db.execute(text("SELECT name FROM sales_agencies WHERE id = :i"), {"i": s["agency_id"]}).scalar() if s["agency_id"] else None
        s["advertiser"] = db.execute(text("SELECT coalesce(nullif(btrim(short_name), ''), name) FROM sales_advertisers WHERE id = :i"),
                                     {"i": s["advertiser_id"]}).scalar() if s["advertiser_id"] else None
    return s


def card(db: Session, c, user) -> dict:
    from app.contract_card.readiness import checks
    perms = get_permissions_for_user(db, user)
    see = lambda s: bool((perms.get(s) or {}).get("view"))  # noqa: E731
    today = date.today()
    out = {"contract": head(db, c), "parties": parties(db, c)}
    sk = sk_of(db, c, today)
    ready = checks(db, c, out["parties"], sk, today)
    if not see("sk_terms"):               # условие СК видно только с правом на агентские условия — в проверке без процента
        ready = [dict(x, text="задано" if x["ok"] else "не задано") if x["key"] == "sk" else x for x in ready]
    out["readiness"] = ready
    if see("sk_terms"):
        out["sk_summary"] = sk
    for key, (section, build) in BLOCKS.items():
        if see(section):
            out[key] = build(db, c, user)
    return out
