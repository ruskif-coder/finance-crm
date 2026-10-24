# -*- coding: utf-8 -*-
"""Уведомления контура закрытия (владелец 21.10.2026): всё в приложении; в телеграм — только две просрочки
(«3 дня на сверке», «30 дней без сканов»); остальное — ещё и ежедневным дайджестом.

События «по факту» зовутся из точек, где случилось действие; просрочки считает сканер (`rules_*`). Сбой уведомления
не роняет действие — сверка и пакет важнее письма."""
import logging
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import func
from sqlalchemy.orm import Session

log = logging.getLogger("finance.closing_notify")

RECON_OVERDUE_DAYS = 3


def _safe(fn):
    """Savepoint вокруг уведомления: упавший запрос не отравляет транзакцию действия (аудит 21.10.2026)."""
    from app.notify.safe import quiet

    def run(*a, **kw):
        with quiet(a[0] if a else kw.get("db"), f"контур закрытия: {fn.__name__}"):
            fn(*a, **kw)
    return run


def _emit(db: Session, key: str, **kw) -> None:
    from app.notify.bus import emit
    emit(db, key, **kw)


# ── сделка ────────────────────────────────────────────────────────────────────────────────────────

@_safe
def deal_on_recon(db: Session, deal, user) -> None:
    from app.sales.deal_label import deal_label
    _emit(db, "recon_arrived", title=f"{deal_label(deal)} — на итоговой сверке",
          body="РК завершена: проверьте факт и подтвердите сверку.", link=f"/sales/deals/{deal.code or deal.id}",
          entity_type="sales_deal", entity_id=deal.id, actor=user, ctx={"deal": deal}, code=deal.code)


@_safe
def deal_sent(db: Session, deal, m, user) -> None:
    from app.sales.deal_label import deal_label
    _emit(db, "deal_sent_to_do", title=f"{deal_label(deal)} — отправлена в ДО",
          body=f"Сверка зафиксирована, сделка в мастер-сделке {m.code}.", link=f"/accounts/master/{m.code}",
          entity_type="sales_deal", entity_id=deal.id, actor=user, ctx={"deal": deal}, code=deal.code)


# ── мастер-сделка ─────────────────────────────────────────────────────────────────────────────────

def _master(db: Session, key: str, m, title: str, body: str, user=None, tone=None) -> None:
    _emit(db, key, title=f"Мастер-сделка {m.code} — {title}", body=body, link=f"/accounts/master/{m.code}",
          entity_type="master_deal", entity_id=m.id, actor=user, ctx={"master": m}, code=m.code,
          **({"tone": tone} if tone else {}))


@_safe
def ready_check(db: Session, m) -> None:
    """Все сделки пакета сверены и отправлены в ДО — собирающему «собрана, ждёт дальнейших действий». Автоматика ДС не создаёт:
    раскладку правят после сверки (владелец 21.10.2026). Адресат получает и своё действие (actor не передаём): последней кнопкой
    мог нажать он сам, а пакет при этом стал собран."""
    from app.master_deal import service as MS
    from app.master_deal.status import DRAFT
    if m.status != DRAFT or not MS.gate(db, m)["ok"]:
        return
    _master(db, "master_deal_ready", m, "собрана, ждёт дальнейших действий",
            "Сверка завершена у всех сделок пакета: проверьте раскладку и создайте ДС — «В конструктор ДС».")


@_safe
def ds_created(db: Session, m, numbers: List[str], user) -> None:
    _master(db, "master_ds_created", m, "ДС созданы, ждут подтверждения",
            "Созданы: " + ", ".join(numbers) + ". Проверьте текст и основания, затем «Подтвердить ДС пакета».", user)


@_safe
def status_changed(db: Session, m, was: str, user) -> None:
    from app.master_deal import status as ST
    if m.status == ST.WAIT_1C and was != ST.WAIT_1C:
        _master(db, "master_wait_1c", m, "ждём 1С", "ДС пакета подтверждены — нужны счёт и УПД из 1С.", user)
    elif was == ST.WAIT_PAY and m.status in (ST.WAIT_SCANS, ST.ARCHIVE):
        _master(db, "master_closed", m, "оплачена",
                "Пакет оплачен." + (" Осталось приложить сканы подписанных документов." if m.status == ST.WAIT_SCANS else ""), user)
    elif m.status == ST.ARCHIVE and was != ST.ARCHIVE:
        _master(db, "master_closed", m, "в архиве", "Пакет закрыт: документы и сканы на месте.", user)


# ── просрочки (сканер) ────────────────────────────────────────────────────────────────────────────

def recon_overdue_hits(db: Session, Hit, fact_days) -> list:
    """Сделка на «Итоговой сверке» дольше 3 дней и ещё не отправлена в ДО — аккаунту и мастерам аккаунтов."""
    from app.final_recon.models import FinalReconDeal
    from app.master_deal.service import RECON_STAGE
    from app.sales.deal_label import deal_label
    from app.sales.models import SalesDeal, SalesDealStageHistory, SalesStage
    st = SalesStage.__table__
    stage_id = db.query(st.c.id).filter(st.c.name == RECON_STAGE).scalar()
    if not stage_id:
        return []
    since = (db.query(SalesDealStageHistory.deal_id, func.max(SalesDealStageHistory.at))
             .filter(SalesDealStageHistory.to_stage_id == stage_id).group_by(SalesDealStageHistory.deal_id).subquery())
    edge = datetime.utcnow() - timedelta(days=RECON_OVERDUE_DAYS)
    rows = (db.query(SalesDeal, since.c[1]).join(since, since.c.deal_id == SalesDeal.id)
            .outerjoin(FinalReconDeal, FinalReconDeal.deal_id == SalesDeal.id)
            .filter(SalesDeal.our_stage_id == stage_id, since.c[1] < edge, FinalReconDeal.sent_at.is_(None)).all())
    hits = []
    for d, at in rows:
        # `at` — timestamptz (с поясом), utcnow — без: вычитать в одном виде (упало 24.10.2026 на первой просрочке)
        days = (datetime.utcnow() - (at.astimezone(timezone.utc).replace(tzinfo=None) if at.tzinfo else at)).days
        hits.append(Hit(entity_type="sales_deal", entity_id=d.id, stage="overdue",
                        title=f"{deal_label(d)} — {days} дн. на итоговой сверке", link=f"/sales/deals/{d.code or d.id}",
                        ctx={"deal": d}, code=d.code, payload={"days": days},
                        facts=[{"k": "на сверке", "v": fact_days(days), "fg": "danger", "hot": True}]))
    return hits


def scans_overdue_hits(db: Session, Hit, fact_days) -> list:
    """Бумажный пакет: отправлен клиенту больше срока назад (`master_scans_due_days`, 30), а сканов нет — собирающему, красным."""
    from app.master_deal import issue as IS
    from app.master_deal import status as ST
    from app.master_deal.models import MasterDeal
    due = IS.due_days(db)
    edge = datetime.utcnow() - timedelta(days=due)
    hits = []
    for m in db.query(MasterDeal).filter(MasterDeal.status.in_((ST.WAIT_PAY, ST.WAIT_SCANS)), MasterDeal.sent_at < edge).all():
        if not ST.is_paper(db, m):
            continue
        miss = IS.missing_scans(db, m)
        if not miss:
            continue
        days = (datetime.utcnow() - m.sent_at).days
        hits.append(Hit(entity_type="master_deal", entity_id=m.id, stage="overdue",
                        title=f"Мастер-сделка {m.code} — {days} дн. без сканов", link=f"/accounts/master/{m.code}",
                        body="Нет сканов: " + ", ".join(x["label"] for x in miss), ctx={"master": m}, code=m.code,
                        payload={"days": days, "missing": len(miss)},
                        facts=[{"k": "без сканов", "v": fact_days(days), "fg": "danger", "hot": True},
                               {"k": "документов", "v": str(len(miss))}]))
    return hits
