"""Флайт РК и всё, что из него следует: темп, прогноз, недокрут, пересчёт плана.

Перенос расчётов дизайн-хендоффа на сервер (решение владельца 04.09.2026: «числа даёт
сервер, фронт их рисует»). Оригинал — `docs/handoff_traffic_dashboard/code/
TrafficDashboard.jsx`, разделы 3–5; он же остаётся спецификацией, если формулы
придётся сверять.

**Флайт, а не календарный месяц.** Темп считается от `date_start`/`date_end` кампании:
РК со стартом 16-го числа на 12-й день месяца ещё не начиналась, и красить её красным
не за что. Обратное тоже верно — РК с флайтом 1–12 на 12-й день уже закончилась, и
«нужно в день» у неё не существует: недокрут закрывается сверкой.

В хендоффе флайт задан НОМЕРАМИ ДНЕЙ внутри месяца (`flight: [16, 30]`, опорный день
`TODAY = 12`) — это упрощение макета. Здесь он от настоящих дат: РК живут не в пределах
месяца, и на границе года номера дней перестали бы сравниваться вовсе.

Функции чистые и в базу не ходят: так их можно проверить на десятках комбинаций дат
без фикстур (`tests/test_ad_flight.py`).

СЛОВАРЬ, который легко перепутать, поэтому имена разведены:

  · `pace`         — ОЖИДАЕМАЯ доля выполнения (0…1) = отчитано дней ÷ длина флайта;
  · `speed`        — фактический темп В ПОКАЗАХ в день = факт ÷ отчитанные дни;
  · `need_per_day` — сколько нужно в день на остаток, чтобы закрыть план.

До 04.09.2026 в ответе дашборда поле `pace` означало ВТОРОЕ. Совпадение имён при разной
единице измерения — самая дорогая ошибка в этом файле, поэтому старое имя не переиспользовано.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, List, Optional, Sequence

from app.bidder.rules import capped_shares, floor_to_fact  # noqa: F401,E402 — реэкспорт

# ── статусы площадки в РК ────────────────────────────────────────────────────
#
# Шесть значений (владелец 04.09.2026). Первые три СТАВИТ КОНВЕЙЕР согласования
# креативов — руками они не выбираются: «у кого сейчас мяч» это следствие вердиктов,
# а не решение. Слова взяты те же, что в очереди трафика (`AssemblyCreatives.rowStatus`),
# чтобы одно состояние не называлось на двух экранах по-разному.
# «Ждёт сборки» добавлено 18.09.2026 по замеру владельца: площадка, попавшая в РК
# кандидатом, показывалась как «у трафика» — то есть будто мяч у нас и работа идёт. На
# деле по ней ещё нет ни одного креатива: сборка не закончена, отправлять нечего.
# Разница не косметическая: «у трафика» ставит площадку в очередь работы, и трафик ищет
# у себя задачу, которой нет.
PLACEMENT_CHAIN = ("ждёт сборки", "у трафика", "у площадки", "ждёт запуска")
PLACEMENT_MANUAL = ("запущен", "пауза", "завершена")
PLACEMENT_STATUSES = PLACEMENT_CHAIN + PLACEMENT_MANUAL

# ДВА РАЗНЫХ набора, и путать их дорого (владелец 04.09.2026):
#
#   · `PLACEMENT_RUNNING` — кто крутит ПРЯМО СЕЙЧАС. По нему считается «крутит N из M»
#     и красятся пипсы;
#   · `PLACEMENT_IN_PLAN` — кто участвует в РАСПРЕДЕЛЕНИИ объёма. Пауза сюда входит:
#     «пауза — приостановка открутки, из суточного плана площадка НЕ исключается».
#     Её доля сохраняется за ней, иначе снятие паузы означало бы новую раскладку и
#     каждая пауза перекраивала бы план всей РК.
#
# Отключение («завершена») — единственное, что выводит площадку из раскладки: объём
# уходит остальным. В DSP отключение уезжает НЕМЕДЛЕННО (`is_checked = false`),
# а перераспределение объёма действует со следующего суточного плана.
PLACEMENT_RUNNING = ("запущен",)
PLACEMENT_IN_PLAN = ("запущен", "пауза")

# УДЕРЖАНИЕ ДОЛЕЙ (владелец 27.09.2026): до старта РК и первые `HOLD_DAYS` дней флайта
# объём делят ВСЕ площадки в работе — от «ждёт сборки» до «запущен» и «пауза», выпадает
# только «завершена». Трафик видит объём каждой площадки до запуска, и креативы уезжают
# в DSP с лимитом. С шестого дня — «перерасчёт по факту запущенного»: делят только
# `PLACEMENT_IN_PLAN`. Раньше делили только запущенные с первого дня, и до запуска у
# всех 1506 площадок прода объём был пуст.
HOLD_DAYS = 5
PLACEMENT_IN_WORK = PLACEMENT_CHAIN + PLACEMENT_IN_PLAN

# Отдельные значения ИМЕНАМИ. Набор жил здесь и раньше, а его члены набирались строкой в
# каждом потребителе: «ждёт запуска» встречалось литералом в трёх местах роутера плюс
# перевод в сборке. Русские строки сравниваются буквально — опечатка не падает, она тихо
# перестаёт совпадать, и площадка навсегда выпадает из счётчика.
PLACEMENT_WAIT = PLACEMENT_CHAIN[0]       # «ждёт сборки» — креативов по ней ещё нет
PLACEMENT_NEW = PLACEMENT_CHAIN[1]        # «у трафика» — материал отправлен, мяч у нас
PLACEMENT_AT_SITE = PLACEMENT_CHAIN[2]    # «у площадки» — ждём её вердикта
PLACEMENT_READY = PLACEMENT_CHAIN[3]      # «ждёт запуска» — согласована, не включена
PLACEMENT_OFF = PLACEMENT_MANUAL[2]       # «завершена» — выведена из раскладки

# ── статусы РК ───────────────────────────────────────────────────────────────
#
# Семь значений жизненного цикла. Делятся так же, как у площадки и креатива, только
# «конвейер» здесь — это состояние САМОЙ РК: её план, площадки и креативы.
#
#   · ВЫЧИСЛЯЕМЫЕ — «ожидает сборки» → «готова» → «запущена». Их не выбирают: они
#     следствие того, что происходит этажами ниже;
#   · РУЧНЫЕ — пауза, остановлена, окончена, архив. Это решения человека, и вывести их
#     не из чего: остановить идущую РК может только тот, кто решил её остановить.
#
# До 04.09.2026 статус был просто хранимым полем без всякой автоматики: синк ставил
# «ожидает сборки» при создании и больше его не трогал. То есть РК оставалась в нём
# навсегда, и «запущена» на экране означало только то, что кто-то написал это руками.
CAMPAIGN_DERIVED = ("ожидает сборки", "готова", "запущена")
CAMPAIGN_MANUAL = ("пауза", "остановлена", "окончена", "архив")
CAMPAIGN_STATUSES = CAMPAIGN_DERIVED + CAMPAIGN_MANUAL


def campaign_chain_status(has_plan: bool, placements: int, running: int,
                          can_start: bool) -> str:
    """Состояние РК по тому, что под ней. Порядок разбора — от самого сильного признака.

    «Запущена» — это ФАКТ работы, а не намерение: хоть одна площадка крутит. «Готова» —
    всё для запуска есть (план, площадки, согласованный креатив), но никто не запущен.
    Иначе — «ожидает сборки».

    Проверка `can_start` та же, что запирает запуск отдельной площадки: без согласованного
    креатива РК не готова, сколько бы площадок к ней ни подключили.
    """
    if running:
        return "запущена"
    if has_plan and placements and can_start:
        return "готова"
    return "ожидает сборки"


def effective_campaign_status(stored: Optional[str], chain: str) -> str:
    """Ручное решение перекрывает расчёт — иначе поставленную на паузу РК тут же
    возвращало бы в «запущена» первой же площадкой, которая продолжает крутить."""
    return stored if stored in CAMPAIGN_MANUAL else chain


# ── статусы креатива ─────────────────────────────────────────────────────────
#
# Устроены так же, как у площадки (владелец 04.09.2026: «кнопки те же и логика та же»):
# первые три ставит конвейер согласования, последние три — трафик. Креатив принадлежит
# ПЛОЩАДКЕ (уникальность `ad_campaign_creative` по паре «площадка × номер»), поэтому один
# и тот же баннер на двух площадках — две единицы учёта со своим ЕРИД и своим хешом в МС.
CREATIVE_CHAIN = ("у трафика", "у площадки", "согласован")
CREATIVE_REJECTED = "отклонён"
CREATIVE_MANUAL = ("запущен", "пауза", CREATIVE_REJECTED)
CREATIVE_STATUSES = CREATIVE_CHAIN + CREATIVE_MANUAL

CREATIVE_RUNNING = ("запущен",)
CREATIVE_IN_PLAN = ("запущен", "пауза")   # пауза долю сохраняет — как у площадки
# Удержание у креативов то же, что у площадок: делят все, кроме отклонённого.
CREATIVE_IN_WORK = CREATIVE_CHAIN + CREATIVE_IN_PLAN
# После удержания делят креативы, готовые крутиться: согласованный, запущенный, на паузе.
# «Запущен» у креатива ставится только руками трафика — запуск площадки его не
# переключает, и согласованный креатив запущенной площадки уже крутится в DSP. Считай
# мы долю только у «запущен», с шестого дня у обычной РК доля креативов была бы пустой и
# в DSP уходили бы креативы без лимита (ревью 27.09.2026).
CREATIVE_SHARES = ("согласован",) + CREATIVE_IN_PLAN


@dataclass(frozen=True)
class Flight:
    """Окно РК в днях. `done` — сколько дней уже отчитано, `left` — сколько осталось."""
    date_from: date
    date_to: date
    length: int
    done: int

    @property
    def left(self) -> int:
        return max(0, self.length - self.done)

    @property
    def pace(self) -> float:
        """Ожидаемая доля выполнения: 0 до старта, 1 после финиша."""
        return (self.done / self.length) if self.length else 0.0

    @property
    def is_over(self) -> bool:
        return self.done >= self.length


def flight_of(date_start: Optional[date], date_end: Optional[date],
              today: Optional[date] = None) -> Optional[Flight]:
    """Флайт РК. Без дат или с перевёрнутым окном — None, а не «ноль дней».

    Разница существенная: None означает «срок неизвестен» и гасит весь расчёт, а нулевая
    длина означала бы «РК длиной в ноль дней» и делила бы на ноль там, где данных просто нет.
    """
    if not (date_start and date_end) or date_end < date_start:
        return None
    today = today or date.today()
    length = (date_end - date_start).days + 1
    done = (min(date_end, today) - date_start).days + 1
    return Flight(date_start, date_end, length, max(0, min(done, length)))


def holds(fl: Optional[Flight]) -> bool:
    """Держат ли долю площадки, ещё не запущенные: до старта и первые `HOLD_DAYS` дней.

    Без дат — да: предварительное распределение лучше пустого, а флайт ещё не задан."""
    return fl is None or fl.done <= HOLD_DAYS


def forecast_of(plan: Optional[float], fact: Optional[float],
                fl: Optional[Flight]) -> Optional[float]:
    """Линейный прогноз на конец флайта: факт ÷ отчитанные дни × длину флайта.

    Ни одного дня не отчитано (РК ещё не стартовала) — прогноза нет: делить не на что,
    и «ноль» здесь соврал бы про недокрут в размере всего плана.
    """
    if fl is None or not plan or fact is None or not fl.done:
        return None
    return fact / fl.done * fl.length


def under_of(plan: Optional[float], forecast: Optional[float]) -> Optional[float]:
    """Недокрут = план − прогноз, но не меньше нуля. Перекрут недокрутом не считается."""
    if forecast is None or not plan:
        return None
    return max(0.0, plan - forecast)


def need_per_day(plan: Optional[float], fact: Optional[float],
                 fl: Optional[Flight]) -> Optional[float]:
    """Сколько нужно в день на остаток флайта, чтобы закрыть план.

    У закончившегося флайта остатка нет — возвращаем None, а не ноль: «нужно 0 в день»
    читается как «всё в порядке», хотя недокрут при этом может быть любым.
    """
    if fl is None or not plan or fact is None or not fl.left:
        return None
    return max(0.0, plan - fact) / fl.left


def progress(plan: Optional[float], fact: Optional[float],
             date_start: Optional[date], date_end: Optional[date],
             today: Optional[date] = None, now: Optional[date] = None) -> dict:
    """Полный расчёт строки РК одним вызовом — то, что уходит в ответ дашборда.

    `today` — дата среза статистики (по ней темп и прогноз), `now` — календарный день:
    «до старта» считается от него, иначе РК, стартовавшая сегодня, весь день «стартует
    через 1 день» (ревью 02.10.2026).

    Все ключи присутствуют ВСЕГДА; отсутствие данных — это None, а не пропуск ключа:
    фронт рисует прочерк по None, а по пропуску ключа рисовал бы `undefined`.
    """
    fl = flight_of(date_start, date_end, today)
    fc = forecast_of(plan, fact, fl)
    speed = (fact / fl.done) if (fl and fl.done and fact is not None) else None
    # Сколько дней ДО СТАРТА. У нестартовавшей РК «осталось N дней» означает длину всего
    # флайта и читается как «идёт и вот-вот кончится» — а она ещё не начиналась. Пока
    # старт впереди, осмысленно только это число (04.09.2026).
    ref = now or today or date.today()
    to_start = ((date_start - ref).days
                if (date_start and fl and not fl.done and date_start > ref) else None)
    return {
        "days_total": fl.length if fl else None,
        "days_to_start": to_start,
        "days_done": fl.done if fl else None,
        "days_left": fl.left if fl else None,
        "pace": round(fl.pace, 4) if fl else None,
        "flight_over": fl.is_over if fl else None,
        "forecast": round(fc) if fc is not None else None,
        "under": round(under_of(plan, fc)) if fc is not None else None,
        "done_pct": round(fact / plan * 100, 1) if (plan and fact is not None) else None,
        "speed": round(speed) if speed is not None else None,
        "need_per_day": (lambda n: round(n) if n is not None else None)(
            need_per_day(plan, fact, fl)),
    }


# ── распределение объёма по площадкам ────────────────────────────────────────

@dataclass(frozen=True)
class _Layout:
    """Итог первого шага раскладки: кто что держит и как делится остаток плана РК.

    Разбито из одной функции `distribute` 07.10.2026 (сложность была 62): расчёт «кто в плане и
    сколько у кого зафиксировано» отдельно от сборки строки по каждой площадке. Поведение прежнее —
    его держат тесты (`tests/test_ad_flight.py`) и дифференциальная проверка со старой версией."""
    settle: bool            # раскладка по факту: факт передан И удержание долей кончилось
    in_plan_set: tuple      # какие статусы участвуют в плане (в удержание — все «в работе»)
    fixed_of: dict          # id(строки) -> заданный объём (после поправки на факт)
    dropped: dict           # id(строки) -> объём выбывшей площадки (= её факт)
    rest: float             # остаток плана РК после заданных объёмов и выбывших
    w_sum: float            # сумма весов живых площадок
    w_of: dict              # id(строки) -> доля остатка


def _fixed_volumes(placements: Sequence[dict], fact_of: dict, settle: bool) -> dict:
    """Заданный по креативам объём площадки; при раскладке по факту — не ниже факта."""
    fixed_of = {id(p): float(p.get("fixed") or 0) for p in placements}
    if settle:   # заданный объём не ниже факта
        fixed_of = {k: (max(v, fact_of[k]) if v else 0.0) for k, v in fixed_of.items()}
    return fixed_of


def _dropped_volumes(placements: Sequence[dict], fact_of: dict, fixed_of: dict,
                     in_plan_set: tuple, settle: bool) -> dict:
    """Вне раскладки (выбыла, нет веса), но уже открутила — держит план = свой факт."""
    return {id(p): fact_of[id(p)] for p in placements
            if settle and fact_of[id(p)] and not fixed_of[id(p)]
            and (p.get("status") not in in_plan_set or not p.get("weight"))}


def _shares_of_rest(live: Sequence[dict], plan: Optional[float], rest: float, cap: Optional[float],
                    settle: bool, fact_of: dict) -> dict:
    """Доли остатка по весам живых площадок с потолком; по факту — через `floor_to_fact`.

    Потолок — от ПЛАНА РК, а делится остаток после заданных объёмов: переводим предел в доли
    остатка. Площадка с ручным индексом (`capless`) потолку не подчиняется."""
    cap_rest = (cap * float(plan) / rest) if (cap and plan and rest) else cap
    capless = frozenset(id(p) for p in live if p.get("capless"))
    if settle and rest:
        amt = floor_to_fact(rest, {id(p): p["weight"] for p in live}, fact_of,
                            (cap * float(plan)) if cap else None, capless)
        return {k: v / rest for k, v in amt.items()}
    return capped_shares({id(p): p["weight"] for p in live}, cap_rest, capless)


def _layout(plan: Optional[float], fl: Optional[Flight], placements: Sequence[dict],
            cap: Optional[float], facts: Optional[dict], hold_fl: Optional[Flight]) -> _Layout:
    hold = holds(hold_fl if hold_fl is not None else fl)
    settle = facts is not None and not hold
    fact_of = {id(p): float((facts or {}).get(p.get("id")) or 0) for p in placements}
    in_plan_set = PLACEMENT_IN_WORK if hold else PLACEMENT_IN_PLAN
    fixed_of = _fixed_volumes(placements, fact_of, settle)
    dropped = _dropped_volumes(placements, fact_of, fixed_of, in_plan_set, settle)
    fixed_in = sum(v for p in placements for v in [fixed_of[id(p)]]
                   if v and p.get("status") in in_plan_set)
    rest = max(0.0, float(plan) - fixed_in - sum(dropped.values())) if plan else 0.0
    live = [p for p in placements
            if p.get("status") in in_plan_set and p.get("weight") and not fixed_of[id(p)]
            and id(p) not in dropped]
    w_sum = sum(float(p["weight"]) for p in live) or 0.0
    w_of = _shares_of_rest(live, plan, rest, cap, settle, fact_of)
    return _Layout(settle, in_plan_set, fixed_of, dropped, rest, w_sum, w_of)


def _plan_and_share(p: dict, lay: _Layout, plan: Optional[float], use_stored: bool,
                    in_plan: bool, no_weight: bool, fixed: float):
    """План (показы) и доля одной площадки: записанные ночью / выбывшая / заданный объём / по весам."""
    if use_stored:
        p_plan = round(p["plan_stored"]) if p.get("plan_stored") else None
        return p_plan, float(p.get("share_stored") or 0.0)
    if id(p) in lay.dropped:
        return round(lay.dropped[id(p)]), ((lay.dropped[id(p)] / plan) if plan else 0.0)
    if fixed:
        return round(fixed), ((fixed / plan) if plan else 0.0)
    w_share = lay.w_of.get(id(p), 0.0) if (in_plan and not no_weight and lay.w_sum) else 0.0
    p_plan = round(lay.rest * w_share) if (lay.rest and w_share) else None
    # Без плана РК доля — по весам, как до объёмов: её показывают дашборд и
    # карточка, и `recompute_shares` пишет её в площадку.
    return p_plan, ((lay.rest * w_share / plan) if plan else w_share)


def _placement_row(p: dict, lay: _Layout, plan: Optional[float], fl: Optional[Flight],
                   use_stored: bool) -> dict:
    running = p.get("status") in PLACEMENT_RUNNING
    in_plan = p.get("status") in lay.in_plan_set
    no_weight = not p.get("weight")
    fixed = lay.fixed_of[id(p)] if in_plan else 0.0
    p_plan, share = _plan_and_share(p, lay, plan, use_stored, in_plan, no_weight, fixed)
    # Факт площадки приходит из среза с разрезом по placement_id. Пока среза нет,
    # вызывающий передаёт None — и здесь ничего не выдумывается: пропорция от факта
    # РК была бы правдоподобным числом, за которым не стоит ни одного замера.
    p_fact = p.get("fact")
    p_fc = forecast_of(p_plan, p_fact, fl)
    return {
        **p,
        "share": round(share, 6),
        "plan_show": p_plan,
        "fact_shows": p_fact,
        "done_pct": round(p_fact / p_plan * 100, 1) if (p_plan and p_fact is not None) else None,
        "forecast": round(p_fc) if p_fc is not None else None,
        "under": round(under_of(p_plan, p_fc)) if p_fc is not None else None,
        "no_weight": no_weight,
        "running": running,
        "in_plan": in_plan,
        # Заданный объём — для подсветки на дашборде: «эта площадка на фиксе».
        "fixed": round(fixed) if fixed else None,
        # Выбыла и держит план = свой факт (правило 05.10.2026).
        "settled": id(p) in lay.dropped,
    }


def distribute(plan: Optional[float], fact: Optional[float], fl: Optional[Flight],
               placements: Sequence[dict], cap: Optional[float] = None,
               facts: Optional[dict] = None, hold_fl: Optional[Flight] = None,
               use_stored: bool = False) -> dict:
    """Доли, планы и прогнозы площадок РК.

    Доля = вес площадки ÷ сумма весов тех, кто УЧАСТВУЕТ В ПЛАНЕ: в удержание (`holds`,
    до старта и первые пять дней) — все площадки в работе, дальше — запущенные И на
    паузе. Отключили площадку — доля пересчитывается по оставшимся; нет веса (не заведён индекс в балансировщике) — доля 0, и это отдельный
    признак `no_weight`, а не «выключена»: площадка подключена, просто не участвует
    в раскладке.

    Доля — план-ориентир. Физически по дням раскладывает пейсер DSP
    (`uniform_pro`), наш рычаг — ставка source и вкл/выкл.

    `share_sum` возвращается наружу, чтобы экран мог показать недобор: сумма меньше
    единицы означает, что часть объёма стоит на площадках без индекса или выключенных.

    ЗАДАННЫЙ ОБЪЁМ (`fixed`, владелец 25.09.2026): площадка в плане с объёмом, заданным
    по её креативам в блоке креатива, получает РОВНО его; остаток плана РК делится по
    весам между остальными. Выключенная площадка объём не держит — он возвращается в
    остаток, как и её доля. Превысить план ввод не даёт (проверка при вводе), но и тут
    остаток не уходит в минус.

    ФАКТ (`facts` = {id площадки: показов с начала РК}, владелец 05.10.2026, правила —
    `app/bidder/rules`). Учитывается после удержания долей и только если передан
    (статистики за вчера нет — вызывающий передаёт None, и раскладка идёт по весам):
    выбывшая («завершена») площадка держит план = своему факту, остальным уходит только
    неоткрученное; план площадки в раскладке не ниже её факта. Пауза держит долю.
    Ревью 05.10.2026: то же для площадки, открутившей и потерявшей вес (снят индекс), и
    для заданного объёма ниже факта.

    `hold_fl` — флайт для решения «идёт ли удержание»: дашборды считают темп на дату среза
    (вчера), а удержание обязано решаться на ту же дату, что у ночного пересчёта (сегодня),
    иначе на стыке 5-го и 6-го дня экран и DSP расходятся на сутки. Не передан — `fl`.

    `use_stored` (владелец 05.10.2026): план и доля площадки — ЗАПИСАННЫЕ ночным пересчётом
    (`plan_stored` / `share_stored` в строке), а не посчитанные заново. Экраны показывают
    ровно то, что ушло лимитами в DSP; прогноз и недокрут считаются от этого плана.
    """
    lay = _layout(plan, fl, placements, cap, facts, hold_fl)
    rows = [_placement_row(p, lay, plan, fl, use_stored) for p in placements]
    return {"rows": rows, "share_sum": round(sum(r["share"] for r in rows), 6),
            # Учтён ли факт на самом деле: передан И удержание долей кончилось.
            "by_fact": lay.settle}


def split_evenly(total, creatives, hold: bool = False):
    """План площадки → поровну между работающими креативами.

    `hold` — удержание (`holds(флайт)`): до старта и первые пять дней РК делят все
    креативы, кроме отклонённого, дальше — согласованные, запущенные и на паузе
    (`CREATIVE_SHARES`).

    «Объём площадки от веса делится РАВНОМЕРНО по работающим креативам» (владелец
    04.09.2026): креативы равнозначны, весов у них нет.

    Остаток от деления отдаётся ПЕРВЫМ по номеру, а не теряется: 1000 на троих это
    334/333/333, и сумма планов креативов сходится с планом площадки. Потерянная
    единица выглядит безобидно ровно до сверки, где не сходится итог.

    Неработающий креатив получает None, а не ноль: ноль означал бы «ему запланировали
    ноль показов», а ему не планировали ничего.
    """
    rows = sorted(creatives, key=lambda c: (c.get("creative_no") or 0, c.get("id") or 0))
    in_plan_set = CREATIVE_IN_WORK if hold else CREATIVE_SHARES
    live = [c for c in rows if c.get("status") in in_plan_set]
    out = []
    if total and live:
        # Креатив с заданным объёмом получает его, остаток площадки — поровну остальным
        # (владелец 25.09.2026).
        fixed = {id(c): int(round(c.get("fixed") or 0)) for c in live}
        free = [c for c in live if not fixed[id(c)]]
        left = max(0, int(round(total)) - sum(fixed.values()))
        base, rest = divmod(left, len(free)) if free else (0, 0)
        free_ids = {id(c) for c in free}
        live_ids = {id(c) for c in live}
        given = 0
        for c in rows:
            if id(c) in live_ids and id(c) not in free_ids:
                out.append({**c, "plan_show": fixed[id(c)],
                            "share": round(fixed[id(c)] / total, 6), "in_plan": True,
                            "running": c.get("status") in CREATIVE_RUNNING})
            elif id(c) in free_ids:
                val = base + (1 if given < rest else 0)
                out.append({**c, "plan_show": val,
                            "share": round(val / total, 6), "in_plan": True,
                            "running": c.get("status") in CREATIVE_RUNNING})
                given += 1
            else:
                out.append({**c, "plan_show": None, "share": 0.0, "in_plan": False,
                            "running": False})
        return out
    for c in rows:
        out.append({**c, "plan_show": None, "share": 0.0,
                    "in_plan": c.get("status") in in_plan_set,
                    "running": c.get("status") in CREATIVE_RUNNING})
    return out


def creative_counts(creatives):
    """Счётчик в строке площадки: всего / согласовано / запущено.

    «Согласовано» — ОДОБРЕНО ПЛОЩАДКОЙ (владелец 04.09.2026), то есть пара сошлась;
    «запущено» — креатив ЕСТЬ В КАБИНЕТЕ DSP, признак `ms_creative_xxhash`.
    Второе не выводится из первого: согласованный креатив может ещё не уехать в DSP, и
    показывать его запущенным значило бы обещать открутку, которой нет.

    СПИСОК ПЕРЕЧИСЛЕН, а не задан отрицанием. Раньше согласованным считалось всё, что не
    «у трафика» и не «у площадки», — то есть в это число попадал и ОТКЛОНЁННЫЙ креатив.
    Пока разница была только в подписи, она почти не мешала; с 14.09.2026 по зазору
    «согласовано минус запущено» красится индикатор площадки, и отклонённый навсегда
    держал бы её оранжевой — тревога, которую нечем снять. Заодно новый статус теперь не
    станет «согласованным» молча, просто оттого что его забыли внести в исключения.
    """
    agreed_statuses = CREATIVE_SHARES
    return {
        "total": len(creatives),
        "agreed": sum(1 for c in creatives if c.get("status") in agreed_statuses),
        "live": sum(1 for c in creatives if c.get("ms_creative_xxhash")),
    }


# ── динамика показов по дням ─────────────────────────────────────────────────

GRAIN_DAYS = {"day": 1, "week": 7}


def daily_buckets(plan: Optional[float], fact: Optional[float], fl: Optional[Flight],
                  facts_by_day: dict, grain: str = "day",
                  date_from: Optional[date] = None,
                  date_to: Optional[date] = None,
                  today: Optional[date] = None) -> Optional[dict]:
    """Столбцы графика «план против факта» с пересчётом плана на остаток.

    Правило пересчёта (требование брифа): прошедшие дни держат ИСХОДНЫЙ план — их уже
    не переиграть, — а будущие получают `(план − факт) ÷ остаток дней`. Такой столбец
    помечается `repaced`, чтобы подпись честно говорила, что план пересчитан.

    Интервал всегда КЛИПУЕТСЯ К ФЛАЙТУ: столбцов не может быть больше, чем дней в РК.
    """
    if fl is None or not plan:
        return None
    today = today or date.today()
    step = GRAIN_DAYS.get(grain, 1)

    lo = max(fl.date_from, date_from) if date_from else fl.date_from
    hi = min(fl.date_to, date_to) if date_to else fl.date_to
    if hi < lo:
        return None

    per_day = plan / fl.length
    # Факта ещё нет («нет данных», а не ноль) — для плана на остаток это ноль показов:
    # иначе `need` пустой, и в первый день запуска все будущие столбцы рисовались с
    # планом 0 — «план не рисуется до конца размещения» (владелец 01.10.2026, 54ZYCH).
    need = need_per_day(plan, fact if fact is not None else 0, fl) or 0.0

    buckets = []
    start = lo
    while start <= hi:
        end = min(hi, start + timedelta(days=step - 1))
        size = (end - start).days + 1
        past = sum(1 for i in range(size) if start + timedelta(days=i) <= today)
        shows = sum(facts_by_day.get(start + timedelta(days=i), (0, 0))[0] for i in range(size))
        clicks = sum(facts_by_day.get(start + timedelta(days=i), (0, 0))[1] for i in range(size))
        if past == size:
            plan_sum = size * per_day          # целиком прошедший столбец — исходный план
            repaced = False
        else:
            plan_sum = past * per_day + (size - past) * need
            repaced = True
        buckets.append({
            "date_from": start, "date_to": end, "days": size, "days_past": past,
            "plan": round(plan_sum), "shows": shows, "clicks": clicks,
            "repaced": repaced,
        })
        start = end + timedelta(days=1)

    return {
        "buckets": buckets,
        "grain": grain,
        "need_per_day": round(need) if fl.left else None,
        "days_left": fl.left,
        "speed": round(fact / fl.done) if (fl.done and fact is not None) else None,
    }


# ── недокрут по площадкам поперёк РК (виджет «Площадки-виновники») ───────────

def culprits(campaign_rows: Iterable[dict], limit: int = 30) -> List[dict]:
    """Сводка недокрута по площадке поперёк ВСЕХ переданных РК.

    Виджета нет в спеке модуля — он выведен из §5: доля площадки считается в каждой РК
    отдельно, поэтому «кто тянет вниз весь портфель» иначе видно только если раскрыть
    каждую РК и сложить в голове.

    На вход — уже посчитанные строки площадок (`distribute().rows`) с добавленным
    `publisher_id`/`domain`. Функция ничего не считает заново: два места, считающие
    недокрут по-своему, разошлись бы на первой же правке порогов.

    `limit` здесь — потолок ОТВЕТА, а не то, что видно: виджет показывает первые десять
    и дальше скроллит (владелец 04.09.2026). Обрезать до видимого значило бы не пускать
    в скролл ничего, а `share` считается от суммы отданных строк — при обрезке по
    видимому доля одиннадцатой площадки просто исчезала бы из знаменателя.
    """
    by_pub: dict = {}
    for row in campaign_rows:
        under = row.get("under")
        if not under:
            continue
        key = row.get("publisher_id") or row.get("domain")
        acc = by_pub.setdefault(key, {
            "publisher_id": row.get("publisher_id"), "domain": row.get("domain"),
            "code": row.get("code"), "campaigns": 0, "under": 0.0, "statuses": set(),
        })
        acc["campaigns"] += 1
        acc["under"] += float(under)
        acc["statuses"].add(row.get("status"))

    out = sorted(by_pub.values(), key=lambda a: -a["under"])[:limit]
    total = sum(a["under"] for a in out) or 1.0
    for a in out:
        a["under"] = round(a["under"])
        a["share"] = round(a["under"] / total, 4)
        # Одна площадка в разных РК бывает в разных статусах — тогда честнее сказать
        # «частично», чем выбрать один из них и выдать за общий.
        a["status"] = next(iter(a["statuses"])) if len(a["statuses"]) == 1 else "частично"
        a.pop("statuses")
    return out


# ── статус площадки из конвейера согласования ────────────────────────────────

def chain_status(traffic_verdict: Optional[str], platform_verdict: Optional[str],
                 has_pair: bool) -> str:
    """У кого мяч — по вердиктам пары «креатив × площадка».

    Первые три статуса площадки НЕ выбираются руками (владелец 04.09.2026): это
    следствие конвейера, а не решение. Порядок разбора повторяет разворот цепочки
    28.08.2026 — сначала трафик, потом площадка:

      · пары нет вовсе        → «у трафика»: материал никому не отправляли;
      · пара есть, трафик молчит → «у трафика»;
      · трафик ответил, площадка молчит → «у площадки»;
      · ответили оба          → «ждёт запуска».

    Отказ и «на переделку» сюда НЕ приводят: работа возвращается в сборку, и площадка
    снова ждёт материала — то есть мяч опять у трафика.
    """
    if not has_pair or not traffic_verdict or traffic_verdict != "ок":
        return "у трафика"
    if platform_verdict != "ок":
        return "у площадки"
    return "ждёт запуска"


# Порядок продвинутости состояний: чем дальше, тем ближе к запуску.
_CHAIN_RANK = {"ждёт сборки": 0, "у трафика": 1, "у площадки": 2, "ждёт запуска": 3}


def as_placement_scale(creative_status: str) -> str:
    """Статус КРЕАТИВА в шкалу ПЛОЩАДКИ. Словари различаются одним словом: у креатива
    согласованное состояние зовётся «согласован», у площадки — «ждёт запуска».

    Вынесено из `routers/traffic_dashboard` 17.09.2026: тем же переводом пользуется
    синк, и вторая копия разошлась бы с первой ровно в том месте, где это дороже всего.
    """
    return PLACEMENT_READY if creative_status == "согласован" else creative_status


def best_chain_status(statuses):
    """Статус площадки по ВСЕМ её креативам — самый продвинутый из них.

    «Площадка запущена только при хоть одном согласованном креативе» (владелец
    04.09.2026). Отсюда и агрегат: одна согласованная пара уже делает площадку готовой
    к запуску, а остальные креативы могут ещё ходить по кругу правок.

    Брать ПОСЛЕДНЮЮ пару, как делалось до 04.09.2026, теперь нельзя: у площадки их
    столько же, сколько креативов, и свежая переделка одного баннера откатывала бы
    в «у трафика» площадку, которая уже крутит другой.
    """
    ranks = [_CHAIN_RANK.get(x, 0) for x in statuses]
    if not ranks:
        # НИ ОДНОГО КРЕАТИВА — значит сборка ещё идёт, а не «мяч у трафика»
        # (владелец 18.09.2026). Пустой список раньше давал «у трафика», и площадка,
        # по которой ничего не отправляли, звала трафик к несуществующей задаче.
        return PLACEMENT_WAIT
    top = max(ranks)
    return next(k for k, v in _CHAIN_RANK.items() if v == top)


def can_start_placement(creative_statuses):
    """Можно ли запускать площадку: нужен ХОТЬ ОДИН согласованный креатив.

    Правило владельца 04.09.2026. Запрет живёт на сервере, а не только серой кнопкой:
    спрятанная кнопка возвращается первым же рефакторингом, а запущенная площадка без
    согласованного материала — это показ несогласованного баннера.
    """
    # «Отклонён» — тоже не согласованный: до 28.09.2026 он проходил проверку, и площадку,
    # у которой креатив отозван или заменён, можно было запустить без материала.
    return any(x not in ("у трафика", "у площадки", "отклонён") for x in creative_statuses)


def effective_status_creative(stored: Optional[str], chain: str) -> str:
    """То же правило, что у площадки, но со словарём креатива.

    Ручной статус трафика перекрывает конвейер: иначе запущенный креатив возвращался бы
    в «согласован» при каждом синке.
    """
    return stored if stored in CREATIVE_MANUAL else chain


def effective_status(stored: Optional[str], chain: str) -> str:
    """Что показать: ручной статус перекрывает цепочку, иначе считаем по ней.

    Как только трафик нажал «запущен», конвейер перестаёт управлять строкой — иначе
    запущенная площадка возвращалась бы в «ждёт запуска» при каждом чтении.
    """
    return stored if stored in PLACEMENT_MANUAL else chain


def screens_tone(got: int, total: int) -> dict:
    """Скрины запуска «сняты из скольких» → индикатор «С» (владелец 01.10.2026): серый — ни
    по одному, жёлтый — по части, зелёный — по всем. Одно правило для дашборда трафика,
    карточки сделки и матрицы согласований."""
    state = "none" if not got else "all" if got == total else "part"
    return {"state": state, "got": got, "total": total}
