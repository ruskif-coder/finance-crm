# -*- coding: utf-8 -*-
"""Обход экранов браузером — ступень 1 автоматических проверок (владелец 27.10.2026).

Зачем: код собирается, сервер отдаёт 200, а страница падает в браузере при гидратации — ни pytest, ни сборка, ни curl этого
не видят (так уже падала карточка сделки 13.09.2026). Ручной прогон открывает только то, что правили; соседний экран, сломанный
общим компонентом, не открывает никто. Здесь — каждый экран карты `frontend/lib/nav.data.json`, вкладки настроек
(`components/SettingsTabs.js`) и образцы карточек с номером, под каждой переданной ролью, только тем, что роли разрешено.

Экран считается сломанным, если: упал JS (`pageerror`), в консоли ошибка, API ответил 5xx, на экране «Application error»,
обход выкинуло на страницу входа. Ничего не нажимает и не пишет — только открывает: данные стенда не трогаются.

Запуск — `bash e2e/run.sh [роли…]` (входы выпускает `backend/scripts/e2e_sessions.py`, браузер — образ Playwright)."""
import argparse
import json
import re
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "https://localhost"
CRASH = ("Application error", "Unhandled Runtime Error", "This page could not be found")
# Шум, который не про наш код: отказ в доступе к необязательному запросу у роли без права — экран обязан пережить его сам
NOISE = (re.compile(r"status of 40[13]"), re.compile(r"favicon"), re.compile(r"Download the React DevTools"))
DETAIL = [("deal", "/sales/deals/{}", "sales_registry"), ("mp", "/accounts/mp/{}", "media_plans"),
          ("counterparty", "/directory/counterparties/{}", "counterparties"), ("publisher", "/publishers/{}", "dir_publishers"),
          ("annex", "/directory/annexes/{}", "annexes"), ("contract", "/directory/contracts/{}", "contracts"), ("campaign", "/traffic/campaign/{}", "traffic_dashboard"),
          ("master", "/accounts/master/{}", "master_deals")]


def screens(root: str, samples: dict) -> list:
    """[(адрес, право | None, только админу)] — карта навигации, вкладки настроек, карточки по образцам."""
    nav = json.load(open(f"{root}/frontend/lib/nav.data.json", encoding="utf-8"))
    out = [(it["href"], it.get("perm"), False) for s in nav["sections"] for it in s.get("items", [])]
    src = open(f"{root}/frontend/components/SettingsTabs.js", encoding="utf-8").read()
    for line in src.splitlines():
        m = re.search(r"href: '([^']+)'", line)
        if m:
            perm = re.search(r"perm: '([^']+)'", line)
            out.append((m.group(1), perm.group(1) if perm else None, "adminOnly: true" in line))
    out += [(path.format(samples[k]), perm, False) for k, path, perm in DETAIL if samples.get(k)]
    return list(dict.fromkeys(out))


def allowed(sess: dict, perm, admin_only: bool) -> bool:
    if sess["role"] == "admin":
        return True
    if admin_only:
        return False
    if not perm:
        return True
    return bool(json.loads(sess["storage"]["permissions"]).get(perm, {}).get("view"))


def visit(page, url: str, timeout: int) -> dict:
    errs = []
    on_page = lambda e: errs.append(f"JS: {e}")                                                       # noqa: E731
    on_console = lambda m: (m.type == "error" and not any(n.search(m.text) for n in NOISE)              # noqa: E731
                            and errs.append(f"консоль: {m.text[:300]}"))
    on_resp = lambda r: ("/api/" in r.url and r.status >= 500 and errs.append(f"API {r.status}: {r.url[len(BASE):]}"))  # noqa: E731
    page.on("pageerror", on_page)
    page.on("console", on_console)
    page.on("response", on_resp)
    t0 = time.time()
    try:
        page.goto(BASE + url, wait_until="load", timeout=timeout)
        try:
            page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            errs.append("не затихла сеть за отведённое время")
        page.wait_for_timeout(600)                     # эффекты после первых ответов
        text = page.inner_text("body")
        errs += [f"на экране: {c}" for c in CRASH if c in text]
        if page.url.split("?")[0].rstrip("/").endswith("/login") and not url.startswith("/login"):
            errs.append("выкинуло на страницу входа")
        size = len(text.strip())
    except Exception as e:
        errs.append(f"не открылась: {str(e).splitlines()[0][:200]}")
        size = 0
    finally:
        page.remove_listener("pageerror", on_page)
        page.remove_listener("console", on_console)
        page.remove_listener("response", on_resp)
    return {"url": url, "ok": not errs, "errors": errs, "ms": int((time.time() - t0) * 1000), "text": size}


def walk(sess: dict, items: list, timeout: int, browser) -> list:
    ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 1600, "height": 1000}, locale="ru-RU")
    ctx.add_init_script("(() => { const s = %s; for (const k in s) localStorage.setItem(k, s[k]) })()" % json.dumps(sess["storage"]))
    page = ctx.new_page()
    res = []
    for url, perm, admin_only in items:
        if allowed(sess, perm, admin_only):
            r = visit(page, url, timeout)
            res.append(r)
            print(f"  {'ok ' if r['ok'] else 'ОШИБКА'} {url} ({r['ms']} мс)" + ("" if r["ok"] else "\n      " + "\n      ".join(r["errors"])), flush=True)
    ctx.close()
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/work")
    ap.add_argument("--sessions", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--timeout", type=int, default=25000)
    a = ap.parse_args()
    data = json.load(open(a.sessions, encoding="utf-8"))
    items = screens(a.root, data["samples"])
    report, bad = [], 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for sess in data["sessions"]:
            print(f"\n== {sess['role_label']} ({sess['role']})", flush=True)
            res = walk(sess, items, a.timeout, browser)
            bad += sum(1 for r in res if not r["ok"])
            report.append({"role": sess["role"], "role_label": sess["role_label"], "results": res})
        browser.close()
    json.dump(report, open(a.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    total = sum(len(r["results"]) for r in report)
    print(f"\nИТОГО: открыто {total} экранов под {len(report)} ролями, сломано {bad}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
