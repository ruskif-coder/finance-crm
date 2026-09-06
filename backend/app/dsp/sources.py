"""Единая точка: наша поверхность (web/app) → ключ источника (source) в DSP.

ОТКРЫТЫЙ ВОПРОС владельца (02.09.2026): app-источник в каталоге блоков (xlsx →
publisher_block.network) записан как `x-simb`, а в тесте таргетинга владельца использовался
`xoalt_simb`. Какой настоящий — решает владелец; менять надо ЗНАЧЕНИЕМ настройки
`company_settings.dsp_source_key_app`, а не кодом. Web — `x-simb-web`, расхождений нет.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

SETTING_APP_KEY = "dsp_source_key_app"
DEFAULT_SOURCE_KEYS = {"web": "x-simb-web", "app": "x-simb"}


def source_key(db: Session, kind: str) -> str:
    kind = (kind or "web").lower()
    if kind == "app":
        v = db.execute(text("SELECT value FROM company_settings WHERE key = :k"),
                       {"k": SETTING_APP_KEY}).scalar()
        return (v or DEFAULT_SOURCE_KEYS["app"]).strip()
    return DEFAULT_SOURCE_KEYS["web"]
