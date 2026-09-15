# -*- coding: utf-8 -*-
"""Догнать сделки их медиапланами: разовый прогон переноса по всем привязкам.

## Зачем

Перенос «план → сделка» (`media_plans._sync_deal_from_plan`) срабатывает В МОМЕНТ
сохранения плана. Значит всё, что было привязано ДО появления переноса (08.09.2026)
или правилось путями, где его не звали, так и осталось расходиться — молча и навсегда,
пока кто-нибудь не откроет план и не сохранит его заново.

Замер 15.09.2026 на стенде: из 21 живой пары план↔сделка расходились 19. Чаще всего
плательщик (15), сумма (14), реже конец периода (4), название (3), бренд (2).

Жалоба аккаунтов звучала как «медиаплан не всегда обновляет сделку» — и она верна
дважды: были дыры в путях (правка из реестра переноса не звала, нулевая сумма не
переносилась) и было накопленное расхождение, которое дыры оставили после себя. Дыры
закрыты в коде; этот скрипт убирает накопленное.

## ПРОТИВОРЕЧИТ РЕШЕНИЮ ВЛАДЕЛЬЦА 08.09.2026 — читать до запуска

Тогда было сказано: массового пересчёта задним числом НЕ БУДЕТ, старые сделки правятся
привязкой корректного плана вручную. Причина не в аккуратности, а в том, что к старым
сделкам уже привязаны ДС и выданы ЕРИД, и сумма в ПОДПИСАННОМ приложении задним числом
меняться не должна.

Поэтому скрипт: (1) существует как инструмент, а не как «прогнать и забыть»,
(2) ПРОПУСКАЕТ сделки, у которых есть приложение к договору, и называет их отдельно,
(3) на проде запускается только по прямому решению владельца.

## Что делает

Зовёт тот же самый перенос, что и сохранение плана, — не свою копию правила. Берёт
старшую версию каждой группы, привязанной к сделке.

Правила переноса не меняются: пустое поле плана сделку не чистит, занятый
ответственный не перезаписывается, каждое записанное поле помечается ручной правкой
(«⟳ Обновить из Битрикса» его не вернёт).

По умолчанию — сухой прогон: показывает, что изменилось бы, и откатывает.

ГОТЧА, на которой этот скрипт уже один раз соврал (15.09.2026): перенос в конце зовёт
`log_action`, а тот делает СВОЙ `db.commit()`. Значит «позвать и откатить» не работает —
к моменту отката всё уже записано, и сухой прогон оказывается боевым. Настоящий откат
тут делается снаружи: сессия привязывается к соединению с открытой транзакцией и режимом
`join_transaction_mode="create_savepoint"`, тогда внутренний `commit` закрывает только
savepoint, а внешний откат снимает всё.

Запуск:
    docker exec finance_backend python -m scripts.2026-09-15_resync_deals_from_plans
    docker exec finance_backend python -m scripts.2026-09-15_resync_deals_from_plans --apply
"""
import contextlib
import sys

from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.notify import models as _n   # noqa: F401  — чтобы отношения моделей собрались
from app.ord import models as _o      # noqa: F401
from app.models import User
from app.sales.models import SalesDeal, SalesMediaPlan
from app.routers.media_plans import _sync_deal_from_plan

WATCH = ("title", "advertiser_id", "brand_id", "agency_id", "payer_counterparty_id",
         "period_from", "period_to", "amount", "amount_with_vat", "service_id",
         "sales_rep_id", "account_manager_id", "traffic_manager_id")


@contextlib.contextmanager
def _session(apply: bool):
    """Боевая сессия при `--apply`, иначе — сессия внутри внешней транзакции.

    Внутренние `commit()` (их делает `log_action`) закрывают savepoint, а не транзакцию;
    внешний откат снимает всё разом. Без этого сухого прогона не существует: см. готчу
    в шапке файла.
    """
    if apply:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
        return
    conn = engine.connect()
    outer = conn.begin()
    db = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield db
    finally:
        db.close()
        outer.rollback()
        conn.close()


def main(apply: bool) -> None:
    with _session(apply) as db:
        # Автор правки — админ: перенос пишет строки override и запись в журнал, и у них
        # должен быть человек. Разовый прогон делает владелец своей учёткой.
        author = (db.query(User).join(User.role)
                  .filter(User.is_active == 1).order_by(User.id).first())

        latest, seen = [], set()
        for p in (db.query(SalesMediaPlan).filter(SalesMediaPlan.deal_id.isnot(None))
                  .order_by(SalesMediaPlan.group_id, SalesMediaPlan.version.desc()).all()):
            if p.group_id in seen:
                continue
            seen.add(p.group_id)
            latest.append(p)

        # Сделки с приложением к договору не трогаем вовсе: сумма в подписанном
        # документе задним числом не меняется (решение владельца 08.09.2026).
        from app.sales.models import SalesDealAnnexAllocation as _Alloc
        signed = {d for (d,) in db.query(_Alloc.deal_id).distinct().all() if d}

        touched, orphan, skipped = 0, 0, []
        for p in latest:
            deal = db.query(SalesDeal).filter(SalesDeal.id == p.deal_id).first()
            if deal is None:
                orphan += 1
                continue
            if deal.id in signed:
                skipped.append(deal.code or deal.id)
                continue
            before = {f: getattr(deal, f, None) for f in WATCH}
            _sync_deal_from_plan(db, p, author)
            diff = [(f, before[f], getattr(deal, f, None))
                    for f in WATCH if before[f] != getattr(deal, f, None)]
            if not diff:
                continue
            touched += 1
            print(f"\n{deal.code or deal.id} ← план {p.id} (v{p.version})")
            for f, was, now in diff:
                print(f"    {f}: {was} → {now}")

        print(f"\nПар план↔сделка: {len(latest)}; расходилось: {touched}; "
              f"привязок на удалённые сделки: {orphan}")
        print("Записано." if apply else
              "СУХОЙ ПРОГОН — ничего не записано. Для переноса: --apply")


if __name__ == "__main__":
    main("--apply" in sys.argv)
