# -*- coding: utf-8 -*-
"""Колонки таблицы медиаплана в ДС — свойство ШАБЛОНА (владелец 17.11.2026: клиент просит в ДС свой формат таблицы МП;
решено не делать разовую вставку под договор, а дать шаблону выбрать колонки из готовых полей).

Где живёт: `columns` у системного блока таблицы (`{"sys": "table", "columns": [...]}`) в версии шаблона — схема базы не меняется.
При сборке список переходит в модель ДС и замораживается вместе с ней: подписанный документ печатается теми колонками,
с которыми его выпустили. Нет списка — прежние 13 колонок (`DEFAULT`), у остальных клиентов ничего не меняется.

Колонка: `{"key": <поле из CATALOG>, "label": <своя шапка, необязательно>, "value": <текст — только у const>,
"map": {<наше значение>: <как у клиента>}, "sum": false — только у объёма: не складывать в ИТОГО}`. `map` — подмена значений внутри колонки («APP» → «IN-APP / (Desktop+Mobile)»):
словарь клиента живёт в его шаблоне, а не новым полем справочника (владелец: «пока не вводим поля»).

Ячейки считаются ЗДЕСЬ, один раз (`view`), — Word (`sales/annex_docx._table`) и PDF (`components/annex/AnnexDocument.jsx`)
их только рисуют. Прежде каждая печать держала свой список колонок и свои форматы, и любой новый формат таблицы пришлось бы
писать дважды."""
from datetime import date
from typing import List, Optional

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

# key: (шапка по умолчанию, выравнивание, доля ширины, начертание, в итог)
# Доли, а не сантиметры: Word нормирует их к полосе набора, поэтому таблица остаётся в полях при любом наборе колонок.
# Доли подобраны по САМОМУ ДЛИННОМУ содержимому, а не по шапке: «12 345 678,90» кеглем 7,5 pt — ~1,7 см с полями; при доле
# 1,5 НДС переносился ПОСЛЕ ЗАПЯТОЙ и читался как другое число (замер 05.09.2026).
CATALOG = {
    "network": ("Место\nразмещения", "center", 1.8, "bold", False),
    "position": ("Позиция", "left", 3.5, "italic", False),
    "geo": ("Гео", "center", 1.1, "", False),
    "format": ("Формат", "center", 1.5, "", False),
    "device": ("Девайс", "center", 1.8, "", False),
    "rotation": ("Тип ротации\n(для медийных\nформатов)", "center", 2.0, "", False),
    "model": ("Модель\nзакупки", "center", 1.6, "", False),
    "volume": ("Объем размещения", "right", 2.2, "", True),
    "period": ("Период", "center", 2.3, "", False),
    "unit_price": ("Стоимость\nза единицу\nзакупки", "right", 1.9, "", False),
    "amount": ("Стоимость\nразмещения", "right", 2.3, "bold", True),
    "vat": ("НДС {rate}%", "right", 2.2, "", True),
    "gross": ("Стоимость\nразмещения\nс учетом НДС", "right", 2.3, "bold", True),
    # новые поля (17.11.2026) — то, что в строке уже есть или выводится из сделки
    "advertiser": ("Рекламодатель", "left", 2.4, "", False),
    "advertiser_legal": ("Рекламодатель", "left", 2.6, "", False),
    "brand": ("Бренд", "left", 2.2, "", False),
    "unit": ("Единица\nизмерения", "center", 1.6, "", False),
    "const": ("", "center", 1.6, "", False),
}
# Подписи полей для редактора шаблона — что именно попадёт в ячейку.
TITLES = {
    "network": "Место размещения (сеть)", "position": "Позиция (услуга)", "geo": "Гео", "format": "Формат",
    "device": "Девайс (WEB / APP / Кросс-девайс)", "rotation": "Тип ротации", "model": "Модель закупки",
    "volume": "Объём", "period": "Период строки", "unit_price": "Цена за единицу", "amount": "Стоимость без НДС",
    "vat": "НДС", "gross": "Стоимость с НДС", "advertiser": "Рекламодатель (имя в системе)",
    "advertiser_legal": "Рекламодатель (юр. название из справочника)", "brand": "Бренд",
    "unit": "Единица измерения (Показов / Кликов / Штук)", "const": "Свой текст в каждой строке",
}
DEFAULT = ["network", "position", "geo", "format", "device", "rotation", "model", "volume", "period", "unit_price", "amount", "vat", "gross"]
MONEY = {"unit_price", "amount", "vat", "gross"}
NAMED = ("advertiser", "advertiser_legal", "brand")          # поля из сделки, а не из строки плана
MAX_COLS = 16
MAX_LABEL = 80
MAX_MAP = 40
UNIT_WORD = {"показы": "Показов", "клики": "Кликов", "штуки": "Штук"}


def normalize(columns) -> Optional[List[dict]]:
    """Проверенный список колонок для хранения; None — «по умолчанию». Ошибка — ValueError с понятным текстом."""
    if columns in (None, []):
        return None
    if not isinstance(columns, list) or len(columns) > MAX_COLS:
        raise ValueError(f"колонок таблицы — от 1 до {MAX_COLS}")
    out = []
    for i, c in enumerate(columns, 1):
        key = c.get("key") if isinstance(c, dict) else None
        if key not in CATALOG:
            raise ValueError(f"колонка {i}: неизвестное поле «{key}»")
        item = {"key": key}
        label = (c.get("label") or "").strip()
        if len(label) > MAX_LABEL:
            raise ValueError(f"колонка {i}: шапка длиннее {MAX_LABEL} знаков")
        if label:
            item["label"] = label
        if key == "const":
            value = (c.get("value") or "").strip()
            if not value or len(value) > MAX_LABEL:
                raise ValueError(f"колонка {i}: у колонки «свой текст» нужен текст до {MAX_LABEL} знаков")
            if not label:
                raise ValueError(f"колонка {i}: у колонки «свой текст» нужна шапка")
            item["value"] = value
        m = c.get("map") or {}
        if not isinstance(m, dict) or len(m) > MAX_MAP:
            raise ValueError(f"колонка {i}: замен значений — не больше {MAX_MAP}")
        m = {str(k).strip(): str(v).strip() for k, v in m.items() if str(k).strip() and str(v).strip()}
        if m and key in MONEY | {"volume", "period", "const"}:
            raise ValueError(f"колонка {i}: замена значений бывает только у текстовых полей")
        if m:
            item["map"] = m
        if key == "volume" and c.get("sum") is False:      # у клиента объём в ИТОГО не складывают (показы с кликами и не сложить)
            item["sum"] = False
        out.append(item)
    if not any(c["key"] in MONEY for c in out):
        raise ValueError("в таблице должна остаться хотя бы одна колонка с деньгами — без неё документ не сверить с суммой")
    if out == [{"key": k} for k in DEFAULT]:
        return None
    return out


def of_blocks(blocks) -> List[dict]:
    """Колонки из блоков шаблона или модели; нет — по умолчанию."""
    t = next((b for b in blocks or [] if isinstance(b, dict) and b.get("sys") == "table"), None)
    cols = (t or {}).get("columns")
    return cols if cols else [{"key": k} for k in DEFAULT]


# ── ячейки ───────────────────────────────────────────────────────────────────────────────────────────

def _dm(d) -> str:
    if isinstance(d, date):
        return d.strftime("%d.%m.%Y")
    s = str(d or "")
    return f"{s[8:10]}.{s[5:7]}.{s[:4]}" if len(s) >= 10 else s


def _int(v) -> str:
    try:
        return f"{int(round(float(v))):,}".replace(",", " ") if v not in (None, "") else ""
    except (TypeError, ValueError):
        return ""


def _fix2(v) -> str:
    return "" if v is None else f"{float(v):,.2f}".replace(",", " ").replace(".", ",")


def _unit(r: dict) -> str:
    from app.sales import units
    u = units.addon_unit(r.get("period")) if r.get("kind") == "extra" else units.service_unit(r.get("model"))
    return UNIT_WORD.get(u, u)


def cell(r: dict, col: dict, d: dict) -> str:
    """Текст ячейки строки `r` для колонки `col`. Бонус — прочерки в деньгах (владелец 14.10.2026)."""
    k = col["key"]
    if k == "const":
        return col.get("value") or ""
    if k in MONEY:
        return "—" if r.get("bonus") else (_fix2(r.get(k)) or "—")
    if k == "volume":
        return _int(r.get("volume")) or "—"
    if k == "period":
        return f"{_dm(r.get('date_from') or d.get('period_from'))} –\n{_dm(r.get('date_to') or d.get('period_to'))}"
    if k == "position":
        v = r.get("doc_position") or r.get("position")
    elif k == "advertiser":
        v = r.get("advertiser_name")
    elif k == "advertiser_legal":
        v = r.get("advertiser_legal")
    elif k == "brand":
        v = r.get("brand_name")
    elif k == "unit":
        v = _unit(r)
    else:
        v = r.get(k)
    v = (col.get("map") or {}).get(v or "", v)
    return v or "—"


def _rate(rate) -> str:
    """22.0 → «22»: Word печатал «НДС 22.0%», PDF — «22%»; теперь оба из одной строки."""
    if rate is None:
        return ""
    f = float(rate)
    return str(int(f)) if f.is_integer() else str(f).replace(".", ",")


def label(col: dict, rate) -> str:
    return (col.get("label") or CATALOG[col["key"]][0]).replace("{rate}", _rate(rate))


def deal_names(db: Session, rows) -> dict:
    """deal_id → (имя рекламодателя, юр. название, бренд) — для колонок, которых нет в строке плана."""
    ids = sorted({r.get("deal_id") for r in rows or [] if r.get("deal_id")})
    if not ids:
        return {}
    q = db.execute(sa_text("""
        SELECT d.id, COALESCE(NULLIF(btrim(a.short_name), ''), a.name) AS adv, NULLIF(btrim(a.legal_name), '') AS legal, b.name AS brand
          FROM sales_deals d LEFT JOIN sales_advertisers a ON a.id = d.advertiser_id LEFT JOIN sales_brands b ON b.id = d.brand_id
         WHERE d.id = ANY(:d)"""), {"d": ids}).all()
    return {x.id: (x.adv, x.legal, x.brand) for x in q}


def view(db: Optional[Session], d: dict, columns: List[dict], names: Optional[dict] = None) -> dict:
    """Готовая таблица для печати: шапка, строки (или заголовок группы), итог. Итог — по СТРОКАМ таблицы, а не из шапки
    документа: колонка и её итог обязаны сходиться на бумаге."""
    rows = d.get("rows") or []
    if names is None:
        names = deal_names(db, rows) if db is not None and any(c["key"] in NAMED for c in columns) else {}
    head = [{"key": c["key"], "label": label(c, d.get("vat_rate")), "align": CATALOG[c["key"]][1], "w": CATALOG[c["key"]][2],
             "style": CATALOG[c["key"]][3]} for c in columns]
    body, total = [], {"volume": 0.0, "amount": 0.0, "vat": 0.0, "gross": 0.0}
    named_cols = any(c["key"] in NAMED for c in columns)
    missing = set()
    for r in rows:
        if r.get("group_title"):
            # бренд или рекламодатель стоит колонкой — заголовок группы «бренд · услуга» его только повторяет (у Альянса
            # таких строк нет, 17.11.2026)
            if not named_cols:
                body.append({"group": r["group_title"]})
            continue
        adv, legal, brand = names.get(r.get("deal_id")) or names.get(str(r.get("deal_id"))) or (None, None, None)
        rr = {**r, "advertiser_name": adv, "advertiser_legal": legal, "brand_name": brand}
        if legal is None and adv and any(c["key"] == "advertiser_legal" for c in columns):
            missing.add(adv)
        body.append({"cells": [cell(rr, c, d) for c in columns]})
        for k in total:
            total[k] += float(r.get(k) or 0)
    def summed(c):
        return CATALOG[c["key"]][4] and c.get("sum", True)
    first = next((i for i, c in enumerate(columns) if summed(c)), len(columns))
    foot = [("" if not summed(c) else (_int(total["volume"]) if c["key"] == "volume" else _fix2(total[c["key"]]))) for c in columns]
    return {"head": head, "rows": body, "total": {"span": first, "cells": foot},
            # юр. название пустое — не подменяем коротким именем (правило `{юр_название}`), а называем, где заполнить
            "missing": [f"юр. название рекламодателя «{a}» (справочник рекламодателей) — для колонки таблицы" for a in sorted(missing)]}
