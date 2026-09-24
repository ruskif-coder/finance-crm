# -*- coding: utf-8 -*-
"""Состояние СЪЁМА статистики Weborama — когда забирали и что доехало.

Не путать с `app/ad/external.py`: тот отвечает на вопрос «заведена ли вставка и есть ли
пиксель у этой площадки», то есть про ЗАВЕДЕНИЕ. Здесь — про ДАННЫЕ: прошёл ли съём,
сколько строк лежит в сырье и сколько из них вообще способно попасть на экран. Вопросы
разные, и слияние их в один показатель скрыло бы худший случай: заведение прошло, съём
прошёл, а чисел на дашборде нет.

ТРИ СОСТОЯНИЯ, КОТОРЫЕ ЛЕГКО СЛИТЬ В ОДНО «не работает»:

· **не настроено** — в окружении нет учётных данных. Виноват не код;
· **не забиралось** — настроено, но съём ни разу не отработал;
· **забрано, но не прицеплено** — сырьё лежит, а соответствий «их вставка → наша
  площадка» нет, поэтому на дашборд не попало ни одно число.

Третье — сегодняшнее состояние и самое коварное: каждый отдельный шаг отчитывается
успехом.
"""
import os
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

# Аккаунт сюда не входит: он настройка, а не переменная (см. `_account`).
ENV = ("WEBORAMA_API_URL", "WEBORAMA_EMAIL", "WEBORAMA_PASSWORD")


def _configured() -> bool:
    """Пустая строка — это НЕ заданное значение.

    compose подставляет `${WEBORAMA_EMAIL:-}`, поэтому переменная в процессе есть всегда,
    и проверка «ключ присутствует» показала бы настроенный коннектор там, где значений
    нет ни одного. На проде сейчас именно так.
    """
    return all((os.getenv(k) or "").strip() for k in ENV)


def _account(db: Session) -> Optional[str]:
    """Тот же аккаунт, что у заведения и съёма, — иначе экран описывал бы не тот."""
    from app.weborama import provision

    try:
        return provision.account_id(db)
    except provision.ProvisionError:
        return None


def stats_state(db: Session, account_id: Optional[str] = None) -> dict:
    account_id = account_id or _account(db)
    out = {"configured": _configured() and bool(account_id),
           "account_id": account_id or None,
           "raw": None, "cursor": None, "mapped_insertions": 0,
           "verdict": None, "written_rows": 0}

    out["mapped_insertions"] = db.execute(text(
        "SELECT count(*) FROM weborama_refs WHERE kind = 'insertion'"
        + (" AND account_id = :a" if account_id else "")),
        ({"a": account_id} if account_id else {})).scalar() or 0
    out["written_rows"] = db.execute(text(
        "SELECT count(*) FROM ad_campaign_stat WHERE source = 'weborama'")).scalar() or 0

    if not out["configured"]:
        out["verdict"] = ("не настроено — учётные данные Weborama не заданы"
                          if not _configured() else
                          "не настроено — не задан аккаунт Weborama (Каталог → Скрипты сайта)")
        return out

    try:
        from app.dsp.db import DspSessionLocal
        if DspSessionLocal is None:
            out["verdict"] = "аналитическая база не подключена — сырьё складывать некуда"
            return out
        dsp = DspSessionLocal()
        try:
            raw = dsp.execute(text(
                "SELECT count(*) AS rows, count(DISTINCT insertion_id) AS insertions, "
                "       min(day) AS since, max(day) AS until, "
                "       coalesce(sum(impression), 0) AS impressions "
                "  FROM wcm_stat_daily WHERE account_id = :a"), {"a": account_id}).mappings().first()
            out["raw"] = dict(raw) if raw else None
            cur = dsp.execute(text(
                "SELECT last_pulled_day, last_run_at, last_rows, last_absent, last_error "
                "  FROM wcm_sync_cursor WHERE account_id = :a"),
                {"a": account_id}).mappings().first()
            out["cursor"] = dict(cur) if cur else None
        finally:
            dsp.close()
    except Exception as e:                                   # noqa: BLE001
        out["verdict"] = f"аналитическая база недоступна: {e!r}"[:200]
        return out

    cur = out["cursor"] or {}
    if cur.get("last_error"):
        out["verdict"] = f"последний съём не удался: {cur['last_error']}"
    elif not cur.get("last_run_at"):
        out["verdict"] = "настроено, но статистику ещё ни разу не забирали"
    elif not out["mapped_insertions"]:
        out["verdict"] = ("данные забраны, но прицепить их не к чему: ни одной вставки "
                          "не заведено через нашу систему")
    elif cur.get("last_absent"):
        out["verdict"] = f"забрано, но Weborama не прислала метрики: {cur['last_absent']}"
    else:
        out["verdict"] = "съём работает"
    return out
