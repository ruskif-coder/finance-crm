# -*- coding: utf-8 -*-
"""Уборка файлов по срокам хранения + отчёт о сиротах.

Правила сроков живут в `app/traffic/retention.py` и здесь НЕ повторяются — этот файл
только обходит хранилище и спрашивает у них «пора ли». Второй счёт того же события
однажды разошёлся бы, и мы начали бы стирать доказательства раньше баннеров.

**По умолчанию НИЧЕГО НЕ УДАЛЯЕТСЯ.** Нужен явный `--apply`: уборка необратима, а
сроки отмеряются от выхода со стадии «Отчёты в ОРД», то есть ошибка в истории стадий
стирает не тот файл. Сухой прогон печатает ровно то, что удалил бы.

    docker exec finance_backend python -m scripts.2026-08-30_retention_sweep
    docker exec finance_backend python -m scripts.2026-08-30_retention_sweep --apply

Покрыты ТРИ вида файлов — те, у которых срок согласован владельцем 27.08.2026:

    скриншоты пары   30 дней   launch_prep_pair_file      uploads/shots/
    песочница        60 дней   распакованный баннер       uploads/sandbox/
    архивы креативов 730 дней  launch_prep_creative_file  uploads/creatives/

Остальные папки хранилища (`deal_files` 310 МБ, `mediakit`, `publishers`, `operations`,
`bx_consolidate`) срока НЕ ИМЕЮТ и здесь не трогаются. Придумать им период — решение
владельца, а не программиста: `deal_files` это медиапланы клиентов.

Второй режим, `--orphans`, — отчёт, обещанный в докстринге `is_expired`: файлы на диске,
на которые не ссылается ни одна строка. Он ничего не удаляет никогда: сирота может быть
как мусором синхронизации, так и единственной копией документа, потерявшего строку.
"""
import os
import shutil
import sys
from datetime import date

from app.database import SessionLocal
from app.launch_prep.models import (LaunchPrepCreativeFile, LaunchPrepCreativeSet,
                                    LaunchPrepPair, LaunchPrepPairFile)
from app.traffic import retention

UPLOADS = os.getenv("UPLOADS_ROOT", "/app/uploads")


def _size(rel):
    try:
        return os.path.getsize(os.path.join(UPLOADS, rel))
    except OSError:
        return 0


def _human(n):
    return f"{n / 1024 / 1024:.1f} МБ" if n >= 1024 * 1024 else f"{n / 1024:.0f} КБ"


def sweep(apply: bool):
    """Обойти три вида файлов. Возвращает (сколько, байт) к удалению."""
    db = SessionLocal()
    today = date.today()
    # Закрытие считается ОДИН РАЗ на сделку: у комплекта десятки файлов, и запрос на
    # каждый превратил бы уборку в тысячи обращений к истории стадий.
    closed = {}

    def deal_closed(deal_id):
        if deal_id not in closed:
            closed[deal_id] = retention.closed_at(db, deal_id)
        return closed[deal_id]

    plan = []

    # 1. Скриншоты размещения — 30 дней.
    rows = (db.query(LaunchPrepPairFile, LaunchPrepCreativeSet)
            .join(LaunchPrepPair, LaunchPrepPair.id == LaunchPrepPairFile.pair_id)
            .join(LaunchPrepCreativeSet, LaunchPrepCreativeSet.id == LaunchPrepPair.set_id)
            .all())
    for f, s in rows:
        if retention.is_expired(deal_closed(s.deal_id), retention.SCREENSHOT_DAYS, today):
            plan.append(("скриншот", f.path, _size(f.path), ("row", f)))

    # 2. Песочница — 60 дней. Стирается КАТАЛОГ, строка остаётся: `sandbox.unpack`
    #    развернёт её из архива заново, и обнулять токен значило бы терять эту связь.
    # 3. Архивы креативов — 730 дней, вместе со строкой.
    cf = (db.query(LaunchPrepCreativeFile, LaunchPrepCreativeSet)
          .join(LaunchPrepCreativeSet, LaunchPrepCreativeSet.id == LaunchPrepCreativeFile.set_id)
          .all())
    for f, s in cf:
        cl = deal_closed(s.deal_id)
        if f.sandbox_token and retention.is_expired(cl, retention.SANDBOX_DAYS, today):
            d = os.path.join("sandbox", f.sandbox_token)
            if os.path.isdir(os.path.join(UPLOADS, d)):
                sz = sum(_size(os.path.join(d, n)) for n in os.listdir(os.path.join(UPLOADS, d)))
                plan.append(("песочница", d, sz, ("dir", None)))
        if retention.is_expired(cl, retention.ARCHIVE_DAYS, today):
            plan.append(("архив", f.path, _size(f.path), ("row", f)))

    total = sum(p[2] for p in plan)
    head = "УДАЛЯЮ" if apply else "сухой прогон — удалил бы"
    print(f"{head}: {len(plan)} шт, {_human(total)}")
    for kind, path, sz, _ in plan[:40]:
        print(f"  {kind:<11} {path}  {_human(sz)}")
    if len(plan) > 40:
        print(f"  … и ещё {len(plan) - 40}")

    if apply:
        for kind, path, _sz, (how, row) in plan:
            full = os.path.join(UPLOADS, path)
            try:
                shutil.rmtree(full) if how == "dir" else os.remove(full)
            except OSError as e:
                print(f"  не удалось стереть {path}: {e}")
            if row is not None:
                db.delete(row)
        db.commit()
        print("готово")
    db.close()
    return len(plan), total


def orphans():
    """Файлы на диске без строки в базе. НИЧЕГО не удаляет — только считает."""
    db = SessionLocal()
    from sqlalchemy import text as sa_text
    known = set()
    for q in ("SELECT path FROM launch_prep_creative_file",
              "SELECT path FROM launch_prep_pair_file",
              "SELECT path FROM sales_deal_files",
              "SELECT path FROM operation_files"):
        try:
            known |= {r[0] for r in db.execute(sa_text(q)) if r[0]}
        except Exception:
            db.rollback()          # таблицы может не быть на другом стенде
    db.close()

    print(f"строк с путями в базе: {len(known)}")
    for folder in sorted(os.listdir(UPLOADS)):
        root = os.path.join(UPLOADS, folder)
        if not os.path.isdir(root) or folder == "sandbox":
            continue
        n = lost = size = 0
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                rel = os.path.relpath(os.path.join(dirpath, name), UPLOADS).replace("\\", "/")
                n += 1
                if rel not in known:
                    lost += 1
                    size += _size(rel)
        mark = "  ← нет правила срока" if folder not in ("creatives", "shots") else ""
        print(f"  {folder:<16} файлов {n:>4}, без строки {lost:>4}  {_human(size):>9}{mark}")


if __name__ == "__main__":
    if "--orphans" in sys.argv:
        orphans()
    else:
        sweep("--apply" in sys.argv)
