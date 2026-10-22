# -*- coding: utf-8 -*-
"""Реестр мастер-сделок: итоговая сверка сделки считается один раз за запрос (аудит v2.6.0→v2.7.0, F1; 21.10.2026).

Замер на стенде: 11 пакетов — 744 запроса (68 на пакет). «Что сделать» по черновикам, раскладка и эффективность пересчитывали
сверку одной сделки до трёх раз. Кэш живёт только внутри одного вызова реестра — пути записи его не видят."""
import collections

import app.model_registry  # noqa: F401


def test_recon_is_computed_once_per_deal_and_memo_does_not_leak():
    from app.database import SessionLocal
    from app.final_recon import closing as CL
    from app.master_deal import registry as R
    from app.models import User
    db = SessionLocal()
    calls = collections.Counter()
    orig = CL._compute

    def spy(db_, d, *a, **k):
        calls[d.id] += 1
        return orig(db_, d, *a, **k)
    try:
        CL._compute = spy
        u = db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
        R.rows(db, u)
        assert calls and max(calls.values()) == 1, dict(calls)
        assert "cl_memo" not in db.info, "кэш сверки остался в сессии — пути записи увидели бы устаревшее"
    finally:
        CL._compute = orig
        db.rollback()
        db.close()
