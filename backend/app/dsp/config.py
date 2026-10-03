# -*- coding: utf-8 -*-
"""Настройки обмена с DSP — одна точка чтения (аудит интеграций 02.10.2026).

Что здесь: ключи настроек админки (скрипты креатива, кабинеты боевого клиента и
нацеливания) и правило «настройка админки главнее, пусто — окружение сервера». До 02.10
это жило в роутере `traffic_catalog`, и модуль DSP импортировал роутер, чтобы узнать,
куда заводить креатив; роутер теперь только показывает и сохраняет эти значения.

Боевой клиент кабинета — `client.configured_partner()` (он читается при каждом создании
клиента); здесь — его ключ и проверка «что реально уйдёт в DSP».
"""
import os

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dsp.client import PARTNER_SETTING

SCRIPT_OUR_CODE = "traffic_creative_script_our_code"     # площадка с нашим кодом
SCRIPT_NO_CODE = "traffic_creative_script_no_code"       # площадка без нашего кода
# Адрес скрипта видимости. В коде адреса НЕТ намеренно (09.09.2026): в имени хоста
# узнаётся поставщик.
SCRIPT_VIEWABILITY = "dsp_viewability_src"
PROD_PARTNER = PARTNER_SETTING
# Кабинет-демоклиент и демокампания для креатива НАЦЕЛИВАНИЯ (владелец 12.09.2026).
TARGETING_PARTNER = "dsp_targeting_partner_xxhash"
TARGETING_CAMPAIGN = "dsp_targeting_campaign_xxhash"

ENV_PROD_PARTNER = "DSP_PARTNER_XXHASH"
ENV_TARGETING_PARTNER = "DSP_TARGETING_PARTNER_XXHASH"
ENV_TARGETING_CAMPAIGN = "DSP_TARGETING_CAMPAIGN_XXHASH"


def _env(key: str) -> str:
    # Чтение — вызовами с именем переменной, а не через словарь имён: прибор
    # `test_env_passthrough` находит читаемые переменные разбором `os.getenv(<имя>)`.
    if key == PROD_PARTNER:
        return os.getenv(ENV_PROD_PARTNER, "")
    if key == TARGETING_PARTNER:
        return os.getenv(ENV_TARGETING_PARTNER, "")
    if key == TARGETING_CAMPAIGN:
        return os.getenv(ENV_TARGETING_CAMPAIGN, "")
    raise KeyError(key)


def setting(db: Session, key: str) -> str:
    return (db.execute(text("SELECT value FROM company_settings WHERE key = :k"),
                       {"k": key}).scalar() or "")


def effective(db: Session, key: str, value=None) -> str:
    """Что реально пойдёт в DSP по ключу кабинета: значение (или настройка), пусто —
    окружение сервера (владелец 28.09.2026: все три хеша задаются и в .env)."""
    v = (value if value is not None else setting(db, key)).strip()
    return v or _env(key).strip()


def env_present(key: str) -> bool:
    """Задан ли запасной хеш в окружении. Значение наружу не отдаётся."""
    return bool(_env(key))


def creative_script(db: Session, our_code: bool) -> str:
    """Какой скрипт вшивать в креатив для этой площадки. ЕДИНСТВЕННАЯ точка выбора."""
    return setting(db, SCRIPT_OUR_CODE if our_code else SCRIPT_NO_CODE).strip()


def viewability_src(db: Session) -> str:
    """Адрес скрипта видимости. ЕДИНСТВЕННАЯ точка чтения."""
    return setting(db, SCRIPT_VIEWABILITY).strip()


def targeting_cabinet(db: Session) -> tuple:
    """Куда заводить креатив нацеливания: (кабинет-демоклиент, демокампания в нём).
    Пара, а не два вызова: по отдельности они бессмысленны, и разъехаться им нельзя."""
    return effective(db, TARGETING_PARTNER), effective(db, TARGETING_CAMPAIGN)
