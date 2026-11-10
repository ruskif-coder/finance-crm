"""Сводка плана оплат: «К оплате», статьи, крупнейшие получатели, что дозаполнить, деньги на сегодня.

Хендофф «План оплат · виджеты сводки» (02.11.2026). Считается здесь, а не на экране: сводка — по ВСЕМУ плану, а
таблица под ней листается страницами. Каждый блок отдаёт `ids` своих строк — клик по блоку фильтрует таблицу ровно
этими операциями (ручка списка операций умеет `ids`), второго расчёта того же условия на экране нет.

Расчёт — чистые функции над готовыми строками: их зовёт прибор с числами, посчитанными руками.
"""
import re
from datetime import date
from typing import Optional

from app import periods

# Заглушка вместо контрагента: строку завели «на будущее», кому платить — ещё не известно. В топ и в дубли не идёт.
STUB = "ПЛАН"
CASH = "Наличные"

_YEAR = re.compile(r"(20\d\d)")


def _is_stub(row) -> bool:
    return (row.get("counterparty") or "").strip().upper() == STUB


def _year(period: Optional[str]) -> Optional[int]:
    m = _YEAR.search(period or "")
    return int(m.group(1)) if m else None


def _ages(rows, year):
    """Год плана против хвостов прошлых лет — по ПЕРИОДУ строки: дата оплаты у плана обычно ещё не стоит."""
    old = [r for r in rows if (_year(r["period"]) or year) < year]
    cur = [r for r in rows if r not in old]
    years = sorted({_year(r["period"]) for r in old})
    old_label = f"хвосты {years[0]} года" if len(years) == 1 else "хвосты прошлых лет"
    out = [{"key": "cur", "label": f"{year} год", "sum": sum(r["sum"] for r in cur), "ids": [r["id"] for r in cur]}]
    if old:
        out.append({"key": "old", "label": old_label, "sum": sum(r["sum"] for r in old), "ids": [r["id"] for r in old]})
    return out


def _articles(rows, total):
    by = {}
    for r in rows:
        by.setdefault(r["article"] or "Без статьи", []).append(r)
    out = [{"name": k, "sum": sum(x["sum"] for x in v), "count": len(v), "ids": [x["id"] for x in v]}
           for k, v in by.items()]
    for a in out:
        a["pct"] = round(a["sum"] / total * 100) if total else 0
    return sorted(out, key=lambda a: -a["sum"])


def _top(rows, limit=5):
    by = {}
    for r in rows:
        if not _is_stub(r) and r["counterparty_id"]:
            by.setdefault(r["counterparty_id"], []).append(r)
    out = [{"counterparty_id": k, "name": v[0]["counterparty"], "sum": sum(x["sum"] for x in v), "count": len(v),
            "periods": sorted({x["period"] for x in v if x["period"]}, key=_period_key),
            "ids": [x["id"] for x in v]} for k, v in by.items()]
    return sorted(out, key=lambda t: -t["sum"])[:limit]


def _period_key(p):
    """«Q2 2025» и «2025-04» в одном порядке: год, потом месяц (квартал — его первый месяц). Квартал разбирает
    единственный парсер проекта (`app/periods.py`), своей регулярки здесь нет."""
    yq = periods.parse_quarter(p)
    if yq:
        return yq[0], yq[1] * 3 - 2
    m = re.match(r"^(\d{4})-(\d\d)$", p or "")
    return (int(m.group(1)), int(m.group(2))) if m else (_year(p) or 0, 0)


def _tags(rows, done):
    """«уже списано?» — проведённая операция с тем же контрагентом и той же суммой; «проверить» — у контрагента по той
    же статье две строки плана и больше. Первое важнее: оно означает возможную двойную оплату."""
    paid = {}
    for o in done:
        paid.setdefault((o["counterparty_id"], round(o["sum"], 2)), []).append(o)
    tags = {}
    for r in rows:
        if _is_stub(r) or not r["counterparty_id"]:
            continue
        hit = paid.get((r["counterparty_id"], round(r["sum"], 2)))
        if hit:
            o = max(hit, key=lambda x: x["date"] or date.min)
            when = o["date"].strftime("%d.%m.%y") if o["date"] else "без даты"
            tags[r["id"]] = {"kind": "done", "text": f"уже списано {when} · {o['bank'] or 'банк не указан'}"}
            continue
        same = [x for x in rows if x["counterparty_id"] == r["counterparty_id"] and x["article"] == r["article"]]
        if len(same) > 1:
            tags[r["id"]] = {"kind": "twin", "text": f"{len(same)} платежа одному контрагенту: "
                                                     + ", ".join(sorted((x["period"] or "—" for x in same),
                                                                        key=_period_key))}
    return tags


PINS = (
    ("dup", "Возможные дубли", "bad", "Совпадает с проведённой операцией или повторяется у контрагента"),
    ("nodate", "Нет даты оплаты", "warn", "Платёж не встанет в календарь — дату нужно поставить"),
    ("nobank", "Не выбран банк", "warn", "Непонятно, с какого счёта платить"),
    ("noinv", "Нет счёта", "warn", "Платить не по чему — запросить счёт у контрагента"),
    ("stub", "Контрагент «ПЛАН»", "bad", "Заглушка вместо контрагента"),
)


def _pins(rows, tags):
    test = {"dup": lambda r: r["id"] in tags, "nodate": lambda r: not r["date"],
            "nobank": lambda r: not r["bank"], "noinv": lambda r: not (r["invoice"] or "").strip(),
            "stub": _is_stub}
    out = []
    for key, label, tone, title in PINS:
        ids = [r["id"] for r in rows if test[key](r)]
        if ids:
            out.append({"key": key, "label": label, "tone": tone, "title": title, "count": len(ids), "ids": ids})
    return out


def summarize(rows, done, year):
    """Сводка по строкам плана. `rows` — строки плана, `done` — проведённые списания тех же контрагентов."""
    total = sum(r["sum"] for r in rows)
    tags = _tags(rows, done)
    return {
        "total": total, "count": len(rows),
        "counterparties": len({r["counterparty_id"] for r in rows if r["counterparty_id"] and not _is_stub(r)}),
        "ages": _ages(rows, year), "articles": _articles(rows, total), "top": _top(rows),
        "pins": _pins(rows, tags), "tags": tags,
        # Строки с заглушкой — для подсветки в таблице: признак «ПЛАН» решает сервер, экран его не повторяет.
        "stub_ids": [r["id"] for r in rows if _is_stub(r)],
    }


def _gap(have, need):
    """Знак не пишется — его несёт подпись «не хватает / остаётся»."""
    d = round(have - need, 2)
    return {"short": d < 0, "value": abs(d)}


def money(banks, credit_lines, total):
    """Деньги на сегодня против плана. `banks` — остатки ДДС по банкам (наличные — тоже строкой), `credit_lines` —
    активные кредитные линии. Кредит — свободный остаток лимита, а не лимит."""
    bank_sum = sum(b["balance"] for b in banks if b["bank"] != CASH)
    cash = sum(b["balance"] for b in banks if b["bank"] == CASH)
    credit = None
    if credit_lines:
        credit = {"free": sum(c["limit_amount"] - c["used_amount"] for c in credit_lines),
                  "limit": sum(c["limit_amount"] for c in credit_lines),
                  "banks": sorted({c["bank"] for c in credit_lines})}
    own = bank_sum + cash
    return {"banks": bank_sum, "bank_count": sum(1 for b in banks if b["bank"] != CASH), "cash": cash,
            "credit": credit, "own": _gap(own, total),
            "with_credit": _gap(own + credit["free"], total) if credit else None}


# ── загрузка из базы ────────────────────────────────────────────────────────────────────────────────────────────────


def _plan_rows(db):
    from app import operation_chains
    from app.models import Article, Counterparty, Operation
    q = (db.query(Operation.id, Operation.expense, Operation.bank, Operation.period, Article.name,
                  Operation.counterparty_id, Counterparty.name, Operation.invoice, Operation.date)
         .outerjoin(Article, Article.id == Operation.article_id)
         .outerjoin(Counterparty, Counterparty.id == Operation.counterparty_id)
         .filter(Operation.pay_plan_at.isnot(None), Operation.status != operation_chains.PAID))
    return [{"id": i, "sum": e or 0, "bank": b, "period": p, "article": a, "counterparty_id": c, "counterparty": cn,
             "invoice": inv, "date": d} for i, e, b, p, a, c, cn, inv, d in q.all()]


def _done(db, cp_ids):
    from app import operation_chains
    from app.models import Operation
    if not cp_ids:
        return []
    q = (db.query(Operation.counterparty_id, Operation.expense, Operation.date, Operation.bank)
         .filter(Operation.status == operation_chains.PAID, Operation.counterparty_id.in_(cp_ids),
                 Operation.expense > 0))
    return [{"counterparty_id": c, "sum": e, "date": d, "bank": b} for c, e, d, b in q.all()]


def _credit_lines(db):
    from app.credit_lines import used_of
    from app.models import CreditLine
    lines = db.query(CreditLine).filter(CreditLine.is_active.is_(True)).all()
    used = used_of(db, lines)          # по операциям тела кредита (10.11.2026); у линии без контрагента — ручное
    return [{"bank": c.bank, "limit_amount": c.limit_amount or 0, "used_amount": used[c.id]} for c in lines]


def load(db, user) -> dict:
    """Сводка для экрана. «Деньги на сегодня» — только тому, у кого есть «Баланс: просмотр» (владелец 02.11.2026):
    остатки банков без этого права не видны и на экране «Баланс». Остаток — тот же, что там (ДДС на сегодня)."""
    from app.permissions import get_permissions_for_user
    from app.routers.reports import get_balance
    rows = _plan_rows(db)
    out = summarize(rows, _done(db, {r["counterparty_id"] for r in rows if r["counterparty_id"]}), date.today().year)
    out["money"] = None
    if get_permissions_for_user(db, user).get("balance", {}).get("view"):
        banks = get_balance(date_to=None, db=db, current_user=user)["banks"]
        out["money"] = money(banks, _credit_lines(db), out["total"])
    return out
