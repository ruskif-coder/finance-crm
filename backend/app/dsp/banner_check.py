# -*- coding: utf-8 -*-
"""Проверка баннера в браузере после заливки в DSP (владелец 15.11.2026).

Зачем. Клиенты жаловались, что на показах не видно ЕРИД: с 14.10 по 09.11 наша растяжка ссылки клика ложилась поверх
плашки «Реклама», и узнали мы об этом от клиентов. Теперь каждый креатив, залитый в DSP, проверяется тем, что видит
человек на площадке: плашка «Реклама» видна и сверху, клик по ней раскрывает ЕРИД и не уводит, клик по баннеру ведёт на
посадочную, скрипт видимости в разметке ровно один.

Как. `enqueue` ставит креатив в очередь сразу после `Creative.edit` (выгрузка РК, `provision`), сама заливка не ждёт.
Крон (`python -m app.dsp.banner_check`) берёт очередь, читает разметку из DSP — ту, что она и показывает, со всеми
правками загрузчика, — и отдаёт её браузеру сайдкара (`pdf-service`, ручка `/banner-check`). Каждый показ — в чистом окне.

Что при провале (владелец 15.11.2026): значок ✗ у креатива на дашборде трафика и уведомление трафику; запуск НЕ
блокируется. Сайдкар не ответил — креатив остаётся в очереди до следующего прогона.
"""
import app.model_registry  # noqa: F401 — крон отдельным процессом: все модели для внешних ключей
import hashlib
import logging
import os
import re
import sys
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dsp.banner_check_models import DspBannerCheck
from app.dsp.creatives import viewability_count

log = logging.getLogger("finance.dsp")

PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "http://pdf:3001")
SIZES = [[300, 600], [970, 250]]
RENDER_TIMEOUT = 150.0          # два показа: загрузка до 45 с + ожидание стилей плашки до 15 с + анимация
DEFAULT_LIMIT = 20              # креативов за прогон: ~30 с на креатив, прогон укладывается в интервал крона
_SRC_RE = re.compile(r"\bsrc=[\"'](https?://[^\"']+)[\"']", re.I)


class BannerCheckError(RuntimeError):
    """Проверить не получилось (сайдкар, DSP) — креатив остаётся в очереди."""


def html_hash(html: str) -> str:
    return hashlib.sha256((html or "").encode("utf-8")).hexdigest()


def enqueue(db: Session, creative_id: int) -> None:
    """Креатив залит или перезалит — в очередь. Прошлый итог стирается: он про другую разметку."""
    db.execute(text(
        "INSERT INTO dsp_banner_check (creative_id) VALUES (:c) "
        "ON CONFLICT (creative_id) DO UPDATE SET checked_at = NULL, ok = NULL, problems = NULL"), {"c": creative_id})
    db.commit()


def request_rules(viewability_src: str, creative_scripts: list) -> dict:
    """Что браузеру грузить, а что резать, — из настроек, а не из кода (имя поставщика в репозиторий не пишем).

    Скрипт видимости пропускаем — он рисует плашку; остальной его домен режем — там маяки. Хосты наших счётчиков режем:
    счётчик открывает скрытые фреймы с чужими рекламными блоками, проверочный показ не должен их дёргать."""
    src = (viewability_src or "").strip()
    host = (urlparse(src).hostname or "").lower()
    parts = host.split(".")
    block_hosts = []
    for tag in creative_scripts:
        for url in _SRC_RE.findall(tag or ""):
            h = (urlparse(url).hostname or "").lower()
            if h and h not in block_hosts:
                block_hosts.append(h)
    return {"allow_urls": [src] if src else [], "block_domain": ".".join(parts[-2:]) if len(parts) >= 2 else "",
            "block_hosts": block_hosts}


def _rules_from_settings(db: Session) -> dict:
    from app.dsp.config import creative_script, viewability_src
    return request_rules(viewability_src(db), [creative_script(db, True), creative_script(db, False)])


def render(html: str, erid: str, opts: dict) -> dict:
    """Замер в браузере сайдкара: {размер: сырые признаки}. Решение — в `problems_of`."""
    try:
        r = httpx.post(f"{PDF_SERVICE_URL}/banner-check", json={"html": html, "erid": erid or "", "sizes": SIZES, **opts},
                       timeout=RENDER_TIMEOUT)
    except httpx.HTTPError as e:
        raise BannerCheckError(f"сайдкар не ответил: {e}") from e
    if r.status_code != 200:
        raise BannerCheckError(f"сайдкар ответил {r.status_code}: {r.text[:200]}")
    return (r.json() or {}).get("sizes") or {}


def _size_problems(v: dict) -> list:
    if v.get("error"):
        return [f"не отрисовался: {v['error']}"]
    out = []
    if not v.get("plaque"):
        out.append("нет плашки «Реклама»")
    elif not v.get("plaque_on_top"):
        out.append(f"плашка «Реклама» перекрыта ({v.get('cover') or '?'})")
    else:
        if not v.get("erid_shown"):
            out.append("клик по плашке не раскрывает ЕРИД")
        if v.get("plaque_click_navigates"):
            out.append("клик по плашке уводит на посадочную")
    if not (v.get("center_ok") or _is_sdk_click(v.get("center_href"))):
        out.append("клик по баннеру не ведёт на посадочную")
    return out


def _is_sdk_click(href) -> bool:
    """Диплинк SDK приложения — правильная ссылка клика у app-площадок в режиме «sdk» (`pub_rules`): подставляется вторым
    шагом выгрузки, клик ведёт в приложение, DSP считает его по `{LINK_ESC}`. Без макроса клик не посчитается — не годится."""
    return isinstance(href, str) and href.startswith("deeplink+://") and "{LINK_ESC}" in href


def problems_of(sizes: dict, html: str) -> dict:
    """Слова проблем: {размер | «разметка»: [что не так]}. Пусто — проверка пройдена."""
    out = {}
    n = viewability_count(html)
    if n != 1:
        out["разметка"] = ["нет скрипта видимости" if n == 0 else f"скриптов видимости {n}, нужен один"]
    for size, v in (sizes or {}).items():
        p = _size_problems(v or {})
        if p:
            out[size] = p
    return out


def _queue(db: Session, limit: int, only: Optional[list]) -> list:
    return db.execute(text(
        "SELECT b.id, b.creative_id, c.ms_creative_xxhash AS xxhash, c.erid, c.ms_title, c.campaign_id "
        "  FROM dsp_banner_check b JOIN ad_campaign_creative c ON c.id = b.creative_id "
        " WHERE b.checked_at IS NULL AND coalesce(c.ms_creative_xxhash, '') <> '' "
        "   AND (CAST(:only AS integer[]) IS NULL OR b.creative_id = ANY(:only)) "
        " ORDER BY b.id LIMIT :n"), {"n": limit, "only": only}).mappings().all()


def _notify(db: Session, row, problems: dict) -> None:
    from app.notify import bus
    from app.routers.traffic_dashboard import rk_label
    lines = [f"{k}: {'; '.join(v)}" for k, v in problems.items()]
    try:
        bus.emit(db, "dsp_banner_check_failed",
                 title=f"Баннер в DSP не прошёл проверку: {row['ms_title'] or row['xxhash']} · {rk_label(db, row['campaign_id'])}",
                 body="Проверка показа в браузере: " + " · ".join(lines) + ". Запуск не заблокирован — креатив крутится.",
                 link=f"/traffic/dashboard?rk={row['campaign_id']}", entity_type="ad_campaign_creative",
                 entity_id=row["creative_id"])
    except Exception:  # noqa: BLE001 — уведомление справка, итог проверки уже записан
        log.exception("уведомление о проверке баннера cr%s не отправлено", row["creative_id"])


def _check_one(db: Session, c, row, opts: dict) -> dict:
    try:
        info = c.creative_get_info(row["xxhash"]) or {}
    except Exception as e:  # noqa: BLE001 — DSP не ответила: пусть повторит следующий прогон
        raise BannerCheckError(f"DSP не отдала креатив: {e}") from e
    html = (info.get("data") or {}).get("html_code") or ""
    if not html.strip():
        return {"html": html, "problems": {"разметка": ["пустая разметка в DSP"]}}
    return {"html": html, "problems": problems_of(render(html, row["erid"] or "", opts), html)}


def run(db: Session, client=None, limit: int = DEFAULT_LIMIT, only: Optional[list] = None) -> dict:
    rep = {"checked": 0, "bad": 0, "failed": 0}
    rows = _queue(db, limit, only)
    if not rows:
        return rep
    opts = _rules_from_settings(db)
    if client is None:
        from app.dsp.client import MsClient
        client = MsClient()
    for row in rows:
        try:
            res = _check_one(db, client, row, opts)
        except BannerCheckError as e:
            rep["failed"] += 1
            log.warning("проверка баннера cr%s отложена: %s", row["creative_id"], e)
            continue
        problems = res["problems"]
        rec = db.get(DspBannerCheck, row["id"])
        rec.html_hash = html_hash(res["html"])
        rec.checked_at = datetime.utcnow()
        rec.ok = not problems
        rec.problems = problems or None
        db.commit()
        rep["checked"] += 1
        if problems:
            rep["bad"] += 1
            _notify(db, row, problems)
    return rep


def state_of(db: Session, creative_ids: list) -> dict:
    """Для экранов: {creative_id: {"state": "ok"|"bad"|"queued", "problems", "checked_at"}}."""
    if not creative_ids:
        return {}
    rows = db.execute(text("SELECT creative_id, checked_at, ok, problems FROM dsp_banner_check WHERE creative_id = ANY(:i)"),
                      {"i": list(creative_ids)}).mappings().all()
    return {r["creative_id"]: {"state": "queued" if r["checked_at"] is None else ("ok" if r["ok"] else "bad"),
                               "problems": r["problems"], "checked_at": r["checked_at"]} for r in rows}


def main(argv=None) -> int:
    from app.database import SessionLocal
    argv = list(sys.argv[1:] if argv is None else argv)
    limit = next((int(a.split("=", 1)[1]) for a in argv if a.startswith("--limit=")), DEFAULT_LIMIT)
    from app.ext_lock import BANNER_CHECK, only_one

    class _Busy(RuntimeError):
        pass
    db = SessionLocal()
    try:
        # Прогон длиннее интервала крона (сайдкар медленный) — второй не стартует поверх первого.
        with only_one(BANNER_CHECK, 0, _Busy, "Проверка баннеров", "сейчас"):
            rep = run(db, limit=limit)
        print(f"проверка баннеров: проверено {rep['checked']}, с проблемами {rep['bad']}, отложено {rep['failed']}")
        return 0
    except _Busy as e:
        print(f"проверка баннеров пропущена: {e}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
