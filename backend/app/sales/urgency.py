"""Срочность сделки: одна чистая функция для очереди аккаунта И для уведомлений.

Почему одна: расхождение между «что делать» на дашборде и лентой уведомлений — это баг,
а не особенность. Раньше правила сканера (rule_invoice_overdue, rule_mp_stuck) считали
свои условия сами, каждое по-своему; здесь единственное место, где решается, что горит.
Очередь показывает строки, лента — их текстовые формулировки, источник один.

Функция намеренно не знает про SQLAlchemy и не ходит в базу: на входе DealFacts —
готовые факты, на выходе Verdict. Так её можно покрыть тестами на десятки комбинаций
дат без фикстур (backend/tests/test_urgency.py), а сборка фактов живёт в роутере.

Порядок правил = приоритет: первое сработавшее выигрывает и определяет и текст причины,
и кнопку действия. Нумерация в комментариях — по ТЗ docs/«кабинет аккаунта v1».
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional

from app.sales.stages import SLA_DEFAULTS

# Уровни срочности по убыванию. Порядок используется и для сортировки очереди.
OVERDUE, TODAY, SOON, NORMAL = "overdue", "today", "soon", "normal"
URGENCY_ORDER = {OVERDUE: 0, TODAY: 1, SOON: 2, NORMAL: 3}

DEFAULT_TERM_DAYS = 60   # как в дебиторке (reports.py): контрагент без term_days

# Правила 1-3 (нет МП / нет визы / нет ДС) осмысленны только ДО запуска: у сделки
# в эфире или на закрытии спрашивать «собери МП» поздно и незачем — там работают
# правила 6-7. Проверка идёт по нашей лестнице, а не по датам: лестница знает, где
# сделка на самом деле.
PRE_LAUNCH_KEYS = {"media_plan", "booking", "launch_prep"}

# Насколько далеко в прошлое смотрим на пропущенный старт. Старт, прошедший месяц
# назад, а сделка всё ещё «в проработке» — это мусор в данных, а не работа на сегодня;
# такие не должны навсегда занимать очередь. Ниже границы отдаём их правилу 5.
STALE_START_DAYS = 30

# За сколько дней до старта бронь пора подтверждать: с этого момента сделка должна
# уйти на сбор запуска, иначе креативы и площадки не успеть согласовать. Порог
# отдельный от SLA стадии: SLA считает «сколько стоим», а здесь важна дата старта.
BOOKING_CONFIRM_DAYS = 15


@dataclass
class DealFacts:
    """Факты о сделке на момент расчёта. Ни одно поле не вычисляется внутри."""
    # Стадия
    stage_key: Optional[str] = None          # позиция 2/2/2; None — не сопоставлена
    money_layer: Optional[str] = None        # None + не is_lost → «требует разбора»
    is_terminal: bool = False
    is_lost: bool = False
    stage_sla_days: Optional[int] = None     # SalesStage.sla_days
    phase_sla_days: Optional[int] = None     # SalesStagePhase.sla_days
    stage_since: Optional[date] = None       # вход в текущую стадию (история стадий)
    # Первая стадия цепочки («МП Подготовка»). Нужна отдельным фактом, а не выводится
    # из stage_key: media_plan носят ДВЕ стадии, а «МП собран конвейером и не проверен»
    # бывает только на первой — дальше сделку двигает сама отметка «Проверено».
    stage_is_first: bool = False
    # Даты размещения
    period_from: Optional[date] = None       # старт РК
    period_to: Optional[date] = None         # конец РК
    # Документы и согласования
    has_mp: bool = False                     # медиаплан есть — наш или пришедший из Битрикса
    mp_rejected: bool = False                # наш МП отклонён (status='rejected') — нужны правки
    # None — «виза неизвестна»: у МП, приехавшего файлом из Битрикса, статуса согласования
    # нет, и считать его незавизированным нельзя. Правило 2 при None не считается.
    mp_approved: Optional[bool] = None
    # Правила по нему сейчас нет — см. комментарий «3 (ТЗ)» в evaluate().
    has_ds: bool = False
    has_closing_docs: bool = False           # УПД или счёт выставлены
    # Оплата. None — «неизвестно», и это НЕ то же самое, что «не оплачено»: связи
    # сделки с операцией в схеме пока нет (мост «сделка → операция» доведён только
    # до приложения), поэтому на уровне сделки факт оплаты не читается. При None
    # правило 7 не считается вовсе — иначе каждая закрытая сделка выглядела бы
    # просроченной и заслоняла настоящие причины.
    is_paid: Optional[bool] = None
    term_days: Optional[int] = None          # отсрочка плательщика (Counterparty.term_days)


@dataclass
class Verdict:
    urgency: str
    reason: str = ""            # человеческая формулировка, одной фразой, без точки
    cta: str = ""               # подпись кнопки действия; пусто — действия нет
    kind: str = ""              # ключ события для уведомлений (registry.EVENTS)
    due: Optional[date] = None  # дата, по которой сортируется очередь внутри группы


def sla_for(f: DealFacts) -> Optional[int]:
    """Каскад SLA: стадия ?? этап ?? дефолт по stage_key.

    0 — «срока нет» и это осознанное значение, а не отсутствие: возвращаем 0, а не None,
    иначе падение на уровень ниже вернуло бы срок там, где его отменили вручную."""
    if f.stage_sla_days is not None:
        return f.stage_sla_days
    if f.phase_sla_days is not None:
        return f.phase_sla_days
    return SLA_DEFAULTS.get(f.stage_key or "")


def payment_due(f: DealFacts) -> Optional[date]:
    """Срок оплаты = конец размещения + отсрочка плательщика.

    Отсрочка берётся из реестра контрагентов (Counterparty.term_days), NULL → 60 дней,
    как в дебиторке. Без даты окончания РК срок посчитать нельзя — это не «сегодня»,
    а «неизвестно», поэтому None."""
    if not f.period_to:
        return None
    from datetime import timedelta
    days = f.term_days if f.term_days is not None else DEFAULT_TERM_DAYS
    return f.period_to + timedelta(days=days)


def _days_until(d: Optional[date], today: date) -> Optional[int]:
    return None if d is None else (d - today).days


def evaluate(f: DealFacts, today: date) -> Verdict:
    """Одна сделка → её срочность. Порядок проверок = приоритет причины."""

    # Терминальные из очереди выпадают: делать с ними нечего. Срыв — тоже исход,
    # а не проблема, требующая внимания сегодня.
    if f.is_terminal or f.is_lost:
        return Verdict(NORMAL)

    # 8 (ТЗ) — но проверяется ПЕРВЫМ. Стадия не отнесена к слою денег: сделка не
    # считается ни в одном слое, значит отчёты по ней врут. Раньше это правило стояло
    # последним, и сделка без стадии получала совет по документам («прикрепите УПД») —
    # а куда её вести, система не знает вовсе, и в очереди она садилась в группу
    # закрытия с пустым светофором. Сначала разобрать, советы потом.
    if f.money_layer is None:
        return Verdict(TODAY, "Стадия не отнесена к слою", "Разобрать", "stage_unmapped")

    start_in = _days_until(f.period_from, today)

    def start_phrase() -> str:
        """«через N дн.» для будущего старта и «прошёл N дн. назад» для пропущенного:
        «через -442 дн.» — то, как выглядит забытая нижняя граница окна."""
        return (f"Старт через {start_in} дн." if start_in >= 0
                else f"Старт прошёл {-start_in} дн. назад")

    # Окно правил 1-3: сделка ещё до запуска и старт в обозримом диапазоне.
    pre_launch = (f.stage_key in PRE_LAUNCH_KEYS and start_in is not None
                  and -STALE_START_DAYS <= start_in)

    # 1. Нет медиаплана, а старт близко (или уже пропущен).
    if pre_launch and not f.has_mp and start_in <= 5:
        return Verdict(OVERDUE, f"{start_phrase()}, МП не готов",
                       "Собрать МП", "deal_mp_missing", f.period_from)

    # 2a. МП отклонён — нужны правки. Раньше правила «не завизирован»: там ждут ответа,
    # а здесь ответ уже получен и он отрицательный. Ждать нечего, надо переделывать.
    if (pre_launch or f.stage_is_first) and f.mp_rejected:
        reason = (f"{start_phrase()}, МП отклонён — нужны правки" if start_in is not None
                  else "МП отклонён — нужны правки")
        return Verdict(OVERDUE, reason, "Переделать МП", "mp_rework", f.period_from)

    # 1a. МП собран конвейером годового плана и человеком ещё не смотрен. Сделка стоит
    # на первой стадии: отметка «Проверено» в конструкторе сама двинет её дальше.
    # Это не «ждём клиента» (mp_unapproved) — тут мяч у аккаунта, и дата старта не важна:
    # непроверенный автоплан нельзя отправлять клиенту в любом случае.
    # ПОСЛЕ правила об отказе: если план уже показали клиенту и он его забраковал,
    # советовать «посмотрите план» бессмысленно — его надо переделывать.
    if f.stage_is_first and f.has_mp:
        return Verdict(OVERDUE if (start_in is not None and start_in <= 5) else SOON,
                       "МП собран конвейером, не проверен",
                       "Проверить", "mp_verify", f.period_from)

    # 2. МП есть, но не завизирован клиентом, а старт совсем близко.
    if pre_launch and f.has_mp and f.mp_approved is False and start_in <= 3:
        return Verdict(OVERDUE, f"{start_phrase()}, МП не завизирован",
                       # НЕ mp_stuck: то событие про план, который висит у согласующих,
                       # и адресовано им. Это — про сделку, у которой горит старт,
                       # и адресовано аккаунту. Разные адресаты, разные тексты.
                       "Пингануть", "mp_unapproved", f.period_from)

    # Бронь под подтверждение: старт на горизонте, пора уходить на сбор запуска.
    # Ниже правил про МП: без плана подтверждать нечего.
    if f.stage_key == "booking" and start_in is not None and -STALE_START_DAYS <= start_in <= BOOKING_CONFIRM_DAYS:
        return Verdict(OVERDUE if start_in <= 5 else SOON,
                       f"{start_phrase()}, бронь не подтверждена",
                       "Подтвердить бронь", "booking_confirm", f.period_from)

    # 3 (ТЗ). «ДС не подписано» УБРАНО 2026-08-17: на живых данных файлов ДС в системе
    # ноль — доп. соглашения ведутся вне неё, — поэтому правило срабатывало на каждой
    # сделке в окне (26 сработок из 26 возможных) и означало не «ДС нет», а «мы этого
    # не знаем». Проверка вернётся, когда ДС начнут попадать в систему приложениями
    # (SalesAnnex), а не файлом. Факт has_ds ниже сохранён: он верен, просто пока
    # ничего не различает.

    # 4 (ТЗ). «Креативы не получены» здесь СОЗНАТЕЛЬНО не считается: согласование
    # креативов уезжает в модуль «Сбор запуска» с другой логикой (набор пропорций,
    # итерации, кабинеты паблишеров), и повторять здесь упрощённую проверку «файл есть»
    # значило бы завести второй источник правды, который потом придётся сносить.

    # 6. Период закрыт, закрывающие не выставлены больше 5 дней — И сделка уже на
    # документообороте. Раньше правило смотрело только на даты: сделке на «Броне» или
    # «В размещении» с закрытым периодом система советовала принести УПД (на живых
    # данных так вышло у 32 строк из 60). Стадии ДО опознаём по слою «фактические» —
    # это и есть признак «деньги закрываем». «Итоговая сверка» (реализуемые) исключена
    # намеренно: там финализируют цифры, документы собирают дальше.
    end_ago = _days_until(f.period_to, today)
    if (f.money_layer == "фактические" and f.period_to
            and end_ago is not None and end_ago < -5 and not f.has_closing_docs):
        # «Прикрепить документы», а не «Загрузить акт»: до автоматической генерации
        # закрывающих аккаунт вешает на сделку то, что есть (УПД, счёт, акт), и одна
        # конкретная бумага в подписи кнопки вводила бы в заблуждение.
        return Verdict(OVERDUE, f"Период закрыт {-end_ago} дн. назад, документов нет",
                       "Прикрепить документы", "act_missing", f.period_to)

    # 7. Срок оплаты прошёл, оплаты нет.
    due = payment_due(f)
    if due and f.is_paid is False:
        overdue_days = _days_until(due, today)
        if overdue_days is not None and overdue_days < 0:
            return Verdict(OVERDUE, f"Просрочка оплаты {-overdue_days} дн.",
                           "Открыть дебиторку", "payment_overdue", due)

    # 5. Стадия висит дольше SLA. Двойной SLA — уже просрочка.
    sla = sla_for(f)
    if sla and f.stage_since:
        stood = (today - f.stage_since).days
        if stood > sla * 2:
            return Verdict(OVERDUE, f"На стадии {stood} дн. (норма {sla})",
                           "Двинуть", "stage_stuck", f.stage_since)
        if stood > sla:
            return Verdict(SOON, f"На стадии {stood} дн. (норма {sla})",
                           "Двинуть", "stage_stuck", f.stage_since)

    # Дедлайн сегодня / на подходе — по ближайшей известной дате.
    for d in (f.period_from, f.period_to):
        left = _days_until(d, today)
        if left == 0:
            return Verdict(TODAY, "Дедлайн сегодня", due=d)
        if left is not None and 0 < left <= 3:
            return Verdict(SOON, f"Дедлайн через {left} дн.", due=d)

    return Verdict(NORMAL)


def queue_sort_key(v: Verdict):
    """Сортировка очереди: overdue → today → soon → normal, внутри — по дате дедлайна.
    Сделки без даты уходят в конец своей группы, а не в начало (date.max)."""
    return (URGENCY_ORDER.get(v.urgency, 9), v.due or date.max)
