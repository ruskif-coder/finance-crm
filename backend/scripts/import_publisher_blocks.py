"""Импорт каталога площадок и блоков из «Площадки и блоки.xlsx».

Первичное наполнение publisher_surface + publisher_block (миграции 2026-09-01_ad_campaigns.sql
и 2026-09-01_publisher_surface.sql). ПРАВИЛО: площадка попадает в каталог ТОЛЬКО если она уже
есть в реестре паблишеров (sales_publishers). Несовпавшие колонки НЕ создают паблишеров —
выводятся в отчёт «создать в реестре или мусор».

Структура файла транспонированная: колонки = площадки. Строка 1 — имя, 2 — ms_publisher_id,
3 — «кукуха2» (блок по умолчанию, авто-цепляется к креативу, скрыт из статистики кабинета).
Далее блоки группами по 4 строки: название / раздел / сеть / id блока.

Матч площадки: точный домен → «ядро» (снятие TLD и суффикса/префикса поверхности .app/_app/
app.) → иначе в отчёт. Поверхность web/app/ios/android — из имени колонки. Один блок на
(поверхность, ms_block_id), upsert — идемпотентно. Dry-run по умолчанию, запись — с --apply.

    docker exec finance_backend python -m scripts.import_publisher_blocks /tmp/blocks.xlsx --apply
"""
import argparse
import re

import app.models  # noqa: F401 — регистрирует users в Base.metadata
import app.launch_prep.models  # noqa: F401 — launch_prep_* (FK из ad.models)
from sqlalchemy import text

from app.ad.models import PublisherBlock  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.sales.models import SalesPublisherSurface  # noqa: E402 — переиспользуем поверхности модуля паблишеров

TLD = re.compile(r"\.(ru|рф|by|kz|club|com|org|net|store|online|app|ios|android)$")


def surface_of(name):
    n = (name or "").strip().lower()
    if n.startswith(("app.", "app_")) or n.endswith((".app", "_app")):
        return "app"
    if n.startswith(("ios.", "ios_")) or n.endswith((".ios", "_ios")):
        return "ios"
    if n.startswith(("android.", "android_")) or n.endswith((".android", "_android")):
        return "android"
    return "web"


def core(s):
    """«Ядро» имени: без протокола, www, суффикса/префикса поверхности и TLD."""
    s = (s or "").strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^www\.", "", s)
    s = re.sub(r"^(app|ios|android)[._]", "", s)
    s = re.sub(r"[._](app|ios|android)$", "", s)
    s = TLD.sub("", s)
    return s.strip()


def cid(v):
    """id из ячейки: openpyxl отдаёт числа как float — приводим к строке без .0."""
    if v in (None, ""):
        return None
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return str(v).strip()


def read_columns(path):
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb["Справочник площадок и блоков"]
    rows = [r for r in ws.iter_rows(values_only=True)]
    wb.close()
    ncol = max(len(r) for r in rows)

    def cell(r, c):
        return rows[r][c] if c < len(rows[r]) else None

    cols = []
    for c in range(1, ncol):
        name = cell(0, c)
        ms_id = cid(cell(1, c))
        kuk = cid(cell(2, c))
        if ms_id is None and name in (None, ""):
            continue
        blocks = []
        r = 3
        while r + 3 < len(rows):
            bn, sec, net, bid = cell(r, c), cell(r + 1, c), cell(r + 2, c), cid(cell(r + 3, c))
            if any(x not in (None, "") for x in (bn, sec, net, bid)):
                blocks.append(dict(
                    name=(str(bn).strip() if bn else None),
                    page_type=(str(sec).strip() if sec else None),
                    network=(str(net).strip() if net else None),
                    ms_block_id=bid,
                ))
            r += 4
        cols.append(dict(
            name=(str(name).strip() if name else None),
            ms_publisher_id=ms_id, default_ms_block_id=kuk, blocks=blocks,
        ))
    return cols


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="/tmp/blocks.xlsx")
    ap.add_argument("--apply", action="store_true", help="записать (по умолчанию dry-run)")
    args = ap.parse_args()

    db = SessionLocal()
    # Архивные площадки в каталог не переносим — как и несовпавшие, уходят в отчёт.
    pubs = db.execute(text("SELECT id, code, name, domain, status FROM sales_publishers")).mappings().all()
    by_domain, by_core = {}, {}
    for p in pubs:
        by_domain[(p["domain"] or "").strip().lower()] = p
        by_core.setdefault(core(p["domain"]) or core(p["name"]), []).append(p)

    matched, unmatched = [], []
    for col in read_columns(args.path):
        nm = col["name"]
        pub = by_domain.get((nm or "").strip().lower())
        if not pub:
            cands = by_core.get(core(nm), [])
            if len(cands) == 1:
                pub = cands[0]
            else:
                why = "неоднозначно: " + str([c["id"] for c in cands]) if cands else "нет в реестре"
                unmatched.append((nm, why, col))
                continue
        if (pub["status"] or "") == "АРХИВ":
            unmatched.append((nm, "площадка в архиве", col))
            continue
        matched.append((pub, surface_of(nm), col))

    print(f"Колонок в файле: {len(matched) + len(unmatched)} | привязано: {len(matched)} "
          f"| в отчёт: {len(unmatched)}")

    n_surf = n_blk = n_skip = n_new_surf = 0
    for pub, surface, col in matched:
        n_surf += 1
        if args.apply:
            # переиспользуем поверхность модуля паблишеров; kind ∈ {web, app}
            surf = db.query(SalesPublisherSurface).filter_by(
                publisher_id=pub["id"], kind=surface).first()
            if not surf:
                surf = SalesPublisherSurface(publisher_id=pub["id"], kind=surface)
                db.add(surf)
                db.flush()
                n_new_surf += 1
            surf.ms_publisher_id = col["ms_publisher_id"]
            surf.default_ms_block_id = col["default_ms_block_id"]
            for b in col["blocks"]:
                if not b["ms_block_id"]:
                    n_skip += 1
                    continue
                blk = db.query(PublisherBlock).filter_by(
                    surface_id=surf.id, ms_block_id=b["ms_block_id"]).first()
                if not blk:
                    blk = PublisherBlock(surface_id=surf.id, ms_block_id=b["ms_block_id"])
                    db.add(blk)
                    n_blk += 1
                blk.publisher_id = pub["id"]
                blk.surface = surface
                blk.name = b["name"]
                blk.page_type = b["page_type"]
                blk.network = b["network"]
        else:
            real = [b for b in col["blocks"] if b["ms_block_id"]]
            n_blk += len(real)
            n_skip += len(col["blocks"]) - len(real)

    if args.apply:
        db.commit()
        print(f"ЗАПИСАНО: поверхностей затронуто {n_surf} (новых +{n_new_surf}), "
              f"блоков +{n_blk}, пропущено без id: {n_skip}")
    else:
        print(f"[dry-run] будет: поверхностей затронуто ~{n_surf}, блоков ~{n_blk}, "
              f"пропуск без id ~{n_skip}")

    if unmatched:
        print("\n--- НЕ привязано (создать в реестре паблишеров или мусор) ---")
        for nm, why, col in unmatched:
            print(f"   {(nm or ''):<26} ms={col['ms_publisher_id'] or '-':<7} "
                  f"блоков={len(col['blocks']):<3} {why}")
    db.close()


if __name__ == "__main__":
    main()
