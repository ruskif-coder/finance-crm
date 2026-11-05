"""Показы Weborama по «постоянной ссылке» на отчёт — РК с ВНЕШНИМ пикселем (владелец 05.11.2026).

Пиксель ставил не наш аккаунт, API к нему у нас нет (наш съём — `daily.py`, только свои вставки). Клиент делится
ссылкой вида `https://adap-interface.wbrm.ru/<аккаунт>/reportcenter/permalink/link/hash/<ключ>`. Она открывает
гостевой просмотр отчёта: первый запрос ставит сессию и переадресует на отчёт с ФИЛЬТРОМ (кампания × площадка),
а цифры страница берёт JSON-запросом `getlinegraphvalues` — его мы и повторяем за флайт РК.

Границы, которые держим сознательно:
  · фильтр — только тот, что пришёл в переадресации ссылки: этим с нами поделились, другие кампании аккаунта
    не запрашиваем;
  · это внутренний интерфейс их экрана, не API: после их обновления может перестать отвечать — тогда `sync_*`
    возвращает ошибку словами, и она видна в отчёте ночного съёма и у кнопки на экране;
  · показы одной цифрой на день по всему фильтру: у внешнего пикселя вставка обычно одна на всю сеть, поэтому
    строки пишутся БЕЗ площадки — сверка по РК в целом, как у ручного итога (`weborama_manual`).

Источник `weborama_link` — измеритель (`app/ad/stat_sources.py`): в факт не идёт никогда. Если по РК есть его
строки, ручной итог в сверку не складывается — это то же число из того же отчёта (`stat_sources.VERIFIER_SQL`).
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Dict, Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

SOURCE = "weborama_link"
HOST = "adap-interface.wbrm.ru"
_LINK = re.compile(r"^https://adap-interface\.wbrm\.ru/(\d+)/reportcenter/permalink/link/hash/([A-Za-z0-9]+)/?$")
_FILTERS = re.compile(r"/dimension_filters/([^/]+)/")
_DIMS = re.compile(r"/dimensions/([^/]+)/")
_SUB = re.compile(r"/sub_dimension/([^/]+)/")
TIMEOUT = 30.0


class LinkError(Exception):
    """Ссылку нельзя принять или по ней не пришли данные — текст для человека."""


def check_url(url: Optional[str]) -> str:
    """Ссылка их отчётного центра или ошибка. Другое не принимаем: поле — не дверь для запросов с нашего сервера."""
    u = (url or "").strip()
    if not _LINK.match(u):
        raise LinkError("Нужна постоянная ссылка на отчёт Weborama: "
                        f"https://{HOST}/<аккаунт>/reportcenter/permalink/link/hash/<ключ>")
    return u


def filters_from_location(location: str) -> str:
    """Фильтр отчёта из переадресации ссылки: `campaign==121,site_offer==1161`."""
    if "/dimension_filters//" in (location or ""):
        # Отчёт на весь аккаунт: его сумма смешала бы чужие РК (так устроена ссылка 57ULHY/FMRS34, 05.11.2026)
        raise LinkError("Ссылка открывает весь аккаунт Weborama, а не отчёт одной кампании — "
                        "попросите у клиента ссылку на отчёт одной кампании")
    m = _FILTERS.search(location or "")
    if not m or "==" not in m.group(1):
        raise LinkError("Weborama не отдала фильтр отчёта по ссылке — ссылка устарела или отчёт удалён")
    return m.group(1)


def dimensions_from_location(location: str) -> str:
    """Разрезы запроса — РОВНО те, что у ссылки (разрез + подразрез), и день. Свой набор их сервер не принимает:
    «dimensions=>… != … Unauthorized parameters» (проверено 05.11.2026) — гостю открыт только отчёт ссылки."""
    m, sub = _DIMS.search(location or ""), _SUB.search(location or "")
    if not m:
        raise LinkError("Weborama не отдала разрезы отчёта по ссылке — ссылка устарела или отчёт удалён")
    return ",".join([m.group(1)] + ([sub.group(1)] if sub else []) + ["day"])


def parse_days(payload: dict) -> Dict[date, int]:
    """{день: показы} из ответа `getlinegraphvalues` ({items: [{day, insertion}]}). Нулевые дни — тоже замер."""
    out: Dict[date, int] = {}
    for it in (payload or {}).get("items") or []:
        try:
            out[date.fromisoformat(str(it["day"])[:10])] = int(float(it.get("insertion") or 0))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def probe(url: str) -> str:
    """Открыть ссылку и проверить, что это отчёт ОДНОЙ кампании, — до сохранения (05.11.2026): иначе неверная ссылка
    лежала бы в РК и роняла ночной съём каждую ночь. Возвращает фильтр отчёта или LinkError словами."""
    u = check_url(url)
    try:
        r = httpx.get(u, timeout=TIMEOUT, follow_redirects=False, headers={"User-Agent": "Mozilla/5.0"})
    except httpx.HTTPError as e:
        raise LinkError(f"Weborama не ответила по ссылке: {e.__class__.__name__}")
    if r.status_code not in (301, 302, 303) or not r.headers.get("location"):
        raise LinkError(f"Ссылка не открыла отчёт (ответ {r.status_code}) — устарела или закрыта")
    loc = r.headers["location"]
    dimensions_from_location(loc)
    return filters_from_location(loc)


def fetch(url: str, start: date, end: date, client: Optional[httpx.Client] = None) -> Dict[date, int]:
    """Суточные показы по ссылке за [start, end]. Сессию ставит сама ссылка; фильтр — из её переадресации."""
    u = check_url(url)
    account = _LINK.match(u).group(1)
    own = client is None
    cl = client or httpx.Client(timeout=TIMEOUT, follow_redirects=False,
                                headers={"X-Requested-With": "XMLHttpRequest", "User-Agent": "Mozilla/5.0"})
    try:
        try:
            r = cl.get(u)
        except httpx.HTTPError as e:
            raise LinkError(f"Weborama не ответила по ссылке: {e.__class__.__name__}")
        if r.status_code not in (301, 302, 303) or not r.headers.get("location"):
            raise LinkError(f"Ссылка не открыла отчёт (ответ {r.status_code}) — устарела или закрыта")
        loc = r.headers["location"]
        filters = filters_from_location(loc)
        api = (f"https://{HOST}/{account}/reportcenter/reporting/getlinegraphvalues/compute_subdimension/false/"
               f"search_dimension//dimensions/{dimensions_from_location(loc)}/dimension_filters/{filters}/graph_mode/total/"
               f"time_unit/day/metrics/impression/start_date/{start.isoformat()}/end_date/{end.isoformat()}/"
               f"quick_search_filter//guest/1")
        try:
            d = cl.get(api, params={"page": 1, "start": 0, "limit": 400})
            payload = d.json() if d.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            payload = None
        if not isinstance(payload, dict) or "items" not in payload:
            raise LinkError("Weborama не отдала показы по ссылке — их интерфейс мог измениться")
        return parse_days(payload)
    finally:
        if own:
            cl.close()


def store(db: Session, campaign_id: int, days: Dict[date, int]) -> int:
    """Одна строка на день без площадки; перезабор дня заменяет число, а не прибавляет."""
    for d, n in days.items():
        db.execute(text(
            "INSERT INTO ad_campaign_stat (campaign_id, placement_id, date, shows, clicks, source) "
            "VALUES (:c, NULL, :d, :n, 0, :s) "
            "ON CONFLICT ON CONSTRAINT uq_ad_stat DO UPDATE SET shows = EXCLUDED.shows, imported_at = now()"),
            {"c": campaign_id, "d": d, "n": int(n), "s": SOURCE})
    return len(days)


def clear(db: Session, campaign_id: int) -> None:
    """Ссылку убрали — её строки тоже: иначе устаревшие показы остались бы в сверке навсегда."""
    db.execute(text("DELETE FROM ad_campaign_stat WHERE campaign_id = :c AND source = :s"),
               {"c": campaign_id, "s": SOURCE})


def window(c, today: Optional[date] = None) -> Optional[tuple]:
    """Отрезок забора: флайт РК до вчера (день ещё идёт — его число неполное). Не стартовала — None."""
    today = today or date.today()
    if not c.date_start or c.date_start >= today:
        return None
    return c.date_start, min(c.date_end or today, today - timedelta(days=1))


def sync_campaign(db: Session, c, client: Optional[httpx.Client] = None, today: Optional[date] = None) -> dict:
    """Снять и записать одну РК. Ошибка — словами в ответе, без исключения: ночной проход идёт дальше."""
    if not c.wr_report_url:
        return {"campaign_id": c.id, "ok": False, "error": "ссылки на отчёт нет"}
    w = window(c, today)
    if w is None:
        return {"campaign_id": c.id, "ok": True, "days": 0, "shows": 0, "note": "РК ещё не стартовала"}
    try:
        days = fetch(c.wr_report_url, w[0], w[1], client)
    except LinkError as e:
        return {"campaign_id": c.id, "ok": False, "error": str(e)}
    store(db, c.id, days)
    db.commit()
    return {"campaign_id": c.id, "ok": True, "days": len(days), "shows": sum(days.values()),
            "last_day": max(days).isoformat() if days else None}


def sync_all(db: Session, today: Optional[date] = None) -> dict:
    """Ночной проход: РК со ссылкой, которые идут или кончились за последнюю неделю (их отчёт ещё дописывается)."""
    from app.ad.models import AdCampaign

    today = today or date.today()
    cs = (db.query(AdCampaign).filter(AdCampaign.wr_report_url.isnot(None), AdCampaign.date_start.isnot(None),
                                      AdCampaign.date_start < today,
                                      (AdCampaign.date_end.is_(None)) | (AdCampaign.date_end >= today - timedelta(days=7)))
          .order_by(AdCampaign.id).all())
    res = []
    with httpx.Client(timeout=TIMEOUT, follow_redirects=False,
                      headers={"X-Requested-With": "XMLHttpRequest", "User-Agent": "Mozilla/5.0"}) as cl:
        for c in cs:
            cl.cookies.clear()            # своя гостевая сессия на каждую ссылку
            res.append(sync_campaign(db, c, cl, today))
    return {"campaigns": len(res), "ok": sum(1 for r in res if r["ok"]),
            "failed": [r for r in res if not r["ok"]], "shows": sum(r.get("shows") or 0 for r in res)}


def state(db: Session, campaign_id: int) -> dict:
    """Для экрана: последний снятый день и когда снимали — «ссылка есть, а данных нет» видно сразу."""
    r = db.execute(text("SELECT max(date) AS last_day, max(imported_at) AS at, sum(shows) AS shows "
                        "FROM ad_campaign_stat WHERE campaign_id = :c AND source = :s"),
                   {"c": campaign_id, "s": SOURCE}).mappings().first()
    return {"last_day": r["last_day"].isoformat() if r and r["last_day"] else None,
            "synced_at": r["at"].isoformat() if r and r["at"] else None, "shows": int(r["shows"] or 0) if r else 0}
