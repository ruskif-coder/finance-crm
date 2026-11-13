# -*- coding: utf-8 -*-
"""XML счёта на оплату для Диадока по формату ФНС: КНД 1110379, приказ ЕД-7-26/29@, схема ON_CHETOP_1_998_01_05_01_04
(действует с 01.01.2026, лежит рядом: `xsd/`). Владелец 12.11.2026: «формировать xml для диадока на основании нашего счёта,
чтобы не заполнять данные вручную».

Номер и дата счёта — из 1С (то, что внесла бухгалтер), суммы — строки нашей заявки: та же сверка, что проходит «Внести»,
значит XML не второй источник. Свой номер система не придумывает: нет номера или даты из 1С — файла нет.

Имя файла — ON_CHETOP_<получатель>_<отправитель>_ГГГГММДД_GUID. Идентификатор участника — код ЭДО (`edo_id`), а без него —
ИНН_КПП, как 1С называет XML УПД, который бухгалтер к нам загружает. Кодировка — windows-1251 (требование формата)."""
import re
import threading
import uuid
from datetime import date, datetime
from typing import Optional
from xml.sax.saxutils import quoteattr, escape

KND, VERSION, PROGRAM = "1110379", "5.01", "SIMB-AD ERP"
PURPOSE_MAX = 210          # НазнПл: T(1-210)


class InvoiceXmlError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _d(v) -> str:
    """ДД.ММ.ГГГГ из date или ISO-строки."""
    if isinstance(v, (date, datetime)):
        return v.strftime("%d.%m.%Y")
    t = str(v)[:10]
    if len(t) == 10 and t[2] == "." and t[5] == ".":            # уже ДД.ММ.ГГГГ — как в XML УПД 1С
        return datetime.strptime(t, "%d.%m.%Y").strftime("%d.%m.%Y")
    return datetime.strptime(t, "%Y-%m-%d").strftime("%d.%m.%Y")


def _m(x) -> str:
    return f"{round(float(x or 0), 2):.2f}"


def _no_vat(r) -> bool:
    """Без НДС: ставки нет или 0 (у нас нулевой ставки не бывает — 0 в заявке значит «ставку не задали», ревью 12.11.2026)."""
    return r is None or float(r) == 0


def _rate(r) -> str:
    """Ставка строкой формата: 22 → «22%», без ставки — «без НДС»."""
    if _no_vat(r):
        return "без НДС"
    r = float(r)
    return f"{int(r)}%" if r == int(r) else f"{r:g}%".replace(".", ",")


_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _attrs(**kw) -> str:
    # управляющие символы из базы сделали бы XML негодным (ревью 12.11.2026)
    return "".join(f" {k}={quoteattr(_CTRL.sub(' ', str(v)))}" for k, v in kw.items() if v not in (None, ""))


def participant_id(p: dict) -> str:
    raw = (p.get("edo_id") or "").strip() or f"{p.get('inn') or ''}_{p.get('kpp') or ''}".strip("_")
    return re.sub(r"[^0-9A-Za-zА-Яа-я_\-]", "", raw)       # в имя файла — без «/» и «..»


def _sole_trader(p: dict) -> str:
    """ИП — по ИНН из 12 цифр: СвИП с ФИО из названия («ИП Петров Пётр Петрович»), иначе схема его не пропустит."""
    name = re.sub(r"^\s*(ИП|индивидуальный предприниматель)\s+", "", p["name"], flags=re.I)
    fio = _fio(name, f"Покупатель-ИП «{p['name']}»: в названии нет фамилии и имени — XML счёта не собрать")
    return f"<СвИП{_attrs(ИННФЛ=p['inn'])}>{fio}</СвИП>"


def _party(tag: str, p: dict, with_bank: bool = False) -> str:
    inn = re.sub(r"\D", "", p.get("inn") or "")
    ul = _sole_trader(p) if len(inn) == 12 else f"<СвЮЛУч{_attrs(НаимОрг=p['name'], ИННЮЛ=p['inn'], КПП=p.get('kpp'))}/>"
    bank = ""
    b = p.get("bank") if with_bank else None
    if b and b.get("account") and b.get("bik") and b.get("corr"):
        bank = f"<БанкРекв{_attrs(НомерСчета=b['account'], НаимБанк=b.get('name'), БИК=b['bik'], КорСчет=b['corr'])}/>"
    if p.get("address_xml"):                 # адрес из УПД 1С как есть (ГАР); негодный схеме — `build` перейдёт на текст
        addr = f"<Адрес>{p['address_xml']}</Адрес>"
    elif p.get("address"):
        addr = f"<Адрес><АдрИнф{_attrs(КодСтр='643', НаимСтран='Россия', АдрТекст=p['address'][:1000])}/></Адрес>"
    else:
        addr = ""
    return f"<{tag}><ИдСв>{ul}</ИдСв>{bank}{addr}</{tag}>"


SIGNER_NO_FIO = "У подписанта нашего юрлица нет ФИО (фамилия и имя) — заполните в карточке нашего юрлица"


def _fio(fio: str, why: str = SIGNER_NO_FIO) -> str:
    """<ФИО/> из «Фамилия Имя [Отчество]» — один разбор для подписанта и покупателя-ИП (ревью 12.11.2026)."""
    parts = (fio or "").split()
    if len(parts) < 2:
        raise InvoiceXmlError(409, why)
    return f"<ФИО{_attrs(Фамилия=parts[0], Имя=parts[1], Отчество=' '.join(parts[2:]) or None)}/>"


def _check(inv: dict) -> None:
    if not (inv.get("number") or "").strip():
        raise InvoiceXmlError(409, "Нет номера счёта из 1С — XML счёта собирается после того, как бухгалтер внесла счёт")
    if not inv.get("date"):
        raise InvoiceXmlError(409, "Нет даты счёта из 1С — XML счёта собирается после того, как бухгалтер внесла счёт")
    for who, p in (("продавца", inv["seller"]), ("покупателя", inv["buyer"])):
        if not (p.get("name") and p.get("inn")):
            raise InvoiceXmlError(409, f"Нет наименования или ИНН {who}")
    s = inv["seller"].get("signer") or {}
    if not ((s.get("position") or "").strip() and (s.get("fio") or "").strip()):
        raise InvoiceXmlError(409, "Нет подписанта нашего юрлица (должность и ФИО) — заполните в карточке нашего юрлица")
    if not inv.get("lines"):
        raise InvoiceXmlError(409, "В счёте нет строк")
    b = inv["seller"].get("bank") or {}
    if not (b.get("account") and b.get("bik") and b.get("corr")):
        # формат требует банк продавца (правило СвПрод: БанкРекв) — без него Диадок файл не примет (ревью 12.11.2026)
        raise InvoiceXmlError(409, "Нет банковских реквизитов нашего юрлица (счёт, БИК, корр. счёт) — ни в XML УПД, ни в карточке")


def build(inv: dict, now: Optional[datetime] = None) -> tuple:
    """→ (имя файла, байты windows-1251). `inv` — см. `for_kit`: номер и дата 1С, стороны, основание, строки, подписант."""
    _check(inv)
    from app.timez import msk_now
    now = now or msk_now()          # ДатаИнф/ВрИнф — московские: контейнер живёт по Гринвичу
    name = f"ON_CHETOP_{participant_id(inv['buyer'])}_{participant_id(inv['seller'])}_{now:%Y%m%d}_{uuid.uuid4()}"
    lines, net, vat, gross = [], 0.0, 0.0, 0.0
    no_vat = all(_line_no_vat(ln) for ln in inv["lines"])
    for i, ln in enumerate(inv["lines"], 1):
        # итог — сумма НАПЕЧАТАННЫХ строк, а не сырых чисел: иначе «всего» расходится с колонкой на копейку (ревью)
        net, vat, gross = net + float(_m(ln["net"])), vat + float(_m(ln["vat"])), gross + float(_m(ln["gross"]))
        tax = "<БезНДС>без НДС</БезНДС>" if _line_no_vat(ln) else f"<СумНал>{_m(ln['vat'])}</СумНал>"
        lines.append(f"<СведТовЦенПок{_attrs(НомСтр=i, НаимТов=(ln['name'] or 'Услуга')[:1000], КолТов=ln.get('qty'), ЦенаТов=ln.get('price'), СтТовБезНДС=_m(ln['net']), СтТовУчНал=_m(ln['gross']))}>"
                     f"<НалСт>{escape(ln.get('rate_text') or _rate(ln.get('vat_rate')))}</НалСт><СумНал>{tax}</СумНал><СумНалБезСки>{tax}</СумНалБезСки>"
                     f"<ДопСведТов ПрТовРаб=\"3\"/></СведТовЦенПок>")
    b = inv.get("basis")
    basis = (f"<Основание><ОснРеквДок{_attrs(РеквНаимДок=b['name'], РеквНомерДок=b['number'], РеквДатаДок=_d(b['date']))}/></Основание>"
             if b and b.get("number") and b.get("date") else "")
    purpose = (inv.get("purpose") or f"Оплата по счёту № {inv['number']} от {_d(inv['date'])}")[:PURPOSE_MAX]
    s = inv["seller"]["signer"]
    body = (
        f"<Файл{_attrs(ИдФайл=name, ВерсФорм=VERSION, ВерсПрог=PROGRAM)}>"
        f"<Документ{_attrs(КНД=KND, Функция='0', ДатаИнф=now.strftime('%d.%m.%Y'), ВрИнф=now.strftime('%H:%M:%S'))}>"
        f"<СодСч{_attrs(ДатаДок=_d(inv['date']), НомерДок=inv['number'].strip(), ВсегоНаим=len(lines))}>"
        f"{basis}{''.join(lines)}"
        f"<ВсегоОпл{_attrs(СтТовБезНДСВсего=_m(net), СтТовУчНалВсего=_m(gross))}><СумНалВсего>{'<БезНДС>без НДС</БезНДС>' if no_vat else f'<СумНал>{_m(vat)}</СумНал>'}</СумНалВсего></ВсегоОпл>"
        f"<ДопСв{_attrs(НазнПл=purpose)}/>"
        f"<ДенИзм НаимОКВ=\"Российский рубль\"><КодОКВ>643</КодОКВ></ДенИзм>"
        f"{_party('СвПрод', inv['seller'], with_bank=True)}{_party('СвПокуп', inv['buyer'])}"
        f"</СодСч>"
        f"<Подписант{_attrs(Должн=s['position'].strip(), СпосПодтПолном='1')}>{_fio(s['fio'])}</Подписант>"
        f"</Документ></Файл>"
    )
    data = ('<?xml version="1.0" encoding="windows-1251"?>' + body).encode("cp1251", errors="xmlcharrefreplace")      # «€», «₽» — ссылкой на символ, а не «?"
    err = schema_error(data)
    if err and any(inv[k].get("address_xml") for k in ("seller", "buyer")):
        # адрес 1С в другой редакции ГАР — тот же адрес текстом, а не негодный файл
        plain = {**inv, "seller": {**inv["seller"], "address_xml": None}, "buyer": {**inv["buyer"], "address_xml": None}}
        return build(plain, now)
    if err:
        raise InvoiceXmlError(409, f"XML счёта не проходит схему ФНС: {err}")
    return name + ".xml", data


def _line_no_vat(ln: dict) -> bool:
    rt = (ln.get("rate_text") or "").strip().lower()
    return rt == "без ндс" if rt else _no_vat(ln.get("vat_rate"))


_SCHEMA = None
_SCHEMA_LOCK = threading.Lock()


def schema_error(data: bytes) -> Optional[str]:
    """Первая ошибка схемы ФНС или None. Файл, который Диадок не примет, не отдаём вовсе (13.11.2026). Под замком: общий
    объект схемы держит журнал последней проверки — без замка параллельный запрос прочёл бы чужую ошибку (ревью)."""
    global _SCHEMA
    import os
    from lxml import etree
    with _SCHEMA_LOCK:
        if _SCHEMA is None:
            _SCHEMA = etree.XMLSchema(etree.parse(os.path.join(os.path.dirname(__file__), "xsd", "ON_CHETOP_1_998_01_05_01_04.xsd")))
        ok = _SCHEMA.validate(etree.fromstring(data))
        return None if ok else str(_SCHEMA.error_log.last_error)


# ── сборка из комплекта ───────────────────────────────────────────────────────────────────────────

def _upd_raw(db, m, k) -> Optional[bytes]:
    """Последний загруженный XML УПД 1С комплекта (байты) или None."""
    from app.master_deal.models import MasterDealFile
    from app.onec_desk import files as OF
    f = (db.query(MasterDealFile).filter_by(master_deal_id=m.id, upd_no=k.upd_no, kind="УПД 1С xml")
         .order_by(MasterDealFile.id.desc()).first())
    if f is None:
        return None
    try:
        return OF.read(f)
    except Exception:  # noqa: BLE001 — файла нет на диске
        return None


def _upd_parties(db, m, k) -> Optional[dict]:
    """Стороны из загруженного XML УПД 1С — `None`, если XML нет или он не читается (тогда банк — из нашей карточки)."""
    from app.master_deal.models import MasterDealFile
    from app.onec_desk import files as OF
    from app.onec_desk import xmlparse as XP
    f = (db.query(MasterDealFile).filter_by(master_deal_id=m.id, upd_no=k.upd_no, kind="УПД 1С xml")
         .order_by(MasterDealFile.id.desc()).first())
    if f is None:
        return None
    try:
        return XP.parties(OF.read(f))
    except Exception:  # noqa: BLE001 — нет файла на диске или битый XML: сверка просто не делается
        return None


def _ours(db, cp_id) -> dict:
    from app.models import Counterparty, CounterpartyBankAccount
    c = db.get(Counterparty, cp_id) if cp_id else None
    if c is None:
        return {}
    accs = db.query(CounterpartyBankAccount).filter_by(counterparty_id=c.id).order_by(CounterpartyBankAccount.sort_order).all()
    return {"row": c, "name": c.name, "inn": c.inn, "kpp": c.kpp, "address": c.address, "edo_id": c.edo_id,
            "accounts": [a.rs for a in accs if a.rs], "first_bank": accs[0] if accs else None}


def requisites(db, m, k, seller_id: Optional[int], buyer_id: Optional[int]) -> Optional[list]:
    """Сверка реквизитов УПД 1С с нашими карточками; `None` — XML УПД ещё не загружен (сверять не с чем). Стороны передаёт
    вызывающий: экран бухгалтера опрашивает выдачу раз в минуту, второй сборки карточки пакета на каждую заявку быть не должно
    (ревью 12.11.2026)."""
    from app.onec_desk import requisites as RQ
    upd = _upd_parties(db, m, k)
    if upd is None:
        return None
    return RQ.diff(upd, {"seller": _ours(db, seller_id), "buyer": _ours(db, buyer_id)})


def response(name: str, data: bytes):
    """Ответ ручки скачивания: имя файла по формату ФНС — Диадок узнаёт формализованный счёт и по имени."""
    from io import BytesIO
    from urllib.parse import quote
    from fastapi.responses import StreamingResponse
    return StreamingResponse(BytesIO(data), media_type="application/xml",
                             headers={"Content-Disposition": f"attachment; filename=\"{quote(name)}\"; filename*=UTF-8''{quote(name)}"})


def for_kit(db, m, k, now: Optional[datetime] = None) -> tuple:
    """XML счёта комплекта — из XML УПД 1С (`from_upd`), номер и дата — счёта 1С. Сумма строк УПД должна совпасть с суммой
    счёта 1С — иначе отказ: в Диадок не должен уйти счёт с другой суммой. Коды участников ЭДО — из наших карточек (их в УПД нет)."""
    from app.onec_desk import queue as Q
    from app.onec_desk import xmlparse as XP
    raw = _upd_raw(db, m, k)
    upd = XP.upd_document(raw) if raw else None
    card = Q.card(db, k)
    seller, buyer = _ours(db, (card.get("seller") or {}).get("id")), _ours(db, (card.get("buyer") or {}).get("id"))
    row = seller.get("row")
    signer = {"position": (row.signer_position if row else "") or "", "fio": (row.director_name if row else "") or ""}
    inv = from_upd(upd, k.onec_invoice_no, k.onec_invoice_date, signer)
    if not inv["number"] or not inv["date"]:
        raise InvoiceXmlError(409, "Нет номера или даты счёта из 1С — XML счёта собирается после того, как бухгалтер внесла счёт")
    gross = round(sum(float(x["gross"]) for x in inv["lines"]), 2)
    if k.onec_gross is not None and abs(gross - float(k.onec_gross)) > 0.01:
        raise InvoiceXmlError(409, f"Сумма строк УПД 1С {gross:.2f} не совпадает с суммой счёта 1С {float(k.onec_gross):.2f} — "
                                   "XML не собираем, чтобы в Диадок не ушёл счёт с другой суммой")
    inv["seller"]["edo_id"], inv["buyer"]["edo_id"] = seller.get("edo_id"), buyer.get("edo_id")
    bank = inv["seller"].get("bank") or {}
    if not bank.get("corr"):
        # корр. счёта в УПД нет — берём его из НАШЕЙ записи того же расчётного счёта; другой счёт не подставляем (ревью 13.11.2026)
        from app.models import CounterpartyBankAccount
        row_b = (db.query(CounterpartyBankAccount).filter_by(counterparty_id=row.id, rs=bank.get("account")).first()
                 if row is not None and bank.get("account") else None)
        if row_b is None and not bank.get("account") and seller.get("first_bank") is not None:
            row_b = seller["first_bank"]
        if row_b is not None:
            inv["seller"]["bank"] = {"account": row_b.rs, "bik": row_b.bik, "corr": row_b.ks, "name": row_b.bank_name}
    try:
        return build(inv, now)
    except (ValueError, KeyError, TypeError) as e:     # кривая дата или сумма в данных — отказ, а не падение архива (ревью)
        raise InvoiceXmlError(409, f"Данные счёта не собрались в XML: {e}") from None


def from_upd(upd: Optional[dict], number, date, signer: dict) -> dict:
    """Счёт из XML УПД 1С (13.11.2026, владелец: «пдф — наш счёт, xml — они должны совпадать»): строки, наименования услуг,
    стороны, адреса, банк и договор — ровно как в документе 1С; номер и дата — счёта 1С (то, что внесла бухгалтер)."""
    if not upd or not upd.get("lines"):
        raise InvoiceXmlError(409, "Нет XML УПД из 1С у комплекта — счёт собирается по нему, чтобы совпасть с документом 1С. "
                                   "Загрузите XML УПД в «Закрывающих документах»")
    s_, b_ = dict(upd.get("seller") or {}), dict(upd.get("buyer") or {})
    vat = sum(float(x["vat"]) for x in upd["lines"])
    tail = f", в т.ч. НДС {_m(vat).replace('.', ',')} руб." if vat else ", без НДС"
    return {
        "number": number or "", "date": date,
        "seller": {**s_, "edo_id": None, "signer": signer},
        "buyer": {**b_, "edo_id": None},
        "basis": upd.get("basis"),
        "purpose": f"Оплата по счёту № {number} от {_d(date)}{tail}" if number and date else "Оплата",
        "lines": upd["lines"],
    }
