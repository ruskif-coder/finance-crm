# -*- coding: utf-8 -*-
"""Ограничение статусов мастер-сделки в базе = статусы в коде (ревью 21.10.2026). Миграции идут по имени, и последняя,
пересоздающая `master_deals_status_check`, определяет итог: она сняла «ждём сканы», хотя предыдущая его добавляла."""
import pathlib
import re

from app.master_deal.status import STATUSES

MIG = pathlib.Path(__file__).resolve().parents[1] / "migrations"


def test_last_migration_defining_status_check_lists_every_status():
    files = sorted(p for p in MIG.glob("*.sql") if "master_deals_status_check" in p.read_text(encoding="utf-8")
                   and "ADD CONSTRAINT master_deals_status_check" in p.read_text(encoding="utf-8"))
    assert files, "миграция ограничения статусов не найдена"
    last = files[-1].read_text(encoding="utf-8")
    check = re.search(r"ADD CONSTRAINT master_deals_status_check\s+CHECK \(status IN \(([^)]*)\)\)", last).group(1)
    assert set(re.findall(r"'([^']+)'", check)) == set(STATUSES), files[-1].name
