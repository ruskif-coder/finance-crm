# -*- coding: utf-8 -*-
"""Имя скачиваемого креатива в кабинете паблишера (владелец 30.09.2026).

Формат: Рекламодатель-Бренд-площадка-период-услуга[-название креатива].расширение, всё
латиницей. Рекламодатель — английское имя из справочника, иначе наше короткое. Кода сделки
в имени НЕТ: паблишеру он не показывается (владелец 30.09.2026).
Раньше площадка получала файл под именем, которое дал клиент (`banner_final_v3.zip`),
и в её папке загрузок было не понять, к какой кампании он относится.

Части разделяются дефисом, пробелы внутри части — подчёркиванием; транслитерация —
та же таблица, что у имён Weborama (`weborama.naming.translit`), чтобы одна и та же
кириллица не латинизировалась двумя способами.
"""
import os
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.weborama.naming import translit

MAX_LEN = 150          # запас до предела имени файла в ОС и в заголовке ответа


def _period(date_from: Optional[date], date_to: Optional[date]) -> str:
    """Финансовый период сделки: `2026-10`, а если сделка на несколько месяцев —
    `2026-09_2026-10`."""
    a = date_from.strftime("%Y-%m") if date_from else ""
    b = date_to.strftime("%Y-%m") if date_to else ""
    if a and b and a != b:
        return f"{a}_{b}"
    return a or b


def build_name(advertiser, brand, publisher, period, service, title, original: str) -> str:
    parts = [translit(str(p)) for p in (advertiser, brand, publisher, period, service, title)
             if p]
    stem = "-".join(p for p in parts if p) or "creative"
    ext = os.path.splitext(original or "")[1].lower()
    ext = ext if ext and len(ext) <= 6 else ""
    return stem[:MAX_LEN - len(ext)] + ext


def for_pair(db: Session, pair_id: int, original: str) -> str:
    """Имя файла креатива пары «креатив × площадка» для кабинета."""
    r = db.execute(text("""
        SELECT COALESCE(NULLIF(a.name_en, ''), a.short_name, a.name) AS advertiser,
               b.name AS brand, p.domain, p.name AS pub_name,
               d.period_from, d.period_to, d.product, s.title
          FROM launch_prep_pair pr
          JOIN launch_prep_creative_set s ON s.id = pr.set_id
          JOIN launch_prep_target t ON t.id = pr.target_id
          JOIN sales_deals d ON d.id = s.deal_id
          JOIN sales_publishers p ON p.id = t.publisher_id
          LEFT JOIN sales_brands b ON b.id = d.brand_id
          LEFT JOIN sales_advertisers a ON a.id = d.advertiser_id
         WHERE pr.id = :p"""), {"p": pair_id}).mappings().first()
    if not r:
        return original or "creative"
    return build_name(r["advertiser"], r["brand"], r["domain"] or r["pub_name"],
                      _period(r["period_from"], r["period_to"]), r["product"], r["title"],
                      original)
