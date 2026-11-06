# -*- coding: utf-8 -*-
"""Черновой ДС пакета подтягивает строки из сделок (владелец 06.11.2026).

Аккаунты правят МП и после «Создать ДС» (даты, объёмы) — а строки ДС брались снимком на момент создания и дальше не менялись:
у XKKTAZ (M-0018) в тексте руками вписали «с 02.10», в таблице осталось «с 01.10». «Вернуть в раскладку» снимает черновик вместе
с правками текста — поэтому «переделать мы не можем».

Правило: пока ДС пакета НЕ подтверждён (без номера) и не ушёл клиенту, его строки — даты, объём, цена, сумма — те же, что даёт
раскладка из сделок сейчас; правки текста в конструкторе (`blocks`) не трогаются; дата ДС меняется, только если её не правили
руками (она равна прежней «по умолчанию»); комплекты УПД пересчитываются (их ещё никто не брал — до 1С неподтверждённый ДС не
доходит). Изменилась сама раскладка (другие ДС, другие группы) — не трогаем: это «вернуть в раскладку».

Вызывается при открытии карточки пакета и ДС (`routers/master_deals.master_view`, `sales/annex_print.annex_of`)."""
import logging
from typing import Optional

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

FIELDS = (("date_from", "дата начала"), ("date_to", "дата окончания"), ("volume", "объём"), ("unit_price", "цена"),
          ("amount", "сумма"))


def _drafts(db: Session, m) -> list:
    from app.master_deal import doc_sign as DSG
    from app.sales.models import SalesAnnex
    out = []
    for a in db.query(SalesAnnex).filter(SalesAnnex.master_deal_id == m.id).order_by(SalesAnnex.id):
        if a.no is not None or DSG.at_client(a) or DSG.is_signed(a) or a.rows is None:
            return []                       # хоть один ДС пакета закреплён — пакет не трогаем
        if getattr(a, "issue_kind", None) == "primary":
            return []                       # первичный ДС живёт по своим правилам (`to_annex.revert`)
        out.append(a)
    return out


def _pair(lay_ds: list, drafts: list) -> Optional[list]:
    """ДС раскладки ↔ черновики пакета: ДС допов — с sub_no, основной — без. Не сходится — None."""
    main = [a for a in drafts if a.sub_no is None]
    adds = [a for a in drafts if a.sub_no is not None]
    want_main = [d for d in lay_ds if d["kind"] != "addons"]
    want_adds = [d for d in lay_ds if d["kind"] == "addons"]
    if len(main) != len(want_main) or len(adds) != len(want_adds) or len(want_main) > 1 or len(want_adds) > 1:
        return None
    return list(zip(want_main, main)) + list(zip(want_adds, adds))


def _key(r: dict) -> tuple:
    # не row_id: сохранение МП пересоздаёт строки с новыми id — та же строка выглядела бы «убранной и новой»
    return (r.get("deal_id"), r.get("kind"), r.get("position"), r.get("device"))


def _keyed(rows) -> dict:
    """Строка → ключ с порядковым номером среди одинаковых (две строки одной позиции и площадки — по порядку)."""
    seen: dict = {}
    out = {}
    for r in rows or []:
        k = _key(r)
        seen[k] = seen.get(k, 0) + 1
        out[(k, seen[k])] = r
    return out


def _fmt(field: str, v) -> str:
    if v in (None, ""):
        return "—"
    if field.startswith("date"):
        s = str(v)[:10]
        return f"{s[8:10]}.{s[5:7]}.{s[:4]}"
    if isinstance(v, float):
        return f"{v:,.2f}".replace(",", " ").replace(".00", "")
    return str(v)


def diff(old: list, new: list, codes: dict) -> list:
    """Что поменялось в строках — человеческими словами для истории пакета."""
    before = _keyed(old)
    out = []
    for key, r in _keyed(new).items():
        o = before.pop(key, None)
        who = codes.get(r.get("deal_id")) or "строка"
        what = " · ".join(x for x in (r.get("position"), r.get("device")) if x)
        if o is None:
            out.append(f"{who} {what}: новая строка")
            continue
        for f, label in FIELDS:
            if (o.get(f) or None) != (r.get(f) or None):
                out.append(f"{who} {what}: {label} {_fmt(f, o.get(f))} → {_fmt(f, r.get(f))}")
    for o in before.values():
        out.append(f"{codes.get(o.get('deal_id')) or 'строка'} {o.get('position') or ''}: строка убрана")
    return out


def sync(db: Session, m) -> list:
    """Обновить строки черновых ДС пакета из сделок. Возвращает список изменений (пусто — ничего не менялось). Только flush."""
    from app.annex_tpl import document as tpl_doc
    from app.master_deal import layout as LY
    from app.master_deal import to_annex as TA
    from app.master_deal.models import MasterDealUpd
    from app.models import Contract
    from app.sales.models import SalesDeal
    if m.status != "согласование":
        return []
    drafts = _drafts(db, m)
    if not drafts:
        return []
    lay = LY.layout(db, m, with_src=True)
    pairs = _pair(lay["ds"], drafts)
    if pairs is None:
        return []
    codes = {d.id: d.code for d in db.query(SalesDeal).filter(SalesDeal.id.in_([r.get("deal_id") for a in drafts for r in a.rows or []] or [0]))}
    pf, pt = TA._bounds(m.period)
    changes, touched = [], []
    for ds, a in pairs:
        new = TA._snapshot(ds)
        if new == a.rows:
            continue
        changes += diff(a.rows, new, codes)
        if a.date == TA.default_date(a.rows, pf, pt):       # дату руками не правили — она по строкам
            a.date = TA.default_date(new, pf, pt)
        a.rows = new
        touched.append((a, TA.allocate(db, a, ds, lay["vat_rate"]), ds))
    if not touched:
        return []
    db.flush()
    c = db.get(Contract, m.contract_id)
    for a, deal_ids, _ in touched:                            # сумма документа — как её соберёт конструктор (НДС по строкам)
        version, _r = tpl_doc.resolve(db, c, a)
        if version is not None:
            a.total_amount = tpl_doc.live(db, c, version, a, deal_ids)["amount"]
    if db.query(MasterDealUpd).filter(MasterDealUpd.master_deal_id == m.id).count():
        ann = {ds["kind"]: a.id for ds, a in pairs}
        db.query(MasterDealUpd).filter(MasterDealUpd.master_deal_id == m.id).delete(synchronize_session=False)
        for ds, a in pairs:
            TA.write_kits(db, m, ds, ann[ds["kind"]])
    db.flush()
    return changes


def on_open(db: Session, m, user) -> None:
    """Открыли пакет или его ДС: подтянуть строки, записать в журнал, сохранить. Сбой — не мешает открыть (в лог)."""
    if m is None or m.status != "согласование":
        return
    try:
        with db.begin_nested():
            changes = sync(db, m)
    except Exception:  # noqa: BLE001
        log.exception("%s: строки ДС из сделок не подтянулись", m.code)
        return
    if not changes:
        return
    db.commit()
    from app.audit import log_action
    log_action(db, user, "master_deal_rows_synced", "master_deal", m.id, f"{m.code}: строки ДС из сделок — " + "; ".join(changes[:20]))
