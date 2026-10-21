# -*- coding: utf-8 -*-
"""Данные договора, без которых документ неликвиден (владелец 21.10.2026: «всё, что требуется для выпуска ликвидного документа»).

Одна функция на конструктор, подтверждение и печать ДС: её строки ложатся в `missing` модели документа, а `missing` запирает
подтверждение и выгрузку (`assert_printable`). Подписанта (ФИО, должность, основание) проверяет `sales.annex.party` — здесь не
дублируется; здесь — договор и реквизиты сторон, которых подписант не покрывает. Каждая строка называет, ГДЕ поправить."""
from typing import List, Optional

WHERE_CONTRACT = "Справочники → Договоры"
WHERE_CP = "карточка контрагента (Справочники → Контрагенты)"
_W10 = (2, 4, 10, 3, 5, 9, 4, 6, 8)
_W12A = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_W12B = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


def _ctl(digits: list, weights: tuple) -> int:
    return sum(d * w for d, w in zip(digits, weights)) % 11 % 10


def inn_ok(inn: Optional[str]) -> bool:
    """ИНН по контрольной сумме ФНС: 10 цифр — юрлицо, 12 — ИП/физлицо."""
    s = (inn or "").strip()
    if not s.isdigit() or len(s) not in (10, 12):
        return False
    d = [int(c) for c in s]
    if len(s) == 10:
        return _ctl(d, _W10) == d[9]
    return _ctl(d, _W12A) == d[10] and _ctl(d, _W12B) == d[11]


def _side(cp, role: str) -> List[dict]:
    if cp is None:
        return []
    out = []
    inn = (cp.inn or "").strip()
    if inn and not inn_ok(inn):                       # пустой ИНН называет `party` — здесь только неверный
        out.append({"text": f"{role}: ИНН {inn} не проходит проверку контрольной суммы", "where": WHERE_CP})
    if len(inn) == 10 and not (cp.kpp or "").strip():
        out.append({"text": f"{role}: КПП (у юрлица обязателен)", "where": WHERE_CP})
    return out


def gaps(db, contract) -> List[dict]:
    """Чего не хватает договору и сторонам для ликвидного ДС. Пусто — можно выпускать."""
    from app import own_company
    out = []
    if not (contract.contract_number or "").strip():
        out.append({"text": "договор: номер", "where": WHERE_CONTRACT})
    if not contract.contract_date:
        out.append({"text": "договор: дата", "where": WHERE_CONTRACT})
    if not contract.counterparty_id:
        out.append({"text": "договор не привязан к контрагенту из реестра", "where": WHERE_CONTRACT + " — колонка «Контрагент»"})
    if not (getattr(contract, "issue_channel", None) or "").strip():
        out.append({"text": "договор: выставление — ЭДО или бумага", "where": WHERE_CONTRACT})
    us = contract.own_company or own_company.sole(db)
    if us is None:
        out.append({"text": "договор: наше юрлицо не выбрано", "where": WHERE_CONTRACT})
    return out + _side(contract.counterparty, "заказчик") + _side(us, "исполнитель")
