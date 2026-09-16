# -*- coding: utf-8 -*-
"""Свежесть бэкапа — по строке на КАЖДУЮ базу.

Жалоба владельца 15.09.2026: «в настройках/статус бэкап показывается только dsp базы,
основную не показывает».

Разбор. Проверка брала самый свежий файл каталога — любой. Бэкап аналитической базы
делается в 03:10, через десять минут после основной, значит «самый свежий» это ВСЕГДА он.
Экран показывал дамп dsp_analytics на 24 КБ, подписывал его «Последний бэкап», и основной
базы на экране не было вовсе.

Хуже промаха в подписи то, что по этому же файлу считалась тревога: упади бэкап основной
базы совсем, строка осталась бы зелёной. Прибор, поставленный ради главного, отчитывался
о второстепенном — тот самый «успех, скрывающий неуспех».

Разделение по имени файла повторяет ротацию в `deploy.sh`: `backup_<дата>.sql` у основной,
`backup_dsp_analytics_<дата>.sql` у аналитической.
"""
import os
import time

from app.system import status


def _touch(d, name, hours_ago, size=1024):
    p = os.path.join(d, name)
    with open(p, "wb") as f:
        f.write(b"x" * size)
    t = time.time() - hours_ago * 3600
    os.utime(p, (t, t))
    return p


def test_each_database_gets_its_own_row(tmp_path, monkeypatch):
    """Дамп аналитической базы СВЕЖЕЕ — и всё равно не подменяет собой основную."""
    d = str(tmp_path)
    _touch(d, "backup_20260915_030000.sql", hours_ago=6, size=6 * 2**20)
    _touch(d, "backup_dsp_analytics_20260915_031000.sql", hours_ago=5, size=24 * 2**10)
    monkeypatch.setattr(status, "BACKUPS_PATH", d)

    rows = {c["key"]: c for c in status.check_backup_visibility()}
    assert set(rows) == {"backups", "backups_dsp"}, "на экране не обе базы"
    assert "backup_20260915_030000.sql" in rows["backups"]["value"], (
        "в строке основной базы стоит чужой файл — ровно та жалоба")
    assert "dsp_analytics" in rows["backups_dsp"]["value"]
    assert rows["backups"]["tone"] == "ok" and rows["backups_dsp"]["tone"] == "ok"


def test_a_missing_main_backup_is_loud_even_when_dsp_is_fresh(tmp_path, monkeypatch):
    """Бэкап основной базы пропал, аналитической — свежий. Экран обязан краснеть.

    До правки он был бы зелёным: единственная строка читала самый свежий файл, то есть
    целый дамп аналитической базы.
    """
    d = str(tmp_path)
    _touch(d, "backup_dsp_analytics_20260915_031000.sql", hours_ago=1)
    monkeypatch.setattr(status, "BACKUPS_PATH", d)

    rows = {c["key"]: c for c in status.check_backup_visibility()}
    assert rows["backups"]["tone"] == "bad", "пропавший бэкап основной базы не виден"
    assert rows["backups_dsp"]["tone"] == "ok"


def test_stale_backup_is_flagged(tmp_path, monkeypatch):
    """Возраст считается по СВОЕМУ файлу: сутки с лишним — предупреждение, двое — тревога."""
    d = str(tmp_path)
    _touch(d, "backup_20260913_030000.sql", hours_ago=60)
    _touch(d, "backup_dsp_analytics_20260914_031000.sql", hours_ago=30)
    monkeypatch.setattr(status, "BACKUPS_PATH", d)

    rows = {c["key"]: c for c in status.check_backup_visibility()}
    assert rows["backups"]["tone"] == "bad"
    assert rows["backups_dsp"]["tone"] == "warn"
