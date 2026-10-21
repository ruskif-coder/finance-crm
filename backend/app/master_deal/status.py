# -*- coding: utf-8 -*-
"""Статус мастер-сделки — что сейчас происходит с пакетом (владелец 19.10.2026).

черновик → согласование → ждём 1С → выставление → ждём оплату → [ждём сканы] → архив.
«Ждём сканы» — только у бумаги (оплачено, но сканов подписанных нет): у ЭДО подпись клиента придёт из Диадока, и из «ждём
оплату» пакет идёт прямо в архив. Бумагу определяет подпись у нас (`signed_by_us_at`) или признак договора — пакет, ушедший
бумагой, остаётся бумажным, даже если у договора потом поставили ЭДО.
Первые два перехода ставит система: «В конструктор ДС» (ДС созданы → согласование) и «Подтвердить ДС» (→ ждём 1С); их откат —
свои кнопки («Вернуть в раскладку»), потому что за ними стоят документы, а не только надпись. Дальше пакет двигают руками:
вперёд на шаг — у кого есть редактирование мастер-сделок, назад на шаг — мастер или админ («мастер может и админ»).
Архив бумаги — только со сканом к КАЖДОМУ ДС и УПД пакета (`issue.missing_scans`); это блокировка, не предупреждение."""
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

DRAFT, AGREE, WAIT_1C, ISSUE, WAIT_PAY, WAIT_SCANS, ARCHIVE = STATUSES = (
    "черновик", "согласование", "ждём 1С", "выставление", "ждём оплату", "ждём сканы", "архив")
SYSTEM = (DRAFT, AGREE, WAIT_1C)        # в эти статусы — только системой (и их собственными кнопками отката)
HIDDEN = (ARCHIVE,)                     # реестр по умолчанию не показывает
PAPER = "бумага"


class StatusError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def channel_of(db: Session, m) -> Optional[str]:
    return db.execute(text("SELECT issue_channel FROM contracts WHERE id = :c"), {"c": m.contract_id}).scalar()


def is_paper(db: Session, m) -> bool:
    """Подпись у нас — бумага навсегда; отправлено без подписи у нас — ушло по ЭДО и ЭДО остаётся, даже если признак договора
    потом сменили (ревью 21.10.2026); до отправки — по признаку договора."""
    if getattr(m, "signed_by_us_at", None):
        return True
    if getattr(m, "sent_at", None):
        return False
    return channel_of(db, m) == PAPER


def sequence(db: Session, m) -> tuple:
    """Стадии ЭТОГО пакета: у ЭДО «ждём сканы» нет."""
    return STATUSES if is_paper(db, m) else tuple(s for s in STATUSES if s != WAIT_SCANS)


def label(db: Session, m) -> str:
    if m.status == ISSUE:
        ch = channel_of(db, m)
        return f"{ISSUE} · {ch}" if ch else ISSUE
    return m.status


def _can_back(user) -> bool:
    role = getattr(user, "role", None)
    return getattr(role, "key", None) == "admin" or bool(getattr(role, "is_master", False))


def _step(db: Session, m, d: int) -> Optional[str]:
    seq = sequence(db, m)
    i = seq.index(m.status) if m.status in seq else -1
    j = i + d
    return seq[j] if 0 <= i and 0 <= j < len(seq) else None


def _missing(db: Session, m) -> list:
    from app.master_deal.issue import missing_scans
    return missing_scans(db, m)


def actions(db: Session, m, user) -> dict:
    """Что показать в карточке: куда можно руками вперёд и назад (None — кнопки нет)."""
    nxt, prv = _step(db, m, 1), _step(db, m, -1)
    return {"next": nxt if nxt and m.status not in (DRAFT, AGREE) else None,
            "prev": prv if prv and prv not in SYSTEM[:-1] and m.status not in SYSTEM and _can_back(user) else None,
            "channel": channel_of(db, m) if m.status in (WAIT_1C, ISSUE) else None}


def move(db: Session, m, to: str, user) -> None:
    if to not in STATUSES:
        raise StatusError(400, "Статус: " + " / ".join(STATUSES))
    if to == _step(db, m, 1):
        if m.status in (DRAFT, AGREE):
            raise StatusError(409, "Этот шаг ставит система: ДС создаются «В конструктор ДС», подтверждаются «Подтвердить ДС»")
        if to == ISSUE and not channel_of(db, m):
            raise StatusError(409, "У договора не задано «Выставление» — ЭДО или бумага. Проставьте его в реестре договоров")
        if to == WAIT_PAY and not getattr(m, "sent_at", None):
            raise StatusError(409, "Сначала отметьте отправку клиенту — «Отправлено» на выставлении")
        if to == ARCHIVE:
            miss = _missing(db, m) if is_paper(db, m) else []
            if miss:
                raise StatusError(409, "В архив — когда приложены сканы подписанных ко всем документам. Нет: " + ", ".join(miss))
            if not getattr(m, "docs_closed_at", None):
                raise StatusError(409, "В архив — когда документы закрыты: отправлены в ЭДО или приложены сканы")
    elif to == _step(db, m, -1):
        if m.status in SYSTEM:
            raise StatusError(409, "Назад отсюда — своей кнопкой: «Вернуть в раскладку» или снятие подтверждения ДС")
        if not _can_back(user):
            raise StatusError(403, "Вернуть статус назад может мастер или админ")
        if m.status == WAIT_PAY:                          # назад из «ждём оплату» — отмена отправки
            closed_by_send = m.docs_closed_at and not getattr(m, "signed_by_us_at", None)   # ЭДО: закрыто отправкой
            m.sent_at = m.sent_by = m.track_no = None
            if closed_by_send:
                m.docs_closed_at = m.docs_closed_by = None
    else:
        raise StatusError(409, f"Двигаем на один шаг: из «{m.status}» — в соседний статус")
    m.status, m.updated_at = to, datetime.utcnow()


# ── «Что нужно сейчас» ────────────────────────────────────────────────────────────────────────────
# Одна строка: что требуется пакету и от кого (аккаунт / юрист / 1С / финансы), тон — как срочно. Считается от статуса и тех
# же проверок, что держат кнопки карточки (`to_annex.ready`, заявки юристу), — второго набора правил нет.

_WHY = (("сверка не завершена", "дождаться сверки сделок"), ("номер ДС", "задать стартовый № ДС"),
        ("не сходится", "свести раскладку с суммой сделок"), ("нет позиций", "разложить позиции"))


def _ready(db: Session, m) -> list:
    from app.master_deal import to_annex as TA
    return TA.ready(db, m)


def _open_legal(db: Session, m) -> int:
    return db.execute(text("""SELECT count(*) FROM legal_requests l JOIN sales_annexes a ON a.id = l.annex_id
                               WHERE a.master_deal_id = :m AND l.status IN ('открыта', 'в работе')"""), {"m": m.id}).scalar() or 0


def _drafts(db: Session, m) -> int:
    return db.execute(text("SELECT count(*) FROM sales_annexes WHERE master_deal_id = :m AND no IS NULL"), {"m": m.id}).scalar() or 0


def _t(text_: str, who: str, tone: str = "info") -> dict:
    return {"text": text_, "who": who, "tone": tone}


def todo(db: Session, m) -> Optional[dict]:
    if m.status == DRAFT:
        why = _ready(db, m)
        for key, act in _WHY:
            if any(key in w for w in why):
                return _t(act, "аккаунт", "warn")
        return _t(why[0], "аккаунт", "warn") if why else _t("создать ДС", "аккаунт")
    if m.status == AGREE:
        n = _open_legal(db, m)
        if n:
            return _t(f"заявка юристу по ДС ({n})", "юрист", "warn")
        return _t(f"подтвердить ДС ({_drafts(db, m)})", "аккаунт")
    if m.status == WAIT_1C:
        if not channel_of(db, m):
            return _t("в договоре не задано ЭДО или бумага", "аккаунт", "bad")
        return _t("ждём УПД из 1С", "1С")
    if m.status == ISSUE:
        ch = channel_of(db, m)
        if ch == "бумага":
            if not getattr(m, "signed_by_us_at", None):
                return _t("распечатать и подписать у нас", "финансы")
            return _t("отправить клиенту · бумага", "аккаунт")
        return _t("отправить в ЭДО" if ch else "в договоре не задано ЭДО или бумага", "аккаунт", "info" if ch else "bad")
    if m.status == WAIT_PAY:
        return _t("ждём оплату", "финансы")
    if m.status == WAIT_SCANS:
        miss = _missing(db, m)
        if not miss:
            return _t("сканы на месте — закрыть пакет", "аккаунт")
        late = m.sent_at and (datetime.utcnow() - m.sent_at).days >= _due_days(db)
        return _t(f"прикрепить сканы подписанных · не хватает {len(miss)}", "аккаунт", "bad" if late else "warn")
    return None


def _due_days(db: Session) -> int:
    from app.master_deal.issue import due_days
    return due_days(db)


def row_step(db: Session, m) -> Optional[str]:
    """Действие прямо из строки реестра (хендофф 19.10.2026): шаги-отметки без ввода данных; остальное — «открыть».
    docs_1c / edo_sent / signed / paper_sent / paid / scans / archive; contract — красная ссылка в договор; None — «открыть».
    `scans` не открывает окно, а раскрывает строку: сканов несколько, и каждый грузится в свою позицию."""
    if m.status == WAIT_1C:                      # до интеграции 1С — отметка руками; с 1С её поставит ответ «УПД готовы»
        return "docs_1c" if channel_of(db, m) else "contract"
    if m.status == ISSUE:
        ch = channel_of(db, m)
        if not ch:
            return "contract"
        if ch == "ЭДО" and not getattr(m, "signed_by_us_at", None):
            return "edo_sent"
        return "paper_sent" if getattr(m, "signed_by_us_at", None) else "signed"
    if m.status == WAIT_PAY:
        if is_paper(db, m):
            return "paid"
        return "archive" if getattr(m, "docs_closed_at", None) else None
    if m.status == WAIT_SCANS:
        return "scans" if _missing(db, m) else "archive"
    return None
