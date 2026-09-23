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

ПОСЧИТАН ≠ НЕ НОЛЬ (найдено 15.09.2026 по жалобе владельца на сделку MHNZUT). Признаком
«план посчитан» был `amount_net`, отличный от нуля, — и ноль читался как «плана ещё нет».
Но ноль бывает настоящим: услуга со стопроцентной скидкой даёт посчитанный план на нулевую
сумму, и реестр показывал по такой сделке 372 000 из Битрикса. Со стороны это выглядит как
«цена не обновилась», хотя план привязан и посчитан.

Признак теперь — СТРОКИ размещения: план со строками посчитан, чему бы ни равнялся итог;
план без строк (болванка, заведённая и брошенная) сумму сделки не трогает. Ноль от
стопроцентной скидки и пустая болванка — разные состояния, и различать их по итогу нельзя.
"""
from typing import Dict, Iterable, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.sales import mp_row
from app.sales.models import SalesMediaPlan, SalesMediaPlanRow


def mp_amounts_by_deal(db: Session, deal_ids: Iterable[int]
                       ) -> Dict[int, Tuple[float, float]]:
    """{deal_id: (net, gross)} по ПОСЛЕДНИМ версиям МП, свёрнутым по группам.

    - берётся старшая версия каждого `group_id` (как и `our_mps` на экранах);
    - план БЕЗ СТРОК размещения не учитывается: заведённая и брошенная болванка не должна
      обнулять сделку — до расчёта показывается сумма Битрикса;
    - план СО СТРОКАМИ учитывается всегда, включая нулевой итог: ноль по стопроцентной
      скидке — это посчитанная цена, а не отсутствие плана;
    - если у сделки несколько групп МП — суммируются (на практике почти всегда одна).

    В словаре только те сделки, у которых есть хотя бы один посчитанный МП. Остальные
    отсутствуют — потребитель берёт `deal.amount`.
    """
    ids = [i for i in deal_ids if i is not None]
    if not ids:
        return {}
    plans = (db.query(SalesMediaPlan)
             .filter(SalesMediaPlan.deal_id.in_(ids))
             .order_by(SalesMediaPlan.group_id, SalesMediaPlan.version.desc()).all())
    if not plans:
        return {}
    # Строки — одним запросом на всю страницу, а не по плану: реестр зовёт это на каждую
    # сотню сделок, и N+1 здесь стоил бы сотни запросов на открытие экрана.
    has_rows = {pid for pid, _n in
                db.query(SalesMediaPlanRow.plan_id, func.count(SalesMediaPlanRow.id))
                .filter(SalesMediaPlanRow.plan_id.in_([p.id for p in plans]))
                .group_by(SalesMediaPlanRow.plan_id).all()}
    seen: Dict[int, set] = {}
    acc: Dict[int, list] = {}
    for p in plans:
        groups = seen.setdefault(p.deal_id, set())
        if p.group_id in groups:
            continue                       # уже взяли старшую версию этой группы
        groups.add(p.group_id)
        if p.id not in has_rows:           # болванка без размещений — план не заводили
            continue                       # не трогаем сумму: не обнуляем сделку пустым МП
        a = acc.setdefault(p.deal_id, [0.0, 0.0])
        a[0] += float(p.amount_net or 0)
        a[1] += float(p.amount_gross or 0)
    # Копейки складываются в двоичный хвост: 733 313,70 + 0,30 даёт 733 314,0000000001,
    # и сумма сделки в реестре отличалась бы от суммы в медиаплане последним знаком.
    return {d: (mp_row.rub(v[0]), mp_row.rub(v[1])) for d, v in acc.items()}


def eff_net(deal, mp: Dict[int, Tuple[float, float]]) -> float:
    """Сумма без НДС: из МП, если он есть и посчитан, иначе из сделки."""
    a = mp.get(deal.id)
    return float(a[0]) if a else float(deal.amount or 0)


def eff_gross(deal, mp: Dict[int, Tuple[float, float]]) -> Optional[float]:
    """Сумма с НДС: из МП; иначе `amount_with_vat` сделки как есть (может быть None)."""
    a = mp.get(deal.id)
    return float(a[1]) if a else deal.amount_with_vat


def vat_pct_of(deal, mp: Dict[int, Tuple[float, float]]) -> Optional[float]:
    """Ставка НДС, по которой ПОСЧИТАНА сделка, — для показа её сумм (правило 23.09.2026).

    Ставка фиксируется на дату расчёта, поэтому берётся из уже посчитанного, а не из
    текущей карточки юрлица: сделка 2025 года на 20 % не должна показываться по 22 %.
    Порядок: медиаплан сделки (его суммы несут его ставку) → суммы самой сделки →
    ставка закона на период сделки. None — нет ни одной суммы, считать нечего.
    """
    from app import vat as vat_rules
    # Деление посчитанных сумм даёт приближение (копейки, рубли у старых планов) — оно
    # приводится к законной ставке; не приводится (17 %, 0 % при ошибке ввода) — не
    # угадываем, идём дальше по порядку (ревью 23.09.2026).
    a = mp.get(deal.id)
    if a and a[0]:
        got = vat_rules.snap((float(a[1]) / float(a[0]) - 1) * 100)
        if got is not None:
            return got
    if deal.amount and deal.amount_with_vat:
        got = vat_rules.snap((float(deal.amount_with_vat) / float(deal.amount) - 1) * 100)
        if got is not None:
            return got
    if deal.amount is None:
        return None
    d = deal.period_from or (deal.date_create.date() if deal.date_create else None)
    return vat_rules.on(d)


def gross_of(deal, mp: Dict[int, Tuple[float, float]]) -> Optional[float]:
    """Сумма сделки с НДС — одно правило для карточки и реестра (ревью 23.09.2026).

    Порядок: посчитанный медиаплан сделки → сохранённая сумма с НДС → досчёт по ставке
    ЗАКОНА на период сделки (сделка 2025 года — по 20 %, а не по текущей). Реестр суммы с
    НДС не отдавал вовсе, и доска сделок досчитывала её сама по зашитым 22 %.
    """
    from app import vat as vat_rules
    if deal.id in mp:
        return eff_gross(deal, mp)
    if deal.amount_with_vat is not None:
        return deal.amount_with_vat
    if deal.amount is None:
        return None
    d = deal.period_from or (deal.date_create.date() if deal.date_create else None)
    return round(float(deal.amount) * (1 + vat_rules.on(d) / 100.0), 2)
