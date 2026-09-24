"""Демо-стенд DSP: отработка цепочки креатива на ДЕМО-клиенте DSP.

Зачем: коннектор собран, но живьём не проверен, а проверять его впервые на боевой РК
значит платить за ошибку деньгами.

**Отдельного демо-клиента у нас НЕТ** (выяснено 09.09.2026; 06.09 это была возможность,
которую я записал как факт). Решение владельца: экран ходит в БОЕВОЙ кабинет, а от беды
его держат три вещи — приставка «ТЕСТ · » в названии, статус STOPPED и запрет трогать
кампании, заведённые не отсюда (`_assert_ours`). Появятся демо-ключи — экран сам
переключится на них, менять ничего не нужно.

**Контур `demo` — не косметика.** Каждый вызов пишется в журнал с `contour='demo'`
(миграция `dsp/2026-09-06_send_log_contour.sql`) — при любых ключах.
Защита от дублей ищет прошлый хеш ВНУТРИ своего контура: иначе демо-прогон по той же
сделке заставил бы боевое заведение решить, что кампания уже создана, — и боевая РК не
завелась бы, молча и «успешно».

Шаги отдельными ручками, а не одной кнопкой «сделать всё»: смысл стенда в том, чтобы
видеть ответ КАЖДОГО шага. Обёртка (`/wrap`) вообще не ходит в сеть — её видно до
отправки, и в этом её проверка.
"""
import hashlib
import logging
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

log = logging.getLogger("finance.dsp")

# Тот же корень хранилища, что у стадии сборки (`routers/launch_prep.UPLOADS_ROOT`).
UPLOADS_ROOT = "/app/uploads"

VIEW = require_permission("dsp_demo", "view")
EDIT = require_permission("dsp_demo", "edit")

# Демо-контур настраивается ОТДЕЛЬНЫМИ переменными — если они есть.
#
# 09.09.2026 выяснилось, что отдельного демо-клиента у нас НЕТ и токена под него тоже:
# в решении 06.09 это была возможность, а не факт, и я записал её как факт. Владелец
# выбрал работать тренировкой в БОЕВОМ кабинете. Отдельные переменные остались первыми
# по очереди: появится демо-клиент — достаточно вписать их в .env, код не трогаем.
ENV_URL = "DSP_DEMO_API_URL"
ENV_TOKEN = "DSP_DEMO_TOKEN"
ENV_PARTNER = "DSP_DEMO_PARTNER_XXHASH"

# Кабинет, в который фактически уходят вызовы экрана.
CAB_DEMO = "demo"     # свой демо-клиент
CAB_PROD = "prod"     # боевой кабинет, ключей демо нет


def _creds() -> Optional[dict]:
    """Чем и куда ходит демо-экран. Демо-ключи вперёд, боевые — только если демо нет.

    Порядок именно такой и обратным быть не может: пока демо-ключи заданы, боевые тут не
    участвуют вовсе.
    """
    if os.getenv(ENV_TOKEN) and os.getenv(ENV_PARTNER):
        return {"url": os.getenv(ENV_URL) or os.getenv("DSP_API_URL"),
                "token": os.getenv(ENV_TOKEN), "partner": os.getenv(ENV_PARTNER),
                "cabinet": CAB_DEMO}
    if os.getenv("DSP_ACCESS_TOKEN") and os.getenv("DSP_PARTNER_XXHASH"):
        return {"url": os.getenv("DSP_API_URL"), "token": os.getenv("DSP_ACCESS_TOKEN"),
                "partner": os.getenv("DSP_PARTNER_XXHASH"), "cabinet": CAB_PROD}
    return None


def _mask(v: Optional[str]) -> Optional[str]:
    """Хвост хеша для опознания. Целиком не показываем даже в демо: экран видят люди,
    которым доступ к кабинету DSP не выдавали."""
    if not v:
        return None
    return f"…{v[-4:]}" if len(v) > 4 else "…"


def demo_client() -> MsClient:
    creds = _creds()
    if not creds:
        raise HTTPException(
            400, "DSP не настроен: нет ни демо-ключей, ни боевых. Владелец кладёт "
                 "значения в .env — из переписки они не переносятся")
    # Контур журнала — ВСЕГДА demo, даже когда ключи боевые. От него зависит, увидит ли
    # боевое заведение РК эти вызовы своими: не должно ни при каких ключах.
    return MsClient(url=creds["url"], token=creds["token"],
                    partner_xxhash=creds["partner"], contour=DEMO)


def _assert_ours(xxhash: str) -> None:
    """В боевом кабинете экран трогает ТОЛЬКО то, что сам же завёл.

    Иначе одна вставленная из буфера строка останавливает настоящую кампанию или меняет
    ей план — «стоп» и «правка лимита» здесь такие же настоящие, как в кабинете.
    Со своим демо-клиентом ограничения нет: там портить нечего.
    """
    creds = _creds()
    if not creds or creds["cabinet"] != CAB_PROD:
        return
    from app.dsp.db import dsp_engine
    try:
        with dsp_engine().connect() as c:
            found = c.execute(text(
                "SELECT 1 FROM dsp_send_log WHERE contour = 'demo' "
                "AND upper(ms_xxhash) = upper(:h) LIMIT 1"), {"h": xxhash}).first()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"Журнал недоступен, а без него в боевом кабинете "
                                 f"проверить принадлежность кампании нечем: {e!r}")
    if not found:
        raise HTTPException(
            403, "Эта кампания заведена не отсюда. Ключей демо-контура нет, экран ходит "
                 "в боевой кабинет — и трогает только то, что создал сам")


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


def _sandbox(user, html: str) -> Optional[str]:
    """Адрес разметки на домене песочницы, или None, если она не настроена.

    Каталог СВОЙ у каждого человека и переиспользуется: тренировка грузит баннер за
    баннером, а сроков хранения у демо-песочницы нет — случайный каталог на каждую
    загрузку копил бы их вечно.

    Своя рамка нужна потому, что баннер после загрузчика ссылается на ЧУЖОЙ CDN, а наш
    CSP такое на своём домене не покажет: `base-uri 'self'` отменяет их `<base href>`,
    `img-src`/`script-src` не пускают их файлы. Пустая рамка выглядит как «предпросмотр
    сломался», хотя ломается ровно то, что и должно.
    """
    from app.launch_prep import sandbox as sb
    try:
        token, entry = sb.stash_html(UPLOADS_ROOT, html, token=_sandbox_token(user))
        return sb.public_url(token, entry)
    except Exception:  # noqa: BLE001 — предпросмотр не должен ронять сам шаг
        log.warning("Не удалось положить разметку в песочницу", exc_info=True)
        return None


def _sandbox_token(user) -> str:
    """Постоянный, но НЕПОДБИРАЕМЫЙ каталог песочницы для этого человека.

    Песочница раздаётся без авторизации — иначе баннер не открылся бы в кабинете
    площадки, — и единственная её защита в том, что адрес не угадать. Простое
    `dspdemo-<id>` эту защиту сняло бы, а случайный каждый раз копил бы каталоги:
    сроков хранения у демо-песочницы нет. Отсюда хеш от секрета приложения и id.
    """
    salt = os.getenv("SECRET_KEY") or ""
    return "d" + hashlib.sha256(f"{salt}:dsp-demo:{user.id}".encode()).hexdigest()[:31]


@router.get("/state")
def state(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Готов ли стенд, в ЧЕЙ кабинет он ходит и что уже отправляли."""
    creds = _creds()
    return {
        "configured": bool(creds),
        # Экран обязан сказать это первым: в боевом кабинете кампании создаются настоящие.
        "cabinet": creds["cabinet"] if creds else None,
        "title_prefix": dsp_campaigns.DEMO_TITLE_PREFIX,
        "url": creds["url"] if creds else None,
        "partner": _mask(creds["partner"] if creds else None),
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
    кабинете. Лимиты — `total` за весь срок, не остаток: DSP засчитает уже открученное.
    """
    limits: Dict[str, Any] = {}
    if payload.total_shows:
        limits["show"] = {"total": int(payload.total_shows), "day": 0, "hour": 0}
    if payload.total_budget:
        limits["budget"] = {"total": float(payload.total_budget), "day": 0, "hour": 0}
    # Приставка ставится ЗДЕСЬ, а не подсказкой на экране: тренировочная кампания лежит в
    # одном кабинете с боевыми, и «человек допишет сам» — это забудут на второй раз.
    title = payload.title.strip()
    if not title.startswith(dsp_campaigns.DEMO_TITLE_PREFIX):
        title = dsp_campaigns.DEMO_TITLE_PREFIX + title
    # traffic_distribution живёт ВНУТРИ limits. Замерено 09.09.2026 на живом кабинете:
    # ключ на верхнем уровне API молча игнорирует, и кампания остаётся с умолчанием
    # `accelerated`. Боевой сборщик (`campaigns.build_campaign_params`) всегда клал его
    # правильно — расходились именно эти два места, и расхождение было тихим.
    limits["traffic_distribution"] = "uniform_pro"
    params = {"title": title[:255],
              "date_start": payload.date_start, "date_end": payload.date_end,
              "status": "STOPPED",            # демо не должно ничего крутить
              "limits": limits}
    c = demo_client()
    try:
        xxhash = c.campaign_add(params, local_ref=payload.local_ref)
    except MsError as e:
        raise HTTPException(502, f"DSP отказал: {e}")
    log_action(db, user, "dsp_demo_campaign", "dsp", None, f"{params['title']} → {xxhash}")
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
    # Размер отдаём наружу: его объявляет сам баннер, а загрузчик возвращает то, КАК он
    # его понял. Расхождение с тем, что человек ждал, видно только здесь.
    return {"url": out["url"], "html": out["html"],
            "macros": cr.macros_found(out["html"]), "bytes": len(data),
            "size": out.get("size"), "sandbox_url": _sandbox(user, out["html"])}


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
    from app.routers.traffic_catalog import creative_script, viewability_src
    script = (creative_script(db, payload.our_code)
              if payload.our_code is not None else None)
    vsrc = viewability_src(db) if payload.viewability else ""
    try:
        out = cr.wrap_html(payload.html, erid=payload.erid,
                           viewability_src=vsrc, extra_script=script)
    except cr.CreativeError as e:
        raise HTTPException(400, str(e))
    return {"html": out, "macros": cr.macros_found(out),
            "sandbox_url": _sandbox(user, out),
            "viewability": bool(vsrc) and vsrc in out,
            # Адрес скрипта видимости не задан на вкладке «Скрипт» админки трафика.
            # Тот же принцип, что у счётчика ниже: молчать нельзя, креатив уедет без него.
            "viewability_missing": payload.viewability and not vsrc,
            # Пусто — настройка колонки не заполнена. Молчать об этом нельзя: креатив
            # уедет без счётчика, и выяснится это только по отсутствию данных.
            "script": script, "script_missing": payload.our_code is not None and not script}


class CreativeIn(BaseModel):
    campaign_xxhash: str
    title: str
    link: str
    html_code: str
    # Размер — из ответа загрузчика на шаге 2. Своего мнения о нём у нас нет.
    size: Optional[str] = None
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
            adomain=payload.adomain, size=payload.size,
            total_shows=payload.total_shows)
    except cr.CreativeError as e:
        raise HTTPException(400, str(e))
    if not payload.html_code.strip():
        raise HTTPException(400, "Нет разметки креатива — сначала шаги 2 и 3")
    # Креатив в ЧУЖУЮ кампанию — это демо-баннер в боевой РК (аудит 23.09.2026, 4.M2).
    _assert_ours(payload.campaign_xxhash)
    c = demo_client()
    try:
        xxhash = c.creative_add(payload.campaign_xxhash, params, local_ref=payload.local_ref)
        edit_result = c.creative_edit(xxhash, {"data": {"html_code": payload.html_code}},
                                      local_ref=payload.local_ref)
    except MsError as e:
        raise HTTPException(502, f"DSP отказал: {e}")
    log_action(db, user, "dsp_demo_creative", "dsp", None,
               f"{payload.title} → {xxhash} в {payload.campaign_xxhash}")
    # Разметка уходит ВТОРЫМ вызовом (`Creative.edit`), и в теле `add` её нет по
    # определению. Пока экран показывал только тело `add`, это читалось как «итоговый
    # html не передан» — говорим прямо, сколько байт ушло и чем.
    return {"xxhash": xxhash, "campaign_xxhash": payload.campaign_xxhash,
            "request": params, "html_bytes": len(payload.html_code),
            "edit": {"method": "Creative.edit", "field": "data.html_code",
                     "result": edit_result}}


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
    # Таргетинг чужой кампании — выключенные площадки боевой РК (аудит 23.09.2026, 4.M2).
    _assert_ours(payload.xxhash)
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
    _assert_ours(xxhash)
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
    _assert_ours(xxhash)
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
    if not payload.dry_run:
        _assert_ours(xxhash)
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
