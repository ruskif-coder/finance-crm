# -*- coding: utf-8 -*-
"""Проверка окна контрагента — одна форма на все блоки (контракт дизайнера `sampleData.js`, элемент `checks`).

`sev`: `bad` — документ или ЕРИД не соберётся; `warn` — скоро помешает или расходится с другим источником.
`source` — правило, на которое проверка опирается: окно не держит своей копии правил ДС и ОРД (анти-цель спецификации).
`fix` — куда вести «исправить»: `{block, ref, field}` — открыть правку блока и поставить курсор; `{link}` — другой экран.
"""
from typing import Optional

BAD, WARN = "bad", "warn"


def check(id: str, block: str, sev: str, title: str, why: str, source: str, fix: Optional[dict] = None) -> dict:
    assert sev in (BAD, WARN), sev
    return {"id": id, "block": block, "sev": sev, "title": title, "why": why, "source": source,
            "fix": fix or {"block": block}}
