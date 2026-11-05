# -*- coding: utf-8 -*-
"""ДС, подписанный вне системы (владелец 02–03.11.2026, миграция 2026-11-03_annex_external.sql).

Внешний ДС — рабочий, как наш: занимает номер в счётчике договора, подписан, к нему уже привязаны сделки пакета и комплекты
УПД (их создал «В конструктор ДС →» из раскладки), он уходит в 1С. Отличие одно — документ не собирается конструктором:
это загруженный файл (слот «скан ДС» мастер-сделки) или ссылка на документ, ранее выгруженный в ЭДО.

Сумму с НДС и услуги указывает аккаунт — содержание документа (`sales_annex_items`). Сверки с раскладкой нет: «это задача
аккаунта такие вещи контролировать». Комплекты УПД по-прежнему из раскладки пакета — иначе в 1С ушло бы не то, что посчитала
сверка.

Сервис не коммитит: номер, файл и подпись сохраняет ручка одним разом (`annexes.commit_confirm`).
"""
import os
import re
import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.annex_tpl import doc_kind as DK
from app.master_deal import doc_sign as DS
from app.master_deal import issue as IS
from app.master_deal.models import MasterDealFile
from app.sales import units as U
from app.sales.models import SalesAddonService, SalesAnnex, SalesAnnexItem, SalesService

ORIGIN = "загружен"
ROOT, SUBDIR = "/app/uploads", "master_files"          # тот же каталог, что у сканов пакета (`master_deal/files.py`)
MAX_BYTES = 20 * 1024 * 1024
# Документ клиента бывает и исходником: к расширениям скана добавлены doc/docx.
EXT = (".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png", ".tif", ".tiff")


class ExternalError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def is_external(a) -> bool:
    return getattr(a, "origin", None) == ORIGIN


def rk_dates(a) -> tuple:
    """Даты РК по умолчанию для строк внешнего ДС — из строк МП черновика пакета (`rows`, снимок раскладки): самая ранняя
    «с», самая поздняя «по». Строк с датами нет — месяц пакета (`period_from`/`period_to` ДС)."""
    def d(v):
        return date.fromisoformat(v[:10]) if isinstance(v, str) and v else (v if isinstance(v, date) else None)
    starts = [x for x in (d(r.get("date_from")) for r in (a.rows or [])) if x]
    ends = [x for x in (d(r.get("date_to")) for r in (a.rows or [])) if x]
    return (min(starts) if starts else a.period_from, max(ends) if ends else a.period_to)


def _date(v, what: str) -> Optional[date]:
    if v in (None, ""):
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise ExternalError(400, f"{what} — дата")


def _items(db: Session, items: List[dict], default: tuple = (None, None), may_change_dates: bool = False) -> List[dict]:
    """Строки ДС: основная услуга (`service_id`) или доп. услуга (`addon_id`), сумма и количество. Единица — снимком из
    справочника (`app/sales/units.py`): смена модели закупки потом не меняет подписанный документ.

    Даты РК строки (`date_from`/`date_to` → `period_from`/`period_to`): по умолчанию — `default` (`rk_dates`); свои — только с
    правом «Мастер-сделки · согласование» (мастер аккаунт и админ, владелец 05.11.2026)."""
    out = []
    for it in items or []:
        sid, aid = it.get("service_id"), it.get("addon_id")
        if bool(sid) == bool(aid):
            raise ExternalError(400, "У строки — услуга или доп. услуга, одна")
        try:
            amount = float(it.get("amount"))
            volume = float(it["volume"]) if it.get("volume") not in (None, "") else None
        except (TypeError, ValueError):
            raise ExternalError(400, "Сумма и количество — числами")
        if amount <= 0:
            raise ExternalError(400, "Сумма услуги — больше нуля")
        if volume is not None and volume < 0:
            raise ExternalError(400, "Количество не бывает отрицательным")
        df = _date(it.get("date_from"), "Начало РК") or default[0]
        dt = _date(it.get("date_to"), "Конец РК") or default[1]
        if df and dt and df > dt:
            raise ExternalError(400, "Начало РК позже конца")
        if (df, dt) != tuple(default) and not may_change_dates:
            raise ExternalError(403, "Даты РК во внешнем ДС меняет мастер аккаунт или админ (право «Мастер-сделки · согласование»)")
        if sid:
            svc = db.get(SalesService, int(sid))
            if svc is None:
                raise ExternalError(400, "Такой услуги нет в справочнике")
            out.append({"service_id": svc.id, "addon_id": None, "amount": amount, "volume": volume,
                        "unit": U.service_unit(svc.calc_form), "period_from": df, "period_to": dt})
        else:
            add = db.get(SalesAddonService, int(aid))
            if add is None:
                raise ExternalError(400, "Такой доп. услуги нет в справочнике")
            out.append({"service_id": None, "addon_id": add.id, "amount": amount, "volume": volume,
                        "unit": U.addon_unit(add.period), "period_from": df, "period_to": dt})
    if not out:
        raise ExternalError(400, "Укажите услугу (или услуги) ДС с суммой — под них потом закрываются")
    return out


def _file(name: Optional[str], content: Optional[bytes]) -> Optional[tuple]:
    if not content:
        return None
    original = name or "ДС"
    if os.path.splitext(original)[1].lower() not in EXT:
        raise ExternalError(415, "Документ ДС — pdf, doc(x), jpg, png или tif")
    if len(content) > MAX_BYTES:
        raise ExternalError(413, f"Файл больше {MAX_BYTES // 1024 // 1024} МБ")
    return original, content


def _store(db: Session, a, user, f: tuple) -> dict:
    original, content = f
    os.makedirs(os.path.join(ROOT, SUBDIR), exist_ok=True)
    safe = re.sub(r"[^\w.-]", "_", original)
    rel = os.path.join(SUBDIR, f"{a.master_deal_id}_{uuid.uuid4().hex[:8]}_{safe}")
    with open(os.path.join(ROOT, rel), "wb") as fh:
        fh.write(content)
    old = db.query(MasterDealFile).filter(MasterDealFile.master_deal_id == a.master_deal_id,
                                          MasterDealFile.annex_id == a.id).first()
    old_path = old.path if old is not None else None
    if old is not None:
        db.delete(old)
        db.flush()
    row = MasterDealFile(master_deal_id=a.master_deal_id, kind=IS.SCAN_DS, annex_id=a.id, filename=original, path=rel,
                         size=len(content), content_type=None, uploaded_by=getattr(user, "id", None))
    db.add(row)
    db.flush()
    return {"path": rel, "old_path": old_path, "file_id": row.id}


def _main_future_no(db: Session, a) -> Optional[int]:
    """Номер, который получит неподтверждённый основной ДС пакета (последний актуальный + 1); подтверждён или его нет — None."""
    from app.master_deal.models import MasterDeal
    main = (db.query(SalesAnnex).filter(SalesAnnex.master_deal_id == a.master_deal_id, SalesAnnex.id != a.id,
                                        SalesAnnex.kind != "addons").first())
    if main is None or main.no is not None:
        return None
    m = db.get(MasterDeal, a.master_deal_id)
    return m.start_no + 1 if m is not None and m.start_no is not None else None


def sign_external(db: Session, a: SalesAnnex, user, *, no: Optional[int], number_text: Optional[str], doc_date: Optional[date],
                  total: Optional[float], items: List[dict], edo_link: Optional[str], file_name: Optional[str],
                  file_bytes: Optional[bytes], own_number: bool = False, may_change_dates: bool = False) -> dict:
    """Черновик ДС пакета → подтверждённый и подписанный внешний ДС. `own_number` — ДС допов подписан отдельным документом
    со своим номером (№ 29), а не суффиксом основного (28-01): владелец 05.11.2026, октябрь АПР Евразии. Возвращает {path, old_path} — прежний файл удаляет
    вызывающий после коммита. Отказ — ExternalError с текстом для человека; до него в базу ничего не пишется."""
    from app.links import validate_link
    if a.no is not None:
        # Выпущенный нами ДС можно переписать внешним (клиент подписал свой документ) — до «согласован»: дальше он ушёл
        # на согласование/подпись, и подмена разошлась бы с тем, что видел клиент (владелец 05.11.2026).
        if (getattr(a, "origin", None) or "система") != "система":
            raise ExternalError(409, "ДС уже загружен как подписанный вне системы")
        if (a.sign_state or "выпущен") != "выпущен":
            raise ExternalError(409, f"ДС уже «{a.sign_state}» — заменить внешним можно только выпущенный и ещё не согласованный")
    if not a.master_deal_id:
        raise ExternalError(409, "Подписать вне системы можно ДС мастер-сделки — черновик из раскладки пакета")
    if no is None or no <= 0:
        raise ExternalError(400, "Номер ДС — целое число больше нуля, как в подписанном документе")
    if own_number:
        if a.kind != "addons":
            raise ExternalError(400, "Свой номер вместо суффикса — только у ДС допов пакета")
        main_no = _main_future_no(db, a)
        if main_no is not None and no == main_no:
            raise ExternalError(409, f"№ {no} займёт основной ДС этого пакета — у ДС допов должен быть другой номер")
        a.sub_no = None
    if doc_date is None:
        raise ExternalError(400, "Дата ДС — как в подписанном документе")
    if not total or total <= 0:
        raise ExternalError(400, "Сумма ДС с НДС — больше нуля")
    lines = _items(db, items, rk_dates(a), may_change_dates)
    link = validate_link(edo_link) if (edo_link or "").strip() else None
    f = _file(file_name, file_bytes)
    if not link and not f:
        raise ExternalError(400, "Приложите файл ДС или ссылку на документ в ЭДО")
    busy = (db.query(SalesAnnex.id).filter(SalesAnnex.contract_id == a.contract_id, SalesAnnex.no == no,
                                          SalesAnnex.id != a.id,
                                          (SalesAnnex.sub_no == a.sub_no) if a.sub_no else SalesAnnex.sub_no.is_(None)).first())
    if busy:
        raise ExternalError(409, f"Номер {no} в этом договоре уже занят другим ДС")

    from app.models import Contract
    c = db.get(Contract, a.contract_id)
    kind = DK.resolve(getattr(a, "doc_kind", None), getattr(c, "annex_word", None), is_master=True)
    a.no, a.doc_kind = no, kind
    a.number = (number_text or "").strip() or DK.number_text(kind, f"{no}-{a.sub_no}" if a.sub_no else no)
    a.date, a.total_amount = doc_date, float(total)
    a.origin, a.edo_link = ORIGIN, link
    a.status, a.confirmed_by, a.confirmed_at = "подтверждён", getattr(user, "id", None), datetime.utcnow()
    db.query(SalesAnnexItem).filter(SalesAnnexItem.annex_id == a.id).delete()
    for ln in lines:
        db.add(SalesAnnexItem(annex_id=a.id, **ln))
    stored = _store(db, a, user, f) if f else {"path": None, "old_path": None, "file_id": None}
    # Подписан — сразу: документ уже подписан сторонами вне системы. Канал — ЭДО, если документ — ссылка оттуда.
    a.sign_state = DS.SIGNED
    a.sign_channel = DS.EDO if link else (a.sign_channel or DS._contract_channel(db, a))
    DS._write_event(db, a, state=DS.SIGNED, channel=a.sign_channel, source="вручную", reason="подписан вне системы",
                    file_id=stored["file_id"], by_user=getattr(user, "id", None))
    db.flush()
    return stored


def assert_not_external(a) -> None:
    """Выгрузка, пересоздание и правки текста — только у ДС, собранного конструктором."""
    if is_external(a):
        raise ExternalError(409, "ДС подписан вне системы — его документ: загруженный файл или ссылка ЭДО")
