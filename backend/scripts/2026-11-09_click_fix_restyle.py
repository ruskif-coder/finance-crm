# -*- coding: utf-8 -*-
"""Снять верхний слой с растянутой ссылки в УЖЕ заведённых креативах DSP (09.11.2026).

Зачем. Фикс клика (`creatives.CLICK_FIX_STYLE`, 14.10) растягивал обёртку DSP `<a href="{LINK_UNESC}">` на весь баннер с
`z-index:2147483000` — она ложилась и поверх плашки ЕРИД, клик по плашке уводил на посадочную. Новые креативы получают стиль
без верхнего слоя, а уже заведённые перевыгрузка не правит: `needs_click_fix` видит метку и второй раз не вставляет. Этот
скрипт заменяет в их HTML любой блок `<style data-simb-click-fix>…</style>` на текущий (`creatives.restyle_click_fix`).

Отбор: креативы с хешом DSP на РК, чей статус — из `--statuses` (по умолчанию только «запущена»), кроме отклонённых. По РК, а
не по статусу креатива: у живой РК креативы в основном «согласован» (замер стенда 09.11: 594 против 29 «запущен»), а «запущен»
стоит и у 154 креативов оконченных РК. Ничего, кроме `html_code`, не меняется: ни статус, ни лимиты, ни ссылка клика.

    docker exec finance_backend python -m scripts.2026-11-09_click_fix_restyle                         # сухо: список и разница
    docker exec finance_backend python -m scripts.2026-11-09_click_fix_restyle "--statuses=запущена,ожидает сборки"
    docker exec finance_backend python -m scripts.2026-11-09_click_fix_restyle --only=<хеш> --apply   # один креатив на пробу
    docker exec finance_backend python -m scripts.2026-11-09_click_fix_restyle --apply

Перед правкой текущий HTML пишется в `/app/logs/dsp_html_backup_clickfix_<хеш>_<дата>.html` (на сервере — `backend/logs/`):
откат — вернуть этот HTML правкой `Creative.edit`. После правки печатается статус креатива в DSP до и после — по нему видно, не
ушёл ли креатив на модерацию или в паузу. Повторный запуск ничего не делает: стиль уже текущий.
"""
import os
import sys
from datetime import date

from sqlalchemy import text

from app.database import SessionLocal
from app.dsp import creatives as cr
from app.dsp.client import MsClient, MsError, safe_error

BACKUP_DIR = os.environ.get("LOG_DIR") or "/app/logs"
DEFAULT_STATUSES = ("запущена",)          # статусы РК


def _style_of(html: str) -> str:
    m = cr._CLICK_FIX_BLOCK_RE.search(html or "")
    return m.group(0) if m else ""


def candidates(db, statuses, only=None) -> list:
    rows = db.execute(text(
        "SELECT r.id, r.ms_creative_xxhash AS xxhash, coalesce(r.ms_title, '') AS title, r.status "
        "  FROM ad_campaign_creative r JOIN ad_campaign c ON c.id = r.campaign_id "
        " WHERE r.ms_creative_xxhash IS NOT NULL AND c.status = ANY(:st) AND r.status <> 'отклонён' "
        "   AND (CAST(:only AS text) IS NULL OR r.ms_creative_xxhash = :only) ORDER BY r.id"),
        {"st": list(statuses), "only": only}).mappings().all()
    return [dict(x) for x in rows]


def _backup(xxhash: str, html: str) -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    path = os.path.join(BACKUP_DIR, "dsp_html_backup_clickfix_%s_%s.html" % (xxhash, date.today().strftime("%Y%m%d")))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return path


def run(statuses=DEFAULT_STATUSES, only=None, apply=False, client=None, db=None) -> dict:
    own_db = db is None
    db = db or SessionLocal()
    c = client or MsClient()
    rep = {"planned": [], "applied": [], "failed": [], "ok": 0, "no_mark": 0}
    try:
        for row in candidates(db, statuses, only):
            name = row["title"] or f"cr{row['id']}"
            try:
                info = c.creative_get_info(row["xxhash"]) or {}
            except MsError as e:
                rep["failed"].append({"creative": name, "error": safe_error(e)})
                continue
            html = (info.get("data") or {}).get("html_code") or ""
            new, changed = cr.restyle_click_fix(html)
            if cr.CLICK_FIX_MARK not in html:
                rep["no_mark"] += 1
                continue
            if not changed:
                rep["ok"] += 1
                continue
            item = {"creative": name, "xxhash": row["xxhash"], "status_before": info.get("status"),
                    "old": _style_of(html), "new": _style_of(new)}
            rep["planned"].append(item)
            if not apply:
                continue
            try:
                item["backup"] = _backup(row["xxhash"], html)
                c.creative_edit(row["xxhash"], {"data": {"html_code": new}}, local_ref=f"clickfix-cr{row['id']}")
                item["status_after"] = (c.creative_get_info(row["xxhash"]) or {}).get("status")
                rep["applied"].append(item)
            except MsError as e:
                rep["failed"].append({"creative": name, "error": safe_error(e)})
    finally:
        if own_db:
            db.rollback()
            db.close()
    return rep


def _arg(argv, key):
    return next((a.split("=", 1)[1] for a in argv if a.startswith(key + "=")), None)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    apply = "--apply" in argv
    statuses = tuple(s.strip() for s in (_arg(argv, "--statuses") or ",".join(DEFAULT_STATUSES)).split(",") if s.strip())
    rep = run(statuses, only=_arg(argv, "--only"), apply=apply)
    print(("ПРИМЕНЕНО" if apply else "СУХОЙ ПРОГОН — ничего не записано")
          + f" · РК {', '.join(statuses)} · уже в порядке {rep['ok']} · без фикса клика {rep['no_mark']}"
          + f" · к правке {len(rep['planned'])}")
    for it in rep["planned"]:
        tail = (f"  DSP {it['status_before']} → {it.get('status_after')}" if apply else f"  DSP {it['status_before']}")
        print(f"  {it['creative']:<34} {it['xxhash']}{tail}")
        print(f"      было:  {it['old']}")
        print(f"      будет: {it['new']}")
    for f in rep["failed"]:
        print(f"  ОШИБКА {f['creative']}: {f['error']}")
    if not apply and rep["planned"]:
        print("Для применения добавьте --apply (сначала --only=<хеш> на одном креативе)")
    return 1 if rep["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
