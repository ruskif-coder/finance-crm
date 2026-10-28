# -*- coding: utf-8 -*-
"""Сборка данных ДС из версии шаблона (спринт 2, 14.10.2026): шаблон + договор + сделки → модель документа.

Модель одна на экран, проверку полноты и (позже) на PDF и Word: числа и тексты считаются здесь один раз.
Что переносится из старого модуля `app/sales/annex.py` и как: нумерация и дата, реквизиты сторон с проверкой полноты, строки медиаплана и допов,
НДС по строкам — вызовы тех же функций; тексты пунктов, подстановки и группировка таблицы — здесь.

Деньги. «Сумма» в тексте — итог С НДС (в шаблоне: «сумму в размере …, включая НДС …»), НДС документа складывается из строк, а не извлекается из итога:
извлечение расходится на копейки уже при двух строках (замер 06.09.2026). Числа в тексте и в таблице — от одного расчёта, поэтому разойтись не могут;
`consistency` всё равно сверяет их и подтверждение ДС при расхождении отказывает.
"""
import re
from typing import List, Optional

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app import own_company
from app.annex_tpl.contract_check import gaps as contract_gaps
from app import vat as vat_rules
from app.annex_tpl.check import MAX_TEXT, numbering, unknown_keys, zone_at
from app.annex_tpl.legal_name import legal_name
from app.annex_tpl.models import AnnexTplTemplate
from app.annex_tpl.subs import SUBS
from app.annex_tpl.service import AnnexTplError
from app.final_recon import money as M
from app.sales import annex as A
from app.sales.rubles import rub_phrase, vat_of

_KEY = re.compile(r"\{([^{}]+)\}")
NBSP = " "


def _num(x) -> str:
    """Число с разрядами и запятой: 671 000,00."""
    return f"{float(x):,.2f}".replace(",", NBSP).replace(".", ",")


def _date(d) -> str:
    return d.strftime("%d.%m.%Y") if d else ""


def _advertisers(db: Session, deal_ids) -> str:
    ids = [i for i in (deal_ids or []) if i]
    if not ids:
        return ""
    rows = db.execute(sa_text("""
        SELECT DISTINCT COALESCE(NULLIF(btrim(a.short_name), ''), a.name) AS adv
          FROM sales_deals d JOIN sales_advertisers a ON a.id = d.advertiser_id
         WHERE d.id = ANY(:d)
    """), {"d": ids}).scalars().all()
    return ", ".join(sorted(x for x in rows if x))


def _brands_only(db: Session, deal_ids) -> str:
    """Названия брендов сделок БЕЗ рекламодателя — для основания закрывающих документов."""
    ids = [i for i in (deal_ids or []) if i]
    if not ids:
        return ""
    rows = db.execute(sa_text("""
        SELECT DISTINCT b.name FROM sales_deals d JOIN sales_brands b ON b.id = d.brand_id WHERE d.id = ANY(:d)
    """), {"d": ids}).scalars().all()
    return ", ".join(sorted(x for x in rows if x))


def _rows_with_tax(db: Session, deal_ids, rate: float) -> list:
    """Строки таблицы: размещения и допы плана, НДС НАЧИСЛЯЕТСЯ поверх стоимости без налога (22/100, а не 22/122)."""
    out = []
    brands = A.deal_brands(db, deal_ids)
    for r in A.plan_rows(db, deal_ids):
        net = r.get("amount")
        vat = M.line_vat(net, rate) if net else None       # НДС строки — общим правилом контура (аудит 2.7.0, п. 2.4)
        out.append({**r,
                    "brand": brands.get(r.get("deal_id")) or "",
                    "vat": vat,
                    # Итог строки = стоимость + НДС строки: независимое округление двух величин расходилось на копейку.
                    "gross": M.r2(net + vat) if net else None,
                    # Бонус: полная скидка — строка остаётся в таблице, деньги (и цена за единицу) — прочерки (владелец 14.10.2026)
                    "bonus": bool(r.get("bonus")) or not net})
    return out


def _snapshot_with_tax(rows: list, rate: float) -> list:
    """Строки снимка раскладки с НДС поверх стоимости — тем же правилом, что строки плана. Даты снимка приходят строками."""
    from datetime import date as _d
    out = []
    for r in rows or []:
        net = r.get("amount")
        vat = M.line_vat(net, rate) if net else None       # НДС строки — общим правилом контура (аудит 2.7.0, п. 2.4)
        dates = {k: (_d.fromisoformat(r[k][:10]) if isinstance(r.get(k), str) and r.get(k) else r.get(k)) for k in ("date_from", "date_to")}
        out.append({**r, **dates, "vat": vat, "gross": round(net + vat, 2) if net else None,
                    "bonus": bool(r.get("bonus")) or (not net and r.get("kind") != "discount")})
    return out


def _groups(rows: list) -> list:
    """Таблица «бренд → услуги → допы»: порядок брендов — по первому появлению, внутри бренда размещения, затем допы."""
    order, by = [], {}
    for r in rows:
        key = r.get("brand") or ""
        if key not in by:
            by[key] = []
            order.append(key)
        by[key].append(r)
    groups = []
    for key in order:
        part = by[key]
        part = [x for x in part if x.get("kind") != "extra"] + [x for x in part if x.get("kind") == "extra"]
        groups.append({"brand": key or None, "rows": part, "totals": _totals(part)})
    return groups


def _totals(rows: list) -> dict:
    return {"volume": sum(float(r.get("volume") or 0) for r in rows),
            "net": round(sum(float(r.get("amount") or 0) for r in rows), 2),
            "vat": round(sum(float(r.get("vat") or 0) for r in rows), 2),
            "gross": round(sum(float(r.get("gross") or 0) for r in rows), 2)}


def _short(d) -> str:
    return d.strftime("%d.%m.%y") if d else ""


def _values(*, no, contract, period_from, period_to, rate, gross, vat, brand, advertisers, brand_only="", doc_date=None,
            service: str = "") -> dict:
    return {
        "услуга": service,
        "бренд_название": brand_only, "сеть": A.PLACEMENT_NETWORK,
        "дата_дс_кратко": _short(doc_date), "договор_дата_кратко": _short(contract.contract_date),
        "рекламодатель": advertisers, "бренд": brand or "",
        "период_с": _date(period_from), "период_по": _date(period_to),
        "сумма": _num(gross), "сумма_прописью": rub_phrase(gross),
        "ндс_ставка": f"{rate:g}", "ндс_сумма": _num(vat), "ндс_сумма_прописью": rub_phrase(vat),
        "номер_дс": str(no), "договор_номер": contract.contract_number or "", "договор_дата": _date(contract.contract_date),
    }


def _parts(text: str, values: dict) -> list:
    """Текст пункта кусками: обычный и подставленное значение (с признаком «пусто») — экран подсвечивает подстановки."""
    out, last = [], 0
    for m in _KEY.finditer(text or ""):
        if m.start() > last:
            out.append({"t": text[last:m.start()]})
        key = m.group(1)
        if key in values:
            v = values[key]
            out.append({"t": v, "key": key, "empty": v == ""})
        else:
            out.append({"t": m.group(0), "key": key, "unknown": True})
        last = m.end()
    if last < len(text or ""):
        out.append({"t": text[last:]})
    return out


# Основание в закрывающих документах (УПД и счёт) — формулировка по образцу владельца 14.10.2026; правится на экране ДС.
CLOSING_KEY = "closing_basis"
CLOSING_DEFAULT = ("Размещение рекламных материалов бренда «{бренд_название}», в сети {сеть}, согласно Доп.соглашению {номер_дс} "
                   "от {дата_дс_кратко} к Договору {договор_номер} от {договор_дата_кратко}г., с {период_с} по {период_по}г.")
# Начало основания по составу ДС (владелец 21.10.2026): допы — «оказание дополнительных услуг ({услуга})», смешанный — и то, и другое.
CLOSING_HEAD = "Размещение рекламных материалов бренда «{бренд_название}», в сети {сеть}"
CLOSING_HEAD_ADDONS = "Оказание дополнительных услуг ({услуга}) для бренда «{бренд_название}»"
CLOSING_HEAD_MIXED = "Размещение рекламных материалов и оказание дополнительных услуг ({услуга}) бренда «{бренд_название}», в сети {сеть}"
# Пункт 1 ДС допов — стандарт, пока аккаунт не правил текст; пункт 1 основного ДС на ДС допов не наследуется.
P1_KEY = "p1"
P1_ADDONS = ("На условиях настоящего Приложения № {номер_дс} (далее по тексту – «Приложение») и Договора Исполнитель принимает на себя "
             "обязанность оказать дополнительные услуги: {услуга} (далее – Услуги) для {рекламодатель} по брендам {бренд} "
             "в период с {период_с} по {период_по}, согласно нижеследующим условиям:")
ADDONS_STD = "стандарт для доп. услуг"


def composition(rows) -> str:
    """Состав ДС: «addons» — только допы, «mixed» — размещение и допы, «main» — только размещение. Скидка состав не меняет."""
    kinds = {r.get("kind") for r in rows or [] if r.get("kind") != "discount"}
    if kinds == {"extra"}:
        return "addons"
    return "mixed" if "extra" in kinds else "main"


def closing_template_for(rows) -> str:
    """Шаблон основания по составу ДС: меняется только начало, подстановки — те же."""
    c = composition(rows)
    if c == "addons":
        return CLOSING_DEFAULT.replace(CLOSING_HEAD, CLOSING_HEAD_ADDONS, 1)
    return CLOSING_DEFAULT.replace(CLOSING_HEAD, CLOSING_HEAD_MIXED, 1) if c == "mixed" else CLOSING_DEFAULT


def _addon_phrases(db: Session) -> dict:
    rows = db.execute(sa_text("SELECT name, doc_phrase FROM sales_addon_services")).all()
    return {n: (p or "").strip() for n, p in rows if (p or "").strip()}


def _lower_first(s: str) -> str:
    """«Комплект …» → «комплект …»; латинские имена (Sales-Lift) и аббревиатуры не трогаем."""
    return s[:1].lower() + s[1:] if s and "А" <= s[0] <= "Я" and not s[:2].isupper() else s


def service_text(db: Session, deal_ids, rows) -> str:
    """Подстановка {услуга} — что оказываем ДОПАМИ этого ДС: формулировки из справочника доп. услуг (нет — название со строчной), по
    первому появлению, без повторов. Услугу сделки сюда не берём (владелец 21.10.2026: у сделки это продукт площадки, «еФарм»), поэтому
    в ДС только с размещением подстановка пустая. `deal_ids` оставлен для единообразия подписи."""
    phrases = _addon_phrases(db)
    out = [phrases.get((r.get("position") or "").strip()) or _lower_first((r.get("position") or "").strip())
           for r in rows or [] if r.get("kind") == "extra"]
    return ", ".join(dict.fromkeys(x for x in out if x))


def closing_resolve(template: str, values: dict, edited: bool, inherited_from: Optional[str] = None) -> dict:
    parts = _parts(template, values)
    return {"template": template, "text": "".join(p["t"] for p in parts), "parts": parts, "edited": edited,
            "inherited_from": inherited_from, "empty": sorted({p["key"] for p in parts if p.get("empty")})}


def validate_edit(blocks: list, key: str, text) -> Optional[str]:
    """Можно ли править этот блок и годится ли текст. Правит аккаунт: ТОЛЬКО зона до таблицы МП и основание закрывающих; после таблицы — юрист."""
    if not isinstance(text, str) or len((text or "").strip()) < 3:
        return "Текст не может быть пустым"
    if len(text) > MAX_TEXT:
        return f"Текст длиннее {MAX_TEXT} знаков"
    bad = unknown_keys(text)
    if bad:
        return "Неизвестная подстановка " + ", ".join("{" + k + "}" for k in bad)
    if key == CLOSING_KEY:
        return None
    for i, b in enumerate(blocks):
        if b.get("id") == key and not b.get("sys"):
            return None if zone_at(blocks, i) == "acc" else "Этот пункт правит только юрист (зона после таблицы МП)"
    return "Нет такого пункта в шаблоне"


def _blocks(blocks: list, values: dict, edits: Optional[dict] = None, defaults: Optional[dict] = None) -> tuple:
    edits = edits or {}
    defaults = defaults or {}
    num = numbering(blocks)
    out, empties = [], {}
    for i, b in enumerate(blocks):
        if b.get("sys"):
            out.append({"id": b["id"], "sys": b["sys"], "title": b.get("title")})
            continue
        zone = zone_at(blocks, i)
        edited = zone == "acc" and b["id"] in edits
        # По умолчанию — текст прошлого ДС этого договора: привязка по id пункта шаблона (владелец 14.10.2026). Пункта нет в шаблоне или он
        # стал юридическим — привязка молча не применяется.
        inherited = zone == "acc" and not edited and b["id"] in defaults
        source = edits[b["id"]] if edited else (defaults[b["id"]]["text"] if inherited else (b.get("text") or ""))
        parts = _parts(source, values)
        for p in parts:
            if p.get("empty"):
                empties[p["key"]] = True
        out.append({"id": b["id"], "title": b.get("title"), "num": num[b["id"]], "sub": bool(b.get("sub")),
                    "req": bool(b.get("req")), "pin": bool(b.get("pin")), "zone": zone,
                    "template_text": b.get("text"), "source_text": source, "edited": edited,
                    "inherited_from": defaults[b["id"]]["from"] if inherited else None,
                    "text": "".join(p["t"] for p in parts), "parts": parts})
    return out, empties


def _missing(empties: dict, executor: dict, customer: dict, rows: list, brand) -> List[dict]:
    out = []
    for key in empties:
        info = SUBS.get(key, {})
        label = info.get("label") or key.replace("_", " ")
        out.append({"text": f"не заполнено: {label}", "where": info.get("where") or "данные сделки и договора"})
    out += [{"text": f"исполнитель: {m}", "where": "карточка нашего юрлица (Справочники → Контрагенты)"} for m in executor["missing"]]
    out += [{"text": f"заказчик: {m}", "where": "карточка контрагента или экран ДС (реквизиты подписанта)"} for m in customer["missing"]]
    if not rows:
        out.append({"text": "в таблице нет строк", "where": "медиаплан сделки"})
    elif not any(r.get("amount") for r in rows):
        out.append({"text": "ни у одной строки нет цены", "where": "медиаплан сделки"})
    return out


def assemble(db: Session, contract, version, *, period_from, period_to, deal_ids=None,
             amount: Optional[float] = None, no: Optional[int] = None, edits: Optional[dict] = None, doc_date=None,
             defaults: Optional[dict] = None, rows_override: Optional[list] = None, sub_no: Optional[str] = None) -> dict:
    """Модель документа по версии шаблона. Ничего не пишет в базу: это предпросмотр; запись — при подтверждении."""
    if version is None:
        raise AnnexTplError(409, "У договора не определён шаблон ДС")
    tpl = db.query(AnnexTplTemplate).filter_by(id=version.template_id).first()
    base = db.query(AnnexTplTemplate).filter_by(id=tpl.base_template_id).first() if tpl and tpl.base_template_id else None

    payer = contract.counterparty
    us = contract.own_company or own_company.sole(db)
    # Ставка — с юрлица, от которого услуги (владелец 14.10.2026); не задана — по закону на дату периода.
    # Одна функция с раскладкой мастер-сделки: юрлицо на дату составления (владелец 21.10.2026).
    rate = vat_rules.for_document(db, contract, doc_date or A.annex_date(period_from))
    n = no or A.next_no(db, contract)

    # ДС мастер-сделки — строки из снимка раскладки (пин сверки, скидка, переносы, группы), не из МП заново (15.10.2026).
    rows = _snapshot_with_tax(rows_override, rate) if rows_override is not None else _rows_with_tax(db, deal_ids, rate)
    if rows:
        totals = _totals(rows)
        gross, vat = totals["gross"], totals["vat"]          # НДС документа складывается из строк
    else:
        gross = float(amount or 0)
        vat = vat_of(gross, rate) if gross else 0.0
    groups = _groups(rows)

    doc_date = doc_date or A.annex_date(period_from)
    no_text = f"{n}-{sub_no}" if sub_no else n
    values = _values(no=no_text, contract=contract, period_from=period_from, period_to=period_to, rate=rate, gross=gross, vat=vat,
                     brand=A.deal_brand(db, deal_ids), advertisers=_advertisers(db, deal_ids),
                     brand_only=_brands_only(db, deal_ids), doc_date=doc_date, service=service_text(db, deal_ids, rows))
    # `None` в правках — «явно по шаблону»: прошлый ДС не наследуется. Строки — собственные правки этого ДС.
    reset = {k for k, v in (edits or {}).items() if v is None}
    edits = {k: v for k, v in (edits or {}).items() if isinstance(v, str) and v.strip()}
    defaults = {k: v for k, v in (defaults or {}).items() if k not in reset and k not in edits}
    if composition(rows) == "addons":     # ДС допов: свой пункт 1 и основание; тексты основного ДС не наследуются
        for k in (P1_KEY, CLOSING_KEY):
            defaults.pop(k, None)
        if P1_KEY not in edits and P1_KEY not in reset:
            defaults[P1_KEY] = {"text": P1_ADDONS, "from": ADDONS_STD}
    blocks, empties = _blocks(version.blocks, values, edits, defaults)
    closing_text = edits.get(CLOSING_KEY)
    closing_default = defaults.get(CLOSING_KEY)
    from app.signers.service import party_of
    ex, cu = party_of(db, us, contract, "исполнитель", doc_date), party_of(db, payer, contract, "заказчик", doc_date)
    ex["legal_name"], cu["legal_name"] = legal_name(ex.get("name")), legal_name(cu.get("name"))

    return {
        "no": n, "number": (f"ДС № {no_text}" if rows_override is not None else f"Приложение № {n}"), "date": doc_date,
        "period_from": period_from, "period_to": period_to,
        "signed_place": getattr(us, "signed_place", None) or "г. Москва",
        "contract": {"id": contract.id, "number": contract.contract_number, "date": contract.contract_date,
                     "link": contract.document_link, "has_file": bool(contract.attached_filename)},
        "executor": ex, "customer": cu,
        "template": {"template_id": version.template_id, "version_id": version.id, "version": version.version,
                     "scope": tpl.scope if tpl else None,
                     "title": (tpl.title if tpl and tpl.title else (base.title if base else None))},
        "vat_rate": rate, "amount": gross, "amount_words": rub_phrase(gross), "vat": vat, "vat_words": rub_phrase(vat),
        "values": values, "blocks": blocks, "table": {"groups": groups, "totals": _totals(rows)},
        # `edits` — ЭФФЕКТИВНЫЕ правки (свои и унаследованные): их и замораживает подтверждение, чтобы следующий ДС наследовал по цепочке.
        "edits": {**{k: v["text"] for k, v in defaults.items() if k in {b["id"] for b in blocks if b.get("zone") == "acc"} or k == CLOSING_KEY},
                  **edits,
                  # явный сброс «по шаблону» тоже замораживается — иначе следующий ДС снова унаследует текст из-за этого ДС
                  **{k: None for k in reset}},
        "closing_basis": closing_resolve(closing_text or (closing_default["text"] if closing_default else closing_template_for(rows)), values, bool(closing_text),
                                         closing_default["from"] if closing_default and not closing_text else None),
        # договор и реквизиты сторон — то, без чего документ неликвиден (21.10.2026); подписанта проверяет `party` выше
        "missing": _missing(empties, ex, cu, rows, values["бренд"]) + contract_gaps(db, contract),
        "consistency": consistency(gross, vat, rows),
    }


def consistency(gross: float, vat: float, rows: list) -> dict:
    """Сверка чисел текста и таблицы: подтверждение ДС при расхождении отказывает (в тексте одна сумма, в таблице другая — это видит подписант)."""
    t = _totals(rows) if rows else None
    if t is None:
        return {"ok": True, "details": []}
    bad = []
    if abs(t["gross"] - round(gross, 2)) >= 0.01:
        bad.append(f"сумма в тексте {_num(gross)} не сходится с итогом таблицы {_num(t['gross'])}")
    if abs(t["vat"] - round(vat, 2)) >= 0.01:
        bad.append(f"НДС в тексте {_num(vat)} не сходится с итогом таблицы {_num(t['vat'])}")
    if abs(round(t["net"] + t["vat"], 2) - t["gross"]) >= 0.02:
        bad.append("итог без НДС плюс НДС не равен итогу с НДС")
    return {"ok": not bad, "details": bad}
