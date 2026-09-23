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
import os
from datetime import date
from io import BytesIO
from typing import Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.models import Contract, Counterparty, User
from app.permissions import require_permission
from app.routers.sales_dashboard import _assert_deal_in_scope
from app.sales import annex as annex_build
from app.sales import annex_docx as docx_build
from app.sales import rugram
from app.sales.models import (AnnexTemplate, SalesAdvertiser, SalesAnnex, SalesDeal,
                              SalesDealAnnexAllocation as Alloc, SalesMediaPlan)

router = APIRouter()

# Своя секция прав с 06.09.2026 (миграция 2026-09-06_annexes_permission.sql): реестр
# приложений показывает суммы сделок и выпускает клиенту документы — это не то же самое,
# что правка карточки договора. Ключ неизменяем: он записан строкой в role_permissions.
VIEW = require_permission("annexes", "view")
CREATE = require_permission("annexes", "create")
EDIT = require_permission("annexes", "edit")


def _contract(db: Session, contract_id: int) -> Contract:
    c = db.query(Contract).filter(Contract.id == contract_id).first()
    if not c:
        raise HTTPException(404, "Договор не найден")
    return c


def _annex(db: Session, annex_id: int) -> SalesAnnex:
    a = db.query(SalesAnnex).filter(SalesAnnex.id == annex_id).first()
    if not a:
        raise HTTPException(404, "Приложение не найдено")
    return a


def _annex_deals(db: Session, annex_id: int) -> list:
    """Сделки, которые закрывает приложение — из таблицы разнесения сумм.

    Одно приложение может закрывать несколько сделок, и таблица заведена ровно затем,
    чтобы выручку можно было вернуть их авторам.
    """
    from app.sales.models import SalesDealAnnexAllocation
    return [d for (d,) in db.query(SalesDealAnnexAllocation.deal_id)
            .filter(SalesDealAnnexAllocation.annex_id == annex_id).all()]


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
        "template_id": a.template_id, "signed_place": a.signed_place,
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
    data = annex_build.build(db, c, period_from=period_from, period_to=period_to,
                             amount=amount, brand=brand, vat_rate=vat_rate,
                             deal_ids=_ids(deal_ids))
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
        signed_place=payload.signed_place or data["signed_place"],
        created_by=getattr(user, "id", None),
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
    a = _annex(db, annex_id)
    if a.no is not None:
        raise HTTPException(400, "Приложение подтверждено — правка запрещена")
    if payload.period_to < payload.period_from:
        raise HTTPException(400, "Конец периода раньше начала")
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
    # Дата тоже правится: правило «последний день предыдущего месяца» покрывает обычный
    # случай, но документ могут датировать последним рабочим днём или числом, о котором
    # договорились с клиентом. Пусто — остаётся посчитанная.
    #
    # Поле НЕ называется `date`: имя затенило бы тип `date` в этой же модели, и Pydantic
    # разобрал бы аннотацию как `Optional[None]` — поле принимало бы только пустоту, молча
    # и без ошибки при импорте.
    doc_date: Optional[date] = None


def _check_no(db: Session, c: Contract, no: int) -> None:
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
    taken = (db.query(SalesAnnex)
             .filter(SalesAnnex.contract_id == c.id, SalesAnnex.no == no).first())
    if taken:
        when = taken.date.strftime("%d.%m.%Y") if taken.date else "без даты"
        raise HTTPException(409, f"Номер {no} по этому договору уже занят "
                                 f"(приложение от {when})")


@router.post("/{annex_id}/confirm")
def confirm_annex(annex_id: int, payload: ConfirmIn, db: Session = Depends(get_db),
                  user: User = Depends(EDIT)):
    """Занять номер. С этого момента приложение перестаёт быть черновиком.

    Номер считается ПРЯМО СЕЙЧАС, а не при создании черновика: между сборкой и
    подтверждением кто-то мог выпустить своё приложение по тому же договору. Уникальность
    держит база (`uq_annex_contract_no`), и отказ по ней читается человеку понятным
    текстом, а не пятисоткой.
    """
    a = _annex(db, annex_id)
    if a.no is not None:
        raise HTTPException(400, "Приложение уже подтверждено")
    c = _contract(db, a.contract_id)
    # Номер запоминаем ОТДЕЛЬНОЙ переменной: после `rollback` объект сброшен, и в тексте
    # отказа оказалось бы «Номер None уже занят» — сообщение, по которому нечего понять.
    # `payload.no or ...` было бы ошибкой: ноль — ложь в Python, и введённый руками 0
    # молча превращался бы в следующий свободный номер вместо отказа.
    no = payload.no if payload.no is not None else annex_build.next_no(db, c)
    _check_no(db, c, no)
    if payload.doc_date:
        a.date = payload.doc_date
    a.no = no
    a.number = f"Приложение № {no}"
    a.status = "подтверждён"
    a.confirmed_by = getattr(user, "id", None)
    a.confirmed_at = date.today()
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(409, f"Номер {no} по этому договору уже занят")
    db.refresh(a)
    log_action(db, user, "annex_confirm", "contract", c.id, f"{a.number}")
    return _out(a)


# Потолок выдачи реестра. Он есть, и о нём надо СКАЗАТЬ: молча обрезанный список
# выглядит как «документ пропал», а не как «показано не всё» — и искать будут документ,
# а не страницу. Появятся тысячи — придут страницы; пока честно названного числа хватает.
LIST_LIMIT = 500


@router.get("")
def list_annexes(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Реестр приложений — учёт, о котором просил владелец: что выпущено и под каким
    номером. Черновики идут первыми: это незакрытая работа, а не архив."""
    total = db.query(sa_func.count(SalesAnnex.id)).scalar() or 0
    rows = (db.query(SalesAnnex, Contract, Counterparty)
            .join(Contract, Contract.id == SalesAnnex.contract_id)
            .outerjoin(Counterparty, Counterparty.id == Contract.counterparty_id)
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
    return {"total": total, "limit": LIST_LIMIT,
            "truncated": total > len(rows),
            "items": [{**_out(a),
                       # ИНН берётся из карточки контрагента, а не из договора: у
                       # легаси-договоров он бывает пуст, а у контрагента заполнен.
                       "counterparty_name": (cp.name if cp else None) or c.counterparty_name,
                       "counterparty_inn": (cp.inn if cp else None) or c.inn,
                       "contract_id": c.id,
                       "contract_number": c.contract_number,
                       "contract_date": c.contract_date,
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
    wb.save(buf)
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
    a = _annex(db, annex_id)
    c = _contract(db, a.contract_id)
    deals = _deal_cards(db, a.id)
    return {**_out(a), "doc": _doc(db, a),
            "deals": deals,
            "mismatch": _mismatch(a, deals),
            # Границу нумерации экран показывает рядом с полем: без неё отказ «номер не
            # больше стартового» выглядит как придирка непонятно к чему.
            "annex_start_no": c.annex_start_no,
            "next_no": annex_build.next_no(db, c)}


# Символы, запрещённые в именах файлов Windows. Слэш приходит сюда штатно: бренд
# собирается как «Рекламодатель / Бренд», и без замены файл не сохранился бы вовсе.
_BAD_IN_NAME = ('\\', '/', ':', '*', '?', '"', '<', '>',
                '|', '\r', '\n', '\t')


def file_name(*, no, doc_date, brand, payer) -> str:
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
    name = " — ".join(parts)
    for ch in _BAD_IN_NAME:
        name = name.replace(ch, " ")
    name = " ".join(name.split())
    # Ограничение длины имени файла — 255 байт в большинстве систем; кириллица в UTF-8
    # занимает по два, поэтому режем по символам с запасом.
    return (name[:110].rstrip() or "ДС") + ".pdf"


class SignerIn(BaseModel):
    """Реквизиты подписанта — правятся прямо с экрана ДС, а хранятся у контрагента.

    Отдельная ручка, а не общая правка контрагента: та перезаписывает карточку целиком
    (`cp.field = data.field` по всем полям), и частичный запрос с экрана ДС стёр бы
    адрес, банк и телефон. Здесь трогаются ровно присланные поля.
    """
    director_name: Optional[str] = None
    signer_position: Optional[str] = None
    signer_basis: Optional[str] = None


@router.put("/party/{counterparty_id}/signer")
def set_signer(counterparty_id: int, payload: SignerIn, db: Session = Depends(get_db),
               user: User = Depends(EDIT)):
    cp = db.query(Counterparty).filter(Counterparty.id == counterparty_id).first()
    if not cp:
        raise HTTPException(404, "Контрагент не найден")
    data = payload.dict(exclude_unset=True)
    if not data:
        raise HTTPException(400, "Нечего сохранять")
    for k, v in data.items():
        setattr(cp, k, (v or "").strip() or None)
    db.commit()
    log_action(db, user, "counterparty_signer", "counterparty", cp.id,
               "; ".join(f"{k}={v}" for k, v in data.items()))
    return {"id": cp.id, "director_name": cp.director_name,
            "signer_position": cp.signer_position, "signer_basis": cp.signer_basis}


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


def assert_printable(doc: dict) -> None:
    """Не дать выгрузить документ с прочерками на месте реквизитов.

    Проверка стоит на ВЫГРУЗКЕ, а не на подтверждении: номер можно занять заранее, а вот
    бумага с пустым местом там, где стоит подпись, уходит клиенту и подписывается не
    глядя. Чего не хватает — перечисляется поимённо, иначе отказ означает «сходи поищи».
    """
    miss = doc.get("missing") or []
    if miss:
        raise HTTPException(400, "Не хватает данных для документа: " + ", ".join(miss))


PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "http://pdf:3001")


def _doc(db: Session, a: SalesAnnex) -> dict:
    """Собранный документ по сохранённому приложению.

    Экран сборки и печать берут ЕГО ЖЕ: если бы экран считал сам, аккаунт проверял бы
    одни числа, а в PDF уходили другие — и разошлись бы они молча.
    """
    c = _contract(db, a.contract_id)
    return annex_build.build(db, c, period_from=a.period_from, period_to=a.period_to,
                             amount=a.total_amount or 0, vat_rate=a.vat_rate, no=a.no,
                             deal_ids=_annex_deals(db, a.id))


@router.get("/{annex_id}/pdf")
def annex_pdf(annex_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Нативный PDF приложения — тем же сайдкаром, что печатает медиаплан.

    Сайдкар открывает НАШУ ЖЕ печатную страницу и печатает её: второй вёрстки документа
    в проекте нет, значит расходиться нечему. Данные инжектятся в окно, поэтому браузеру
    не нужен ни токен, ни доступ к API — доступ проверен здесь.
    """
    a = _annex(db, annex_id)
    doc = _doc(db, a)
    assert_printable(doc)
    # Адрес печатной формы переехал вместе с разделом в Справочники (05.09.2026):
    # приложения к договору живут рядом с самими договорами, а не в контуре аккаунтов.
    payload = {"path": f"/directory/annexes/pdf/{a.id}", "key": "__ANNEX__",
               "flag": "__ANNEX_RENDERED__", "data": jsonable_encoder(doc)}
    try:
        r = httpx.post(f"{PDF_SERVICE_URL}/render", json=payload, timeout=60.0)
        r.raise_for_status()
    except Exception:
        raise HTTPException(502, "Сервис генерации PDF недоступен")
    # Имя файла — кириллицей, а заголовки HTTP умеют только latin-1. Поэтому RFC 5987:
    # ASCII-запасное имя для старых клиентов и `filename*` в UTF-8 для остальных. Без
    # этого ручка падала пятисоткой на кодировке заголовка, а не на документе.
    human = file_name(no=a.no, doc_date=doc["date"], brand=doc.get("brand"),
                      payer=(doc.get("customer") or {}).get("name"))
    ascii_name = f"Annex_{a.no or a.id}_{doc['date']:%Y-%m-%d}.pdf"
    quoted = quote(human)
    return StreamingResponse(
        BytesIO(r.content), media_type="application/pdf",
        headers={"Content-Disposition":
                 f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quoted}"})


class StartNoIn(BaseModel):
    annex_start_no: Optional[int] = None


@router.get("/{annex_id}/docx")
def annex_docx(annex_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Редактируемый .docx — тот же документ, что PDF, из того же собранного словаря.

    Оба формата нужны: PDF уходит на подпись, .docx — юристу клиента, который вносит
    правки до подписания. Проверка полноты реквизитов ОДНА И ТА ЖЕ: документ с прочерком
    на месте подписанта одинаково опасен в любом формате.
    """
    a = _annex(db, annex_id)
    doc = _doc(db, a)
    assert_printable(doc)
    data = docx_build.build_docx(doc)
    human = file_name(no=a.no, doc_date=doc["date"], brand=doc.get("brand"),
                      payer=(doc.get("customer") or {}).get("name")).replace(".pdf", ".docx")
    ascii_name = f"Annex_{a.no or a.id}_{doc['date']:%Y-%m-%d}.docx"
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
