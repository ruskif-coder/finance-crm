# -*- coding: utf-8 -*-
"""Выход из «исход неизвестен»: сверка с кабинетом DSP и Weborama (владелец 23.09.2026).

Вызов, ушедший без ответа, ЗАПИРАЕТ повтор (этап 4 аудита): объект в чужом кабинете мог
создаться, а второй там не удалить. Но запертое без выхода — тупик, который до этого
снимался только запросом в базу. Выход устроен так же, как у ОРД: человек смотрит в
кабинет и отмечает одно из двух.

  · НАШЁЛ + id — объект записывается как наш, и следующее нажатие продолжает с него:
    DSP дошьёт код в найденный креатив, Weborama заберёт пиксель найденной вставки;
  · НЕТ В КАБИНЕТЕ — попытка закрывается как «не создано», повтор разрешён.

ПРОВЕРКА НАЙДЕННОГО. Чужой id, записанный как наш, хуже тупика: в него поедут код и
показы. Поэтому DSP спрашивается своим чтением (`getInfo`), вставка Weborama — своим
тегом. Метода чтения ПРОЕКТА и КАМПАНИИ Weborama мы вживую не проверяли, и выдумывать его
здесь нельзя — там id принимается как введён, и журнал попытки говорит это прямо.

ГДЕ ЛЕЖИТ ОТМЕТКА. У Weborama — в её же журнале попыток (`weborama_submissions`) и
реестре. У DSP — строкой в журнале отправок: «найден» записывается удачным вызовом с
хешом (его и находит защита от дублей), «нет» — строкой с `response.resolved`, которую
поиск зависших считает точкой сброса.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.ad.models import AdCampaign, AdCampaignCreative, AdCampaignPlacement
from app.dsp.campaigns import campaign_title
from app.dsp.client import XXHASH_RE, MsClient, MsError
from app.ext_lock import DSP_PROVISION, WEBORAMA_PROVISION, only_one
from app.sales.models import SalesDeal
from app.weborama import provision as wprov
from app.weborama.client import WcmClient, WcmError
from app.weborama.models import (KIND_CAMPAIGN, KIND_INSERTION, KIND_PROJECT,
                                 WeboramaRef, WeboramaSubmission)

WHAT = {KIND_PROJECT: "проект", KIND_CAMPAIGN: "кампания", KIND_INSERTION: "вставка"}
SYSTEMS = ("weborama", "dsp")


class ResolveError(RuntimeError):
    """Отметку принять нельзя. Текст показывается человеку как есть."""


def _placement_ids(db: Session, camp) -> list:
    return [p.id for p in db.query(AdCampaignPlacement)
            .filter(AdCampaignPlacement.campaign_id == camp.id).all()]


def _creatives(db: Session, camp) -> list:
    """Креативы РК без хеша — только у них может висеть заведение."""
    return [c for c in db.query(AdCampaignCreative)
            .filter(AdCampaignCreative.campaign_id == camp.id).all()
            if not (c.ms_creative_xxhash or "").strip()]


def _wb_scope(db: Session, camp) -> set:
    """Что из Weborama принадлежит этой РК: проект сделки, кампания РК, вставки площадок."""
    return ({(KIND_PROJECT, camp.deal_id), (KIND_CAMPAIGN, camp.id)}
            | {(KIND_INSERTION, i) for i in _placement_ids(db, camp)})


def _wb_hung(db: Session, camp, acc: str) -> list:
    scope = _wb_scope(db, camp)
    rows = (db.query(WeboramaSubmission)
            .filter(WeboramaSubmission.account_id == acc,
                    WeboramaSubmission.finished_at.is_(None),
                    WeboramaSubmission.kind.in_([k for k, _ in scope])).all())
    return [s for s in rows if (s.kind, s.local_id) in scope]


def _dsp_label(db: Session, camp) -> Optional[str]:
    deal = db.query(SalesDeal).get(camp.deal_id)
    return campaign_title(camp, deal) if deal else None


def list_unknown(db: Session, camp, *, dsp_client: Optional[MsClient] = None,
                 systems=SYSTEMS) -> list:
    """Зависшие попытки по РК — с тем, что искать в чужом кабинете."""
    out = []
    if "weborama" in systems:
        try:
            acc = wprov.account_id(db)
        except wprov.ProvisionError:
            acc = None
        for s in (_wb_hung(db, camp, acc) if acc else []):
            out.append({"system": "weborama", "ref": str(s.id),
                        "what": WHAT.get(s.kind, s.kind),
                        "label": (s.request or {}).get("label"),
                        "since": s.started_at.isoformat() if s.started_at else None,
                        "checked": s.kind == KIND_INSERTION})
    if "dsp" in systems:
        c = dsp_client or MsClient()
        if not getattr(camp, "ms_campaign_xxhash", None) and \
                c.unknown_refs("Campaign.add", "campaign", [camp.id]):
            out.append({"system": "dsp", "ref": "campaign", "what": "кампания",
                        "label": _dsp_label(db, camp), "since": None, "checked": True})
        crs = _creatives(db, camp)
        hung = c.unknown_refs("Creative.add", "creative", [f"cr{x.id}" for x in crs])
        for x in crs:
            if f"cr{x.id}" in hung:
                out.append({"system": "dsp", "ref": f"cr{x.id}", "what": "креатив",
                            "label": x.ms_title, "since": None, "checked": True})
    return out


def _hash_taken(db: Session, xx: str) -> bool:
    """Хеш уже записан за какой-то нашей РК или креативом."""
    return bool(db.query(AdCampaign.id).filter(AdCampaign.ms_campaign_xxhash == xx).first()
                or db.query(AdCampaignCreative.id)
                .filter(AdCampaignCreative.ms_creative_xxhash == xx).first())


def resolve(db: Session, camp, system: str, ref: str, *, found: bool,
            external_id: Optional[str], user, dsp_client: Optional[MsClient] = None,
            wcm_client: Optional[WcmClient] = None) -> dict:
    """Принять отметку человека после сверки с кабинетом.

    Под ТЕМ ЖЕ замком, что заведение (ревью 23.09.2026): попытка без ответа бывает и
    идущей — соседний клик ещё ждёт. Отметить её «нет в кабинете» значило бы открыть
    повтор, пока первый вызов может создать объект.
    """
    who = getattr(user, "name", None) or f"#{getattr(user, 'id', '?')}"
    if system == "weborama":
        with only_one(WEBORAMA_PROVISION, camp.deal_id, ResolveError, "Заведение в Weborama"):
            return _resolve_wb(db, camp, ref, found, external_id, user, who, wcm_client)
    if system == "dsp":
        with only_one(DSP_PROVISION, camp.id, ResolveError, "Выгрузка в DSP"):
            return _resolve_dsp(db, camp, ref, found, external_id, who,
                                dsp_client or MsClient())
    raise ResolveError(f"неизвестная система: {system}")


def _resolve_wb(db, camp, ref, found, external_id, user, who, client) -> dict:
    try:
        acc = wprov.account_id(db)
    except wprov.ProvisionError as e:
        raise ResolveError(str(e))
    try:
        sub = db.query(WeboramaSubmission).get(int(ref))
    except (TypeError, ValueError):
        sub = None
    # Отметить можно только незавершённую попытку ЭТОЙ РК: номер попытки приходит из
    # запроса, и чужой по нему закрывать нельзя.
    if (sub is None or sub.account_id != acc or sub.finished_at is not None
            or (sub.kind, sub.local_id) not in _wb_scope(db, camp)):
        raise ResolveError("Такой незавершённой попытки у этой РК нет — обновите экран")

    now = datetime.utcnow()
    if not found:
        sub.finished_at, sub.error = now, f"сверено вручную ({who}): в кабинете нет"
        db.commit()
        return {"system": "weborama", "ref": ref, "found": False}

    wid = "".join(ch for ch in (external_id or "") if ch.isdigit())
    if not wid:
        raise ResolveError("Укажите id объекта из кабинета Weborama — цифрами")
    checked = sub.kind == KIND_INSERTION
    if checked:
        try:
            (client or WcmClient(acc)).insertion_tag(wid)
        except WcmError as e:
            raise ResolveError(f"Weborama не отдаёт тег вставки {wid} — проверьте id: {e}")
    if wprov._ref(db, acc, sub.kind, sub.local_id):
        raise ResolveError("Этот объект уже записан как наш — обновите экран")
    # Тег доказывает, что вставка есть, но не что она ЭТОЙ площадки. Id, уже записанный
    # за другим объектом, — почти наверняка ошибка: показы легли бы не на ту площадку.
    if db.query(WeboramaRef.id).filter(WeboramaRef.account_id == acc,
                                       WeboramaRef.kind == sub.kind,
                                       WeboramaRef.wcm_id == wid).first():
        raise ResolveError(f"{WHAT.get(sub.kind, sub.kind).capitalize()} {wid} уже записан(а) "
                           f"за другим нашим объектом — проверьте id")
    db.add(WeboramaRef(account_id=acc, kind=sub.kind, local_id=sub.local_id, wcm_id=wid,
                       label=(sub.request or {}).get("label") or f"{sub.kind} {sub.local_id}",
                       created_by=getattr(user, "id", None)))
    sub.finished_at, sub.wcm_id = now, wid
    sub.error = (f"сверено вручную ({who}): найден"
                 + ("" if checked else "; id не проверен через API — метода чтения нет"))
    db.commit()
    return {"system": "weborama", "ref": ref, "found": True, "id": wid, "checked": checked}


def _resolve_dsp(db, camp, ref, found, external_id, who, c: MsClient) -> dict:
    if ref == "campaign":
        if getattr(camp, "ms_campaign_xxhash", None):
            raise ResolveError("Кампания в DSP уже записана — обновите экран")
        method, et, local = "Campaign.add", "campaign", str(camp.id)
    elif ref.startswith("cr") and ref[2:].isdigit() and \
            int(ref[2:]) in {x.id for x in _creatives(db, camp)}:
        method, et, local = "Creative.add", "creative", ref
    else:
        raise ResolveError("Такого креатива без хеша у этой РК нет — обновите экран")
    if local not in c.unknown_refs(method, et, [local]):
        raise ResolveError("По этому объекту нет незавершённой попытки — обновите экран")

    if found:
        xx = (external_id or "").strip().upper()
        if not XXHASH_RE.match(xx):
            raise ResolveError("Хеш из кабинета DSP — 16 знаков: цифры и буквы A–F")
        # `getInfo` отвечает на ЛЮБОЙ объект кабинета, включая чужие РК и тренировки
        # (ревью 23.09.2026). Поэтому ещё два условия: хеш не записан за другим нашим
        # объектом, и имя совпадает с тем, под которым мы заводили.
        if _hash_taken(db, xx):
            raise ResolveError(f"Хеш {xx} уже записан за другой нашей РК или креативом")
        try:
            info = (c.campaign_get_info if et == "campaign" else c.creative_get_info)(xx)
        except MsError as e:
            raise ResolveError(f"DSP не знает объект {xx} — проверьте хеш: {e}")
        want = (_dsp_label(db, camp) if et == "campaign"
                else next((x.ms_title for x in _creatives(db, camp) if f"cr{x.id}" == local),
                          None))
        got = info.get("title") if isinstance(info, dict) else None
        # Имя сравнивается, когда DSP его вернул: у кампании оно в ответе есть всегда
        # (замер 17.09.2026), у креатива — не проверяли, и выдумывать поле нельзя.
        if (got or et == "campaign") and want and got != want:
            raise ResolveError(f"В DSP под хешом {xx} — «{got}», а мы заводили «{want}». "
                               f"Это не наш объект — проверьте хеш")
        # Сперва журнал, потом наша колонка: не легла отметка — не пишем и хеш, иначе
        # повтор получил бы «уже записана», а попытка осталась бы висеть (ревью).
        c.journal_raw(method, et, local, {"resolved_by": who}, {"resolved": "found"},
                      xx, True, None)
        if c.unknown_outcome(method, et, local):
            raise ResolveError("Отметка не записалась в журнал DSP — попробуйте ещё раз")
        if et == "campaign":
            camp.ms_campaign_xxhash, camp.ms_synced_at = xx, datetime.utcnow()
            db.commit()
        return {"system": "dsp", "ref": ref, "found": True, "id": xx}
    else:
        xx = None
        c.journal_raw(method, et, local, {"resolved_by": who}, {"resolved": "not_found"},
                      None, False, f"сверено вручную ({who}): в кабинете нет")
    # Журнал отправок не роняет вызов при сбое записи — значит, проверяем, что отметка
    # легла: иначе человек увидел бы «принято», а повтор остался бы запертым.
    if c.unknown_outcome(method, et, local):
        raise ResolveError("Отметка не записалась в журнал DSP — попробуйте ещё раз")
    return {"system": "dsp", "ref": ref, "found": bool(found), "id": xx}


__all__ = ["list_unknown", "resolve", "ResolveError"]
