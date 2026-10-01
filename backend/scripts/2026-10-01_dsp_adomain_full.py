# -*- coding: utf-8 -*-
"""Разовая правка «конечного URL» (`adomain`) у креативов, уже заведённых в DSP
(владелец 01.10.2026).

Было: в `adomain` — только домен посадочной (по документации DSP предел 128 символов).
Надо: посадочная креатива целиком — та, что пришла с креативом от аккаунтов или от
площадки при запросе, не кликовая ссылка Weborama. Вводные DSP 01.10.2026: предел 1024.
Правило одно с выгрузкой — `creatives.landing_adomain`.

По умолчанию — пробный прогон: только читает из DSP и показывает план. Запись — `--apply`.
Повтор безопасен: совпадающее не шлётся.

    docker exec finance_backend python -m scripts.2026-10-01_dsp_adomain_full [--apply] [--deal CODE]
"""
import sys

from sqlalchemy import text

import app.main  # noqa: F401
from app.database import SessionLocal
from app.dsp import creatives as CR
from app.dsp.client import MsClient, MsError


def main():
    apply = "--apply" in sys.argv
    deal = sys.argv[sys.argv.index("--deal") + 1].upper() if "--deal" in sys.argv else ""
    db = SessionLocal()
    rows = db.execute(text("""
        SELECT cr.id, cr.ms_creative_xxhash, d.code, st.advertiser_url
          FROM ad_campaign_creative cr
          JOIN ad_campaign a ON a.id = cr.campaign_id
          JOIN sales_deals d ON d.id = a.deal_id
          LEFT JOIN launch_prep_pair pr ON pr.id = cr.pair_id
          -- Посадочная — из состава креатива (пара «креатив × площадка»), как у выгрузки
          -- (`provision._rows`), а не у получателя сделки: там её у части сделок нет.
          LEFT JOIN launch_prep_set_target st ON st.set_id = pr.set_id AND st.target_id = pr.target_id
         WHERE cr.ms_creative_xxhash IS NOT NULL AND (:deal = '' OR upper(d.code) = :deal)
         ORDER BY d.code, cr.id
    """), {"deal": deal}).all()
    c = MsClient()
    plan, sent, same, skipped, failed = 0, 0, 0, [], []
    for cid, h, code, landing in rows:
        want = CR.landing_adomain(landing)
        if not want:
            skipped.append(f"{code} cr{cid}: нет посадочной")
            continue
        try:
            have = (c.creative_get_info(h) or {}).get("adomain")
        except MsError as e:
            failed.append(f"{code} cr{cid}: getInfo — {e}")
            continue
        if have == want:
            same += 1
            continue
        plan += 1
        if plan <= 5:
            print(f"  {code} cr{cid} {h}\n    {have} → {want}")
        if apply:
            try:
                c.creative_edit(h, {"adomain": want}, local_ref=f"cr{cid}")
                sent += 1
            except MsError as e:
                failed.append(f"{code} cr{cid}: Creative.edit — {e}")
    print({"креативов": len(rows), "к правке": plan, "уже так": same, "отправлено": sent,
           "без посадочной": len(skipped), "сбоев": len(failed)})
    for line in (skipped + failed)[:20]:
        print("  ", line)
    if not apply:
        print("пробный прогон — в DSP ничего не отправлено; для записи --apply")
    db.close()


if __name__ == "__main__":
    main()
