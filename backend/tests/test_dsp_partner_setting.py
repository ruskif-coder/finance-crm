"""Кабинеты DSP: боевой клиент для РК, демоклиент для нацеливания (владелец 28.09.2026).

До этого дня клиент боевых РК брался только из окружения сервера, а в админке стояли два
хеша — оба про нацеливание. Боевые РК ушли в кабинет демоклиента; теперь у каждой
сущности своё поле, и совпасть им не дают.
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import text

import app.main  # noqa: F401
from app.database import SessionLocal
from app.dsp import client as dsp_client
from app.dsp import config as dsp_config
from app.routers import traffic_catalog as tcat


def _set(key, value):
    db = SessionLocal()
    try:
        if value is None:
            db.execute(text("DELETE FROM company_settings WHERE key = :k"), {"k": key})
        else:
            db.execute(text("INSERT INTO company_settings (key, value) VALUES (:k, :v) "
                            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"),
                       {"k": key, "v": value})
        db.commit()
    finally:
        db.close()


def _get(key):
    db = SessionLocal()
    try:
        return db.execute(text("SELECT value FROM company_settings WHERE key = :k"),
                          {"k": key}).scalar()
    finally:
        db.close()


@pytest.fixture
def saved_setting():
    """Настройку стенда возвращаем как была — тест пишет в общую таблицу."""
    before = _get(dsp_client.PARTNER_SETTING)
    yield
    _set(dsp_client.PARTNER_SETTING, before)


def test_admin_setting_wins_over_env(saved_setting, monkeypatch):
    monkeypatch.setenv("DSP_PARTNER_XXHASH", "E" * 16)
    _set(dsp_client.PARTNER_SETTING, "A" * 16)
    assert dsp_client.MsClient(url="http://x/", token="t").partner_xxhash == "A" * 16
    # Явный клиент (нацеливание) настройкой не перебивается.
    assert dsp_client.MsClient(url="http://x/", token="t",
                               partner_xxhash="D" * 16).partner_xxhash == "D" * 16


def test_empty_setting_falls_back_to_env(saved_setting, monkeypatch):
    monkeypatch.setenv("DSP_PARTNER_XXHASH", "E" * 16)
    _set(dsp_client.PARTNER_SETTING, "")
    assert dsp_client.MsClient(url="http://x/", token="t").partner_xxhash == "E" * 16


def test_prod_and_demo_cabinets_may_not_match():
    db = SessionLocal()
    try:
        with pytest.raises(HTTPException) as e:
            tcat.set_site_script(tcat.SiteScriptIn(prod_partner="ab" * 8, targeting_partner="AB" * 8),
                                 db=db, user=None)
        assert e.value.status_code == 400 and "совпадают" in e.value.detail
    finally:
        db.rollback()
        db.close()


def test_targeting_hashes_fall_back_to_env(monkeypatch):
    """Все три хеша задаются и в .env (владелец 28.09.2026); настройка админки главнее."""
    db = SessionLocal()
    try:
        # Чтение настроек DSP — `app.dsp.config` (02.10.2026).
        monkeypatch.setattr(dsp_config, "setting", lambda db_, key: "")
        monkeypatch.setenv("DSP_TARGETING_PARTNER_XXHASH", "D" * 16)
        monkeypatch.setenv("DSP_TARGETING_CAMPAIGN_XXHASH", "C" * 16)
        assert tcat.targeting_cabinet(db) == ("D" * 16, "C" * 16)
        monkeypatch.setattr(dsp_config, "setting", lambda db_, key: "A" * 16)
        assert tcat.targeting_cabinet(db) == ("A" * 16, "A" * 16)
    finally:
        db.close()


def test_same_cabinet_is_caught_through_env(monkeypatch):
    """Поле боевого пусто, в .env лежит тот же хеш, что вписывают в демо, — всё равно отказ."""
    monkeypatch.setenv("DSP_PARTNER_XXHASH", "AB" * 8)
    monkeypatch.setattr(tcat, "_setting", lambda db_, key: "")
    db = SessionLocal()
    try:
        with pytest.raises(HTTPException):
            tcat.set_site_script(tcat.SiteScriptIn(targeting_partner="ab" * 8), db=db, user=None)
    finally:
        db.rollback()
        db.close()
