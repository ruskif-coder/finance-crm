"""Сроки хранения файлов: одно определение «закрытия» на три уборки.

Точка отсчёта — ВЫХОД со стадии «Отчёты в ОРД» (владелец 27.08.2026). Именно выход, а не
вход: пока сделка стоит на подаче, отчёт не сдан, и стирать доказательства рано. Ушла и
вернулась — берём последний выход.

Лестница сроков читается как одно правило: **чем ближе файл к доказательству, тем дольше
он живёт.** Скриншот подтверждает разовый факт «стояло»; распакованный баннер —
производная копия; исходный архив — то, на что ссылается согласование площадки и на что
выдан ЕРИД.

Приятное следствие: два года мы в любой момент восстановим предпросмотр. Песочница
умирает через два месяца, но она производная — `sandbox.unpack` разворачивает её из
архива одним вызовом, поэтому короткий срок у неё ничего не стоит.

Одна функция на всех потребителей по той же причине, что и чистая функция срочности: два
счёта одного события однажды разойдутся, и мы начнём стирать доказательства раньше
баннеров.
"""
from datetime import date, datetime
from typing import Iterable, Optional

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app import timez

# Имя, а не id: стадии — данные, и на другом стенде id окажется другим. Строка сравнивается
# буквально, как и все русские значения в этом проекте.
ORD_REPORT_STAGE = "Отчёты в ОРД"

SCREENSHOT_DAYS = 30      # файлы пары
SANDBOX_DAYS = 60         # распакованное в песочнице
ARCHIVE_DAYS = 730        # исходные архивы креативов — два года (владелец)


def last_exit(rows: Iterable) -> Optional[datetime]:
    """Чистое ядро: последний выход из стадии по строкам истории.

    `rows` — пары (from_stage_id, at) в любом порядке. Пусто → None, и это НЕ «давно»,
    а «не выходила»: см. `is_expired`.
    """
    moments = [at for _from, at in rows if at is not None]
    return max(moments) if moments else None


def closed_at(db: Session, deal_id: int) -> Optional[datetime]:
    """Когда сделка прошла подачу в ОРД. None — не прошла (и файлы не удаляются)."""
    row = db.execute(sa_text("""
        SELECT h.at
        FROM sales_deal_stage_history h
        JOIN sales_stages s ON s.id = h.from_stage_id
        WHERE h.deal_id = :d AND s.name = :n
        ORDER BY h.at DESC
        LIMIT 1
    """), {"d": deal_id, "n": ORD_REPORT_STAGE}).first()
    return row[0] if row else None


def is_expired(closed: Optional[datetime], days: int, today: date) -> bool:
    """Пора ли стирать. Незакрытая сделка не истекает НИКОГДА.

    Это не дыра, а безопасное поведение по умолчанию: отказ уборки должен выглядеть как
    «файлы копятся», а не как «файлы исчезли». Что накопилось — покажет отчёт сверки
    диска с базой (`python -m scripts.2026-08-30_retention_sweep` без `--apply` — сухой прогон).
    """
    if closed is None:
        return False
    # Момент закрытия лежит в UTC, `today` — московский: день берётся по Москве, иначе
    # закрытое в 00:00–03:00 МСК стиралось на сутки раньше срока (ревью 23.09.2026).
    closed_day = timez.msk_date(closed) if isinstance(closed, datetime) else closed
    return (today - closed_day).days > days
