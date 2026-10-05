"""Настройки «SIMB ID» (владелец 05.10.2026): коэффициенты для отчётов клиенту по РК.

* частота — базовое значение и поправка ±% (уники = показы ÷ частота дня);
* CTR — базовое значение (в %) и поправка ±%.

Одни на все РК. Хранятся строкой JSON в `company_settings` (ключ `simb_id`) — отдельная
таблица под четыре числа не нужна. Ежедневные значения, посчитанные из этих настроек,
храниться будут отдельно и не меняться задним числом (следующий шаг, схема — на согласование).

Только админ: настройка действует на отчёты всех клиентов, в конструктор ролей её не
выносим, чтобы не выдать по неосторожности (как «Статус», «Пользователи»).
"""
import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit import log_action, require_admin
from app.database import get_db
from app.models import User

router = APIRouter()
KEY = "simb_id"
DEFAULTS = {"freq_base": 3.7, "freq_dev_pct": 0.0, "ctr_base": 0.1, "ctr_dev_pct": 0.0}


class SimbIdIn(BaseModel):
    freq_base: float = Field(gt=0, le=100)        # показов на человека
    freq_dev_pct: float = Field(ge=0, le=100)     # поправка ±%
    ctr_base: float = Field(ge=0, le=100)         # CTR, %
    ctr_dev_pct: float = Field(ge=0, le=100)      # поправка ±%


def load(db: Session) -> dict:
    """Текущие настройки; не сохранялись или испорчены — значения по умолчанию."""
    raw = db.execute(text("SELECT value FROM company_settings WHERE key = :k"),
                     {"k": KEY}).scalar()
    try:
        saved = json.loads(raw) if raw else {}
    except ValueError:
        saved = {}
    return {k: saved.get(k, v) for k, v in DEFAULTS.items()}


@router.get("")
def get_settings(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return load(db)


@router.put("")
def put_settings(payload: SimbIdIn, db: Session = Depends(get_db),
                 user: User = Depends(require_admin)):
    value = payload.dict()
    db.execute(text("""
        INSERT INTO company_settings (key, value) VALUES (:k, :v)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"""),
        {"k": KEY, "v": json.dumps(value)})
    db.commit()
    log_action(db, user, "simb_id_settings", "company_settings", None,
               f"частота {value['freq_base']} ±{value['freq_dev_pct']} %, "
               f"CTR {value['ctr_base']} % ±{value['ctr_dev_pct']} %")
    return value
