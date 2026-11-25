"""Сценарий под ролью Мастер Сейлз: правятся ли цели в «Плане продаж» и статусы продаж.

Смысл: до 25.11.2026 экран спрашивал право двухаргументной формой `can('sales_plan','edit')` и молча
запрещал правку всем, кроме админа. Проверяем наблюдаемое: под role_5 нет подсказки «цели правит роль
с правкой», а по ячейке цели открывается редактор; «Статусы продаж» показывают таблицу.

Сессия подкладывается тем же способом, что в `walk_screens.py` — init-скриптом в localStorage.
"""
import argparse
import json
import sys

from playwright.sync_api import sync_playwright

BASE = "https://localhost"
HINT = "цели правит роль"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    with open(args.sessions, encoding="utf-8") as f:
        data = json.load(f)
    sess = data[0] if isinstance(data, list) else data.get("sessions", [data])[0]
    out = {"role": sess.get("role"), "role_label": sess.get("role_label"), "checks": []}

    def note(name, ok, detail=""):
        out["checks"].append({"check": name, "ok": bool(ok), "detail": detail})

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--ignore-certificate-errors"])
        ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 1600, "height": 1100})
        ctx.add_init_script("(() => { if (window.top !== window) return; const s = %s; "
                            "for (const k in s) localStorage.setItem(k, s[k]) })()"
                            % json.dumps(sess["storage"]))
        page = ctx.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        page.goto(f"{BASE}/sales/plan?year=2026", wait_until="networkidle")
        body = page.inner_text("body").lower()
        note("экран плана открылся", "план" in body or "цел" in body, body[:120].replace("\n", " "))
        note("нет подсказки «цели правит роль с правкой»", HINT not in body,
             "подсказка есть — правка закрыта" if HINT in body else "")

        # Экран по умолчанию открыт в режиме «Выполнение» — цели правятся в режиме «Цели».
        page.get_by_text("Цели", exact=True).first.click()
        page.wait_for_timeout(600)
        body_goals = page.inner_text("body").lower()
        note("в режиме «Цели» нет подсказки «цели правит роль с правкой»", HINT not in body_goals,
             "подсказка есть — правка закрыта" if HINT in body_goals else "")
        # Ячейка цели при праве «правка» — это <input inputmode="decimal"> прямо в таблице;
        # без права вместо поля стоит текст «—». Именно это и различает canEdit.
        fields = page.locator('input[inputmode="decimal"]').count()
        note("цели — редактируемые поля, а не текст", fields > 0, f"полей целей: {fields}")

        page.goto(f"{BASE}/sales/status", wait_until="networkidle")
        body2 = page.inner_text("body").lower()
        note("«Статусы продаж» отдают таблицу", len(body2) > 400, f"текста: {len(body2)}")
        note("ошибок JS нет", not errors, "; ".join(errors[:3]))

        page.screenshot(path=args.report.replace(".json", "_plan.png"))
        browser.close()

    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    bad = [c for c in out["checks"] if not c["ok"]]
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"провалено проверок: {len(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
