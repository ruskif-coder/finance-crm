# -*- coding: utf-8 -*-
"""Документы пакета — одна модель для карточки и расхлопа реестра (хендофф «реестр + карточка», 19.10.2026).

ДС[] → комплекты УПД[]; у каждого документа — электронный файл, скан (бумага) и подпись (`sign`, 02.11.2026): где документ
у клиента (`doc_sign`: выпущен / согласован / подписан у нас / выставлен / подписан / отклонён), каким каналом и куда его
можно отметить дальше. Счёт, УПД и Отчёт придут из 1С — до интеграции у комплекта их нет (`onec: False`), экран пишет «ждём 1С»."""
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.master_deal import doc_sign as DSG
from app.master_deal import issue as IS
from app.master_deal import status as ST

EXTRA = "Доп. размещение"


def _services(rows: list) -> list:
    out = []
    for r in rows or []:
        s = EXTRA if r.get("kind") == "extra" else (r.get("position") or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def _files(db: Session, m) -> dict:
    rows = db.execute(text("""SELECT id, annex_id, upd_no, filename, uploaded_at FROM master_deal_files
                               WHERE master_deal_id = :m AND kind IN ('скан ДС', 'скан УПД')"""), {"m": m.id}).all()
    out = {}
    for fid, a, u, name, at in rows:
        out[("a", a) if a is not None else ("u", u)] = {"id": fid, "filename": name, "at": at.isoformat(timespec="seconds") if at else None}
    return out


def _onec_files(db: Session, m) -> dict:
    """Файлы из 1С по комплектам (05.11.2026): {upd_no: {invoice|upd|xml: {id, filename}}}."""
    from app.onec_desk.files import KINDS
    out: dict = {}
    for fid, u, kind, name in db.execute(text("""SELECT id, upd_no, kind, filename FROM master_deal_files
                                                  WHERE master_deal_id = :m AND kind = ANY(:k) ORDER BY id"""),
                                         {"m": m.id, "k": list(KINDS)}).all():
        out.setdefault(u, {})[KINDS[kind]] = {"id": fid, "filename": name}
    return out


def _desk(db: Session, upd_no: int, state, u) -> dict:
    """Где комплект у бухгалтерии: состояние; если вернули — что не так; если бухгалтер спросила и аккаунт ещё не ответил —
    её вопрос (ответ — из карточки, `onec-reply`)."""
    if u is None:
        return {"state": state, "returned": None, "question": None}
    rows = db.execute(text("""SELECT kind, text FROM onec_desk_events WHERE upd_id = :k AND kind IN ('возврат', 'комментарий', 'ответ')
                               ORDER BY id"""), {"k": u.id}).all()
    returned = next((r.text for r in reversed(rows) if r.kind == "возврат"), None) if state == "возвращён" else None
    last = next((r for r in reversed(rows) if r.kind in ("комментарий", "ответ")), None)
    question = last.text if last is not None and last.kind == "комментарий" and state != "внесён" else None
    return {"state": state, "returned": returned, "question": question}


def doc_url(a, has_file: bool = False) -> Optional[str]:
    """Кнопка «ДС pdf»: собранный документ, а у ДС, подписанного вне системы, — загруженный файл клиента (сборка нашего
    документа для него запрещена: 12.11.2026 кнопка отказывала). Внешний ДС без файла — только ссылка на Диадок
    (`edo_link`, статус «уже в ЭДО»): скачивать нечего, кнопки нет."""
    from app.sales import annex_external as X
    if X.is_external(a):
        return f"/annexes/{a.id}/external-file" if has_file else None
    return f"/annexes/{a.id}/docx"


def build(db: Session, m) -> dict:
    from app.master_deal.models import MasterDealUpd
    from app.sales.models import SalesAnnex
    paper = ST.is_paper(db, m)
    channel = ST.channel_of(db, m)
    upd_rows = {u.upd_no: u for u in db.query(MasterDealUpd).filter(MasterDealUpd.master_deal_id == m.id)}
    upd_open = m.status in (ST.ISSUE, ST.WAIT_PAY, ST.WAIT_SCANS)        # УПД отмечают, когда они пришли из 1С
    files = _files(db, m)
    onec_files = _onec_files(db, m)
    annexes = (db.query(SalesAnnex).filter(SalesAnnex.master_deal_id == m.id)
               .order_by(SalesAnnex.sub_no.isnot(None), SalesAnnex.sub_no, SalesAnnex.id).all())
    kits = db.execute(text("""SELECT upd_no, annex_id, brand, service, gross, onec_at, onec_invoice_no, onec_upd_no, net,
                                      onec_invoice_date, onec_upd_date, onec_state, onec_gross FROM master_deal_upds
                               WHERE master_deal_id = :m ORDER BY upd_no"""), {"m": m.id}).all()
    codes = {r[0]: r[1] for r in db.execute(text("""SELECT x.annex_id, string_agg(d.code, ', ' ORDER BY d.code)
                                                     FROM sales_deal_annex_allocation x JOIN sales_deals d ON d.id = x.deal_id
                                                    WHERE x.annex_id = ANY(:a) GROUP BY x.annex_id"""), {"a": [a.id for a in annexes] or [0]})}
    from app.master_deal import to_annex as TA
    from app.sales import annex_external as X
    numbers = {x["id"]: x["number"] for x in TA.annexes_of(db, m)}      # черновик тоже со своим номером: «ДС № 2-01»
    ds = []
    for a in annexes:
        confirmed = a.no is not None
        scan = files.get(("a", a.id))
        ds.append({
            "annex_id": a.id, "number": numbers.get(a.id) or a.number or f"ДС id {a.id}",
            "kind": "extra" if a.kind == "addons" else "base", "primary": a.issue_kind == "primary",
            "services": _services(a.rows), "gross": float(a.total_amount or 0), "confirmed": confirmed,
            "net": round(sum(float(r.get("amount") or 0) for r in (a.rows or [])), 2) if a.rows is not None else None,
            "doc_url": doc_url(a, has_file=scan is not None), "scan": scan,
            "sign": DSG.view(db, a, channel),
            "external": X.is_external(a),                              # подписан вне системы: просмотра нашего документа нет
            "edo_link": a.edo_link if X.is_external(a) else None,     # внешний ДС уже в Диадоке (12.11.2026)
            "kits": [{"upd_no": k[0], "group": " · ".join(x for x in (k[2], k[3]) if x) or "весь пакет", "gross": float(k[4] or 0),
                      "net": float(k[8] or 0), "deals": (codes.get(a.id) or "").split(", ") if codes.get(a.id) else [], "onec": bool(k[5]),
                      "invoice_no": k[6], "upd_doc_no": k[7],
                      "invoice_date": k[9].isoformat() if k[9] else None, "upd_doc_date": k[10].isoformat() if k[10] else None,
                      "desk": _desk(db, k[0], k[11], upd_rows.get(k[0])), "onec_gross": k[12], "onec_files": onec_files.get(k[0], {}),
                      "scan": files.get(("u", k[0])), "sign": _upd_sign(db, upd_rows.get(k[0]), channel, upd_open)}
                     for k in kits if k[1] == a.id],
        })
    return {"paper": paper, "ds": ds, "summary": IS.state(db, m)}


def _upd_sign(db: Session, u, channel: Optional[str], open_: bool) -> dict:
    if u is None:
        return {"state": None, "channel": None, "next": []}
    v = DSG.view(db, u, channel)
    return v if open_ else {**v, "next": []}


def events(db: Session, m, limit: int = 10) -> list:
    rows = db.execute(text("""SELECT details, user_name, created_at FROM audit_log
                               WHERE entity_type = 'master_deal' AND entity_id = :m ORDER BY id DESC LIMIT :n"""),
                      {"m": m.id, "n": limit}).all()
    return [{"what": (d or "").split(": ", 1)[-1], "who": w or "система", "at": at.isoformat(timespec="seconds") if at else None}
            for d, w, at in rows]


def deal_price(db: Session, deal_id: int) -> Optional[dict]:
    """Цена за единицу и модель — из базовой строки МП сделки (первая не-доп строка)."""
    from app.sales import annex as annex_mod
    for r in annex_mod.plan_rows(db, [deal_id]):
        if r.get("kind") != "extra" and r.get("unit_price") is not None:
            return {"price": float(r["unit_price"]), "model": r.get("model") or ""}
    return None
