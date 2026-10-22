# -*- coding: utf-8 -*-
"""Подписан ли ДС — одна функция с источниками (владелец 16.10.2026: «как инфраструктура догонит — подключим»).

Источники по надёжности:
  1. ЭДО — статус подписи у оператора (внешнее подтверждение, перепроверяемое). Пока не подключено: `_from_edo` возвращает None.
  2. Подписанный файл ДС, приложенный к сделке (`sales_deal_files.kind = 'ds'`) — ставится руками.
  3. Нет данных — «не подписан».

Зачем: первичный ДС, выпущенный на старте, на закрытии либо пересобирается по факту (не подписан — важен только номер), либо
остаётся как есть, а закрывающие идут по факту с расхождением (подписан). Подпись перепроверяется непосредственно перед
пересборкой — подписанный клиентом документ не переписываем. Расхождение источников (файл есть, ЭДО «не подписан» и наоборот)
показывается тревогой и не разрешается здесь — это спринт ЭДО."""
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

SOURCE_LABEL = {"edo": "ЭДО", "file": "файл подписанного ДС", None: "нет данных"}


def _from_edo(db: Session, annex) -> Optional[dict]:
    """Место под ЭДО: {signed: bool, at} или None, пока источник не подключён."""
    return None


def _from_file(db: Session, annex) -> Optional[dict]:
    """Подписанный файл ДС у любой сделки этого ДС. Файл лежит на сделке, а не на ДС: так его прикладывают сейчас."""
    row = db.execute(text("""
        SELECT f.filename, f.synced_at FROM sales_deal_files f
          JOIN sales_deal_annex_allocation al ON al.deal_id = f.deal_id
         WHERE al.annex_id = :a AND f.kind = 'ds' ORDER BY f.synced_at DESC LIMIT 1"""), {"a": annex.id}).mappings().first()
    return {"signed": True, "at": row["synced_at"], "file": row["filename"]} if row else None


def signed_state(db: Session, annex) -> dict:
    """{signed, source, source_label, at, conflict}: источник — первый, что что-то знает; `conflict` — источники расходятся."""
    edo, file = _from_edo(db, annex), _from_file(db, annex)
    first = edo or file
    conflict = bool(edo and file and edo.get("signed") != file.get("signed"))
    src = "edo" if edo else ("file" if file else None)
    return {"signed": bool(first and first.get("signed")), "source": src, "source_label": SOURCE_LABEL[src],
            "at": (first or {}).get("at"), "conflict": conflict}
