# -*- coding: utf-8 -*-
"""
Загружает воронки и их стадии из Битрикс24 (VibeCode) в sales_pipelines
и sales_pipeline_stages.

Запуск: docker exec finance_backend python -m scripts.load_pipeline_stages

Читает только те воронки, что уже есть в sales_pipelines (по имени), плюс
проставляет им bitrix_category_id. Новые воронки из Битрикса НЕ создаёт молча —
о них печатает, решение оставляет человеку. Так «Новая воронка» и «Площадки»
не попадут в учёт без ведома оператора.
"""
import os
import sys
import httpx

sys.path.insert(0, "/app")   # запуск через `python -m scripts.<имя>` это уже делает; строка оставлена для прямого вызова

from app.database import SessionLocal  # noqa: E402
from app import models as core_models  # noqa: E402,F401
from app.sales.models import SalesPipeline, SalesPipelineStage  # noqa: E402
from app.sales.normalize import normalize_name  # noqa: E402

BASE = "https://vibecode.bitrix24.tech/v1"
KEY = os.getenv("VIBECODE_API_KEY", "")


def fetch(client, path, **params):
    r = client.get(f"{BASE}/{path}", params=params, headers={"X-Api-Key": KEY})
    r.raise_for_status()
    data = r.json()
    if not data.get("success", True):
        raise RuntimeError(f"{path}: {data}")
    return data["data"]


def main():
    if not KEY:
        raise SystemExit("VIBECODE_API_KEY не задан в окружении контейнера")

    db = SessionLocal()
    client = httpx.Client(timeout=30)
    try:
        cats = fetch(client, "deal-categories", limit=50)
        # DEAL_STAGE (без суффикса) — воронка id=0, общая; остальные DEAL_STAGE_<id>
        statuses = fetch(client, "statuses", limit=300)
        stages_by_cat = {}
        for s in statuses:
            ent = s["entityId"]
            if ent == "DEAL_STAGE":
                cat = 0
            elif ent.startswith("DEAL_STAGE_"):
                cat = int(ent.rsplit("_", 1)[1])
            else:
                continue
            stages_by_cat.setdefault(cat, []).append(s)

        cats_by_id = {c["id"]: c["name"] for c in cats}
        cats_by_id.setdefault(0, "Общая")  # воронка по умолчанию без суффикса

        pipes = {normalize_name(p.name): p for p in db.query(SalesPipeline).all()}
        linked, unknown = 0, []

        for cat_id, name in cats_by_id.items():
            p = pipes.get(normalize_name(name))
            if p is None:
                # воронка есть в Битриксе, но не заведена у нас — не создаём молча
                if cat_id in stages_by_cat:
                    unknown.append((cat_id, name, len(stages_by_cat.get(cat_id, []))))
                continue

            p.bitrix_category_id = cat_id
            linked += 1

            have = {(st.bitrix_category_id, st.status_id)
                    for st in db.query(SalesPipelineStage)
                    .filter(SalesPipelineStage.pipeline_id == p.id).all()}
            for i, s in enumerate(sorted(stages_by_cat.get(cat_id, []),
                                         key=lambda x: x.get("sort", 0))):
                key = (cat_id, s["statusId"])
                if key in have:
                    continue
                db.add(SalesPipelineStage(
                    pipeline_id=p.id, bitrix_category_id=cat_id,
                    status_id=s["statusId"], name=s["name"], sort_order=s.get("sort", i)))

        db.commit()
        print(f"Связано воронок с Битриксом: {linked}")
        for cat_id, name, n in unknown:
            print(f"  НЕ в учёте: id={cat_id} «{name}» ({n} стадий) — завести вручную, если нужно")

        total = db.query(SalesPipelineStage).count()
        print(f"Всего стадий в справочнике: {total}")
    finally:
        client.close()
        db.close()


if __name__ == "__main__":
    main()
