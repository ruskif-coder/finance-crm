"""Запросы поиска по типам объектов.

Каждый искатель — `fn(db, q, limit, offset, ctx) -> [строка]`, строка ровно
`{id, title, subtitle, href, archived}` (прибор `test_search_dto_pin`). Сумм нет ни в
одном типе (решение владельца 27.09.2026): поиск — маршрутизатор, не финансовый отчёт.

Порядок внутри типа (решение 9): `0` точное совпадение кода / ИНН / номера, `1` начало
слова, `2` подстрока; при равном ранге — неархивные раньше, потом свежие.

Видимость — теми же функциями, что у реестров: сделки через `app.sales.scope`,
медиапланы через `_mp_own_only` / `_plan_owned` реестра медиапланов. Своих условий
здесь не пишем: копия условия видимости расходится с оригиналом молча.
"""
from urllib.parse import quote

from sqlalchemy import and_, case, func, or_

from app.launch_prep.models import LaunchPrepCreativeSet
from app.models import Contract, Counterparty
from app.ord.models import OrdInitialContract
from app.sales.models import (PUBLISHER_ARCHIVE_STATUS, SalesAdvertiser,
                              SalesAdvertiserCounterparty, SalesAgency,
                              SalesAgencyCounterparty, SalesBrand, SalesDeal,
                              SalesMediaPlan, SalesPublisher, SalesStage)
from app.sales.scope import apply_own_scope

ORD_ENV_LABEL = {"prod": "боевой", "demo": "песочница"}


def _esc(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _match(fields, q):
    """Фильтр «подстрока в любом из полей»."""
    pat = f"%{_esc(q)}%"
    return or_(*[f.ilike(pat, escape="\\") for f in fields])


def _rank(fields, exact, q):
    """0 — точное (только для полей-идентификаторов), 1 — начало слова, 2 — подстрока."""
    e = _esc(q)
    ql = q.lower()
    start = [f.ilike(f"{e}%", escape="\\") for f in fields]
    word = [f.ilike(f"% {e}%", escape="\\") for f in fields]
    whens = []
    if exact:
        whens.append((or_(*[func.lower(f) == ql for f in exact]), 0))
    whens.append((or_(*start, *word), 1))
    return case(*whens, else_=2)


def _row(id_, title, subtitle="", href="/", archived=False):
    return {"id": id_, "title": title or "", "subtitle": subtitle or "", "href": href,
            "archived": bool(archived)}


def _d(d):
    return d.strftime("%d.%m.%Y") if d else ""


# ── сделки ──────────────────────────────────────────────────────────────────────

def _deal_archived():
    # Архив — любой терминальный исход, как в фильтре реестра «скрыть архив».
    return or_(SalesStage.is_terminal.is_(True), SalesStage.is_lost.is_(True))


def deals(db, q, limit, offset, ctx):
    adv = func.coalesce(SalesAdvertiser.short_name, SalesAdvertiser.name)
    ag = func.coalesce(SalesAgency.short_name, SalesAgency.name)
    fields = [SalesDeal.code, SalesDeal.title, SalesDeal.bitrix_id, adv, SalesBrand.name, ag]
    exact = [SalesDeal.code, SalesDeal.bitrix_id]
    arch = case((_deal_archived(), 1), else_=0)
    query = (db.query(SalesDeal.id, SalesDeal.code, SalesDeal.title,
                      SalesStage.name.label("stage"), arch.label("arch"))
             .outerjoin(SalesStage, SalesStage.id == SalesDeal.our_stage_id)
             .outerjoin(SalesAdvertiser, SalesAdvertiser.id == SalesDeal.advertiser_id)
             .outerjoin(SalesBrand, SalesBrand.id == SalesDeal.brand_id)
             .outerjoin(SalesAgency, SalesAgency.id == SalesDeal.agency_id)
             .filter(_match(fields, q)))
    query = apply_own_scope(query, ctx["deals"])
    rows = (query.order_by(_rank(fields, exact, q), arch,
                           func.coalesce(SalesDeal.date_modify, SalesDeal.synced_at)
                           .desc().nullslast(), SalesDeal.id.desc())
            .offset(offset).limit(limit).all())
    return [_row(r.id, " · ".join(x for x in (r.code, r.title) if x), r.stage,
                 f"/sales/deals/{r.code or r.id}", r.arch) for r in rows]


# ── контрагенты и договоры ──────────────────────────────────────────────────────

def _counterparty_roles(db, ids):
    """Роли юрлица одним запросом на тип, не по строке."""
    from app.sales.models import SalesPublisherCounterparty
    roles = {i: [] for i in ids}
    if not ids:
        return roles
    for model, col, label in ((SalesAgencyCounterparty, SalesAgencyCounterparty.counterparty_id,
                               "агентство"),
                              (SalesPublisherCounterparty,
                               SalesPublisherCounterparty.counterparty_id, "площадка"),
                              (SalesAdvertiserCounterparty,
                               SalesAdvertiserCounterparty.counterparty_id, "рекламодатель")):
        for (cid,) in db.query(col).filter(col.in_(ids)).distinct().all():
            roles[cid].append(label)
    return roles


def counterparties(db, q, limit, offset, ctx):
    fields = [Counterparty.name, Counterparty.inn]
    exact = [Counterparty.inn, Counterparty.name]
    rows = (db.query(Counterparty.id, Counterparty.name, Counterparty.inn)
            .filter(_match(fields, q))
            .order_by(_rank(fields, exact, q), Counterparty.id.desc())
            .offset(offset).limit(limit).all())
    roles = _counterparty_roles(db, [r.id for r in rows])
    out = []
    for r in rows:
        sub = " · ".join(x for x in ((f"ИНН {r.inn}" if r.inn else ""),
                                     ", ".join(roles.get(r.id, []))) if x)
        out.append(_row(r.id, r.name, sub, f"/directory/counterparties/{r.id}"))
    return out


def contracts(db, q, limit, offset, ctx):
    fields = [Contract.contract_number, Contract.counterparty_name, Contract.inn]
    exact = [Contract.contract_number, Contract.inn]
    rows = (db.query(Contract.id, Contract.contract_number, Contract.contract_date,
                     Contract.counterparty_name)
            .filter(_match(fields, q))
            .order_by(_rank(fields, exact, q), Contract.contract_date.desc().nullslast(),
                      Contract.id.desc())
            .offset(offset).limit(limit).all())
    out = []
    for r in rows:
        title = " от ".join(x for x in ((f"№ {r.contract_number}" if r.contract_number
                                         else "Договор без номера"), _d(r.contract_date)) if x)
        # номер договора — не персональные данные; реестр договоров сам умеет `?q=`
        href = (f"/directory/contracts?q={quote(r.contract_number)}" if r.contract_number
                else "/directory/contracts")
        out.append(_row(r.id, title, r.counterparty_name, href))
    return out


# ── площадки ────────────────────────────────────────────────────────────────────

def publishers(db, q, limit, offset, ctx):
    fields = [SalesPublisher.name, SalesPublisher.domain, SalesPublisher.code]
    exact = [SalesPublisher.code, SalesPublisher.domain]
    arch = case((SalesPublisher.status == PUBLISHER_ARCHIVE_STATUS, 1), else_=0)
    rows = (db.query(SalesPublisher.id, SalesPublisher.name, SalesPublisher.kind,
                     SalesPublisher.domain, arch.label("arch"))
            .filter(_match(fields, q))
            .order_by(_rank(fields, exact, q), arch, SalesPublisher.id.desc())
            .offset(offset).limit(limit).all())
    return [_row(r.id, r.name, " · ".join(x for x in (r.kind, r.domain) if x),
                 f"/publishers/{r.id}", r.arch) for r in rows]


# ── рекламодатели, агентства, бренды ───────────────────────────────────────────

def _deal_counts(db, col, ids):
    """Число сделок — одним сгруппированным запросом на выданные строки, как в реестре."""
    if not ids:
        return {}
    return dict(db.query(col, func.count(SalesDeal.id)).filter(col.in_(ids))
                .group_by(col).all())


def advertisers(db, q, limit, offset, ctx):
    fields = [SalesAdvertiser.short_name, SalesAdvertiser.name, SalesAdvertiser.name_ru,
              SalesAdvertiser.name_en]
    by_brand = (db.query(SalesBrand.advertiser_id)
                .filter(SalesBrand.name.ilike(f"%{_esc(q)}%", escape="\\")))
    rows = (db.query(SalesAdvertiser.id,
                     func.coalesce(SalesAdvertiser.short_name, SalesAdvertiser.name)
                     .label("title"))
            .filter(or_(_match(fields, q), SalesAdvertiser.id.in_(by_brand)))
            .order_by(_rank(fields, fields[:2], q), SalesAdvertiser.id.desc())
            .offset(offset).limit(limit).all())
    n = _deal_counts(db, SalesDeal.advertiser_id, [r.id for r in rows])
    return [_row(r.id, r.title, f"сделок: {n.get(r.id, 0)}", "/directory/advertisers")
            for r in rows]


def agencies(db, q, limit, offset, ctx):
    fields = [SalesAgency.short_name, SalesAgency.name, SalesAgency.name_ru,
              SalesAgency.name_en]
    rows = (db.query(SalesAgency.id,
                     func.coalesce(SalesAgency.short_name, SalesAgency.name).label("title"),
                     SalesAgency.holding)
            .filter(_match(fields, q))
            .order_by(_rank(fields, fields[:2], q), SalesAgency.id.desc())
            .offset(offset).limit(limit).all())
    return [_row(r.id, r.title, r.holding, "/directory/agencies") for r in rows]


def brands(db, q, limit, offset, ctx):
    fields = [SalesBrand.name]
    rows = (db.query(SalesBrand.id, SalesBrand.name,
                     func.coalesce(SalesAdvertiser.short_name, SalesAdvertiser.name)
                     .label("adv"))
            .join(SalesAdvertiser, SalesAdvertiser.id == SalesBrand.advertiser_id)
            .filter(_match(fields, q))
            .order_by(_rank(fields, fields, q), SalesBrand.id.desc())
            .offset(offset).limit(limit).all())
    return [_row(r.id, r.name, r.adv, "/directory/advertisers") for r in rows]


# ── медиапланы ──────────────────────────────────────────────────────────────────

def media_plans(db, q, limit, offset, ctx):
    """Последняя версия каждого плана, как в реестре. Область — функцией реестра
    `_plan_owned`: она работает по объекту, поэтому отбор «своих» идёт после запроса.
    Планов порядка сотни — выборка без LIMIT здесь дешевле второй копии условия в SQL."""
    from app.routers.media_plans import _plan_owned
    latest = (db.query(SalesMediaPlan.group_id,
                       func.max(SalesMediaPlan.version).label("v"))
              .group_by(SalesMediaPlan.group_id).subquery())
    fields = [SalesMediaPlan.title, SalesDeal.code, SalesDeal.title]
    rows = (db.query(SalesMediaPlan, SalesDeal.code.label("deal_code"))
            .join(latest, and_(latest.c.group_id == SalesMediaPlan.group_id,
                               latest.c.v == SalesMediaPlan.version))
            .outerjoin(SalesDeal, SalesDeal.id == SalesMediaPlan.deal_id)
            .filter(_match(fields, q))
            .order_by(_rank(fields, [SalesDeal.code], q),
                      SalesMediaPlan.updated_at.desc().nullslast(), SalesMediaPlan.id.desc())
            .all())
    if ctx["mp_own"]:
        rows = [r for r in rows if _plan_owned(r[0], ctx["user"])]
    out = []
    for p, code in rows[offset:offset + limit]:
        sub = " · ".join(x for x in (code, f"версия {p.version}") if x)
        out.append(_row(p.id, p.title or f"Медиаплан {p.id}", sub, f"/accounts/mp/{p.id}"))
    return out


# ── ОРД ─────────────────────────────────────────────────────────────────────────

def ord_contracts(db, q, limit, offset, ctx):
    c = OrdInitialContract
    fields = [c.number, c.advertiser_name, c.contractor_name, c.advertiser_inn,
              c.contractor_inn]
    exact = [c.number, c.advertiser_inn, c.contractor_inn]
    rows = (db.query(c.id, c.number, c.date, c.advertiser_name, c.contractor_name, c.ord_env)
            .filter(_match(fields, q))
            .order_by(_rank(fields, exact, q), c.date.desc().nullslast(), c.id.desc())
            .offset(offset).limit(limit).all())
    out = []
    for r in rows:
        title = " от ".join(x for x in ((f"№ {r.number}" if r.number else "Без номера"),
                                         _d(r.date)) if x)
        sides = " → ".join(x for x in (r.advertiser_name, r.contractor_name) if x)
        sub = " · ".join(x for x in (sides, ORD_ENV_LABEL.get(r.ord_env, "")) if x)
        out.append(_row(r.id, title, sub, "/accounts/ord"))
    return out


def erids(db, q, limit, offset, ctx):
    """ЕРИД ведёт на сделку — видимость у него сделочная (область `sales_registry`).

    Живые ЕРИД лежат в двух местах: у креатива РК (`ad_campaign_creative.erid`, свой на
    связку «креатив × площадка») и у комплекта креативов сборки
    (`launch_prep_creative_set.erid`). Зеркало ОРД `ord_creatives` не заполняется и не
    читается никем — искать там значило бы молча не находить ничего (ревью 27.09.2026).
    Строк единицы десятков, поэтому два запроса и слияние в памяти.
    """
    from app.ad.models import AdCampaign, AdCampaignCreative
    ql = q.lower()
    found = {}
    sources = (
        (db.query(AdCampaignCreative.id.label("rid"), AdCampaignCreative.erid.label("erid"),
                  AdCampaignCreative.creative_no.label("no"),
                  SalesDeal.id.label("did"), SalesDeal.code)
         .join(AdCampaign, AdCampaign.id == AdCampaignCreative.campaign_id)
         .join(SalesDeal, SalesDeal.id == AdCampaign.deal_id)
         .filter(_match([AdCampaignCreative.erid], q))),
        (db.query((-LaunchPrepCreativeSet.id).label("rid"), LaunchPrepCreativeSet.erid.label("erid"),
                  LaunchPrepCreativeSet.no.label("no"),
                  SalesDeal.id.label("did"), SalesDeal.code)
         .join(SalesDeal, SalesDeal.id == LaunchPrepCreativeSet.deal_id)
         .filter(_match([LaunchPrepCreativeSet.erid], q))),
    )
    for query in sources:
        for r in apply_own_scope(query, ctx["deals"]).order_by(SalesDeal.id.desc()).all():
            found.setdefault(r.erid, r)
    ranked = sorted(found.values(), key=lambda r: (
        0 if r.erid.lower() == ql else 1 if r.erid.lower().startswith(ql) else 2, -r.did))
    out = []
    for r in ranked[offset:offset + limit]:
        sub = " · ".join(x for x in ((f"креатив {r.no}" if r.no else ""), r.code) if x)
        # id строки — запись ЕРИД, не сделка: у сделки их бывает несколько. Комплекты
        # сборки — со знаком минус, чтобы не совпасть с id креатива РК.
        out.append(_row(r.rid, r.erid, sub, f"/sales/deals/{r.code or r.did}"))
    return out
