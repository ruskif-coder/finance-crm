r"""
Нормализация значений, приходящих из Битрикс24.

ИНН из выгрузок и API приходит как float — "1673005251.0" или в научной нотации.
Очистка регуляркой \D по такой строке даёт лишнюю цифру в конце и молча ломает
сопоставление с counterparties (0 совпадений, без ошибки). Поэтому десятичная
форма разбирается явно через Decimal, до всякой очистки.

См. docs/INTEGRATION_SPEC.md раздел 7 — ловушка проверена на реальном файле выгрузки.
"""
import re
from decimal import Decimal, InvalidOperation

_VALID_INN_LENGTHS = (10, 12)


def normalize_inn(raw) -> str | None:
    """Приводит ИНН к строке из 10 или 12 цифр.

    Возвращает None, если значение отсутствует или не похоже на ИНН — вызывающий код
    обязан обработать None, а не подставлять пустую строку в поиск: пустая строка
    в LIKE-запросе даёт ложные совпадения."""
    if raw is None:
        return None

    s = str(raw).strip()
    if not s:
        return None

    # Десятичная или научная форма ("1673005251.0", "5.00100732259e+11") —
    # разбираем как число, иначе потеряем или добавим цифру.
    if "." in s or "e" in s.lower():
        try:
            digits = format(Decimal(s), "f")
        except (InvalidOperation, ValueError):
            digits = s
        digits = digits.split(".")[0]
        digits = re.sub(r"\D", "", digits)
    else:
        digits = re.sub(r"\D", "", s)

    if len(digits) not in _VALID_INN_LENGTHS:
        return None
    return digits


def normalize_name(raw) -> str:
    """Схлопывает регистр и повторяющиеся пробелы.

    Используется для сопоставления услуг и брендов со справочником: в исходных данных
    одна и та же услуга встречается как "web", "in-app", "inapp", "in app"."""
    if raw is None:
        return ""
    return re.sub(r"\s+", " ", str(raw).strip()).lower()
