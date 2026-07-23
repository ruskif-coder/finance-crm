"""
Разбивка периода размещения по календарным месяцам.

Умолчание размещения — календарный месяц. Размещение шире месяца разносится
равными долями, тем же приёмом, что квартал в reports.py::expand_quarter_rows.
Одна логика на систему, не вторая параллельная.

Арифметика ведётся в Decimal, хотя в БД суммы хранятся как double precision
(однородность с operations): плавающие копейки рождаются в вычислениях,
а не в хранении, и в расчётах премий недопустимы.
"""
from decimal import Decimal, ROUND_DOWN


def _months_between(start, end) -> list[str]:
    keys = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        keys.append(f"{y:04d}-{m:02d}")
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return keys


def split_amount_by_months(period_from, period_to, amount) -> list[tuple[str, Decimal]]:
    """Делит сумму поровну между календарными месяцами периода.

    Остаток от округления отдаётся последнему месяцу: сумма долей обязана
    совпадать с исходной суммой до копейки, иначе агрегаты расходятся
    и выручка «усыхает» при каждой группировке.

    period_to = None означает «календарный месяц period_from» — умолчание
    для размещений, у которых в Битриксе нет явной даты окончания.
    """
    if period_from is None:
        raise ValueError("period_from обязателен")
    if period_to is None:
        period_to = period_from
    if period_to < period_from:
        raise ValueError("period_to не может быть раньше period_from")

    amount = Decimal(amount)
    keys = _months_between(period_from, period_to)
    n = len(keys)

    share = (amount / n).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    shares = [share] * n
    shares[-1] = amount - share * (n - 1)
    return list(zip(keys, shares))
