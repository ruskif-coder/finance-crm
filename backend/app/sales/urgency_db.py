"""Перевод «база → DealFacts»: единственное место, где факты для срочности читаются из БД.

Отдельным модулем, а не внутри сканера или роутера, по одной причине: очередь на
дашборде аккаунта и лента уведомлений обязаны считаться ОДНИМ кодом. Два сборщика
фактов — и они разойдутся на первой же правке, причём молча: цифры в обоих местах
останутся правдоподобными.

Сама функция срочности (app/sales/urgency.py) базы не знает и проверяется таблицей
дат в тестах. Здесь — только выборки пачкой, без N+1.
"""
from datetime import date

from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from app.sales.urgency import DealFacts, evaluate


def stage_since(db: Session, ids) -> dict:
    """(сделка, стадия) → МОСКОВСКИЙ день последнего входа в эту стадию.

    `at` — `timestamptz`, драйвер отдаёт его в UTC. День берётся по Москве, потому что
    сравнивается с московским «сегодня»: вход в 01:30 МСК по Гринвичу ещё вчерашний, и
    просрочка наступала на сутки раньше (аудит 23.09.2026).
    """
    from app.sales.models import SalesDealStageHistory
    from app.timez import msk_date
    return {(did, sid): msk_date(at)
            for did, sid, at in (db.query(SalesDealStageHistory.deal_id,
                                          SalesDealStageHistory.to_stage_id,
                                          sqlfunc.max(SalesDealStageHistory.at))
                                 .filter(SalesDealStageHistory.deal_id.in_(ids))
                                 .group_by(SalesDealStageHistory.deal_id,
                                           SalesDealStageHistory.to_stage_id).all())}


def facts_for_deals(db: Session, deals, today: date = None):
    """Считает срочность для переданных сделок. Возвращает [(deal, verdict)].

    deals передаётся снаружи, а не выбирается здесь: у очереди свой own-scope
    и свои фильтры, у сканера — свой горизонт рассылки. Правила при этом одни."""
    from app.models import Counterparty
    from app.sales.models import (SalesStage, SalesStagePhase, SalesMediaPlan,
                                  SalesDealFile)

    today = today or date.today()
    deals = list(deals)
    if not deals:
        return []
    ids = [d.id for d in deals]

    stages = {s.id: s for s in db.query(SalesStage).all()}
    # Первая стадия цепочки — из того же каталога, что и движение сделки, чтобы
    # «первая» не разъехалась с тем, куда конвейер ставит новые сделки.
    from app.sales.catalog import Catalog
    first_stage = Catalog(db).first()
    first_id = first_stage.id if first_stage else None
    phases = {p.id: p for p in db.query(SalesStagePhase).all()}
    terms = {c.id: c.term_days
             for c in db.query(Counterparty.id, Counterparty.term_days).all()}

    # Медиаплан сделки бывает двух происхождений, и оба считаются наличием плана:
    # наш (sales_media_plans) и приехавший файлом из Битрикса (sales_deal_files.kind='mp').
    # Учитывать только наши было бы неверно: на живых данных наших МП две штуки
    # на полторы тысячи сделок, и «МП не готов» выпало бы почти на всё.
    #
    # Статус плана здесь больше не читается (30.08.2026): своего состояния у плана нет,
    # где он — говорит стадия сделки. Прежний разбор «побеждает последняя версия» вместе
    # со статусом и уехал.
    mp_ours = {did for (did,) in db.query(SalesMediaPlan.deal_id)
               .filter(SalesMediaPlan.deal_id.in_(ids)).distinct().all()}

    docs = {}
    for did, kind in (db.query(SalesDealFile.deal_id, SalesDealFile.kind)
                      .filter(SalesDealFile.deal_id.in_(ids)).all()):
        docs.setdefault(did, set()).add(kind)

    # Вход в текущую стадию — последняя запись истории с этим to_stage_id.
    # Сделки без истории (импортированные до её появления) отдают None: правило 5
    # по ним не считается, и это честнее, чем принять дату создания за вход в стадию.
    since = stage_since(db, ids)

    out = []
    for d in deals:
        st = stages.get(d.our_stage_id)
        ph = phases.get(st.phase_id) if st else None
        kinds = docs.get(d.id, set())
        f = DealFacts(
            stage_key=st.stage_key if st else None,
            money_layer=st.money_layer if st else None,
            is_terminal=bool(st and st.is_terminal),
            is_lost=bool(st and st.is_lost),
            stage_sla_days=st.sla_days if st else None,
            phase_sla_days=ph.sla_days if ph else None,
            stage_since=since.get((d.id, d.our_stage_id)),
            stage_is_first=(d.our_stage_id is not None and d.our_stage_id == first_id),
            period_from=d.period_from, period_to=d.period_to,
            has_mp=(d.id in mp_ours) or ("mp" in kinds),
            has_ds="ds" in kinds,
            has_closing_docs=bool({"upd", "invoice", "act"} & kinds),
            # is_paid не заполняем: на уровне сделки факт оплаты не читается (см. urgency.py).
            term_days=terms.get(d.payer_counterparty_id or d.counterparty_id),
        )
        out.append((d, evaluate(f, today)))
    return out
