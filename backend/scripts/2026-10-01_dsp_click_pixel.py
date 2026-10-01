# -*- coding: utf-8 -*-
"""Разовая правка креативов, уже заведённых в DSP (владелец 01.10.2026, первые боевые РК).

Было: конечный URL креатива (`link`) — голая посадочная площадки, пиксель показа
Weborama — тегом `<img>` в конце HTML баннера, поле `pixel` пустое.
Надо: `link` — кликовый счётчик Weborama с посадочной в `g.lu`; пиксель — ТОЛЬКО полем
`pixel` (из HTML убрать, иначе показ считался бы дважды).

Шаги:
  1. Кликовые ссылки Weborama для площадок, у которых пиксель уже заведён, — повторным
     чтением тегов вставки (`insertions/{id}/tags.json`). Новых вставок НЕ заводит.
  2. По каждому креативу в DSP (есть хеш) из РК, где пиксель заказан:
     `Creative.edit` {link, pixel} и, если в HTML есть наш `<img>` Weborama, — разметка
     без него. Внешний тег сделки: pixel = он, link — посадочная (кликового нет).

По умолчанию — пробный прогон: ничего не пишет ни у нас, ни в DSP, показывает план и
три примера. Запись — `--apply`. Повтор безопасен: то, что уже совпадает, не шлётся.

    docker exec finance_backend python -m scripts.2026-10-01_dsp_click_pixel [--apply] [--deal CODE]
"""
import re
import sys

from sqlalchemy import text

import app.main  # noqa: F401
from app.ad.build import pixel_setup
from app.ad.models import AdCampaign, AdCampaignCreative, AdCampaignPlacement
from app.database import SessionLocal
from app.dsp import provision as P
from app.dsp.client import MsClient, MsError
from app.sales.models import SalesPublisher

IMG_WR = re.compile(r'\s*<img src="https://wcm\.weborama[^"]*"[^>]*>\s*$')
SIZE = re.compile(r"^(\d+)x(\d+)$")


def backfill_clicks(db, apply: bool, deal: str = None) -> dict:
    from app.weborama import provision as WP
    from app.weborama import tags
    from app.weborama.client import WcmClient
    rows = db.execute(text("""
        SELECT p.id, r.wcm_id FROM ad_campaign_placement p
          JOIN ad_campaign a ON a.id = p.campaign_id
          JOIN sales_deals d ON d.id = a.deal_id
          JOIN weborama_refs r ON r.kind = 'insertion' AND r.local_id = p.id
         WHERE p.weborama_pixel IS NOT NULL AND p.weborama_click IS NULL
           AND (:deal = '' OR d.code = :deal)
    """), {"deal": deal or ""}).all()
    if not rows:
        return {"нужно": 0, "получено": 0}
    c = WcmClient(WP.account_id(db))
    got = 0
    for pid, ins in rows:
        try:
            click = tags.parse(c.insertion_tag(ins)).get("click")
        except Exception as e:  # noqa: BLE001 — одна вставка не держит остальные
            print(f"  вставка {ins}: тег не прочитан — {e}")
            continue
        if click:
            got += 1
            # И в пробном прогоне пишем в сессию: шаг 2 должен показать ИТОГОВУЮ ссылку,
            # а в конце пробного прогона всё откатывается.
            db.execute(text("UPDATE ad_campaign_placement SET weborama_click = :c WHERE id = :p"),
                       {"c": click, "p": pid})
    return {"нужно": len(rows), "получено": got}


def fix_creatives(db, apply: bool, deal: str = None) -> dict:
    q = (db.query(AdCampaignCreative, AdCampaignPlacement, AdCampaign, SalesPublisher)
         .join(AdCampaignPlacement, AdCampaignPlacement.id == AdCampaignCreative.placement_id)
         .join(AdCampaign, AdCampaign.id == AdCampaignCreative.campaign_id)
         .join(SalesPublisher, SalesPublisher.id == AdCampaignPlacement.publisher_id)
         .filter(AdCampaignCreative.ms_creative_xxhash.isnot(None)))
    c = MsClient()
    plan, sent, failed, shown = 0, 0, [], 0
    for cre, pl, camp, pub in q.all():
        code = db.execute(text("SELECT code FROM sales_deals WHERE id = :d"), {"d": camp.deal_id}).scalar()
        if deal and code != deal:
            continue
        px = pixel_setup(db, camp.deal_id)
        if not px["needed"] or (px["mode"] == "external" and not px["tag"]):
            continue
        tgt = db.execute(text("""
            SELECT t.advertiser_url FROM launch_prep_pair pr
              JOIN launch_prep_target t ON t.id = pr.target_id WHERE pr.id = :p
        """), {"p": cre.pair_id}).first()
        landing = tgt[0] if tgt else None
        try:
            info = c.creative_get_info(cre.ms_creative_xxhash) or {}
        except MsError as e:
            failed.append(f"{code} {pub.name}: getInfo — {e}")
            continue
        m = SIZE.match(str(info.get("size") or ""))
        w, h = (int(m.group(1)), int(m.group(2))) if m else (None, None)
        row = {"placement": pl, "publisher": pub}
        try:
            pix = P.pixel_url(row, w, h, px["tag"], cre.erid)
        except ValueError as e:
            failed.append(f"{code} {pub.name}: пиксель не собран — {e}")
            continue
        link = (P.click_link(row, landing, cre.erid) if px["mode"] != "external" else landing) or landing
        html = ((info.get("data") or {}).get("html_code") or "")
        clean = IMG_WR.sub("", html)
        edit = {}
        if link and info.get("link") != link:
            edit["link"] = link
        if info.get("pixel") != pix:
            edit["pixel"] = pix
        if clean != html:
            edit["data"] = {"html_code": clean}
        if not edit:
            continue
        plan += 1
        if shown < 3:
            shown += 1
            print(f"  {code} · {pub.name} · {cre.ms_title}")
            print(f"    link:  {info.get('link')} → {edit.get('link', '(без изменений)')}")
            print(f"    pixel: {(info.get('pixel') or '—')[:60]} → {edit.get('pixel', '(без изменений)')}")
            print(f"    из HTML убирается тег Weborama: {'да' if 'data' in edit else 'нет'}")
        if apply:
            try:
                c.creative_edit(cre.ms_creative_xxhash, edit, local_ref=f"cr{cre.id}")
                sent += 1
            except MsError as e:
                failed.append(f"{code} {pub.name}: Creative.edit — {e}")
    return {"к правке": plan, "отправлено": sent, "сбоев": len(failed), "сбои": failed[:10]}


def main():
    apply = "--apply" in sys.argv
    deal = sys.argv[sys.argv.index("--deal") + 1] if "--deal" in sys.argv else None
    db = SessionLocal()
    try:
        print("1. кликовые ссылки Weborama:", backfill_clicks(db, apply, deal))
        print("2. креативы в DSP:")
        print("  ", fix_creatives(db, apply, deal))
        if apply:
            db.commit()
            print("ЗАПИСАНО")
        else:
            db.rollback()
            print("пробный прогон — ничего не записано и в DSP не отправлено; для записи --apply")
    finally:
        db.close()


if __name__ == "__main__":
    main()
