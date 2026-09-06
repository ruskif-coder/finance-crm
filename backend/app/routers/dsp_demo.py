"""Демо-стенд DSP: отработка цепочки креатива на ДЕМО-клиенте DSP.

Зачем (владелец 06.09.2026): внутри DSP есть демо-клиент, на котором можно тренироваться
вне боевых кампаний. Коннектор собран, но живьём не проверен — а проверять его впервые на
боевой РК значит платить за ошибку деньгами.

**Контур `demo` — не косметика.** У демо свои токен и `partner_xxhash`, и каждый вызов
пишется в журнал с `contour='demo'` (миграция `dsp/2026-09-06_send_log_contour.sql`).
Защита от дублей ищет прошлый хеш ВНУТРИ своего контура: иначе демо-прогон по той же
сделке заставил бы боевое заведение решить, что кампания уже создана, — и боевая РК не
завелась бы, молча и «успешно».

Шаги отдельными ручками, а не одной кнопкой «сделать всё»: смысл стенда в том, чтобы
видеть ответ КАЖДОГО шага. Обёртка (`/wrap`) вообще не ходит в сеть — её видно до
отправки, и в этом её проверка.
"""
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.dsp import campaigns as dsp_campaigns
from app.dsp import creatives as cr
from app.dsp.client import DEMO, MsClient, MsError
from app.dsp.sources import source_key
from app.models import User
from app.permissions import require_permission

router = APIRouter()

VIEW = require_permission("dsp_demo", "view")
EDIT = require_permission("dsp_demo", "edit")

# Демо-контур настраивается ОТДЕЛЬНЫМИ переменными. Не «переключателем» у боевых: один
# забытый флаг — и тренировка уходит в боевой кабинет.
ENV_URL = "DSP_DEMO_API_URL"
ENV_TOKEN = "DSP_DEMO_TOKEN"
ENV_PARTNER = "DSP_DEMO_PARTNER_XXHASH"


def _mask(v: Optional[str]) -> Optional[str]:
    """Хвост хеша для опознания. Целиком не показываем даже в демо: экран видят люди,
    которым доступ к кабинету DSP не выдавали."""
    if not v:
        return None
    return f"…{v[-4:]}" if len(v) > 4 else "…"


def demo_client() -> MsClient:
    missing = [k for k in (ENV_TOKEN, ENV_PARTNER) if not os.getenv(k)]
    if missing:
        raise HTTPException(
            400, "Демо-контур не настроен: нет " + ", ".join(missing)
                 + ". Владелец кладёт значения в .env — из переписки они не переносятся")
    return MsClient(url=os.getenv(ENV_URL) or os.getenv("DSP_API_URL"),
                    token=os.getenv(ENV_TOKEN),
                    partner_xxhash=os.getenv(ENV_PARTNER),
                    contour=DEMO)


def _log_rows(limit: int = 30) -> List[dict]:
    """Последние строки журнала ДЕМО-контура. Боевые сюда не попадают по условию."""
    from app.dsp.db import dsp_engine
    try:
        with dsp_engine().connect() as c:
            rows = c.execute(text(
                "SELECT ts, method, entity_type, local_ref, ms_xxhash, ok, error "
                "FROM dsp_send_log WHERE contour = 'demo' ORDER BY ts DESC LIMIT :n"),
                {"n": limit}).mappings().all()
        return [dict(r) for r in rows]
    except Exception as e:  # noqa: BLE001 — журнал не должен ронять экран
        return [{"error": f"журнал недоступен: {e!r}"}]


@router.get("/state")
def state(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Готов ли стенд и что уже отправляли."""
    return {
        "configured": bool(os.getenv(ENV_TOKEN) and os.getenv(ENV_PARTNER)),
        "url": os.getenv(ENV_URL) or os.getenv("DSP_API_URL"),
        "partner": _mask(os.getenv(ENV_PARTNER)),
        "env": {"token": ENV_TOKEN, "partner": ENV_PARTNER, "url": ENV_URL},
        "source_keys": {"web": source_key(db, "web"), "app": source_key(db, "app")},
        "log": _log_rows(),
    }


class CampaignIn(BaseModel):
    title: str
    date_start: str
    date_end: str
    total_shows: Optional[int] = None
    total_budget: Optional[float] = None
    local_ref: Optional[str] = "demo"


@router.post("/campaign")
def create_campaign(payload: CampaignIn, db: Session = Depends(get_db),
                    user: User = Depends(EDIT)):
    """Шаг 1 — мастер-кампания. Возвращает её xxhash.

    `uniform_pro` шлём ЯВНО: умолчание у API — `accelerated`, а не то, что стоит в
    кабинете. Лимиты — `total` за весь срок, не остаток: МС засчитает уже открученное.
    """
    limits: Dict[str, Any] = {}
    if payload.total_shows:
        limits["show"] = {"total": int(payload.total_shows), "day": 0, "hour": 0}
    if payload.total_budget:
        limits["budget"] = {"total": float(payload.total_budget), "day": 0, "hour": 0}
    params = {"title": payload.title.strip()[:255],
              "date_start": payload.date_start, "date_end": payload.date_end,
              "status": "STOPPED",            # демо не должно ничего крутить
              "traffic_distribution": "uniform_pro",
              "limits": limits}
    c = demo_client()
    try:
        xxhash = c.campaign_add(params, local_ref=payload.local_ref)
    except MsError as e:
        raise HTTPException(502, f"DSP отказал: {e}")
    log_action(db, user, "dsp_demo_campaign", "dsp", None, f"{payload.title} → {xxhash}")
    return {"xxhash": xxhash, "request": params}


@router.post("/upload")
def upload(file: UploadFile = File(...), local_ref: str = Form("demo"),
           user: User = Depends(EDIT)):
    """Шаг 2 — архив баннера. Возвращает HTML, который выдал загрузчик DSP."""
    # Читаем ПОРЦИЯМИ с потолком: `file.read()` целиком поднял бы в память контейнера
    # (mem_limit 512m) сколько угодно, и ограничение в 20 МБ внутри `check_zip`
    # сработало бы уже после падения по OOM — вместе со всеми чужими запросами.
    data = b""
    while True:
        chunk = file.file.read(1024 * 1024)
        if not chunk:
            break
        data += chunk
        if len(data) > cr.MAX_ZIP_BYTES:
            raise HTTPException(
                413, f"Архив больше {cr.MAX_ZIP_BYTES // (1024 * 1024)} МБ")
    c = demo_client()
    try:
        out = cr.upload_zip(c, data, file.filename or "creative.zip", local_ref=local_ref)
    except cr.CreativeError as e:
        raise HTTPException(400, str(e))
    except MsError as e:
        raise HTTPException(502, f"DSP отказал: {e}")
    return {"url": out["url"], "html": out["html"],
            "macros": cr.macros_found(out["html"]), "bytes": len(data)}


class WrapIn(BaseModel):
    html: str
    erid: Optional[str] = None
    viewability: bool = True
    # Признак площадки, на которую пойдёт креатив: от него зависит, КАКОЙ наш счётчик
    # вшивается. None — не вшивать вовсе (проверка одной обёртки).
    our_code: Optional[bool] = None


@router.post("/wrap")
def wrap(payload: WrapIn, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Шаг 3 — обёртка. БЕЗ сети: результат видно до отправки, в этом её проверка."""
    from app.routers.traffic_catalog import creative_script
    script = (creative_script(db, payload.our_code)
              if payload.our_code is not None else None)
    try:
        out = cr.wrap_html(payload.html, erid=payload.erid,
                           viewability=payload.viewability, extra_script=script)
    except cr.CreativeError as e:
        raise HTTPException(400, str(e))
    return {"html": out, "macros": cr.macros_found(out),
            "viewability": cr.VIEWABILITY_SRC in out,
            # Пусто — настройка колонки не заполнена. Молчать об этом нельзя: креатив
            # уедет без счётчика, и выяснится это только по отсутствию данных.
            "script": script, "script_missing": payload.our_code is not None and not script}


class CreativeIn(BaseModel):
    campaign_xxhash: str
    title: str
    link: str
    html_code: str
    erid: Optional[str] = None
    self_inn: Optional[str] = None
    self_name: Optional[str] = None
    adomain: Optional[str] = None
    total_shows: Optional[int] = None
    local_ref: Optional[str] = "demo"


@router.post("/creative")
def create_creative(payload: CreativeIn, db: Session = Depends(get_db),
                    user: User = Depends(EDIT)):
    """Шаг 4 — креатив в кампании: `Creative.add`, затем `Creative.edit` с разметкой.

    Два вызова, а не один: `add` заводит объект и возвращает хеш, разметка кладётся
    правкой. `description` не трогаем — ломается (готча из теста владельца).
    """
    try:
        params = cr.build_creative_params(
            title=payload.title, link=payload.link, erid=payload.erid,
            self_inn=payload.self_inn, self_name=payload.self_name,
            adomain=payload.adomain, total_shows=payload.total_shows)
    except cr.CreativeError as e:
        raise HTTPException(400, str(e))
    if not payload.html_code.strip():
        raise HTTPException(400, "Нет разметки креатива — сначала шаги 2 и 3")
    c = demo_client()
    try:
        xxhash = c.creative_add(payload.campaign_xxhash, params, local_ref=payload.local_ref)
        c.creative_edit(xxhash, {"data": {"html_code": payload.html_code}},
                        local_ref=payload.local_ref)
    except MsError as e:
        raise HTTPException(502, f"DSP отказал: {e}")
    log_action(db, user, "dsp_demo_creative", "dsp", None,
               f"{payload.title} → {xxhash} в {payload.campaign_xxhash}")
    return {"xxhash": xxhash, "campaign_xxhash": payload.campaign_xxhash,
            "request": params}


class TargetingIn(BaseModel):
    xxhash: str
    target_key: str = "source"
    items: Dict[str, Any]
    is_invert_mode: bool = False


@router.post("/targeting")
def set_targeting(payload: TargetingIn, db: Session = Depends(get_db),
                  user: User = Depends(EDIT)):
    """Шаг 5 — таргетинг. Для площадки это `source`: у него нет лимита, только
    включённость и ставка — поэтому суточный лимит на площадку у нас ОРИЕНТИР."""
    c = demo_client()
    try:
        out = c.targeting_set(payload.xxhash, payload.target_key, payload.items,
                              is_invert_mode=payload.is_invert_mode)
    except MsError as e:
        raise HTTPException(502, f"DSP отказал: {e}")
    # Таргетинг МЕНЯЕТ кампанию в чужой системе — значит попадает в журнал действий, как
    # статус и план. Прогон 06.09.2026 нашёл его единственной изменяющей ручкой стенда без
    # записи: действие есть, а найти его потом негде.
    log_action(db, user, "dsp_demo_targeting", "dsp", None,
               f"{payload.xxhash}: {payload.target_key} = {list(payload.items)[:5]}")
    return {"result": out}


# ── Управление кампанией: статус и план до конца срока ───────────────────────

# У DSP нет отдельной «паузы»: выдачу останавливает один статус STOPPED.
# «Стоп» отличается от паузы только тем, что кампанию убирают из работы совсем (ARCHIVE),
# и обратно это уже не включается. Подписи на экране говорят об этом прямо — иначе
# «пауза» и «стоп» выглядели бы двумя разными состояниями, которых в DSP нет.
STATUS_ACTIONS = {"start": "LAUNCHED", "pause": "STOPPED", "stop": "ARCHIVE"}


@router.get("/campaign/{xxhash}")
def campaign_info(xxhash: str, user: User = Depends(VIEW)):
    """Что сейчас у кампании в DSP: статус, лимиты, даты. Ответ отдаём как есть —
    смысл стенда в том, чтобы видеть настоящий ответ, а не наш пересказ."""
    c = demo_client()
    try:
        return {"info": c.campaign_get_info(xxhash)}
    except MsError as e:
        raise HTTPException(502, f"DSP отказал: {e}")


class StatusIn(BaseModel):
    action: str      # start | pause | stop


@router.post("/campaign/{xxhash}/status")
def campaign_status(xxhash: str, payload: StatusIn, db: Session = Depends(get_db),
                    user: User = Depends(EDIT)):
    status = STATUS_ACTIONS.get(payload.action)
    if not status:
        raise HTTPException(400, f"Неизвестное действие «{payload.action}»")
    c = demo_client()
    try:
        out = c.campaign_set_status(xxhash, status, local_ref=xxhash)
    except MsError as e:
        raise HTTPException(502, f"DSP отказал: {e}")
    log_action(db, user, "dsp_demo_status", "dsp", None, f"{xxhash} → {status}")
    return {"status": status, "result": out}


class PlanIn(BaseModel):
    """Человек думает ОСТАТКОМ: «до конца надо открутить ещё столько»."""
    delivered_show: Optional[float] = 0
    remaining_show: Optional[float] = None
    delivered_budget: Optional[float] = 0
    remaining_budget: Optional[float] = None
    date_end: Optional[str] = None
    dry_run: bool = False


@router.post("/campaign/{xxhash}/plan")
def campaign_plan(xxhash: str, payload: PlanIn, db: Session = Depends(get_db),
                  user: User = Depends(EDIT)):
    """Поменять план до конца кампании.

    Суточный темп в МС пересчитывается сам: `(total − открутили) / оставшиеся дни`. Значит
    менять сутки нужно ИЗМЕНЕНИЕМ ОСТАТКА — но в API уходит не остаток, а полный новый
    total за весь срок (`campaigns.plan_total`). Прислать остаток напрямую значит сказать,
    что весь план равен остатку: МС засчитает открученное и остановит кампанию раньше.

    `dry_run` показывает, ЧТО уйдёт, ничего не отправляя, — арифметику видно до нажатия.
    """
    if payload.remaining_show is None and payload.remaining_budget is None:
        raise HTTPException(400, "Не задан остаток — нечего менять")
    show_total = (dsp_campaigns.plan_total(payload.delivered_show, payload.remaining_show)
                  if payload.remaining_show is not None else None)
    budget_total = (dsp_campaigns.plan_total(payload.delivered_budget, payload.remaining_budget)
                    if payload.remaining_budget is not None else None)
    params = dsp_campaigns.build_plan_params(show_total=show_total,
                                             budget_total=budget_total,
                                             date_end=payload.date_end)
    explain = {"show": None, "budget": None}
    if show_total is not None:
        explain["show"] = {"delivered": payload.delivered_show,
                           "remaining": payload.remaining_show, "total": show_total}
    if budget_total is not None:
        explain["budget"] = {"delivered": payload.delivered_budget,
                             "remaining": payload.remaining_budget, "total": budget_total}
    if payload.dry_run:
        return {"sent": False, "request": params, "explain": explain}
    c = demo_client()
    try:
        out = c.campaign_edit(xxhash, params, local_ref=xxhash)
    except MsError as e:
        raise HTTPException(502, f"DSP отказал: {e}")
    log_action(db, user, "dsp_demo_plan", "dsp", None,
               f"{xxhash}: show total {show_total}, budget total {budget_total}")
    return {"sent": True, "request": params, "explain": explain, "result": out}
