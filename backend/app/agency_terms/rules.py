# -*- coding: utf-8 -*-
"""Подбор правила СК — конструктор «Агентских условий» (владелец 27.10.2026, схема — docs/СХЕМА_СК.md).

Правило — набор необязательных признаков (договор, агентство, рекламодатель, бренд, услуга). Сделке подходит правило, чьи
ЗАДАННЫЕ признаки с ней совпадают; побеждает правило с наибольшим числом признаков: «чем больше условий задано — тем точнее
расчёт». Два одинаково точных правила, подходящих одной сделке в один период, хранить нельзя — `conflict` отказывает при
сохранении, иначе процент решался бы порядком строк.

Основная СК — одна на сделку. Партнёрская — отдельная выплата: самое точное правило подбирается для КАЖДОГО получателя.
Функции чистые: правила и признаки сделки — словари, база не нужна."""
import calendar
import re
from datetime import date
from typing import List, Optional

FEATURES = ("contract_id", "agency_id", "advertiser_id", "brand_id", "service_id")
KINDS = MAIN, PARTNER = ("основная", "партнёрская")
MODES = POSTPAY, DISCOUNT = ("постоплата", "скидка в счёт")


class RuleError(ValueError):
    """Правило ввести нельзя; текст — человеку."""


def _set(rule: dict) -> dict:
    return {k: rule[k] for k in FEATURES if rule.get(k) is not None}


def specificity(rule: dict) -> int:
    return len(_set(rule))


def active(rule: dict, on: date) -> bool:
    return rule["valid_from"] <= on and (rule.get("valid_to") is None or on <= rule["valid_to"])


def _direct(rule: dict) -> bool:
    """Основная СК рекламодателя без агентства — «прямой договор»: только для сделок без агентства (27.10.2026). Иначе у
    сделки агентства (у неё есть и рекламодатель) спорили бы поровну правило агентства и правило рекламодателя."""
    return rule.get("kind") == MAIN and rule.get("agency_id") is None and rule.get("advertiser_id") is not None


def matches(rule: dict, deal: dict) -> bool:
    if _direct(rule) and deal.get("agency_id") is not None:
        return False
    return all(deal.get(k) == v for k, v in _set(rule).items())


def _best(cands: List[dict]) -> Optional[dict]:
    # Ничья по точности не возникает: `conflict` не даёт её сохранить; id — только чтобы порядок был устойчивым.
    return max(cands, key=lambda r: (specificity(r), r.get("id") or 0)) if cands else None


def pick(rules: List[dict], deal: dict, on: date, kind: str) -> Optional[dict]:
    """Самое точное действующее правило вида `kind`, подходящее сделке; нет — None («условие не задано»)."""
    return _best([r for r in rules if r["kind"] == kind and active(r, on) and matches(r, deal)])


def pick_partners(rules: List[dict], deal: dict, on: date) -> List[dict]:
    """Партнёрская — по самому точному правилу на КАЖДОГО получателя."""
    by: dict = {}
    for r in rules:
        if r["kind"] == PARTNER and active(r, on) and matches(r, deal):
            by.setdefault(r["recipient_id"], []).append(r)
    return [_best(rs) for _rid, rs in sorted(by.items())]


def _overlap(a: dict, b: dict) -> bool:
    end_a, end_b = a.get("valid_to") or date.max, b.get("valid_to") or date.max
    return a["valid_from"] <= end_b and b["valid_from"] <= end_a


def _compatible(a: dict, b: dict) -> bool:
    """Найдётся ли сделка, которой подходят оба: ни один признак не задан в них по-разному."""
    if (_direct(a) and b.get("agency_id") is not None) or (_direct(b) and a.get("agency_id") is not None):
        return False                        # прямой договор и сделка агентства не встречаются в одной сделке
    sa, sb = _set(a), _set(b)
    return all(sb[k] == v for k, v in sa.items() if k in sb)


def conflict(rule: dict, others: List[dict]) -> Optional[dict]:
    """Правило, с которым `rule` спорило бы за одну сделку: тот же вид (и получатель у партнёрской), та же точность,
    совместимые признаки, пересекающиеся периоды. None — спора нет."""
    for o in others:
        if o.get("id") is not None and o.get("id") == rule.get("id"):
            continue
        if o["kind"] != rule["kind"] or (rule["kind"] == PARTNER and o.get("recipient_id") != rule.get("recipient_id")):
            continue
        if specificity(o) == specificity(rule) and _compatible(o, rule) and _overlap(o, rule):
            return o
    return None


def validate(rule: dict) -> None:
    """Отказ с объяснением, ЧТО поправить. CHECK в базе держит то же — здесь человеку понятный текст."""
    if rule.get("kind") not in KINDS:
        raise RuleError(f"Вид СК — {' или '.join(KINDS)}")
    if rule.get("mode") not in MODES:
        raise RuleError(f"Способ — {' или '.join(MODES)}")
    pct = rule.get("percent")
    if pct is None or not (0 <= float(pct) <= 100):
        raise RuleError("Процент СК — от 0 до 100")
    if not rule.get("valid_from"):
        raise RuleError("Укажите, с какой даты действует условие")
    if rule.get("valid_to") and rule["valid_to"] < rule["valid_from"]:
        raise RuleError("Дата окончания раньше даты начала")
    if rule["kind"] == MAIN:
        if rule.get("contract_id") is None:
            raise RuleError("Основная СК задаётся по договору — выберите договор")
        if rule.get("agency_id") is None and rule.get("advertiser_id") is None:
            raise RuleError("Основная СК — в связке с договором: выберите агентство или рекламодатель (прямой договор)")
    else:
        if rule.get("recipient_id") is None:
            raise RuleError("Партнёрская СК — отдельная выплата: выберите получателя")
        if not _set(rule):
            raise RuleError("Партнёрской СК нужен хотя бы один признак: рекламодатель, бренд, агентство, договор или услуга")


def close_date(period: str) -> date:
    """Дата, на которую берётся условие: момент закрытия месяца — его последний день (владелец 27.10.2026). Правило «по
    31.10» действует для октября, даже если месяц закрывают в ноябре."""
    y, m = int(period[:4]), int(period[5:7])
    return date(y, m, calendar.monthrange(y, m)[1])


def months_of(period: str) -> List[str]:
    """`YYYY-MM` → [он сам]; `YYYY-Q1..Q4` → три месяца квартала. Иное — RuleError."""
    m = re.fullmatch(r"(\d{4})-(\d{2})", period or "")
    if m and 1 <= int(m.group(2)) <= 12:
        return [period]
    from app.periods import parse_quarter        # кварталы в проекте разбирает один модуль (tests/test_periods.py)
    q = parse_quarter(period) if period and "Q" in period else None
    if q:
        year, n = q
        first = (n - 1) * 3 + 1
        return [f"{year}-{first + i:02d}" for i in range(3)]
    raise RuleError("Период — месяц YYYY-MM или квартал YYYY-Q1…Q4")
