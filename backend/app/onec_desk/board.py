# -*- coding: utf-8 -*-
"""Вся выдача экрана «Документы для бухгалтерии» одним ответом — в форме контракта хендоффа (`components/onecDesk/sampleData`
в пакете дизайна, 05.11.2026). Заявка = комплект мастер-сделки (одна УПД + один счёт). `code` — код мастер-сделки, а если
комплектов у неё несколько — «M-0016 · УПД 2»: по нему экран различает заявки.

Ждут — комплекты пакетов от «ждём 1С» до архива без ответа 1С; возвращены — у аккаунта; внесены — последние DONE_LIMIT."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.onec_desk import close as CL
from app.onec_desk import files as OF
from app.onec_desk import rules as R
from app.onec_desk.service import DONE, OPEN, RETURNED

DONE_LIMIT = 300
ANNEX_SHORT = (("Дополнительное соглашение", "ДС"), ("Приложение", "Прил."))


def _iso(v) -> Optional[str]:
    """Время в базе — UTC без пояса (DateTime): отдаём с поясом, экран считает по МСК."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return datetime(v.year, v.month, v.day, tzinfo=R.MSK).isoformat()


def _ru(d) -> str:
    return d.strftime("%d.%m.%Y") if d else ""


def _annex(number: Optional[str], a) -> dict:
    title = number or "ДС"
    short = title
    for long_, s in ANNEX_SHORT:
        short = short.replace(long_, s)
    kind = "ДС" if title.startswith("Доп") or title.startswith("ДС") else "Прил"
    return {"id": a.id if a is not None else None, "kind": kind, "no": a.no if a is not None else None,
            "date": _iso(a.date) if a is not None and a.date else None, "title": title, "short": short,
            "external": bool(a is not None and a.origin == "загружен")}


def _status(k, m) -> Optional[str]:
    if k.onec_state == DONE:
        return "done"
    if k.onec_state == RETURNED:
        return "returned"
    return "wait" if m.status in OPEN else None


def _thread(evs: list, seen_at) -> list:
    """Сообщения: вопросы бухгалтера (комментарий) и ответы аккаунта; новые сверху. Системные события экран добавляет сам."""
    out = [{"at": _iso(e.at), "who": e.who or ("Аккаунт" if e.kind == "ответ" else "Бухгалтер"), "text": e.text,
            "from_account": e.kind == "ответ", "unread": e.kind == "ответ" and (seen_at is None or e.at > seen_at)}
           for e in evs if e.kind in ("комментарий", "ответ") and e.text]
    return out[::-1]


def snapshot(req: dict) -> dict:
    """Что запоминаем при возврате, чтобы при повторной отправке показать «было → стало»."""
    t = _expected(req)
    return {"ИНН покупателя": req["buyer"]["inn"], "КПП покупателя": req["buyer"]["kpp"], "покупатель": req["buyer"]["name"],
            "договор": req["contract"]["no"], "ДС": req["annex"]["title"] + (" подписан" if req["ds_signed"] else ""),
            "сумма с НДС": f"{t['gross']:.2f}", "основание": req["basis"]}


def _expected(req: dict) -> dict:
    return {k: round(sum(float(l[k]) for l in req["lines"]), 2) for k in ("net", "vat", "gross")}


def _resent(evs: list, req: dict) -> Optional[dict]:
    """Заявка вернулась после возврата: последнее «исправлено» новее последнего «возврат»."""
    back = next((e for e in reversed(evs) if e.kind == "возврат"), None)
    fix = next((e for e in reversed(evs) if e.kind == "исправлено"), None)
    if back is None or fix is None or fix.id < back.id or req["status"] != "wait":
        return None
    now, was = snapshot(req), back.snapshot or {}
    changes = [{"label": k, "from": was.get(k) or "—", "to": now.get(k) or "—"} for k in now
               if k in was and str(was.get(k) or "") != str(now.get(k) or "") and k != "основание"]
    if was.get("основание") and was.get("основание") != now.get("основание"):
        changes.append({"label": "основание", "from": "было иначе", "to": "изменено"})
    when = back.at.replace(tzinfo=timezone.utc).astimezone(R.MSK).strftime("%d.%m %H:%M") if back.at else ""
    return {"at": _iso(fix.at), "was": f"Возвращали {when}: «{back.text}»" + (f" · аккаунт: «{fix.text}»" if fix.text else ""),
            "changes": changes}


def _since(m, evs: list):
    """С какого момента заявка ждёт бухгалтера: пакет пришёл в «ждём 1С» (истории статусов нет — `updated_at` пакета) или
    аккаунт прислал исправленное."""
    fix = next((e.at for e in reversed(evs) if e.kind == "исправлено"), None)
    return max(x for x in (m.updated_at, fix) if x is not None) if (m.updated_at or fix) else None


def _ds_signed(db: Session, a) -> bool:
    if a is None:
        return False
    if a.origin == "загружен" or a.sign_state == "подписан":
        return True
    return bool(db.execute(text("SELECT 1 FROM master_deal_files WHERE annex_id = :a AND kind = 'скан ДС' LIMIT 1"), {"a": a.id}).first())


def _events(db: Session, ids: list) -> dict:
    rows = db.execute(text("""SELECT e.id, e.upd_id, e.kind, e.text, e.at, e.snapshot, u.name AS who FROM onec_desk_events e
                               LEFT JOIN users u ON u.id = e.by_user WHERE e.upd_id = ANY(:ids) ORDER BY e.id"""),
                      {"ids": ids or [0]}).all()
    out: dict = {}
    for r in rows:
        out.setdefault(r.upd_id, []).append(r)
    return out


def _files(f: dict) -> dict:
    """Файлы комплекта в форме экрана: invPdf / updPdf / updXml → {id, name, size, url}."""
    conv = {"invoice": "invPdf", "upd": "updPdf", "xml": "updXml"}
    return {conv[k]: {"id": v["id"], "name": v["filename"], "size": v.get("size") or 0, "url": None} for k, v in f.items()}


def _accounts(db: Session, annex_id) -> list:
    """Аккаунты сделок, разнесённых на ДС комплекта (владелец 09.11.2026: «вот сюда нужно вывести аккаунта сделки»)."""
    if not annex_id:
        return []
    return sorted({r for (r,) in db.execute(text("""
        SELECT DISTINCT r.name FROM sales_deal_annex_allocation x JOIN sales_deals d ON d.id = x.deal_id
          JOIN sales_reps r ON r.id = d.account_manager_id WHERE x.annex_id = :a AND r.name IS NOT NULL"""), {"a": annex_id})})


def request(db: Session, m, k, kit: dict, n_kits: int, evs: list, cal: tuple, now: datetime, c=None, buyer=None) -> Optional[dict]:
    from app.onec_desk import queue as Q
    from app.sales.models import SalesAnnex
    status = _status(k, m)
    if status is None:
        return None
    a = db.get(SalesAnnex, k.annex_id) if k.annex_id else None
    rate = float(a.vat_rate) if a is not None and a.vat_rate is not None else (round(float(k.vat or 0) / float(k.net) * 100) if k.net else 0.0)
    lines = Q._lines(db, k, a, kit.get("values") or {}, rate) if a is not None else []
    if not lines:          # строк своей УПД нет (ДС без строк) — одна строка из комплекта
        lines = [{"service": k.service or "", "net": float(k.net or 0), "vat_rate": rate, "vat": float(k.vat or 0), "gross": float(k.gross or 0)}]
    basis = kit.get("basis") or ""
    if basis:              # в строку УПД идёт согласованное основание, а не позиция ДС (владелец 05.11.2026)
        own = {x.get("row_id"): x["text"] for x in kit.get("lines") or []}
        lines = [{**x, "service": own.get(x.get("row_id")) or basis} for x in lines]
        if len(lines) > 1:     # строки со своим основанием (06.11.2026, «вариант 3»): в 1С — столько же строк с этими текстами
            basis = "\n".join(x["service"] for x in lines)
    pf = (a.period_from if a is not None and a.period_from else None)
    pt = (a.period_to if a is not None and a.period_to else None)
    if pf is None or pt is None:
        last = Q._last_day(m.period)
        pf, pt = pf or f"{m.period}-01", pt or last
    since = _since(m, evs)
    files = OF.files_of(db, m, k)
    req = {
        "code": m.code if n_kits == 1 else f"{m.code} · УПД {k.upd_no}", "master": m.code, "kit_id": k.id, "upd_no": k.upd_no,
        "status": status, "since": _iso(since),
        "wait_work_hours": round(R.work_hours(since.replace(tzinfo=timezone.utc), now, *cal), 2) if since and status == "wait" else None,
        "buyer": {"name": (buyer.name if buyer else c.counterparty_name) or "", "inn": (buyer.inn if buyer else c.inn) or "",
                  "kpp": (buyer.kpp if buyer else None) or ""},
        "contract": {"no": c.contract_number or "", "date": _iso(c.contract_date) if c.contract_date else None},
        "annex": _annex(kit.get("annex_number") or (a.number if a is not None else None), a),
        "brand": " · ".join(x for x in (k.brand, k.service) if x),
        "period": {"from": _iso_day(pf), "to": _iso_day(pt, end=True)},
        "basis": basis, "lines": lines,
        "ds_signed": _ds_signed(db, a), "ds_file_url": "ds" if a is not None else None,
        "ds_scan_url": "scan" if a is not None and Q._ds_scan(db, a) else None,
        "draft": None, "files": _files(files), "seen": True, "resent": None, "returned": None, "done": None,
        "thread": _thread(evs, k.onec_seen_at), "edo": None,
        # Как выставляем (владелец 06.11.2026: «забыли буху показать»): признак договора, а ушедшее клиенту — по своему каналу
        "channel": _channel(db, m),
        "accounts": _accounts(db, k.annex_id),
        "sk_in_invoice": kit_sk_note(db, m, a, lines),
    }
    unseen_fix = False
    if status == "wait":
        req["draft"] = dict(k.onec_draft or {}) or None
        req["resent"] = _resent(evs, req)
        fix_at = next((e.at for e in reversed(evs) if e.kind == "исправлено"), None)
        unseen_fix = bool(req["resent"]) and (k.onec_seen_at is None or k.onec_seen_at < fix_at)
    # «ответ» и «исправлено» в очереди — пока бухгалтер не открыл заявку после них
    req["seen"] = not unseen_fix and not any(t["unread"] for t in req["thread"])
    if status == "returned":
        back = next((e for e in reversed(evs) if e.kind == "возврат"), None)
        req["returned"] = {"at": _iso(back.at), "reason": back.text} if back else None
    if status == "done":
        fl = req["files"]
        req["done"] = {"at": _iso(k.onec_at),
                       "inv": {"no": k.onec_invoice_no, "date": _ru(k.onec_invoice_date), "pdf": fl.get("invPdf")},
                       "upd": {"no": k.onec_upd_no, "date": _ru(k.onec_upd_date), "pdf": fl.get("updPdf"), "xml": fl.get("updXml")},
                       "sums": {"net": k.onec_net, "vat": k.onec_vat, "gross": k.onec_gross}}
    return req


def _channel(db: Session, m) -> Optional[str]:
    """«ЭДО» / «бумага» / None (у договора не задан — пакет сам в «выставление» не уйдёт)."""
    from app.master_deal import status as ST
    if ST.is_paper(db, m):
        return ST.PAPER
    return ST.channel_of(db, m) or None


def _iso_day(v, end: bool = False) -> Optional[str]:
    if v is None:
        return None
    s = v.isoformat() if hasattr(v, "isoformat") else str(v)
    return s[:10] + ("T23:59:00+03:00" if end else "T00:00:00+03:00")


def board(db: Session, now: Optional[datetime] = None) -> dict:
    """GET /onec-desk/board — вся страница: сейчас, настройки бухгалтерии, наше юрлицо, заявки."""
    from app import own_company
    from app.master_deal import to_annex as TA
    from app.master_deal.models import MasterDeal, MasterDealUpd
    from app.models import Contract, Counterparty
    now = now or datetime.now(timezone.utc)
    st = CL.settings(db, now)
    cal = CL.sets(st["calendar"])
    rows = db.execute(text("""SELECT k.id FROM master_deal_upds k JOIN master_deals m ON m.id = k.master_deal_id
                               WHERE (m.status = ANY(:open) AND k.onec_state IS NULL) OR k.onec_state = :r
                               UNION ALL
                              SELECT id FROM (SELECT k.id FROM master_deal_upds k WHERE k.onec_state = :d
                                               ORDER BY k.onec_at DESC NULLS LAST LIMIT :n) x"""),
                      {"open": list(OPEN), "r": RETURNED, "d": DONE, "n": DONE_LIMIT}).scalars().all()
    kits = db.query(MasterDealUpd).filter(MasterDealUpd.id.in_(rows or [0])).all()
    evs = _events(db, [k.id for k in kits])
    by_master: dict = {}
    for k in kits:
        by_master.setdefault(k.master_deal_id, []).append(k)
    out, seller = [], None
    for mid, ks in by_master.items():
        m = db.get(MasterDeal, mid)
        c = db.get(Contract, m.contract_id)
        buyer = db.get(Counterparty, c.counterparty_id) if c is not None and c.counterparty_id else None
        if seller is None and c is not None:
            s = own_company.for_contract(db, c)
            seller = {"name": s.name, "inn": s.inn, "kpp": s.kpp} if s is not None else None
        n_kits = db.query(MasterDealUpd).filter(MasterDealUpd.master_deal_id == m.id).count()
        upds = {u["upd_no"]: u for u in TA.upds_of(db, m)}
        for k in sorted(ks, key=lambda x: x.upd_no):
            r = request(db, m, k, upds.get(k.upd_no, {}), n_kits, evs.get(k.id, []), cal, now, c=c, buyer=buyer)
            if r is not None:
                out.append(r)
    from app.onec_desk import upstream as UP
    up = UP.upstream(db, st["month"])     # «ещё не дошли» (09.11.2026) → прогноз «Ещё в пути» второй строкой плашки срока (хендофф 09.11)
    return {"now": now.astimezone(R.MSK).isoformat(), "settings": st, "seller": seller, "requests": out,
            "not_arrived": UP.not_arrived(up)}


def request_for(db: Session, m, k, now: Optional[datetime] = None) -> Optional[dict]:
    """Одна заявка — для «Внести» (правила сверяются с тем же, что видел экран) и снимка при возврате."""
    from app.master_deal import to_annex as TA
    from app.master_deal.models import MasterDealUpd
    from app.models import Contract, Counterparty
    now = now or datetime.now(timezone.utc)
    c = db.get(Contract, m.contract_id)
    buyer = db.get(Counterparty, c.counterparty_id) if c is not None and c.counterparty_id else None
    n_kits = db.query(MasterDealUpd).filter(MasterDealUpd.master_deal_id == m.id).count()
    kit = next((u for u in TA.upds_of(db, m) if u["upd_no"] == k.upd_no), {})
    cal = CL.sets(CL.work_calendar(db))
    return request(db, m, k, kit, n_kits, _events(db, [k.id]).get(k.id, []), cal, now, c=c, buyer=buyer)


def _deal_ids(db: Session, m) -> list:
    return list(db.execute(text("SELECT deal_id FROM master_deal_items WHERE master_deal_id = :m ORDER BY id"), {"m": m.id}).scalars())


def sk_in_bill(db: Session, m, only: Optional[set] = None) -> list:
    """Сделки пакета со скидкой СК в счёт (только для сведения, владелец 11.11.2026); `only` — id сделок комплекта."""
    from app.final_recon import sk as SK
    from app.sales.models import SalesDeal
    out = []
    for i in _deal_ids(db, m):
        if only is not None and i not in only:
            continue
        d = db.get(SalesDeal, i)
        sk = SK.of_deal(db, d) if d is not None else {}
        if sk.get("mode") == "скидка в счёт" and float(sk.get("percent") or 0) > 0:
            out.append({"deal": d.code, "pct": float(sk["percent"])})
    return out


def kit_sk_note(db: Session, m, a, lines: list) -> list:
    """Плашка заявки «со скидкой в счёт»: сделки СВОЕГО комплекта, чьё размещение в нём есть (доп СК не облагается).
    ДС по старому правилу (строка «Скидка СК», до 11.11.2026) — без плашки: такую строку заявка не видит, и «скидка уже
    в цене» было бы неправдой (ревью 11.11.2026)."""
    if a is not None and any((r or {}).get("kind") == "discount" for r in (a.rows or [])):
        return []
    ids = {x.get("deal_id") for x in lines if x.get("kind") == "размещение" and x.get("deal_id")}
    return sk_in_bill(db, m, ids) if ids else []
