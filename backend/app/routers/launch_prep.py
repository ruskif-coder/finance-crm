"""Модуль креативов: комплекты, получатели, первичная проверка.

Экран сборки креативов живёт на карточке сделки и получает всё дерево одним ответом —
тем же приёмом, что сборка ОРД: несколько запросов на один блок дают мигание и
рассинхрон, когда часть уже обновилась, а часть нет.

Что здесь есть и чего намеренно нет:

  · **получатели подставляются автоматически** по паре «услуга × поверхность» при первом
    открытии блока (решение владельца 27.08.2026) — аккаунт дальше снимает лишних.
    Срабатывает ровно один раз: признак не пустота списка, а отсутствие следа в журнале,
    иначе снятый вручную получатель возвращался бы при каждом открытии страницы.
    Разметка покрывает 190 живых сделок из 298, поэтому пустой результат объясняется
    текстом на экране, а не выглядит поломкой;
  · **услуга разрешается по цепочке медиаплан → продукт → выбор руками.** Ссылки на
    услугу у сделки нет, но имя из справочника лежит в `product` и совпадает у 297 живых
    сделок из 298;
  · **отправка — событие, а не флаг:** она заводит пары и ПУСТЫЕ строки ожидания. Пустой
    вердикт означает «спросили, ответа нет», и из этого списка берутся знаменатель порога
    ЕРИД и ответ на «кто молчит третий день»;
  · **маркер выпускается на КОМПЛЕКТ по порогу** согласовавших, а не на каждого
    получателя. Знаменатель — те, кому комплект отправлен, включая отказавших.

Таблицы созданы миграцией backend/migrations/2026-08-26_launch_prep_creatives.sql.
"""
import base64
import os
import re
import shutil
from datetime import date, datetime
from math import ceil
from types import SimpleNamespace
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.launch_prep import sandbox
from app.launch_prep.models import (SET_ORIGINS, TARGET_STATE_PUBLIC, TARGET_STATES,
                                    LaunchPrepCreativeFile, LaunchPrepCreativeSet,
                                    LaunchPrepPair, LaunchPrepPairFile, LaunchPrepReview,
                                    LaunchPrepSetTarget, LaunchPrepTarget,
                                    SalesRefusalReason, SalesReworkReason,
                                    SalesUrlRequestPhrase)
from app.models import AuditLog, User
from app.notify import emit
from app.ord import submit as ord_submit
from app.ord.client import OrdError
from app.ord import client as ord_client
from app.ord import registry
from app.ord.matching import resolve_final
from app.ord.models import OrdInitialContract, OrdKktu
from app.ord.payloads import OrdPayloadError
from app.permissions import require_any_permission, require_permission
from app.routers.sales_dashboard import _assert_deal_in_scope
from app.sales.models import (SalesBrand, SalesDeal, SalesMediaPlan, SalesMediaPlanRow,
                              SalesStage,
                              SalesPublisher, SalesPublisherService,
                              SalesPublisherSurface, SalesService)

router = APIRouter()

# Файлы креативов рядом с остальными загрузками, в том же volume (./uploads:/app/uploads).
# В колонке лежит ОТНОСИТЕЛЬНЫЙ ключ от корня хранилища — соглашение от 23.08.2026, и
# этот модуль его первый потребитель.
UPLOADS_ROOT = "/app/uploads"
CREATIVES_DIR = "creatives"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# HTML5-баннер приходит архивом; распаковка на нашей стороне не нужна — в ОРД он уезжает
# тем же архивом с признаком isArchive.
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
                      ".mp4", ".webm", ".mov", ".mp3", ".zip", ".html"}
ARCHIVE_EXTENSIONS = {".zip"}

VIEW = require_permission("creatives", "view")
EDIT = require_permission("creatives", "edit")
APPROVE = require_permission("creatives", "approve")
# Сам материал смотрит ещё и трафик — он его проверяет, и предпросмотр у него тот же
# самый компонент. Отдельного права на файл не заводим: у файла нет своей судьбы, он
# часть комплекта, и второе право означало бы, что его можно выдать без комплекта.
FILE_VIEW = require_any_permission((("creatives", "view"), ("traffic_queue", "view")))
# Тестовую ссылку нацеливания заводит ТРАФИК — это его инструмент проверки, — а
# пользуются ей и аккаунты. Право общее по той же причине, что и у файла: у ссылки нет
# своей судьбы, она свойство креатива, и второе право означало бы, что её можно выдать
# отдельно от него.
TARGETING_EDIT = require_any_permission((("creatives", "edit"), ("traffic_queue", "edit")))


# ============================== вспомогательное ==============================

def _deal(db: Session, deal_id: int, user: User) -> SalesDeal:
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, user, deal)
    return deal


def resolve_service(db: Session, deal: SalesDeal):
    """Услуга сделки и то, откуда она взялась.

    Ссылки на услугу у сделки нет — есть имя. Порядок источников не случаен:
    медиаплан точнее (там услуга выбрана из справочника при сборке), `product` —
    текст, приехавший из Битрикса. Оба сверяются с справочником по имени, потому что
    другого ключа нет; несовпадение возвращается честно, а не подменяется догадкой.
    """
    plan_ids = [p.id for p in db.query(SalesMediaPlan.id)
                .filter(SalesMediaPlan.deal_id == deal.id).all()]
    if plan_ids:
        names = [r.position for r in db.query(SalesMediaPlanRow.position)
                 .filter(SalesMediaPlanRow.plan_id.in_(plan_ids)).all() if r.position]
        for name in names:
            svc = db.query(SalesService).filter(SalesService.name == name).first()
            if svc:
                return svc, "из медиаплана"

    if deal.product:
        svc = db.query(SalesService).filter(SalesService.name == deal.product).first()
        if svc:
            return svc, "из продукта сделки"
        # Продукт есть, а услуги такой нет — это дыра в справочнике, и человек должен
        # увидеть её здесь, а не упереться в пустой список площадок.
        return None, f"продукт «{deal.product}» не найден в справочнике услуг"

    return None, "у сделки не указан продукт"


def _surfaces_from_plan(db: Session, deal: SalesDeal) -> List[str]:
    """Поверхности из медиаплана: `cross` означает обе, а не третью."""
    plan_ids = [p.id for p in db.query(SalesMediaPlan.id)
                .filter(SalesMediaPlan.deal_id == deal.id).all()]
    if not plan_ids:
        return []
    out = []
    for (inv,) in db.query(SalesMediaPlanRow.inventory).filter(
            SalesMediaPlanRow.plan_id.in_(plan_ids)).distinct().all():
        if inv == "cross":
            out += ["web", "app"]
        elif inv in ("web", "app"):
            out.append(inv)
    return sorted(set(out))


def _candidates(db: Session, service_id: int, surfaces: List[str]) -> List[dict]:
    """Площадки, у которых эта услуга отмечена на рабочей поверхности.

    Оба условия обязательны. Наличие строки поверхности значит «поверхность у площадки
    есть», а `we_work` — «мы с ней работаем»: в Excel это было склеено, и предлагать
    площадку, приложение которой мы не продаём, значит вернуть ту же путаницу.
    """
    q = (db.query(SalesPublisherService, SalesPublisher)
         .join(SalesPublisher, SalesPublisher.id == SalesPublisherService.publisher_id)
         .join(SalesPublisherSurface,
               (SalesPublisherSurface.publisher_id == SalesPublisherService.publisher_id)
               & (SalesPublisherSurface.kind == SalesPublisherService.surface_kind))
         .filter(SalesPublisherService.service_id == service_id,
                 SalesPublisherService.is_active.is_(True),
                 SalesPublisherSurface.we_work.is_(True)))
    if surfaces:
        q = q.filter(SalesPublisherService.surface_kind.in_(surfaces))
    rows = q.all()
    return [{"publisher_id": p.id, "name": p.name, "domain": p.domain,
             "code": p.code, "surface_kind": ps.surface_kind,
             # ТТ отдаются вместе с площадкой: кнопка рядом со списком открывает их
             # прямо на экране отправки, без похода в справочник.
             "tech_requirements": p.tech_requirements}
            for ps, p in sorted(rows, key=lambda r: r[1].name.lower())]


def _recipient_out(target, pub, pair=None, review=None, traffic=None,
                   files_count=0) -> dict:
    """Строка получателя внутри комплекта.

    До отправки это кандидат, после — пара с вердиктом и кодом. Одна форма на оба случая
    намеренно: экран рисует один список, а не два похожих, и не расходится между ними.

    Вердикт трафиков с 28.08.2026 показывается отдельным полем: он перестал быть
    автоматическим и встал ПЕРЕД площадкой, то есть у строки появилось состояние
    «ждём трафик», которого раньше не существовало. Пока он был машинным, галочка «ок»
    у каждой площадки была бы шумом, похожим на проделанную работу; теперь она — работа.
    """
    return {
        "target_id": target.id,
        "publisher_id": target.publisher_id,
        "name": pub.name if pub else None,
        "code": pub.code if pub else None,
        "tech_requirements": pub.tech_requirements if pub else None,
        "surface_kind": target.surface_kind,
        "state": target.state,
        "advertiser_url": target.advertiser_url,
        "url_state": url_state(target),
        "url_requested_at": target.url_requested_at,
        "url_request_text": target.url_request_text,
        # Пара появляется в момент отправки; до неё эти поля пусты.
        "pair_id": pair.id if pair else None,
        "pair_code": pair.code if pair else None,
        "sent_at": pair.sent_at if pair else None,
        "verdict": review.verdict if review else None,
        "reason": review.reason if review else None,
        "decided_by": review.decided_by if review else None,
        # Проверка трафика — ступень ПЕРЕД площадкой. Пустой вердикт при заведённой
        # строке означает «спросили, ответа нет»; отсутствие строки — «ещё не отправляли».
        "traffic_verdict": traffic.verdict if traffic else None,
        "traffic_reason": traffic.reason if traffic else None,
        "traffic_decided_by": traffic.decided_by if traffic else None,
        # «Есть скриншоты» в свёрнутой сводке и кнопка скачивания архива у аккаунта.
        "files_count": files_count,
    }


def _set_out(s: LaunchPrepCreativeSet, files, reviews, pairs=(), targets=None,
             pubs=None, candidates=(), file_counts=None) -> dict:
    """Комплект для экрана. Состояние ВЫЧИСЛЯЕТСЯ, а не читается из колонки.

    Площадки живут ВНУТРИ комплекта, а не отдельным списком сверху (решение владельца
    27.08.2026): креатив первичен — сначала прикрепляем материал, потом выбираем, кому он
    уходит. Поэтому `recipients` — до отправки кандидаты, после отправки пары; форма одна.
    """
    primary = next((r for r in reviews if r.kind == "первичная_тт" and r.pair_id is None), None)
    by_pair = {r.pair_id: r for r in reviews if r.kind == "площадка" and r.pair_id}
    by_traffic = {r.pair_id: r for r in reviews if r.kind == "трафики" and r.pair_id}
    targets = targets or {}
    pubs = pubs or {}
    file_counts = file_counts or {}

    if pairs:
        recipients = []
        for p in pairs:
            t = targets.get(p.target_id)
            if t is None:
                continue          # получателя сняли — пара ушла каскадом, строки нет
            recipients.append(_recipient_out(t, pubs.get(t.publisher_id), p, by_pair.get(p.id),
                                             by_traffic.get(p.id), file_counts.get(p.id, 0)))
    else:
        recipients = [_recipient_out(t, pubs.get(t.publisher_id)) for t in candidates]

    return {
        "id": s.id, "no": s.no, "title": s.title, "origin": s.origin,
        "replaces_set_id": s.replaces_set_id,
        "publisher_id": s.publisher_id,
        "scope": "персональный" if s.publisher_id else "общий",
        "form": s.form, "kktu_code": s.kktu_code, "description": s.description,
        "erid": s.erid, "erid_source": s.erid_source,
        "ord_status": s.ord_status, "ord_error": s.ord_error,
        "sent_at": s.sent_at,
        "test_targeting_url": s.test_targeting_url,
        "files": [{"id": f.id, "ratio": f.ratio, "name": f.original_name,
                   "size_bytes": f.size_bytes, "is_archive": f.is_archive,
                   "content_type": f.content_type,
                   # Готовый адрес, а не токен: собрать его должен тот, кто знает домен
                   # песочницы, а знает его окружение бэкенда, не браузер.
                   "sandbox_url": sandbox.public_url(f.sandbox_token, f.entry_path)}
                  for f in files],
        "primary_review": ({"verdict": primary.verdict, "reason": primary.reason,
                            "decided_by": primary.decided_by, "decided_at": primary.decided_at,
                            "source": primary.source} if primary else None),
        "recipients": recipients,
        "state": _set_state(s, primary, recipients),
    }


# Заглушка на случай, когда получателя пары уже нет: пара каскадом уходит вместе с ним,
# но между запросом и отрисовкой это возможно, и падать на None здесь незачем.
_NOTARGET = type("NoTarget", (), {"publisher_id": None, "surface_kind": None})()


def _set_state(s: LaunchPrepCreativeSet, primary, recipients=()) -> str:
    """Состояние комплекта — производное. Хранимая копия разъехалась бы с вердиктами.

    После разворота цепочки (28.08.2026) «отправлен» распалось надвое: материал сначала
    лежит у трафика и только его отмашкой уходит площадкам. Одно слово на оба состояния
    прямо вводило в заблуждение — владелец прочитал его как «ушло в площадку», когда
    пары стояли в очереди трафика. Плашка обязана называть того, У КОГО СЕЙЧАС МЯЧ.
    """
    if s.erid:
        return "маркирован"
    if primary is None or primary.verdict is None:
        return "черновик"
    if primary.verdict == "на доработку":
        return "на доработку"
    if not s.sent_at:
        return "готов к отправке"
    # Хотя бы одна пара ещё у трафика — комплект целиком считается непроверенным:
    # площадкам уходит материал, а не отдельные строки, и «частично отправлен»
    # состоянием комплекта не является.
    if any(r.get("pair_id") and not r.get("traffic_verdict") for r in recipients):
        return "у трафика"
    return "отправлен"


def _derive_form(files) -> Optional[str]:
    """Форма распространения — из самих файлов, а не из отдельного вопроса человеку.

    Значения из перечня ОРД. Архив и html — HTML5-баннер, видео — ролик, аудио — запись,
    остальное — баннер. Переопределить можно руками: смешанный комплект код не угадает.
    """
    exts = {os.path.splitext(f.original_name or "")[1].lower() for f in files}
    if exts & {".zip", ".html"}:
        return "BannerHtml5"
    if exts & {".mp4", ".webm", ".mov"}:
        return "Video"
    if exts & {".mp3"}:
        return "Audio"
    return "Banner" if exts else None


# ============================== чтение ==============================

@router.get("/deal/{deal_id}")
def deal_creatives(deal_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(VIEW)):
    """Всё дерево креативов сделки одним ответом."""
    deal = _deal(db, deal_id, current_user)
    service, service_reason = resolve_service(db, deal)

    targets = (db.query(LaunchPrepTarget)
               .filter(LaunchPrepTarget.deal_id == deal_id)
               .order_by(LaunchPrepTarget.id).all())
    pubs = {p.id: p for p in db.query(SalesPublisher).filter(
        SalesPublisher.id.in_([t.publisher_id for t in targets]))} if targets else {}

    sets = (db.query(LaunchPrepCreativeSet)
            .filter(LaunchPrepCreativeSet.deal_id == deal_id)
            .order_by(LaunchPrepCreativeSet.no).all())
    set_ids = [s.id for s in sets]
    files, reviews, pairs = [], [], []
    if set_ids:
        files = db.query(LaunchPrepCreativeFile).filter(
            LaunchPrepCreativeFile.set_id.in_(set_ids)).order_by(
            LaunchPrepCreativeFile.id).all()
        reviews = db.query(LaunchPrepReview).filter(
            LaunchPrepReview.set_id.in_(set_ids)).all()
        pairs = db.query(LaunchPrepPair).filter(
            LaunchPrepPair.set_id.in_(set_ids)).order_by(LaunchPrepPair.id).all()
    by_target = {t.id: t for t in targets}
    # Сколько скриншотов приложено к каждой паре — одним GROUP BY, а не запросом на строку.
    file_counts = {}
    if pairs:
        from sqlalchemy import func as sa_f
        file_counts = dict(db.query(LaunchPrepPairFile.pair_id,
                                    sa_f.count(LaunchPrepPairFile.id))
                           .filter(LaunchPrepPairFile.pair_id.in_([p.id for p in pairs]),
                                   LaunchPrepPairFile.kind == 'размещение')
                           .group_by(LaunchPrepPairFile.pair_id).all())

    return {
        "deal": {"id": deal.id, "code": deal.code, "title": deal.title,
                 "is_self_promo": bool(deal.is_self_promo)},
        "service": ({"id": service.id, "name": service.name} if service else None),
        "service_reason": service_reason,
        "surfaces": _surfaces_from_plan(db, deal),
        "targets": [{"id": t.id, "publisher_id": t.publisher_id,
                     "name": pubs[t.publisher_id].name if t.publisher_id in pubs else None,
                     "code": pubs[t.publisher_id].code if t.publisher_id in pubs else None,
                     "tech_requirements": (pubs[t.publisher_id].tech_requirements
                                           if t.publisher_id in pubs else None),
                     "surface_kind": t.surface_kind, "state": t.state,
                     "advertiser_url": t.advertiser_url,
                     "url_state": url_state(t),
                     "url_requested_at": t.url_requested_at,
                     "url_request_text": t.url_request_text}
                    for t in targets],
        "sets": [_set_out(s, [f for f in files if f.set_id == s.id],
                          [r for r in reviews if r.set_id == s.id],
                          [p for p in pairs if p.set_id == s.id],
                          by_target, pubs,
                          # Кандидаты нужны только неотправленному комплекту: у
                          # отправленного список уже зафиксирован парами.
                          () if any(p.set_id == s.id for p in pairs)
                          else _targets_for_set(db, s),
                          file_counts)
                 for s in sets],
    }


@router.get("/deal/{deal_id}/target-options")
def target_options(deal_id: int, set_id: Optional[int] = None,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(VIEW)):
    """Кого предлагаем и из кого выбирать руками.

    `proposed` — площадки с этой услугой на рабочей поверхности. `all` — весь справочник,
    потому что разметка покрывает две услуги из семи, и без ручного выбора модуль был бы
    неприменим к 108 живым сделкам из 298.
    """
    deal = _deal(db, deal_id, current_user)
    service, reason = resolve_service(db, deal)
    surfaces = _surfaces_from_plan(db, deal)
    # Занято — В ЭТОМ креативе, а не в сделке: площадка, получившая первый баннер,
    # обязана оставаться доступной для второго. Без set_id (старый вызов) считаем по
    # сделке, как раньше.
    q = db.query(LaunchPrepTarget.publisher_id).filter(LaunchPrepTarget.deal_id == deal_id)
    if set_id:
        q = q.join(LaunchPrepSetTarget,
                   LaunchPrepSetTarget.target_id == LaunchPrepTarget.id).filter(
            LaunchPrepSetTarget.set_id == set_id)
    taken = {t.publisher_id for t in q.all()}

    proposed = _candidates(db, service.id, surfaces) if service else []
    all_pubs = (db.query(SalesPublisher)
                .filter(SalesPublisher.status != "АРХИВ")
                .order_by(SalesPublisher.name).all())
    return {
        "service": ({"id": service.id, "name": service.name} if service else None),
        "service_reason": reason,
        "surfaces": surfaces,
        "proposed": [c for c in proposed if c["publisher_id"] not in taken],
        "all": [{"publisher_id": p.id, "name": p.name, "domain": p.domain, "code": p.code,
                 "already": p.id in taken} for p in all_pubs],
    }


# ============================== получатели ==============================

class TargetsIn(BaseModel):
    """Кого добавляем. Поверхность обязательна: одна площадка может брать веб и приложение
    по разным правилам, и «просто площадка» не определяет размещение."""
    items: List[dict]        # [{publisher_id, surface_kind}]
    set_id: Optional[int] = None      # в какой креатив; без него — только в сделку


def _attach(db: Session, deal, service, items, set_id: Optional[int]) -> List[str]:
    """Завести площадку у сделки (если её там нет) и адресовать ЭТОМУ креативу.

    Две записи, а не одна: площадка со своим состоянием и посадочной страницей живёт у
    сделки, а «кому этот баннер» — у креатива. Повтор безвреден: и то, и другое
    добавляется только когда отсутствует.
    """
    by_pub = {t.publisher_id: t for t in db.query(LaunchPrepTarget)
              .filter(LaunchPrepTarget.deal_id == deal.id).all()}
    member = set()
    if set_id:
        member = {m for (m,) in db.query(LaunchPrepSetTarget.target_id)
                  .filter(LaunchPrepSetTarget.set_id == set_id).all()}
    added = []                       # имена тех, кого адресовали ЭТОМУ креативу
    for item in items:
        pub_id = item.get("publisher_id")
        surface = item.get("surface_kind")
        if surface not in ("web", "app"):
            raise HTTPException(status_code=400, detail="Поверхность: web или app")
        pub = db.query(SalesPublisher).filter(SalesPublisher.id == pub_id).first()
        if not pub:
            raise HTTPException(status_code=404, detail=f"Площадка {pub_id} не найдена")
        target = by_pub.get(pub_id)
        # Поверхность решается ВЫШЕ — на услуге: площадка получает запрос по app, только
        # если приложение у неё подключено (владелец 28.08.2026). Сегодня ни у одной
        # площадки одна услуга не подключена на обеих поверхностях — замер 28.08.2026, ноль
        # случаев, — но ключ здесь по площадке, и появись такая связка, вторая поверхность
        # МОЛЧА взяла бы строку первой: запрос по приложению стал бы запросом по вебу.
        # Отказ вместо тишины: неверная поверхность в задании не видна ни нам, ни площадке.
        if target is not None and surface and target.surface_kind != surface:
            raise HTTPException(
                status_code=400,
                detail=f"«{pub.name}» уже добавлена в эту сделку с поверхностью "
                       f"«{target.surface_kind}». Две поверхности одной площадки в одной "
                       f"сделке модель пока не описывает — заведите вторую сделку")
        if target is None:
            target = LaunchPrepTarget(deal_id=deal.id, publisher_id=pub_id,
                                      service_id=service.id, surface_kind=surface,
                                      period_from=deal.period_from,
                                      period_to=deal.period_to)
            db.add(target)
            db.flush()                # у сессий проекта autoflush=False — нужен id
            by_pub[pub_id] = target
        if set_id and target.id not in member:
            db.add(LaunchPrepSetTarget(set_id=set_id, target_id=target.id))
            member.add(target.id)
            added.append(pub.name)
        elif not set_id:
            added.append(pub.name)
    return added


@router.post("/deal/{deal_id}/targets")
def add_targets(deal_id: int, payload: TargetsIn, db: Session = Depends(get_db),
                current_user: User = Depends(EDIT)):
    deal = _deal(db, deal_id, current_user)
    service, reason = resolve_service(db, deal)
    if service is None:
        # Услуга — ключ подстановки и снимок в получателе. Отказ здесь понятнее, чем
        # запись получателя без услуги и упор в это же на следующем шаге.
        raise HTTPException(status_code=400, detail=f"Услуга сделки не определена: {reason}")

    added = _attach(db, deal, service, payload.items, payload.set_id)
    db.commit()
    if added:
        log_action(db, current_user, "add_creative_targets", "sales_deal", deal_id,
                   f"креатив {payload.set_id}: {', '.join(added)}")
    return {"added": len(added)}


def _member_count(db: Session, set_id: Optional[int]) -> int:
    """Сколько площадок адресовано этому креативу."""
    if not set_id:
        return 0
    return (db.query(LaunchPrepSetTarget)
              .filter(LaunchPrepSetTarget.set_id == set_id).count())


TARGET_ACTIONS = ("add_creative_targets", "auto_creative_targets")


class AutoIn(BaseModel):
    set_id: Optional[int] = None


@router.post("/deal/{deal_id}/targets/auto")
def auto_targets(deal_id: int, payload: AutoIn = AutoIn(), db: Session = Depends(get_db),
                 current_user: User = Depends(EDIT)):
    """Подставить получателей по услуге при первом открытии блока.

    Решение владельца 27.08.2026: площадки, попадающие под услугу, подставляются сразу,
    а не выбираются в диалоге. Аккаунт дальше снимает лишних — это быстрее, чем каждый
    раз собирать список заново, а состав по услуге он и так знает наизусть.

    **Срабатывает ровно один раз.** Признак — не пустота списка (её можно получить,
    сняв всех вручную), а ОТСУТСТВИЕ СЛЕДА в журнале действий: снятый получатель не
    должен возвращаться при следующем открытии страницы. Отдельной колонки под «уже
    подставляли» не заводим — журнал и есть та память, и он durable по построению.

    Запись, а не чтение: подстановка добавляет строки, поэтому это POST, который зовёт
    экран, а не побочный эффект внутри GET.
    """
    deal = _deal(db, deal_id, current_user)
    if not payload.set_id:
        return {"added": 0, "reason": "не указан креатив"}
    if _member_count(db, payload.set_id):
        return {"added": 0, "reason": "получатели уже есть"}

    # ПОДСТАВЛЯЕМ ТОЛЬКО В ПЕРВЫЙ креатив сделки. Второй и дальше открываются пустыми
    # (владелец, 27.08.2026): второй материал обычно идёт не туда же, куда первый, и
    # копия чужого состава — это лишняя работа по вычёркиванию, а не экономия.
    first = (db.query(LaunchPrepCreativeSet.id)
               .filter(LaunchPrepCreativeSet.deal_id == deal_id)
               .order_by(LaunchPrepCreativeSet.no).first())
    if not first or first[0] != payload.set_id:
        return {"added": 0, "reason": "второй креатив собирается вручную"}

    seen = (db.query(AuditLog.id)
            .filter(AuditLog.entity_type == "sales_deal", AuditLog.entity_id == deal_id,
                    AuditLog.action.in_(TARGET_ACTIONS)).first())
    if seen:
        return {"added": 0, "reason": "состав уже собирали — подставлять заново не будем"}

    service, reason = resolve_service(db, deal)
    if service is None:
        return {"added": 0, "reason": reason}

    candidates = _candidates(db, service.id, _surfaces_from_plan(db, deal))
    if not candidates:
        return {"added": 0,
                "reason": f"у услуги «{service.name}» не отмечена ни одна площадка"}

    _attach(db, deal, service, candidates, payload.set_id)
    names = [c["name"] for c in candidates]
    db.commit()
    log_action(db, current_user, "auto_creative_targets", "sales_deal", deal_id,
               f"подставлено по услуге «{service.name}»: {', '.join(names)}")
    return {"added": len(names), "reason": f"по услуге «{service.name}»"}


@router.delete("/set/{set_id}/target/{target_id}")
def drop_set_target(set_id: int, target_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(EDIT)):
    """Убрать площадку ИЗ ЭТОГО креатива. У остальных она остаётся.

    Если после этого площадка не адресована ни одному креативу и ей ничего не отправляли,
    удаляем и её саму — тогда она возвращается в список выбора под кнопкой «+ Площадки».
    Оставь мы пустую строку у сделки, площадка числилась бы участником кампании, не
    получая ни одного материала, и в список выбора уже не вернулась бы.
    """
    row = db.query(LaunchPrepTarget).filter(LaunchPrepTarget.id == target_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Получатель не найден")
    _deal(db, row.deal_id, current_user)

    sent = (db.query(LaunchPrepPair)
              .filter(LaunchPrepPair.set_id == set_id,
                      LaunchPrepPair.target_id == target_id).first())
    if sent:
        raise HTTPException(status_code=400,
                            detail="Этой площадке комплект уже отправляли — снять нельзя")

    (db.query(LaunchPrepSetTarget)
       .filter(LaunchPrepSetTarget.set_id == set_id,
               LaunchPrepSetTarget.target_id == target_id)
       .delete(synchronize_session=False))
    db.flush()          # у сессий проекта autoflush=False: иначе увидим своё же членство

    orphan = not db.query(LaunchPrepSetTarget).filter(
        LaunchPrepSetTarget.target_id == target_id).first()
    if orphan and not row.pairs:
        db.delete(row)
    db.commit()
    return {"ok": True, "target_removed": bool(orphan and not row.pairs)}


# ============================== комплекты ==============================

class ProlongIn(BaseModel):
    """Новый период продлённой кампании. Всё остальное копируется как есть."""
    period_from: str
    period_to: Optional[str] = None


@router.post("/deal/{deal_id}/prolong")
def prolong_deal(deal_id: int, payload: ProlongIn, db: Session = Depends(get_db),
                 current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """Продлить кампанию: копия сделки новым периодом.

    Порядок, описанный владельцем 28.08.2026: любую РК можно скопировать, переносятся
    все данные, ставится новый период, сделка сразу на стадии сборки с уже пройденной
    проверкой трафика; дальше обычный процесс — площадка даёт «запуск разрешён», мы
    выпускаем новый ЕРИД.

    **Копия — экономия времени, а не особое состояние.** Исходная кампания живёт своей
    жизнью в рамках стадий и никуда не переводится.

    ЧТО НЕ КОПИРУЕТСЯ, и каждое по своей причине:

      · **ЕРИД и всё, что с ним связано** (`erid`, `ord_creative_id`, `ord_status`,
        `ord_env`). Маркер выдан на прошлый период; уехав в ЕРИР под ним, продление
        стало бы вторым размещением с одним идентификатором. Это ровно тот случай,
        когда «скопировать всё» тихо ломает отчётность;
      · **связь с ячейкой годового плана** (`year_plan_line_id`, `plan_month`,
        `plan_deal_idx`). Копия — не та же ячейка, и оставленная связь удвоила бы план;
      · **идентификатор Битрикса**: новая сделка заводится локальной, как всякая
        созданная у нас;
      · **виза медиаплана.** Цифры копируются все, а согласование — нет: виза даётся на
        конкретный период, и перенесённая она утверждала бы то, чего никто не смотрел.
    """
    src = _deal(db, deal_id, current_user)

    try:
        pf = date.fromisoformat(payload.period_from)
        pt = date.fromisoformat(payload.period_to) if payload.period_to else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Период в виде ГГГГ-ММ-ДД")
    if pt and pt < pf:
        raise HTTPException(status_code=400, detail="Конец периода раньше начала")

    stage = db.query(SalesStage).filter(SalesStage.stage_key == "launch_prep").first()

    import uuid as _uuid
    from app.sales.deal_code import assign_code

    new = SalesDeal(
        bitrix_id="local-" + _uuid.uuid4().hex,
        title=src.title, pipeline=src.pipeline, bitrix_stage=src.bitrix_stage,
        amount=src.amount, amount_with_vat=src.amount_with_vat, currency=src.currency,
        counterparty_id=src.counterparty_id, payer_counterparty_id=src.payer_counterparty_id,
        payer_name=src.payer_name,
        advertiser_id=src.advertiser_id, brand_id=src.brand_id, agency_id=src.agency_id,
        product=src.product,
        sales_rep_id=src.sales_rep_id, account_manager_id=src.account_manager_id,
        traffic_manager_id=src.traffic_manager_id,
        is_self_promo=src.is_self_promo,
        # Договоры ОРД переносятся: стороны те же, и цепочка у продления та же самая.
        ord_initial_contract_id=src.ord_initial_contract_id,
        ord_final_contract_id=src.ord_final_contract_id,
        our_stage_id=stage.id if stage else src.our_stage_id,
        period_from=pf, period_to=pt,
        prolonged_from_id=src.id,
        date_create=datetime.utcnow(),
    )
    assign_code(db, new)
    db.add(new)
    db.flush()

    # ── медиаплан: все показатели и цифры, виза сброшена ────────────────────
    plans = (db.query(SalesMediaPlan).filter(SalesMediaPlan.deal_id == src.id)
             .order_by(SalesMediaPlan.id.desc()).all())
    if plans:
        p0 = plans[0]
        mp = SalesMediaPlan(
            group_id=None, version=1, status="draft", title=p0.title,
            advertiser_id=p0.advertiser_id, brand_id=p0.brand_id, agency_id=p0.agency_id,
            payer_counterparty_id=p0.payer_counterparty_id,
            period=payload.period_from[:7], geo_id=p0.geo_id,
            date_from=pf, date_to=pt,
            targeting=p0.targeting, goals=p0.goals,
            sales_rep_id=p0.sales_rep_id, account_manager_id=p0.account_manager_id,
            traffic_manager_id=p0.traffic_manager_id,
            amount_net=p0.amount_net, amount_gross=p0.amount_gross,
            deal_id=new.id, created_by=getattr(current_user, "id", None),
        )
        db.add(mp)
        db.flush()
        for r in (db.query(SalesMediaPlanRow)
                  .filter(SalesMediaPlanRow.plan_id == p0.id)
                  .order_by(SalesMediaPlanRow.sort_order, SalesMediaPlanRow.id).all()):
            db.add(SalesMediaPlanRow(
                plan_id=mp.id, sort_order=r.sort_order, position=r.position,
                format=r.format, model=r.model, inventory=r.inventory,
                volume=r.volume, unit_price=r.unit_price, discount=r.discount,
                forecast=r.forecast))

    # ── площадки: состав, поверхность, посадочные ───────────────────────────
    old_to_new_target = {}
    personal_of = {}          # площадка → её старые получатели (для персональных комплектов)
    for t in (db.query(LaunchPrepTarget).filter(LaunchPrepTarget.deal_id == src.id)
              .order_by(LaunchPrepTarget.id).all()):
        personal_of.setdefault(t.publisher_id, []).append(t.id)
        nt = LaunchPrepTarget(
            deal_id=new.id, publisher_id=t.publisher_id, service_id=t.service_id,
            surface_kind=t.surface_kind,
            # ВСЕ начинают с «согласование», включая тех, кто отказал в прошлой кампании:
            # отказ закрывал ТО размещение, а не отношения с площадкой.
            state="согласование",
            period_from=pf, period_to=pt,
            # Посадочная переносится: страница у площадки та же, и заново её просить —
            # ровно та работа, ради экономии которой продление и делается.
            advertiser_url=t.advertiser_url)
        db.add(nt)
        db.flush()
        old_to_new_target[t.id] = nt.id

    # ── креативы: файлы, состав получателей, первичная проверка ─────────────
    sets = (db.query(LaunchPrepCreativeSet)
            .filter(LaunchPrepCreativeSet.deal_id == src.id,
                    LaunchPrepCreativeSet.erid.isnot(None))
            .order_by(LaunchPrepCreativeSet.no).all())
    if not sets:
        # Продлевать нечего: маркер не выпускался ни на один комплект, значит кампания
        # ещё не запускалась. Копия материала без этого была бы просто дублем сделки.
        sets = (db.query(LaunchPrepCreativeSet)
                .filter(LaunchPrepCreativeSet.deal_id == src.id)
                .order_by(LaunchPrepCreativeSet.no).all())

    copied_sets = 0
    for s0 in sets:
        ns = LaunchPrepCreativeSet(
            deal_id=new.id, publisher_id=s0.publisher_id, no=s0.no,
            title=s0.title, origin="продление",
            form=s0.form, kktu_code=s0.kktu_code, description=s0.description,
            test_targeting_url=s0.test_targeting_url,
            # erid / ord_* НЕ переносятся — см. шапку.
            erid_source=s0.erid_source)
        db.add(ns)
        db.flush()
        copied_sets += 1

        for f in (db.query(LaunchPrepCreativeFile)
                  .filter(LaunchPrepCreativeFile.set_id == s0.id)
                  .order_by(LaunchPrepCreativeFile.id).all()):
            src_path = os.path.join(UPLOADS_ROOT, f.path)
            if not os.path.exists(src_path):
                continue
            # Файл копируется ФИЗИЧЕСКИ, а не переиспользуется по пути: общая ссылка
            # означала бы, что удаление файла в одной кампании ломает предпросмотр в
            # другой. Архив весит сотни килобайт — цена копии несопоставима с ценой связи.
            stored = f"cre{ns.id}_" + os.path.basename(f.path).split("_", 1)[-1]
            dst_path = os.path.join(UPLOADS_ROOT, CREATIVES_DIR, stored)
            os.makedirs(os.path.join(UPLOADS_ROOT, CREATIVES_DIR), exist_ok=True)
            shutil.copyfile(src_path, dst_path)

            token = entry = None
            if f.is_archive:
                # Песочница разворачивается заново: у копии свой адрес предпросмотра.
                try:
                    token, entry = sandbox.unpack(dst_path, UPLOADS_ROOT)
                except sandbox.SandboxError:
                    token = entry = None
            db.add(LaunchPrepCreativeFile(
                set_id=ns.id, ratio=f.ratio, path=f"{CREATIVES_DIR}/{stored}",
                original_name=f.original_name, content_type=f.content_type,
                size_bytes=f.size_bytes, is_archive=f.is_archive,
                sandbox_token=token, entry_path=entry))

        # Адресуется ВЕСЬ список площадок изначального плана, а не состав того комплекта
        # (владелец 28.08.2026) — включая тех, кто в прошлый раз отказал: обстоятельства
        # могли измениться, товар появился, ограничение по бренду снялось. Спросить и
        # получить второй отказ дешевле, чем не спросить и потерять размещение.
        #
        # Исключение — персональный комплект (`publisher_id` заполнен): он собирался под
        # сложные ТТ конкретного сайта, и разослать его всем значило бы отправить
        # чужой материал.
        if s0.publisher_id:
            own = next((nt for t_old, nt in old_to_new_target.items()
                        if t_old in personal_of.get(s0.publisher_id, ())), None)
            if own:
                db.add(LaunchPrepSetTarget(set_id=ns.id, target_id=own))
        else:
            for nt in old_to_new_target.values():
                db.add(LaunchPrepSetTarget(set_id=ns.id, target_id=nt))

        # Первичная проверка переносится вместе с материалом: файл тот же, и требовать
        # её заново значит проверять то же самое второй раз.
        db.add(LaunchPrepReview(set_id=ns.id, kind="первичная_тт", verdict="ок",
                                source="продление", decided_by=current_user.name,
                                decided_at=datetime.utcnow()))

    db.commit()
    log_action(db, current_user, "prolong_deal", "sales_deal", new.id,
               f"продление {src.code} → {new.code}: площадок {len(old_to_new_target)}, "
               f"креативов {copied_sets}")
    return {"id": new.id, "code": new.code, "targets": len(old_to_new_target),
            "sets": copied_sets}


class SetIn(BaseModel):
    publisher_id: Optional[int] = None      # NULL = общий комплект
    origin: str = "первичный"
    replaces_set_id: Optional[int] = None


@router.post("/deal/{deal_id}/sets")
def create_set(deal_id: int, payload: SetIn, db: Session = Depends(get_db),
               current_user: User = Depends(EDIT)):
    _deal(db, deal_id, current_user)
    if payload.origin not in SET_ORIGINS:
        raise HTTPException(status_code=400, detail=f"Происхождение: {', '.join(SET_ORIGINS)}")
    if payload.replaces_set_id and payload.origin != "доработка":
        # То же ограничение стоит в базе (ck_lp_set_replaces); здесь оно повторено ради
        # внятного текста: IntegrityError пользователю ничего не объясняет.
        raise HTTPException(status_code=400,
                            detail="Ссылка на заменяемый комплект — только у доработки")

    last = (db.query(LaunchPrepCreativeSet.no)
            .filter(LaunchPrepCreativeSet.deal_id == deal_id)
            .order_by(LaunchPrepCreativeSet.no.desc()).first())
    row = LaunchPrepCreativeSet(deal_id=deal_id, publisher_id=payload.publisher_id,
                                no=(last[0] + 1) if last else 1,
                                origin=payload.origin,
                                replaces_set_id=payload.replaces_set_id)
    db.add(row)
    db.flush()          # у сессий проекта autoflush=False — id нужен ниже

    # Персональный комплект адресован ровно своей площадке, и это известно уже здесь:
    # доработка рождается из отказа конкретного получателя. Общий открывается ПУСТЫМ —
    # состав собирают руками (или подставляет `targets/auto`, но только у первого).
    if row.publisher_id:
        target = (db.query(LaunchPrepTarget)
                    .filter(LaunchPrepTarget.deal_id == deal_id,
                            LaunchPrepTarget.publisher_id == row.publisher_id).first())
        if target:
            db.add(LaunchPrepSetTarget(set_id=row.id, target_id=target.id))

    db.commit()
    db.refresh(row)
    log_action(db, current_user, "create_creative_set", "sales_deal", deal_id,
               f"комплект №{row.no} ({row.origin})")
    return {"id": row.id, "no": row.no}


class SetTitleIn(BaseModel):
    title: Optional[str] = None


@router.put("/set/{set_id}/title")
def set_title(set_id: int, payload: SetTitleIn, db: Session = Depends(get_db),
              current_user: User = Depends(EDIT)):
    """Переименовать креатив. Номер при этом не трогается — он опорный.

    Пустая строка снимает название, и комплект снова зовётся просто «Креатив №N»:
    это не то же, что «название потерялось», и отличать одно от другого не нужно.
    """
    row = db.query(LaunchPrepCreativeSet).filter(LaunchPrepCreativeSet.id == set_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Комплект не найден")
    _deal(db, row.deal_id, current_user)
    title = (payload.title or "").strip()
    if len(title) > 120:
        raise HTTPException(status_code=400, detail="Название длиннее 120 знаков")
    row.title = title or None
    db.commit()
    return {"id": row.id, "no": row.no, "title": row.title}


class TargetingUrlIn(BaseModel):
    url: Optional[str] = None


@router.put("/set/{set_id}/targeting-url")
def set_targeting_url(set_id: int, payload: TargetingUrlIn, db: Session = Depends(get_db),
                      current_user: User = Depends(TARGETING_EDIT)):
    """Тестовая ссылка нацеливания креатива — та, что ставит демо-куку кампании.

    Правится и после отправки, в отличие от файлов: она не входит в согласованный
    материал. Площадка согласовывает баннер, а ссылка — инструмент проверки на нашей
    стороне, и запрет её менять только мешал бы трафику.

    Схема проверяется, как у ссылки на документ договора: `javascript:` и `data:` в
    кликаемом поле — известный вектор, и одного лишь «поле техническое» тут мало.
    """
    row = db.query(LaunchPrepCreativeSet).filter(LaunchPrepCreativeSet.id == set_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Комплект не найден")
    _deal(db, row.deal_id, current_user)
    url = (payload.url or "").strip()
    if url and not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400,
                            detail="Ссылка должна начинаться с http:// или https://")
    if len(url) > 2000:
        raise HTTPException(status_code=400, detail="Ссылка длиннее 2000 знаков")
    row.test_targeting_url = url or None
    db.commit()
    return {"id": row.id, "test_targeting_url": row.test_targeting_url}


@router.delete("/set/{set_id}")
def drop_set(set_id: int, db: Session = Depends(get_db),
             current_user: User = Depends(EDIT)):
    """Удалить можно только неотправленный комплект без маркера."""
    row = db.query(LaunchPrepCreativeSet).filter(LaunchPrepCreativeSet.id == set_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Комплект не найден")
    _deal(db, row.deal_id, current_user)
    if row.sent_at or row.erid:
        raise HTTPException(status_code=400,
                            detail="Комплект уже отправлен или маркирован — удалить нельзя")
    for f in db.query(LaunchPrepCreativeFile).filter(
            LaunchPrepCreativeFile.set_id == set_id).all():
        _remove_file(f.path, f.sandbox_token)
    db.delete(row)
    db.commit()
    return {"ok": True}


# ============================== файлы ==============================

def _remove_file(rel_path: str, token: str = None):
    """Файл с диска: путь в колонке относительный, склейка — только здесь.

    Вместе с исходником убирается и распакованное в песочнице: оставленный каталог
    продолжал бы раздаваться по своему адресу после удаления материала — то есть
    отозванный баннер оставался бы доступен всем, у кого сохранилась ссылка.
    """
    try:
        os.remove(os.path.join(UPLOADS_ROOT, rel_path))
    except OSError:
        pass          # файла нет — запись всё равно уходит, иначе строка зависнет навсегда
    sandbox.remove(UPLOADS_ROOT, token)


@router.post("/set/{set_id}/files")
async def upload_file(set_id: int, ratio: Optional[str] = None,
                      file: UploadFile = File(...), db: Session = Depends(get_db),
                      current_user: User = Depends(EDIT)):
    row = db.query(LaunchPrepCreativeSet).filter(LaunchPrepCreativeSet.id == set_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Комплект не найден")
    _deal(db, row.deal_id, current_user)
    if row.sent_at:
        # Иначе получается «согласовали ровно этот файл», а файл потом подменили —
        # ровно та дыра, ради которой доработка сделана новой итерацией.
        raise HTTPException(status_code=400,
                            detail="Комплект отправлен — материал меняется новой итерацией")

    original = file.filename or "file"
    ext = os.path.splitext(original)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415,
                            detail=f"Недопустимый тип файла. Разрешены: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413,
                            detail=f"Файл слишком большой (максимум {MAX_UPLOAD_BYTES // 1024 // 1024} МБ)")

    safe = re.sub(r"[^\w.\-]", "_", original)
    # Имя несёт вид сущности: медиакит площадки №7 и файл комплекта №7 в общем каталоге
    # иначе затрут друг друга — это уже случалось с документами площадок.
    stored = f"cre{set_id}_{safe}"
    os.makedirs(os.path.join(UPLOADS_ROOT, CREATIVES_DIR), exist_ok=True)
    with open(os.path.join(UPLOADS_ROOT, CREATIVES_DIR, stored), "wb") as fh:
        fh.write(content)

    # Архив разворачивается в песочницу СРАЗУ, а не при первом открытии предпросмотра:
    # негодный архив тогда обнаружился бы через неделю, когда его пошли смотреть, — и уже
    # после того, как его отправили площадкам. Отказ здесь останавливает загрузку.
    token = entry = None
    if ext in ARCHIVE_EXTENSIONS:
        try:
            token, entry = sandbox.unpack(
                os.path.join(UPLOADS_ROOT, CREATIVES_DIR, stored), UPLOADS_ROOT)
        except sandbox.SandboxError as e:
            os.remove(os.path.join(UPLOADS_ROOT, CREATIVES_DIR, stored))
            raise HTTPException(status_code=400, detail=str(e))

    # Размер берём из самого баннера, если он там объявлен: имя файла врёт, а
    # `<meta name="ad.size">` пишет тот, кто баннер собирал.
    if token and not (ratio or "").strip():
        ratio = sandbox.read_size(UPLOADS_ROOT, token, entry)

    rec = LaunchPrepCreativeFile(
        set_id=set_id, ratio=(ratio or "").strip() or None,
        path=f"{CREATIVES_DIR}/{stored}",          # относительный ключ, не абсолютный путь
        original_name=original, content_type=file.content_type,
        size_bytes=len(content), is_archive=ext in ARCHIVE_EXTENSIONS,
        sandbox_token=token, entry_path=entry)
    db.add(rec)
    db.flush()

    # Форма выводится из состава файлов после каждой загрузки, пока её не переопределили.
    files = db.query(LaunchPrepCreativeFile).filter(
        LaunchPrepCreativeFile.set_id == set_id).all()
    row.form = _derive_form(files)
    db.commit()
    return {"id": rec.id, "form": row.form}


# Что показываем прямо в браузере, а что отдаём файлом. Картинка безопасна: разметка её
# не исполняет. HTML5-баннер — чужой исполняемый код, и место ему в песочнице на отдельном
# origin, а не на домене, где живёт сессия пользователя.
INLINE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                ".gif": "image/gif", ".webp": "image/webp"}


@router.get("/file/{file_id}")
def get_file(file_id: int, db: Session = Depends(get_db),
             current_user: User = Depends(FILE_VIEW)):
    """Отдать файл комплекта — для предпросмотра и скачивания.

    SVG в список показа НЕ входит, хотя это картинка: внутри него бывает скрипт, и
    отданный с типом image/svg+xml он исполняется при прямом открытии. Разница между
    «безопасно в <img>» и «безопасно по ссылке» слишком тонкая, чтобы полагаться на неё.
    """
    rec = db.query(LaunchPrepCreativeFile).filter(
        LaunchPrepCreativeFile.id == file_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Файл не найден")
    parent = db.query(LaunchPrepCreativeSet).filter(
        LaunchPrepCreativeSet.id == rec.set_id).first()
    _deal(db, parent.deal_id, current_user)

    full = os.path.join(UPLOADS_ROOT, rec.path)
    if not os.path.exists(full):
        raise HTTPException(status_code=404, detail="Файл не найден в хранилище")

    ext = os.path.splitext(rec.original_name or "")[1].lower()
    media = INLINE_TYPES.get(ext)
    if media:
        return FileResponse(full, media_type=media)
    # Всё остальное уезжает вложением: браузер сохранит, а не отрисует.
    return FileResponse(full, filename=rec.original_name or "creative",
                        media_type="application/octet-stream")


@router.delete("/file/{file_id}")
def drop_file(file_id: int, db: Session = Depends(get_db),
              current_user: User = Depends(EDIT)):
    rec = db.query(LaunchPrepCreativeFile).filter(
        LaunchPrepCreativeFile.id == file_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Файл не найден")
    parent = db.query(LaunchPrepCreativeSet).filter(
        LaunchPrepCreativeSet.id == rec.set_id).first()
    _deal(db, parent.deal_id, current_user)
    if parent.sent_at:
        raise HTTPException(status_code=400,
                            detail="Комплект отправлен — материал меняется новой итерацией")
    _remove_file(rec.path, rec.sandbox_token)
    db.delete(rec)
    db.commit()
    return {"ok": True}


# ============================== первичная проверка ==============================

class PrimaryReviewIn(BaseModel):
    verdict: str                    # ок | на доработку
    reason: Optional[str] = None


# ============================== отправка и вердикты ==============================

def _targets_for_set(db: Session, s: LaunchPrepCreativeSet) -> List[LaunchPrepTarget]:
    """Кому уходит этот комплект: персональный — только своей площадке, общий — всем.

    Всем, КРОМЕ тех, кто уже ушёл на персональный: площадка, отклонившая общий комплект,
    дальше живёт отдельно, и повторно слать ей общий значило бы спрашивать заново то, на
    что она уже ответила «нет».
    """
    # Состав берётся из ЧЛЕНСТВА (launch_prep_set_target), а не из площадок сделки.
    # До 27.08.2026 здесь стоял фильтр по deal_id, и все неотправленные комплекты
    # показывали один и тот же список: площадка, добавленная во второй креатив,
    # появлялась и в первом.
    q = (db.query(LaunchPrepTarget)
           .join(LaunchPrepSetTarget, LaunchPrepSetTarget.target_id == LaunchPrepTarget.id)
           .filter(LaunchPrepSetTarget.set_id == s.id)
           .order_by(LaunchPrepTarget.id))
    if s.publisher_id:
        return q.filter(LaunchPrepTarget.publisher_id == s.publisher_id).all()

    personal = {p for (p,) in db.query(LaunchPrepCreativeSet.publisher_id)
                .filter(LaunchPrepCreativeSet.deal_id == s.deal_id,
                        LaunchPrepCreativeSet.publisher_id.isnot(None)).all()}
    # Отказавшаяся площадка из кампании выпала: слать ей следующий комплект значит
    # спрашивать заново то, на что уже ответили «мы это не берём».
    return [t for t in q.all()
            if t.publisher_id not in personal and t.state != "отказ площадки"]


def _next_pair_no(db: Session, target_id: int) -> int:
    """Номер креатива внутри размещения: считаем СРОСШИЕСЯ пары, а не итерации.

    Отвергнутая итерация имени не получала, поэтому в нумерации нет дыр от версий,
    которых не было в эфире.
    """
    named = (db.query(LaunchPrepPair)
             .filter(LaunchPrepPair.target_id == target_id,
                     LaunchPrepPair.code.isnot(None)).count())
    return named + 1


def _pair_code(deal_code: str, publisher_code: str, no: int) -> str:
    return f"{deal_code}-{publisher_code}-{no:02d}"


def _recompute_target_state(db: Session, target: LaunchPrepTarget):
    """Состояние получателя — из его пар. Хранится, но пересчитывается по фактам.

    Дальше «согласован» состояние двигает маркер и запуск (этап 4): здесь только первый
    переход, чтобы не заводить половину машины состояний в двух местах.

    **`flush()` обязателен.** У сессий проекта `autoflush=False` (`app/database.py`),
    поэтому запрос ниже не увидел бы `agreed_at`, поставленный этим же вызовом парой
    строк выше: состояние осталось бы прежним, ничего не упало бы, и расхождение
    всплыло бы позже — у площадки, которая согласовала, но числится ждущей.
    """
    db.flush()
    if target.state not in (None, "согласование"):
        return
    agreed = (db.query(LaunchPrepPair)
              .filter(LaunchPrepPair.target_id == target.id,
                      LaunchPrepPair.agreed_at.isnot(None)).first())
    if agreed:
        target.state = "согласован"


class SendIn(BaseModel):
    """Отправка комплекта получателям. Список пуст = всем, кому этот комплект адресован."""
    target_ids: Optional[List[int]] = None


@router.post("/set/{set_id}/send")
def send_set(set_id: int, payload: SendIn, db: Session = Depends(get_db),
             current_user: User = Depends(EDIT)):
    """Отправка — событие, а не флаг: она заводит пары и ПУСТЫЕ строки ожидания.

    Пустой вердикт означает «спросили, ответа нет». Из этого списка берутся сразу две
    величины: знаменатель порога ЕРИД и ответ на «кто молчит третий день» для пинга.
    Заводи мы строку только вместе с вердиктом — обе стали бы невычислимыми.

    Вердикт трафиков проставляется автоматически «ок» с источником `авто` (решение
    владельца 26.08.2026) — до появления конвейера проверки и раздела трафиков.
    Источник отдельным значением нужен затем, чтобы машинная отметка не стала со временем
    неотличимой от человеческой.
    """
    s = db.query(LaunchPrepCreativeSet).filter(LaunchPrepCreativeSet.id == set_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Комплект не найден")
    deal = _deal(db, s.deal_id, current_user)

    primary = (db.query(LaunchPrepReview)
               .filter(LaunchPrepReview.set_id == set_id,
                       LaunchPrepReview.pair_id.is_(None),
                       LaunchPrepReview.kind == "первичная_тт").first())
    if primary is None or primary.verdict != "ок":
        raise HTTPException(status_code=400,
                            detail="Сначала первичная проверка материала по ТТ")

    targets = _targets_for_set(db, s)
    if payload.target_ids:
        targets = [t for t in targets if t.id in set(payload.target_ids)]
    if not targets:
        raise HTTPException(status_code=400, detail="Некому отправлять: получатели не выбраны")

    # Код площадки нужен, чтобы пара получила имя при схождении. Проверяем ЗДЕСЬ, а не
    # на вердикте: отправить то, что потом нельзя будет назвать, — тупик, а на вердикте
    # отказ пришёлся бы на факт, который сообщила площадка, и чинить его поздно.
    pubs = {p.id: p for p in db.query(SalesPublisher).filter(
        SalesPublisher.id.in_([t.publisher_id for t in targets])).all()}
    unnamed = [pubs[t.publisher_id].name for t in targets
               if not (pubs.get(t.publisher_id) and pubs[t.publisher_id].code)]
    if unnamed:
        raise HTTPException(
            status_code=400,
            detail=f"Не задан код площадки: {', '.join(sorted(unnamed))}. "
                   f"Без него размещение не получит номер для DSP")

    from sqlalchemy.sql import func as sa_func
    created = 0
    for t in targets:
        pair = (db.query(LaunchPrepPair)
                .filter(LaunchPrepPair.set_id == set_id,
                        LaunchPrepPair.target_id == t.id).first())
        if pair:
            continue          # повторная отправка тем же получателям — не дубль
        pair = LaunchPrepPair(set_id=set_id, target_id=t.id)
        db.add(pair)
        db.flush()
        # Спрашиваем ТОЛЬКО трафик (разворот цепочки 28.08.2026). Строка площадки здесь
        # не заводится: «строка проверки = спросили», а площадку ещё не спрашивали —
        # материал до неё не дошёл. Заводит её вердикт трафика, см. routers/traffic.py.
        #
        # `sent_at` пары тоже остаётся пустым: он означает «ушла площадке», и так было
        # написано в модели с самого начала — до разворота цепочки это просто совпадало
        # с моментом создания пары.
        #
        # ПРОДЛЕНИЕ — единственное исключение: материал скопирован с прошлой кампании и
        # трафиком уже проверен, повторная проверка того же файла ничего не добавит.
        # Отметка идёт источником `продление`, а не `авто`: разница между «никто не
        # смотрел» и «смотрели в прошлом периоде» стоит отдельного значения.
        if s.origin == "продление":
            db.add(LaunchPrepReview(set_id=set_id, pair_id=pair.id, kind="трафики",
                                    verdict="ок", source="продление",
                                    decided_at=sa_func.now()))
            db.add(LaunchPrepReview(set_id=set_id, pair_id=pair.id, kind="площадка",
                                    source="аккаунт"))
            pair.sent_at = sa_func.now()
        else:
            db.add(LaunchPrepReview(set_id=set_id, pair_id=pair.id, kind="трафики",
                                    source="трафики"))
        created += 1

    if s.sent_at is None:
        s.sent_at = sa_func.now()
    db.commit()
    log_action(db, current_user, "send_creative_set", "sales_deal", deal.id,
               f"комплект №{s.no}: отправлен на проверку трафику — пар {created}")
    if created:
        emit(db, "creative_set_sent",
             title=f"Комплект №{s.no} — на проверке у трафика · {deal.code}",
             body=f"Пар в очереди: {created}. Площадкам уйдёт после проверки.",
             link=f"/sales/deals/{deal.code or deal.id}",
             entity_type="sales_deal", entity_id=deal.id, actor=current_user,
             ctx={"deal_id": deal.id})
        db.commit()
    return {"sent": created}


class PairVerdictIn(BaseModel):
    verdict: str                    # ок | на доработку
    reason: Optional[str] = None


PLATFORM_VERDICTS = ("ок", "на доработку", "отказ")


def apply_platform_verdict(db: Session, pair_id: int, verdict: str,
                           reason: Optional[str], author_name: str,
                           author_email: Optional[str], source: str, actor=None) -> dict:
    """Записать вердикт площадки. ОДНА функция на два входа: аккаунт и кабинет.

    Правил здесь больше, чем кажется: неизменяемость, обязательная причина у обоих
    отрицательных исходов, инвариант порядка «после трафика», выдача кода пары по
    схождению, боковой выход в «отказ площадки». Вторая их реализация — в SQL или в
    сервисе кабинета — разошлась бы с этой; в проекте так уже случалось со срочностью
    и с разбором кварталов.

    Поэтому кабинет НЕ пишет в базу: он зовёт ядро, и запись делает этот код. Инвариант
    «у таблицы один писатель» от этого не ослаб, а усилился.

    `source` отличает, чьими руками записано: 'аккаунт' — со слов площадки, 'кабинет' —
    самой площадкой. Через год отличить одно от другого будет уже не по чему.
    """
    pair = db.query(LaunchPrepPair).filter(LaunchPrepPair.id == pair_id).first()
    if not pair:
        raise HTTPException(status_code=404, detail="Пара не найдена")
    s = db.query(LaunchPrepCreativeSet).filter(
        LaunchPrepCreativeSet.id == pair.set_id).first()
    deal = db.query(SalesDeal).filter(SalesDeal.id == s.deal_id).first()

    if verdict not in PLATFORM_VERDICTS:
        raise HTTPException(status_code=400,
                            detail="Вердикт: «ок», «на доработку» или «отказ»")
    if verdict in ("на доработку", "отказ") and not (reason or "").strip():
        raise HTTPException(status_code=400, detail="Укажите причину")

    # ИНВАРИАНТ ПОРЯДКА (28.08.2026): площадка отвечает только после трафика. Проверка
    # стоит здесь, а не только на экране: спрятанная кнопка возвращается первым же
    # рефакторингом, а порог ЕРИД опирается на то, что «ок» площадки означает оба «ок».
    traffic = (db.query(LaunchPrepReview)
               .filter(LaunchPrepReview.pair_id == pair_id,
                       LaunchPrepReview.kind == "трафики").first())
    if traffic is None or traffic.verdict != "ок":
        raise HTTPException(
            status_code=400,
            detail="Материал ещё не прошёл проверку трафика — площадке он не отправлен")

    # НЕЗАКРЫТЫЙ ЗАПРОС ССЫЛКИ БЛОКИРУЕТ «ок» (владелец 29.08.2026).
    #
    # Условие узкое: мешает не отсутствие посадочной, а то, что мы САМИ её попросили и
    # ещё ждём. Не спрашивали — не мешаем (ссылку могли согласовать письмом); ссылка
    # есть — тем более. «Ок» при висящем запросе означал бы, что мы молча сняли
    # собственный вопрос: пара сходится, выдаётся код в DSP, за ним идёт ЕРИД — а вести
    # рекламу некуда, и обнаружится это уже на старте.
    #
    # Отрицательные исходы не трогаем: и доработка, и отказ закрывают вопрос вместе с
    # размещением — требовать под них посадочную бессмысленно.
    #
    # Проверка здесь, а не только на кнопке, по той же причине, что и инвариант выше:
    # входов в эту функцию два (аккаунт и кабинет), и правило, оставленное на экранах,
    # существовало бы в двух экземплярах и разошлось бы.
    if verdict == "ок":
        target = db.query(LaunchPrepTarget).filter(
            LaunchPrepTarget.id == pair.target_id).first()
        if target is not None and url_state(target) == "запрошена":
            raise HTTPException(
                status_code=400,
                detail="Мы ждём от этой площадки посадочную страницу — "
                       "согласовать можно после того, как придёт ссылка")

    rec = (db.query(LaunchPrepReview)
           .filter(LaunchPrepReview.pair_id == pair_id,
                   LaunchPrepReview.kind == "площадка").first())
    if rec is None:
        raise HTTPException(status_code=400, detail="Комплект этой площадке не отправляли")
    if rec.verdict is not None:
        raise HTTPException(status_code=400,
                            detail="Вердикт уже выставлен. Доработка — это новый комплект")

    from sqlalchemy.sql import func as sa_func
    rec.verdict = verdict
    rec.reason = (reason or "").strip() or None
    rec.decided_by = author_name
    rec.decided_email = (author_email or "").strip() or None
    rec.decided_at = sa_func.now()
    rec.source = source

    code = None
    if verdict == "отказ":
        # Площадка выпадает из кампании: новая версия ей не поможет, и висеть в ожидании
        # доработки она не должна — иначе порог ЕРИД будет вечно ждать её ответа, который
        # уже дан. В знаменателе порога она остаётся: спрашивали — значит считаем.
        target = db.query(LaunchPrepTarget).filter(
            LaunchPrepTarget.id == pair.target_id).first()
        if target:
            target.state = "отказ площадки"
    if verdict == "ок":
        target = db.query(LaunchPrepTarget).filter(
            LaunchPrepTarget.id == pair.target_id).first()
        pub = db.query(SalesPublisher).filter(
            SalesPublisher.id == target.publisher_id).first()
        code = _pair_code(deal.code, pub.code, _next_pair_no(db, target.id))
        pair.code = code
        pair.agreed_at = sa_func.now()
        _recompute_target_state(db, target)

    db.commit()
    who = f" ({author_name})" if source == "кабинет" else ""
    log_action(db, actor, "creative_pair_verdict", "sales_deal", deal.id,
               f"комплект №{s.no}: {verdict}{who}" + (f", код {code}" if code else ""))
    emit(db, "creative_verdict",
         title=f"Площадка ответила: {verdict} · {deal.code}",
         body=(rec.reason or f"Комплект №{s.no}" + (f", код {code}" if code else "")),
         link=f"/sales/deals/{deal.code or deal.id}",
         entity_type="sales_deal", entity_id=deal.id, actor=actor,
         ctx={"deal_id": deal.id})
    db.commit()
    return {"verdict": rec.verdict, "code": code, "deal_id": deal.id}


@router.post("/pair/{pair_id}/verdict")
def pair_verdict(pair_id: int, payload: PairVerdictIn, db: Session = Depends(get_db),
                 current_user: User = Depends(APPROVE)):
    """Вердикт площадки, записанный АККАУНТОМ с её слов (звонок, письмо, чат).

    Второй вход в ту же запись — из кабинета, там площадка отвечает сама. Различает их
    `source`; правила у обоих одни и те же, потому что функция одна.
    """
    pair = db.query(LaunchPrepPair).filter(LaunchPrepPair.id == pair_id).first()
    if not pair:
        raise HTTPException(status_code=404, detail="Пара не найдена")
    s = db.query(LaunchPrepCreativeSet).filter(
        LaunchPrepCreativeSet.id == pair.set_id).first()
    # Область видимости сделки — до записи: аккаунт не отвечает за чужие сделки.
    _deal(db, s.deal_id, current_user)
    out = apply_platform_verdict(db, pair_id, payload.verdict, payload.reason,
                                 current_user.name, getattr(current_user, "email", None),
                                 "аккаунт", actor=current_user)
    return {"verdict": out["verdict"], "code": out["code"]}


# ============================== причины доработки ==============================

class ReasonIn(BaseModel):
    name: str


@router.get("/rework-reasons")
def rework_reasons(db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    rows = (db.query(SalesReworkReason)
            .filter(SalesReworkReason.is_active.is_(True))
            .order_by(SalesReworkReason.sort_order, SalesReworkReason.name).all())
    return {"items": [{"id": r.id, "name": r.name} for r in rows]}


@router.post("/rework-reasons")
def add_rework_reason(payload: ReasonIn, db: Session = Depends(get_db),
                      current_user: User = Depends(EDIT)):
    """Накопитель: новая причина уходит в общий список и дальше предлагается всем.

    Имя хранится строкой в вердикте, а не внешним ключом — переименование значения не
    должно осиротить уже вынесенные вердикты.
    """
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Пустая причина")
    row = db.query(SalesReworkReason).filter(SalesReworkReason.name == name).first()
    if row is None:
        row = SalesReworkReason(name=name)
        db.add(row)
        db.commit()
        db.refresh(row)
    return {"id": row.id, "name": row.name}


@router.post("/set/{set_id}/primary-review")
def primary_review(set_id: int, payload: PrimaryReviewIn, db: Session = Depends(get_db),
                   current_user: User = Depends(APPROVE)):
    """Первичная проверка материала по ТТ — единственная, что про комплект целиком.

    У неё нет получателя (`pair_id IS NULL`): она делается до раскладки по площадкам.
    Отдельное право `approve` — чтобы можно было развести того, кто грузит материал, и
    того, кто под ним подписывается.
    """
    row = db.query(LaunchPrepCreativeSet).filter(LaunchPrepCreativeSet.id == set_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Комплект не найден")
    _deal(db, row.deal_id, current_user)
    if payload.verdict not in ("ок", "на доработку"):
        raise HTTPException(status_code=400, detail="Вердикт: «ок» или «на доработку»")
    if payload.verdict == "на доработку" and not (payload.reason or "").strip():
        # Причина обязательна: «на доработку» без неё превращается в «переделайте
        # что-нибудь» и возвращается клиенту тем же составом.
        raise HTTPException(status_code=400, detail="Укажите причину доработки")
    if not db.query(LaunchPrepCreativeFile).filter(
            LaunchPrepCreativeFile.set_id == set_id).first():
        raise HTTPException(status_code=400, detail="В комплекте нет ни одного файла")

    rec = (db.query(LaunchPrepReview)
           .filter(LaunchPrepReview.set_id == set_id,
                   LaunchPrepReview.pair_id.is_(None),
                   LaunchPrepReview.kind == "первичная_тт").first())
    if rec is None:
        rec = LaunchPrepReview(set_id=set_id, kind="первичная_тт", source="аккаунт")
        db.add(rec)
    elif rec.verdict is not None:
        # Вердикт неизменяем: иначе «согласовал → подменили → в системе по-прежнему ок».
        raise HTTPException(status_code=400,
                            detail="Вердикт уже выставлен. Доработка — это новый комплект")
    rec.verdict = payload.verdict
    rec.reason = (payload.reason or "").strip() or None
    rec.decided_by = current_user.name
    rec.source = "аккаунт"
    from sqlalchemy.sql import func as sa_func
    rec.decided_at = sa_func.now()
    db.commit()
    log_action(db, current_user, "primary_creative_review", "sales_deal", row.deal_id,
               f"комплект №{row.no}: {payload.verdict}")
    return {"verdict": rec.verdict}


# ============================== маркер ==============================

# Доля согласовавших, при которой выпускается ЕРИД. Величина того же рода, что SLA стадии:
# её меняют по опыту, а не по коду, поэтому значение читается из настроек, а константа —
# запасное дно. Место в «настройках сборки» на услуге, когда их состав закроют.
ERID_THRESHOLD_KEY = "creatives_erid_threshold"
ERID_THRESHOLD_DEFAULT = 0.25


def erid_threshold(db: Session) -> float:
    row = db.execute(sa_text("SELECT value FROM company_settings WHERE key = :k"),
                     {"k": ERID_THRESHOLD_KEY}).first()
    try:
        return float(row[0]) if row and row[0] else ERID_THRESHOLD_DEFAULT
    except (TypeError, ValueError):
        return ERID_THRESHOLD_DEFAULT


def threshold_state(db: Session, set_id: int, share: float) -> dict:
    """Знаменатель — те, КОМУ КОМПЛЕКТ АДРЕСОВАН, а не те, кто согласовал.

    Отказ остаётся в знаменателе намеренно: иначе четверть считалась бы от одних
    довольных, и маркер выпускался бы раньше срока. Округление вверх, минимум один —
    четверть от трёх это один, а не ноль.

    После разворота цепочки (28.08.2026) формула НЕ изменилась, и это осознанно. Пары
    заводятся всё так же все сразу, просто теперь между парой и вопросом площадке стоит
    проверка трафика. Знаменатель от этого тот же, а числитель может расти только после
    двух «ок» — значит порог стал строже сам собой, без правки правила. Проверять здесь
    ещё и вердикт трафика было бы вторым местом, где записан один и тот же порядок.
    """
    pairs = db.query(LaunchPrepPair).filter(LaunchPrepPair.set_id == set_id).all()
    sent = len(pairs)
    agreed = len([p for p in pairs if p.agreed_at])
    need = max(1, ceil(sent * share)) if sent else 0
    return {"sent": sent, "agreed": agreed, "need": need,
            "ready": bool(sent) and agreed >= need}


def _files_with_content(db: Session, set_id: int):
    """Файлы комплекта вместе с содержимым: в ОРД материал уезжает base64.

    Ссылкой нельзя: схема требует URL, доступный БЕЗ авторизации, а превью креативов
    живёт в песочнице и наружу не открыто.
    """
    out = []
    for f in db.query(LaunchPrepCreativeFile).filter(
            LaunchPrepCreativeFile.set_id == set_id).order_by(LaunchPrepCreativeFile.id):
        full = os.path.join(UPLOADS_ROOT, f.path)
        try:
            with open(full, "rb") as fh:
                content = base64.b64encode(fh.read()).decode()
        except OSError:
            raise HTTPException(status_code=400,
                                detail=f"Файл «{f.original_name}» не найден в хранилище")
        out.append(SimpleNamespace(original_name=f.original_name,
                                   is_archive=f.is_archive, content_b64=content))
    return out


def _ord_chain(db: Session, deal: SalesDeal):
    """Идентификаторы договорной цепочки сделки в ОРД.

    Креатив нельзя создать, не назвав доходный договор, — поэтому цепочка собирается
    раньше маркера, и её отсутствие объясняется здесь, а не отказом реестра.
    """
    # Доходный договор — НАШ договор из реестра, помеченный колонками ord_*: своей
    # таблицы у него нет (зеркало завело её только изначальным, чужим договорам).
    #
    # СПРАШИВАЕМ ТУ ЖЕ ФУНКЦИЮ, ЧТО И ЭКРАН СБОРКИ (`resolve_final`), а не колонку
    # ручного выбора. Колонка — только переопределение, и она пуста у всех сделок:
    # обычный случай — договор ВЫЧИСЛЯЕТСЯ по плательщику. Читая колонку, мы получали
    # None там, где лестница показывает зелёное, и уходили в запасную ветку ниже.
    # И берём идентификаторы ТОГО контура, на который сейчас отправляем: демо и прод
    # выдают разные, и договор, зарегистрированный в обоих, зовётся там по-разному.
    env = ord_client.env()

    fr = resolve_final(db, deal)
    final_ord_id = None
    if fr.contract is not None:
        final_ord_id = registry.known_id(db, 'final_contract', fr.contract.id, env,
                                         fr.contract.ord_contract_id,
                                         fr.contract.ord_env)

    initial_ord_id = None
    if deal.ord_initial_contract_id:
        row = db.query(OrdInitialContract).filter(
            OrdInitialContract.id == deal.ord_initial_contract_id).first()
        if row:
            initial_ord_id = registry.known_id(db, 'initial_contract', row.id, env,
                                               row.ord_id, row.ord_env)
        # Запасной ветки «взять доходный из первой попавшейся связи» здесь БЫЛО, и она
        # была опасна: изначальный договор бывает привязан к нескольким доходным (22 из
        # 126, до трёх у одного), `first()` брал произвольный, и на HCLA6E это давал
        # ЧУЖОЙ договор, которого у нас в реестре нет вовсе, — при том что экран
        # показывал договор плательщика. Креатив ушёл бы в ЕРИР под чужим доходным
        # и не отозвался бы. Если доходный не определился, пусть отказ скажет об этом.
    return final_ord_id, initial_ord_id


def _target_urls(db: Session, set_id: int) -> List[str]:
    """Посадочные страницы получателей ЭТОГО комплекта: у каждой площадки своя.

    Вынесено из `issue_erid` не ради красоты. Тот же запрос стоял там строкой с
    `.with_entities(LaunchPrepTarget)` и распаковкой `for (t,) in ...` — а запрос,
    просящий ОДНУ сущность, отдаёт саму сущность, а не кортеж из неё. Выпуск маркера
    падал на `TypeError`, и не находилось это годами по одной причине: шаг стоит в самом
    конце цепочки, в тестах не вызывается (там сеть), а руками до него доходят редко.
    Отдельная функция проверяется прибором без обращения к ОРД.

    Пустые ссылки не отсеиваются здесь: их убирает сборка тела (`ord/payloads.py`),
    и второе место с тем же правилом однажды разошлось бы с первым.
    """
    return [t.advertiser_url for t in
            db.query(LaunchPrepTarget)
              .join(LaunchPrepPair, LaunchPrepPair.target_id == LaunchPrepTarget.id)
              .filter(LaunchPrepPair.set_id == set_id).all()]


def _mark_targets_erid(db: Session, set_id: int):
    """Согласовавшие получатели этого комплекта переходят в «ерид получен».

    Дальше их двигает модуль трафиков («заведён в DSP») и запуск — вручную, потому что
    ни того, ни другого система пока не знает.
    """
    for pair in db.query(LaunchPrepPair).filter(
            LaunchPrepPair.set_id == set_id, LaunchPrepPair.agreed_at.isnot(None)).all():
        t = db.query(LaunchPrepTarget).filter(
            LaunchPrepTarget.id == pair.target_id).first()
        if t and t.state == "согласован":
            t.state = "ерид получен"


def _brand_marking_out(db: Session, brand) -> Optional[dict]:
    """Маркировка бренда для экрана: код, его расшифровка и описание объекта.

    Расшифровка берётся из зеркала справочника, а не хранится рядом с кодом: код —
    единственное, что мы решаем, имя категории принадлежит классификатору и меняется
    вместе с ним. Зеркала может не быть (не заливали) — тогда показываем голый код,
    это честнее выдуманного названия.
    """
    if brand is None:
        return None
    name = None
    if brand.kktu_code:
        row = (db.query(OrdKktu.name)
                 .filter(OrdKktu.code == brand.kktu_code).first())
        name = row[0] if row else None
    return {"id": brand.id, "name": brand.name, "kktu_code": brand.kktu_code,
            "kktu_name": name, "ad_object_description": brand.ad_object_description}


@router.get("/set/{set_id}/erid-readiness")
def erid_readiness(set_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(VIEW)):
    """Сколько согласовавших нужно для маркера и чего не хватает."""
    s = db.query(LaunchPrepCreativeSet).filter(LaunchPrepCreativeSet.id == set_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Комплект не найден")
    deal = _deal(db, s.deal_id, current_user)
    st = threshold_state(db, set_id, erid_threshold(db))
    final_ord_id, initial_ord_id = _ord_chain(db, deal)
    brand = (db.query(SalesBrand).filter(SalesBrand.id == deal.brand_id).first()
             if deal.brand_id else None)
    # Блокер несёт КОД, а не только текст: экран решает по коду, какой из них можно
    # нажать и починить не уходя. Разбирать русскую фразу на фронте значило бы
    # привязать поведение кнопки к формулировке, которую однажды перепишут.
    blockers = []
    if not st["ready"]:
        blockers.append({"code": "threshold",
                         "text": f"согласовали {st['agreed']} из {st['sent']}, "
                                 f"нужно {st['need']}"})
    if not final_ord_id:
        blockers.append({"code": "chain", "text": "не собрана договорная цепочка ОРД"})
    if not (s.kktu_code or (brand.kktu_code if brand else None)):
        blockers.append({"code": "kktu", "text": "не заполнен код ККТУ у бренда"})
    return {**st, "threshold": erid_threshold(db), "blockers": blockers,
            # Бренд отдаётся всегда, а не только когда он мешает: тем же ответом
            # живёт справочная строка «что проставлено», а не только отказ.
            "brand": _brand_marking_out(db, brand),
            "erid": s.erid, "erid_source": s.erid_source, "ord_status": s.ord_status}


@router.post("/set/{set_id}/erid")
def issue_erid(set_id: int, db: Session = Depends(get_db),
               current_user: User = Depends(require_permission("ord_submit", "create"))):
    """Выпустить маркер на комплект.

    Право `ord_submit`, а не `creatives.edit`: запись в ЕРИР необратима, и за одним
    правом стоит одна необратимость — то же, что у регистрации договоров.
    """
    s = db.query(LaunchPrepCreativeSet).filter(LaunchPrepCreativeSet.id == set_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Комплект не найден")
    deal = _deal(db, s.deal_id, current_user)

    st = threshold_state(db, set_id, erid_threshold(db))
    if not st["ready"]:
        raise HTTPException(
            status_code=400,
            detail=f"Порог не взят: согласовали {st['agreed']} из {st['sent']}, "
                   f"нужно {st['need']}")

    final_ord_id, initial_ord_id = _ord_chain(db, deal)
    brand = (db.query(SalesBrand).filter(SalesBrand.id == deal.brand_id).first()
             if deal.brand_id else None)
    files = _files_with_content(db, set_id)
    urls = _target_urls(db, set_id)

    try:
        out = ord_submit.register_creative(db, s, files, deal, brand, final_ord_id,
                                           initial_ord_id, current_user,
                                           advertiser_urls=urls)
    except (ord_submit.OrdSubmitRefused, OrdPayloadError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OrdError as e:
        raise HTTPException(status_code=400, detail=e.message)

    _mark_targets_erid(db, set_id)
    db.commit()
    log_action(db, current_user, "issue_erid", "sales_deal", deal.id,
               f"комплект №{s.no}: ЕРИД {out.get('erid')}")
    emit(db, "creative_erid_issued",
         title=f"ЕРИД выпущен · {deal.code}",
         body=f"Комплект №{s.no}: {out.get('erid')}. Статус регистрации: {out.get('status')}",
         link=f"/sales/deals/{deal.code or deal.id}",
         entity_type="sales_deal", entity_id=deal.id, actor=current_user,
         ctx={"deal_id": deal.id})
    db.commit()
    return out


@router.post("/set/{set_id}/erid/refresh")
def refresh_erid(set_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(VIEW)):
    """Опросить статус: маркер выдан сразу, а регистрация в ЕРИР идёт асинхронно."""
    s = db.query(LaunchPrepCreativeSet).filter(LaunchPrepCreativeSet.id == set_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Комплект не найден")
    _deal(db, s.deal_id, current_user)
    try:
        return ord_submit.refresh_creative_status(db, s)
    except ord_submit.OrdSubmitRefused as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OrdError as e:
        raise HTTPException(status_code=400, detail=e.message)


class ForeignEridIn(BaseModel):
    erid: str


@router.put("/set/{set_id}/erid")
def set_foreign_erid(set_id: int, payload: ForeignEridIn, db: Session = Depends(get_db),
                     current_user: User = Depends(EDIT)):
    """Чужой маркер: у саморекламы ЕРИД выпускает площадка в своём ОРД.

    Он приходит извне и вводится руками. Источник помечается явно — иначе код будет
    вечно пытаться получить то, что за ним никогда не стояло, и опрашивать статус
    регистрации, которой не было.
    """
    s = db.query(LaunchPrepCreativeSet).filter(LaunchPrepCreativeSet.id == set_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Комплект не найден")
    deal = _deal(db, s.deal_id, current_user)
    if s.ord_creative_id:
        raise HTTPException(status_code=400,
                            detail="Комплект зарегистрирован в нашем ОРД — маркер уже наш")
    erid = (payload.erid or "").strip()
    if not erid:
        raise HTTPException(status_code=400, detail="Пустой маркер")
    s.erid = erid
    s.erid_source = "площадки"
    _mark_targets_erid(db, set_id)
    db.commit()
    log_action(db, current_user, "set_foreign_erid", "sales_deal", deal.id,
               f"комплект №{s.no}: чужой ЕРИД {erid}")
    return {"erid": s.erid, "erid_source": s.erid_source}


class TargetStateIn(BaseModel):
    state: str


@router.put("/target/{target_id}/state")
def move_target(target_id: int, payload: TargetStateIn, db: Session = Depends(get_db),
                current_user: User = Depends(EDIT)):
    """Двигать получателя после маркера.

    «Заведён в DSP» — работа модуля трафиков, которого ещё нет: состояние существует, но
    проскакивается, поэтому переход из «ерид получен» сразу в «в размещении» законен.
    Наружу эти три состояния всё равно сворачиваются в одно.
    """
    t = db.query(LaunchPrepTarget).filter(LaunchPrepTarget.id == target_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Получатель не найден")
    deal = _deal(db, t.deal_id, current_user)
    if payload.state not in TARGET_STATES:
        raise HTTPException(status_code=400,
                            detail=f"Состояние: {', '.join(TARGET_STATES)}")
    if t.state == "отказ площадки":
        raise HTTPException(status_code=400,
                            detail="Площадка отказалась — вернуть её в кампанию нельзя")
    order = list(TARGET_STATES)
    if order.index(payload.state) < order.index(t.state or "согласование"):
        # Назад состояние не двигается: доработка — это новый комплект, а не откат.
        raise HTTPException(status_code=400,
                            detail="Назад состояние не двигается: доработка — новый комплект")
    t.state = payload.state
    db.commit()
    log_action(db, current_user, "move_creative_target", "sales_deal", deal.id,
               f"{t.publisher_id}: {payload.state}")
    return {"state": t.state, "public": TARGET_STATE_PUBLIC.get(t.state)}


# ============================== посадочные страницы ==============================

def url_state(target) -> str:
    """Состояние ссылки — производное, а не колонка.

    Три ответа на «где ссылка»: её не спрашивали, её ждут от площадки, она есть.
    Хранимый статус разъехался бы с самими полями при первой же правке руками.

    **Единственная реализация на весь бэкенд ядра** — зовут отсюда и `traffic.py`, и
    `cabinet_gateway.py`. Вторая копия живёт в СЕРВИСЕ КАБИНЕТА (`cabinet/app/main.py`)
    и убрана быть не может: это отдельный процесс под отдельной ролью БД, импортировать
    `app.*` он не должен по построению — в этом и смысл внешнего контура. Меняя эти три
    ответа, править надо оба места; вторая правка не забудется, если менять их одним
    заходом. Значения сравниваются буквально и в JS обоих фронтов.
    """
    if target.advertiser_url:
        return "есть"
    return "запрошена" if target.url_requested_at else "нужна"


class TargetUrlIn(BaseModel):
    url: Optional[str] = None


@router.put("/target/{target_id}/url")
def set_target_url(target_id: int, payload: TargetUrlIn, db: Session = Depends(get_db),
                   current_user: User = Depends(EDIT)):
    """Посадочная страница этой площадки.

    Проверка схемы та же, что у ссылки на документ договора, и по той же причине:
    «javascript:» в поле, которое где-то отрисуется ссылкой, — это XSS, а не опечатка.
    """
    t = db.query(LaunchPrepTarget).filter(LaunchPrepTarget.id == target_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Получатель не найден")
    deal = _deal(db, t.deal_id, current_user)
    url = (payload.url or "").strip()
    if url and not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400,
                            detail="Ссылка должна начинаться с http:// или https://")
    t.advertiser_url = url or None
    db.commit()
    log_action(db, current_user, "set_target_url", "sales_deal", deal.id,
               f"площадка {t.publisher_id}: {url or 'ссылка снята'}")
    return {"advertiser_url": t.advertiser_url, "url_state": url_state(t)}


class UrlRequestIn(BaseModel):
    text: str


@router.post("/target/{target_id}/url-request")
def request_target_url(target_id: int, payload: UrlRequestIn, db: Session = Depends(get_db),
                       current_user: User = Depends(TARGETING_EDIT)):
    """Запросить ссылку у площадки: записать текст запроса и отметить время.

    Право — «креативы ИЛИ очередь трафика», как у ссылки нацеливания рядом: дыру в
    посадочных первым видит трафик, и заставлять его писать аккаунту, чтобы тот нажал
    кнопку, значит терять день на пересказ.

    **Система ничего не отправляет.** Внешнего канала до площадки пока нет: получатель
    уведомлений — `User`, а площадка им не является, и отдельный тип получателя вместе
    со своим ботом появляется только на этапе кабинета. Поэтому кнопка фиксирует ФАКТ
    запроса и отдаёт текст, который человек отправляет почтой или в чат. Делать вид,
    что письмо ушло, — хуже, чем не отправлять его вовсе.
    """
    t = db.query(LaunchPrepTarget).filter(LaunchPrepTarget.id == target_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Получатель не найден")
    deal = _deal(db, t.deal_id, current_user)
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Пустой текст запроса")
    if t.advertiser_url:
        raise HTTPException(status_code=400, detail="Ссылка уже есть — запрашивать нечего")

    from sqlalchemy.sql import func as sa_func
    t.url_request_text = text
    t.url_requested_at = sa_func.now()
    db.commit()
    log_action(db, current_user, "request_target_url", "sales_deal", deal.id,
               f"площадка {t.publisher_id}: запрошена ссылка")
    return {"url_state": url_state(t), "text": text}


@router.get("/refusal-reasons")
def refusal_reasons(db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    rows = (db.query(SalesRefusalReason)
            .filter(SalesRefusalReason.is_active.is_(True))
            .order_by(SalesRefusalReason.sort_order, SalesRefusalReason.id).all())
    return {"items": [{"id": r.id, "name": r.text} for r in rows]}


@router.post("/refusal-reasons")
def add_refusal_reason(payload: ReasonIn, db: Session = Depends(get_db),
                       current_user: User = Depends(EDIT)):
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Пустая причина")
    row = db.query(SalesRefusalReason).filter(SalesRefusalReason.text == name).first()
    if row is None:
        last = (db.query(SalesRefusalReason.sort_order)
                .order_by(SalesRefusalReason.sort_order.desc()).first())
        row = SalesRefusalReason(text=name, sort_order=((last[0] if last else 0) + 10))
        db.add(row)
        db.commit()
        db.refresh(row)
    return {"id": row.id, "name": row.text}


@router.get("/url-request-phrases")
def url_request_phrases(db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    rows = (db.query(SalesUrlRequestPhrase)
            .filter(SalesUrlRequestPhrase.is_active.is_(True))
            .order_by(SalesUrlRequestPhrase.sort_order, SalesUrlRequestPhrase.id).all())
    return {"items": [{"id": r.id, "text": r.text} for r in rows]}


@router.post("/url-request-phrases")
def add_url_request_phrase(payload: UrlRequestIn, db: Session = Depends(get_db),
                           current_user: User = Depends(EDIT)):
    """Накопитель: набранная фраза уходит в общий список и предлагается всем."""
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Пустая фраза")
    row = db.query(SalesUrlRequestPhrase).filter(
        SalesUrlRequestPhrase.text == text).first()
    if row is None:
        last = (db.query(SalesUrlRequestPhrase.sort_order)
                .order_by(SalesUrlRequestPhrase.sort_order.desc()).first())
        row = SalesUrlRequestPhrase(text=text, sort_order=((last[0] if last else 0) + 10))
        db.add(row)
        db.commit()
        db.refresh(row)
    return {"id": row.id, "text": row.text}
