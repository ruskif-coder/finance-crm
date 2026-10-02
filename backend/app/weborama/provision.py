# -*- coding: utf-8 -*-
"""Заведение структуры Weborama под РК: проект → кампания → вставки → пиксели.

Единственное место, где в WCM что-то СОЗДАЁТСЯ по нашей воле. Демо-стенд остаётся
инструментом разбора, а конвейер ходит сюда.

ТРИ ПРАВИЛА, КАЖДОЕ ОПЛАЧЕНО.

1. **Реестр перед вызовом.** Уже заведённое не заводится второй раз. Уникальный индекс
   реестра ловит дубль только ПОСЛЕ внешнего вызова, поэтому одновременность держит
   замок на сделку (`app/ext_lock.py`): два нажатия иначе создадут две вставки, а
   удалить их у Weborama нечем.
2. **Журнал ДО вызова, с коммитом.** Ответ может потеряться по таймауту. Строка с
   `finished_at IS NULL` означает «исход неизвестен» и БЛОКИРУЕТ повтор по этой площадке,
   пока человек не сверится с их кабинетом. Тот же порядок, что в ОРД.
3. **Пиксель только показной.** В их теге две ссылки, и кликовая выглядит так же
   (`a.A=cl`). Взять её вместо показной — значит не считать показы вовсе и узнать об этом
   через месяц по пустым отчётам.
"""
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ad.build import pixel_setup
from app.ad.models import AdCampaign, AdCampaignPlacement
from app.weborama import enums, naming, tags
from app.ext_lock import WEBORAMA_PROVISION, only_one
from app.weborama.client import WcmClient, WcmError, WcmUnknownOutcome
from app.weborama.models import (KIND_CAMPAIGN, KIND_INSERTION, KIND_PROJECT,
                                 WeboramaRef, WeboramaSubmission)
from app.sales.models import SalesDeal, SalesPublisher

log = logging.getLogger("finance.weborama")

SETTING_ACCOUNT = "weborama_account_id"

# Кому пиксель нужен: площадка согласована и готова к запуску либо уже крутит. Раньше —
# рано (её ещё могут снять), позже — поздно (креатив уедет в DSP без пикселя и не начнёт
# крутиться).
READY_STATUSES = ("ждёт запуска", "запущен", "пауза")
# И ЕЩЁ ЕРИД (владелец 30.09.2026): пиксель — только размещению, у которого есть
# согласованный креатив с ЕРИД. Случай с прода: 54ZYCH / Максавит — пиксель в 10:44, ЕРИД
# автовыпуском в 11:00; по журналу так же ещё 8 размещений. Вставку в их кабинете не
# удалить, поэтому запираем ДО вызова, а не проверяем после.
ERID_CREATIVE_OK = ("согласован", "запущен", "пауза")
NO_ERID = ("нет ЕРИД у согласованного креатива — пиксель Weborama заводится после выпуска "
           "ЕРИД (автовыпуск раз в 30 минут)")


def erid_ready(db: Session, placement_ids) -> set:
    """Размещения, у которых есть согласованный креатив с ЕРИД."""
    ids = list(placement_ids)
    if not ids:
        return set()
    return {r[0] for r in db.execute(text("""
        SELECT DISTINCT placement_id FROM ad_campaign_creative
         WHERE placement_id = ANY(:p) AND erid IS NOT NULL AND status = ANY(:ok)
    """), {"p": ids, "ok": list(ERID_CREATIVE_OK)})}


class ProvisionError(RuntimeError):
    """Причина, по которой заводить нельзя. Текст показывается человеку как есть."""


def account_id(db: Session) -> str:
    """Аккаунт WCM для заведения. Настройка, а не переменная окружения: аккаунты
    закреплены за клиентами, и однажды их станет больше одного."""
    v = db.execute(text("SELECT value FROM company_settings WHERE key = :k"),
                   {"k": SETTING_ACCOUNT}).scalar()
    if not (v or "").strip():
        raise ProvisionError(
            "Не задан аккаунт Weborama. Настройка `weborama_account_id` — её значение "
            "выдаёт Weborama списком, и выбирается оно осознанно")
    return v.strip()


def _ref(db: Session, acc: str, kind: str, local_id: int) -> Optional[WeboramaRef]:
    return (db.query(WeboramaRef)
            .filter(WeboramaRef.account_id == acc, WeboramaRef.kind == kind,
                    WeboramaRef.local_id == local_id).first())


def _open_attempt(db: Session, acc: str, kind: str, local_id: int) -> bool:
    """Есть ли незакрытая попытка. Она запрещает повтор: объект мог создаться."""
    return bool(db.execute(text("""
        SELECT 1 FROM weborama_submissions
         WHERE account_id = :a AND kind = :k AND local_id = :l AND finished_at IS NULL
         LIMIT 1"""), {"a": acc, "k": kind, "l": local_id}).first())


def _start(db: Session, acc: str, kind: str, local_id: int, method: str,
           request: dict, user_id: Optional[int]) -> WeboramaSubmission:
    """Открыть попытку и СРАЗУ закоммитить: след должен пережить падение процесса."""
    s = WeboramaSubmission(account_id=acc, kind=kind, local_id=local_id, method=method,
                           request=request, user_id=user_id)
    db.add(s)
    db.commit()
    return s


def _finish(db: Session, s: WeboramaSubmission, wcm_id=None, error=None) -> None:
    from datetime import datetime
    s.finished_at = datetime.utcnow()      # в базе UTC, как у всех остальных колонок
    s.wcm_id = str(wcm_id) if wcm_id else None
    s.error = error
    db.commit()


def _ensure(db: Session, client: WcmClient, acc: str, kind: str, local_id: int,
            label: str, method: str, data: dict, user_id) -> str:
    """Завести объект, если его ещё нет. Возвращает их id.

    Порядок именно такой: реестр → незакрытая попытка → журнал → вызов → реестр.
    Пропустить любой шаг значит однажды получить дубль в чужой системе.
    """
    have = _ref(db, acc, kind, local_id)
    if have:
        return have.wcm_id
    if _open_attempt(db, acc, kind, local_id):
        raise ProvisionError(
            "По этому объекту есть незавершённая попытка: вызов ушёл, ответ не вернулся. "
            "Объект мог создаться — сверьтесь с кабинетом Weborama, повтор запрещён")

    s = _start(db, acc, kind, local_id, method, {**data, "label": label}, user_id)
    try:
        raw = client.call("POST", method, data={**data, "label": label})
        wid = client._created(raw, kind)
    except WcmUnknownOutcome as e:
        # Правило 2: исход неизвестен — попытка остаётся открытой и запирает повтор.
        # До 23.09.2026 таймаут закрывался как отказ, и повтор заводил вторую вставку.
        s.error = f"исход неизвестен: {e}"
        db.commit()
        raise ProvisionError(
            f"Weborama не подтвердила заведение ({e}). Объект мог создаться — сверьтесь "
            f"с кабинетом Weborama, повтор запрещён до сверки")
    except WcmError as e:
        _finish(db, s, error=str(e))
        raise ProvisionError(f"Weborama отказала: {e}")
    _finish(db, s, wcm_id=wid)

    db.add(WeboramaRef(account_id=acc, kind=kind, local_id=local_id,
                       wcm_id=wid, label=label, created_by=user_id))
    try:
        db.commit()
    except IntegrityError:
        # Замок на сделку не пускает два заведения разом, но у реестра есть и другие
        # писатели. Проигравший гонку получает текст, а не 500, — и текст честный:
        # в их кабинете этот объект теперь может быть дважды.
        db.rollback()
        raise ProvisionError(
            f"Этот объект одновременно завёл другой запрос; наш вызов тоже прошёл "
            f"(id {wid}) — в кабинете Weborama их может быть два, сверьтесь")
    return wid


# Посадочная КАМПАНИИ у Weborama — НАШ САЙТ (владелец 18.09.2026).
#
# Поле у них одно на кампанию и справочное: счёт ведут вставки, каждая со своей
# площадкой. Мы же до 18.09 подставляли туда адрес самой весомой площадки — выбор
# произвольный и вводящий в заблуждение: в диалоге стояло «Посадочная кампании:
# minicen.ru» рядом со строкой Maksavit, и это читалось как перепутанный адрес.
#
# Наш сайт честнее любой из двадцати одной: он ничей из них и ничего не обещает. На
# счёт показов поле не влияет — в креатив уезжает ссылка СВОЕЙ площадки, а не эта.
from app.dsp.creatives import OWN_SITE  # noqa: E402 — один адрес сайта на систему (Н-3)
OWN_LANDING = OWN_SITE.rstrip("/")


def default_landing(db: Session, camp: AdCampaign) -> str:
    """Посадочная ссылка кампании Weborama — всегда наш сайт.

    Аргументы остались ради вызывающих: подпись менять незачем, а чтение из базы здесь
    больше не нужно.
    """
    return OWN_LANDING


def plan(db: Session, camp: AdCampaign) -> dict:
    """Что произойдёт при нажатии. Показывается ДО подтверждения — цифра в вопросе
    «завести N вставок?» и есть то, что отличает осознанное действие от случайного."""
    pls = (db.query(AdCampaignPlacement)
           .filter(AdCampaignPlacement.campaign_id == camp.id).all())
    ready = [p for p in pls if p.status in READY_STATUSES and not p.is_direct]
    # Пиксель заказывает аккаунт галочкой в доп. параметрах РК (владелец 14.09.2026).
    # Не заказан — говорим это словами, а не пустыми числами: «0 площадок» и «по этой РК
    # пиксель не нужен» человек читает совершенно по-разному.
    px = pixel_setup(db, camp.deal_id)
    if not px["needed"]:
        return {"ready": len(ready), "todo": 0, "have": 0, "not_ordered": True,
                "blocked": "по этой РК пиксель Weborama не заказан — "
                           "включается в карточке сделки, блок «Доп. параметры РК»"}
    # Внешний тег означает, что вставку завёл клиент. Заводить свою рядом — это вторая
    # вставка на то же размещение и, как следствие, второй счёт показов.
    if px["mode"] == "external":
        return {"ready": len(ready), "todo": 0, "have": 0, "external": True,
                "blocked": "по этой РК внешний пиксель: вставку завёл клиент, "
                           "заводить свою не нужно"}
    try:
        acc = account_id(db)
    except ProvisionError as e:
        return {"ready": len(ready), "todo": 0, "have": 0, "blocked": str(e)}
    done = {r.local_id for r in db.query(WeboramaRef)
            .filter(WeboramaRef.account_id == acc, WeboramaRef.kind == KIND_INSERTION,
                    WeboramaRef.local_id.in_([p.id for p in ready] or [0])).all()}
    have_pixel = [p for p in ready if p.weborama_pixel]
    with_erid = erid_ready(db, [p.id for p in ready])
    proj = _ref(db, acc, KIND_PROJECT, camp.deal_id)
    wcamp = _ref(db, acc, KIND_CAMPAIGN, camp.id)
    return {"account": acc,
            # Привязка к уже заведённым в их кабинете (владелец 28.09.2026) — экран
            # показывает, что уже связано, и предлагает связать недостающее.
            "project_id": proj.wcm_id if proj else None,
            "campaign_id": wcamp.wcm_id if wcamp else None,
            "ready": len(ready),
            "have": len(have_pixel),
            # Без ЕРИД заводить нельзя — такие не считаются к заведению, а ждут автовыпуска.
            "todo": len([p for p in ready if not p.weborama_pixel and p.id in with_erid]),
            "wait_erid": len([p for p in ready if not p.weborama_pixel and p.id not in with_erid]),
            "registered": len(done),
            "skipped_direct": len([p for p in pls if p.is_direct]),
            "not_ready": len([p for p in pls if p.status not in READY_STATUSES])}


def provision(db: Session, camp: AdCampaign, landing_url: str, user_id=None,
              client: Optional[WcmClient] = None) -> dict:
    """Завести всё недостающее и забрать пиксели. Идёт по площадкам, не падая целиком:
    отказ по одной не должен отменять восемнадцать удачных.

    Один проход на СДЕЛКУ за раз (4.H4): проект Weborama заводится на сделку, и две РК
    одной сделки, нажатые разом, завели бы два проекта.
    """
    with only_one(WEBORAMA_PROVISION, camp.deal_id, ProvisionError, "Заведение в Weborama"):
        return _provision(db, camp, landing_url, user_id, client)


def _provision(db: Session, camp: AdCampaign, landing_url: str, user_id,
               client: Optional[WcmClient]) -> dict:
    acc = account_id(db)
    deal = db.query(SalesDeal).filter(SalesDeal.id == camp.deal_id).first()
    if not deal:
        raise ProvisionError("У РК нет сделки")
    # Отказ ЗДЕСЬ, а не только в `plan`: у заведения вставок два входа (кнопка дашборда
    # и прямой вызов), и правило, стоящее на одном из них, однажды обойдут по второму.
    # Заведение необратимо — вставки в их кабинете не удаляются по API.
    px = pixel_setup(db, deal.id)
    if not px["needed"]:
        raise ProvisionError(
            "По этой РК пиксель Weborama не заказан. Включается в карточке сделки, "
            "блок «Доп. параметры РК»")
    if px["mode"] == "external":
        raise ProvisionError(
            "По этой РК внешний пиксель — вставку завёл клиент. Заводить свою нельзя: "
            "это второй счёт показов по тому же размещению")
    brand = db.execute(text("SELECT b.name FROM sales_brands b WHERE b.id = :i"),
                       {"i": deal.brand_id}).scalar() if deal.brand_id else None
    if not brand:
        raise ProvisionError(
            "У сделки не указан бренд, а проект в Weborama заводится по бренду")
    if not (landing_url or "").strip():
        raise ProvisionError("Weborama требует посадочную ссылку у кампании")

    c = client or WcmClient(acc)
    proj_label = naming.project_label(deal.code, brand, camp.month)
    camp_label = naming.campaign_label(brand, deal.code)

    project_id = _ensure(db, c, acc, KIND_PROJECT, deal.id, proj_label,
                         "/advertiser/projects.json", {}, user_id)
    campaign_id = _ensure(db, c, acc, KIND_CAMPAIGN, camp.id, camp_label,
                          "/advertiser/campaigns.json",
                          {"project_id": project_id, "landing_url": landing_url.strip(),
                           "channel_id": enums.DEFAULT_CHANNEL}, user_id)

    # ad_space и сеть — константы аккаунта; берём их из уже заведённых вставок, а при
    # первом заведении находим в каталоге по метке.
    space = _our_space(db, c)

    pls = [p for p in db.query(AdCampaignPlacement)
           .filter(AdCampaignPlacement.campaign_id == camp.id).all()
           if p.status in READY_STATUSES and not p.is_direct and not p.weborama_pixel]
    done, failed = [], []
    with_erid = erid_ready(db, [p.id for p in pls])
    for p in pls:
        pub = db.query(SalesPublisher).filter(SalesPublisher.id == p.publisher_id).first()
        if p.id not in with_erid:
            failed.append({"placement_id": p.id, "name": pub.name if pub else "?",
                           "error": NO_ERID})
            continue
        domain = naming.domain_of(pub.domain if pub else "")
        if not domain:
            failed.append({"placement_id": p.id, "name": pub.name if pub else "?",
                           "error": "у площадки не задан домен, а он единственный "
                                    "различитель вставок"})
            continue
        label = naming.position_name(
            "SIMB-AD", "banner", naming.row_name("Desktop", camp_label, domain))
        try:
            ins = _ensure(db, c, acc, KIND_INSERTION, p.id, label,
                          "/advertiser/insertions/placements/json",
                          {"campaign_id": campaign_id, "ad_network_id": space["network"],
                           "ad_space_id": space["id"],
                           "delivery_format_id": enums.FORMAT_TRACKING_PIXEL}, user_id)
            pixel = _fetch_pixel(db, c, acc, p.id, ins, user_id)
        except ProvisionError as e:
            failed.append({"placement_id": p.id, "name": pub.name if pub else "?",
                           "error": str(e)})
            continue
        if not pixel:
            failed.append({"placement_id": p.id, "name": pub.name if pub else "?",
                           "error": "в теге нет пикселя показа (a.A=im) — кликовый вместо "
                                    "него брать нельзя"})
            continue
        p.weborama_pixel = pixel
        db.commit()
        done.append({"placement_id": p.id, "name": pub.name if pub else "?",
                     "insertion_id": ins})
    return {"project_id": project_id, "campaign_id": campaign_id,
            "done": done, "failed": failed}


def _our_space(db: Session, client: WcmClient) -> dict:
    """Наш ad_space и сеть. Один на все размещения — «какая площадка» несёт только метка
    вставки. Каталог у них глобальный (1080 записей), поэтому ищем по метке."""
    from app.weborama import matching
    from app.weborama.client import WcmError
    try:
        rows = client.ad_spaces_all()
    except WcmError as e:
        # Каталог не прочитался — отказ словами: проект и кампания к этому моменту уже
        # заведены, и 500 скрыл бы это (аудит 01.10.2026, С-14).
        raise ProvisionError(f"каталог ad_space Weborama не прочитан: {e}") from e
    got = matching.find_our_ad_space(rows)
    if not got.get("id"):
        raise ProvisionError(got.get("reason") or "не найден наш ad_space")
    return got


def _fetch_pixel(db: Session, client: WcmClient, acc: str, placement_id: int,
                 insertion_id: str, user_id) -> Optional[str]:
    """Забрать тег и достать из него ПОКАЗНЫЙ пиксель.

    Формат вставки — 3 («показы и клики»): именно он отдаёт `a.A=im`. Формат 4 меряет
    видимость и вместо пикселя даёт js-блок, которому место в другом поле креатива DSP.
    """
    s = _start(db, acc, "tag", placement_id, f"/advertiser/insertions/{insertion_id}/tags.json",
               {"insertion_id": insertion_id}, user_id)
    try:
        raw = client.insertion_tag(insertion_id)
    except WcmError as e:
        _finish(db, s, error=str(e))
        raise ProvisionError(f"Тег не получен: {e}")
    pixel = tags.impression_pixel(raw)
    _finish(db, s, wcm_id=insertion_id,
            error=None if pixel else "в ответе нет пикселя показа")
    # Кликовый счётчик — из того же ответа (01.10.2026): конечный URL креатива в DSP.
    click = tags.parse(raw).get("click")
    if click:
        db.execute(text("UPDATE ad_campaign_placement SET weborama_click = :c WHERE id = :p"),
                   {"c": click, "p": placement_id})
    return pixel


__all__ = ["plan", "provision", "account_id", "ProvisionError", "READY_STATUSES", "erid_ready"]


def attach_existing(db: Session, camp: AdCampaign, project_id, campaign_id,
                    user_id=None) -> dict:
    """Привязать к РК проект и кампанию, УЖЕ заведённые в кабинете Weborama (владелец
    28.09.2026: «дать возможность повесить на заведённую уже»).

    Случай 54ZYCH: проект и кампанию завели 18.09 с демо-экрана, реестр о них не знал, и
    кнопка W упиралась в «label must be unique». После привязки W берёт их из реестра и
    заводит только вставки.

    Номера вводит человек из кабинета Weborama; прочитать их список по API нам нечем.
    Защиты: номер — число; уже связанное с ЭТОЙ РК другим номером не перезаписывается;
    номер, связанный с ДРУГОЙ сделкой или РК, не принимается — два наших объекта на
    одной их кампании сложили бы чужие показы в одну строку.
    """
    acc = account_id(db)
    pairs = ((KIND_PROJECT, camp.deal_id, project_id, "проект"),
             (KIND_CAMPAIGN, camp.id, campaign_id, "кампания"))
    todo = []
    for kind, local_id, wid, what in pairs:
        wid = str(wid or "").strip()
        if not wid:
            continue
        if not wid.isdigit():
            raise ProvisionError(f"{what}: номер Weborama — только цифры, а не «{wid}»")
        have = _ref(db, acc, kind, local_id)
        if have:
            if have.wcm_id == wid:
                continue
            raise ProvisionError(f"{what} уже связан с номером {have.wcm_id} — "
                                 f"перепривязка не делается, сверьтесь с кабинетом")
        other = (db.query(WeboramaRef)
                 .filter(WeboramaRef.account_id == acc, WeboramaRef.kind == kind,
                         WeboramaRef.wcm_id == wid, WeboramaRef.local_id != local_id).first())
        if other:
            raise ProvisionError(f"{what} {wid} уже связан с другой "
                                 f"{'сделкой' if kind == KIND_PROJECT else 'РК'} "
                                 f"(#{other.local_id})")
        todo.append((kind, local_id, wid, what))
    if not todo:
        raise ProvisionError("Нечего привязывать: номера не указаны или уже связаны")
    if any(k == KIND_CAMPAIGN for k, *_ in todo) and not (
            _ref(db, acc, KIND_PROJECT, camp.deal_id)
            or any(k == KIND_PROJECT for k, *_ in todo)):
        raise ProvisionError("Кампания Weborama живёт внутри проекта — укажите и проект")
    for kind, local_id, wid, what in todo:
        db.add(WeboramaRef(account_id=acc, kind=kind, local_id=local_id, wcm_id=wid,
                           label=f"привязан вручную: {what} {wid}", created_by=user_id))
    db.commit()
    return {"attached": [{"kind": k, "wcm_id": w} for k, _l, w, _ in todo]}
