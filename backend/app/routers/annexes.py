# -*- coding: utf-8 -*-
"""Приложения к договору (ДС): сборка, подтверждение, шаблоны формулировок.

Право — `contracts`, а не своё: приложение это часть договора, и тот, кто ведёт договоры,
ведёт и приложения к ним. Своя секция прав завелась бы новым НЕИЗМЕНЯЕМЫМ ключом, и
заводить его до решения владельца дороже, чем переиспользовать существующий.

Порядок работы:

  · **предпросмотр** ничего не пишет и номера не занимает — он показывает, каким документ
    получится, и чего для него не хватает;
  · **черновик** живёт без номера (`no IS NULL`), и таких может быть сколько угодно;
  · **подтверждение** занимает номер насовсем: с этого момента документ ушёл клиенту, а
    номер внутри договора больше никому не достанется.

Разделение на черновик и подтверждение не формальность: брошенный черновик не должен
сжигать номер, а занятый номер не должен меняться задним числом.
"""
import calendar
import logging
import os
from datetime import date, datetime
from io import BytesIO
from typing import Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func as sa_func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.annex_tpl import document as tpl_doc
from app.sales import annex_signed
from app.annex_tpl.assemble import (CLOSING_KEY, closing_template_for as tpl_closing_for, assemble as tpl_assemble,
                                    closing_resolve as tpl_closing_resolve, validate_edit as tpl_validate_edit)
from app.annex_tpl.service import AnnexTplError
from app.annex_tpl.service import remember as tpl_remember
from app.audit import log_action
from app.database import get_db
from app.models import Contract, Counterparty, User
from app.permissions import require_permission
from app.routers.sales_dashboard import _assert_deal_in_scope, _scope_deal_ids
from app.sales import annex as annex_build
from app.sales import annex_docx as docx_build
from app.sales import rugram
from app.sales.models import (AnnexTemplate, SalesAdvertiser, SalesAnnex, SalesDeal,
                              SalesDealAnnexAllocation as Alloc, SalesMediaPlan)

router = APIRouter()
log = logging.getLogger(__name__)

# Своя секция прав с 06.09.2026 (миграция 2026-09-06_annexes_permission.sql): реестр
# приложений показывает суммы сделок и выпускает клиенту документы — это не то же самое,
# что правка карточки договора. Ключ неизменяем: он записан строкой в role_permissions.
VIEW = require_permission("annexes", "view")
CREATE = require_permission("annexes", "create")
EDIT = require_permission("annexes", "edit")

# Печатная сборка ДС — в сервисе `app/sales/annex_print.py` (аудит 2.7.0, п. 2.7); прежние имена — ссылками туда.
from app.sales import annex_print as AP  # noqa: E402
_contract, _annex, _annex_deals = AP.contract_of, AP.annex_of, AP.annex_deals
_assert_no_open_legal, file_name, assert_printable, _doc = AP.assert_no_open_legal, AP.file_name, AP.assert_printable, AP.printable_doc


def _deal_cards(db: Session, annex_id: int) -> list:
    """Сделки приложения для экрана: метка, название и разнесённая сумма.

    Экран показывает их ссылками — из документа надо уметь вернуться к тому, из чего он
    собран. В адресах сделок используется `code` (шестизначная метка), а не id: так они
    выглядят везде в интерфейсе.
    """
    rows = (db.query(SalesDeal, Alloc.amount)
            .join(Alloc, Alloc.deal_id == SalesDeal.id)
            .filter(Alloc.annex_id == annex_id)
            .order_by(SalesDeal.id).all())
    return [{"id": d.id, "code": d.code, "title": d.title, "amount": amt,
             "deal_amount_with_vat": d.amount_with_vat}
            for d, amt in rows]


def _mismatch(a: SalesAnnex, deals: list) -> Optional[str]:
    """Расхождение суммы документа с суммой его сделок — вслух, до подписания.

    Сумма приложения собирается из медиаплана, сумма сделки живёт своей жизнью (её правят,
    переносят, она приезжает из Битрикса). До 23.09.2026 сверки не было вовсе: сумму ДС
    подменяли итогом той же таблицы, и «не сходится с планом» сравнивало число само с собой
    (аудит 23.09.2026, 3.H1). Рубль допуска — на округления строк.
    """
    # Сумма неизвестна хоть у одной сделки — сравнивать не с чем: сумма остальных всегда
    # меньше итога документа, и «не совпадает» было бы ложной тревогой (ревью 23.09.2026).
    known = [d.get("deal_amount_with_vat") for d in deals]
    if not known or any(v is None for v in known) or a.total_amount is None:
        return None
    deals_sum = round(sum(known), 2)
    if abs(deals_sum - float(a.total_amount)) <= 1.0:
        return None
    f = lambda v: f"{v:,.2f}".replace(",", " ")  # noqa: E731
    return (f"Сумма приложения {f(float(a.total_amount))} ₽ не совпадает с суммой сделок "
            f"{f(deals_sum)} ₽ (с НДС). Проверьте медиаплан и сумму сделки до подписания.")


def _out(a: SalesAnnex) -> dict:
    return {
        "id": a.id, "contract_id": a.contract_id, "no": a.no, "number": a.number,
        "date": a.date, "period_from": a.period_from, "period_to": a.period_to,
        "total_amount": a.total_amount, "vat_rate": a.vat_rate, "status": a.status,
        "template_id": a.template_id, "template_version_id": a.template_version_id, "signed_place": a.signed_place,
        "confirmed_at": a.confirmed_at, "file_path": a.file_path,
        # Черновик отличается от выпущенного ровно наличием номера — отдельного флага
        # заводить не стали: два признака одного состояния разъезжаются.
        "is_draft": a.no is None,
    }


# ── сборка ───────────────────────────────────────────────────────────────────

@router.get("/preview")
def preview(contract_id: int, period_from: date, period_to: date, amount: float,
            brand: Optional[str] = None, vat_rate: Optional[float] = None,
            deal_ids: Optional[str] = None,
            db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Каким получится документ. Ничего не пишет и номер не занимает.

    Отдаёт и `missing` — чего не хватает для печати. Документ с пустым местом на месте
    директора хуже отказа: его подпишут не глядя.
    """
    if period_to < period_from:
        raise HTTPException(400, "Конец периода раньше начала")
    c = _contract(db, contract_id)
    ids = _scope_deal_ids(db, user, _ids(deal_ids))         # медиаплан чужой сделки не собирается (аудит 21.10.2026)
    data = annex_build.build(db, c, period_from=period_from, period_to=period_to,
                             amount=amount, brand=brand, vat_rate=vat_rate,
                             deal_ids=ids)
    data["no_hint"] = annex_build.no_hint(db, c)
    data["annex_start_no"] = c.annex_start_no
    return data


def _ids(raw) -> list:
    """«12,15» → [12, 15]. Сделки приходят строкой: приложение закрывает их несколько,
    а разнесение сумм по ним живёт отдельной таблицей."""
    if not raw:
        return []
    return [int(x) for x in str(raw).replace(" ", "").split(",") if x.isdigit()]


class AnnexIn(BaseModel):
    contract_id: int
    deal_ids: Optional[list] = None
    period_from: date
    period_to: date
    total_amount: float
    brand: Optional[str] = None
    vat_rate: Optional[float] = None
    template_id: Optional[int] = None
    signed_place: Optional[str] = None


@router.post("")
def create_annex(payload: AnnexIn, db: Session = Depends(get_db), user: User = Depends(CREATE)):
    """Завести ЧЕРНОВИК: номер не присваивается, дата считается от периода."""
    if payload.period_to < payload.period_from:
        raise HTTPException(400, "Конец периода раньше начала")
    c = _contract(db, payload.contract_id)
    version, reason = tpl_doc.resolve(db, c)
    if version is None:
        raise HTTPException(409, reason)            # формат не указан или шаблон не назначен — ДС не собирается
    if payload.deal_ids:
        _scope_deal_ids(db, user, payload.deal_ids)    # разнесение выручки — только в свои сделки (аудит 21.10.2026)
    _assert_one_advertiser(db, payload.deal_ids)
    data = annex_build.build(db, c, period_from=payload.period_from,
                             period_to=payload.period_to, amount=payload.total_amount,
                             brand=payload.brand, vat_rate=payload.vat_rate,
                             deal_ids=payload.deal_ids)
    # Главный — МЕДИАПЛАН (владелец 06.09.2026). Сумма сделки и сумма плана — два
    # независимых числа, и до 06.09.2026 в документе стояло первое, а в таблице второе:
    # у приложения № 1 это 610 000,24 против 590 164,17. Пересборка вторым проходом, а не
    # правкой словаря: сумма прописью и НДС считаются внутри, и подменять их снаружи
    # значило бы завести третье место, где живёт та же формула.
    total = payload.total_amount
    if data.get("plan_total") is not None:
        total = data["plan_total"]
        data = annex_build.build(db, c, period_from=payload.period_from,
                                 period_to=payload.period_to, amount=total,
                                 brand=payload.brand, vat_rate=payload.vat_rate,
                                 deal_ids=payload.deal_ids)
    a = SalesAnnex(
        contract_id=c.id, no=None, number=None,
        date=data["date"], period_from=payload.period_from, period_to=payload.period_to,
        total_amount=total, vat_rate=data["vat_rate"],
        status="черновик",
        template_id=payload.template_id or data["template_id"],
        template_version_id=version.id,
        signed_place=payload.signed_place or data["signed_place"],
        created_by=getattr(user, "id", None),
        # Создан до итоговой сверки (кнопка «Создать» в карточке сделки, реестр) — первичный, на план (владелец 16.10.2026).
        issue_kind="primary",
    )
    db.add(a)
    db.flush()
    _link_deals(db, a, payload.deal_ids, total)
    db.commit()
    db.refresh(a)
    log_action(db, user, "annex_create", "contract", c.id,
               f"черновик приложения на {total:.2f}")
    return _out(a)


def _assert_one_advertiser(db: Session, deal_ids) -> None:
    """Одно приложение — один рекламодатель (правило владельца 06.09.2026).

    Формулировка в документе говорит про материалы ОДНОГО бренда. Собрав в приложение
    сделки разных рекламодателей, мы выпустим бумагу, где перечислены два чужих друг другу
    бренда под одной услугой — и заметит это юрист клиента, а не мы.

    Сделка без рекламодателя тоже считается отдельным значением: «неизвестно» нельзя
    объявить тем же самым, что «Dr. Reddy's», не проверив.
    """
    ids = [i for i in (deal_ids or []) if i]
    if len(ids) < 2:
        return
    rows = (db.query(SalesDeal.id, SalesDeal.code, SalesDeal.advertiser_id,
                     SalesAdvertiser.short_name, SalesAdvertiser.name)
            .outerjoin(SalesAdvertiser, SalesAdvertiser.id == SalesDeal.advertiser_id)
            .filter(SalesDeal.id.in_(ids)).all())
    seen = {}
    for did, code, adv_id, short, full in rows:
        label = (short or full or "").strip() or "без рекламодателя"
        seen.setdefault(adv_id, (label, []))[1].append(code or str(did))
    if len(seen) > 1:
        parts = "; ".join(f"{label} — {', '.join(codes)}" for label, codes in seen.values())
        raise HTTPException(
            400, f"В одно приложение попали сделки разных рекламодателей: {parts}. "
                 f"Приложение выпускается на одного рекламодателя")


def _link_deals(db: Session, a: SalesAnnex, deal_ids, total: float) -> None:
    """Разнести сумму приложения по сделкам.

    До 05.09.2026 `deal_ids` участвовал только в сборке предпросмотра и НЕ сохранялся:
    приложение выпускалось, а связь со сделкой не возникала — то есть таблица размещения
    в документе была, а вернуть выручку авторам было нечем.

    Дробление пропорционально суммам сделок, остаток от округления кладётся на последнюю,
    чтобы разнесённое в сумме совпадало с приложением до копейки.
    """
    ids = [i for i in (deal_ids or []) if i]
    if not ids:
        return
    deals = db.query(SalesDeal).filter(SalesDeal.id.in_(ids)).all()
    if not deals:
        return
    weights = [float(d.amount_with_vat or d.amount or 0) for d in deals]
    base = sum(weights) or 0
    left = round(float(total or 0), 2)
    for i, d in enumerate(deals):
        if i == len(deals) - 1:
            part = left
        else:
            part = round(float(total or 0) * (weights[i] / base), 2) if base else 0
            left = round(left - part, 2)
        db.add(Alloc(deal_id=d.id, annex_id=a.id, amount=part))


def _deal_period(db: Session, d: SalesDeal):
    """Период размещения: сначала медиаплан, потом сама сделка.

    Замерено 05.09.2026: у медиапланов на стенде `date_from`/`date_to` пустые, а период
    сделки заполнен у 442 из 920. Требовать даты именно у плана значило бы отказывать там,
    где период известен — и человек не понял бы, чего от него хотят.

    Конец месяца достраивается, когда у сделки задано только начало: приложение на период
    нулевой длины подписать нельзя.
    """
    mp = (db.query(SalesMediaPlan).filter(SalesMediaPlan.deal_id == d.id,
                                          SalesMediaPlan.status != "rejected")
          .order_by(SalesMediaPlan.version.desc(), SalesMediaPlan.id.desc()).first())
    if mp and mp.date_from and mp.date_to:
        return mp.date_from, mp.date_to
    pf, pt = d.period_from, d.period_to
    if pf and not pt:
        pt = pf.replace(day=calendar.monthrange(pf.year, pf.month)[1])
    return pf, pt


@router.post("/from-deal/{deal_id}")
def create_from_deal(deal_id: int, db: Session = Depends(get_db), user: User = Depends(CREATE)):
    """Завести черновик приложения ПРЯМО ИЗ СДЕЛКИ — кнопка «Создать» в её документах.

    Всё, что нужно документу, у сделки уже есть, и переспрашивать это формой значит
    заставлять человека вводить то, что система знает: плательщик даёт договор, медиаплан
    — период, сама сделка — сумму с НДС. Чего не хватает — называется вслух, а не
    заменяется умолчанием: приложение не на тот договор или не за тот период исправляется
    только выпуском нового номера.
    """
    d = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if not d:
        raise HTTPException(404, "Сделка не найдена")
    # Ручка трогает КОНКРЕТНУЮ сделку, значит спрашивает область видимости: роль «свои»
    # не выпускает документ по чужой сделке. Прибор `test_deal_scope` считает маршрут без
    # этой проверки дырой — и поймал её здесь 05.09.2026.
    _assert_deal_in_scope(db, user, d)
    cp_id = d.payer_counterparty_id or d.counterparty_id
    if not cp_id:
        raise HTTPException(400, "У сделки не указан плательщик — договор брать не от кого")
    c = (db.query(Contract).filter(Contract.counterparty_id == cp_id)
         .order_by(Contract.contract_date.desc().nullslast(), Contract.id.desc()).first())
    if not c:
        raise HTTPException(400, "У плательщика нет договора в реестре")
    pf, pt = _deal_period(db, d)
    if not pf or not pt:
        raise HTTPException(400, "У сделки не задан период размещения — брать его неоткуда")
    # Сумма приложения приходит из МЕДИАПЛАНА, а не из сделки: план — источник
    # (владелец 06.09.2026), и приложение выпускается уже на этапе сборки, когда план
    # зафиксирован. Сумма сделки остаётся лишь запасом на случай, когда строк плана нет
    # вовсе — тогда и таблицы в документе не будет, и расходиться нечему.
    amount = float(d.amount_with_vat or d.amount or 0)
    if amount <= 0:
        raise HTTPException(400, "У сделки нулевая сумма")
    return create_annex(AnnexIn(contract_id=c.id, deal_ids=[d.id],
                                period_from=pf, period_to=pt,
                                total_amount=amount), db, user)


@router.put("/{annex_id}")
def edit_annex(annex_id: int, payload: AnnexIn, db: Session = Depends(get_db),
               user: User = Depends(EDIT)):
    """Правка ЧЕРНОВИКА. Подтверждённое не меняем: документ уже у клиента, и правка
    задним числом означала бы два разных приложения под одним номером."""
    a = _annex(db, annex_id, user)
    if a.no is not None:
        raise HTTPException(400, "Приложение подтверждено — правка запрещена")
    if payload.period_to < payload.period_from:
        raise HTTPException(400, "Конец периода раньше начала")
    # Дата идёт за началом периода, только если её не меняли руками: выставленную аккаунтом дату правка периода не затирает.
    date_is_default = a.date is None or a.date == annex_build.annex_date(a.period_from)
    a.period_from, a.period_to = payload.period_from, payload.period_to
    # Ставка — присланная, иначе СВОЯ ставка черновика. Пустая ставка в `build` означает
    # «текущая юрлица», и правка без поля ставки пересчитывала документ, посчитанный по
    # 20 %, по 22 % (ревью 23.09.2026; правило «ставка на дату расчёта»).
    rate = payload.vat_rate if payload.vat_rate is not None else a.vat_rate
    # Сумма пересчитывается по медиаплану, как и при сборке: править её руками означало бы
    # развести текст документа с его же таблицей.
    plan = annex_build.build(db, _contract(db, a.contract_id),
                             period_from=payload.period_from, period_to=payload.period_to,
                             amount=payload.total_amount, vat_rate=rate,
                             deal_ids=_annex_deals(db, a.id)).get("plan_total")
    a.total_amount = plan if plan is not None else payload.total_amount
    # Разнесение по сделкам — вслед за суммой. До 23.09.2026 оно писалось только при
    # создании черновика: правка меняла сумму документа, а доли в карточках сделок
    # оставались старыми и переставали в неё складываться (аудит 23.09.2026, 2.M6).
    deal_ids = _annex_deals(db, a.id)
    db.query(Alloc).filter(Alloc.annex_id == a.id).delete(synchronize_session=False)
    _link_deals(db, a, deal_ids, a.total_amount)
    if date_is_default:
        a.date = annex_build.annex_date(payload.period_from)
    if payload.vat_rate is not None:
        a.vat_rate = payload.vat_rate
    if payload.template_id is not None:
        a.template_id = payload.template_id
    if payload.signed_place is not None:
        a.signed_place = payload.signed_place
    db.commit()
    log_action(db, user, "annex_edit", "contract", a.contract_id, f"черновик #{a.id}")
    return _out(a)


class ConfirmIn(BaseModel):
    # Номер можно задать руками: бывает, что бумажный документ уже выпущен под своим.
    no: Optional[int] = None
    # Дата тоже правится: по умолчанию это начало РК, но документ могут датировать числом,
    # о котором договорились с клиентом. Пусто — остаётся прежняя.
    #
    # Поле НЕ называется `date`: имя затенило бы тип `date` в этой же модели, и Pydantic
    # разобрал бы аннотацию как `Optional[None]` — поле принимало бы только пустоту, молча
    # и без ошибки при импорте.
    doc_date: Optional[date] = None


def _check_no(db: Session, c: Contract, no: int, sub_no=None) -> None:
    """Три проверки номера перед тем, как он станет постоянным.

    Уникальность в конечном счёте держит база (`uq_annex_contract_no`) — между проверкой
    и записью номер мог занять кто-то другой. Но отказ по индексу приходит без объяснения,
    а человек в этот момент выбирает номер руками: сказать «74 уже у приложения от
    31.05.2026» полезнее, чем «конфликт».

    Стартовый номер — последний, выданный ВНЕ системы. Номер не больше него означает
    второй документ под тем же числом у клиента, и заметит это клиент, а не мы.
    """
    if not isinstance(no, int) or no < 1:
        raise HTTPException(400, "Номер приложения — целое число больше нуля")
    start = c.annex_start_no or 0
    if no <= start:
        raise HTTPException(
            400, f"Номер {no} не больше стартового ({start}): номера по {start} "
                 f"включительно выданы вне системы")
    # «5» и «5-01» — разные номера (ДС допов мастер-сделки, суффикс `sub_no`)
    taken = (db.query(SalesAnnex)
             .filter(SalesAnnex.contract_id == c.id, SalesAnnex.no == no,
                     (SalesAnnex.sub_no == sub_no) if sub_no else SalesAnnex.sub_no.is_(None)).first())
    if taken:
        when = taken.date.strftime("%d.%m.%Y") if taken.date else "без даты"
        raise HTTPException(409, f"Номер {no} по этому договору уже занят "
                                 f"(приложение от {when})")


def _freeze_for_confirm(db: Session, a: SalesAnnex, c: Contract, no: int, version=None, edits=None) -> dict:
    """Собрать документ по ТЕКУЩЕЙ версии шаблона этого ДС (выбранного или по умолчанию) и заморозить. Не прошёл полноту или сверку
    чисел — подтверждение отказывает поимённо (номер не занимается): бумагу с пустым местом или с двумя разными суммами подписывают не глядя."""
    if version is None:
        version, reason = tpl_doc.resolve(db, c, a)
        if version is None:
            raise HTTPException(409, reason)
    try:
        model = tpl_assemble(db, c, version, period_from=a.period_from, period_to=a.period_to,
                             deal_ids=_annex_deals(db, a.id), amount=a.total_amount, no=no,
                             edits=tpl_doc.edits_of(a) if edits is None else edits, doc_date=a.date,
                             defaults=tpl_doc.previous_defaults(db, a, c),
                             rows_override=getattr(a, "rows", None), sub_no=getattr(a, "sub_no", None))   # ДС пакета — из снимка раскладки
    except AnnexTplError as e:
        raise HTTPException(e.status, e.message)
    problems = [f"{m['text']} ({m['where']})" for m in model["missing"]] + model["consistency"]["details"]
    if a.total_amount is not None and abs(float(a.total_amount) - float(model["amount"])) >= 0.01:
        problems.append(f"сумма приложения {a.total_amount:,.2f} не сходится с собранным документом {model['amount']:,.2f}")
    if problems:
        raise HTTPException(409, "Приложение не подтверждено — документ неполон: " + "; ".join(problems))
    model["date"] = a.date or model["date"]
    return tpl_doc.freeze(model)


class EditIn(BaseModel):
    key: str                      # id пункта шаблона из зоны аккаунта или `closing_basis`
    text: Optional[str] = None    # None — вернуть по шаблону


@router.put("/{annex_id}/edits")
def edit_block(annex_id: int, payload: EditIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Быстрая правка блока, доступного аккаунту (зона до таблицы МП), и «основания для закрывающих документов». Текст хранится С подстановками —
    значения подставляются при сборке и остаются живыми. Черновик: правки в `blocks.edits`. Подтверждённое, пока не ушло в 1С: пункт зоны
    аккаунта пересобирает документ на той же версии шаблона (номер и дата прежние), основание закрывающих правится внутри замороженного документа."""
    a = _annex(db, annex_id, user)
    c = _contract(db, a.contract_id)
    frozen = tpl_doc.is_frozen(a)
    if a.no is not None and not frozen:
        raise HTTPException(409, "Приложение собрано до конструктора — пересоздайте его на новом шаблоне, тогда его можно править")
    if frozen and _sent_to_onec(a):
        raise HTTPException(409, "Приложение уже ушло в 1С — править его нельзя")
    key = payload.key
    if payload.text is not None:
        if frozen:
            blocks = a.blocks["blocks"]                      # зоны и системные блоки читаются из самого замороженного документа
        else:
            version, reason = tpl_doc.resolve(db, c, a)
            if version is None:
                raise HTTPException(409, reason)
            blocks = version.blocks
        err = tpl_validate_edit(blocks, key, payload.text)
        if err:
            raise HTTPException(400, err)
    edits = tpl_doc.edits_of(a)
    if payload.text is None or not payload.text.strip():
        # «Вернуть по шаблону»: если по умолчанию наследуется текст прошлого ДС — фиксируем явный сброс (None), иначе он вернулся бы сам.
        if key in tpl_doc.previous_defaults(db, a, c):
            edits[key] = None
        else:
            edits.pop(key, None)
    else:
        edits[key] = payload.text.strip()
    if frozen and key == CLOSING_KEY:                  # основание пересчитывается внутри замороженного документа, подписанный текст не трогаем
        model = tpl_doc.upgrade_frozen(db, a, c, _annex_deals(db, a.id))
        model["edits"] = edits
        model["closing_basis"] = tpl_closing_resolve(edits.get(key) or tpl_closing_for([r for g in (model.get("table") or {}).get("groups") or [] for r in g.get("rows") or []]), model["values"], bool(edits.get(key)))
        a.blocks = model
    elif frozen:                                       # пункт зоны аккаунта: документ собирается заново на ТОЙ ЖЕ версии шаблона, номер и дата прежние
        was = tpl_doc.version_row(db, a.template_version_id)
        a.blocks = _freeze_for_confirm(db, a, c, a.no, version=was, edits=edits)
    else:
        a.blocks = {"edits": edits} if edits else None
    db.commit()
    log_action(db, user, "annex_edit", "contract", c.id, f"#{a.id}: правка блока {key}" + (" (возвращён по шаблону)" if payload.text is None else ""))
    return {"ok": True, "edits": edits}


class DateIn(BaseModel):
    doc_date: date


@router.put("/{annex_id}/date")
def set_annex_date(annex_id: int, payload: DateIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Сменить дату ДС (владелец 14.10.2026): по умолчанию она — начало РК, аккаунт ставит другую с экрана ДС после «Уверены?».
    Черновик — просто дата. Подтверждённое, пока не ушло в 1С, — документ пересобирается на той же версии шаблона с новой датой
    (номер прежний). Было и стало — в журнал."""
    a = _annex(db, annex_id, user)
    c = _contract(db, a.contract_id)
    frozen = tpl_doc.is_frozen(a)
    if a.no is not None and not frozen:
        raise HTTPException(409, "Приложение собрано до конструктора — пересоздайте его на новом шаблоне, тогда дату можно менять")
    if frozen and _sent_to_onec(a):
        raise HTTPException(409, "Приложение уже ушло в 1С — дату менять нельзя")
    was = a.date
    if was == payload.doc_date:
        return _out(a)
    a.date = payload.doc_date
    if frozen:
        a.blocks = _freeze_for_confirm(db, a, c, a.no, version=tpl_doc.version_row(db, a.template_version_id))
    db.commit()
    fmt = (lambda d: d.strftime("%d.%m.%Y") if d else "без даты")
    log_action(db, user, "annex_date_change", "contract", c.id,
               f"{a.number or f'черновик #{a.id}'}: дата {fmt(was)} → {fmt(a.date)}")
    return _out(a)


def _sent_to_onec(a: SalesAnnex) -> bool:
    """Ушло ли приложение в 1С — после отправки пересоздавать его нельзя (документ уже учтён). Отправка в 1С появится в спринте 6;
    до тех пор признака нет, и пересоздавать можно любое подтверждённое. Условие вынесено в функцию, чтобы спринт 6 поменял одно место."""
    return False


def rebuild_frozen(db: Session, a: SalesAnnex, c: Contract) -> None:
    """Собрать подтверждённое заново по актуальной версии шаблона договора и заморозить (номер и дата прежние). Без commit — его делает
    вызывающий: кнопка «Пересоздать» и закрытие заявки юристу («Сделано» пересобирает ДС сам, владелец 14.10.2026)."""
    frozen = _freeze_for_confirm(db, a, c, a.no)
    a.template_version_id = frozen["template"]["version_id"]
    a.tpl_template_id = frozen["template"].get("template_id") or getattr(a, "tpl_template_id", None)
    a.blocks = frozen


@router.post("/{annex_id}/rebuild")
def rebuild_annex(annex_id: int, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Пересоздать подтверждённое приложение на АКТУАЛЬНОЙ версии шаблона договора (владелец 14.10.2026): для ДС, собранных до конструктора,
    и для тех, что собраны по старой версии шаблона, пока они не ушли в 1С. Номер и дата сохраняются, документ собирается заново и замораживается
    (полнота и сверка чисел те же, что при подтверждении). Прежний замороженный текст заменяется; что было и что стало — в журнале."""
    a = _annex(db, annex_id, user)
    if a.no is None:
        raise HTTPException(400, "Черновик собирается по текущему шаблону сам — пересоздавать нечего")
    if _sent_to_onec(a):
        raise HTTPException(409, "Приложение уже ушло в 1С — пересоздать его нельзя")
    c = _contract(db, a.contract_id)
    was = tpl_doc.version_row(db, a.template_version_id)
    rebuild_frozen(db, a, c)
    db.commit()
    now = tpl_doc.version_row(db, a.template_version_id)
    log_action(db, user, "annex_rebuild", "contract", c.id,
               f"{a.number}: пересобрано на шаблоне v{now.version if now else '?'}"
               + (f" (было v{was.version})" if was else " (было собрано до конструктора)"))
    return _out(a)


def confirm_one(db: Session, a: SalesAnnex, payload: "ConfirmIn", user) -> tuple:
    """Подтверждение одного приложения БЕЗ сохранения: номер, заморозка документа, отметка. Сохраняет вызывающий —
    кнопка конструктора сразу, «Подтвердить ДС пакета» — одним разом за весь пакет (атомарно, 21.10.2026). Возвращает (договор, номер)."""
    if a.no is not None:
        raise HTTPException(400, "Приложение уже подтверждено")
    _assert_no_open_legal(db, a)
    c = _contract(db, a.contract_id)
    # Номер запоминаем ОТДЕЛЬНОЙ переменной: после `rollback` объект сброшен, и в тексте
    # отказа оказалось бы «Номер None уже занят» — сообщение, по которому нечего понять.
    # `payload.no or ...` было бы ошибкой: ноль — ложь в Python, и введённый руками 0
    # молча превращался бы в следующий свободный номер вместо отказа.
    no = payload.no if payload.no is not None else annex_build.next_no(db, c)
    master_id, sub_no = getattr(a, "master_deal_id", None), getattr(a, "sub_no", None)
    if master_id:                          # ДС пакета: номер — из раскладки (последний актуальный + 1), у допов — суффикс «01»
        from app.master_deal.models import MasterDeal
        m = db.get(MasterDeal, master_id)
        # Номер основного ДС пакета: уже занятый (первичный ДС, пересобранный по факту, или подтверждённый основной) — его же
        # (у ДС допов — с суффиксом «01»); иначе — из раскладки: последний актуальный + 1.
        taken_main = (db.query(SalesAnnex.no).filter(SalesAnnex.master_deal_id == master_id, SalesAnnex.no.isnot(None),
                                                     SalesAnnex.sub_no.is_(None), SalesAnnex.id != a.id).scalar())
        if taken_main is not None:
            no = taken_main
        elif m and m.start_no is not None:
            no = m.start_no + 1
        else:
            raise HTTPException(409, "У мастер-сделки не задан номер ДС — задайте его на раскладке")
    _check_no(db, c, no, sub_no) if sub_no else _check_no(db, c, no)
    if payload.doc_date:
        a.date = payload.doc_date
    frozen = _freeze_for_confirm(db, a, c, no)
    a.template_version_id = frozen["template"]["version_id"]
    # Шаблон, по которому заморожен документ, — в сам ДС и в память его брендов: следующий ДС бренда в этом договоре получит его же.
    a.tpl_template_id = frozen["template"].get("template_id") or getattr(a, "tpl_template_id", None)
    if a.tpl_template_id:
        tpl_remember(db, c.id, tpl_doc.brand_ids(db, a), a.tpl_template_id, getattr(user, "id", None))
    a.blocks = frozen
    a.no = no
    a.number = (f"ДС № {no}" + (f"-{sub_no}" if sub_no else "")) if master_id else f"Приложение № {no}"
    a.status = "подтверждён"
    a.confirmed_by = getattr(user, "id", None)
    a.confirmed_at = datetime.utcnow()     # колонка — момент (в базе UTC), а не дата
    return c, no


def commit_confirm(db: Session, no, annex_id, work=None):
    """Выполнить `work` (подтверждения без сохранения) и сохранить; отказ базы — понятным текстом, номер при этом не занят
    (всё откатывается). База может отказать уже внутри `work` (автозапись перед запросом), поэтому он — внутри той же защиты."""
    try:
        out = work() if work else None
        db.commit()
        return out
    except IntegrityError as e:
        db.rollback()
        if "uq_annex_contract_no" in str(e.orig):
            raise HTTPException(409, f"Номер {no} по этому договору уже занят" if no is not None else "Номер ДС по этому договору уже занят")
        log.warning("Подтверждение приложения #%s отклонено базой: %s", annex_id, e.orig)
        raise HTTPException(409, "Приложение не подтверждено: данные не прошли проверку "
                                 "базы. Номер не занят — сообщите администратору")
    except SQLAlchemyError:
        # Любая ошибка базы раньше выдавалась за «номер занят» — человек выбирал другой
        # номер вместо того, чтобы повторить (аудит 23.09.2026, 2.L9).
        db.rollback()
        raise HTTPException(503, "Приложение не подтверждено: база не ответила. "
                                 "Номер не занят — повторите через минуту")


@router.post("/{annex_id}/confirm")
def confirm_annex(annex_id: int, payload: ConfirmIn, db: Session = Depends(get_db),
                  user: User = Depends(EDIT)):
    """Занять номер. С этого момента приложение перестаёт быть черновиком.

    Номер считается ПРЯМО СЕЙЧАС, а не при создании черновика: между сборкой и
    подтверждением кто-то мог выпустить своё приложение по тому же договору. Уникальность
    держит база (`uq_annex_contract_no`), и отказ по ней читается человеку понятным
    текстом, а не пятисоткой.
    """
    a = _annex(db, annex_id, user)
    c, no = commit_confirm(db, payload.no, a.id, lambda: confirm_one(db, a, payload, user))
    db.refresh(a)
    log_action(db, user, "annex_confirm", "contract", c.id, f"{a.number}")
    return _out(a)


# Потолок выдачи реестра. Он есть, и о нём надо СКАЗАТЬ: молча обрезанный список
# выглядит как «документ пропал», а не как «показано не всё» — и искать будут документ,
# а не страницу. Появятся тысячи — придут страницы; пока честно названного числа хватает.
LIST_LIMIT = 500


@router.get("")
def list_annexes(db: Session = Depends(get_db), user: User = Depends(VIEW), contract_id: Optional[int] = None):
    """Реестр приложений — учёт, о котором просил владелец: что выпущено и под каким
    номером. Черновики идут первыми: это незакрытая работа, а не архив. `contract_id` — ДС одного
    договора (окно «Шаблон ДС» в реестре договоров, 28.10.2026)."""
    by_contract = [SalesAnnex.contract_id == contract_id] if contract_id is not None else []
    total = db.query(sa_func.count(SalesAnnex.id)).filter(*by_contract).scalar() or 0
    rows = (db.query(SalesAnnex, Contract, Counterparty)
            .join(Contract, Contract.id == SalesAnnex.contract_id)
            .outerjoin(Counterparty, Counterparty.id == Contract.counterparty_id)
            .filter(*by_contract)
            .order_by(SalesAnnex.no.is_(None).desc(),
                      SalesAnnex.date.desc().nullslast(), SalesAnnex.id.desc())
            .limit(LIST_LIMIT).all())
    # Сделки берутся ОДНИМ запросом на страницу, а не по строке: реестр на пятьсот
    # приложений иначе делал бы пятьсот запросов, и заметно это стало бы не на стенде.
    deals = {}
    for did, code, aid in (db.query(SalesDeal.id, SalesDeal.code, Alloc.annex_id)
                           .join(Alloc, Alloc.deal_id == SalesDeal.id)
                           .filter(Alloc.annex_id.in_([a.id for a, _, _ in rows] or [0]))
                           .all()):
        deals.setdefault(aid, []).append({"id": did, "code": code})
    tpls = tpl_doc.template_labels(db, [a.template_version_id for a, _, _ in rows])
    # Область «свои» (аудит 21.10.2026): реестр не отдаёт ДС с чужими сделками — правило то же, что у карточки ДС.
    from app.sales import scope as SC
    own = SC.own_rep_ids_or_all(db, user, "sales_registry")
    truncated = total > len(rows)          # до фильтра: иначе у «своих» усечение старых ДС пряталось (ревью 22.10.2026)
    if own is not None:
        owners = SC.annex_owners(db, [a.id for a, _, _ in rows])
        rows = [r for r in rows if SC.annex_visible(owners[r[0].id], own, r[0].created_by, user.id)]
        total = len(rows)
    return {"total": total, "limit": LIST_LIMIT,
            "truncated": truncated,
            "items": [{**_out(a), "template": tpls.get(a.template_version_id),
                       # ИНН берётся из карточки контрагента, а не из договора: у
                       # легаси-договоров он бывает пуст, а у контрагента заполнен.
                       "counterparty_name": (cp.name if cp else None) or c.counterparty_name,
                       "counterparty_inn": (cp.inn if cp else None) or c.inn,
                       "contract_id": c.id,
                       "contract_number": c.contract_number,
                       "contract_date": c.contract_date,
                       # Вид базового шаблона ДС выводится из формата договора (макет 13.10.2026).
                       "cooperation_format": c.cooperation_format,
                       "deals": deals.get(a.id, [])}
                      for a, c, cp in rows]}


class ExportIn(BaseModel):
    """Порядок строк задаёт ЭКРАН, а не сервер.

    Сортировка в реестре живёт на клиенте (клик по заголовку). Повторять её здесь значило
    бы завести вторую реализацию того же правила — они расходятся молча, и выгрузка
    начинает отличаться от того, что человек видел перед нажатием. Поэтому экран
    присылает готовый порядок id, а сервер его соблюдает.
    """
    # None — экран не прислал отбора (выгружаем весь реестр). Пустой СПИСОК — прислал и
    # он пуст: под фильтр не подошло ничего, и в файле не должно быть ничего. Спутать эти
    # два состояния значит выгрузить весь реестр там, где человек ждал пустой файл.
    ids: Optional[list] = None


@router.post("/export.xlsx")
def export_annexes(payload: ExportIn, db: Session = Depends(get_db),
                   user: User = Depends(VIEW)):
    """Реестр приложений в Excel — ровно то и в том порядке, что на экране."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    items = {i["id"]: i for i in list_annexes(db, user)["items"]}
    order = (list(items) if payload.ids is None
             else [i for i in payload.ids if i in items])
    wb = Workbook()
    ws = wb.active
    ws.title = "Приложения"
    head = ["Юрлицо", "ИНН", "Договор", "Дата договора", "Приложение", "Дата",
            "Период с", "Период по", "Сумма с НДС", "Сделки", "Статус"]
    ws.append(head)
    fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for w, letter in zip([34, 13, 18, 13, 17, 12, 12, 12, 15, 16, 12], "ABCDEFGHIJK"):
        ws.column_dimensions[letter].width = w
    for i in order:
        a = items[i]
        ws.append([
            a["counterparty_name"], a["counterparty_inn"],
            a["contract_number"], a["contract_date"],
            a["number"] or "черновик", a["date"],
            a["period_from"], a["period_to"], a["total_amount"],
            ", ".join(d["code"] or str(d["id"]) for d in a["deals"]),
            "черновик" if a["is_draft"] else "выпущено",
        ])
    for row in ws.iter_rows(min_row=2, min_col=4, max_col=8):
        for c in row:
            c.number_format = "DD.MM.YYYY"
    for row in ws.iter_rows(min_row=2, min_col=9, max_col=9):
        for c in row:
            c.number_format = "# ##0.00"
    ws.freeze_panes = "A2"
    buf = BytesIO()
    from app.xlsx_safe import save_workbook   # формулы только наши (аудит, 1.L7)
    save_workbook(wb, buf)
    buf.seek(0)
    human = f"Приложения к договорам {date.today():%d.%m.%Y}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f"attachment; filename=\"annexes.xlsx\"; "
                 f"filename*=UTF-8''{quote(human)}"})


@router.get("/{annex_id}")
def get_annex(annex_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Приложение вместе с собранным документом — тем же расчётом, что предпросмотр."""
    a = _annex(db, annex_id, user)
    c = _contract(db, a.contract_id)
    deals = _deal_cards(db, a.id)
    state = tpl_doc.model_of(db, a, c, _annex_deals(db, a.id))
    return {**_out(a), "doc": _doc(db, a),
            # Документ по шаблону ДС (спринт 2): живой у черновика, замороженный у подтверждённого, пусто у собранных до конструктора.
            "model": state["model"], "model_frozen": state["frozen"], "model_legacy": state["legacy"],
            "model_reason": state["reason"], "template_state": state["template_state"],
            # Выбор шаблона на сборке (27.10.2026): варианты, что собирает сейчас и почему; у подтверждённого — нет.
            "template_choice": state["choice"],
            "deals": deals,
            "mismatch": _mismatch(a, deals),
            # Границу нумерации экран показывает рядом с полем: без неё отказ «номер не
            # больше стартового» выглядит как придирка непонятно к чему.
            "annex_start_no": c.annex_start_no,
            "next_no": annex_build.next_no(db, c),
            # ДС мастер-сделки: ссылка «← Раскладка M-…» и номер, который займёт подтверждение (из раскладки).
            "master": _master_ref(db, a),
            # Вид ДС и подпись (16.10.2026): первичный на план или по факту; подпись — из источников (сейчас файл, позже ЭДО).
            "issue_kind": getattr(a, "issue_kind", None),
            "signed": annex_signed.signed_state(db, a)}


def _master_ref(db: Session, a) -> Optional[dict]:
    mid = getattr(a, "master_deal_id", None)
    if not mid:
        return None
    from app.master_deal.models import MasterDeal
    m = db.get(MasterDeal, mid)
    if not m:
        return None
    from app.master_deal import to_annex as TA
    # Все ДС пакета (основной и допы «-01») — конструктор открывает первый, к остальным переход отсюда (владелец 20.10.2026).
    siblings = [{"id": x["id"], "number": x["number"], "confirmed": x["confirmed"]} for x in TA.annexes_of(db, m)]
    return {"code": m.code, "kind": a.kind, "siblings": siblings,
            "will_be": (f"ДС № {m.start_no + 1}" + (f"-{a.sub_no}" if a.sub_no else "")) if m.start_no is not None else None}


# Символы, запрещённые в именах файлов Windows. Слэш приходит сюда штатно: бренд
# собирается как «Рекламодатель / Бренд», и без замены файл не сохранился бы вовсе.
class SignerIn(BaseModel):
    """Реквизиты подписанта — правятся прямо с экрана ДС, а хранятся у подписанта юрлица (`counterparty_signers`, 28.10.2026).

    `signer_id` — подписант, который стоит в документе (выбранный договором или по умолчанию); без него правится подписант по
    умолчанию, а нет его — заводится. Трогаются ровно присланные поля.
    """
    signer_id: Optional[int] = None
    director_name: Optional[str] = None
    signer_position: Optional[str] = None
    signer_basis: Optional[str] = None


@router.put("/party/{counterparty_id}/signer")
def set_signer(counterparty_id: int, payload: SignerIn, db: Session = Depends(get_db),
               user: User = Depends(EDIT)):
    cp = db.query(Counterparty).filter(Counterparty.id == counterparty_id).first()
    if not cp:
        raise HTTPException(404, "Контрагент не найден")
    from app.signers import service as SG
    data = payload.dict(exclude_unset=True)
    sid = data.pop("signer_id", None)
    if not data:
        raise HTTPException(400, "Нечего сохранять")
    try:
        if sid is not None:
            s = SG.update(db, sid, data, user)
            if s.counterparty_id != cp.id:
                raise SG.SignerError(400, "Подписант не относится к этому юрлицу")
        else:
            s = SG.upsert_default(db, cp, data, user)
        db.commit()
    except SG.SignerError as e:
        db.rollback()
        raise HTTPException(e.status, e.message)
    log_action(db, user, "counterparty_signer", "counterparty", cp.id,
               "; ".join(f"{k}={v}" for k, v in data.items()))
    return {"id": cp.id, "signer_id": s.id if s else None, "director_name": s.director_name if s else None,
            "signer_position": s.signer_position if s else None, "signer_basis": s.signer_basis if s else None}


class PhraseIn(BaseModel):
    """Что человек НАБРАЛ в полях подписанта — ещё не сохранённое."""
    director_name: Optional[str] = None
    signer_position: Optional[str] = None
    signer_basis: Optional[str] = None


@router.post("/party/phrase")
def party_phrase(payload: PhraseIn, user: User = Depends(VIEW)):
    """Падежные формы для строки «в лице …» по НЕСОХРАНЁННЫМ значениям.

    Экран показывает под полями то, что реально напечатается, и обязан меняться по мере
    ввода. Склонять на клиенте нельзя: правила живут в `app/sales/rugram.py`, и вторая
    реализация разошлась бы с первой — в предпросмотре одна фамилия, в документе другая.
    """
    return {
        "position_gen": rugram.gen_position(payload.signer_position),
        "director_gen": rugram.gen_fio(payload.director_name),
        "basis_gen": rugram.gen_basis(payload.signer_basis),
        "acting": rugram.acting(payload.director_name),
    }


PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "http://pdf:3001")


@router.get("/{annex_id}/pdf")
def annex_pdf(annex_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW), with_basis: bool = False):
    """Нативный PDF приложения — тем же сайдкаром, что печатает медиаплан.

    Сайдкар открывает НАШУ ЖЕ печатную страницу и печатает её: второй вёрстки документа
    в проекте нет, значит расходиться нечему. Данные инжектятся в окно, поэтому браузеру
    не нужен ни токен, ни доступ к API — доступ проверен здесь.
    """
    a = _annex(db, annex_id, user)
    if not with_basis:
        _assert_no_open_legal(db, a)
    doc = _doc(db, a)
    assert_printable(doc)
    # Адрес печатной формы переехал вместе с разделом в Справочники (05.09.2026):
    # приложения к договору живут рядом с самими договорами, а не в контуре аккаунтов.
    payload = {"path": f"/directory/annexes/pdf/{a.id}", "key": "__ANNEX__", "footer": doc.get("master_code") or "",
               "flag": "__ANNEX_RENDERED__", "data": jsonable_encoder({**doc, "with_basis": bool(with_basis and doc.get("closing_basis"))})}
    try:
        r = httpx.post(f"{PDF_SERVICE_URL}/render", json=payload, timeout=60.0)
        r.raise_for_status()
    except Exception:
        raise HTTPException(502, "Сервис генерации PDF недоступен")
    # Имя файла — кириллицей, а заголовки HTTP умеют только latin-1. Поэтому RFC 5987:
    # ASCII-запасное имя для старых клиентов и `filename*` в UTF-8 для остальных. Без
    # этого ручка падала пятисоткой на кодировке заголовка, а не на документе.
    human = file_name(no=a.no, doc_date=doc["date"], brand=doc.get("brand"),
                      payer=(doc.get("customer") or {}).get("name"), basis=with_basis)
    ascii_name = f"Annex_{a.no or a.id}_{doc['date']:%Y-%m-%d}{'_with_basis' if with_basis else ''}.pdf"
    quoted = quote(human)
    return StreamingResponse(
        BytesIO(r.content), media_type="application/pdf",
        headers={"Content-Disposition":
                 f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quoted}"})


class StartNoIn(BaseModel):
    annex_start_no: Optional[int] = None


@router.get("/{annex_id}/docx")
def annex_docx(annex_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW), with_basis: bool = False):
    """Редактируемый .docx — тот же документ, что PDF, из того же собранного словаря.

    Оба формата нужны: PDF уходит на подпись, .docx — юристу клиента, который вносит
    правки до подписания. Проверка полноты реквизитов ОДНА И ТА ЖЕ: документ с прочерком
    на месте подписанта одинаково опасен в любом формате.
    """
    a = _annex(db, annex_id, user)
    if not with_basis:
        _assert_no_open_legal(db, a)
    doc = _doc(db, a)
    assert_printable(doc)
    data = docx_build.build_docx(doc, with_basis=with_basis)
    human = file_name(no=a.no, doc_date=doc["date"], brand=doc.get("brand"),
                      payer=(doc.get("customer") or {}).get("name"), basis=with_basis).replace(".pdf", ".docx")
    ascii_name = f"Annex_{a.no or a.id}_{doc['date']:%Y-%m-%d}{'_with_basis' if with_basis else ''}.docx"
    quoted = quote(human)
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition":
                 f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quoted}"})


@router.put("/contract/{contract_id}/start-no")
def set_start_no(contract_id: int, payload: StartNoIn, db: Session = Depends(get_db),
                 user: User = Depends(EDIT)):
    """Последний номер приложения, выданный ВНЕ системы.

    Ставится человеком и один раз: автоматически взять его из старых операций нельзя —
    там встречается мусор вроде 590425 (см. `annex.no_hint`).
    """
    c = _contract(db, contract_id)
    if payload.annex_start_no is not None and payload.annex_start_no < 0:
        raise HTTPException(400, "Номер не бывает отрицательным")
    old, c.annex_start_no = c.annex_start_no, payload.annex_start_no
    db.commit()
    log_action(db, user, "annex_start_no", "contract", c.id,
               f"стартовый номер: {old or '—'} → {c.annex_start_no or '—'}")
    return {"contract_id": c.id, "annex_start_no": c.annex_start_no,
            "next_no": annex_build.next_no(db, c)}


# ── шаблоны формулировок ─────────────────────────────────────────────────────

class TemplateIn(BaseModel):
    name: str
    body: str
    payer_id: Optional[int] = None
    is_default: bool = False


@router.get("/templates/list")
def list_templates(payer_id: Optional[int] = None, db: Session = Depends(get_db),
                   user: User = Depends(VIEW)):
    """Шаблоны: типовые и, если спросили про плательщика, его собственные."""
    q = db.query(AnnexTemplate)
    if payer_id:
        q = q.filter((AnnexTemplate.payer_id == payer_id)
                     | (AnnexTemplate.payer_id.is_(None)))
    rows = q.order_by(AnnexTemplate.payer_id.nullsfirst(), AnnexTemplate.id).all()
    return {"items": [{"id": t.id, "name": t.name, "body": t.body,
                       "payer_id": t.payer_id, "is_default": t.is_default}
                      for t in rows]}


@router.post("/templates")
def create_template(payload: TemplateIn, db: Session = Depends(get_db),
                    user: User = Depends(EDIT)):
    if not (payload.name or "").strip() or not (payload.body or "").strip():
        raise HTTPException(400, "Название и текст шаблона обязательны")
    t = AnnexTemplate(name=payload.name.strip(), body=payload.body,
                      payer_id=payload.payer_id, is_default=payload.is_default,
                      created_by=getattr(user, "id", None))
    db.add(t)
    db.commit()
    db.refresh(t)
    log_action(db, user, "annex_template_create", "counterparty", payload.payer_id,
               t.name)
    return {"id": t.id, "name": t.name}


@router.put("/templates/{template_id}")
def edit_template(template_id: int, payload: TemplateIn, db: Session = Depends(get_db),
                  user: User = Depends(EDIT)):
    """Правка шаблона НЕ меняет уже выпущенные приложения: они хранят ссылку на шаблон,
    но текст в документ подставлен на момент выпуска и лежит в файле."""
    t = db.query(AnnexTemplate).filter(AnnexTemplate.id == template_id).first()
    if not t:
        raise HTTPException(404, "Шаблон не найден")
    t.name, t.body = payload.name.strip(), payload.body
    t.payer_id, t.is_default = payload.payer_id, payload.is_default
    db.commit()
    log_action(db, user, "annex_template_edit", "counterparty", t.payer_id, t.name)
    return {"id": t.id, "name": t.name}


@router.get("/templates/keys")
def template_keys(user: User = Depends(VIEW)):
    """Какие подстановки понимает шаблон — чтобы редактор не гадал."""
    return {"keys": [
        {"key": "бренд", "hint": "Мезим / Mezym"},
        {"key": "период_с", "hint": "01.06.2026"},
        {"key": "период_по", "hint": "30.06.2026"},
        {"key": "номер", "hint": "68"},
        {"key": "сумма", "hint": "732 000.00"},
        {"key": "сумма_прописью", "hint": "732 000 (Семьсот тридцать две тысячи) рублей 00 копеек"},
        {"key": "ндс_ставка", "hint": "22"},
        {"key": "ндс_сумма", "hint": "132 000.00"},
        {"key": "ндс_сумма_прописью", "hint": "132 000 (Сто тридцать две тысячи) рублей 00 копеек"},
        {"key": "договор_номер", "hint": "РМ 30-11-2023"},
        {"key": "договор_дата", "hint": "30.11.2023"},
    ]}
