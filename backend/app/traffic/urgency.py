"""Срочность пары «креатив × площадка» — одна чистая функция на очередь и на сканер.

Пишется сразу такой, хотя уведомлений трафика ещё нет: иначе через месяц появится вторая
копия правил, и «горит» на экране перестанет совпадать с «горит» в письме. Ровно это уже
случилось у аккаунта, и разбиралось потом.

Зерно другое, чем у сделки: строка очереди — ПАРА, а не сделка. Один баннер на восьми
площадках это восемь единиц работы, и семь из них могут быть в порядке.

Функция не знает про SQLAlchemy и не ходит в базу: на входе готовые факты, на выходе
вердикт. Сборка фактов живёт в роутере, комбинации дат покрываются тестами без фикстур
(backend/tests/test_traffic_urgency.py).
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional

# Уровни по убыванию — те же имена, что у аккаунта (app/sales/urgency.py). Совпадение
# не косметическое: очереди рисуются одним компонентом, и третий словарь уровней в
# проекте означал бы третий набор цветов светофора.
OVERDUE, TODAY, SOON, NORMAL = "overdue", "today", "soon", "normal"
URGENCY_ORDER = {OVERDUE: 0, TODAY: 1, SOON: 2, NORMAL: 3}

# За сколько дней до старта размещения непроверенный материал становится «на сегодня».
# Два дня — из правила уведомлений владельца: «старт через 2 дня, размещение не проверено».
START_SOON_DAYS = 2

# Сколько пара может ждать ответа, прежде чем это станет заметно. Три дня, как у
# «кто молчит третий день» в согласовании площадок: правило то же, просто адресат другой.
STALE_DAYS = 3


@dataclass
class PairFacts:
    """Факты о паре на момент расчёта. Ни одно поле не вычисляется внутри."""
    # Проверка трафика: None — «спросили, ответа нет». Это НЕ то же, что «не спрашивали»:
    # у непосланной пары строки проверки вообще нет, и в очередь она не попадает.
    traffic_verdict: Optional[str] = None      # None | ок | на переделку
    asked_at: Optional[date] = None            # когда материал попал в очередь
    period_from: Optional[date] = None         # старт размещения у этой площадки
    # Площадка выпала из кампании (отказ) или получателя сняли — работы по ней нет,
    # но строка может доживать в выдаче до перезагрузки экрана.
    is_dropped: bool = False


@dataclass
class Verdict:
    urgency: str
    reason: str = ""            # человеческая формулировка, одной фразой, без точки
    cta: str = ""               # подпись кнопки действия; пусто — действия нет
    kind: str = ""              # ключ события для уведомлений
    due: Optional[date] = None  # по ней сортируется очередь внутри группы


def evaluate(f: PairFacts, today: date) -> Verdict:
    """Одна пара → её срочность. Порядок проверок = приоритет причины."""

    # Работы нет: ответ уже дан либо площадка выпала. «На переделку» тоже закрывает
    # строку для трафика — дальше ход аккаунта, он собирает новую итерацию.
    if f.is_dropped or f.traffic_verdict is not None:
        return Verdict(NORMAL)

    days_to_start = None if f.period_from is None else (f.period_from - today).days

    # Старт УЖЕ прошёл, а материал не проверен. Самое срочное, что здесь бывает:
    # площадка не получила баннер, которому полагалось стоять со вчерашнего дня.
    if days_to_start is not None and days_to_start < 0:
        return Verdict(OVERDUE,
                       reason=f"старт был {-days_to_start} дн. назад, материал не проверен",
                       cta="Проверить", kind="traffic_pair_start_passed",
                       due=f.period_from)

    # Старт вот-вот. Проверить нужно сегодня, иначе площадка не успеет разместить.
    if days_to_start is not None and days_to_start <= START_SOON_DAYS:
        when = "сегодня" if days_to_start == 0 else f"через {days_to_start} дн."
        return Verdict(TODAY, reason=f"старт {when}, материал не проверен",
                       cta="Проверить", kind="traffic_pair_start_soon",
                       due=f.period_from)

    # Просто висит. Дата старта тут ни при чём — материал может ждать месяц до запуска,
    # и это всё равно незакрытая работа.
    waiting = None if f.asked_at is None else (today - f.asked_at).days
    if waiting is not None and waiting >= STALE_DAYS:
        return Verdict(SOON, reason=f"ждёт проверки {waiting} дн.",
                       cta="Проверить", kind="traffic_pair_stale", due=f.asked_at)

    return Verdict(NORMAL, reason="ждёт проверки", cta="Проверить", due=f.period_from)
