# -*- coding: utf-8 -*-
"""Печатная сборка ДС — найти, собрать документ, проверить реквизиты, назвать файл (внешний аудит 2.7.0, п. 2.7).

Жила в роутере `routers/annexes.py`, и архив мастер-сделки (`master_deal/bundle.py`) брал её оттуда тремя приватными функциями:
их переименование ломало сборку архива, а заметить это можно было только руками. Теперь это сервис; роутер держит прежние
имена ссылками сюда, поэтому ручки и тесты, подменяющие их в роутере, не изменились."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.annex_tpl import document as tpl_doc
from app.legal import service as legal
from app.models import Contract
from app.sales import annex as annex_build
from app.sales import annex_docx as docx_build
from app.sales.models import SalesAnnex


def contract_of(db: Session, contract_id: int) -> Contract:
    c = db.query(Contract).filter(Contract.id == contract_id).first()
    if not c:
        raise HTTPException(404, "Договор не найден")
    return c


def annex_of(db: Session, annex_id: int, user=None) -> SalesAnnex:
    """ДС по id. С пользователем — ещё и область «свои» (аудит 21.10.2026): ручки обязаны передавать `user`,
    служебные вызовы без него проверку не делают."""
    a = db.query(SalesAnnex).filter(SalesAnnex.id == annex_id).first()
    if not a:
        raise HTTPException(404, "Приложение не найдено")
    if user is not None:
        from app.sales import scope as SC
        SC.annex_in_scope(db, user, a)
    return a


def annex_deals(db: Session, annex_id: int) -> list:
    """Сделки, которые закрывает приложение — из таблицы разнесения сумм.

    Одно приложение может закрывать несколько сделок, и таблица заведена ровно затем,
    чтобы выручку можно было вернуть их авторам.
    """
    from app.sales.models import SalesDealAnnexAllocation
    return [d for (d,) in db.query(SalesDealAnnexAllocation.deal_id)
            .filter(SalesDealAnnexAllocation.annex_id == annex_id).all()]


def assert_no_open_legal(db: Session, a: SalesAnnex) -> None:
    """Открытая заявка юристу блокирует выпуск ДС: подтверждение и чистовые выгрузки (владелец 13.10.2026, п. 50). Клиентские файлы
    на согласование не блокируются — их и отправляют, пока юрист работает."""
    why = legal.blocking_reason(db, a.id)
    if why:
        raise HTTPException(409, why)


_BAD_IN_NAME = ('\\', '/', ':', '*', '?', '"', '<', '>',
                '|', '\r', '\n', '\t')


def file_name(*, no, doc_date, brand, payer, basis: bool = False) -> str:
    """Имя файла ДС: «ДС №68 от 31.05.2026 — Dr. Reddy's Хелинорм — ООО Ромашка.pdf».

    Четыре части по правилу владельца 05.09.2026: номер, дата, рекламодатель с брендом,
    юрлицо по договору. Порядок не косметика — по такому имени документ находят в папке
    и в переписке, не открывая.

    Пустые части выпадают, а не оставляют пустое место с разделителем: у черновика
    номера ещё нет, у части контрагентов не заполнен бренд.
    """
    parts = [f"ДС №{no}" if no else "ДС без номера"]
    if doc_date:
        parts[0] += f" от {doc_date.strftime('%d.%m.%Y')}"
    for v in (brand, payer):
        v = " ".join((v or "").split())
        if v:
            parts.append(v)
    if basis:
        parts.append("с основанием для закрывающих")
    name = " — ".join(parts)
    for ch in _BAD_IN_NAME:
        name = name.replace(ch, " ")
    name = " ".join(name.split())
    # Ограничение длины имени файла — 255 байт в большинстве систем; кириллица в UTF-8
    # занимает по два, поэтому режем по символам с запасом.
    return (name[:110].rstrip() or "ДС") + ".pdf"


def assert_printable(doc: dict) -> None:
    """Не дать выгрузить документ с прочерками на месте реквизитов.

    Проверка стоит на ВЫГРУЗКЕ, а не на подтверждении: номер можно занять заранее, а вот
    бумага с пустым местом там, где стоит подпись, уходит клиенту и подписывается не
    глядя. Чего не хватает — перечисляется поимённо, иначе отказ означает «сходи поищи».
    """
    miss = doc.get("missing") or []
    if miss:
        raise HTTPException(400, "Не хватает данных для документа: " + ", ".join(miss))


def printable_doc(db: Session, a: SalesAnnex) -> dict:
    """Собранный документ по сохранённому приложению.

    Экран сборки и печать берут ЕГО ЖЕ: если бы экран считал сам, аккаунт проверял бы
    одни числа, а в PDF уходили другие — и разошлись бы они молча.
    """
    c = contract_of(db, a.contract_id)
    deal_ids = annex_deals(db, a.id)
    doc = annex_build.build(db, c, period_from=a.period_from, period_to=a.period_to,
                            amount=a.total_amount or 0, vat_rate=a.vat_rate, no=a.no,
                            deal_ids=deal_ids)
    # Пункт 1 и замечания — из шаблона ДС (мост до переписывания генерации файлов).
    return tpl_doc.bridge_old_doc(db, a, c, doc, deal_ids)


def printable_docx(db: Session, annex_id: int) -> tuple:
    """(имя, байты) чистового DOCX ДС — то же, что ручка `/annexes/{id}/docx`; отказ — HTTPException с причиной."""
    a = annex_of(db, annex_id)
    assert_no_open_legal(db, a)
    doc = printable_doc(db, a)
    assert_printable(doc)
    name = file_name(no=a.no, doc_date=doc["date"], brand=doc.get("brand"),
                     payer=(doc.get("customer") or {}).get("name")).replace(".pdf", ".docx")
    return name, docx_build.build_docx(doc)
