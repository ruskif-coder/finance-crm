# -*- coding: utf-8 -*-
"""Денежные правила сверки, раскладки мастер-сделки и ДС — в одном месте (внешний аудит 2.7.0, пп. 2.3–2.5).

* Строки базовой услуги масштабируются под сумму сверки так, что складываются в неё РОВНО: каждая округляется до копейки,
  остаток копеек забирает последняя. Без этого сумма строк ДС (её документ пишет прописью) расходилась с подтверждённой
  суммой в 81 % пакетов на 1–11 копеек.
* НДС — по строкам, как в счёте-фактуре и УПД (владелец 22.10.2026): НДС строки округляется «половина вверх», НДС документа —
  сумма НДС строк. Раньше сверка считала от итога, раскладка — от суммы группы, ДС — по строкам: три ответа на один вопрос.
Арифметика — десятичная: двоичная дробь и допуски «±полкопейки» здесь не нужны."""
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, List, Optional

_CENT = Decimal("0.01")


def dec(v) -> Decimal:
    return Decimal(str(v or 0))


def r2(v) -> float:
    """Округление до копейки «половина вверх» — для сумм, уходящих на экран и в документ."""
    return float(dec(v).quantize(_CENT, rounding=ROUND_HALF_UP))


def scale_to(amounts: List[float], target: float) -> List[float]:
    """Строки, пропорциональные `amounts`, в сумме ровно `target`; остаток копеек — последней строке."""
    total = sum(dec(a) for a in amounts)
    if not amounts or total == 0:
        return [0.0 for _ in amounts]
    t = dec(target)
    out = [(dec(a) * t / total).quantize(_CENT, rounding=ROUND_HALF_UP) for a in amounts[:-1]]
    out.append(t - sum(out, Decimal(0)))
    return [float(x) for x in out]


def line_vat(net, rate_pct: Optional[float]) -> float:
    """НДС строки: стоимость без НДС × ставка, «половина вверх» до копейки."""
    if not rate_pct or not net:
        return 0.0
    return float((dec(net) * dec(rate_pct) / 100).quantize(_CENT, rounding=ROUND_HALF_UP))


def doc_vat(nets: Iterable[float], rate_pct: Optional[float]) -> float:
    """НДС документа — сумма НДС его строк."""
    return float(sum((dec(line_vat(n, rate_pct)) for n in nets), Decimal(0)))
