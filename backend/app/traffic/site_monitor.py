# -*- coding: utf-8 -*-
"""Доступность сайтов площадок (владелец 30.09.2026).

Перенос внешнего скрипта трафика (`downbot.py`) внутрь системы: он жил вне контура, со
своими доступами в файле и своим ботом. Теперь:

* СПИСОК — не из конфига, а из реестра: все web-поверхности площадок не в архиве,
  `site_check <> 'off'`; плюс «доп. сайты» из настроек (`site_monitor_extra`) — наши
  подключённые сайты вне реестра. Строка настройки: адрес и, через пробел, `browser`.
* ПРОВЕРКА — как в скрипте: обычный запрос с браузерными заголовками и повторами; при
  ответе 401/403 (похоже на антибот) или при режиме `browser` — настоящий браузер
  PDF-сервиса (`/probe`). Итог: ok | antibot | down. Антибот — только на экране, тревоги
  нет (владелец 30.09.2026): сайт для людей открывается, режется лишь робот.
* ТРЕВОГА — на СМЕНЕ состояния, не каждый час: `site_down` при падении, `site_recovered`
  при восстановлении. Через наш модуль уведомлений (бот + панель), адресаты — в реестре.
* ИСТОРИЯ — `site_checks`, 30 дней; текущее состояние = последняя строка адреса.

Запуск кроном раз в час: `python -m app.traffic.site_monitor`.
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.sales.models import PUBLISHER_ARCHIVE_STATUS

log = logging.getLogger("finance.site_monitor")

OK, ANTIBOT, DOWN = "ok", "antibot", "down"
SETTING_EXTRA = "site_monitor_extra"
SETTING_DSP_EXCLUDE = "site_monitor_dsp_exclude"
PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "http://pdf:3001")
KEEP_DAYS = 30
ANTIBOT_CODES = (401, 403)
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
}


def site_url(domain: str) -> Optional[str]:
    """Домен площадки → адрес проверки. Кириллический домен кодируется в punycode."""
    d = (domain or "").strip().lower()
    if not d:
        return None
    if "://" in d:
        d = d.split("://", 1)[1]
    d = d.split("/", 1)[0]
    try:
        d = d.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    return f"https://{d}"


def _setting(db: Session, key: str) -> str:
    return db.execute(text("SELECT value FROM company_settings WHERE key = :k"),
                      {"k": key}).scalar() or ""


def extra_sites(db: Session) -> List[dict]:
    """Доп. сайты из настроек: [{url, mode}]."""
    out = []
    for line in _setting(db, SETTING_EXTRA).splitlines():
        parts = line.split()
        if not parts or parts[0].startswith("#"):   # «# адрес» — сайт выключен из проверки
            continue
        url = site_url(parts[0])
        if url:
            out.append({"url": url, "mode": "browser" if "browser" in parts[1:] else "http",
                        "publisher_id": None, "name": parts[0].split("://")[-1]})
    return out


def targets(db: Session) -> List[dict]:
    """Что проверяем: web-поверхности площадок реестра не в архиве (владелец 30.09.2026)
    + доп. сайты. Отметка «работаем» не нужна: пингуем все наши подключённые сайты."""
    rows = db.execute(text("""
        SELECT DISTINCT ON (p.id) p.id, p.name, p.domain, s.site_check
          FROM sales_publisher_surfaces s JOIN sales_publishers p ON p.id = s.publisher_id
         WHERE s.kind = 'web' AND s.site_check <> 'off'
           AND p.status <> :arch AND coalesce(p.domain, '') <> ''
         ORDER BY p.id, (s.site_check = 'browser') DESC
    """), {"arch": PUBLISHER_ARCHIVE_STATUS}).mappings().all()
    out, seen = [], set()
    for r in rows:
        url = site_url(r["domain"])
        if url and url not in seen:
            seen.add(url)
            out.append({"url": url, "mode": r["site_check"], "publisher_id": r["id"],
                        "name": r["name"]})
    for e in extra_sites(db):
        if e["url"] not in seen:
            seen.add(e["url"])
            out.append(e)
    return out


def _http(url: str) -> dict:
    """Обычный запрос с повторами; сеть/таймаут — исключение наружу."""
    last = None
    for _ in range(3):
        try:
            with httpx.Client(headers=HEADERS, follow_redirects=True,
                              timeout=httpx.Timeout(30.0, connect=10.0)) as c:
                r = c.get(url)
            if r.status_code in (429, 500, 502, 503, 504):
                last = r
                continue
            return {"http_status": r.status_code, "final_url": str(r.url)}
        except httpx.HTTPError as e:
            last = e
    if isinstance(last, httpx.Response):
        return {"http_status": last.status_code, "final_url": str(last.url)}
    raise last


def _browser(url: str) -> dict:
    r = httpx.post(f"{PDF_SERVICE_URL}/probe", json={"url": url}, timeout=75.0)
    r.raise_for_status()
    return r.json()


def check(url: str, mode: str = "http", http=_http, browser=_browser) -> dict:
    """Одна проверка → {status, http_status, method, final_url, message}."""
    need_browser = mode == "browser"
    if not need_browser:
        try:
            r = http(url)
            code = r["http_status"]
            if code < 400:
                return {"status": OK, "http_status": code, "method": "http",
                        "final_url": r["final_url"], "message": f"HTTP {code}"}
            if code not in ANTIBOT_CODES:
                return {"status": DOWN, "http_status": code, "method": "http",
                        "final_url": r["final_url"], "message": f"HTTP {code}"}
        except Exception as e:  # noqa: BLE001 — любая сетевая беда = повод спросить браузер
            log.info("site_monitor %s: запрос не прошёл (%s) — пробую браузером", url, e)
    try:
        b = browser(url)
    except Exception as e:  # noqa: BLE001
        return {"status": DOWN, "http_status": None, "method": "browser", "final_url": url,
                "message": f"браузер недоступен: {str(e)[:250]}"}
    code = b.get("status")
    if code is None:
        return {"status": DOWN, "http_status": None, "method": "browser", "final_url": url,
                "message": (b.get("error") or "нет ответа")[:300]}
    if code < 400:
        return {"status": OK if need_browser else ANTIBOT, "http_status": code,
                "method": "browser", "final_url": b.get("final_url") or url,
                "message": (f"браузер {code}" if need_browser
                            else f"простой запрос режется, браузер {code}")}
    if code in ANTIBOT_CODES:
        return {"status": ANTIBOT, "http_status": code, "method": "browser",
                "final_url": b.get("final_url") or url,
                "message": f"антибот режет и браузер ({code})"}
    return {"status": DOWN, "http_status": code, "method": "browser",
            "final_url": b.get("final_url") or url, "message": f"браузер HTTP {code}"}


def latest(db: Session) -> dict:
    """{url: последняя проверка} + с какого момента в текущем статусе и сколько подряд."""
    rows = db.execute(text("""
        SELECT DISTINCT ON (url) url, publisher_id, checked_at, status, http_status, method,
               final_url, message
          FROM site_checks ORDER BY url, checked_at DESC, id DESC
    """)).mappings().all()
    out = {r["url"]: dict(r) for r in rows}
    if not out:
        return out
    since = db.execute(text("""
        SELECT c.url, min(c.checked_at) AS since, count(*) AS streak
          FROM site_checks c
          JOIN (SELECT DISTINCT ON (url) url, status FROM site_checks
                 ORDER BY url, checked_at DESC, id DESC) l ON l.url = c.url
         WHERE c.checked_at > coalesce((SELECT max(x.checked_at) FROM site_checks x
                                         WHERE x.url = c.url AND x.status <> l.status),
                                        'epoch'::timestamptz)
         GROUP BY c.url""")).mappings().all()
    for s in since:
        if s["url"] in out:
            out[s["url"]].update(since=s["since"], streak=s["streak"])
    return out


def history(db: Session, hours: int = 24) -> dict:
    """{url: [статусы за последние N проверок, старые слева]} — полоска на экране."""
    rows = db.execute(text("""
        SELECT url, status FROM (
          SELECT url, status, checked_at,
                 row_number() OVER (PARTITION BY url ORDER BY checked_at DESC) AS n
            FROM site_checks) x
         WHERE n <= :h ORDER BY url, checked_at"""), {"h": hours}).all()
    out: dict = {}
    for url, st in rows:
        out.setdefault(url, []).append(st)
    return out


def _notify(db: Session, t: dict, prev: Optional[dict], res: dict) -> None:
    """Тревога на СМЕНЕ: упал / поднялся. Антибот — без тревоги (владелец 30.09.2026)."""
    from app.notify.bus import emit
    was = (prev or {}).get("status")
    name = t["name"] or t["url"]
    if res["status"] == DOWN and was != DOWN:
        emit(db, "site_down", title=f"Сайт недоступен · {name}",
             body=f"{t['url']} — {res['message']}", link="/traffic/catalog",
             entity_type="sales_publisher", entity_id=t.get("publisher_id"), tone="bad")
    elif was == DOWN and res["status"] != DOWN:
        emit(db, "site_recovered", title=f"Сайт снова доступен · {name}",
             body=f"{t['url']} — {res['message']}", link="/traffic/catalog",
             entity_type="sales_publisher", entity_id=t.get("publisher_id"), tone="ok")


def run(db: Session, only_url: Optional[str] = None, http=_http, browser=_browser,
        notify: bool = True) -> dict:
    """Проверить всё (или один адрес), записать историю, разослать тревоги на смене."""
    prev = latest(db)
    counts = {OK: 0, ANTIBOT: 0, DOWN: 0}
    for t in targets(db):
        if only_url and t["url"] != only_url:
            continue
        res = check(t["url"], t["mode"], http=http, browser=browser)
        counts[res["status"]] += 1
        db.execute(text("""
            INSERT INTO site_checks (url, publisher_id, checked_at, status, http_status,
                                     method, final_url, message)
            VALUES (:u, :p, clock_timestamp(), :s, :h, :m, :f, :msg)"""),
            {"u": t["url"], "p": t.get("publisher_id"), "s": res["status"],
             "h": res["http_status"], "m": res["method"], "f": res["final_url"],
             "msg": res["message"]})
        db.commit()
        if notify:
            try:
                _notify(db, t, prev.get(t["url"]), res)
                db.commit()
            except Exception:  # noqa: BLE001 — сбой рассылки проверку не отменяет
                db.rollback()
                log.exception("site_monitor: тревога по %s не ушла", t["url"])
    db.execute(text("DELETE FROM site_checks WHERE checked_at < :t"),
               {"t": datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)})
    db.commit()
    return counts


def down_publishers(db: Session) -> set:
    """Площадки, чей сайт СЕЙЧАС недоступен — для алерта в конвейере согласования."""
    return {r["publisher_id"] for r in latest(db).values()
            if r["status"] == DOWN and r.get("publisher_id")}


def main() -> None:
    import app.main  # noqa: F401 — все модели в реестре SQLAlchemy
    from app.database import SessionLocal
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        print("site_monitor:", run(db))
        try:
            print("dsp_missing:", dsp_missing(db))
        except Exception:  # noqa: BLE001 — сбой DSP не отменяет проверку сайтов
            db.rollback()
            log.exception("site_monitor: проверка пропавших из показов DSP не удалась")
    finally:
        db.close()



# ── Пропали из показов DSP (вторая часть скрипта трафика) ─────────────────────
# Сайты, у которых вчера были показы, а сегодня нет. Статистика по сайтам есть только в
# админ-кабинете DSP (вход по логину и паролю), а не в нашем партнёрском API по токену —
# поэтому доступы отдельные и лежат в `.env` сервера. Без них проверка честно говорит
# «не настроено» и ничего не шлёт.
SETTING_DSP_STATE = "site_monitor_dsp_missing"
DSP_ENV = ("DSP_ADMIN_API_URL", "DSP_ADMIN_LOGIN", "DSP_ADMIN_PASSWORD")


def dsp_configured() -> bool:
    return all(os.getenv(k) for k in DSP_ENV)


def _dsp_rpc(client: httpx.Client, url: str, method: str, params: dict, rid: int) -> dict:
    r = client.post(url, json={"jsonrpc": "2.0", "method": method, "params": params, "id": rid})
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(f"{method}: {data['error']}")
    return data.get("result")


def _sites_with_shows(client, url, day) -> set:
    items = _dsp_rpc(client, url, "platform.getStatistics", {"filter": {
        "date_from": day.isoformat(), "date_to": day.isoformat(), "main_group": ["site"]}}, 2) or []
    out = set()
    for it in items:
        try:
            shows = int(it.get("shows") or 0)
        except (TypeError, ValueError):
            shows = 0
        if it.get("site") and shows > 0:
            out.add(it["site"])
    return out


def _domain(site: str) -> str:
    from urllib.parse import urlparse
    s = site if "://" in site else "http://" + site
    return (urlparse(s).hostname or "").lower()


def dsp_missing(db: Session, fetch=None, notify: bool = True) -> dict:
    """Сравнить сайты с показами вчера и сегодня; тревога — при смене списка пропавших."""
    import json
    from datetime import date
    if fetch is None:
        if not dsp_configured():
            return {"configured": False}
        url, login, password = (os.getenv(k) for k in DSP_ENV)

        def fetch(day):
            with httpx.Client(timeout=60.0) as c:
                tok = (_dsp_rpc(c, url, "user.auth", {"login": login, "password": password}, 1)
                       or {}).get("access_token")
                if not tok:
                    raise RuntimeError("DSP: в ответе на вход нет токена")
                c.headers["Authorization"] = f"Bearer {tok}"
                return _sites_with_shows(c, url, day)
    today = date.today()
    prev_sites, cur_sites = fetch(today - timedelta(days=1)), fetch(today)
    exclude = {x.strip().lower() for x in _setting(db, SETTING_DSP_EXCLUDE).splitlines() if x.strip()}
    missing = sorted(s for s in prev_sites - cur_sites if _domain(s) not in exclude)
    try:
        was = json.loads(_setting(db, SETTING_DSP_STATE) or "{}").get("missing", [])
    except ValueError:
        was = []
    state = {"missing": missing, "checked_at": datetime.now(timezone.utc).isoformat(),
             "day": today.isoformat()}
    db.execute(text("INSERT INTO company_settings (key, value) VALUES (:k, :v) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"),
               {"k": SETTING_DSP_STATE, "v": json.dumps(state, ensure_ascii=False)})
    db.commit()
    if notify and missing != was:
        from app.notify.bus import emit
        if missing:
            emit(db, "dsp_sites_missing", title=f"Сайты пропали из показов DSP · {len(missing)}",
                 body="Вчера были показы, сегодня нет: " + ", ".join(missing),
                 link="/traffic/catalog", tone="warn")
        elif was:
            emit(db, "dsp_sites_missing", title="Показы DSP восстановились",
                 body="Все сайты со вчерашними показами снова крутятся.",
                 link="/traffic/catalog", tone="ok")
        db.commit()
    return {"configured": True, **state}


def dsp_state(db: Session) -> dict:
    import json
    try:
        st = json.loads(_setting(db, SETTING_DSP_STATE) or "{}")
    except ValueError:
        st = {}
    return {"configured": dsp_configured(), **st}


if __name__ == "__main__":
    main()
