# -*- coding: utf-8 -*-
"""Разметка требований к переходам для услуги «еФарм».

Схема — миграция 2026-09-13_stage_checks.sql, реестр проверок — app/sales/stage_checks.py.
Черновик согласован с владельцем 13.09.2026 построчно.

## Почему всё привязано к услуге

Владелец 13.09.2026: «сейчас задача полностью провести базовую услугу еФарм до закрытия,
потом начать прорабатывать остальные». Поэтому КАЖДАЯ строка несёт
`applies_when = {"service_id": <еФарм>}`.

Без этого разметка мгновенно распространилась бы на все 920 сделок — включая 99
«Альфарм-Таргет» и 64 «Клик-аут», которые сейчас в полёте и требований не проходили.
Включить следующую услугу = добавить строки, а не править код.

ИСКЛЮЧЕНИЕ — три записи на входе в архив (`ARCHIVE_RECORD` ниже). Они БЕЗ условий и
касаются ЛЮБОЙ услуги: владелец 13.09.2026 назвал услугу, медиаплан и период вместе как
минимум записи о сделке. Следствие надо знать заранее: сделка другой услуги не закроется
в архив, пока к ней не привязан план. Замер на день разметки — закрыть смогут 21 из 90
сделок за прошлые периоды.

## Правила «по свежести сделки» НЕТ

Владелец 13.09.2026: «я могу создавать сделки с МП за прошлые периоды и переводить их в
архив успешных, не надо никаких правил по свежести сделки вообще».

Оно и не нужно: при входной адресации сделка, заведённая задним числом и отправленная
сразу в «Архив успешных сделок», встречает требования ТОЛЬКО архива — план, услугу и
период. Стадии, через которые она не проходила, ничего не спрашивают.

## Адресация ВХОДНАЯ

Требование висит на стадии, в которую ВХОДИМ (решение владельца 13.09.2026): у перехода
«вперёд» и у перехода «в срыв» требования разные, и входная адресация выражает это сама.

Две стадии остаются БЕЗ требований, и это не пропуск:
 · «Бронь» — ответ клиента на план нигде не фиксируется, а ручную отметку владелец
   заводить не стал: сам факт движения и есть запись;
 · «Итоговая сверка» — туда сделку заводит кнопка «РК завершена» у трафика, она же и
   двигает; требование на входе дублировало бы кнопку.

## Что запирает, а что предупреждает

Запрет ставим там, где отсутствие данных делает следующий шаг невозможным. Предупреждение
— там, где проверка сегодня не может отличить «нет» от «не знаем»: `ds_signed` (файлов ДС
в системе ноль, их ведут вне её), `fact_collected` (боевого съёма статистики нет вовсе),
и три проверки без интеграций (Диадок, акты ОРД, оплата). Сделать их запретом значит
остановить конвейер на первом же прогоне.

    docker exec finance_backend python -m scripts.2026-09-13_seed_efarm_checks --dry-run
    docker exec finance_backend python -m scripts.2026-09-13_seed_efarm_checks --commit
"""
import argparse
import sys

sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import text

from app.database import SessionLocal
from app.sales.stage_checks import REGISTRY

SERVICE = "еФарм"

# Минимум записи о сделке: услуга, медиаплан и период (владелец 13.09.2026 — «всё растёт
# из медиаплана»). Без этих трёх архивная строка ничего не значит для отчётности, поэтому
# условий применимости они НЕ несут: проверяются у любой сделки любой услуги, входящей в
# архив. Перечислены владельцем вместе, и разделять их на «для еФарма» и «для всех» было
# бы произволом.
#
# Отдельно от `mp_linked` на «МП Отправлено»: там это гейт лестницы еФарма, здесь — запись.
# Строки разные (ключ таблицы — пара стадия+проверка), поэтому и область у них разная.
ARCHIVE_RECORD = ("mp_linked", "service_set", "period_set")

# (стадия, куда ВХОДИМ) → [(имя проверки, запрет?)]
MARKUP = [
    ("МП Отправлено", [
        ("mp_linked", True),
    ]),
    ("Готовятся к старту", [
        ("realization_pipeline", True),
        ("payer_set", True),
        ("final_contract", True),
        ("ord_initial_contract", False),
    ]),
    ("В размещении", [
        ("creatives_accepted", True),
        ("placements_approved", True),
        ("erid_issued", True),
        ("campaign_ready", True),
    ]),
    ("Подготовка ДС", [
        ("fact_collected", False),
    ]),
    ("Согласование ДС", [
        ("annex_generated", True),
        ("signatory_filled", True),
    ]),
    ("Подготовка закрывающих", [
        ("ds_signed", False),
    ]),
    ("ЭДО", [
        ("invoice_issued", True),
        ("upd_issued", True),
        ("report_attached", False),
    ]),
    ("Отчёты в ОРД", [
        ("edo_sent", False),
    ]),
    ("Оплата", [
        ("ord_acts_sent", False),
    ]),
    ("Архив успешных сделок", [
        # МП и здесь: при ВХОДНОЙ адресации прыжок сразу в архив чтит требования только
        # ЦЕЛИ, а не пройденного мимо. Сделка за прошлый период идёт этим прыжком — и
        # без этой строки уехала бы в архив вообще без плана, хотя правило владельца
        # 13.09.2026 звучит «требуют ТОЛЬКО мп», а не «ничего не требуют».
        ("mp_linked", True),
        ("service_set", True),
        ("period_set", True),
        ("payment_received", False),
    ]),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    write = args.commit and not args.dry_run

    db = SessionLocal()
    try:
        # Проверки СНАЧАЛА, до единой записи: половинчатая разметка хуже отсутствующей —
        # часть переходов заперта, часть нет, и понять почему нельзя.
        svc = db.execute(text("SELECT id FROM sales_services WHERE name = :n"),
                         {"n": SERVICE}).first()
        if not svc:
            sys.exit(f"в справочнике услуг нет «{SERVICE}» — разметку вешать не на что")
        service_id = svc[0]

        stages = {n: i for i, n in db.execute(text(
            "SELECT id, name FROM sales_stages")).fetchall()}
        missing_stage = [s for s, _ in MARKUP if s not in stages]
        if missing_stage:
            sys.exit(f"стадий нет в каталоге: {missing_stage}")

        bad_keys = sorted({k for _, rows in MARKUP for k, _ in rows if k not in REGISTRY})
        if bad_keys:
            sys.exit(f"проверок нет в реестре: {bad_keys}")

        added = skipped = 0
        for stage_name, rows in MARKUP:
            stage_id = stages[stage_name]
            for order, (key, blocking) in enumerate(rows):
                exists = db.execute(text(
                    "SELECT 1 FROM sales_stage_checks "
                    " WHERE stage_id = :s AND check_key = :k"),
                    {"s": stage_id, "k": key}).first()
                if exists:
                    skipped += 1
                    continue
                # Три записи архива — услуга, план и период — БЕЗ условий вообще: они
                # минимум записи о сделке, и «услуга определена», привязанная к услуге,
                # у сделки без услуги не сработала бы никогда. `mp_linked` применим к
                # любой сделке еФарма; остальное — только к живым.
                if stage_name == "Архив успешных сделок" and key in ARCHIVE_RECORD:
                    scope = None
                elif key == "mp_linked":
                    scope = f'{{"service_id": {service_id}}}'
                else:
                    scope = f'{{"service_id": {service_id}}}'
                if write:
                    db.execute(text("""
                        INSERT INTO sales_stage_checks
                               (stage_id, check_key, is_blocking, applies_when, sort_order)
                        VALUES (:s, :k, :b, CAST(:w AS jsonb), :o)
                    """), {"s": stage_id, "k": key, "b": blocking,
                           "w": scope, "o": order})
                added += 1

        if write:
            db.commit()

        print(f"услуга «{SERVICE}» = id {service_id}")
        for stage_name, rows in MARKUP:
            marks = " · ".join(f"{k}{'!' if b else ''}" for k, b in rows)
            print(f"  вход в «{stage_name}»: {marks}")
        print(f"\n! = запрет. строк {'записано' if write else 'к записи'}: {added}, "
              f"уже было: {skipped}")
        if not write:
            print("прогон без записи — для записи добавьте --commit")
    finally:
        db.close()


if __name__ == "__main__":
    main()
