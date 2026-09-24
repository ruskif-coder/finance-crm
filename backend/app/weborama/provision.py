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
OWN_LANDING = "https://simb-ad.com"


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
    return {"account": acc,
            "ready": len(ready),
            "have": len(have_pixel),
            "todo": len([p for p in ready if not p.weborama_pixel]),
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
    for p in pls:
        pub = db.query(SalesPublisher).filter(SalesPublisher.id == p.publisher_id).first()
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
    rows = client.ad_spaces_all()
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
    return pixel


__all__ = ["plan", "provision", "account_id", "ProvisionError", "READY_STATUSES"]
