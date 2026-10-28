# -*- coding: utf-8 -*-
"""Входы под ролями для обхода экранов браузером (`e2e/walk_screens.py`, 27.10.2026) — ТОЛЬКО для локального стенда.

Для каждой роли берётся первый активный пользователь с ней и выпускается обычный токен входа (8 ч) — то же, что кладёт в
localStorage страница входа: token, role, role_label, is_admin, permissions, name. Пароли не нужны и не трогаются, учёток
не заводим. Плюс образцы карточек (последние сделка, МП, контрагент, площадка, РК, ДС) — чтобы обход открыл и экраны с номером.

Токены пишутся ТОЛЬКО в файл `--out` и не печатаются: файл живёт до конца прогона, `e2e/run.sh` удаляет его сам.

    docker exec finance_backend python -m scripts.e2e_sessions --out /tmp/e2e_sessions.json admin role_7 role_8"""
import argparse
import json
import os
import sys

import app.model_registry  # noqa: F401
from sqlalchemy import text

from app.database import SessionLocal
from app.models import Role, User
from app.permissions import get_permissions_for_user
from app.routers.auth import create_access_token, token_claims

SAMPLES = {
    "deal": "SELECT t.id::text FROM sales_deals t ORDER BY t.id DESC LIMIT 1",
    "mp": "SELECT t.id::text FROM sales_media_plans t ORDER BY t.id DESC LIMIT 1",
    "counterparty": "SELECT t.id::text FROM counterparties t ORDER BY t.id DESC LIMIT 1",
    "publisher": "SELECT t.id::text FROM sales_publishers t ORDER BY t.id DESC LIMIT 1",
    "annex": "SELECT t.id::text FROM sales_annexes t ORDER BY t.id DESC LIMIT 1",
    "campaign": "SELECT d.code FROM ad_campaign a JOIN sales_deals d ON d.id = a.deal_id ORDER BY a.id DESC LIMIT 1",
    "master": "SELECT code FROM master_deals ORDER BY id DESC LIMIT 1",
    # карточка договора (28.10.2026): договор с ДС — у него заполнены все блоки
    "contract": "SELECT t.contract_id::text FROM sales_annexes t ORDER BY t.id DESC LIMIT 1",
}


def session_of(db, role: Role) -> dict:
    # согласие не принято — API отвечает consent_required и уводит на вход: обход проверял бы не экраны, а согласие
    u = (db.query(User).filter(User.role_id == role.id, User.is_active == 1, User.consent_accepted_at.isnot(None))
         .order_by(User.id).first())
    if u is None:
        return None
    return {"role": role.key, "role_label": role.label or role.key, "user_id": u.id,
            "storage": {"token": create_access_token(token_claims(u)), "role": role.key, "role_label": role.label or "",
                        "is_admin": "1" if role.key == "admin" else "0",
                        "permissions": json.dumps(get_permissions_for_user(db, u), ensure_ascii=False), "name": u.name or ""}}


def samples(db) -> dict:
    out = {}
    for k, sql in SAMPLES.items():
        try:
            out[k] = db.execute(text(sql)).scalar()
        except Exception:                      # таблицы нет на этом стенде — образца нет, обход его пропустит
            db.rollback()
            out[k] = None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("roles", nargs="+")
    a = ap.parse_args()
    if os.getenv("DOMAIN", "localhost") != "localhost":       # на проде контейнер тот же — боевые токены не выпускаем
        sys.exit("Отказ: только локальный стенд (DOMAIN=localhost)")
    db = SessionLocal()
    try:
        roles = {r.key: r for r in db.query(Role).filter(Role.key.in_(a.roles)).all()}
        sessions, missing = [], []
        for key in a.roles:
            s = session_of(db, roles[key]) if key in roles else None
            (sessions.append(s) if s else missing.append(key))
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump({"sessions": sessions, "samples": samples(db)}, f, ensure_ascii=False)
        print(f"входов: {len(sessions)}" + (f"; нет активного пользователя с принятым согласием у ролей: {', '.join(missing)}" if missing else ""))
    finally:
        db.close()


if __name__ == "__main__":
    main()
