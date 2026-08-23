"""Импорт реестра документов Диадока и привязка их к операциям.

Выгрузка делается вручную из веб-интерфейса Диадока (API не подключён) — CSV в cp1251
с разделителем «;». Направление (исходящий/входящий) в файле НЕ указано, поэтому
задаётся при импорте параметром.

Матч идёт каскадом, от надёжного к слабому:
  number_date   — ИНН + номер счёта + дата счёта
  number        — ИНН + номер счёта (дата в операции не заполнена)
  amount_window — ИНН + сумма, оплата в окне [-5..180] дней от даты счёта

Замер на боевых данных 2026-08-20 (867 строк после фильтра статуса): 611 / 47 / 116
однозначных, 38 неоднозначных, 55 без операции. Слабое правило намеренно НЕ
применяется само — круглые повторяющиеся суммы дают ложные привязки, которые потом
не отличить от верных.
"""

import csv
import io
import re
from datetime import datetime, date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.links import validate_link
from app.database import get_db
from app.models import Operation, Counterparty, User
from app.diadoc_models import DiadocDocument, OperationDocument
from app.permissions import require_permission
from app.audit import log_action

router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024

# Статусы документооборота берутся дословно, по-русски — они сравниваются буквально.
# Аннулируемые документы не грузятся: по ним ещё не решено, существуют ли они.
ACCEPTED_STATUSES = (
    "Документооборот завершен",
    "Документооборот завершен. Отказано в аннулировании",
    "Подписан контрагентом",
)

# Окно между датой счёта и датой оплаты для слабого правила. Медиана разрыва на
# боевых данных — 61 день, p90 — 105, максимум 178. Отрицательный край нужен для
# случаев, когда оплата прошла раньше выставления счёта.
WINDOW_BEFORE = -5
WINDOW_AFTER = 180


# ---------------------------------------------------------------- разбор файла

def _norm_number(value: Optional[str]) -> str:
    """«№ 000012» → «12». Номера в базе записаны свободно, матч идёт по нормализованному."""
    s = _unquote(value or "")
    s = s.replace("№", "").replace("N", "").strip().lower()
    s = re.sub(r"\s+", "", s)
    return s.lstrip("0") or s


def _unquote(value: str) -> str:
    """Диадок пишет ИНН как ="7713076301" — защита Excel от потери ведущих нулей."""
    return re.sub(r'^=?"*|"*$', "", (value or "").strip())


def _to_float(value: str) -> Optional[float]:
    s = (value or "").replace("\xa0", " ").replace(" ", "").replace(",", ".")
    try:
        return round(float(s), 2)
    except (TypeError, ValueError):
        return None


def _to_date(value: str) -> Optional[date]:
    try:
        return datetime.strptime((value or "").strip()[:10], "%d.%m.%Y").date()
    except (TypeError, ValueError):
        return None


def _doc_type(file_name: str) -> str:
    """Тип документа берётся из «Имени файла»: «Счет №12 от ...» → «Счет»."""
    first = re.split(r"[ _\d]", (file_name or "").strip())[0]
    return first or "Документ"


def _parse_csv(contents: bytes) -> List[dict]:
    text = None
    for enc in ("cp1251", "utf-8-sig", "utf-8"):
        try:
            text = contents.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise HTTPException(status_code=400, detail="Не удалось определить кодировку файла")

    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    if not reader.fieldnames or "Ссылка" not in [f.strip() for f in reader.fieldnames]:
        raise HTTPException(
            status_code=400,
            detail="Это не похоже на реестр Диадока: нет колонки «Ссылка». "
                   "Выгрузите реестр документов из Диадока целиком, не меняя колонки.")

    keys = {f.strip(): f for f in reader.fieldnames}

    def get(row, name):
        return (row.get(keys.get(name, name)) or "").strip()

    out = []
    for row in reader:
        link = get(row, "Ссылка")
        m = re.search(r"diadoc\.kontur\.ru/([0-9a-f-]+)/Document/Show\?letterId=([0-9a-f-]+)"
                      r"&documentId=([0-9a-f-]+)", link)
        if not m:
            continue
        out.append({
            "box_id": m.group(1),
            "letter_id": m.group(2),
            "document_id": m.group(3),
            "doc_type": _doc_type(get(row, "Имя файла")),
            "number": _unquote(get(row, "Номер документа")),
            "number_norm": _norm_number(get(row, "Номер документа")),
            "doc_date": _to_date(get(row, "Дата документа")),
            "total": _to_float(get(row, "Всего")),
            "vat": _to_float(get(row, "НДС")),
            "counterparty_inn": _unquote(get(row, "ИНН")),
            "counterparty_kpp": _unquote(get(row, "КПП")),
            # Кавычки убираются целиком: csv-разбор съедает закрывающую кавычку названия
            # («ООО ""УАЙТ БОКС МЕДИА""» превращается в «ООО "УАЙТ БОКС МЕДИА»), и
            # чинить их парность надёжнее отказом от кавычек, чем угадыванием.
            "counterparty_name": re.sub(r'"+', "", get(row, "Название организации")).strip(),
            "status": get(row, "Статус документа"),
            "file_name": get(row, "Имя файла"),
            # Ссылку не берём из файла как есть, а СОБИРАЕМ из разобранных частей.
            # Причина: регулярка выше ищет подстроку (re.search), поэтому строка вида
            # "javascript:...//diadoc.kontur.ru/…/Document/Show?letterId=…&documentId=…"
            # успешно разбирается, а в базу легла бы целиком — вместе со схемой
            # javascript:. На фронте она рендерится как <a href={...}> (DiadocImport.js),
            # то есть исполнилась бы у того, кто по ней кликнул.
            "link": (f"https://diadoc.kontur.ru/{m.group(1)}/Document/Show"
                     f"?letterId={m.group(2)}&documentId={m.group(3)}"),
            "comment": get(row, "Комментарий"),
        })
    return out


# ------------------------------------------------------------------- матчинг

def _op_amount(op: Operation, direction: str) -> float:
    return round((op.income or 0) if direction == "outgoing" else (op.expense or 0), 2)


def _op_brief(op: Operation, item: dict) -> dict:
    """Краткая карточка операции для выбора кандидата.

    ИНН, название контрагента и его id отдаются всегда: когда кандидатов несколько,
    различить их по одной сумме и дате невозможно, а по id контрагента ещё и открывается
    его карточка. Дубли в справочнике (один ИНН, две записи) видно только так.
    """
    return {
        "id": op.id,
        "date": op.date.isoformat() if op.date else None,
        "status": op.status,
        "income": op.income or 0,
        "expense": op.expense or 0,
        "period": op.period,
        "invoice": op.invoice,
        "invoice_date": op.invoice_date.isoformat() if op.invoice_date else None,
        "counterparty": item.get("name"),
        "counterparty_inn": item.get("inn") or None,
        "counterparty_id": item.get("cp_id"),
        "description": op.description,
        "document_link": op.document_link or None,
    }


def _candidate_pool(db: Session, direction: str, doc_type: str):
    """Операции нужного знака, ещё не связанные с документом ТОГО ЖЕ типа.

    Тип важен: у операции законно бывает и счёт, и УПД — вторая привязка не дубль.
    Operation.document_link не учитывается: это ручная разметка входящих документов,
    импорт её не заменяет и не перетирает.
    """
    q = db.query(Operation, Counterparty.inn, Counterparty.name, Counterparty.id).outerjoin(
        Counterparty, Counterparty.id == Operation.counterparty_id)
    if direction == "outgoing":
        q = q.filter(Operation.income > 0)
    else:
        q = q.filter(Operation.expense > 0)

    taken = set(
        r[0] for r in db.query(OperationDocument.operation_id)
        .join(DiadocDocument, DiadocDocument.id == OperationDocument.document_id)
        .filter(DiadocDocument.doc_type == doc_type).all())

    pool = []
    for op, inn, cp_name, cp_id in q.all():
        if op.id in taken:
            continue
        pool.append({"op": op, "inn": (inn or "").strip(), "name": cp_name or "",
                     "cp_id": cp_id, "amount": _op_amount(op, direction)})
    return pool


def _build_indexes(pool: List[dict]):
    by_number_date, by_number, by_amount = {}, {}, {}
    for item in pool:
        op, inn = item["op"], item["inn"]
        if not inn:
            continue
        num = _norm_number(op.invoice)
        if num:
            by_number.setdefault((inn, num), []).append(item)
            if op.invoice_date:
                by_number_date.setdefault((inn, num, op.invoice_date), []).append(item)
        by_amount.setdefault((inn, item["amount"]), []).append(item)
    return by_number_date, by_number, by_amount


def _plausible(item: dict, row: dict, ddate: Optional[date]) -> bool:
    """Вторая опора для матча по одному номеру: сумма сошлась либо дата в окне."""
    if row["total"] is not None and abs(item["amount"] - row["total"]) < 0.01:
        return True
    op_date = item["op"].date
    if ddate and op_date and WINDOW_BEFORE <= (op_date - ddate).days <= WINDOW_AFTER:
        return True
    # Плановая операция ещё не оплачена, даты нет — опираемся на дату счёта в самой операции.
    inv_date = item["op"].invoice_date
    if ddate and inv_date and abs((inv_date - ddate).days) <= 5:
        return True
    return False


def _match_row(row: dict, idx) -> dict:
    by_number_date, by_number, by_amount = idx
    inn, num, ddate = row["counterparty_inn"], row["number_norm"], row["doc_date"]

    if inn and num and ddate:
        hit = by_number_date.get((inn, num, ddate), [])
        if len(hit) == 1:
            return {"rule": "number_date", "candidates": hit}
        if len(hit) > 1:
            return {"rule": "ambiguous", "candidates": hit}

    if inn and num:
        # Номера счетов сквозные и начинаются заново каждый год: «22» существует и в
        # 2024, и в 2025. Поэтому одного совпадения номера мало — нужна ещё одна
        # опора: та же сумма либо оплата в разумном окне от даты счёта. Без этой
        # проверки счёт 2024 года цеплялся к операции 2025-го (проверено на боевых).
        hit = [x for x in by_number.get((inn, num), []) if _plausible(x, row, ddate)]
        if len(hit) == 1:
            return {"rule": "number", "candidates": hit}
        if len(hit) > 1:
            return {"rule": "ambiguous", "candidates": hit}

    if inn and row["total"] is not None and ddate:
        hit = [x for x in by_amount.get((inn, row["total"]), [])
               if x["op"].date and WINDOW_BEFORE <= (x["op"].date - ddate).days <= WINDOW_AFTER]
        if len(hit) == 1:
            return {"rule": "amount_window", "candidates": hit}
        if len(hit) > 1:
            return {"rule": "ambiguous", "candidates": hit}

    return {"rule": "none", "candidates": []}


# Автоматически применяются только правила по номеру счёта. amount_window попадает
# в очередь на подтверждение — см. шапку модуля.
AUTO_RULES = ("number_date", "number")

# Один платёж законно закрывает несколько счетов, поэтому строку, под которую не нашлось
# операции с той же суммой, имеет смысл искать в связке с соседними. Перебор ограничен
# двойками и тройками: на четвёрках число сочетаний растёт быстрее, чем растёт доверие
# к найденному совпадению — «сумма сошлась» у случайной четвёрки уже не редкость.
COMBO_MAX = 3
# Окно для склейки шире одиночного: счета одного платежа могут быть выставлены в разные
# месяцы, а оплачены одним переводом.
COMBO_BEFORE, COMBO_AFTER = -10, 240


def _close_gaps(out: List[dict], none_items: List[dict], doc_type: str) -> List[dict]:
    """Документ опознан по номеру, но операция больше него — ищем, чем закрыть разницу."""
    from itertools import combinations

    free = {}
    for it in none_items:
        r = it["row"]
        if r["counterparty_inn"] and r["total"] is not None:
            free.setdefault(r["counterparty_inn"], []).append(r)

    combos, used = [], set()
    for o in out:
        if o["state"] != "queue" or o["doc_type"] != doc_type or not o["candidates"]:
            continue
        cand = o["candidates"][0]
        gap = cand["amount_mismatch"]
        if gap is None or gap <= 0:
            continue
        pot = [r for r in free.get(o["counterparty_inn"], [])
               if r["document_id"] not in used]
        found = None
        for size in (1, 2):
            for pack in combinations(pot, size):
                if abs(sum(r["total"] for r in pack) - gap) < 0.01:
                    found = pack
                    break
            if found:
                break
        if not found:
            continue
        for r in found:
            used.add(r["document_id"])
        ids = [o["document_id"]] + [r["document_id"] for r in found]
        combos.append({"operation": cand,
                       "op_amount": round((cand["income"] or 0) or (cand["expense"] or 0), 2),
                       "docs_total": round(o["total"] + sum(r["total"] for r in found), 2),
                       "document_ids": ids})
    return combos


def _find_combos(none_items: List[dict], pool: List[dict], consumed: set) -> List[dict]:
    """Наборы из 2-3 документов, сумма которых равна сумме одной свободной операции."""
    from itertools import combinations

    docs_by_inn = {}
    for it in none_items:
        inn = it["row"]["counterparty_inn"]
        if inn and it["row"]["total"] is not None and it["row"]["doc_date"]:
            docs_by_inn.setdefault(inn, []).append(it)

    ops_by_inn = {}
    for item in pool:
        if item["inn"] and item["op"].id not in consumed and item["op"].date:
            ops_by_inn.setdefault(item["inn"], []).append(item)

    combos, used_docs = [], set()
    for inn, docs in docs_by_inn.items():
        ops = sorted(ops_by_inn.get(inn, []), key=lambda x: x["op"].date)
        for item in ops:
            op = item["op"]
            pot = [d for d in docs
                   if d["row"]["document_id"] not in used_docs
                   and COMBO_BEFORE <= (op.date - d["row"]["doc_date"]).days <= COMBO_AFTER]
            if len(pot) < 2:
                continue
            found = None
            for size in range(2, COMBO_MAX + 1):
                for pack in combinations(pot, size):
                    if abs(sum(d["row"]["total"] for d in pack) - item["amount"]) < 0.01:
                        found = pack
                        break
                if found:
                    break
            if not found:
                continue
            for d in found:
                used_docs.add(d["row"]["document_id"])
            combos.append({"operation": _op_brief(op, item),
                           "op_amount": item["amount"],
                           "docs_total": round(sum(d["row"]["total"] for d in found), 2),
                           "document_ids": [d["row"]["document_id"] for d in found]})
            consumed.add(op.id)
    return combos


# ------------------------------------------------------------------ эндпоинты

@router.post("/import/preview")
async def preview_import(
    file: UploadFile = File(...),
    direction: str = "outgoing",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operations", "view")),
):
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Файл слишком большой (максимум 10 МБ)")
    if direction not in ("outgoing", "incoming"):
        raise HTTPException(status_code=400, detail="Направление: outgoing или incoming")

    rows = _parse_csv(contents)
    if not rows:
        raise HTTPException(status_code=400, detail="В файле не нашлось ни одной строки со ссылкой на документ")

    skipped_status = [r for r in rows if r["status"] not in ACCEPTED_STATUSES]
    rows = [r for r in rows if r["status"] in ACCEPTED_STATUSES]

    known = {d.document_id: d for d in db.query(DiadocDocument).filter(
        DiadocDocument.document_id.in_([r["document_id"] for r in rows])).all()} if rows else {}
    linked_docs = set()
    if known:
        linked_docs = set(r[0] for r in db.query(OperationDocument.document_id).filter(
            OperationDocument.document_id.in_([d.id for d in known.values()])).all())

    doc_types = set(r["doc_type"] for r in rows)
    pools_raw = {t: _candidate_pool(db, direction, t) for t in doc_types}
    pools = {t: _build_indexes(pools_raw[t]) for t in doc_types}

    cp_by_inn = {}
    for cp in db.query(Counterparty).all():
        if (cp.inn or "").strip():
            cp_by_inn.setdefault(cp.inn.strip(), cp)

    out, counts = [], {"auto": 0, "queue": 0, "ambiguous": 0, "none": 0, "already": 0}
    for r in rows:
        existing = known.get(r["document_id"])
        if existing is not None and existing.id in linked_docs:
            counts["already"] += 1
            out.append({**_row_public(r), "state": "already", "rule": None, "candidates": []})
            continue

        m = _match_row(r, pools[r["doc_type"]])
        cands = [{**_op_brief(c["op"], c),
                  "amount_mismatch": (None if r["total"] is None
                                      or abs(c["amount"] - r["total"]) < 0.01
                                      else round(c["amount"] - r["total"], 2))}
                 for c in m["candidates"]]

        if m["rule"] in AUTO_RULES:
            # Номер и дата совпали, а сумма разошлась — это не повод привязывать молча:
            # на боевых данных так вылезали случаи вроде 330 099 против 165 000.
            state = "queue" if (cands and cands[0]["amount_mismatch"] is not None) else "auto"
        elif m["rule"] == "amount_window":
            state = "queue"
        elif m["rule"] == "ambiguous":
            state = "ambiguous"
        else:
            state = "none"
        counts[state] += 1

        out.append({**_row_public(r), "state": state, "rule": m["rule"],
                    "candidates": cands,
                    "counterparty_known": bool(cp_by_inn.get(r["counterparty_inn"]))})

    # Операции, уже разобранные одиночными правилами, в склейки не отдаём — иначе один
    # платёж предложится и как пара документов, и как одиночный.
    by_docid = {r["document_id"]: r for r in rows}
    consumed = set()
    for o in out:
        if o["state"] in ("auto", "queue") and o["candidates"]:
            consumed.add(o["candidates"][0]["id"])

    combos = []
    for doc_type in doc_types:
        none_items = [{"row": by_docid[o["document_id"]]} for o in out
                      if o["state"] == "none" and o["doc_type"] == doc_type]
        combos += _find_combos(none_items, pools_raw[doc_type], consumed)
        # Более частый вид склейки: один документ уже опознан по номеру, но операция
        # больше него — недостающую разницу закрывает ещё один непривязанный документ
        # того же контрагента.
        combos += _close_gaps(out, none_items, doc_type)

    in_combo = {}
    for i, c in enumerate(combos):
        c["id"] = i
        for did in c["document_ids"]:
            in_combo[did] = i

    # Остальным «не нашлось» даём список соседних операций того же ИНН, чтобы склеить
    # руками: суммой они не совпали, но платёж может быть частичным или сборным.
    for o in out:
        if o["document_id"] in in_combo:
            counts[o["state"]] -= 1
            o["state"] = "combo"
            o["combo_id"] = in_combo[o["document_id"]]
            counts["combo"] = counts.get("combo", 0) + 1
        elif o["state"] == "none" and o["counterparty_inn"]:
            d0 = by_docid[o["document_id"]]["doc_date"]
            # consumed здесь НЕ исключаем: операция, которой уже достался один документ,
            # как раз и есть самый вероятный адресат склейки.
            near = [it for it in pools_raw[o["doc_type"]]
                    if it["inn"] == o["counterparty_inn"]
                    and (not d0 or not it["op"].date
                         or COMBO_BEFORE <= (it["op"].date - d0).days <= COMBO_AFTER)]
            near.sort(key=lambda it: (it["op"].date or date.max))
            o["near"] = [{**_op_brief(it["op"], it), "amount_mismatch": None}
                         for it in near[:8]]

    return {
        "combos": combos,
        "direction": direction,
        "counts": {**counts, "total": len(rows), "skipped_status": len(skipped_status)},
        "skipped_statuses": sorted(set(r["status"] for r in skipped_status)),
        "rows": out,
    }


def _row_public(r: dict) -> dict:
    return {**r, "doc_date": r["doc_date"].isoformat() if r["doc_date"] else None}


class ApplyRow(BaseModel):
    document_id: str
    box_id: str
    letter_id: str
    doc_type: str = "Счет"
    number: Optional[str] = None
    number_norm: Optional[str] = None
    doc_date: Optional[date] = None
    total: Optional[float] = None
    vat: Optional[float] = None
    counterparty_inn: Optional[str] = None
    counterparty_kpp: Optional[str] = None
    counterparty_name: Optional[str] = None
    status: Optional[str] = None
    file_name: Optional[str] = None
    link: Optional[str] = None
    comment: Optional[str] = None
    # Операция, к которой привязать. None — документ грузится в реестр без привязки.
    operation_id: Optional[int] = None
    match_rule: str = "manual"


class ApplyRequest(BaseModel):
    direction: str = "outgoing"
    rows: List[ApplyRow]


@router.post("/import/apply")
def apply_import(
    payload: ApplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operations", "edit")),
):
    if payload.direction not in ("outgoing", "incoming"):
        raise HTTPException(status_code=400, detail="Направление: outgoing или incoming")

    cp_by_inn = {}
    for cp in db.query(Counterparty).all():
        if (cp.inn or "").strip():
            cp_by_inn.setdefault(cp.inn.strip(), cp)

    created_docs = updated_docs = created_links = skipped_links = 0

    # Расхождение суммы считается на ОПЕРАЦИЮ, а не на документ: когда один платёж
    # закрывает несколько счетов, разница «операция минус один документ» бессмысленна
    # и выглядела бы ошибкой. Складываем документы, которые в этой загрузке идут на
    # одну операцию, и пишем одну и ту же разницу во все её привязки.
    batch_totals = {}
    for row in payload.rows:
        if row.operation_id and row.total is not None:
            batch_totals[row.operation_id] = round(
                batch_totals.get(row.operation_id, 0) + row.total, 2)

    for row in payload.rows:
        doc = db.query(DiadocDocument).filter(
            DiadocDocument.document_id == row.document_id).first()
        if doc is None:
            doc = DiadocDocument(document_id=row.document_id, imported_by=current_user.id)
            db.add(doc)
            created_docs += 1
        else:
            updated_docs += 1

        doc.box_id = row.box_id
        doc.letter_id = row.letter_id
        doc.doc_type = row.doc_type
        doc.direction = payload.direction
        doc.number = row.number
        doc.number_norm = row.number_norm or _norm_number(row.number)
        doc.doc_date = row.doc_date
        doc.total = row.total
        doc.vat = row.vat
        doc.counterparty_inn = (row.counterparty_inn or "").strip() or None
        doc.counterparty_kpp = row.counterparty_kpp
        doc.counterparty_name = row.counterparty_name
        doc.status = row.status
        doc.file_name = row.file_name
        # Второй путь входа — payload от клиента, минуя разбор файла: схему проверяем.
        doc.link = validate_link(row.link, raise_on_bad=False)
        doc.comment = row.comment
        cp = cp_by_inn.get((row.counterparty_inn or "").strip())
        doc.counterparty_id = cp.id if cp else None

        db.flush()

        if row.operation_id:
            op = db.query(Operation).filter(Operation.id == row.operation_id).first()
            if op is None:
                skipped_links += 1
                continue
            exists = db.query(OperationDocument).filter(
                OperationDocument.operation_id == op.id,
                OperationDocument.document_id == doc.id).first()
            if exists:
                skipped_links += 1
                continue
            amount = _op_amount(op, payload.direction)
            docs_sum = batch_totals.get(op.id)
            mismatch = (None if docs_sum is None or abs(amount - docs_sum) < 0.01
                        else round(amount - docs_sum, 2))
            db.add(OperationDocument(
                operation_id=op.id, document_id=doc.id, match_rule=row.match_rule,
                amount_mismatch=mismatch, matched_by=current_user.id))
            created_links += 1

    db.commit()
    log_action(db, current_user, "diadoc_import",
               "diadoc", None,
               f"направление={payload.direction}, документов новых={created_docs}, "
               f"обновлено={updated_docs}, привязок={created_links}")
    return {"created_documents": created_docs, "updated_documents": updated_docs,
            "created_links": created_links, "skipped_links": skipped_links}


@router.get("/documents")
def list_documents(
    operation_id: Optional[int] = None,
    unlinked: bool = False,
    limit: int = 500,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operations", "view")),
):
    """Документы операции (для иконок) либо документы без привязки (отчёт о дырах)."""
    if operation_id is not None:
        rows = db.query(DiadocDocument, OperationDocument).join(
            OperationDocument, OperationDocument.document_id == DiadocDocument.id).filter(
            OperationDocument.operation_id == operation_id).all()
        return [{"id": d.id, "doc_type": d.doc_type, "number": d.number,
                 "doc_date": d.doc_date.isoformat() if d.doc_date else None,
                 "total": d.total, "link": d.link, "match_rule": l.match_rule,
                 "amount_mismatch": l.amount_mismatch, "link_id": l.id}
                for d, l in rows]

    q = db.query(DiadocDocument)
    if unlinked:
        linked = db.query(OperationDocument.document_id).subquery()
        q = q.filter(~DiadocDocument.id.in_(linked))
    rows = q.order_by(DiadocDocument.doc_date.desc().nullslast()).limit(limit).all()
    return [{"id": d.id, "doc_type": d.doc_type, "number": d.number,
             "doc_date": d.doc_date.isoformat() if d.doc_date else None,
             "total": d.total, "counterparty_name": d.counterparty_name,
             "counterparty_inn": d.counterparty_inn, "link": d.link,
             "status": d.status} for d in rows]


@router.delete("/links/{link_id}")
def delete_link(
    link_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operations", "edit")),
):
    link = db.query(OperationDocument).filter(OperationDocument.id == link_id).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    db.delete(link)
    db.commit()
    log_action(db, current_user, "diadoc_unlink", "operation", link.operation_id, "")
    return {"ok": True}
