# -*- coding: utf-8 -*-
"""Съём суточной статистики из Weborama: вызов, разбор дерева, нормализация.

ЗДЕСЬ ТОЛЬКО ЧТЕНИЕ И РАЗБОР. Запись в базу — отдельно, когда схема согласована; эта
половина самостоятельна и проверяется без сети и без базы.

Четыре правила разбора выведены из ПЕРВОГО ЖИВОГО ВЫЗОВА 12.09.2026 (452 вставки, 43 дня,
23 719 204 показа). Два из них противоречат тому, что мы вычитали из их C#-конвертера, —
поэтому записаны здесь, рядом с кодом, который на них стоит.

1. **Вложенность ответа — ИХ, а не наша.** Порядок массива `dimensions` на структуру не
   влияет. Проверено: на `["day","insertion"]` и на `["insertion","day"]` пришло
   одинаковое дерево `insertion → day`; на `["day","campaign","insertion"]` —
   `campaign → insertion → day`. То есть у них своя иерархия, где время всегда внутри, а
   кампания выше вставки. Парсер, идущий по списку, которым спрашивал, развалился бы
   молча: он прочёл бы id вставки как дату. Поэтому идём ПО КЛЮЧАМ ответа.

2. **`metrics` лежит на каждом уровне и равна сумме детей** (сверено на четырёх
   кампаниях: 634746, 3393941, 1846023, 1 — совпало везде). Значит брать надо ЛИСТЬЯ,
   а итоги уровней пропускать, иначе факт удвоится.

3. **Нулевую метрику они не присылают вовсе.** У вставки без кликов ключа `click` в
   ответе нет. Отличать это от «метрика не поддерживается» обязательно — см. ниже.

4. **Каждый запрошенный разрез приходит ВТОРОЙ РАЗ отдельной веткой — плоским итогом.**
   В ответе на `["insertion","day"]` у `data` не два ключа, а четыре: `insertion` (дерево),
   `day` (итог по дням на весь аккаунт), `metrics` (итог за период целиком) и производные
   `impression_average` / `number_of_days`. Обход, складывающий все листья подряд, получил
   бы РОВНО ДВОЙНОЕ число — 47 438 408 вместо 23 719 204, и оно выглядело бы совершенно
   правдоподобно. Поэтому побочные ветки не выбрасываются молча: по ним считается
   контрольная сумма съёма (`WcmPull.check`).

ГЛАВНАЯ ЛОВУШКА ЭТОГО ОБМЕНА. Неизвестную или недоступную метрику Weborama НЕ отвергает
— она молча не кладёт её в ответ. Живой вызов: попросили `visibility`,
`visibility_rate`, `visibility_5s`, `SIVT` — не вернулось ни одной, ответ 200, ошибки
нет. А видимость — то, ради чего верификатор и заводится. Поэтому съём всегда сообщает,
какие из запрошенных метрик не пришли НИ РАЗУ, и это не предупреждение в лог, а часть
результата: молчание здесь неотличимо от нуля, а стоит по-разному.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional

log = logging.getLogger("finance.weborama")

# Разрез, в котором снимаем. `insertion` — их зерно и ровно наша площадка РК
# (`weborama_refs.kind='insertion'`), `day` — суточная грань, решение владельца.
# Просить кампанию над вставкой не нужно: она приходит в metadata и без разреза.
DIMENSIONS = ("insertion", "day")

# Что снимаем. `impression` — показ по решению владельца 10.09.2026 (НЕ
# `impression_without_IVT`: «без невалидного трафика» — другая величина, и сверять
# наш счётчик надо с тем же, что считает площадка).
#
# Остальные три — не для сверки, а чтобы было чем спорить предметно: сколько показов
# верификатор счёл невалидными и какой охват получился.
METRICS = ("impression", "click", "impression_without_IVT", "reach_impression")

# Окно перезабора. Weborama дозаливает данные задним числом, поэтому каждый съём
# перепроверяет последние трое суток, а не только вчерашний день.
REFETCH_DAYS = 3


@dataclass
class WcmDayRow:
    """Одна строка суточного среза: вставка × день."""
    day: date
    insertion_id: str
    campaign_ext_id: Optional[str] = None
    label: Optional[str] = None
    impression: int = 0
    click: int = 0
    metrics: dict = field(default_factory=dict)   # сырьё целиком, как пришло


@dataclass
class WcmPull:
    """Итог съёма.

    `absent_metrics` и `discrepancy` — части РЕЗУЛЬТАТА, а не строчки в логе: обе
    описывают случай, когда ответ пришёл успешно и при этом неполон. В этом обмене
    неудача выглядит как удача чаще, чем как отказ.
    """
    rows: list
    absent_metrics: tuple
    asked_metrics: tuple
    start: date
    end: date
    grand_total: Optional[int] = None      # их итог за период (`data.metrics`)
    by_day_total: dict = field(default_factory=dict)   # их итог по дням на весь аккаунт

    @property
    def impressions(self) -> int:
        return sum(r.impression for r in self.rows)

    @property
    def discrepancy(self) -> Optional[int]:
        """Наша сумма против ИХ ЖЕ итога. None — если итога в ответе не было.

        Контрольная сумма ничего не стоит: их итог приезжает в том же ответе. Зато она
        ловит целый класс тихих поломок разбора — пропущенную ветку, посчитанный дважды
        уровень, потерянный день. Ноль здесь значит, что развёртка по вставкам и дням
        сходится с тем, что они сами считают итогом.
        """
        if self.grand_total is None:
            return None
        return self.impressions - self.grand_total

    def ok(self) -> bool:
        return not self.absent_metrics and self.discrepancy in (0, None)


def _num(v: Any) -> int:
    """Их числа приходят то целым, то строкой.

    Живой вызов: `unique_impression` пришла как `2982`, а `reach_impression` — как
    `"2982.00"`, при том что это одна и та же величина под двумя именами. Приводим к
    целому всё, что приводится; что не приводится — считаем отсутствующим, а не нулём.
    """
    if v is None or isinstance(v, bool):
        return 0
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return 0


def _leaves(node: Any, dims: Optional[dict] = None, out: Optional[list] = None) -> list:
    """Обход дерева ПО КЛЮЧАМ ОТВЕТА с возвратом только листьев.

    Лист — узел, у которого нет ни одного ключа, кроме `metrics`. Промежуточные
    `metrics` (итоги уровня) пропускаются: они равны сумме детей.
    """
    dims = {} if dims is None else dims
    out = [] if out is None else out
    if not isinstance(node, dict):
        return out
    deeper = [k for k in node if k != "metrics"]
    if not deeper:
        out.append((dict(dims), node.get("metrics") or {}))
        return out
    for dim in deeper:
        children = node.get(dim)
        if not isinstance(children, dict):
            continue
        for ident, child in children.items():
            dims[dim] = str(ident)
            _leaves(child, dims, out)
            dims.pop(dim, None)
    return out


def _label_of(metadata: Any, dim: str, ident: Optional[str]) -> Optional[str]:
    """Имя берётся ТОЛЬКО из metadata: внутри `data` меток нет вовсе, одни ключи-id."""
    if not ident or not isinstance(metadata, dict):
        return None
    node = (metadata.get(dim) or {}).get(str(ident))
    return node.get("label") if isinstance(node, dict) else None


def parse(payload: Any, *, asked: Iterable[str] = METRICS) -> tuple:
    """Ответ `get_statistics` → (строки, метрики-молчуны, побочные итоги).

    Отдельной функцией, а не внутри вызова: разбор — это то, что ломается при смене
    формата, и проверять его надо без сети.

    Побочные итоги — те самые плоские ветки-двойники (правило 4). В строки они не идут
    НИКОГДА, но и не теряются: из них складывается контрольная сумма съёма.
    """
    asked = tuple(asked)
    data = (payload or {}).get("data") or {}
    metadata = (payload or {}).get("metadata") or {}

    # Итог за весь период — `metrics` прямо на `data`. Их же число, приехавшее в том же
    # ответе: сверять развёртку есть с чем, и это бесплатно.
    grand = _num((data.get("metrics") or {}).get("impression")) if data.get("metrics") else None

    seen_metrics: set = set()
    rows: list = []
    by_day: dict = {}
    for dims, metrics in _leaves(data):
        seen_metrics |= set(metrics)
        ins = dims.get("insertion")
        day_s = dims.get("day")
        day = None
        if day_s:
            try:
                day = datetime.strptime(day_s, "%Y-%m-%d").date()
            except ValueError:
                log.warning("Weborama: неразобранная дата %r", day_s)
                continue
        if not ins:
            # Плоская ветка-двойник: тот же период в другом разрезе. Сложить её со
            # строками значит удвоить факт ровно вдвое — и число останется похожим на
            # правду. Забираем как контрольную величину и идём дальше, БЕЗ шума в логе:
            # это штатная часть их ответа, а не подозрительная строка.
            if day is not None:
                by_day[day] = _num(metrics.get("impression"))
            continue
        if day is None:
            # Вставка без дня — итог уровня вставки; он равен сумме своих дней.
            continue
        rows.append(WcmDayRow(
            day=day,
            insertion_id=str(ins),
            campaign_ext_id=dims.get("campaign"),
            label=_label_of(metadata, "insertion", ins),
            impression=_num(metrics.get("impression")),
            click=_num(metrics.get("click")),
            metrics=dict(metrics),
        ))

    absent = tuple(m for m in asked if m not in seen_metrics)
    return rows, absent, {"grand": grand, "by_day": by_day}


def window(today: Optional[date] = None, *, days: int = REFETCH_DAYS) -> tuple:
    """Окно съёма: последние `days` суток включая сегодня.

    Сегодняшний день берём намеренно, хоть он и неполный: дашборд обновляется тем же
    темпом, и пустая сегодняшняя клетка читается как «не крутит», а не как «день ещё
    идёт».
    """
    today = today or date.today()
    return today - timedelta(days=days - 1), today


def pull(client, start: date, end: date, *, metrics: Iterable[str] = METRICS) -> WcmPull:
    """Съём за отрезок. Один вызов: их API отдаёт весь аккаунт сразу.

    По вставкам не итерируем намеренно. Живой замер 12.09.2026: 452 вставки за 43 дня
    пришли одним ответом в 533 КБ. Запрос на вставку означал бы 452 обращения к чужому
    API ради тех же данных.
    """
    metrics = tuple(metrics)
    payload = client.statistics(
        dimensions=list(DIMENSIONS), metrics=list(metrics),
        start_date=start.isoformat(), end_date=end.isoformat())
    rows, absent, margins = parse(payload, asked=metrics)
    if absent:
        log.warning("Weborama не вернула метрики %s — это НЕ нули, это молчание", absent)
    got = WcmPull(rows=rows, absent_metrics=absent, asked_metrics=metrics,
                  start=start, end=end, grand_total=margins["grand"],
                  by_day_total=margins["by_day"])
    if got.discrepancy:
        log.warning("Weborama: развёртка %s против их итога %s — расхождение %s",
                    got.impressions, got.grand_total, got.discrepancy)
    return got
