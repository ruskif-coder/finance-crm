"""Сумма сделки при наличии нашего медиаплана.

Правило (владелец 31.08.2026): аккаунты правят сделки, выгруженные из Битрикса, и заводят
НАШИ медиапланы. При любом раскладе, если к сделке привязан наш МП с посчитанной суммой,
и реестр, и дашборд, и карточка обязаны показывать сумму ИЗ МП, а не `deal.amount`
(значение Битрикса). До этого суммы «не обновлялись»: МП тянулся в `our_mps` отдельно и на
деньги не влиял.

Одна точка на всех потребителей — деньги в этом проекте уже разъезжались между тремя
реализациями одного правила, второй раз повторять не будем.

Соответствие: `deal.amount`  ↔ `SalesMediaPlan.amount_net`  (без НДС),
              `deal.amount_with_vat` ↔ `SalesMediaPlan.amount_gross` (с НДС).
"""
from typing import Dict, Iterable, Optional, Tuple

from sqlalchemy.orm import Session

from app.sales.models import SalesMediaPlan


def mp_amounts_by_deal(db: Session, deal_ids: Iterable[int]
                       ) -> Dict[int, Tuple[float, float]]:
    """{deal_id: (net, gross)} по ПОСЛЕДНИМ версиям МП, свёрнутым по группам.

    - берётся старшая версия каждого `group_id` (как и `our_mps` на экранах);
    - НЕ посчитанный или ПУСТОЙ план (`amount_net` NULL или 0) не учитывается: пустой МП
      не должен обнулять сделку — до расчёта показывается сумма Битрикса. Настоящий МП
      всегда > 0, так что нулём мы теряем только незаполненные;
    - если у сделки несколько групп МП — суммируются (на практике почти всегда одна).

    В словаре только те сделки, у которых есть хотя бы один посчитанный МП. Остальные
    отсутствуют — потребитель берёт `deal.amount`.
    """
    ids = [i for i in deal_ids if i is not None]
    if not ids:
        return {}
    seen: Dict[int, set] = {}
    acc: Dict[int, list] = {}
    for p in (db.query(SalesMediaPlan)
              .filter(SalesMediaPlan.deal_id.in_(ids))
              .order_by(SalesMediaPlan.group_id, SalesMediaPlan.version.desc()).all()):
        groups = seen.setdefault(p.deal_id, set())
        if p.group_id in groups:
            continue                       # уже взяли старшую версию этой группы
        groups.add(p.group_id)
        if not p.amount_net:               # None или 0 — план не посчитан/пуст
            continue                       # не трогаем сумму: не обнуляем сделку пустым МП
        a = acc.setdefault(p.deal_id, [0.0, 0.0])
        a[0] += float(p.amount_net or 0)
        a[1] += float(p.amount_gross or 0)
    return {d: (v[0], v[1]) for d, v in acc.items()}


def eff_net(deal, mp: Dict[int, Tuple[float, float]]) -> float:
    """Сумма без НДС: из МП, если он есть и посчитан, иначе из сделки."""
    a = mp.get(deal.id)
    return float(a[0]) if a else float(deal.amount or 0)


def eff_gross(deal, mp: Dict[int, Tuple[float, float]]) -> Optional[float]:
    """Сумма с НДС: из МП; иначе `amount_with_vat` сделки как есть (может быть None)."""
    a = mp.get(deal.id)
    return float(a[1]) if a else deal.amount_with_vat
