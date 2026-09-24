"""«Объект» записи журнала действий: что именно изменили (владелец, 24.09.2026).

Запись вида «Жанна Смирнова · Сделка переведена · МП Подготовка → МП Отправлено» не
говорила, о КАКОЙ сделке речь: у записи есть тип и номер объекта, но номер — это id в
базе, человеку он ничего не говорит. Здесь по (тип, id) подбирается подпись и, где есть
экран, ссылка.

Считается ПРИ ПОКАЗЕ, а не при записи: так подписаны и все старые записи. Пачкой — по
одному запросу на тип, а не на строку (страница журнала — до сотни записей).

Объект, которого уже нет, подписывается словами («сделка #12 — удалена»), а не
пропадает: запись о действии над удалённым объектом — ровно то, ради чего журнал ведут.
"""
from typing import Dict, Iterable, Optional, Tuple

from sqlalchemy.orm import Session


def _deal(o):
    from app.sales.deal_label import deal_label
    return deal_label(o), (f"/sales/deals/{o.code}" if o.code else None)


def _name(field="name"):
    return lambda o: ((getattr(o, field, None) or getattr(o, "name", None) or "").strip()
                      or f"#{o.id}", None)


def _kinds():
    """(тип в журнале) → (модель, подпись(объект) → (текст, ссылка), что это по-русски)."""
    from app.cabinet.models import Cabinet
    from app.models import Contract, Counterparty, Operation, Role, User
    from app.sales.models import (SalesAdvertiser, SalesAgency, SalesBrand, SalesDeal,
                                  SalesMediaPlan, SalesPublisher, SalesYearPlan)

    def mp(o):
        return (o.title or f"медиаплан #{o.id}"), f"/accounts/mp/{o.id}"

    def op(o):
        when = o.date.strftime("%d.%m.%Y") if getattr(o, "date", None) else ""
        money = o.income or o.expense or 0
        return (f"операция #{o.id}" + (f" от {when}" if when else "")
                + (f" · {money:,.0f} ₽".replace(",", " ") if money else "")), \
            f"/finance/operations?op={o.id}"

    def cp(o):
        return (o.name or f"#{o.id}"), f"/directory/counterparties/{o.id}"

    def contract(o):
        return (f"договор {o.contract_number or 'б/н'}"
                + (f" · {o.counterparty_name}" if o.counterparty_name else "")), None

    def pub(o):
        return (o.name or f"#{o.id}"), f"/publishers/{o.id}"

    def short(o):
        return ((getattr(o, "short_name", None) or o.name or f"#{o.id}"), None)

    deal = (SalesDeal, _deal, "сделка")
    adv = (SalesAdvertiser, short, "рекламодатель")
    ag = (SalesAgency, short, "агентство")
    return {
        "sales_deal": deal, "deals": deal,
        "media_plan": (SalesMediaPlan, mp, "медиаплан"),
        "operation": (Operation, op, "операция"),
        "counterparty": (Counterparty, cp, "контрагент"),
        "contract": (Contract, contract, "договор"),
        "sales_publisher": (SalesPublisher, pub, "площадка"),
        "sales_advertiser": adv, "advertisers": adv,
        "sales_agency": ag, "agencies": ag,
        "sales_brand": (SalesBrand, _name(), "бренд"),
        "year_plan": (SalesYearPlan, lambda o: (o.title or f"годовой план #{o.id}", None),
                      "годовой план"),
        "user": (User, _name(), "пользователь"),
        "role": (Role, _name("label"), "роль"),
        "cabinet": (Cabinet, _name(), "кабинет"),
    }


def describe(db: Session, keys: Iterable[Tuple[Optional[str], Optional[int]]]
             ) -> Dict[Tuple[str, int], dict]:
    """{(тип, id): {"label", "href"}} для известных типов. Незнакомый тип не подписывается —
    журнал покажет запись, как раньше."""
    kinds = _kinds()
    by_type: Dict[str, set] = {}
    for t, i in keys:
        if t in kinds and i is not None:
            by_type.setdefault(t, set()).add(int(i))
    out: Dict[Tuple[str, int], dict] = {}
    for t, ids in by_type.items():
        model, fmt, what = kinds[t]
        found = {o.id: o for o in db.query(model).filter(model.id.in_(ids)).all()}
        for i in ids:
            o = found.get(i)
            if o is None:
                out[(t, i)] = {"label": f"{what} #{i} — удалена" if what in ("сделка", "операция")
                               else f"{what} #{i} — удалён", "href": None}
                continue
            try:
                label, href = fmt(o)
            except Exception:                  # подпись не должна ронять журнал
                label, href = f"{what} #{i}", None
            out[(t, i)] = {"label": label, "href": href, "kind": what}
    return out
