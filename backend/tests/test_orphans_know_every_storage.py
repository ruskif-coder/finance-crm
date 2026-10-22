# -*- coding: utf-8 -*-
"""Экран сирот знает каждое хранилище (аудит 2.6.76, п. 1.17; живо в 2.7.0 — плюс сканы мастер-сделок и вложения баг-репортов).
Хранилище, не внесённое в `PATH_COLUMNS`, показывает свои живые файлы сиротами. Прибор: каждая колонка с ключом файла в базе
(`path`, `*_path`) и каждая колонка песочницы (`sandbox_token`) — в списках экрана, или названа здесь как не-ключ."""
from sqlalchemy import text

from app.database import SessionLocal
from app.system import status as S

# `entry_path` — точка входа ВНУТРИ распакованной песочницы, не ключ файла хранилища.
NOT_A_STORAGE_KEY = {("creative_check", "entry_path"), ("launch_prep_creative_file", "entry_path")}


def _cols(where):
    db = SessionLocal()
    try:
        return {tuple(r) for r in db.execute(text(f"""SELECT table_name, column_name FROM information_schema.columns
                 WHERE table_schema = 'public' AND data_type IN ('character varying', 'text') AND {where}"""))}
    finally:
        db.close()


def test_every_file_key_column_is_known():
    keys = _cols("(column_name = 'path' OR column_name LIKE '%\_path')") - NOT_A_STORAGE_KEY
    missing = keys - set(S.PATH_COLUMNS)
    assert not missing, f"хранилища не в PATH_COLUMNS: {sorted(missing)}"


def test_every_sandbox_column_is_known():
    missing = _cols("column_name = 'sandbox_token'") - set(S.SANDBOX_COLUMNS)
    assert not missing, f"песочницы не в SANDBOX_COLUMNS: {sorted(missing)}"
