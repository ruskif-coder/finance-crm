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
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.ad.models import AdCampaign
from app.dsp.client import MsClient, MsError
from app.sales.models import SalesDeal

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
        "status": "STOPPED",
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
    except MsError:
        pass  # список не критичен: без него просто идём в add

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
           "sync_campaign_plan", "plan_total", "build_plan_params", "date"]
