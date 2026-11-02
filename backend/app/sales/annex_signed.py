# -*- coding: utf-8 -*-
"""Подписан ли ДС — одна функция с источниками (владелец 16.10.2026: «как инфраструктура догонит — подключим»).

Источники по надёжности:
  1. ЭДО — статус подписи у оператора (внешнее подтверждение, перепроверяемое). Пока не подключено: `_from_edo` возвращает None.
  2. Отметка подписи на самом ДС — `sign_state = 'подписан'` (`master_deal.doc_sign`, 02.11.2026): руками до Диадока, у бумаги —
     только со сканом.
  3. Нет данных — «не подписан».
До 02.11.2026 вторым источником был любой файл ДС у сделки: подписанный ДС без скана считался неподписанным и на закрытии
пересобирался по факту под тем же номером, а приложенный неподписанный проект — подписанным.
Зачем: первичный ДС, выпущенный на старте, на закрытии либо пересобирается по факту (не ушёл клиенту — важен только номер), либо
остаётся как есть, а закрывающие идут по факту с расхождением (подписан). Подпись перепроверяется непосредственно перед
пересборкой. Расхождение источников показывается тревогой и не разрешается здесь — это спринт ЭДО."""
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

SOURCE_LABEL = {"edo": "ЭДО", "mark": "отметка «подписан»", None: "нет данных"}


def _from_edo(db: Session, annex) -> Optional[dict]:
    """Место под ЭДО: {signed: bool, at} или None, пока источник не подключён."""
    return None


def _signed_at(db: Session, annex) -> Optional[str]:
    at = db.execute(text("SELECT max(at) FROM doc_sign_events WHERE annex_id = :a AND state = 'подписан'"), {"a": annex.id}).scalar()
    return at.isoformat(timespec="seconds") if at else None


def _from_mark(db: Session, annex) -> Optional[dict]:
    if getattr(annex, "sign_state", None) != "подписан":
        return None
    return {"signed": True, "at": _signed_at(db, annex)}


def signed_state(db: Session, annex) -> dict:
    """{signed, source, source_label, at, conflict}: источник — первый, что что-то знает; `conflict` — источники расходятся."""
    edo, mark = _from_edo(db, annex), _from_mark(db, annex)
    first = edo or mark
    conflict = bool(edo and mark and edo.get("signed") != mark.get("signed"))
    src = "edo" if edo else ("mark" if mark else None)
    return {"signed": bool(first and first.get("signed")), "source": src, "source_label": SOURCE_LABEL[src],
            "at": (first or {}).get("at"), "conflict": conflict}
