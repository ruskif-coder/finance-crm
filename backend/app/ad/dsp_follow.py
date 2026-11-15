# -*- coding: utf-8 -*-
"""Кампания в DSP следует статусу РК — ПОСЛЕ коммита наших изменений (аудит 13.11.2026, владелец 14.11: «отдельной задачей с
полным набором тестов»).

КАК БЫЛО. Ручки статуса РК и площадки держали транзакцию и замок долей РК (`ext_lock.lock_campaign_shares`, до 60 с ожидания)
всё время, пока шли вызовы DSP: план кампании, её статус, статус каждого креатива, лимиты и перечитывание — 2N+3 и больше
последовательных HTTP по 30 с. Соседние действия по той же РК ждали или получали 409, а повтор нажатия после таймаута
браузера запускал второй полный проход.

КАК СТАЛО.
  1. Снимок того, что ручка меняет (статус РК; статус и первая отметка запуска каждой площадки; состояние пар «в размещении»
     сбора запуска) — до первой записи.
  2. Наши изменения записываются и КОММИТЯТСЯ: замок долей отпущен, транзакции нет.
  3. Вызовы DSP — под `only_one(DSP_FOLLOW, РК)`: второй клик сразу получает «уже идёт», а не второй проход.
  4. DSP отказал по КАМПАНИИ — наши изменения откатываются по снимку (компенсирующая запись) и ручка отвечает 502, как и
     раньше: экран не говорит о кампании того, чего в DSP нет. Откат — «сравнить и вернуть»: строка, которую после нас уже
     изменил кто-то другой, не трогается и называется в ответе.

Цена: пока идут вызовы DSP (секунды), экран может показать новый статус до подтверждения DSP.
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session


class FollowBusy(RuntimeError):
    """По этой РК уже идёт отправка статуса в DSP."""


@dataclass
class Snapshot:
    campaign_id: int
    campaign_status: Optional[str] = None
    placements: Dict[int, Tuple[Optional[str], object]] = field(default_factory=dict)    # id → (статус, first_started_at)
    targets: Dict[int, Optional[str]] = field(default_factory=dict)                       # launch_prep_target.id → state
    after: Dict[str, dict] = field(default_factory=dict)                                  # что записали мы — для сравнения


def take(db: Session, c) -> Snapshot:
    """Снимок ДО изменений ручки."""
    from app.ad.models import AdCampaignPlacement
    s = Snapshot(campaign_id=c.id, campaign_status=c.status)
    for p in db.query(AdCampaignPlacement).filter_by(campaign_id=c.id).all():
        s.placements[p.id] = (p.status, getattr(p, "first_started_at", None))
    s.targets = dict(db.execute(text("SELECT id, state FROM launch_prep_target WHERE deal_id = :d AND archived_at IS NULL"),
                                {"d": c.deal_id}).all())
    return s


def mark_written(db: Session, s: Snapshot, c) -> None:
    """Запомнить, ЧТО записали мы (после своих изменений, до коммита): откат вернёт только то, что с тех пор не тронули."""
    from app.ad.models import AdCampaignPlacement
    s.after["campaign"] = {"status": c.status}
    s.after["placements"] = {p.id: (p.status, getattr(p, "first_started_at", None))
                             for p in db.query(AdCampaignPlacement).filter_by(campaign_id=c.id).all()}
    s.after["targets"] = dict(db.execute(text("SELECT id, state FROM launch_prep_target WHERE deal_id = :d AND archived_at IS NULL"),
                                         {"d": c.deal_id}).all())


def restore(db: Session, s: Snapshot) -> list:
    """Вернуть снимок «сравнить и вернуть». → что не вернули, потому что после нас это уже поменял другой (словами)."""
    from app.ad import build
    from app.ad.models import AdCampaign, AdCampaignPlacement
    skipped = []
    c = db.get(AdCampaign, s.campaign_id)
    if c is not None:
        if c.status == s.after.get("campaign", {}).get("status"):
            c.status = s.campaign_status
        elif c.status != s.campaign_status:
            skipped.append(f"статус РК уже «{c.status}»")
    ours = s.after.get("placements", {})
    for p in db.query(AdCampaignPlacement).filter_by(campaign_id=s.campaign_id).all():
        before, mine = s.placements.get(p.id), ours.get(p.id)
        if before is None or mine is None or (p.status, p.first_started_at) == before:
            continue
        if (p.status, p.first_started_at) == mine:
            p.status, p.first_started_at = before
        else:
            skipped.append(f"площадка #{p.id} уже «{p.status}»")
    mine_t = s.after.get("targets", {})
    for tid, was in s.targets.items():
        if mine_t.get(tid) == was:
            continue
        cur = db.execute(text("SELECT state FROM launch_prep_target WHERE id = :i"), {"i": tid}).scalar()
        if cur == mine_t.get(tid):
            db.execute(text("UPDATE launch_prep_target SET state = :s WHERE id = :i"), {"s": was, "i": tid})
    db.flush()
    build.recompute_shares(db, s.campaign_id)
    return skipped


def run(db: Session, c, snapshot: Snapshot, call_dsp: Callable[[], Optional[str]], *,
        lock_shares: Callable[[], None], on_refused: Callable[[Exception, list], Exception]) -> Optional[str]:
    """Шаги 2–4: коммит своего, вызовы DSP вне транзакции, откат по снимку при отказе DSP по кампании.

    `call_dsp` — вызов `dsp.campaigns.apply_status` (возвращает статус DSP или None); `lock_shares` — замок долей РК для
    отката; `on_refused(ошибка, не_вернули)` — исключение, которым ручка ответит (502 с причиной)."""
    from app.dsp.client import MsError
    mark_written(db, snapshot, c)
    db.commit()                                                     # замок долей отпущен, транзакции нет
    try:
        return call_dsp()
    except MsError as e:
        db.rollback()
        lock_shares()
        skipped = restore(db, snapshot)
        db.commit()
        raise on_refused(e, skipped)


def one_at_a_time(campaign_id: int):
    """Один проход в DSP на РК: второй клик — сразу «уже идёт», а не ожидание и второй полный проход."""
    from app.ext_lock import DSP_FOLLOW, only_one
    return only_one(DSP_FOLLOW, campaign_id, FollowBusy, "Отправка статуса в DSP")
