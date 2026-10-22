# -*- coding: utf-8 -*-
"""Уведомления Приоритезации (владелец 19.10.2026: «уведомления поднимай»).

Внутрь — аккаунту сделки (реестр, группа «Приоритезация»): ответ площадки, автостоп по плану, сбой автостопа, сбой сбора.
Наружу — площадке (`notify_publisher`): запрос и его повтор, старт и стоп РК. Денег площадке нет — как везде.
Сбой уведомления не отменяет действие: отправка, запуск и стоп важнее письма."""
import logging

from sqlalchemy.orm import Session

log = logging.getLogger("finance.prio")

VERDICT_TEXT = {"согласовано": "согласовала", "правки": "вернула с замечанием", "отказ": "отказала"}


def _pub_name(db: Session, publisher_id: int) -> str:
    from app.sales.models import SalesPublisher
    p = db.get(SalesPublisher, publisher_id)
    return (p.name if p else None) or f"площадка {publisher_id}"


def _inward(db: Session, key: str, deal, **kw) -> None:
    from app.notify.bus import emit
    from app.notify.safe import quiet
    from app.sales.deal_label import deal_label
    with quiet(db, f"приоритезация {deal.code}: {key}"):
        emit(db, key, title=f"{deal_label(deal)} — {kw.pop('title')}", link=f"/sales/deals/{deal.id}",
             entity_type="sales_deal", entity_id=deal.id, ctx={"deal": deal}, code=deal.code, **kw)


def site_answered(db: Session, deal, p) -> None:
    what = VERDICT_TEXT.get(p.status)
    if not what:
        return
    body = f"{_pub_name(db, p.publisher_id)} {what} запрос на приоритезацию."
    if p.comment and p.status != "согласовано":
        body += f" «{p.comment}»"
    _inward(db, "prio_site_answered", deal, title=f"площадка {what}", body=body,
            tone={"согласовано": "ok", "правки": "warn", "отказ": "bad"}[p.status])


def goal_reached(db: Session, deal, item: dict) -> None:
    _inward(db, "prio_goal_reached", deal, title="площадка выполнила план",
            body=f"{_pub_name(db, item['publisher_id'])}: {item['fact']} показов из {item['limit']} — "
                 "РК в системе приоритезации остановлена. Докрутить — «Старт» в карточке сделки.")


def stop_failed(db: Session, deal, item: dict) -> None:
    _inward(db, "prio_stop_failed", deal, title="план выполнен, а остановить не удалось",
            body=f"{_pub_name(db, item['publisher_id'])}: {item['fact']} из {item['limit']}, система не приняла стоп — "
                 f"{item['error']}. Площадка продолжает крутить: остановите вручную.")


def stat_failed(db: Session, error: str) -> None:
    from app.notify.bus import emit
    try:
        emit(db, "cron_prio_stat_failed", title="Сбор статистики приоритезации: ошибка", body=str(error)[:600],
             link="/settings/system", entity_type="cron", entity_id=1, actor=None)
        db.commit()
    except Exception:  # noqa: BLE001
        log.exception("тревога сбора приоритезации не ушла")


# ── площадке ──────────────────────────────────────────────────────────────────────────────────────

def _outward(db: Session, kind: str, deal, p, title: str, body: str, facts=()) -> dict:
    from app.launch_prep.erid_service import _deal_brand_name, deal_period_text
    from app.notify.outward import notify_publisher
    from app.sales.models import SalesPublisher
    pub = db.get(SalesPublisher, p.publisher_id)
    if pub is None:
        return {"status": "skip"}
    # Savepoint, а не `db.rollback()`: откат уносил внутренние уведомления по уже обработанным площадкам (аудит 21.10.2026).
    try:
        with db.begin_nested():
            brand, period = _deal_brand_name(db, deal), deal_period_text(deal)
            return notify_publisher(db, kind, pub.id, title=title, body=body, facts=list(facts),
                                    context=" · ".join(x for x in ((pub.domain or pub.name), brand, period) if x),
                                    link="/", entity_type="prio_placement", entity_id=p.id,
                                    values={"бренд": brand, "период": period})
    except Exception as e:  # noqa: BLE001
        log.warning("Площадке %s не ушло «%s»: %s", pub.id, kind, e)
        return {"status": "error", "why": str(e)[:200]}


def request_to_site(db: Session, deal, p, why: str) -> dict:
    """why: «новый» — отправка, «напоминание», «ответ» — после правок аккаунта."""
    from app.prio.service import request_of
    r = request_of(db, deal)
    title = {"новый": "Запрос на приоритезацию", "напоминание": "Напоминание: запрос на приоритезацию ждёт ответа",
             "ответ": "Запрос на приоритезацию поправлен"}[why]
    # По примеру баннеров («новый креатив», владелец 19.10.2026): что пришло, что от площадки нужно, плашки — что и какая услуга.
    body = ("Запрос прошёл нашу проверку и ждёт вашего решения. Впишите SKU товара на вашей витрине, "
            "проверьте посадочную и согласуйте — или верните с замечанием." if why != "ответ"
            else f"Мы ответили на ваше замечание: «{p.comment or ''}». Запрос снова ждёт вашего решения.")
    return _outward(db, "запрос приоритезации", deal, p, title, body,
                    facts=[("препарат", (r.product_name if r else None) or "—"), ("услуга", deal.product or "Приоритезация")])


def live_to_site(db: Session, deal, p, on: bool, reason: str = "") -> dict:
    if on:
        return _outward(db, "старт рк", deal, p, "Приоритезация запущена", "Размещение вышло в эфир.")
    return _outward(db, "приоритезация остановлена", deal, p, "Приоритезация остановлена",
                    "Мы остановили размещение" + (f": {reason}." if reason else "."))
