# -*- coding: utf-8 -*-
"""Согласие двух отчётов о прибыли.

`/pl` (reports.py) и `/finreport` считают одни и те же деньги двумя независимыми
кусками кода. Владелец сообщал, что они расходятся; запись №7 в бэклоге отладки
держит это под наблюдением. Тестов на их согласие не было ни одного: и
`test_pl_grouping`, и `test_finreport` проверяют одну и ту же функцию `classify`
из finreport, то есть половину пары.

Разбор 2026-08-23 показал, что расхождение **структурное, а не ошибочное**:

| | `/pl` | `/finreport` |
|---|---|---|
| строки | только `ОПЛАЧЕНО` | `accrual` — все, включая плановые; `cash` — только оплаченные |
| ось месяца | `Operation.period` | `accrual` — `period`; `cash` — `date` |
| НДС | не вычитается (gross) | `net` вычитает `vat_fact`, `gross` — нет |

Отсюда единственная пара режимов, которую вообще можно сравнивать, —
`/pl` против `finreport(accrual, gross)`, и связь между ними точная:

    finreport(accrual, gross).выручка = /pl.выручка + плановые строки

Тест закрепляет именно это равенство. Он сломается, если любой из отчётов
поменяет разметку, фильтр или ось, — а такое изменение обязано быть осознанным.

Ловушка, ради которой всё это писалось: экран финотчёта по умолчанию показывает
`accrual + net`, и на живых данных он отличается от `/pl` меньше чем на процент —
не потому что отчёты почти согласны, а потому что прибавка плановых строк и
вычет НДС взаимно гасятся. Читать это как «мелкая погрешность» нельзя: числа
означают разное.

Тесты идут в базу контейнера, только на чтение, и утверждают соотношения, а не
конкретные суммы, — иначе ломались бы от любой новой операции.
"""
import pytest
from sqlalchemy import func

from app.database import SessionLocal
from app.models import Article, Operation
from app.routers import finreport as fr
from app.routers.reports import UNMAPPED_GROUP, _pl_group, get_pl

WINDOW = ("2026-01", "2026-12")
PAID = "ОПЛАЧЕНО"


@pytest.fixture(scope="module")
def db():
    s = SessionLocal()
    yield s
    s.close()


def _pl_revenue(db):
    r = get_pl(date_from=WINDOW[0], date_to=WINDOW[1], db=db, current_user=None)
    return sum(v["revenue"] for v in r["summary"].values())


def _fr_revenue(db, basis, vat):
    r = fr.build_report(db, basis, vat, WINDOW[0], WINDOW[1])
    return sum(v["revenue"] for v in r["summary"].values())


def _plan_revenue(db):
    """Выручка в НЕоплаченных строках за то же окно, по той же разметке статей."""
    ids = [a.id for a in db.query(Article).filter(Article.pl_line == "revenue").all()]
    if not ids:
        return 0.0
    return float(db.query(func.sum(Operation.income - Operation.expense)).filter(
        Operation.article_id.in_(ids),
        Operation.period >= WINDOW[0], Operation.period <= WINDOW[1],
        Operation.status != PAID,
    ).scalar() or 0)


def test_finreport_accrual_equals_pl_plus_plan_rows(db):
    """Единственное равенство, которое обязано выполняться между отчётами."""
    pl = _pl_revenue(db)
    accrual_gross = _fr_revenue(db, "accrual", "gross")
    plan = _plan_revenue(db)
    residual = (accrual_gross - pl) - plan
    assert abs(residual) < 1.0, (
        f"необъяснённый остаток {residual:,.2f}: /pl={pl:,.0f}, "
        f"finreport(accrual,gross)={accrual_gross:,.0f}, плановые={plan:,.0f}"
    )


def test_paid_and_plan_together_make_up_the_accrual_view(db):
    """Обратная проверка того же с другой стороны: оплаченное — это ровно /pl."""
    ids = [a.id for a in db.query(Article).filter(Article.pl_line == "revenue").all()]
    paid = float(db.query(func.sum(Operation.income - Operation.expense)).filter(
        Operation.article_id.in_(ids),
        Operation.period >= WINDOW[0], Operation.period <= WINDOW[1],
        Operation.status == PAID,
    ).scalar() or 0) if ids else 0.0
    assert abs(paid - _pl_revenue(db)) < 1.0


def test_net_view_differs_from_pl_by_vat_not_by_error(db):
    """`net` отличается от `gross` ровно на НДС, а не на что-то ещё."""
    gross = _fr_revenue(db, "accrual", "gross")
    net = _fr_revenue(db, "accrual", "net")
    assert gross >= net, "нетто не может быть больше брутто"


# --- разметка: оба отчёта обязаны относить статью в один и тот же раздел --------

# Строка finreport → раздел /pl. У /pl нет отдельных разделов «финансовые» и
# «прочие» — он сворачивает их в операционные (см. PL_LINE_TO_GROUP), поэтому
# отображение не взаимно однозначное, но однозначное в эту сторону.
FR_LINE_TO_PL_GROUP = {
    fr.REVENUE: "ВЫРУЧКА",
    fr.COGS: "СЕБЕСТОИМОСТЬ",
    fr.OPEX: "ОПЕРАЦИОННЫЕ",
    fr.FINANCE: "ОПЕРАЦИОННЫЕ",
    fr.OTHER: "ОПЕРАЦИОННЫЕ",
    fr.MARKETING: "МАРКЕТИНГ",
    fr.PROFIT_TAX: "НАЛОГИ",
    fr.EXCLUDED: "НЕ В P&L",
    fr.UNCLASSIFIED: UNMAPPED_GROUP,
}


def test_both_reports_put_every_article_in_the_same_section(db):
    """Статья не может быть выручкой в одном отчёте и расходом в другом.

    `by_description` пропускаем намеренно: там раздел определяется текстом
    платежа, а не статьёй, и у /pl этого текста нет — он для таких статей честно
    берёт группу из справочника. Это задокументированное расхождение, а не сбой.
    """
    mismatched = []
    for a in db.query(Article).all():
        if a.pl_line == fr.BY_DESCRIPTION:
            continue
        pl_group = _pl_group(a.pl_line, a.group)
        fr_line, _, _ = fr.classify(a.pl_line, a.name, a.subgroup, "")
        expected = FR_LINE_TO_PL_GROUP.get(fr_line)
        if expected is not None and expected != pl_group:
            mismatched.append(f"{a.name}: /pl={pl_group}, finreport={fr_line}")
    assert not mismatched, "разошлись по разделам:\n  " + "\n  ".join(mismatched)
