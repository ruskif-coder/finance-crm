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

# ──────────────── АККАУНТИНГ: очередь сделок (сканер, urgency.py) ────────────────
# Шесть событий одного источника: все считаются функцией app.sales.urgency.evaluate,
# той же, что строит очередь «Что делать» на дашборде аккаунта. Ключ события приходит
# в Verdict.kind — сканер не пересчитывает условия заново. Это и есть гарантия, что
# лента уведомлений не разойдётся с очередью: расхождение между ними было бы багом,
# а не разными точками зрения.
#
# Порогов here нет: их задаёт сама функция срочности (правила 1-8 ТЗ), а не params —
# иначе порог жил бы в двух местах и очередь с лентой начали бы считать по-разному.
# repeat_days — единственный параметр, он про частоту напоминания, не про условие.
#
# Получатель везде «Аккаунт сделки»: это его рабочая очередь. Сейлз о срыве старта
# узнаёт из своих событий, дублировать ему документные напоминания незачем.

register(Event(
    key="deal_mp_missing", direction="account", group="Очередь сделок",
    title="Нет медиаплана, а старт близко",
    description=("Старт РК через 5 дней или меньше, а медиаплан к сделке не привязан. "
                 "Первое правило очереди: без плана дальше ничего не двинется."),
    tone="danger", action="Собрать МП", widget_group="Сделки", scan=True,
    recipients=[{"type": "resolver", "value": "account_manager"}],
    channels={"app": True},
    params={"repeat_days": 2},
))

register(Event(
    key="mp_unapproved", direction="account", group="Очередь сделок",
    title="МП не завизирован, старт через 3 дня",
    description=("План есть, визы клиента нет, а РК стартует. В отличие от «МП висит "
                 "на согласовании» адресовано аккаунту сделки, а не согласующим."),
    tone="danger", action="Пингануть", widget_group="Сделки", scan=True,
    recipients=[{"type": "resolver", "value": "account_manager"}],
    channels={"app": True},
    params={"repeat_days": 2},
))

register(Event(
    key="mp_rework", direction="account", group="Очередь сделок",
    title="МП отклонён — нужны правки",
    description=("Клиент ответил отказом, а старт РК близко. Отличается от «МП не "
                 "завизирован»: там ждут ответа, здесь ответ получен и он отрицательный."),
    tone="danger", action="Переделать МП", widget_group="Сделки", scan=True,
    recipients=[{"type": "resolver", "value": "account_manager"}],
    channels={"app": True},
    params={"repeat_days": 2},
))

register(Event(
    key="mp_verify", direction="account", group="Очередь сделок",
    title="МП собран конвейером и не проверен",
    description=("Конвейер годового плана создал сделку вместе с медиапланом. Пока аккаунт "
                 "не открыл план и не отметил «Проверено», сделка стоит на первой стадии — "
                 "отправлять клиенту непроверенный автоплан нельзя."),
    tone="warning", action="Проверить МП", widget_group="Сделки", scan=True,
    recipients=[{"type": "resolver", "value": "account_manager"}],
    channels={"app": True},
    params={"repeat_days": 3},
))

register(Event(
    key="booking_confirm", direction="account", group="Очередь сделок",
    title="Бронь не подтверждена, старт на горизонте",
    description=("До старта РК 15 дней или меньше, а сделка всё ещё в брони. "
                 "Дальше — сбор запуска: креативы и площадки нужно успеть согласовать."),
    tone="warning", action="Подтвердить бронь", widget_group="Сделки", scan=True,
    recipients=[{"type": "resolver", "value": "account_manager"}],
    channels={"app": True},
    params={"repeat_days": 3},
))

# Событие «ДС не подписано» здесь было и убрано 2026-08-17 вместе с правилом:
# файлов ДС в системе ноль, правило срабатывало на всех сделках в окне подряд.
# Вернётся вместе с приложениями к договору (SalesAnnex), когда ДС станут данными.

register(Event(
    key="act_missing", direction="account", group="Очередь сделок",
    title="Период закрыт, закрывающих нет",
    description=("РК закончилась больше 5 дней назад, а УПД/счёт не выставлены. "
                 "Пока их нет, платить клиенту не за что — это тормоз для денег."),
    tone="warning", action="Прикрепить документы", widget_group="Документы", scan=True,
    recipients=[{"type": "resolver", "value": "account_manager"}],
    channels={"app": True},
    params={"repeat_days": 5},
))

register(Event(
    key="stage_stuck", direction="account", group="Очередь сделок",
    title="Сделка стоит на стадии дольше нормы",
    description=("Норма — sla_days: у стадии, иначе у этапа, иначе дефолт слоя. "
                 "Свыше нормы — «скоро», свыше двойной — «просрочено»."),
    tone="warning", action="Двинуть", widget_group="Сделки", scan=True,
    recipients=[{"type": "resolver", "value": "account_manager"}],
    channels={"app": True},
    params={"repeat_days": 7},
))

register(Event(
    key="stage_unmapped", direction="account", group="Очередь сделок",
    title="Стадия не отнесена к слою денег",
    description=("Сделка не попадает ни в один слой, значит отчёты по ней врут. "
                 "Отключать не стоит: молча посчитанная планом сделка — это тихая "
                 "ошибка в деньгах, а не мелкое неудобство."),
    tone="danger", action="Разобрать", widget_group="Сделки", scan=True, locked=True,
    recipients=[{"type": "resolver", "value": "account_manager"},
                {"type": "role", "value": "admin"}],
    channels={"app": True},
    params={"repeat_days": 7},
))

# Правило 7 функции срочности (просрочка оплаты) события здесь НЕ имеет намеренно:
# тема дебиторки принадлежит invoice_overdue, который считает её по операциям — там,
# где факт оплаты действительно известен. На уровне сделки оплата не читается
# (связи deal → operation в схеме нет), поэтому в очереди строка появится только
# когда мост будет доведён, а уведомление так и останется за финмодулем.


# ─────────────────────────── СЕЙЛЗЫ: воронка ───────────────────────────
# Три события одного места — перехода сделки по нашему каталогу стадий (move_deal).
# Адресат везде «Сейлз сделки», а не «Ответственный»: последний отдаёт заодно аккаунта,
# у которого движение сделки и так стоит в очереди «Что делать». Дублировать ему то же
# самое второй раз значит приучить его не читать уведомления.
#
# Руководитель добавлен только к двум крайним исходам (бронь и срыв): это точки, где
# меняется прогноз квартала. К «доведено» его нет — деньги там уже посчитаны раньше.

register(Event(
    key="deal_booked", direction="sales", group="Воронка",
    title="Сделка ушла в бронь",
    description=("Сделка перешла на стадию «Бронь»: деньги из плановых стали реальными. "
                 "Отсюда же начинается отсчёт до подтверждения брони у аккаунта."),
    tone="success", action="Открыть сделку", widget_group="Сделки",
    recipients=[{"type": "resolver", "value": "sales_rep_of_deal"},
                {"type": "resolver", "value": "sales_head"}],
    channels={"app": True},
))

register(Event(
    key="deal_lost", direction="sales", group="Воронка",
    title="Сделка не состоялась",
    description=("Сделка переведена на терминальную стадию срыва («не случилась» / "
                 "«сорвалась») — с комментарием, который оставил тот, кто её двигал. "
                 "Порога по сумме нет: сообщаем по любой."),
    tone="danger", action="Открыть сделку", widget_group="Сделки",
    recipients=[{"type": "resolver", "value": "sales_rep_of_deal"},
                {"type": "resolver", "value": "sales_head"}],
    channels={"app": True},
))

register(Event(
    key="deal_done", direction="sales", group="Воронка",
    title="Сделка доведена",
    description="Сделка дошла до терминальной стадии успеха — бонус по ней сформирован.",
    tone="success", action="Открыть сделку", widget_group="Сделки",
    recipients=[{"type": "resolver", "value": "sales_rep_of_deal"}],
    channels={"app": True},
))


# ─────────────────────────── СЕЙЛЗЫ: годовой план ───────────────────────────

register(Event(
    key="plan_deals_generated", direction="sales", group="Годовой план",
    title="Конвейер создал сделки по плану",
    description=("Прогон конвейера годового плана. Адресат — сейлз, которому план "
                 "принадлежит; сам себе уведомление не приходит (emit не шлёт актору), "
                 "поэтому событие срабатывает, когда конвейер запустил кто-то другой."),
    tone="info", action="Открыть план", widget_group="Сделки",
    recipients=[{"type": "resolver", "value": "year_plan_owner"}],
    channels={"app": True},
))

register(Event(
    key="plan_month_empty", direction="sales", group="Годовой план",
    title="Месяц запланирован, а сделок нет",
    description=("В строке плана месяц включён и сумма проставлена, но ни одной сделки "
                 "в эту ячейку не привязано, а месяц уже начинается. Ступени: "
                 "предупреждение до начала месяца, «просрочено» — после."),
    tone="warning", action="Открыть план", widget_group="Сделки", scan=True,
    recipients=[{"type": "resolver", "value": "year_plan_owner"}],
    channels={"app": True},
    params={"before_days": 14, "repeat_days": 7},
))


# ─────────────────────────── СЕЙЛЗЫ: конструктор МП ───────────────────────────

register(Event(
    key="mp_draft_stale", direction="sales", group="Медиапланы",
    title="Черновик МП заброшен",
    description=("План лежит в черновиках и на согласование не уходил. Планы, собранные "
                 "конвейером годового плана, сюда НЕ попадают: про них есть своё событие "
                 "«МП собран конвейером и не проверен», адресованное аккаунту."),
    tone="warning", action="Открыть МП", widget_group="Документы", scan=True,
    recipients=[{"type": "resolver", "value": "mp_author"}],
    channels={"app": True},
    params={"after_days": 7, "repeat_days": 7},
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
