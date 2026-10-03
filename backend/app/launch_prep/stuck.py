"""«Согласования → Подвисшие» (владелец 03.10.2026): экран менеджера паблишеров — что
подвисло на площадках.

Строка — пара «креатив × площадка» одного из трёх видов:
* **waiting** — отправлено, площадка молчит дольше `LATE_WORKDAYS` рабочих дней (порог —
  тот же, что у «просрочено» матрицы, одно правило на оба экрана);
* **rework** — открытый запрос на доработку, любой давности, с комментарием площадки;
* **refused** — отказ площадки.

Сделки — до стадии «Итоговая сверка» (её саму и дальше уже не показываем), без проигранных.
Только чтение. Группировка — по площадке: звонят площадке, а не по сделке.
"""
from collections import defaultdict
from datetime import date, datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.launch_prep.matrix import AGREED, LATE_WORKDAYS, REFUSED, workdays_between

CUTOFF_STAGE = "Итоговая сверка"
# «Горит / срочно / терпит» — по старту размещения у площадки (владелец 03.10.2026). То же
# правило, что «просрочено / срочно» в кабинете площадки (cabinet-frontend/lib/urgency.js):
# у нас и у площадки одни слова. «Срочно» — до старта не больше 3 рабочих дней.
URGENT_WORKDAYS = 3
URGENCY_ORDER = {"burning": 0, "urgent": 1, "calm": 2}
REWORK = "на доработку"
REFUSAL = "отказ"


def classify(sent_at: Optional[datetime], agreed_at: Optional[datetime],
             withdrawn_at: Optional[datetime], verdict: Optional[str],
             decided_at: Optional[datetime], state: str, today: date) -> Optional[dict]:
    """Вид подвисания пары и сколько рабочих дней оно длится; None — не подвисла.
    Доработка проверяется раньше согласования: площадка могла отозвать согласование из
    кабинета, и `agreed_at` тогда остаётся (так же считает матрица)."""
    if withdrawn_at or not sent_at:
        return None
    since = lambda d: workdays_between(d.date(), today) if d else 0   # noqa: E731
    if state == REFUSED or verdict == REFUSAL:
        return {"kind": "refused", "days": since(decided_at)}
    # Получатель уже согласован или размещается — старая доработка не висит (как в матрице).
    if verdict == REWORK and state not in AGREED:
        return {"kind": "rework", "days": since(decided_at)}
    if agreed_at or state in AGREED or not sent_at or verdict:
        return None
    days = since(sent_at)
    return {"kind": "waiting", "days": days} if days > LATE_WORKDAYS else None


def start_urgency(start: Optional[date], today: date) -> str:
    """Старт прошёл — горит; до него ≤ URGENT_WORKDAYS рабочих дней — срочно; иначе терпит."""
    if start is None:
        return "calm"
    if start < today:
        return "burning"
    return "urgent" if workdays_between(today, start) <= URGENT_WORKDAYS else "calm"


def order_rows(rows: list) -> list:
    """Внутри площадки: горящие сверху, потом по числу дней ожидания."""
    return sorted(rows, key=lambda x: (URGENCY_ORDER[x["urgency"]], -x["days"],
                                       x["deal_code"] or "", x["code"] or ""))


_ROWS = text("""
    SELECT p.id AS pair_id, p.code, p.sent_at, p.agreed_at, p.withdrawn_at,
           cs.id AS set_id, cs.no AS set_no, cs.title, cs.form,
           t.state, t.surface_kind, sv.name AS service,
           coalesce(t.period_from, d.period_from) AS start,
           d.id AS deal_id, d.code AS deal_code, coalesce(b.name, d.title) AS brand,
           coalesce(a.short_name, a.name) AS advertiser, rep.name AS account, st.name AS stage,
           pub.id AS publisher_id, pub.name AS publisher, pub.code AS publisher_code,
           pub.chat_url AS tg, pub.chat_url_max AS max,
           r.verdict, r.reason, r.decided_at, r.decided_by, r.decided_email, r.source
      FROM launch_prep_pair p
      JOIN launch_prep_target t ON t.id = p.target_id
      JOIN launch_prep_creative_set cs ON cs.id = p.set_id
      JOIN sales_deals d ON d.id = t.deal_id
      JOIN sales_stages st ON st.id = d.our_stage_id
      JOIN sales_stage_phases ph ON ph.id = st.phase_id
      JOIN sales_publishers pub ON pub.id = t.publisher_id
      LEFT JOIN sales_services sv ON sv.id = t.service_id
      LEFT JOIN sales_brands b ON b.id = d.brand_id
      LEFT JOIN sales_advertisers a ON a.id = d.advertiser_id
      LEFT JOIN sales_reps rep ON rep.id = d.account_manager_id
      LEFT JOIN launch_prep_review r ON r.pair_id = p.id AND r.kind = 'площадка'
     WHERE p.withdrawn_at IS NULL AND t.archived_at IS NULL AND NOT st.is_lost
       -- Доработку закрыл новый комплект: старая пара — история (erid_service, ad/build).
       AND NOT EXISTS (SELECT 1 FROM launch_prep_creative_set n
                        WHERE n.replaces_set_id = cs.id AND n.publisher_id = t.publisher_id)
       AND (ph.sort_order, st.sort_order) < (
           SELECT ph2.sort_order, s2.sort_order FROM sales_stages s2
             JOIN sales_stage_phases ph2 ON ph2.id = s2.phase_id
            WHERE s2.name = :cutoff)
""")

_PAIR_KEYS = ("pair_id", "code", "set_id", "set_no", "title", "form", "surface_kind", "service",
              "deal_id", "deal_code", "brand", "advertiser", "account", "stage", "sent_at",
              "verdict", "reason", "decided_at", "decided_by", "decided_email", "source", "start")


def load(db: Session, today: Optional[date] = None) -> dict:
    """Подвисшее сейчас, сгруппированное по площадке; площадки — от самого долгого."""
    today = today or date.today()
    pubs: dict = {}
    rows = defaultdict(list)
    for r in db.execute(_ROWS, {"cutoff": CUTOFF_STAGE}).mappings():
        c = classify(r["sent_at"], r["agreed_at"], r["withdrawn_at"], r["verdict"],
                     r["decided_at"], r["state"], today)
        if not c:
            continue
        pid = r["publisher_id"]
        pubs.setdefault(pid, {"id": pid, "name": r["publisher"], "code": r["publisher_code"],
                              "tg": r["tg"], "max": r["max"]})
        rows[pid].append({**{k: r[k] for k in _PAIR_KEYS}, **c,
                          "urgency": start_urgency(r["start"], today)})
    out = []
    for pid, p in pubs.items():
        rs = order_rows(rows[pid])
        n = defaultdict(int)
        for x in rs:
            n[x["kind"]] += 1
        burning = sum(x["urgency"] == "burning" for x in rs)
        out.append({**p, "rows": rs, "max_days": max(x["days"] for x in rs),
                    "burning": burning, "counts": dict(n)})
    out.sort(key=lambda p: (-p["burning"], -p["max_days"], p["name"]))
    return {"publishers": out, "late_workdays": LATE_WORKDAYS,
            "urgent_workdays": URGENT_WORKDAYS, "today": today, "cutoff_stage": CUTOFF_STAGE}
