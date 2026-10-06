# -*- coding: utf-8 -*-
"""Разнести посадочные на веб и ссылку в приложении (владелец 06.10.2026).

  advertiser_url — ВСЕГДА веб; deeplink_url — ссылка в приложении.

Что переносится (`pub_rules.split_landing`):
  * диплинк SDK `deeplink+://…` в посадочной → в deeplink_url, его primaryUrl → в посадочную;
  * «https://… веб storefront://…» одной строкой (так вписывали у kuper) → по частям;
  * app-пара с одной веб-ссылкой → та же ссылка и во второе поле (ревью 06.10.2026).
deeplink_url, уже заполненный, не перезаписывается.

    docker exec finance_backend python -m scripts.2026-10-06_split_app_links           # показать
    docker exec finance_backend python -m scripts.2026-10-06_split_app_links --apply   # записать
Повторный запуск ничего не меняет.
"""
import re
import sys
from typing import Optional

from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.audit import log_action
from app.database import SessionLocal
from app.launch_prep.pub_rules import split_landing


def plan_row(adv: Optional[str], dl: Optional[str], surface: Optional[str]):
    """Что сделать со строкой → None (ничего) или (веб, приложение, причина пропуска).

    Ревью 06.10.2026: app-пара с одной веб-ссылкой получает её же во второе поле — иначе
    после выкладки она откатилась бы с «есть» на «запрошена» (ссылки могут совпадать,
    владелец). Второе поле уже занято ДРУГОЙ ссылкой — конфликт, не перезапись."""
    adv = (adv or "").strip()
    dl = (dl or "").strip() or None
    if not adv:
        return None
    if re.match(r"^https?://\S+$", adv, re.I):
        return (adv, adv, None) if surface == "app" and not dl else None
    web, app = split_landing(adv)
    if not web:
        return None, None, "веб-ссылку не вынуть — оставлено как есть, поправить руками"
    if dl and app and dl != app:
        return web, dl, f"конфликт: во втором поле уже другая ссылка ({dl[:60]}) — пропущено"
    return web, dl or app or (web if surface == "app" else None), None


def run(apply: bool) -> list:
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT m.id, d.code, sp.name, s.no, t.surface_kind, m.advertiser_url, m.deeplink_url
              FROM launch_prep_set_target m
              JOIN launch_prep_target t ON t.id = m.target_id
              JOIN sales_publishers sp ON sp.id = t.publisher_id
              JOIN launch_prep_creative_set s ON s.id = m.set_id
              JOIN sales_deals d ON d.id = s.deal_id
             WHERE m.advertiser_url IS NOT NULL
             ORDER BY m.id""")).mappings().all()
        out = []
        for r in rows:
            p = plan_row(r["advertiser_url"], r["deeplink_url"], r["surface_kind"])
            if p is None:
                continue
            web, app, why = p
            out.append((r, web, app, why))
            if apply and not why:
                db.execute(text("UPDATE launch_prep_set_target SET advertiser_url = :w, "
                                "deeplink_url = :a WHERE id = :i"),
                           {"w": web, "a": app, "i": r["id"]})
        moved = sum(1 for x in out if not x[3])
        if apply and moved:
            db.commit()
            log_action(db, None, "split_app_links", "launch_prep_set_target", None,
                       f"посадочные разнесены на веб и ссылку в приложении: {moved} строк")
        return out
    finally:
        db.close()


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    res = run(apply)
    for r, web, app, why in res:
        print(f"{r['code']} · {r['name']} · №{r['no']} (строка {r['id']}):")
        print(f"    было:  {r['advertiser_url'][:110]}")
        if why:
            print(f"    {why}")
        else:
            print(f"    веб:   {web[:110]}")
            print(f"    прил.: {(app or '—')[:110]}")
    ok = sum(1 for x in res if not x[3])
    print(f"{'ЗАПИСАНО' if apply else 'ПОКАЗ (без --apply ничего не записано)'}: строк {ok}"
          f"{f', пропущено с причиной: {len(res) - ok}' if len(res) - ok else ''}")
