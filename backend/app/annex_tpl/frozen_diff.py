# -*- coding: utf-8 -*-
"""Что поменяется в выпущенном документе — «было → станет» перед «Пересоздать» и «Обновить из сделки» (владелец 17.11.2026:
«по аналогии с DSP — показывать, что поменяется»). Повод — M-0004: бренд переименовали в справочнике, а подтверждённый ДС и
основание УПД остались со старым именем; пересборку делают вслепую, не видя, что именно она перепишет.

Сравниваются ровно те места, которые печатаются: заголовок, место и дата, пункты, реквизиты сторон, строки таблицы, сумма,
основание к закрытию;
у пакета — ещё бренд, услуга, сумма и основание каждого комплекта. Изменение — `{"where", "was", "now"}`; одинаковое не попадает."""
from typing import Optional

from app.final_recon.money import r2

PARTY_FIELDS = (("legal_name", "наименование"), ("inn", "ИНН"), ("kpp", "КПП"), ("address", "адрес"), ("position", "должность"),
                ("director", "подписант"), ("basis", "основание полномочий"))
PARTIES = (("customer", "Заказчик"), ("executor", "Исполнитель"))
ROW_FIELDS = (("brand", "строка"), ("volume", "объём"), ("unit_price", "цена за ед."), ("amount", "стоимость"), ("gross", "с НДС"))


def _txt(x) -> str:
    if isinstance(x, dict):
        return (x.get("text") or "").strip()
    return (x or "").strip() if isinstance(x, str) else ("" if x is None else str(x))


def _num(v):
    if v is None or v == "":
        return None
    try:
        return r2(v)
    except (TypeError, ValueError, ArithmeticError):
        return v


def _rows(model: dict) -> list:
    return [r for g in ((model.get("table") or {}).get("groups") or []) for r in (g.get("rows") or [])]


def _push(out: list, where: str, was, now) -> None:
    if was != now:
        out.append({"where": where, "was": was, "now": now})


def model_changes(before: Optional[dict], after: Optional[dict]) -> list:
    """Печатаемые места замороженной модели ДС: что стало иначе. Модель до конструктора (без блоков) — сравнивается то, что есть."""
    b, a = before or {}, after or {}
    out: list = []
    _push(out, "Заголовок", _txt(b.get("head")) or _txt(b.get("number")), _txt(a.get("head")) or _txt(a.get("number")))
    _push(out, "Место и дата", _txt(b.get("place")), _txt(a.get("place")))
    bb = {x.get("id"): x for x in b.get("blocks") or [] if not x.get("sys")}
    ab = [x for x in a.get("blocks") or [] if not x.get("sys")]
    for x in ab:
        name = f"Пункт {x.get('num') or ''} {x.get('title') or ''}".replace("  ", " ").strip()
        p = bb.pop(x.get("id"), None)
        _push(out, name, _txt(p) if p else "", _txt(x))
    for p in bb.values():
        _push(out, f"Пункт {p.get('num') or ''} {p.get('title') or ''}".replace("  ", " ").strip(), _txt(p), "")
    from app.annex_tpl import table_cols as TC
    cb, ca = TC.of_blocks(b.get("blocks")), TC.of_blocks(a.get("blocks"))
    if cb != ca:
        _push(out, "Таблица · колонки", " | ".join(TC.label(c, None) for c in cb).replace(chr(10), " "),
              " | ".join(TC.label(c, None) for c in ca).replace(chr(10), " "))
    rb, ra = _rows(b), _rows(a)
    for i in range(max(len(rb), len(ra))):
        x, y = (rb[i] if i < len(rb) else {}), (ra[i] if i < len(ra) else {})
        label = y.get("brand") or x.get("brand") or f"строка {i + 1}"
        for key, cap in ROW_FIELDS:
            was, now = x.get(key), y.get(key)
            if key != "brand":
                was, now = _num(was), _num(now)
            _push(out, f"Таблица · {label} · {cap}" if key != "brand" else f"Таблица · строка {i + 1}", was, now)
    for side, cap in PARTIES:
        x, y = b.get(side) or {}, a.get(side) or {}
        for key, name in PARTY_FIELDS:
            _push(out, f"{cap} · {name}", x.get(key), y.get(key))
    _push(out, "Сумма с НДС", _num(b.get("amount")), _num(a.get("amount")))
    _push(out, "Основание к закрытию", _txt(b.get("closing_basis")), _txt(a.get("closing_basis")))
    return out


def kit_changes(before: list, after: list) -> list:
    """Комплекты УПД пакета (`to_annex.upds_of`): бренд, услуга, сумма, основание — по номеру УПД."""
    ib = {k["upd_no"]: k for k in before or []}
    out: list = []
    for k in after or []:
        p = ib.get(k["upd_no"]) or {}
        n = k["upd_no"]
        _push(out, f"УПД № {n} · бренд", p.get("brand"), k.get("brand"))
        _push(out, f"УПД № {n} · услуга", p.get("service"), k.get("service"))
        _push(out, f"УПД № {n} · сумма с НДС", _num(p.get("gross")), _num(k.get("gross")))
        _push(out, f"УПД № {n} · основание", _txt(p.get("basis")), _txt(k.get("basis")))
    return out
