# -*- coding: utf-8 -*-
"""Демо-стенд Weborama (WCM) — по образцу стенда DSP.

Зачем: коннектор собран, но живьём не проверен ни разу. Проверять его впервые «в бою»
здесь дороже, чем в DSP: неверно заведённая позиция означает, что показы площадки
измеряются под чужим именем, и заметно это станет только по расхождению отчётов.

**Своего демо-аккаунта у нас нет** — как и у DSP. Но в кабинете Weborama есть проект
`TEST_2026`, и тренироваться правильно в нём: заводить учебные структуры под именем,
которое видно в списке.

Шаги отдельными ручками, а не одной кнопкой: смысл стенда — видеть ОТВЕТ КАЖДОГО шага.
Ответ отдаётся как есть (`raw`), потому что формы ответов в их доке нет вовсе, а пересказ
неизвестного — способ потерять половину.

`account_id` приходит С ЭКРАНА, а не из окружения. Аккаунты Weborama выдаёт списком и
закрепляет за клиентами: взять его из переменной среды значит однажды записать кампанию
одного рекламодателя в измерения другого. Переменная `WEBORAMA_DEMO_ACCOUNT_ID` только
ПОДСТАВЛЯЕТ значение в поле — выбор всё равно делает человек, и он его видит.
"""
import logging
import os
import re
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.models import User
from app.permissions import require_permission
from app.weborama import enums, matching, naming, tags
from app.weborama.client import (ENV_EMAIL, ENV_PASSWORD, ENV_URL, WcmAuthError,
                                 WcmClient, WcmError)
from app import timez

router = APIRouter()

log = logging.getLogger("finance.weborama")

VIEW = require_permission("weborama_demo", "view")
EDIT = require_permission("weborama_demo", "edit")

ENV_ACCOUNT = "WEBORAMA_DEMO_ACCOUNT_ID"    # только подсказка в поле, не умолчание клиента


def _client(account_id: str) -> WcmClient:
    if not str(account_id or "").strip():
        raise HTTPException(400, "Не выбран аккаунт Weborama — он адресует весь обмен")
    if not (os.getenv(ENV_EMAIL) and os.getenv(ENV_PASSWORD)):
        raise HTTPException(
            400, f"Weborama не настроена: нет {ENV_EMAIL} или {ENV_PASSWORD}. "
                 f"Значения кладёт владелец в .env — из переписки они не переносятся")
    try:
        return WcmClient(account_id)
    except WcmError as e:
        raise HTTPException(400, str(e))


def _run(fn, *a, **kw):
    """Один вызов с переводом ошибок обмена в понятный человеку отказ."""
    try:
        return fn(*a, **kw)
    except WcmAuthError as e:
        raise HTTPException(401, f"Weborama не пустила: {e}")
    except WcmError as e:
        raise HTTPException(502, f"Weborama отказала: {e}")



# ── журнал стенда ────────────────────────────────────────────────────────────
#
# Пишем КАЖДЫЙ шаг с полным ответом в текстовый файл. Зачем файл, а не таблица: схему
# хранения согласуют до кода, а разбирать проблемы обмена надо уже сейчас — и разбирать
# их по пересказу в чате невозможно, нужен сырой ответ целиком.
#
# `/app/logs` смонтирован на `backend/logs` хоста, то есть файл читается и снаружи
# контейнера. Пароль и токен сюда не попадают никогда: в шаге входа пишется только
# аккаунт и длина токена.
LOG_PATH = "/app/logs/weborama_demo.log"
LOG_MAX_BYTES = 5 * 1024 * 1024      # больше — это уже не журнал, а свалка


def _journal(step: str, user, request: Any = None, response: Any = None,
             error: Any = None) -> None:
    """Одна запись журнала. Сбой записи НЕ роняет шаг: журнал — свидетель, а не участник."""
    import json as _json
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > LOG_MAX_BYTES:
            os.replace(LOG_PATH, LOG_PATH + ".1")
        stamp = timez.msk_now().strftime("%Y-%m-%d %H:%M:%S")   # журнал читают люди
        who = getattr(user, "name", None) or getattr(user, "id", "—")

        def dump(v):
            try:
                return _json.dumps(v, ensure_ascii=False, indent=2, default=str)
            except Exception:      # noqa: BLE001
                return str(v)

        sep = "=" * 78
        block = ["", sep, f"[{stamp}] ШАГ: {step}   пользователь: {who}"]
        if request is not None:
            block += ["— запрос:", dump(request)]
        if response is not None:
            block += ["— ответ:", dump(response)]
        if error is not None:
            block += ["— ОТКАЗ:", dump(error)]
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write("\n".join(block) + "\n")
    except Exception:              # noqa: BLE001
        log.warning("Не удалось записать шаг «%s» в журнал стенда", step, exc_info=True)


@router.get("/log")
def read_log(lines: int = 200, user: User = Depends(VIEW)):
    """Хвост журнала — чтобы смотреть его с экрана, не заходя в контейнер."""
    try:
        with open(LOG_PATH, encoding="utf-8") as fh:
            tail = fh.readlines()[-max(1, min(lines, 2000)):]
        return {"path": LOG_PATH, "lines": len(tail), "text": "".join(tail)}
    except FileNotFoundError:
        return {"path": LOG_PATH, "lines": 0, "text": "Журнал пуст — шагов ещё не было."}


@router.get("/state")
def state(user: User = Depends(VIEW)):
    """Настроен ли стенд и чем он будет ходить."""
    return {
        "configured": bool(os.getenv(ENV_EMAIL) and os.getenv(ENV_PASSWORD)),
        "url": os.getenv(ENV_URL) or "https://api-wcm-ru.weborama.io",
        "email": os.getenv(ENV_EMAIL),          # адрес, а не пароль: по нему видно, чей вход
        "account_hint": os.getenv(ENV_ACCOUNT) or "",
        "env": {"url": ENV_URL, "email": ENV_EMAIL, "password": ENV_PASSWORD,
                "account": ENV_ACCOUNT},
        "channel_id": enums.DEFAULT_CHANNEL,
        "delivery_format_id": enums.DEFAULT_DELIVERY_FORMAT,
        "formats": enums.DELIVERY_FORMATS,
    }


class AccountIn(BaseModel):
    account_id: str


@router.post("/login")
def login(payload: AccountIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Шаг 1 — вход. Токен НЕ показываем и не возвращаем: он ключ ко всему аккаунту.

    Отдаём только факт и его длину — этого достаточно, чтобы отличить «вошли» от «пришло
    что-то не то», и недостаточно, чтобы токен утёк на экран, который видят несколько
    человек.
    """
    c = _client(payload.account_id)
    try:
        token = _run(c.login)
    except HTTPException as e:
        _journal("1 · вход", user, {"account_id": payload.account_id}, error=e.detail)
        raise
    out = {"ok": True, "token_length": len(token or ""), "account_id": payload.account_id}
    _journal("1 · вход", user, {"account_id": payload.account_id}, out)
    log_action(db, user, "weborama_login", "weborama", None, f"аккаунт {payload.account_id}")
    return out


@router.post("/ad-spaces")
def ad_spaces(payload: AccountIn, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Шаг 2 — найти НАШ ad_space и сеть.

    Здесь стояло сопоставление наших площадок с их ad_space по домену. Живой вызов
    09.09.2026 показал, что задачи такой нет: каталог глобальный (1080 записей, включая
    французские сайты), ни одного нашего домена в нём нет, а все наши вставки висят на
    ОДНОМ ad_space `SIMB-AD`. Значит ad_space и сеть — константы аккаунта, а «какая
    площадка» несёт только метка вставки.
    """
    c = _client(payload.account_id)
    try:
        rows = _run(c.ad_spaces_all)
    except HTTPException as e:
        _journal("2 · ad_space", user, {"account_id": payload.account_id}, error=e.detail)
        raise
    ours = matching.find_our_ad_space(rows)
    _journal("2 · ad_space", user, {"account_id": payload.account_id},
             {"total": len(rows), "ad_space": ours})
    return {"total": len(rows), "ad_space": ours,
            "sample": matching.ad_space_index(rows)[:5],
            "hint": "ad_space и ad_network — константы аккаунта; площадку различает "
                    "только метка вставки"}


class ProjectIn(AccountIn):
    deal_code: str
    brand: str
    month: str                      # ГГГГ-ММ


@router.post("/project")
def create_project(payload: ProjectIn, db: Session = Depends(get_db),
                   user: User = Depends(EDIT)):
    """Шаг 3 — проект. Имя `<код сделки>_<бренд>_<ГГГГ-ММ>` (решение владельца 09.09.2026)."""
    try:
        label = naming.project_label(payload.deal_code, payload.brand, payload.month)
    except ValueError as e:
        raise HTTPException(400, str(e))
    c = _client(payload.account_id)
    raw = _run(c.call, "POST", "/advertiser/projects.json", data={"label": label})
    wid = _run(c._created, raw, "проект")
    _journal("4 · проект", user, payload.dict(), raw)
    log_action(db, user, "weborama_project", "weborama", None, f"{label} → {wid}")
    return {"label": label, "id": wid, "raw": raw}


class CampaignIn(AccountIn):
    project_id: str
    brand: str
    ident: str
    landing_url: str


@router.post("/campaign")
def create_campaign(payload: CampaignIn, db: Session = Depends(get_db),
                    user: User = Depends(EDIT)):
    """Шаг 4 — кампания. Имя `<бренд>_<ID>`; `landing_url` обязателен у них."""
    try:
        label = naming.campaign_label(payload.brand, payload.ident)
    except ValueError as e:
        raise HTTPException(400, str(e))
    url = (payload.landing_url or "").strip()
    if not url:
        raise HTTPException(400, "Weborama требует landing_url у кампании")
    # Проверяем ДО отправки. 09.09.2026 в это поле уехала markdown-ссылка целиком —
    # `[www.simb-ad.com](https://www.simb-ad.com)`, — и Weborama ответила 406, вернув весь
    # объект с умолчаниями вместо объяснения. Сказать «это не адрес» можно раньше и понятнее.
    if not re.match(r"^https?://[^\s<>\[\]()]+$", url):
        raise HTTPException(
            400, "landing_url должен быть адресом вида https://example.ru — без пробелов "
                 "и без разметки. Похоже, вставилась ссылка целиком со скобками: "
                 "оставьте только адрес")
    c = _client(payload.account_id)
    raw = _run(c.call, "POST", "/advertiser/campaigns.json",
               data={"project_id": payload.project_id, "label": label,
                     "landing_url": payload.landing_url.strip(),
                     "channel_id": enums.DEFAULT_CHANNEL})
    wid = _run(c._created, raw, "кампанию")
    _journal("5 · кампания", user, payload.dict(), raw)
    log_action(db, user, "weborama_campaign", "weborama", None, f"{label} → {wid}")
    return {"label": label, "id": wid, "raw": raw}


class NetworkIn(AccountIn):
    label: str = "SIMB-AD"


@router.post("/ad-network")
def create_ad_network(payload: NetworkIn, db: Session = Depends(get_db),
                      user: User = Depends(EDIT)):
    """Шаг 5 — рекламная сеть.

    В боевом аккаунте она УЖЕ есть: **id 106** — замерено 09.09.2026 по вставкам, все 500
    висят под ней. Заводить её на каждую РК не нужно, это константа аккаунта.

    ⚠ Число 1080, которое видно в кабинете рядом с «SIMB-AD», — это НЕ сеть, а **ad_space**
    (тип Site, внутри сети 106). Совпадение с общим числом ad_space в каталоге (тоже 1080)
    случайно и сбивает с толку — проверено запросом, а не глазами.

    Ручка оставлена для нового аккаунта; метода «получить список сетей» в доке нет, поэтому
    известный id вводится руками на экране.
    """
    c = _client(payload.account_id)
    raw = _run(c.call, "POST", "/advertiser/ad_networks.json", data={"label": payload.label})
    wid = _run(c._created, raw, "сеть")
    _journal("6 · сеть", user, payload.dict(), raw)
    log_action(db, user, "weborama_ad_network", "weborama", None, f"{payload.label} → {wid}")
    return {"label": payload.label, "id": wid, "raw": raw}


class InsertionIn(AccountIn):
    campaign_id: str
    ad_network_id: str
    ad_space_id: str
    campaign_label: str
    domain: str
    channel: str = "Desktop"
    fmt: str = "banner"
    account_label: str = "SIMB-AD"
    # Формат вставки выбирается: от него зависит, ЧЕМ она измеряет.
    #   3 — показы и клики → отдаёт пиксель `a.A=im` (в DSP это поле `pixel`);
    #   4 — плюс видимость → отдаёт js-блок (в DSP это `js_code_audit`).
    # Видимость картинкой 1×1 не измерить, поэтому четвёрка и не даёт URL-пикселя.
    delivery_format_id: int = enums.DEFAULT_DELIVERY_FORMAT


@router.post("/insertion")
def create_insertion(payload: InsertionIn, db: Session = Depends(get_db),
                     user: User = Depends(EDIT)):
    """Шаг 6 — вставка. Она и есть «кампания × площадка», и на ней живёт пиксель.

    Формат — `Impression/Click/Visibility`: видимость и есть причина, по которой
    верификатор подключают.
    """
    # Домен обязателен, и это не придирка к форме. ad_space у нас ОДИН на все размещения
    # (1080 «SIMB-AD»), поэтому «какая это площадка» несёт ТОЛЬКО метка вставки. Без домена
    # метка перестаёт различать площадки: вторая такая же вставка станет неотличимой от
    # первой, и показы двух сайтов сольются в одну строку отчёта.
    #
    # Поймано 09.09.2026 на живой пробе: вставка 567 уехала с меткой
    # `SIMB-AD_banner_Desktop_viferon_F99A73` — без сайта.
    if not naming.domain_of(payload.domain):
        raise HTTPException(
            400, "Не указан домен площадки. У нас один ad_space на все размещения, и "
                 "какая это площадка, говорит только метка вставки — без домена она "
                 "перестаёт их различать")
    label = naming.position_name(
        payload.account_label, payload.fmt,
        naming.row_name(payload.channel, payload.campaign_label, payload.domain))
    c = _client(payload.account_id)
    raw = _run(c.call, "POST", "/advertiser/insertions/placements/json",
               data={"campaign_id": payload.campaign_id,
                     "ad_network_id": payload.ad_network_id,
                     "ad_space_id": payload.ad_space_id,
                     "label": label,
                     "delivery_format_id": int(payload.delivery_format_id)})
    wid = _run(c._created, raw, "вставку")
    _journal("7 · вставка", user, payload.dict(), raw)
    log_action(db, user, "weborama_insertion", "weborama", None, f"{label} → {wid}")
    return {"label": label, "id": wid, "raw": raw,
            "delivery_format": enums.DELIVERY_FORMATS.get(int(payload.delivery_format_id),
                                                          str(payload.delivery_format_id))}


class TagIn(AccountIn):
    insertion_id: str


@router.post("/tag")
def insertion_tag(payload: TagIn, user: User = Depends(VIEW)):
    """Шаг 8 — забрать тег. Ответ отдаём как есть И разобранным.

    В их `js_ru` живут ДВЕ разные ссылки: пиксель показа (`a.A=im`) и счётчик клика
    (`a.A=cl`). Поиск «любого адреса с [RANDOM]» подставлял кликовый вместо показного —
    поймано на живой пробе 09.09.2026. Креатив уехал бы в DSP с кликовым счётчиком на
    месте показного: всё «работает», показы не считаются, видно через месяц по пустым
    отчётам. Поэтому разбираем по `a.A`, а не по виду строки.
    """
    c = _client(payload.account_id)
    raw = _run(c.insertion_tag, payload.insertion_id)
    parsed = tags.parse(raw)
    _journal("8 · тег", user, {"insertion_id": payload.insertion_id},
             {"parsed": parsed, "raw": raw})
    return {"raw": raw, "parsed": parsed,
            "pixel": parsed.get("impression"),
            "warning": None if parsed.get("impression") else
                       "Пикселя показа (a.A=im) в ответе НЕТ — только js-блок с кликовой "
                       "ссылкой. Похоже, так и задумано: формат 4 меряет ВИДИМОСТЬ, а её "
                       "картинкой 1×1 не измерить — показы считает сам скрипт. Пиксель "
                       "a.A=im отдаёт формат 3 (без видимости). Проверяется заведением "
                       "вставки с форматом 3 на шаге 7"}


class AssembleIn(BaseModel):
    """Сборка итогового тега — БЕЗ сети: результат видно до того, как он куда-то уедет."""
    pixel: str
    domain: str
    kind: str = "dsp"
    # Размер баннера: им заменяются ~WIDTH~/~HEIGHT~. Мы его знаем — он объявлен в самом
    # креативе (`ad.size`), поэтому подставляем, а не оставляем макрос ехать в DSP.
    width: Optional[int] = None
    height: Optional[int] = None


@router.post("/assemble")
def assemble(payload: AssembleIn, user: User = Depends(VIEW)):
    """Шаг 8 — подстановка макроса рандомизатора и хвост с адресом площадки."""
    # Кликовый счётчик на месте показного пикселя — тихая беда: тег соберётся, уедет в
    # DSP и не будет считать показы. Отказываем прямо, а не «на всякий случай».
    if tags.ACTION_CLICK in (payload.pixel or ""):
        raise HTTPException(
            400, "Это счётчик КЛИКА (a.A=cl), а не пиксель показа. В поле pixel креатива "
                 "нужен адрес с a.A=im — иначе показы считаться не будут")
    pixel = payload.pixel
    if payload.width is not None and payload.height is not None:
        pixel = tags.fill_size(pixel, payload.width, payload.height)
    try:
        tag = naming.final_tag(pixel, payload.domain, payload.kind)
    except ValueError as e:
        raise HTTPException(400, str(e))
    rest = tags.leftovers(tag)
    out = {"tag": tag, "kind": payload.kind,
           "macro": naming.RANDOM_MACRO[payload.kind.lower()],
           "leftovers": rest,
           "warning": None if not rest else
                      "В теге остались макросы, которых DSP не знает: "
                      + " ".join(rest) +
                      ". Они уедут в счётчик как есть — подставьте размер баннера, а про "
                      "${GDPR}-параметры спросите Weborama: в их же выгрузке Excel их не было"}
    _journal("9 · итоговый тег", user, payload.dict(), out)
    return out


class NamesIn(BaseModel):
    """Предпросмотр имён — тоже без сети. Имена уезжают наружу навсегда, и увидеть их
    до отправки дешевле, чем переименовывать в чужом кабинете."""
    deal_code: str
    brand: str
    month: str
    ident: Optional[str] = None
    domain: str = "example.ru"
    channel: str = "Desktop"
    fmt: str = "banner"
    account_label: str = "SIMB-AD"
    # Формат вставки выбирается: от него зависит, ЧЕМ она измеряет.
    #   3 — показы и клики → отдаёт пиксель `a.A=im` (в DSP это поле `pixel`);
    #   4 — плюс видимость → отдаёт js-блок (в DSP это `js_code_audit`).
    # Видимость картинкой 1×1 не измерить, поэтому четвёрка и не даёт URL-пикселя.
    delivery_format_id: int = enums.DEFAULT_DELIVERY_FORMAT


@router.post("/names")
def preview_names(payload: NamesIn, user: User = Depends(VIEW)):
    try:
        proj = naming.project_label(payload.deal_code, payload.brand, payload.month)
        camp = naming.campaign_label(payload.brand, payload.ident or payload.deal_code)
        pos = naming.position_name(
            payload.account_label, payload.fmt,
            naming.row_name(payload.channel, camp, payload.domain))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"project": proj, "campaign": camp, "insertion": pos}


@router.get("/deals")
def deals_for_demo(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Подсказка для полей: РК месяца с кодом сделки и брендом.

    Экран учебный, но подставлять руками код и бренд — верный способ завести проект под
    опечаткой, а переименовать его в чужом кабинете уже нельзя.
    """
    from app.ad.models import AdCampaign
    from app.sales.models import SalesBrand, SalesDeal

    rows = (db.query(AdCampaign, SalesDeal, SalesBrand)
            .join(SalesDeal, SalesDeal.id == AdCampaign.deal_id)
            .outerjoin(SalesBrand, SalesBrand.id == SalesDeal.brand_id)
            .order_by(AdCampaign.month.desc(), SalesDeal.code)
            .limit(60).all())
    out: List[Dict[str, Any]] = []
    for camp, deal, brand in rows:
        month = camp.month.strftime("%Y-%m") if isinstance(camp.month, date) else None
        out.append({"campaign_id": camp.id, "deal_code": deal.code,
                    "deal_title": deal.title, "brand": brand.name if brand else None,
                    "month": month, "status": camp.status})
    return {"rows": out}
