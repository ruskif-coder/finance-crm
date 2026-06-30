"""
Перенос старого текстового Contract.payment_term в новые структурированные поля
payment_term_days (число дней) и payment_term_condition (С даты УПД / С даты АКТ /
По периоду).

Колонки добавляются заранее через migrate_payment_term.sql (psql, ALTER TABLE ...
ADD COLUMN IF NOT EXISTS) — этот скрипт только переносит данные. Старая колонка
payment_term не трогается и не удаляется (см. CLAUDE.md), просто перестаёт
использоваться в API/UI после переноса.

Парсинг — только однозначные случаи:
  - дни: если в тексте ровно одно число — берём его. Если чисел 0 или больше
    одного (например, "30-60 дней") — дни не трогаем, строка уходит в отчёт
    "неоднозначно/не распознано" на ручной разбор.
  - условие: ищем целые слова-токены "упд", "акт*", "период*" (с учётом
    русских окончаний). Если совпало ровно одно условие — берём его. Текст
    токенизируется по буквам, поэтому "контракт" не матчится как "акт"
    (это не отдельный токен "акт", а другое слово целиком).
Дни и условие парсятся независимо — можно получить только одно из двух
(например, "30 дней" без упоминания условия даёт days=30, condition=None).
Никакого нечёткого сопоставления; всё неоднозначное остаётся как есть.

Запуск:
    docker exec finance_backend python -m app.migrate_payment_term            # dry-run
    docker exec finance_backend python -m app.migrate_payment_term --apply    # применить

migrate_payment_term.bat сам прогоняет ALTER TABLE, dry-run, спрашивает
подтверждение, делает pg_dump и только потом запускает --apply.
"""
import re
import sys

from app.database import SessionLocal
from app.models import Contract

WORD_RE = re.compile(r"[а-яёa-z]+")
NUMBER_RE = re.compile(r"\d+")

CONDITION_RULES = [
    ("С даты УПД", lambda tokens: any(t == "упд" for t in tokens)),
    ("С даты АКТ", lambda tokens: any(t.startswith("акт") for t in tokens)),
    ("По периоду", lambda tokens: any(t.startswith("период") for t in tokens)),
]


def parse_payment_term(raw):
    """Возвращает (days|None, days_ambiguous, condition|None, condition_ambiguous)."""
    text = (raw or "").strip()
    if not text:
        return None, False, None, False

    numbers = NUMBER_RE.findall(text)
    days = None
    days_ambiguous = False
    if len(numbers) == 1:
        days = int(numbers[0])
    elif len(numbers) > 1:
        days_ambiguous = True

    tokens = WORD_RE.findall(text.lower())
    matched = [label for label, check in CONDITION_RULES if check(tokens)]
    condition = None
    condition_ambiguous = False
    if len(matched) == 1:
        condition = matched[0]
    elif len(matched) > 1:
        condition_ambiguous = True

    return days, days_ambiguous, condition, condition_ambiguous


def main():
    apply_mode = "--apply" in sys.argv
    db = SessionLocal()
    try:
        contracts = (
            db.query(Contract)
            .filter(Contract.payment_term.isnot(None))
            .filter(Contract.payment_term_days.is_(None))
            .filter(Contract.payment_term_condition.is_(None))
            .all()
        )

        fully_parsed = []
        partially_parsed = []
        ambiguous = []
        not_parsed = []

        for c in contracts:
            days, days_amb, condition, cond_amb = parse_payment_term(c.payment_term)

            if days_amb or cond_amb:
                ambiguous.append((c.id, c.payment_term, days_amb, cond_amb))
                continue
            if days is None and condition is None:
                not_parsed.append((c.id, c.payment_term))
                continue

            c.payment_term_days = days
            c.payment_term_condition = condition
            if days is not None and condition is not None:
                fully_parsed.append((c.id, c.payment_term, days, condition))
            else:
                partially_parsed.append((c.id, c.payment_term, days, condition))

        print("=" * 78)
        print("Перенос Contract.payment_term -> payment_term_days / payment_term_condition")
        print("=" * 78)
        print(f"Строк к обработке (старое поле есть, новые поля пусты): {len(contracts)}")
        print()
        print(f"Полностью разобрано (дни + условие): {len(fully_parsed)}")
        for cid, old, days, cond in fully_parsed:
            print(f"  #{cid}: \"{old}\"  ->  дни={days}, условие=\"{cond}\"")
        print(f"Частично разобрано (только дни или только условие): {len(partially_parsed)}")
        for cid, old, days, cond in partially_parsed:
            print(f"  #{cid}: \"{old}\"  ->  дни={days if days is not None else '—'}, условие=\"{cond or '—'}\"")
        print(f"Неоднозначно (не трогали — несколько чисел и/или условий в тексте): {len(ambiguous)}")
        for cid, old, days_amb, cond_amb in ambiguous:
            reason = ", ".join(filter(None, [
                "несколько чисел" if days_amb else None,
                "несколько условий" if cond_amb else None,
            ]))
            print(f"  #{cid}: \"{old}\" — {reason}")
        print(f"Не распознано (не трогали — ни числа, ни условия не найдены): {len(not_parsed)}")
        for cid, old in not_parsed:
            print(f"  #{cid}: \"{old}\"")

        print()
        print("=" * 78)
        if apply_mode:
            db.commit()
            print("Изменения ЗАПИСАНЫ в базу.")
        else:
            db.rollback()
            print("DRY RUN — изменения НЕ записаны. Запустите с --apply, чтобы применить.")
        print("Неоднозначные и нераспознанные строки требуют ручного заполнения через UI.")
        print("=" * 78)
    finally:
        db.close()


if __name__ == "__main__":
    main()
