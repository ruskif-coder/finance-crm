# -*- coding: utf-8 -*-
"""Что бухгалтер делает с комплектом: внести ответ 1С, вернуть аккаунту с комментарием, принять «исправлено», прокомментировать.
Единственное место, где меняется `master_deal_upds.onec_state`. Функции только `flush` — коммит и журнал делает роутер.
Ошибки — `DeskError` с кодом и текстом для человека."""
import json
import logging
import math
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.master_deal import status as ST
from app.master_deal.models import MasterDealUpd, OnecDeskEvent

log = logging.getLogger(__name__)

RETURNED, DONE = "возвращён", "внесён"
TOLERANCE = 1.0          # решение 42: расхождение с 1С до 1 ₽ принимаем
NO_LEN = 40              # master_deal_upds.onec_invoice_no / onec_upd_no — String(40)
OPEN = (ST.WAIT_1C, ST.ISSUE, ST.WAIT_PAY, ST.WAIT_SCANS)      # внести и поправить можно, пока пакет не в архиве
FIELDS = (("invoice_no", "№ счёта"), ("invoice_date", "дата счёта"), ("upd_no", "№ УПД"), ("upd_date", "дата УПД"),
          ("net", "сумма без НДС"), ("vat", "НДС"), ("gross", "сумма с НДС"))


class DeskError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _notify(db: Session, key: str, m, **kw) -> None:
    from app.notify import closing as CN
    CN.onec_desk(db, key, m, **kw)


def _event(db: Session, k, kind: str, text_: Optional[str], user) -> None:
    db.add(OnecDeskEvent(upd_id=k.id, kind=kind, text=text_, by_user=getattr(user, "id", None)))


def _clean(v) -> Optional[str]:
    return (str(v).strip() or None) if v is not None else None


def kits(db: Session, m) -> list:
    return db.query(MasterDealUpd).filter(MasterDealUpd.master_deal_id == m.id).order_by(MasterDealUpd.upd_no).all()


def pending(db: Session, m) -> list:
    """Комплекты пакета, по которым ответ 1С ещё не внесён — «УПД № n»."""
    return [f"УПД № {k.upd_no}" for k in kits(db, m) if k.onec_state != DONE]


def enter(db: Session, m, k, data: dict, user) -> dict:
    """Внести ответ 1С по комплекту. Повтор по внесённому — правка. Внесены все комплекты — пакет уходит в «выставление»
    (если у договора задан канал), по счёту рождается операция «план поступлений» от суммы 1С."""
    if m.status not in OPEN:
        raise DeskError(409, "Документы 1С вносятся, когда ДС пакета подтверждены и пакет ждёт 1С" if m.status != ST.ARCHIVE
                        else "Пакет в архиве — документы закрытого пакета не меняются")
    missing = [label for f, label in FIELDS if data.get(f) is None or (isinstance(data.get(f), str) and not data[f].strip())]
    if missing:
        raise DeskError(400, "Не заполнено: " + ", ".join(missing))
    for f, label in (("invoice_no", "№ счёта"), ("upd_no", "№ УПД")):
        if len(str(data[f]).strip()) > NO_LEN:
            raise DeskError(400, f"{label} длиннее {NO_LEN} знаков — впишите только номер, без «Счёт на оплату … от …»")
    try:
        net, vat, gross = (round(float(data[f]), 2) for f in ("net", "vat", "gross"))
    except (TypeError, ValueError):
        raise DeskError(400, "Суммы — числами")
    if not all(math.isfinite(x) for x in (net, vat, gross)) or net <= 0 or vat < 0 or gross <= 0:
        raise DeskError(400, "Суммы — положительные числа")
    if abs(net + vat - gross) > TOLERANCE:
        raise DeskError(400, f"Без НДС + НДС = {net + vat:,.2f}, а сумма с НДС {gross:,.2f} — проверьте цифры".replace(",", " "))
    comment = _clean(data.get("comment"))
    diff = round(gross - float(k.gross or 0), 2)
    if abs(diff) > TOLERANCE and not comment:
        raise DeskError(400, f"Сумма 1С расходится с пакетом на {diff:+,.2f} ₽ — больше 1 ₽: напишите причину в комментарии"
                        .replace(",", " "))
    again = k.onec_state == DONE
    k.onec_invoice_no, k.onec_invoice_date = _clean(data["invoice_no"]), data["invoice_date"]
    k.onec_upd_no, k.onec_upd_date = _clean(data["upd_no"]), data["upd_date"]
    k.onec_net, k.onec_vat, k.onec_gross = net, vat, gross
    k.onec_at = k.onec_at if again and k.onec_at else datetime.utcnow()
    k.onec_by = getattr(user, "id", None)
    k.onec_state = DONE
    _event(db, k, "правка" if again else "внесено", comment, user)
    db.flush()
    op_error = _bridge(db, m, k)
    return {"moved": _advance(db, m, user, notify=not again), "again": again, "operation_error": op_error}


def _bridge(db: Session, m, k) -> Optional[str]:
    """Операция «план поступлений» по счёту. Сбой не отменяет внесённое бухгалтером (номер в 1С уже есть), но и не молчит:
    текст уходит в ответ — экран покажет, что операция не создана (ревью 05.11.2026)."""
    from app.master_deal import bridge as BR
    try:
        with db.begin_nested():
            BR.sync_kit(db, m, k)
        return None
    except Exception as e:  # noqa: BLE001
        log.exception("%s: операция по УПД № %s не сформирована", m.code, k.upd_no)
        return f"Внесено, но операция по счёту не создана: {e}. Сообщите администратору"


def _advance(db: Session, m, user, notify: bool = True) -> bool:
    """Все комплекты внесены → «выставление». Канала у договора нет — пакет ждёт, «что нужно сейчас» скажет, чего не хватает.
    «Внесены все» уходит аккаунту один раз — на последнем внесении, не на правках."""
    if m.status != ST.WAIT_1C or pending(db, m):
        return False
    if notify:
        _notify(db, "master_onec_done", m, user=user)
    if not ST.channel_of(db, m):
        return False
    from app.master_deal import deal_stages as DST
    was = m.status
    m.status, m.updated_at = ST.ISSUE, datetime.utcnow()
    db.flush()
    DST.follow(db, m, was, user)
    return True


def give_back(db: Session, m, k, text_: Optional[str], user, reason: Optional[str] = None, snap: Optional[dict] = None) -> None:
    """Вернуть комплект аккаунту: неверные реквизиты, основание, сумма. Пакет остаётся в «ждём 1С». reason — причина-подсказка
    экрана («реквизиты покупателя», …), snap — заявка на момент возврата: из неё «было → стало», когда аккаунт пришлёт снова."""
    t = ": ".join(x for x in (_clean(reason), _clean(text_)) if x)
    if not t:
        raise DeskError(400, "Выберите причину или напишите, что не так — иначе аккаунт не поймёт, что править")
    if k.onec_state == DONE:
        raise DeskError(409, "Комплект уже внесён — исправьте внесённое, а не возвращайте")
    if m.status != ST.WAIT_1C:
        raise DeskError(409, "Вернуть можно, пока пакет ждёт 1С")
    k.onec_state = RETURNED
    db.add(OnecDeskEvent(upd_id=k.id, kind="возврат", text=t, by_user=getattr(user, "id", None), snapshot=snap))
    db.flush()
    _notify(db, "master_onec_returned", m, user=user, upd_no=k.upd_no, text=t)


def fixed(db: Session, m, k, text_: Optional[str], user) -> None:
    """Аккаунт исправил — комплект снова в очереди бухгалтера."""
    if k.onec_state != RETURNED:
        raise DeskError(409, "Комплект не возвращался бухгалтером — исправлять нечего")
    k.onec_state = None
    _event(db, k, "исправлено", _clean(text_), user)
    db.flush()


def comment(db: Session, k, text_: Optional[str], user, m=None) -> None:
    """Вопрос бухгалтера аккаунту без возврата комплекта; аккаунту уходит уведомление, если передан пакет."""
    t = _clean(text_)
    if not t:
        raise DeskError(400, "Пустой комментарий")
    _event(db, k, "комментарий", t, user)
    db.flush()
    if m is not None:
        _notify(db, "master_onec_question", m, user=user, upd_no=k.upd_no, text=t)


def reply(db: Session, m, k, text_: Optional[str], user) -> None:
    """Ответ аккаунта бухгалтеру (из карточки мастер-сделки): в очереди у заявки появится метка «ответ»."""
    t = _clean(text_)
    if not t:
        raise DeskError(400, "Пустой ответ")
    if m.status == ST.ARCHIVE:
        raise DeskError(409, "Пакет в архиве")
    _event(db, k, "ответ", t, user)
    db.flush()


DRAFT_KEYS = ("invNo", "invDate", "updNo", "updDate", "net", "vat", "gross", "fromXml", "xml", "comment")
DRAFT_TEXT = ("invNo", "invDate", "updNo", "updDate", "net", "vat", "gross", "comment")
DRAFT_MAX = 20_000


def save_draft(db: Session, m, k, form: dict, user) -> datetime:
    """Черновик формы бухгалтера: только поля формы (файлы лежат в master_deal_files), строки — как ввёл человек."""
    if k.onec_state == DONE:
        raise DeskError(409, "Заявка уже внесена — черновик не нужен")
    if m.status not in OPEN:
        raise DeskError(409, "Пакет не ждёт документов 1С")
    clean = {key: form.get(key) for key in DRAFT_KEYS if key in form}
    for key in DRAFT_TEXT:
        if clean.get(key) is not None and not isinstance(clean[key], str):
            clean[key] = str(clean[key])
    if len(json.dumps(clean, ensure_ascii=False)) > DRAFT_MAX:
        raise DeskError(413, "Черновик слишком большой")
    k.onec_draft, k.onec_draft_at, k.onec_draft_by = clean, datetime.utcnow(), getattr(user, "id", None)
    db.flush()
    return k.onec_draft_at


def mark_seen(db: Session, k) -> None:
    k.onec_seen_at = datetime.utcnow()
    db.flush()


def check_number(db: Session, kind: str, no: str, exclude_kit: Optional[int]) -> Optional[dict]:
    """№ счёта / УПД уже есть в этом году — среди внесённых или в черновике другой заявки (предупреждение, не запрет)."""
    no = (no or "").strip()
    if not no or kind not in ("inv", "upd"):
        return None
    col, dcol, dkey = ("onec_invoice_no", "onec_invoice_date", "invNo") if kind == "inv" else ("onec_upd_no", "onec_upd_date", "updNo")
    r = db.execute(text(f"""SELECT m.code, k.onec_state, k.onec_at, k.upd_no,
                                   (SELECT count(*) FROM master_deal_upds x WHERE x.master_deal_id = m.id) AS n
                              FROM master_deal_upds k JOIN master_deals m ON m.id = k.master_deal_id
                             WHERE k.id IS DISTINCT FROM :ex
                               AND ((k.onec_state = :d AND k.{col} = :no
                                     AND date_part('year', coalesce(k.{dcol}, k.onec_at)) = date_part('year', now()))
                                    OR (k.onec_state IS DISTINCT FROM :d AND k.onec_draft ->> :dk = :no))
                             ORDER BY (k.onec_state = :d) DESC, k.onec_at DESC NULLS LAST LIMIT 1"""),
                   {"ex": exclude_kit, "no": no, "d": DONE, "dk": dkey}).first()
    if r is None:
        return None
    code = r.code if r.n == 1 else f"{r.code} · УПД {r.upd_no}"
    at = r.onec_at.replace(tzinfo=timezone.utc).isoformat() if r.onec_at and r.onec_state == DONE else None
    return {"code": code, "status": "done" if r.onec_state == DONE else "wait", "at": at}


def submit(db: Session, m, k, form: dict, req: dict, user, closed_until=None) -> dict:
    """«Внести» с экрана: те же правила, что на экране (`rules.evaluate`, порт accDocsLogic), фронту не верим. Файлы и XML —
    с сервера: PDF и XML лежат в master_deal_files, покупатель и договор XML — из разбора самого файла."""
    from app.onec_desk import files as OF
    from app.onec_desk import rules as R
    from app.onec_desk import xmlparse as XP
    fl = OF.files_of(db, m, k)
    xml = XP.parse(OF.read(OF.get(db, m, k, fl["xml"]["id"])), req["contract"]["no"], req["basis"]) if fl.get("xml") else None

    def g(key: str) -> str:
        return str(form.get(key) or "").strip()

    f_ = R.Form(inv_no=g("invNo"), inv_date=g("invDate"), inv_pdf_id=(fl.get("invoice") or {}).get("id"),
                upd_no=g("updNo"), upd_date=g("updDate"), net=g("net"), vat=g("vat"), gross=g("gross"),
                upd_pdf_id=(fl.get("upd") or {}).get("id"), upd_xml_id=(fl.get("xml") or {}).get("id"),
                xml_buyer_inn=xml["buyer"]["inn"] if xml else None, xml_buyer_kpp=xml["buyer"]["kpp"] if xml else None,
                xml_contract=xml["contract"] if xml else None, xml_basis=xml["basis"] if xml else None, comment=g("comment"))
    exp = {key: R.Decimal(str(round(sum(float(x[key]) for x in req["lines"]), 2))) for key in ("net", "vat", "gross")}
    who = SimpleNamespace(buyer_inn=req["buyer"]["inn"], buyer_kpp=req["buyer"]["kpp"],
                          contract_no=req["contract"]["no"], ds_signed=req["ds_signed"], basis=req["basis"])
    pe = datetime.fromisoformat(req["period"]["to"]).date() if req["period"]["to"] else None
    res = R.evaluate(who, f_, expected=exp, dup_inv=None, dup_upd=None, closed_until=closed_until, period_end=pe)
    if not res.ready:
        raise DeskError(409, "Не хватает: " + ", ".join(label for label, _ in res.missing))
    out = enter(db, m, k, {"invoice_no": g("invNo"), "invoice_date": R.ru_date(g("invDate")), "upd_no": g("updNo"),
                           "upd_date": R.ru_date(g("updDate")), "net": float(R.parse_money(g("net"))),
                           "vat": float(R.parse_money(g("vat"))), "gross": float(R.parse_money(g("gross"))),
                           "comment": g("comment") or None}, user)
    k.onec_draft = None
    db.flush()
    return {**out, "warns": res.warns}


def events(db: Session, k) -> list:
    rows = db.execute(text("""SELECT e.kind, e.text, e.source, e.at, u.name FROM onec_desk_events e
                               LEFT JOIN users u ON u.id = e.by_user WHERE e.upd_id = :k ORDER BY e.id"""), {"k": k.id}).all()
    return [{"kind": r.kind, "text": r.text, "source": r.source, "who": r.name or "система",
             "at": r.at.isoformat(timespec="seconds") if r.at else None} for r in rows]


def last_return(db: Session, m) -> Optional[dict]:
    """Последний возврат по пакету, ещё не исправленный: для «что нужно сейчас» и реестра."""
    r = db.execute(text("""SELECT k.upd_no, e.text FROM master_deal_upds k
                             JOIN onec_desk_events e ON e.upd_id = k.id AND e.kind = 'возврат'
                            WHERE k.master_deal_id = :m AND k.onec_state = :s ORDER BY e.id DESC LIMIT 1"""),
                   {"m": m.id, "s": RETURNED}).first()
    return {"upd_no": r.upd_no, "text": r.text} if r else None
