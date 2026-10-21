# -*- coding: utf-8 -*-
"""Стоп ночного пересчёта долей при поломке сбора статистики DSP (владелец 16.10.2026).

16.10 DSP перестала отдавать статистику по креативам: факт по площадкам за 15.10 не пришёл, и
пересчёт, читающий отсутствие как ноль, раскладывал бы объём по нулям. Поэтому:

  * плановый сбор, увидевший поломку (`stat_daily.is_bad`), ставит стоп;
  * ночной пересчёт (`app.ad.daily_shares`) при стопе не идёт вовсе — ни весов, ни лимитов;
  * снимает стоп только человек кнопкой «Возобновить» на странице «Биддер»: один удачный
    прогон не значит, что дыры в данных закрыты.

Пересчёт по событию (`app.ad.volumes_now` — согласование и запуск площадки) стопом не
останавливается: через него новые площадки получают лимиты на старте.

Хранится в `company_settings` одной строкой JSON: {since, reason}."""
import json
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

KEY = "dsp_stat_hold"


def get(db: Session) -> Optional[dict]:
    v = db.execute(text("SELECT value FROM company_settings WHERE key = :k"), {"k": KEY}).scalar()
    return json.loads(v) if v else None


def engage(db: Session, reason: str) -> dict:
    """Поставить стоп. Уже стоит — первая причина и время сохраняются."""
    cur = get(db)
    if cur:
        return cur
    hold = {"since": datetime.utcnow().isoformat(timespec="seconds"), "reason": (reason or "")[:300]}
    db.execute(text("INSERT INTO company_settings (key, value) VALUES (:k, :v) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"),
               {"k": KEY, "v": json.dumps(hold, ensure_ascii=False)})
    return hold


def clear(db: Session, user) -> Optional[dict]:
    """Снять стоп («Возобновить»). Возвращает снятый стоп — для журнала действий."""
    cur = get(db)
    # Пустое значение = стопа нет: удаляющий SQL в app/ запрещён (`test_startup_ddl`).
    db.execute(text("UPDATE company_settings SET value = '' WHERE key = :k"), {"k": KEY})
    return cur
