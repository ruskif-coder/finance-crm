# -*- coding: utf-8 -*-
"""Сделки, у которых конец размещения РАНЬШЕ старта.

## Что это

Размещения, кончающегося до своего начала, не бывает — это всегда след переноса
кампании, при котором доехала половина: старт новый, конец прошлогодний. Замер
15.09.2026 на стенде: 32 сделки из 920, разброс от одного дня до года с лишним
(старт 07.2026 — конец 09.2025; встречается и конец «0025-12-24», набранный руками).

## Чем это мешало

Отбор реестра по периоду считал концом `coalesce(period_to, period_from)` как есть, и
такая сделка выпадала из окна, в котором стоит её же старт: в столбце «Период» июль,
а в июльском отборе сделки нет. Сам отбор починен 15.09.2026 (`greatest` в
`_base_query`), и с испорченными данными он теперь справляется — но данные от этого
не перестали быть испорченными: конец размещения участвует ещё и в сроке оплаты,
и в правиле «период закрыт, документов нет», и в разбивке суммы по месяцам
(`periods.split_amount_by_months` на таком диапазоне просто падает).

## Две двери, откуда это натекало, закрыты той же правкой

* `deal_sync` тянул из Битрикса ТОЛЬКО старт — конец не обновлялся ни разу с момента
  импорта. Теперь тянет оба (`F_PERIOD_TO`).
* Правка «Периода» в реестре меняет месяц старта; конец она не трогала вовсе. Теперь
  протухший конец снимается вместе с переносом старта.

## Что делает скрипт

По умолчанию — только показывает. С `--apply` снимает невозможный конец: NULL по
контракту модели читается как «календарный месяц старта». Это утверждение, а не потеря
данных: прошлогодняя дата не описывает ничего. Настоящий конец вернётся сам при
следующей сверке с Битриксом — теперь она его тянет.

Запуск:
    docker exec finance_backend python -m scripts.2026-09-15_stale_period_end
    docker exec finance_backend python -m scripts.2026-09-15_stale_period_end --apply
"""
import sys

from app.database import SessionLocal
from app.sales.models import SalesDeal, SalesDealFieldOverride


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        rows = (db.query(SalesDeal)
                .filter(SalesDeal.period_from.isnot(None),
                        SalesDeal.period_to.isnot(None),
                        SalesDeal.period_to < SalesDeal.period_from)
                .order_by(SalesDeal.period_from).all())
        if not rows:
            print("Сделок с концом раньше старта нет.")
            return

        print(f"Сделок с концом раньше старта: {len(rows)}\n")
        print(f"{'код':<8} {'старт':<12} {'конец':<12} разница")
        for d in rows:
            print(f"{(d.code or d.id)!s:<8} {d.period_from!s:<12} {d.period_to!s:<12} "
                  f"{(d.period_from - d.period_to).days} дн.")

        if not apply:
            print("\nСУХОЙ ПРОГОН — ничего не изменено. Для снятия конца: --apply")
            return

        # Снятый конец помечаем ручной правкой: иначе ближайшая сверка вернёт из Битрикса
        # ту же протухшую дату, и работа отменится молча.
        have = {(o.deal_id, o.field_name): o for o in db.query(SalesDealFieldOverride)
                .filter(SalesDealFieldOverride.deal_id.in_([d.id for d in rows]),
                        SalesDealFieldOverride.field_name == "period_to").all()}
        for d in rows:
            d.period_to = None
            row = have.get((d.id, "period_to"))
            if row is None:
                row = SalesDealFieldOverride(deal_id=d.id, field_name="period_to")
                db.add(row)
            row.value_int = None
            row.value_text = None
            row.pushed_at = None
        db.commit()
        print(f"\nГотово: конец снят у {len(rows)} сделок "
              f"(NULL = календарный месяц старта).")
    finally:
        db.close()


if __name__ == "__main__":
    main("--apply" in sys.argv)
