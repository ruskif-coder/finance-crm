# -*- coding: utf-8 -*-
"""Разметка видимости блоков карточки сделки (таблица `sales_stage_blocks`).

Владелец 13.09.2026: «вещи, которые ещё не положены по стадиям, не должны отображаться в
карточке». Замер до разметки: на «МП Подготовка» карточка показывала ОРД, Креативы и
восемь плиток документов — все пустые.

Уточнение владельца 14.09.2026: **документы из этого правила выведены** — блок остаётся
видимым всегда, см. комментарий у `MARKUP`. Прячем то, что появляется по ходу дела, а не
перечень того, что предстоит собрать.

Разметка НЕ привязана к услуге: «когда появляется блок ОРД» — свойство лестницы, а не
продукта. Если у какой-то услуги порядок другой, это решается применимостью самой стадии
(`sales_stage_services`), а не вторым набором блоков.

Три правила живут в коде (`app/sales/stage_scope.py`), а не здесь, и их надо помнить,
читая эту таблицу:
 · появился — больше не исчезает (блок виден НАЧИНАЯ с указанной стадии);
 · непустое не прячем никогда (блок с данными виден раньше своей стадии);
 · нет строки — виден всегда.

    docker exec finance_backend python -m scripts.2026-09-13_seed_stage_blocks --dry-run
    docker exec finance_backend python -m scripts.2026-09-13_seed_stage_blocks --commit
"""
import argparse
import sys

sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import text

from app.database import SessionLocal
from app.sales.stage_scope import BLOCK_KEYS

# блок → стадия, С КОТОРОЙ он становится виден
MARKUP = {
    # «head» и «mp» не размечаем намеренно: шапка нужна всегда, а медиаплан — то, ради
    # чего сделка заводится. Строки для них означали бы «спрятать на первой стадии»,
    # то есть спрятать единственное, что там есть.
    "ord": "Бронь",                        # договоры выбирают здесь
    "traffic-brief": "Готовятся к старту",  # бриф трафику пишут на сборе запуска
    "creatives": "Готовятся к старту",
    "campaign": "Готовятся к старту",      # РК заводится на этой же стадии
    # Доп. параметры РК — тот же сбор запуска (владелец 15.09.2026). Раньше строки не
    # было, то есть блок показывался с первой стадии: на «МП Подготовка» у сделки ещё
    # нет ни площадок, ни баннеров, а карточка уже спрашивала, нужен ли пиксель. Это
    # вопрос сборки, и до неё он не имеет ответа.
    #
    # Правило 2 («непустое не прячем») продолжает действовать: если параметр кто-то
    # включил раньше, блок виден раньше — см. `_has_content` для `campaign-extra`.
    "campaign-extra": "Готовятся к старту",
    # «docs» НЕ размечаем — решение владельца 14.09.2026. Блок документов виден на всех
    # стадиях. Он не «появляется по ходу дела», как ОРД или креативы: договор и медиаплан
    # лежат в нём с самого начала, а место для остальных плиток — это перечень того, что
    # по сделке ещё предстоит собрать. Спрятать его до «Подготовки ДС» значило бы убрать
    # у аккаунта и то, что уже есть, и сам список.
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    write = args.commit and not args.dry_run

    db = SessionLocal()
    try:
        bad_keys = [k for k in MARKUP if k not in BLOCK_KEYS]
        if bad_keys:
            sys.exit(f"блоков нет в списке карточки: {bad_keys}")

        stages = {n: i for i, n in db.execute(text(
            "SELECT id, name FROM sales_stages")).fetchall()}
        missing = [s for s in MARKUP.values() if s not in stages]
        if missing:
            sys.exit(f"стадий нет в каталоге: {missing}")

        added = skipped = 0
        for block, stage_name in MARKUP.items():
            sid = stages[stage_name]
            exists = db.execute(text(
                "SELECT 1 FROM sales_stage_blocks WHERE stage_id = :s AND block_key = :b"),
                {"s": sid, "b": block}).first()
            if exists:
                skipped += 1
                continue
            if write:
                db.execute(text(
                    "INSERT INTO sales_stage_blocks (stage_id, block_key) VALUES (:s, :b)"),
                    {"s": sid, "b": block})
            added += 1

        if write:
            db.commit()
        for block, stage_name in MARKUP.items():
            print(f"  {block:16} виден с «{stage_name}»")
        not_marked = [k for k in BLOCK_KEYS if k not in MARKUP]
        print(f"  без разметки (видны всегда): {', '.join(not_marked)}")
        print(f"\nстрок {'записано' if write else 'к записи'}: {added}, уже было: {skipped}")
        if not write:
            print("прогон без записи — для записи добавьте --commit")
    finally:
        db.close()


if __name__ == "__main__":
    main()
