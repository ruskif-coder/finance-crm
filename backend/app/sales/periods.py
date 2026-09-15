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


def end_is_stale(period_from, period_to) -> bool:
    """Конец размещения РАНЬШЕ старта — значит он протух и описывает прошлую жизнь сделки.

    Такого размещения не бывает: это всегда след переноса кампании, при котором доехала
    только половина (старт новый, конец старый). На 15.09.2026 таких сделок 32.

    Отдельной функцией, а не сравнением по месту: по этому признаку принимают решение
    три разных кода — отбор по периоду в реестре, правка периода поштучно и пачкой, —
    и разъехаться им нельзя.
    """
    return bool(period_from and period_to and period_to < period_from)


def month_key(day) -> str | None:
    """Календарный месяц даты как «ГГГГ-ММ». None для пустой даты.

    Не `strftime("%Y-%m")`: на годе меньше тысячи он печатает «25-12» вместо «0025-12».
    Такие даты в базе есть — их заводят руками в Битриксе (встречен конец РК «0025-12-24»),
    — и двузначный год читается как нормальный, из-за чего строка выглядит стоящей не на
    своём месте в сортировке, хотя сортировка верна: она идёт по дате, а не по подписи.
    """
    return f"{day.year:04d}-{day.month:02d}" if day else None


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
