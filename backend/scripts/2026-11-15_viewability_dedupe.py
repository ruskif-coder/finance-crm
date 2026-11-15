# -*- coding: utf-8 -*-
"""Убрать второй `viewability.js` из УЖЕ заведённых креативов DSP (15.11.2026).

Зачем. Дизайнер вкладывает скрипт видимости в архив баннера, загрузчик DSP добавляет свой — в креативе два подключения, скрипт
DSP рисует две плашки ЕРИД, и у части баннеров одна из них без стилей уходит под фон (замер 15.11: 121 из 720 ноябрьских, 8 РК;
у Изопринозина WTFANV плашки не видно совсем). Новые креативы чистит `creatives.wrap_html`; этот скрипт правит уже заведённые
через `creatives.dedupe_viewability` — оставляет последний скрипт, тот, что после настроек кампании.

Отбор тот же, что у `2026-11-09_click_fix_restyle`: креативы с хешом DSP на РК в статусах `--statuses` (по умолчанию «запущена»),
кроме отклонённых; `--targeting` — копии нацеливания у демоклиента. Меняется только `html_code`.

    docker exec finance_backend python -m scripts.2026-11-15_viewability_dedupe                       # сухо: список
    docker exec finance_backend python -m scripts.2026-11-15_viewability_dedupe --only=<хеш> --apply # один на пробу
    docker exec finance_backend python -m scripts.2026-11-15_viewability_dedupe --apply
    docker exec finance_backend python -m scripts.2026-11-15_viewability_dedupe --targeting

Перед правкой HTML пишется в `/app/logs/dsp_html_backup_viewability_<хеш>_<дата>.html` — откат правкой `Creative.edit` этим
HTML. Печатается статус креатива в DSP до и после. Повторный запуск ничего не делает.
"""
import importlib
import os
import sys
from datetime import date

from app.database import SessionLocal
from app.dsp import creatives as cr
from app.dsp.client import MsClient, MsError, safe_error

_base = importlib.import_module("scripts.2026-11-09_click_fix_restyle")   # отбор креативов и кабинет нацеливания — общие
BACKUP_DIR = os.environ.get("LOG_DIR") or "/app/logs"
DEFAULT_STATUSES = _base.DEFAULT_STATUSES


def _backup(xxhash: str, html: str) -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    path = os.path.join(BACKUP_DIR, "dsp_html_backup_viewability_%s_%s.html" % (xxhash, date.today().strftime("%Y%m%d")))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return path


def run(statuses=DEFAULT_STATUSES, only=None, apply=False, client=None, db=None, mode="campaigns") -> dict:
    own_db = db is None
    db = db or SessionLocal()
    c = client or (_base.targeting_client(db) if mode == "targeting" else MsClient())
    rows = _base.targeting_candidates(db, only) if mode == "targeting" else _base.candidates(db, statuses, only)
    rep = {"planned": [], "applied": [], "failed": [], "ok": 0}
    try:
        for row in rows:
            name = row["title"] or f"cr{row['id']}"
            try:
                info = c.creative_get_info(row["xxhash"]) or {}
            except MsError as e:
                rep["failed"].append({"creative": name, "error": safe_error(e)})
                continue
            html = (info.get("data") or {}).get("html_code") or ""
            new, changed = cr.dedupe_viewability(html)
            if not changed:
                rep["ok"] += 1
                continue
            item = {"creative": name, "xxhash": row["xxhash"], "status_before": info.get("status"),
                    "count": html.count("viewability.js")}
            rep["planned"].append(item)
            if not apply:
                continue
            try:
                item["backup"] = _backup(row["xxhash"], html)
                c.creative_edit(row["xxhash"], {"data": {"html_code": new}}, local_ref=f"viewability-cr{row['id']}")
                item["status_after"] = (c.creative_get_info(row["xxhash"]) or {}).get("status")
                rep["applied"].append(item)
            except MsError as e:
                rep["failed"].append({"creative": name, "error": safe_error(e)})
    finally:
        if own_db:
            db.rollback()
            db.close()
    return rep


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    apply = "--apply" in argv
    statuses = tuple(s.strip() for s in (_base._arg(argv, "--statuses") or ",".join(DEFAULT_STATUSES)).split(",") if s.strip())
    mode = "targeting" if "--targeting" in argv else "campaigns"
    rep = run(statuses, only=_base._arg(argv, "--only"), apply=apply, mode=mode)
    print(("ПРИМЕНЕНО" if apply else "СУХОЙ ПРОГОН — ничего не записано")
          + (" · копии нацеливания" if mode == "targeting" else f" · РК {', '.join(statuses)}")
          + f" · один скрипт видимости {rep['ok']} · к правке {len(rep['planned'])}")
    for it in rep["planned"]:
        tail = (f"  DSP {it['status_before']} → {it.get('status_after')}" if apply else f"  DSP {it['status_before']}")
        print(f"  {it['creative']:<34} {it['xxhash']}  скриптов {it['count']}{tail}")
    for f in rep["failed"]:
        print(f"  ОШИБКА {f['creative']}: {f['error']}")
    if not apply and rep["planned"]:
        print("Для применения добавьте --apply (сначала --only=<хеш> на одном креативе)")
    return 1 if rep["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
