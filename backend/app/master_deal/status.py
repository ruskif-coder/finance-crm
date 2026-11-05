# -*- coding: utf-8 -*-
"""Статус мастер-сделки — что сейчас происходит с пакетом (владелец 19.10.2026, 02.11.2026).

черновик → согласование → ждём 1С → выставление → ждём оплату → [ждём сканы] → архив.
Пакет, заведённый на старте ради первичного ДС (`issued_at_start`, 02.11.2026): черновик → согласование → ждём закрытия;
«Отправить в ДО» на итоговой сверке возвращает его в черновик, и дальше он идёт обычным путём. «Ждём закрытия» стоит в
списке ПЕРЕД «ждём 1С»: всё от «ждём 1С» — закрытые сделки (расчёт СК, `agency_terms.calc`), стартовый пакет к ним не относится.
«Ждём сканы» — только у бумаги (оплачено, подписанных ещё нет). Бумагу определяет канал документов, уже ушедших клиенту
(`sign_channel`), до отправки — признак договора: ушедшее бумагой остаётся бумагой, даже если у договора потом поставили ЭДО.
Системные переходы (черновик, согласование, ждём закрытия, ждём 1С) ставят кнопки «В конструктор ДС», «Подтвердить ДС»,
«Отправить в ДО»; их откат — свои кнопки, потому что за ними стоят документы, а не только надпись. Дальше пакет двигают
руками: вперёд на шаг — у кого есть редактирование мастер-сделок, назад на шаг — мастер или админ. Условия шагов — по
документам (`issue`): «ждём оплату» — все выставлены, архив — все подписаны; это блокировка, не предупреждение."""
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

DRAFT, AGREE, WAIT_CLOSE, WAIT_1C, ISSUE, WAIT_PAY, WAIT_SCANS, ARCHIVE = STATUSES = (
    "черновик", "согласование", "ждём закрытия", "ждём 1С", "выставление", "ждём оплату", "ждём сканы", "архив")
SYSTEM = (DRAFT, AGREE, WAIT_CLOSE, WAIT_1C)   # в эти статусы — только системой (и их собственными кнопками отката)
HIDDEN = (ARCHIVE,)                     # реестр по умолчанию не показывает
PAPER = "бумага"


class StatusError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def channel_of(db: Session, m) -> Optional[str]:
    return db.execute(text("SELECT issue_channel FROM contracts WHERE id = :c"), {"c": m.contract_id}).scalar()


def is_paper(db: Session, m) -> bool:
    """Бумага ли этот пакет: документы, уже ушедшие клиенту, держат свой канал (хоть один бумажный — бумага); ничего не ушло —
    по признаку договора (ревью 21.10.2026: ушедшее по ЭДО не становится бумагой от смены признака)."""
    from app.master_deal import issue as IS
    gone = {getattr(d, "sign_channel", None) for d in IS.docs(db, m)} - {None}
    if gone:
        return PAPER in gone
    return channel_of(db, m) == PAPER


def sequence(db: Session, m) -> tuple:
    """Стадии ЭТОГО пакета: у ЭДО нет «ждём сканы», «ждём закрытия» — только у пакета со стартовым ДС."""
    skip = set()
    if not is_paper(db, m):
        skip.add(WAIT_SCANS)
    if not getattr(m, "issued_at_start", False):
        skip.add(WAIT_CLOSE)
    return tuple(s for s in STATUSES if s not in skip)


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


def _issue():
    from app.master_deal import issue as IS
    return IS


def actions(db: Session, m, user) -> dict:
    """Что показать в карточке: куда можно руками вперёд и назад (None — кнопки нет)."""
    nxt, prv = _step(db, m, 1), _step(db, m, -1)
    return {"next": nxt if nxt and m.status not in SYSTEM[:-1] else None,
            "prev": prv if prv and prv not in SYSTEM[:-1] and m.status not in SYSTEM and _can_back(user) else None,
            "channel": channel_of(db, m) if m.status in (WAIT_1C, ISSUE) else None}


def _check_forward(db: Session, m, to: str) -> None:
    IS = _issue()
    if m.status in SYSTEM[:-1]:
        raise StatusError(409, "Этот шаг ставит система: ДС создаются «В конструктор ДС», подтверждаются «Подтвердить ДС», "
                               "стартовый пакет возвращает в работу «Отправить в ДО»")
    if to == ISSUE and not channel_of(db, m):
        raise StatusError(409, "У договора не задано «Выставление» — ЭДО или бумага. Проставьте его в реестре договоров")
    if to == ISSUE and m.status == WAIT_1C:
        left = _desk_pending(db, m)
        if left:     # 05.11.2026: ручная отметка «УПД из 1С получены» заменена «Документами для 1С»
            raise StatusError(409, "Счёт и УПД вносит бухгалтер в «Документах для 1С». Не внесены: " + ", ".join(left))
    if to == WAIT_PAY:
        left = IS.not_sent(db, m)
        if left:
            raise StatusError(409, "В «ждём оплату» — когда выставлены все документы. Не выставлены: " + ", ".join(left))
    if to == ARCHIVE:
        left = IS.unsigned(db, m)
        if left or not IS.state(db, m)["total"]:
            raise StatusError(409, "В архив — когда подписаны все документы пакета. Не подписаны: " + (", ".join(left) or "документов нет"))


def _desk_pending(db: Session, m) -> list:
    from app.onec_desk.service import pending
    return pending(db, m)


def move(db: Session, m, to: str, user) -> None:
    if to not in STATUSES:
        raise StatusError(400, "Статус: " + " / ".join(STATUSES))
    if to == _step(db, m, 1):
        _check_forward(db, m, to)
    elif to == _step(db, m, -1):
        if m.status in SYSTEM:
            raise StatusError(409, "Назад отсюда — своей кнопкой: «Вернуть в раскладку» или снятие подтверждения ДС")
        if not _can_back(user):
            raise StatusError(403, "Вернуть статус назад может мастер или админ")
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


def _desk(db: Session, m) -> tuple:
    """«Документы для 1С»: (неисправленный возврат | None, сколько комплектов не внесено, сколько всего)."""
    from app.onec_desk import service as SV
    return SV.last_return(db, m), len(SV.pending(db, m)), len(SV.kits(db, m))


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
    if m.status == WAIT_CLOSE:
        return _t("ДС на старте выпущен — закрытие после итоговой сверки", "аккаунт")
    if m.status == WAIT_1C:
        if not channel_of(db, m):
            return _t("в договоре не задано ЭДО или бумага", "аккаунт", "bad")
        back, left, total = _desk(db, m)
        if back:
            return _t(f"бухгалтер вернул УПД № {back['upd_no']}: {back['text']}", "аккаунт", "bad")
        if total and not left:     # всё внесено, а пакет стоит: канал проставили позже или пакет вернули на шаг (ревью 05.11.2026)
            return _t("счёт и УПД внесены — переведите в «выставление»", "аккаунт", "warn")
        return _t(f"бухгалтерия: внесено {total - left} из {total}" if total - left else "ждём счёт и УПД от бухгалтерии",
                  "бухгалтерия")
    return _todo_issue(db, m)


def _todo_issue(db: Session, m) -> Optional[dict]:
    """Выставление и дальше — по документам: отклонённый клиентом документ важнее всего остального."""
    if m.status not in (ISSUE, WAIT_PAY, WAIT_SCANS):
        return None
    IS = _issue()
    bad = IS.rejected(db, m)
    if bad:
        return _t("клиент отклонил: " + ", ".join(bad), "аккаунт", "bad")
    if m.status == ISSUE:
        if not channel_of(db, m):
            return _t("в договоре не задано ЭДО или бумага", "аккаунт", "bad")
        left = IS.not_sent(db, m)
        return _t(f"выставить клиенту · осталось {len(left)}", "аккаунт") if left else _t("всё выставлено — ждём оплату", "финансы")
    if m.status == WAIT_PAY:
        return _t("ждём оплату", "финансы")
    left = IS.unsigned(db, m)
    if not left:
        return _t("всё подписано — закрыть пакет", "аккаунт")
    sent = IS.last_sent_at(db, m)
    late = bool(sent and (datetime.utcnow() - sent).days >= _due_days(db))
    return _t(f"ждём подписанных · не хватает {len(left)}", "аккаунт", "bad" if late else "warn")


def _due_days(db: Session) -> int:
    from app.master_deal.issue import due_days
    return due_days(db)


def row_step(db: Session, m) -> Optional[str]:
    """Действие прямо из строки реестра (хендофф 19.10.2026): шаги-отметки без ввода данных; остальное — «открыть».
    docs_1c / docs / paid / archive; contract — красная ссылка в договор; None — «открыть».
    `docs` не открывает окно, а раскрывает строку: с 02.11.2026 у каждого документа своя отметка подписи."""
    if m.status == WAIT_1C:                      # счёт и УПД вносит бухгалтер в «Документах для 1С» (05.11.2026), пакет уходит сам;
        if not channel_of(db, m):                # шаг руками — только если всё внесено, а пакет остался стоять
            return "contract"
        return None if _desk_pending(db, m) else "docs_1c"
    if m.status == ISSUE:
        return "docs" if channel_of(db, m) else "contract"
    if m.status == WAIT_PAY and is_paper(db, m):
        return "paid"
    if m.status in (WAIT_PAY, WAIT_SCANS):
        return "archive" if (not _issue().unsigned(db, m) and _issue().state(db, m)["total"]) else "docs"
    return None
