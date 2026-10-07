# -*- coding: utf-8 -*-
"""Привести УЖЕ заведённые в DSP креативы к правилам ссылок (07.10.2026).

Зачем. Выгрузка (`dsp/provision`) умеет класть диплинк SDK в `<a href>` и якорь в «Конечный URL», но
креатив, уже лежащий в DSP, сама не меняет (`state == "ok"` — пропуск). Раньше такие правки делались
вручную по просьбе; теперь это команда. Правило то же, что у выгрузки (одна функция на всё):
  · диплинк SDK — `pub_rules.post_upload_href` (режим «sdk»/«обе» или диплинк в цели пары);
  · «Конечный URL» — `creatives.landing_adomain` (посадочная целиком, с якорем).
Статус креатива НЕ меняется (ни запуск, ни остановка), кликовая ссылка (`link`) не трогается.

    docker exec finance_backend python -m scripts.2026-10-07_sync_creative_links 4FKFD2 LBS2QH          # сухо
    docker exec finance_backend python -m scripts.2026-10-07_sync_creative_links 4FKFD2 --apply

Перед правкой html исходник пишется в `/app/logs/dsp_html_backup_<код>_<площадка>_cr<id>_<дата>.html`
(на сервере — `backend/logs/`): откат — вернуть этот html правкой `Creative.edit`. Повторный запуск ничего
не делает, если креатив уже в порядке.
"""
import os
import sys
from datetime import date
from typing import Optional

from sqlalchemy import text

from app.database import SessionLocal
from app.dsp import creatives as cr
from app.dsp import provision as prov
from app.dsp.client import MsClient, MsError, safe_error
from app.launch_prep import pub_rules
from app.launch_prep.sandbox import set_html_click_href

BACKUP_DIR = os.environ.get("LOG_DIR") or "/app/logs"


def plan_edits(rule: Optional[dict], advertiser_url: Optional[str], deeplink_url: Optional[str],
               info: dict) -> dict:
    """Что нужно поправить в креативе, чтобы он соответствовал правилам. Чистая функция.

    {} — всё в порядке. Ключи: `html` (новый html_code), `adomain` (новый конечный URL)."""
    out = {}
    html = ((info.get("data") or {}).get("html_code") or "")
    href = pub_rules.post_upload_href(rule, advertiser_url, deeplink_url)
    if href and html:
        new_html, changed = set_html_click_href(html, href)
        if changed:
            out["html"] = new_html
    want_adomain = cr.landing_adomain(pub_rules.web_url(advertiser_url))
    if want_adomain and (info.get("adomain") or "") != want_adomain:
        out["adomain"] = want_adomain
    return out


def _slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in (name or "x"))


def run(codes, apply: bool = False, client=None, db=None) -> dict:
    own_db = db is None
    db = db or SessionLocal()
    c = client or MsClient()
    report = {"planned": [], "applied": [], "failed": [], "ok": 0}
    try:
        camps = db.execute(text(
            "SELECT c.id FROM ad_campaign c JOIN sales_deals d ON d.id = c.deal_id "
            "WHERE upper(d.code) = ANY(:codes) ORDER BY c.id"),
            {"codes": [x.upper() for x in codes]}).scalars().all()
        from app.ad.models import AdCampaign
        for cid in camps:
            camp = db.get(AdCampaign, cid)
            for r in prov._rows(db, camp):
                cre, tgt = r["creative"], r["target"]
                if not cre.ms_creative_xxhash or tgt is None:
                    continue
                name = f"{camp.id}/{getattr(r['publisher'], 'name', '?')}/cr{cre.id}"
                try:
                    info = c.creative_get_info(cre.ms_creative_xxhash) or {}
                except MsError as e:
                    report["failed"].append({"creative": name, "error": safe_error(e)})
                    continue
                edits = plan_edits(r.get("rule"), tgt.advertiser_url,
                                   getattr(tgt, "deeplink_url", None), info)
                if not edits:
                    report["ok"] += 1
                    continue
                item = {"creative": name, "status": info.get("status"), "edits": sorted(edits)}
                report["planned"].append(item)
                if not apply:
                    continue
                try:
                    if "html" in edits:
                        orig = (info.get("data") or {}).get("html_code") or ""
                        os.makedirs(BACKUP_DIR, exist_ok=True)
                        path = os.path.join(BACKUP_DIR, "dsp_html_backup_%s_%s_cr%s_%s.html" % (
                            _slug(getattr(r["publisher"], "name", "")), cid, cre.id,
                            date.today().strftime("%Y%m%d")))
                        with open(path, "w", encoding="utf-8") as fh:
                            fh.write(orig)
                        c.creative_edit(cre.ms_creative_xxhash, {"data": {"html_code": edits["html"]}},
                                        local_ref=f"sync-links-cr{cre.id}")
                    if "adomain" in edits:
                        c.creative_edit(cre.ms_creative_xxhash, {"adomain": edits["adomain"]},
                                        local_ref=f"sync-links-cr{cre.id}")
                    report["applied"].append(item)
                except MsError as e:
                    report["failed"].append({"creative": name, "error": safe_error(e)})
    finally:
        if own_db:
            db.rollback()
            db.close()
    return report


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    apply = "--apply" in argv
    codes = [a for a in argv if not a.startswith("--")]
    if not codes:
        print(__doc__)
        return 2
    rep = run(codes, apply=apply)
    print(("ПРИМЕНЕНО" if apply else "СУХОЙ ПРОГОН — ничего не записано") + f": креативов в порядке {rep['ok']}")
    for it in rep["planned"]:
        mark = "ok" if it in rep["applied"] else ("—" if not apply else "?")
        print(f"  {it['creative']:<42} DSP={it['status']!s:<9} правки: {', '.join(it['edits'])}  [{mark}]")
    for f in rep["failed"]:
        print(f"  ОШИБКА {f['creative']}: {f['error']}")
    if not apply and rep["planned"]:
        print("Для применения добавьте --apply")
    return 1 if rep["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
