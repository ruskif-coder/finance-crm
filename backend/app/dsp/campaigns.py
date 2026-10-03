"""Заведение РК в DSP: наши данные → Campaign.add → xxhash → ad_campaign.

Единственное место, где из `AdCampaign` + сделки собираются параметры кампании МС и где
полученный хеш кладётся в `ad_campaign.ms_campaign_xxhash`. Правила (решения владельца
01–02.09.2026, память dsp-api / traffic-dashboard-mvp):

  · в МС уходит ПЛАН целиком (`limits.*.total` + даты), остаток никогда — темп по дням держит
    пейсер МС; `traffic_distribution="uniform_pro"` шлём ЯВНО (default API — accelerated);
  · day/hour лимиты = 0 (при uniform_pro они конфликтуют);
  · создаём всегда STOPPED — запуск отдельным событием (ЕРИД есть И дата наступила);
  · защита от дублей в три ступени: хеш уже у нас → хеш в журнале по нашему local_ref
    (МС создал, наш коммит не дошёл) → совпадение по title в getListByPartner → только тогда add.
"""
import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.ad.models import AdCampaign
from app.dsp import client as ds
from app.dsp.client import MsClient, MsError
from app.sales.models import SalesDeal

log = logging.getLogger(__name__)

TITLE_MAX = 254

# Приставка к названию тренировочной кампании. Решение владельца 09.09.2026: отдельного
# демо-клиента у нас НЕТ, и демо-экран ходит в боевой кабинет — значит тренировочные
# кампании лежат там же, где настоящие, и должны быть отличимы с одного взгляда.
#
# Она же закрывает третью ступень защиты от дублей ниже: та сверяет название ТОЧНЫМ
# равенством по всему кабинету партнёра, и без приставки тренировка с тем же именем была
# бы принята за уже заведённую боевую РК — мы бы привязали сделку к чужой кампании.
DEMO_TITLE_PREFIX = "ТЕСТ · "


def campaign_title(camp: AdCampaign, deal: SalesDeal) -> str:
    """Имя РК в МС: <код сделки> · <название сделки> · <YYYY-MM>. По коду находим у себя."""
    parts = [str(deal.code or deal.id)]
    if (deal.title or "").strip():
        parts.append(deal.title.strip())
    if camp.month:
        parts.append(camp.month.strftime("%Y-%m"))
    return " · ".join(parts)[:TITLE_MAX]


def _limit(total) -> dict:
    return {"total": int(round(total or 0)), "day": 0, "hour": 0}


def build_campaign_params(camp: AdCampaign, deal: SalesDeal) -> dict:
    if not (camp.date_start and camp.date_end):
        raise MsError(f"РК #{camp.id}: нет date_start/date_end — МС их требует")
    if camp.date_end < camp.date_start:
        raise MsError(f"РК #{camp.id}: date_end раньше date_start")
    return {
        "title": campaign_title(camp, deal),
        "status": ds.STOPPED,
        "limits": {
            "traffic_distribution": "uniform_pro",
            "show": _limit(camp.plan_show),
            "click": _limit(camp.plan_click),
            "budget": _limit(camp.plan_budget),
            "show_per_user": {"total": 0, "day": 0, "hour": 0},
        },
        "date_start": camp.date_start.isoformat(),
        "date_end": camp.date_end.isoformat(),
    }


def _persist(db: Session, camp: AdCampaign, xxhash: str, commit: bool) -> str:
    camp.ms_campaign_xxhash = xxhash
    camp.ms_synced_at = datetime.utcnow()
    db.flush()
    if commit:
        db.commit()
    return xxhash


def ensure_campaign(db: Session, camp: AdCampaign, client: MsClient,
                    commit: bool = True) -> str:
    """Гарантирует, что у РК есть кампания в МС; возвращает её xxhash."""
    if camp.ms_campaign_xxhash:
        return camp.ms_campaign_xxhash

    # 1) МС мог создать, а наш коммит не дойти — журнал помнит
    prev = client.last_ok_xxhash("Campaign.add", "campaign", camp.id)
    if prev:
        return _persist(db, camp, prev, commit)

    deal = db.query(SalesDeal).get(camp.deal_id)
    if deal is None:
        raise MsError(f"РК #{camp.id}: сделка {camp.deal_id} не найдена")
    params = build_campaign_params(camp, deal)

    # Прошлый add ушёл без ответа (таймаут): кампания могла создаться. Тогда поиск по
    # имени — не удобство, а условие: без списка повторять вслепую нельзя (4.L5).
    unsure = client.unknown_outcome("Campaign.add", "campaign", camp.id)

    # 2) та же кампания по имени уже есть у партнёра (заведена руками или раньше).
    #    Тренировочные пропускаем: они живут в том же кабинете и настоящей РК не являются.
    try:
        for row in client.campaign_list_by_partner():
            if not isinstance(row, dict) or not row.get("xxhash"):
                continue
            title = str(row.get("title") or "")
            if title.startswith(DEMO_TITLE_PREFIX):
                continue
            if title == params["title"]:
                return _persist(db, camp, str(row["xxhash"]).upper(), commit)
    except MsError as e:
        if unsure:
            raise MsError(
                "прошлая попытка завести кампанию осталась без ответа, а список кампаний "
                f"сейчас недоступен ({e}). Кампания могла создаться — сверьтесь с "
                "кабинетом DSP, повтор вслепую завёл бы вторую")
        # без сомнений список не критичен: просто идём в add

    # 3) создаём
    xxhash = client.campaign_add(params, local_ref=camp.id)
    return _persist(db, camp, xxhash, commit)


def sync_campaign_plan(db: Session, camp: AdCampaign, client: MsClient,
                       commit: bool = True) -> Optional[str]:
    """План изменился (объём/даты) → Campaign.edit с ПОЛНЫМ новым total (не остатком!)."""
    if not camp.ms_campaign_xxhash:
        return None
    deal = db.query(SalesDeal).get(camp.deal_id)
    params = build_campaign_params(camp, deal)
    params.pop("status", None)  # статусом рулим отдельно (setStatus), edit его не трогает
    client.campaign_edit(camp.ms_campaign_xxhash, params, local_ref=camp.id)
    camp.ms_synced_at = datetime.utcnow()
    db.flush()
    if commit:
        db.commit()
    return camp.ms_campaign_xxhash


# ИТОГОВЫЙ статус РК → статус кампании в DSP. Обратимое у нас остаётся обратимым и там:
# «остановлена» у нас можно снова запустить, а ARCHIVE в DSP назад не включается —
# поэтому она STOPPED. В архив уходит только то, что закончилось и у нас. «Готова» и
# «ожидает сборки» — ничего не крутит, значит и DSP стоит.
DSP_STATUS_OF = {
    "ожидает сборки": ds.STOPPED,
    "готова": ds.STOPPED,
    "запущена": ds.LAUNCHED,
    "пауза": ds.STOPPED,
    "остановлена": ds.STOPPED,
    "окончена": ds.ARCHIVE,
    "архив": ds.ARCHIVE,
}


def apply_status(db: Session, camp: AdCampaign, status: str,
                 client: Optional[MsClient] = None) -> Optional[str]:
    """Кнопка статуса РК → кампания в DSP. Возвращает выставленный статус DSP или None.

    До 23.09.2026 кнопка меняла только наш статус: кампания в DSP стояла, какой её
    завели, план туда не доезжал, а экран писал «крутится» (аудит, 4.M5). Крона нет —
    решение владельца: запуск и план уходят в DSP ТОЛЬКО нажатием.

    При запуске сначала ПОЛНЫЙ план, потом LAUNCHED: иначе кампания стартует со старым
    объёмом и датами. Кампании в DSP нет (площадки крутят сами или выгрузки не было) —
    трогать нечего, меняется только наш статус.

    Отказ DSP по КАМПАНИИ поднимается наверх: вызывающий НЕ меняет наш статус, иначе
    экран снова говорил бы о кампании, которая в DSP в другом состоянии. Отказ по
    отдельному КРЕАТИВУ — нет (аудит 01.10.2026, К-6): кампания уже принята, и откат
    нашего статуса сказал бы «не сохранено», когда в DSP крутится. Такой отказ уходит в
    отчёт (`refused`).
    """
    target = DSP_STATUS_OF.get(status)
    if not target or not camp.ms_campaign_xxhash:
        return None
    c = client or MsClient()
    if target == ds.LAUNCHED:
        sync_campaign_plan(db, camp, c, commit=False)
    c.campaign_set_status(camp.ms_campaign_xxhash, target, local_ref=camp.id)
    want, refused = follow_creatives(db, camp, target, c)
    # Отчёт после нажатия (владелец 30.09.2026): лимиты и сверка — не повод отменять уже
    # принятый DSP статус, поэтому их сбой пишется в отчёт, а не поднимается наверх.
    camp._dsp_check = {**after_status(db, camp, target, want, c), "refused": refused}
    return target


def after_status(db: Session, camp: AdCampaign, target: str, want: dict, client) -> dict:
    """После смены статуса: (1) при запуске — лимиты креативов догоняют их долю сразу, а не
    ночью (`dsp.limits.sync_limits`): доли пересчитаны по весам и запущенным площадкам в
    момент нажатия; (2) «отбивка» — статусы кампании и креативов ПЕРЕЧИТЫВАЮТСЯ из DSP.
    Ответ без ошибки ещё не значит, что DSP в том состоянии, о котором говорит экран.

    → {"limits": {...} | None, "mismatch": [{"what", "want", "got"}], "error": str | None}"""
    out = {"limits": None, "mismatch": [], "error": None}
    try:
        if target == ds.LAUNCHED:
            from app.dsp.limits import sync_limits
            out["limits"] = sync_limits(db, camp, client)
        got = (client.campaign_get_info(camp.ms_campaign_xxhash) or {}).get("status")
        if got != target:
            out["mismatch"].append({"what": "кампания", "want": target, "got": got})
        for xx, st in (want or {}).items():
            g = (client.creative_get_info(xx) or {}).get("status")
            if g != st:
                out["mismatch"].append({"what": f"креатив {xx}", "want": st, "got": g})
    except Exception as e:  # noqa: BLE001 — отчёт, а не отказ: статус DSP уже принял
        out["error"] = f"сверка с DSP не прошла: {e}"
    return out


# Креатив в РК крутится, только если запущена его ПЛОЩАДКА и сам он согласован (владелец
# 28.09.2026: «общий старт — всё, что согласовано и получено, или кнопкой против каждой
# площадки»). До этого креативы жили в DSP в том статусе, в каком их завели, — STOPPED, и
# запуск включал только кампанию.
CREATIVE_LIVE = ("согласован", "запущен")


def creative_targets(rows, campaign_target: str) -> dict:
    """{хеш: LAUNCHED|STOPPED} по строкам (хеш, статус площадки, статус креатива).

    Кампания в архиве — креативы не трогаем (они уходят вместе с ней). «Отклонён» —
    тоже: отозванный уже в архиве DSP, а STOPPED вернул бы его оттуда."""
    if campaign_target == ds.ARCHIVE:
        return {}
    out = {}
    for xx, pl_status, cr_status in rows:
        if not (xx or "").strip() or cr_status == "отклонён":
            continue
        live = (campaign_target == ds.LAUNCHED and pl_status == "запущен"
                and cr_status in CREATIVE_LIVE)
        out[xx.strip()] = ds.LAUNCHED if live else ds.STOPPED
    return out


def follow_creatives(db: Session, camp: AdCampaign, campaign_target: str, client) -> dict:
    from app.ad.models import AdCampaignCreative, AdCampaignPlacement
    rows = (db.query(AdCampaignCreative.ms_creative_xxhash, AdCampaignPlacement.status,
                     AdCampaignCreative.status)
            .join(AdCampaignPlacement, AdCampaignPlacement.id == AdCampaignCreative.placement_id)
            .filter(AdCampaignCreative.campaign_id == camp.id).all())
    want = creative_targets(rows, campaign_target)
    refused = []
    for xx, st in want.items():
        # Поштучно (аудит 01.10.2026, К-6): кампания уже принята DSP, и отказ на одном
        # креативе не должен ни бросать остальные, ни откатывать наш статус — тогда
        # экран говорил бы «не сохранено», а в DSP крутилось бы. Несогласие DSP видно в
        # сверке `after_status`: она перечитывает статус каждого креатива.
        try:
            client.creative_set_status(xx, st, local_ref=camp.id)
        except MsError as e:
            log.warning("DSP не принял статус %s креатива %s: %s", st, xx, e)
            refused.append({"what": f"креатив {xx}", "want": st, "error": str(e)[:300]})
    return want, refused


def plan_total(delivered, remaining) -> int:
    """Новый ПОЛНЫЙ `total` для `Campaign.edit`, когда меняем остаток.

    ЛОВУШКА, из-за которой эта функция и существует: в DSP `total` — лимит за
    ВЕСЬ срок кампании, а не остаток. Человек же думает остатком: «до конца надо открутить
    ещё столько». Послать остаток напрямую значит сказать МС, что весь план равен остатку,
    — он засчитает уже открученное и остановит кампанию раньше срока.

    Поэтому: `новый total = откручено + остаток`. Суточный темп МС пересчитает сам —
    `(total − открутили) / оставшиеся дни`, — и меняем мы именно ОСТАТОК, чтобы поменялись
    сутки.
    """
    d = max(0, int(round(float(delivered or 0))))
    r = max(0, int(round(float(remaining or 0))))
    return d + r


def build_plan_params(*, show_total=None, click_total=None, budget_total=None,
                      date_start=None, date_end=None) -> dict:
    """Тело `Campaign.edit` для правки плана: только то, что задано.

    Статус сюда не кладём — им рулит `Campaign.setStatus`, и `edit` его не трогает.
    День и час нулями: суточным темпом рулит МС (`uniform_pro`), наш суточный план —
    ориентир для решений, а не лимит наружу.
    """
    limits = {"traffic_distribution": "uniform_pro"}
    if show_total is not None:
        limits["show"] = _limit(show_total)
    if click_total is not None:
        limits["click"] = _limit(click_total)
    if budget_total is not None:
        limits["budget"] = _limit(budget_total)
    params = {"limits": limits}
    if date_start:
        params["date_start"] = date_start
    if date_end:
        params["date_end"] = date_end
    return params


__all__ = ["campaign_title", "build_campaign_params", "ensure_campaign",
           "sync_campaign_plan", "apply_status", "DSP_STATUS_OF", "plan_total", "build_plan_params", "date"]
