"""Единая точка: наша поверхность (web/app) → ключ источника (source) в DSP.

Ключи подтверждены стороной DSP 28.09.2026 (образец из документации, переслан владельцем):
`xoalt_simb` — приложения, `x-simb-web` — веб. Каталог боевого кабинета (чтение 28.09.2026)
говорит то же.

`x-simb` — ключ из каталога блоков (xlsx → `publisher_block.network`), которым app-источник
был записан до подтверждения; в DSP такого источника НЕТ, креативы для приложений ушли бы
никуда. Он же лежит значением настройки `dsp_source_key_app` на проде. Читается как
`xoalt_simb` здесь, в одной точке, — а не правкой базы прода: старое значение безвредно,
где бы оно ни осталось.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

SETTING_APP_KEY = "dsp_source_key_app"
DEFAULT_SOURCE_KEYS = {"web": "x-simb-web", "app": "xoalt_simb"}
# Прежние записи ключа → настоящий ключ DSP.
LEGACY_KEYS = {"x-simb": "xoalt_simb"}


def source_key(db: Session, kind: str) -> str:
    kind = (kind or "web").lower()
    if kind == "app":
        v = db.execute(text("SELECT value FROM company_settings WHERE key = :k"),
                       {"k": SETTING_APP_KEY}).scalar()
        key = (v or "").strip() or DEFAULT_SOURCE_KEYS["app"]
        return LEGACY_KEYS.get(key, key)
    return DEFAULT_SOURCE_KEYS["web"]
