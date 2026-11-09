"""
Серверные правила «Документы для бухгалтерии» — порт accDocsLogic.js один в один.
Используются: (1) в GET /api/acc-docs — отдать readiness / inv_done / upd_done / wait_work_hours в очереди;
(2) в POST /api/acc-docs/{code}/submit — повторить evaluate и отклонить 409, если не ready (фронту не доверяем);
(3) при разборе XML — сверка покупателя.

Таблицы/эндпоинты — в README §5. Время — Europe/Moscow, рабочий день 9–18, календарь из production_calendar.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from decimal import Decimal, InvalidOperation
import re
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")
SUM_TOLERANCE = Decimal("1")
WORK_FROM, WORK_TO, WORK_DAY_H = 9, 18, 9
DATE_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")


# ── деньги / даты ──
def parse_money(s) -> Decimal | None | str:
    """'' → None; '1 000 000,40' → Decimal; мусор → 'NaN'"""
    if s is None or str(s).strip() == "":
        return None
    try:
        return Decimal(re.sub(r"[\s ]", "", str(s)).replace(",", "."))
    except InvalidOperation:
        return "NaN"


def ru_date(v: str | None) -> date | None:
    m = DATE_RE.match((v or "").strip())
    if not m:
        return None
    try:
        return date(int(m[3]), int(m[2]), int(m[1]))
    except ValueError:
        return None


# ── рабочее время ──
def work_hours(a: datetime, b: datetime, holidays: set[date] = frozenset(), workdays: set[date] = frozenset()) -> float:
    if b <= a:
        return 0.0
    a, b = a.astimezone(MSK), b.astimezone(MSK)
    total, d = 0.0, a.date()
    while d <= b.date():
        working = d in workdays or (d.weekday() < 5 and d not in holidays)
        if working:
            s = max(a, datetime(d.year, d.month, d.day, WORK_FROM, tzinfo=MSK))
            e = min(b, datetime(d.year, d.month, d.day, WORK_TO, tzinfo=MSK))
            if e > s:
                total += (e - s).total_seconds() / 3600
        d += timedelta(days=1)
    return total


# ── оценка формы ──
@dataclass
class Form:
    inv_no: str = ""; inv_date: str = ""; inv_pdf_id: int | None = None
    upd_no: str = ""; upd_date: str = ""; net: str = ""; vat: str = ""; gross: str = ""
    upd_pdf_id: int | None = None; upd_xml_id: int | None = None
    xml_buyer_inn: str | None = None; xml_buyer_kpp: str | None = None; xml_contract: str | None = None
    xml_basis: str | None = None   # наименование услуги из XML — должно совпасть с согласованным основанием (05.11.2026)
    comment: str = ""

    def started(self) -> bool:
        return any([self.inv_no, self.inv_date, self.inv_pdf_id, self.upd_no, self.upd_date, self.net, self.vat, self.gross, self.upd_pdf_id, self.upd_xml_id])


def xml_mismatch(inn, kpp, contract, basis, req) -> list[str]:
    """Что в XML УПД не совпало с заявкой: покупатель, договор, основание (если задано). Одно правило для «Внести» и для
    догрузки XML во внесённую заявку; на экране — его пара `xmlCheck` в accDocsLogic.js."""
    pairs = [("ИНН покупателя", inn, req.buyer_inn), ("КПП покупателя", kpp, req.buyer_kpp), ("договор", contract, req.contract_no)]
    if getattr(req, "basis", ""):
        pairs.append(("основание", basis, req.basis))
    return [label for label, got, want in pairs if got != want]


@dataclass
class Result:
    inv_ok: bool; upd_ok: bool; ready: bool; readiness: str
    missing: list[tuple[str, str]] = field(default_factory=list)   # (label, tone: need|bad|warn) — блокируют
    warns: list[str] = field(default_factory=list)                  # не блокируют


PAPER = "бумага"   # канал выдачи договора (`master_deal.status.PAPER`) — XML для ЭДО не нужен


def evaluate(req, f: Form, *, expected: dict[str, Decimal], dup_inv: str | None, dup_upd: str | None,
             closed_until: date | None, period_end: date, read_only: bool = False) -> Result:
    """req: buyer_inn, buyer_kpp, contract_no, ds_signed. expected: net/vat/gross из строк ДС."""
    vals = {k: parse_money(getattr(f, k)) for k in ("net", "vat", "gross")}
    any_empty = any(v is None for v in vals.values())
    bad_num = any(v == "NaN" for v in vals.values())
    diffs = [abs(v - expected[k]) for k, v in vals.items() if isinstance(v, Decimal)]
    max_diff = max(diffs, default=Decimal(0))
    need_comment = max_diff > SUM_TOLERANCE
    sum_ok = not any_empty and not bad_num and (not need_comment or f.comment.strip() != "")

    xml_err = bool(f.upd_xml_id) and f.xml_buyer_inn is not None and bool(
        xml_mismatch(f.xml_buyer_inn, f.xml_buyer_kpp, f.xml_contract, f.xml_basis, req))

    inv_d, upd_d = ru_date(f.inv_date), ru_date(f.upd_date)
    inv_date_bad = bool(f.inv_date) and inv_d is None
    upd_date_bad = bool(f.upd_date) and upd_d is None
    inv_ok = bool(f.inv_no and inv_d and f.inv_pdf_id)
    # XML для ЭДО обязателен везде, кроме бумаги; канал не задан — как ЭДО (владелец 09.11.2026)
    need_xml = getattr(req, "channel", None) != PAPER
    upd_ok = bool(f.upd_no and upd_d and f.upd_pdf_id) and sum_ok and not xml_err and (bool(f.upd_xml_id) or not need_xml)

    missing: list[tuple[str, str]] = []
    if not f.inv_no: missing.append(("№ счёта", "need"))
    if not f.inv_date: missing.append(("дата счёта", "need"))
    elif inv_date_bad: missing.append(("дата счёта", "bad"))
    if not f.inv_pdf_id: missing.append(("PDF счёта", "need"))
    if not f.upd_no: missing.append(("№ УПД", "need"))
    if not f.upd_date: missing.append(("дата УПД", "need"))
    elif upd_date_bad: missing.append(("дата УПД", "bad"))
    if bad_num: missing.append(("сумма УПД", "bad"))
    elif any_empty: missing.append(("суммы УПД", "need"))
    if need_comment and not f.comment.strip(): missing.append(("комментарий к расхождению", "warn"))
    if not f.upd_pdf_id: missing.append(("PDF УПД", "need"))
    if need_xml and not f.upd_xml_id: missing.append(("XML УПД", "need"))
    if xml_err: missing.append(("XML: покупатель, договор или основание не совпадает", "bad"))

    warns: list[str] = []
    if not req.ds_signed: warns.append("ДС не подписан")
    if dup_inv: warns.append("№ счёта уже был")
    if dup_upd: warns.append("№ УПД уже был")
    if not read_only:
        for d, is_upd, lab in ((inv_d, False, "дата счёта"), (upd_d, True, "дата УПД")):
            if d is None: continue
            if closed_until and d <= closed_until: warns.append(f"{lab}: период закрыт")
            elif is_upd and d < period_end: warns.append(f"{lab}: раньше конца периода ДС ({period_end:%d.%m.%Y})")

    ready = not missing
    return Result(inv_ok, upd_ok, ready, "none" if not f.started() else "ready" if ready else "started", missing, warns)
