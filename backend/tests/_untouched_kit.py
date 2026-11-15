# -*- coding: utf-8 -*-
"""Комплект УПД из пакета, которого бухгалтер ещё не касался — для фикстур, которые сами вносят ответ 1С.

До 09.11.2026 фикстуры брали первый комплект по id. На копии прода это настоящий внесённый комплект: своя операция моста,
свои файлы 1С и история — тесты падали на «уже есть» и находили чужую операцию. Пакет целиком, потому что тесты обходят
все его комплекты."""
from sqlalchemy import text


def untouched_kit(db):
    from app.master_deal.models import MasterDealUpd
    kid_rows = db.execute(text("""
        SELECT k.id FROM master_deal_upds k
         WHERE k.annex_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM master_deal_upds x WHERE x.master_deal_id = k.master_deal_id
                              AND (x.onec_state IS NOT NULL OR x.onec_invoice_no IS NOT NULL))
           AND NOT EXISTS (SELECT 1 FROM operations o JOIN master_deal_upds x ON x.id = o.master_deal_upd_id
                            WHERE x.master_deal_id = k.master_deal_id)
           AND NOT EXISTS (SELECT 1 FROM master_deal_files f WHERE f.master_deal_id = k.master_deal_id AND f.kind LIKE '%%1С%%')
           AND NOT EXISTS (SELECT 1 FROM onec_desk_events e JOIN master_deal_upds x ON x.id = e.upd_id
                            WHERE x.master_deal_id = k.master_deal_id)
         ORDER BY k.id LIMIT 20""")).scalars().all()
    # Первый комплект, у которого строки ДС сходятся с его суммой. Черновой ДС, собранный до правила «скидка СК в цене единицы»
    # (M-0029 от 05.11), не сходился — тесты падали от данных (15.11.2026). Пересобирать его здесь нельзя: проверяемый код читает
    # те же строки другим соединением и ждал бы снятия блокировки. Только чтение.
    from app.onec_desk import queue as Q
    for kid in kid_rows:
        k = db.get(MasterDealUpd, kid)
        lines = Q.card(db, k).get("lines") or []
        if lines and abs(sum(x["net"] for x in lines) - float(k.net or 0)) < 1:
            return k
    return None
