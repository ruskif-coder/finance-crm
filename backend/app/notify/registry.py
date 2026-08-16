"""Реестр событий — единственный источник правды о том, какие уведомления вообще бывают.

Живёт в КОДЕ, а не в базе (как SECTIONS в permissions.py): событие без обслуживающей его
функции бессмысленно, а редактируемый через интерфейс список немедленно разъехался бы
с кодом — ровно так, как в своё время разъехались ACTION_LABELS в журнале действий.
В базе хранится только event_key строкой, без FK.

Правило пополнения: событие попадает сюда ТОЛЬКО вместе с кодом, который его порождает
(вызов emit() или функция сканера). Каталог из макета docs/mockup_notifications.html —
это план, а не реестр; события переезжают сюда по мере реализации.

Страница настроек строится из этого реестра, поэтому новое событие = одна запись здесь,
без правки фронта.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Направления — вкладки в настройках уведомлений
DIRECTIONS = [
    ("account", "Аккаунтинг"),
    ("sales", "Сейлзы"),
    ("fin", "Финансы"),
    ("traffic", "Трафик"),
    ("sys", "Системные"),
]

CHANNELS = ["app", "tg", "mail", "digest"]


@dataclass(frozen=True)
class Event:
    key: str
    direction: str
    group: str                      # блок внутри направления («Медиапланы», «Оплаты»)
    title: str                      # как называется в настройках
    description: str
    tone: str = "info"              # danger | warning | success | info — тон в виджете
    action: str = ""                # подпись кнопки в уведомлении («Открыть МП»)
    widget_group: str = "Сделки"    # вкладка виджета на дашборде
    scan: bool = False              # True — состояниевое, считается сканером по расписанию
    locked: bool = False            # нельзя отключить (можно только перевести в дайджест)
    recipients: List[dict] = field(default_factory=list)   # дефолт: [{"type":..,"value":..}]
    channels: Dict[str, bool] = field(default_factory=lambda: {"app": True})
    params: Dict[str, int] = field(default_factory=dict)   # дефолтные пороги правила


EVENTS: Dict[str, Event] = {}


def register(ev: Event) -> Event:
    if ev.key in EVENTS:
        raise ValueError(f"Событие {ev.key} уже зарегистрировано")
    EVENTS[ev.key] = ev
    return ev


def get(key: str) -> Optional[Event]:
    return EVENTS.get(key)


def by_direction(direction: str) -> List[Event]:
    return [e for e in EVENTS.values() if e.direction == direction]


# ─────────────────────────── МЕДИАПЛАНЫ ───────────────────────────
# Четыре события, работавшие до появления реестра (жили прямыми вызовами notify_many
# в media_plans.py). Получатели и тексты сохранены один в один — переезд не должен
# менять поведение согласования МП.

register(Event(
    key="mp_submit", direction="account", group="Медиапланы",
    title="МП отправлен на согласование",
    description="Аккаунт нажал «На согласование». Уходит тем, кто согласует.",
    tone="info", action="Открыть МП", widget_group="Документы",
    recipients=[{"type": "resolver", "value": "mp_approvers"}],
    channels={"app": True},
))

register(Event(
    key="mp_approved", direction="account", group="Медиапланы",
    title="МП согласован",
    description="Автору плана и ответственным по нему. Дальше можно выставлять счёт.",
    tone="success", widget_group="Документы",
    recipients=[{"type": "resolver", "value": "mp_stakeholders"}],
    channels={"app": True},
))

register(Event(
    key="mp_rejected", direction="account", group="Медиапланы",
    title="МП отклонён",
    description="Автору плана и ответственным, с причиной отклонения.",
    tone="danger", action="Открыть МП", widget_group="Документы", locked=True,
    recipients=[{"type": "resolver", "value": "mp_stakeholders"}],
    channels={"app": True},
))

register(Event(
    key="mp_archived", direction="account", group="Медиапланы",
    title="МП отправлен в архив",
    description="Согласованный или отклонённый план убрали в архив.",
    tone="info", widget_group="Документы",
    recipients=[{"type": "resolver", "value": "mp_stakeholders"}],
    channels={"app": True},
))

register(Event(
    key="mp_recalled", direction="account", group="Медиапланы",
    title="МП отозван из согласования",
    description="Автор вернул план в черновики — согласующим больше не нужно его смотреть.",
    tone="warning", action="Открыть МП", widget_group="Документы",
    recipients=[{"type": "resolver", "value": "mp_approvers"}],
    channels={"app": True},
))

# Легаси-вид: до разделения на конкретные переходы все статусы МП писались одним kind.
# В реестре нужен, чтобы старые строки в notifications корректно оформлялись в виджете.
register(Event(
    key="mp_status", direction="account", group="Медиапланы",
    title="Смена статуса МП (легаси)",
    description="Старые уведомления, созданные до разделения на конкретные виды событий.",
    tone="info", action="Открыть МП", widget_group="Документы",
    recipients=[], channels={"app": True},
))


# ─────────────────────────── ФИНАНСЫ (сканер) ───────────────────────────
# Каденция общая: предупреждение за N дней до истечения текущего статуса, дальше
# повтор каждые N дней. Повтор считается от ФАКТА последней отправки (last_sent_at),
# а не по календарной сетке — пропущенный прогон сканера догоняется.

register(Event(
    key="invoice_overdue", direction="fin", group="Оплаты и дебиторка",
    title="Счёт не оплачен в срок",
    description=("Срок оплаты = конец периода операции + отсрочка контрагента "
                 "(та же формула, что в дебиторке). Ступени: предупреждение до срока, "
                 "срок наступил, просрочено сверх буфера."),
    tone="danger", action="Открыть операции", widget_group="Оплаты", locked=True,
    scan=True,
    recipients=[{"type": "role", "value": "manager"}, {"type": "role", "value": "admin"}],
    channels={"app": True},
    params={"before_days": 10, "repeat_days": 10},
))

# ─────────────────────────── АККАУНТИНГ (сканер) ───────────────────────────

register(Event(
    key="mp_stuck", direction="account", group="Медиапланы",
    title="МП висит на согласовании",
    description="План отправлен на согласование, но решение по нему так и не приняли.",
    tone="warning", action="Открыть МП", widget_group="Документы", scan=True,
    recipients=[{"type": "resolver", "value": "mp_approvers"}],
    channels={"app": True},
    params={"after_days": 3, "repeat_days": 10},
))

# ─────────────────────────── СИСТЕМНЫЕ: бэклог отладки ───────────────────────────
# Каналы по умолчанию — ТОЛЬКО "app". Обработчика дайджеста в системе нет (см. bus.py,
# LIVE_CHANNELS): событие, отправленное в дайджест, ложится в очередь и человеку
# не показывается вовсе. Дайджест здесь появится вместе со своим обработчиком.

register(Event(
    key="backlog_created", direction="sys", group="Бэклог отладки",
    title="Заведена запись наблюдения",
    description="После крупной правки что-то поставили под наблюдение — стоит знать, что именно.",
    tone="info", action="Открыть бэклог", widget_group="Документы",
    recipients=[{"type": "role", "value": "admin"}],
    channels={"app": True},
))

register(Event(
    key="backlog_confirmed", direction="sys", group="Бэклог отладки",
    title="Опасение подтвердилось",
    description=("Запись переведена в статус «подтвердилось»: то, чего боялись, "
                 "случилось. Отключать не стоит — это и есть смысл всего раздела."),
    tone="danger", action="Открыть бэклог", widget_group="Документы", locked=True,
    recipients=[{"type": "role", "value": "admin"}],
    channels={"app": True},
))

register(Event(
    key="backlog_overdue", direction="sys", group="Бэклог отладки",
    title="Истёк срок наблюдения",
    description=("watch_until прошёл, а запись так и не закрыта. Считается сканером: "
                 "истечение срока — не действие человека, эмитить его неоткуда."),
    tone="warning", action="Открыть бэклог", widget_group="Документы", scan=True,
    recipients=[{"type": "role", "value": "admin"}],
    channels={"app": True},
    # Напоминаем не чаще раза в неделю: чаще — и раздел выключат целиком.
    params={"repeat_days": 7},
))
