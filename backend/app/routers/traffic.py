"""Контур «Траффики»: очередь проверки материала перед отправкой площадкам.

Зерно очереди — ПАРА «креатив × площадка», а не сделка. Один баннер на восьми площадках
это восемь единиц работы, и семь из них могут быть в порядке; сводка по сделке такую
картину не показывает вовсе.

Проверка трафика встаёт ПЕРЕД площадкой (владелец 28.08.2026), значит это проверка
МАТЕРИАЛА, а не размещения. Отсюда три правила, и каждое живёт в коде, а не на экране:

  · строка проверки площадки заводится ЗДЕСЬ, вердиктом «всё ок». До него площадку не
    спрашивали, и пустая строка ожидания у неё соврала бы: «строка = спросили»;
  · вердикт `отказ` этой ручкой не принимается. Закрыть площадку — не полномочие трафика
    (владелец). Спрятанной кнопки мало: она возвращается первым же рефакторингом;
  · порог ЕРИД не трогается вовсе. Раз площадка отвечает только после трафика, её «ок»
    уже означает оба, и второе место, где записан этот порядок, было бы лишним.

Файлы пары — скриншоты размещения — раздаются только отсюда и только авторизованно: в
песочницу они не попадают и в контракт кабинета `pub.*_v1` не выводятся.

Состав согласован владельцем 28.08.2026, разбор —
docs/SCHEMA_конвейер_трафиков_на_согласование.md.
"""
import io
import os
import zipfile
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.sql import func as sa_func

from app.files_safe import existing_upload_path, inside_uploads, remove_upload
from app.audit import log_action
from app.database import get_db
from app.launch_prep import sandbox
from app.routers.launch_prep import url_state
from app.launch_prep.models import (LaunchPrepCreativeFile, LaunchPrepCreativeSet,
                                    LaunchPrepPair, LaunchPrepPairFile, LaunchPrepReview,
                                    LaunchPrepTarget)
from app.models import Role, User
from app.notify import emit
from app.permissions import require_any_permission, require_permission
from app.sales.deal_label import deal_label
from app.sales.models import (SalesAdvertiser, SalesBrand, SalesDeal, SalesPublisher,
                              SalesRep)
from app.traffic import files as tfiles
from app.traffic import urgency

router = APIRouter()

UPLOADS_ROOT = "/app/uploads"
SHOTS_DIR = "shots"

VIEW = require_permission("traffic_queue", "view")
EDIT = require_permission("traffic_queue", "edit")
APPROVE = require_permission("traffic_queue", "approve")
# Скриншоты смотрит и скачивает ещё аккаунт: доказательство собирается для него, и
# ходить за ним в чужой раздел ему незачем. Отдельного права под это не заводим —
# у файла нет своей судьбы, он приложение к паре.
FILES_VIEW = require_any_permission(
    (("traffic_queue", "view"), ("creatives", "view")))


# ============================== область видимости ==============================

def _my_rep_ids(db: Session, user: User) -> List[int]:
    return [r.id for r in db.query(SalesRep.id).filter(SalesRep.user_id == user.id).all()]


def _is_master(user: User) -> bool:
    return user.role.key == "admin" or bool(getattr(user.role, "is_master", False))


def traffic_reps(db: Session) -> List[dict]:
    """Кого можно выбрать в переключателе: трафики с живой учёткой.

    Рабочая группа берётся у РОЛИ (`Role.staff_group == 'traffic'`), как и в остальных
    списках сотрудников: у `SalesRep` своей группы нет, он общий справочник ответственных.
    """
    rows = (db.query(SalesRep.id, SalesRep.name)
            .join(User, User.id == SalesRep.user_id)
            .join(Role, Role.id == User.role_id)
            .filter(Role.staff_group == "traffic", User.is_active == 1,
                    SalesRep.is_active.is_(True))
            .order_by(SalesRep.name).all())
    return [{"id": r_id, "name": name} for r_id, name in rows]


def _apply_scope(q, db: Session, user: User, rep_id=None, all_reps: bool = False):
    """Очередь ОБЩАЯ: её целиком видит каждый, у кого есть право (владелец 03.09.2026).

    Правило менялось дважды, и оба раза по тому, как работают люди, а не по коду.
    31.08.2026 очередь распределялась: рядовой трафик видел только назначенное ему,
    «ничьё» не показывалось никому. Прогон с сотрудниками показал, что материал
    разбирают не по назначению, а по наличию времени, — распределение только мешало,
    а необходимость назначить трафика ДО отправки упиралась в стену там, где её никто
    не ждал (см. `launch_prep.send_set`).

    `traffic_manager_id` остаётся ОТМЕТКОЙ ответственного за кампанию — её ставят и
    меняют вручную до старта, — но области видимости больше не задаёт. `rep_id`
    остаётся фильтром экрана и работает у всех: «покажи, что за таким-то». `all_reps`
    сохранён в подписи как часть контракта ручки (её зовут напрямую приборы и фронт) и
    теперь ничего не меняет: без фильтра очередь и так полная.
    """
    if rep_id:
        return q.filter(SalesDeal.traffic_manager_id == int(rep_id))
    return q


def _pair_in_scope(db: Session, pair_id: int, user: User):
    """Пара + её окружение. 404, если пары нет вовсе.

    Область ДЕЙСТВИЙ равна области ВИДИМОСТИ, а очередь общая (03.09.2026) — значит
    нажать можно по любой строке, которую видно. Функция остаётся: она собирает
    окружение пары одним запросом, и через неё же пойдёт ограничение, если оно
    когда-нибудь вернётся.
    """
    row = (db.query(LaunchPrepPair, LaunchPrepCreativeSet, LaunchPrepTarget,
                    SalesPublisher, SalesDeal)
           .join(LaunchPrepCreativeSet, LaunchPrepCreativeSet.id == LaunchPrepPair.set_id)
           .join(LaunchPrepTarget, LaunchPrepTarget.id == LaunchPrepPair.target_id)
           .join(SalesDeal, SalesDeal.id == LaunchPrepCreativeSet.deal_id)
           .outerjoin(SalesPublisher, SalesPublisher.id == LaunchPrepTarget.publisher_id)
           .filter(LaunchPrepPair.id == pair_id))
    row = _apply_scope(row, db, user, all_reps=_is_master(user)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Пара не найдена")
    return row


# ============================== очередь ==============================

def _facts(traffic: LaunchPrepReview, target: LaunchPrepTarget,
           deal: SalesDeal) -> urgency.PairFacts:
    """Сборка фактов — здесь, расчёт — в чистой функции. Она не ходит в базу нарочно."""
    start = target.period_from or deal.period_from
    return urgency.PairFacts(
        traffic_verdict=traffic.verdict,
        asked_at=traffic.asked_at.date() if traffic.asked_at else None,
        period_from=start,
        is_dropped=(target.state == "отказ площадки"),
    )


@router.get("/queue")
def queue(status: str = "waiting", db: Session = Depends(get_db),
          current_user: User = Depends(VIEW),
          # Новые параметры ПОСЛЕ зависимостей: порядок аргументов у этой ручки —
          # публичный контракт для приборов, которые зовут её напрямую
          # (tests/test_traffic_queue.py: `traffic.queue('all', db, user)`). FastAPI
          # разбирает query-параметры по именам, ему порядок безразличен.
          rep_id: Optional[int] = None, all_reps: bool = False):
    """Очередь проверки. `status`: waiting (по умолчанию) | done | all.

    `rep_id` — фильтр «чья кампания», доступен всем: очередь общая (03.09.2026), и
    переключатель здесь сужает список, а не выдаёт доступ. `all_reps` остался в
    подписи ради контракта ручки и ничего не меняет.

    Один запрос на весь экран — тем же приёмом, что сборка креативов: несколько запросов
    на один список дают мигание и рассинхрон, когда часть уже обновилась, а часть нет.
    """
    q = (db.query(LaunchPrepReview, LaunchPrepPair, LaunchPrepCreativeSet,
                  LaunchPrepTarget, SalesPublisher, SalesDeal)
         .join(LaunchPrepPair, LaunchPrepPair.id == LaunchPrepReview.pair_id)
         .join(LaunchPrepCreativeSet, LaunchPrepCreativeSet.id == LaunchPrepPair.set_id)
         .join(LaunchPrepTarget, LaunchPrepTarget.id == LaunchPrepPair.target_id)
         .join(SalesDeal, SalesDeal.id == LaunchPrepCreativeSet.deal_id)
         .outerjoin(SalesPublisher, SalesPublisher.id == LaunchPrepTarget.publisher_id)
         .filter(LaunchPrepReview.kind == "трафики"))
    if status == "waiting":
        q = q.filter(LaunchPrepReview.verdict.is_(None))
    elif status == "done":
        q = q.filter(LaunchPrepReview.verdict.isnot(None))
    rows = (_apply_scope(q, db, current_user, rep_id, all_reps)
            .order_by(LaunchPrepReview.id).all())

    set_ids = {s.id for _r, _p, s, _t, _pub, _d in rows}
    files = []
    if set_ids:
        files = (db.query(LaunchPrepCreativeFile)
                 .filter(LaunchPrepCreativeFile.set_id.in_(set_ids))
                 .order_by(LaunchPrepCreativeFile.id).all())
    # Чья это кампания — тремя именами, а не тремя идентификаторами. Трафик не ведёт
    # сделки и по id не опознаёт ничего; ему нужно понять, чей материал он смотрит, и к
    # кому идти с вопросом. Три отдельных выборки по множеству id, а не join к основному
    # запросу: тот и без них соединяет пять таблиц, а строк здесь десятки.
    deals = {d.id: d for _r, _p, _s, _t, _pub, d in rows}
    adv = dict(db.query(SalesAdvertiser.id, SalesAdvertiser.short_name).filter(
        SalesAdvertiser.id.in_({d.advertiser_id for d in deals.values() if d.advertiser_id}
                               or {0})).all())
    adv_full = dict(db.query(SalesAdvertiser.id, SalesAdvertiser.name).filter(
        SalesAdvertiser.id.in_({d.advertiser_id for d in deals.values() if d.advertiser_id}
                               or {0})).all())
    brands = dict(db.query(SalesBrand.id, SalesBrand.name).filter(
        SalesBrand.id.in_({d.brand_id for d in deals.values() if d.brand_id} or {0})).all())
    reps = dict(db.query(SalesRep.id, SalesRep.name).filter(
        SalesRep.id.in_({d.account_manager_id for d in deals.values()
                         if d.account_manager_id} or {0})).all())

    pair_ids = [p.id for _r, p, _s, _t, _pub, _d in rows]
    shots = {}
    if pair_ids:
        # Только СВОИ файлы: площадка кладёт в ту же таблицу картинки к доработке, и
        # без фильтра «скрины · 3» появлялось бы у пары, где размещения ещё не было.
        shots = dict(db.query(LaunchPrepPairFile.pair_id, sa_func.count(LaunchPrepPairFile.id))
                     .filter(LaunchPrepPairFile.pair_id.in_(pair_ids),
                             LaunchPrepPairFile.kind == 'размещение')
                     .group_by(LaunchPrepPairFile.pair_id).all())

    today = date.today()
    out = []
    for review, pair, s, target, pub, deal in rows:
        mine = [f for f in files if f.set_id == s.id]
        v = urgency.evaluate(_facts(review, target, deal), today)
        out.append({
            "pair_id": pair.id,
            # Полного кода пары на этой стадии НЕ существует: `-01` выдаётся по факту
            # схождения, а трафик смотрит до него. Показываем префикс, и это честно.
            "pair_prefix": f"{deal.code}-{pub.code}" if deal.code and pub and pub.code else None,
            "deal": {"id": deal.id, "code": deal.code, "title": deal.title,
                     # Короткое имя, а не каноничное: в реестрах основная колонка —
                     # `short_name`, и экран, показавший вместо него полное юридическое
                     # название, уже читался как «справочники не синхронизировались».
                     "advertiser": (adv.get(deal.advertiser_id)
                                    or adv_full.get(deal.advertiser_id)),
                     "brand": brands.get(deal.brand_id),
                     "account": reps.get(deal.account_manager_id)},
            "set": {"id": s.id, "no": s.no, "title": s.title, "form": s.form,
                    "test_targeting_url": s.test_targeting_url},
            "publisher": {"id": target.publisher_id,
                          "name": pub.name if pub else None,
                          # Домен нормализован в справочнике — по нему и открываем сайт.
                          # Собирать адрес из `name` нельзя: имя площадки не обязано быть
                          # доменом, а домен обязан.
                          "domain": pub.domain if pub else None,
                          "code": pub.code if pub else None,
                          "tech_requirements": pub.tech_requirements if pub else None},
            "surface_kind": target.surface_kind,
            # Посадочная живёт на ПОЛУЧАТЕЛЕ, а не на паре: страница одна на всю кампанию
            # у этого сайта. Отдаём `target_id` и состояние запроса, чтобы трафик мог не
            # только увидеть дыру, но и закрыть её — той же ручкой, что аккаунт.
            "target_id": target.id,
            "advertiser_url": target.advertiser_url,
            # Состояние ссылки — ОДНОЙ функцией на весь бэкенд. Здесь стояла своя копия
            # тех же трёх ответов; копия дешевле импорта ровно до первого изменения
            # правила, после которого один экран начинает врать.
            "url_state": url_state(target),
            "url_request_text": target.url_request_text,
            "period_from": target.period_from or deal.period_from,
            "period_to": target.period_to or deal.period_to,
            # Размер баннера — из самого баннера (`<meta name="ad.size">` при распаковке),
            # а не из имени файла: имя врёт, метатег пишет тот, кто баннер собирал.
            "sizes": [f.ratio for f in mine if f.ratio],
            "files": [{"id": f.id, "name": f.original_name, "ratio": f.ratio,
                       "is_archive": f.is_archive,
                       "sandbox_url": sandbox.public_url(f.sandbox_token, f.entry_path)}
                      for f in mine],
            "shots_count": shots.get(pair.id, 0),
            "asked_at": review.asked_at,
            "verdict": review.verdict,
            "reason": review.reason,
            "decided_by": review.decided_by,
            "decided_at": review.decided_at,
            "urgency": v.urgency, "urgency_reason": v.reason, "due": v.due,
        })
    out.sort(key=lambda r: (urgency.URGENCY_ORDER.get(r["urgency"], 9),
                            r["due"] or date.max, r["pair_id"]))
    my = _my_rep_ids(db, current_user)
    return {"rows": out, "status": status, "is_master": _is_master(current_user),
            # Кого показали на самом деле: None — очередь целиком (умолчание).
            "rep_id": int(rep_id) if rep_id else None,
            "my_rep_id": my[0] if my else None,
            # Фильтр по ответственному видят все — очередь общая, и прятать сужение
            # списка не от чего.
            "can_view_others": True,
            "reps": traffic_reps(db)}


@router.get("/queue/count")
def queue_count(db: Session = Depends(get_db), current_user: User = Depends(VIEW)):
    """Сколько креативов ждут проверки — только число, для счётчика в меню.

    Отдельной ручкой, а не полем в `/queue`: бейдж в шапке считается на КАЖДОЙ странице,
    а `/queue` тянет пять таблиц, файлы и три выборки имён. Здесь — один COUNT по всей
    очереди: она общая, и число у всех одинаковое.
    """
    q = (db.query(LaunchPrepReview.id)
         .join(LaunchPrepPair, LaunchPrepPair.id == LaunchPrepReview.pair_id)
         .join(LaunchPrepCreativeSet, LaunchPrepCreativeSet.id == LaunchPrepPair.set_id)
         .join(LaunchPrepTarget, LaunchPrepTarget.id == LaunchPrepPair.target_id)
         .join(SalesDeal, SalesDeal.id == LaunchPrepCreativeSet.deal_id)
         .filter(LaunchPrepReview.kind == "трафики",
                 LaunchPrepReview.verdict.is_(None)))
    n = _apply_scope(q, db, current_user).count()
    return {"waiting": n}


# ============================== вердикт ==============================

class VerdictIn(BaseModel):
    verdict: str                    # ок | на переделку
    reason: Optional[str] = None


TRAFFIC_VERDICTS = ("ок", "на переделку")


def _apply_verdict(db: Session, pair, s, target, pub, deal,
                   verdict: str, reason: Optional[str], user: User):
    """Одна пара. Возвращает текст для журнала либо кидает 400.

    Вынесено из ручки, потому что массовая отметка обязана вести себя ТАК ЖЕ: один баннер
    на восемь сайтов — восемь одинаковых «ок», и разойтись эти два пути не должны.
    """
    rec = (db.query(LaunchPrepReview)
           .filter(LaunchPrepReview.pair_id == pair.id,
                   LaunchPrepReview.kind == "трафики").first())
    if rec is None:
        raise HTTPException(status_code=400, detail="Эта пара трафику не отправлялась")
    if rec.verdict is not None:
        raise HTTPException(status_code=400,
                            detail="Вердикт уже выставлен. Переделка — это новый комплект")

    rec.verdict = verdict
    rec.reason = (reason or "").strip() or None
    rec.decided_by = user.name
    rec.decided_at = sa_func.now()

    if verdict == "ок":
        # Ровно здесь материал уходит площадке: заводим ЕЁ строку ожидания и ставим паре
        # `sent_at`. До этой минуты пустая строка у площадки означала бы «спросили», хотя
        # никто не спрашивал, — и знаменатель молчания считал бы несуществующее ожидание.
        exists = (db.query(LaunchPrepReview)
                  .filter(LaunchPrepReview.pair_id == pair.id,
                          LaunchPrepReview.kind == "площадка").first())
        if exists is None:
            db.add(LaunchPrepReview(set_id=s.id, pair_id=pair.id, kind="площадка",
                                    source="аккаунт"))
        pair.sent_at = sa_func.now()
        _tell_publisher(db, pair, s, target, pub, deal)
    return f"{deal.code}-{pub.code if pub else '?'} комплект №{s.no}: {verdict}"


def _tell_publisher(db, pair, s, target, pub, deal) -> None:
    """Сказать площадке, что материал ждёт её решения.

    Ровно та же дыра, что закрывал `traffic_new_work` внутри: до 14.09.2026 площадка
    узнавала о работе, только зайдя в кабинет, — а заходит она тогда, когда вспомнит.
    Первый вид рассылки наружу, у которого появился отправитель.

    Письмо НЕ ОТМЕНЯЕТ вердикт: прослойка возвращает причину, а не бросает исключение.
    Материал уже у площадки — в кабинете он виден независимо от почты.
    """
    # Импорты локальные: `launch_prep` импортирует этот модуль, и связь на уровне
    # файла замкнула бы круг.
    import logging

    from app.notify.outward import notify_publisher
    from app.routers.launch_prep import _deal_brand_name, deal_period_text

    log = logging.getLogger("finance.traffic")
    if pub is None:
        return
    # Имя бренда берём ТОЙ ЖЕ функцией, что подставляет его в письмо-запрос посадочной:
    # два способа назвать бренд разошлись бы, и площадка получила бы разные имена в
    # двух письмах об одном размещении.
    brand = _deal_brand_name(db, deal)
    period = deal_period_text(deal)
    # НАШЕГО кода сделки здесь нет: площадка знает бренд, услугу и период.
    context = " · ".join(x for x in ((pub.domain or pub.name), brand, period) if x)
    try:
        notify_publisher(
            db, "новый креатив", pub.id,
            title="Новый креатив на согласование",
            body="Материал прошёл нашу проверку и ждёт вашего решения. "
                 "Посмотрите дисклеймер, вес архива и соответствие техрегламенту.",
            facts=[("комплект", f"№{s.no}"), ("услуга", deal.product or "—")],
            context=context, link="/", entity_type="launch_prep_pair", entity_id=pair.id)
    except Exception as e:                                   # noqa: BLE001
        # Ошибка рассылки не должна ронять вердикт: он уже записан, и откат оставил бы
        # человека с ошибкой при выполненном действии.
        log.warning("Площадке %s не ушло «новый креатив»: %s", pub.id, e)


@router.post("/pair/{pair_id}/verdict")
def pair_verdict(pair_id: int, payload: VerdictIn, db: Session = Depends(get_db),
                 current_user: User = Depends(APPROVE)):
    """Вердикт трафика по паре. Исходов ДВА, и третий отклоняется сервером.

    «Отказ» — закрытие площадки для кампании, и это не полномочие трафика (владелец).
    Проверка стоит здесь, а не в интерфейсе: спрятанная кнопка возвращается первым же
    рефакторингом, а отказ, записанный трафиком, вывел бы площадку из кампании молча.
    """
    if payload.verdict not in TRAFFIC_VERDICTS:
        detail = ("Отказ площадки трафик не ставит — это решение площадки"
                  if payload.verdict == "отказ"
                  else "Вердикт: «ок» или «на переделку»")
        raise HTTPException(status_code=400, detail=detail)
    if payload.verdict == "на переделку" and not (payload.reason or "").strip():
        raise HTTPException(status_code=400, detail="Укажите, что переделать")

    pair, s, target, pub, deal = _pair_in_scope(db, pair_id, current_user)
    details = _apply_verdict(db, pair, s, target, pub, deal,
                             payload.verdict, payload.reason, current_user)
    db.commit()
    log_action(db, current_user, "traffic_pair_verdict", "sales_deal", deal.id, details)
    if payload.verdict == "на переделку":
        emit(db, "traffic_rework",
             title=f"Трафик вернул креатив №{s.no} · {deal_label(deal)}",
             body=(payload.reason or "").strip() or "Без комментария",
             link=f"/sales/deals/{deal.code or deal.id}",
             entity_type="sales_deal", entity_id=deal.id, actor=current_user,
             ctx={"deal": deal})
    db.commit()
    return {"verdict": payload.verdict}


class BulkVerdictIn(BaseModel):
    pair_ids: List[int]
    verdict: str
    reason: Optional[str] = None


@router.post("/pairs/verdict")
def bulk_verdict(payload: BulkVerdictIn, db: Session = Depends(get_db),
                 current_user: User = Depends(APPROVE)):
    """Массовая отметка. Один баннер на восемь сайтов — восемь одинаковых «ок».

    Уже отвеченные пары ПРОПУСКАЮТСЯ, а не роняют весь запрос: в списке из восьми одна
    может быть закрыта соседом минуту назад, и терять из-за неё остальные семь незачем.
    Сколько пропущено — в ответе, чтобы это не выглядело как «сработало на всех».
    """
    if payload.verdict not in TRAFFIC_VERDICTS:
        raise HTTPException(status_code=400, detail="Вердикт: «ок» или «на переделку»")
    if payload.verdict == "на переделку" and not (payload.reason or "").strip():
        raise HTTPException(status_code=400, detail="Укажите, что переделать")
    if not payload.pair_ids:
        raise HTTPException(status_code=400, detail="Не выбрано ни одной пары")

    done, skipped, deals = 0, 0, {}
    for pid in payload.pair_ids:
        pair, s, target, pub, deal = _pair_in_scope(db, pid, current_user)
        try:
            _apply_verdict(db, pair, s, target, pub, deal,
                           payload.verdict, payload.reason, current_user)
        except HTTPException:
            skipped += 1
            continue
        done += 1
        deals.setdefault(deal.id, (deal, s))
    db.commit()
    for deal_id, (deal, s) in deals.items():
        log_action(db, current_user, "traffic_pair_verdict", "sales_deal", deal_id,
                   f"комплект №{s.no}: {payload.verdict} — пар {done}")
        if payload.verdict == "на переделку":
            emit(db, "traffic_rework",
                 title=f"Трафик вернул креатив №{s.no} · {deal_label(deal)}",
                 body=(payload.reason or "").strip() or "Без комментария",
                 link=f"/sales/deals/{deal.code or deal.id}",
                 entity_type="sales_deal", entity_id=deal_id, actor=current_user,
                 ctx={"deal": deal})
    db.commit()
    return {"done": done, "skipped": skipped}


# ============================== архив креатива ==============================

@router.get("/pair/{pair_id}/creative-archive")
def creative_archive(pair_id: int, db: Session = Depends(get_db),
                     current_user: User = Depends(VIEW)):
    """Материал комплекта — чтобы посмотреть его вне предпросмотра.

    **Один файл отдаётся КАК ЕСТЬ, только под нашим именем.** HTML5-баннер и так приходит
    архивом; заворачивать его во второй zip значило заставлять человека распаковывать
    дважды, чтобы добраться до того же самого файла. Переименование решает ровно ту
    задачу, ради которой архив собирался, — узнаваемое имя в папке загрузок.

    Собираем zip только когда файлов НЕСКОЛЬКО: тогда контейнер несёт смысл, он держит
    их вместе. Расширение у одиночного файла своё — подменённое на `.zip` оно сломало бы
    открытие двойным щелчком.

    Отдаём ИСХОДНИК. Вживление счётчика перед отправкой в DSP — админская часть модуля
    трафика и отдельная кнопка с другой подписью (раздел 8 согласования): в предпросмотре
    и на проверке смотрят то, что согласовали, а не то, что уедет в сеть.
    """
    pair, s, target, pub, deal = _pair_in_scope(db, pair_id, current_user)
    rows = (db.query(LaunchPrepCreativeFile)
            .filter(LaunchPrepCreativeFile.set_id == s.id)
            .order_by(LaunchPrepCreativeFile.id).all())
    if not rows:
        raise HTTPException(status_code=404, detail="В комплекте нет файлов")

    if len(rows) == 1:
        f = rows[0]
        # Граница хранилища — общей проверкой (`app/files_safe`).
        full = existing_upload_path(f.path)
        ext = os.path.splitext(f.original_name or f.path)[1].lower() or ".bin"
        return FileResponse(full, media_type="application/octet-stream",
                            filename=tfiles.creative_download_name(deal.code, s.no, ext))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in rows:
            # Та же граница хранилища, что и у ветки «один файл» десятью строками выше.
            # Здесь тихий режим: одна испорченная строка не должна лишать человека
            # остальных файлов комплекта — пропускаем её так же, как отсутствующую.
            full = inside_uploads(f.path)
            if not full or not os.path.exists(full):
                continue
            z.write(full, arcname=f.original_name or os.path.basename(f.path))
    name = tfiles.creative_download_name(deal.code, s.no, ".zip")
    return Response(content=buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ============================== скриншоты ==============================

def _shot_out(f: LaunchPrepPairFile) -> dict:
    return {"id": f.id, "name": os.path.basename(f.path), "original_name": f.original_name,
            "size_bytes": f.size_bytes, "content_type": f.content_type,
            "uploaded_at": f.uploaded_at, "uploaded_by": f.uploaded_by}


@router.get("/pair/{pair_id}/files")
def list_files(pair_id: int, db: Session = Depends(get_db),
               current_user: User = Depends(FILES_VIEW)):
    # Несуществующая пара — это 404, а не пустой список: «файлов нет» и «нет такой пары»
    # разные ответы, и второй означает опечатку в ссылке или удалённую сущность.
    if not db.query(LaunchPrepPair.id).filter(LaunchPrepPair.id == pair_id).first():
        raise HTTPException(status_code=404, detail="Пара не найдена")
    rows = (db.query(LaunchPrepPairFile)
            .filter(LaunchPrepPairFile.pair_id == pair_id,
                    LaunchPrepPairFile.kind == 'размещение')
            .order_by(LaunchPrepPairFile.id).all())
    return {"files": [_shot_out(f) for f in rows]}


@router.post("/pair/{pair_id}/files")
async def upload_shot(pair_id: int, file: UploadFile = File(...),
                      db: Session = Depends(get_db), current_user: User = Depends(EDIT)):
    """Приложить скриншот размещения. Имя на диске собираем МЫ, по цепочке.

    Скриншоты — зона ответственности трафика, машину съёмки мы не строим, и полагаться
    на то, как назвал файл его инструмент, незачем. Собранное имя даёт три вещи разом:
    говорит, где стояло; не ломает распаковщики Windows кириллицей (архив уходит
    клиенту); сортируется по имени в порядке загрузки, то есть по маршруту съёмки.
    """
    pair, s, target, pub, deal = _pair_in_scope(db, pair_id, current_user)

    count = (db.query(LaunchPrepPairFile)
             .filter(LaunchPrepPairFile.pair_id == pair_id,
                     LaunchPrepPairFile.kind == 'размещение').count())
    if count >= tfiles.MAX_PAIR_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"К паре уже приложено {tfiles.MAX_PAIR_FILES} файлов — это предел")

    original = file.filename or "shot"
    ext = tfiles.split_ext(original)
    if ext not in tfiles.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Разрешены: {', '.join(sorted(tfiles.ALLOWED_EXTENSIONS))}")
    content = await file.read()
    if len(content) > tfiles.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Файл больше {tfiles.MAX_UPLOAD_BYTES // 1024 // 1024} МБ")

    content, ext, ctype = tfiles.convert(content, ext)
    stored = tfiles.traffic_file_name(deal.code, pub.code if pub else None,
                                      s.no, count + 1, ext)
    os.makedirs(os.path.join(UPLOADS_ROOT, SHOTS_DIR), exist_ok=True)
    # Пара в имени каталога не нужна — она уже в имени файла; а вот столкнуться двум
    # одинаковым именам из разных пар нельзя, поэтому префикс пары остаётся в пути.
    rel = f"{SHOTS_DIR}/p{pair_id}_{stored}"
    with open(os.path.join(UPLOADS_ROOT, rel), "wb") as fh:
        fh.write(content)

    rec = LaunchPrepPairFile(pair_id=pair_id, path=rel, original_name=original,
                             content_type=ctype, size_bytes=len(content),
                             uploaded_by=current_user.name)
    db.add(rec)
    db.commit()
    log_action(db, current_user, "traffic_pair_file", "sales_deal", deal.id,
               f"скриншот {stored}")
    return _shot_out(rec)


@router.get("/file/{file_id}")
def get_shot(file_id: int, db: Session = Depends(get_db),
             current_user: User = Depends(FILES_VIEW)):
    rec = db.query(LaunchPrepPairFile).filter(LaunchPrepPairFile.id == file_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Файл не найден")
    # Путь из базы — через общую проверку границы хранилища (`app/files_safe`).
    # До 11.09.2026 она была ровно в одном месте из десяти.
    full = existing_upload_path(rec.path)
    return FileResponse(full, media_type=rec.content_type or "application/octet-stream")


@router.delete("/file/{file_id}")
def drop_shot(file_id: int, db: Session = Depends(get_db),
              current_user: User = Depends(EDIT)):
    rec = db.query(LaunchPrepPairFile).filter(LaunchPrepPairFile.id == file_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Файл не найден")
    # Что удалили — запоминаем ДО удаления: после `db.delete` объект уже не читается,
    # а в журнале нужно имя файла, а не голый id.
    rel, what, pair_id = rec.path, rec.filename or rec.path, rec.pair_id
    db.delete(rec)
    db.commit()
    # Уборка — через общую проверку границы: строки уже нет, и отказать некому, поэтому
    # негодный путь просто не удаляется (и попадает в лог). Отсутствующий файл — сирота,
    # а не ошибка запроса.
    remove_upload(rel)
    # Удаление разрушительно и необратимо, а до 05.09.2026 не попадало в журнал вовсе:
    # скриншот размещения исчезал, и восстановить, кто его снял, было неоткуда.
    log_action(db, current_user, "delete_pair_file", "launch_prep_pair", pair_id,
               f"удалён файл «{what}»")
    return {"deleted": file_id}


@router.get("/pair/{pair_id}/files/archive")
def files_archive(pair_id: int, db: Session = Depends(get_db),
                  current_user: User = Depends(FILES_VIEW)):
    """Скриншоты пары одним архивом — тот срез, в котором проверяли.

    Группировки «по сайту» у нас нет по построению: получатели живут внутри креатива,
    и вешать такую кнопку некуда. Имя архива собирается из префикса пары и номера
    креатива, чтобы в загрузках не появлялось «архив (3).zip».
    """
    pair, s, target, pub, deal = _pair_in_scope(db, pair_id, current_user)
    rows = (db.query(LaunchPrepPairFile)
            .filter(LaunchPrepPairFile.pair_id == pair_id)
            .order_by(LaunchPrepPairFile.id).all())
    if not rows:
        raise HTTPException(status_code=404, detail="Скриншотов нет")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in rows:
            full = inside_uploads(f.path)
            if full and os.path.exists(full):
                z.write(full, arcname=os.path.basename(f.path).split("_", 1)[-1])
    prefix = f"{deal.code or deal.id}-{pub.code if pub else 'site'}"
    name = f"{prefix}-cr{s.no}-shots.zip"
    return Response(content=buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
