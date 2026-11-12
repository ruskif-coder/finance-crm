# -*- coding: utf-8 -*-
"""Возврат стадии мастер-сделки и «Обновить из сделки» (владелец 12.11.2026: «нужна штатная функция возврата стадии с настройкой
прав, ибо даже сейчас моментов, когда надо переделать, — масса»; переделывают от написания бренда после правки справочника до
ошибок в реквизитах со стороны 1С).

Куда (право `master_deals_revert`, причина обязательна) — на любую более раннюю стадию этого пакета из `TARGETS`:
  «ждём оплату» / «выставление» — ничего не сбрасываем: лишние отметки снимаются «отменить» у документа;
  «ждём 1С» (ошибка в документах 1С) — комплекты снова у бухгалтера: ответ 1С и отметки отправки/подписи УПД сняты; файлы 1С
     остаются, пока бухгалтер не заменит; ДС не трогаем — ошибка не в них;
  «согласование» (поменялись данные) — то же плюс ДС пакета снова «выпущен»: будут пересобраны «Обновить из сделки», круг
     подписи начинается заново; дальше «ДС проверены → в 1С».
До «черновика» не возвращаем (владелец 12.11.2026): смена состава пакета — не пересборка, а другая задача.
Сделки идут за пакетом: с «Оплаты» — обратно на «Подготовку ДС» (`deal_stages.follow`)."""
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.master_deal import doc_sign as DSG
from app.master_deal import status as ST

TARGETS = (ST.AGREE, ST.WAIT_1C, ST.ISSUE, ST.WAIT_PAY)
EVENT = "возврат стадии"          # событие подписи документа, не состояние


class RevertError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def targets(db: Session, m) -> list:
    """Куда этот пакет можно вернуть отсюда — по порядку стадий."""
    seq = ST.sequence(db, m)
    if m.status not in seq:
        return []
    return [s for s in seq[:seq.index(m.status)] if s in TARGETS]


RETIRED = "скан до возврата"     # скан переделанного документа: остаётся в пакете историей, подписью больше не считается


def _retire_scans(db: Session, m, annex_ids: list = (), upd_nos: list = ()) -> None:
    """Скан старого документа не должен засчитаться подписью нового (ревью 12.11.2026): отвязать от документа. Привязку
    снимаем совсем — уникальные индексы файлов пакета частичные по annex_id / upd_no, повторный возврат не упрётся в них."""
    db.execute(text("""UPDATE master_deal_files SET kind = :r, annex_id = NULL, upd_no = NULL
                       WHERE master_deal_id = :m AND kind IN ('скан ДС', 'скан УПД')
                         AND (annex_id = ANY(:a) OR upd_no = ANY(:u))"""),
               {"r": RETIRED, "m": m.id, "a": list(annex_ids) or [0], "u": list(upd_nos) or [0]})


def _reset_kits(db: Session, m, user, reason: str) -> tuple:
    """Комплекты — снова у бухгалтера и не у клиента. (сколько комплектов, сколько из них уже было внесено в 1С)."""
    from app.master_deal.models import MasterDealUpd
    kits = db.query(MasterDealUpd).filter(MasterDealUpd.master_deal_id == m.id).all()
    in_1c = sum(1 for k in kits if k.onec_at is not None)          # возвращённые аккаунту в 1С не вносились
    for k in kits:
        k.onec_state, k.onec_at = None, None
        if k.sign_state is not None:
            DSG._write_event(db, k, state=EVENT, channel=k.sign_channel, source="вручную", reason=reason, file_id=None,
                             by_user=getattr(user, "id", None))
        k.sign_state, k.sign_channel = None, None
    _retire_scans(db, m, upd_nos=[k.upd_no for k in kits])
    return len(kits), in_1c


def _reissue_ds(db: Session, m, user, reason: str) -> int:
    from app.sales import annex_external as X
    from app.sales.models import SalesAnnex
    done = []
    for a in db.query(SalesAnnex).filter(SalesAnnex.master_deal_id == m.id, SalesAnnex.no.isnot(None)):
        # подписан вне системы, или подписанный ДС старта без снимка строк — документ клиента, пересборки не будет
        if X.is_external(a) or a.rows is None:
            continue
        DSG.issued(db, a, user, reason=f"{EVENT}: {reason}")
        done.append(a.id)
    _retire_scans(db, m, annex_ids=done)
    return len(done)


def _deals_back(db: Session, m, was: str, user) -> dict:
    """Сделки за пакетом: стадии пакета до «выставления» стадий сделок не двигают — сделки встают на «Подготовку ДС»."""
    from app.master_deal import deal_stages as DST
    to = m.status
    if was in DST.STAGE and to not in DST.STAGE and was != ST.ISSUE:
        m.status = ST.ISSUE
        out = DST.follow(db, m, was, user)
        m.status = to
        return out
    return DST.follow(db, m, was, user)


def revert(db: Session, m, to: str, user, reason: str) -> dict:
    """Вернуть пакет на стадию `to`. Без commit — его делает ручка. → {was, kits, in_1c, ds, deals}."""
    reason = (reason or "").strip()
    if not reason:
        raise RevertError(400, "Возврат стадии — с причиной: что переделываем")
    if to == ST.DRAFT:
        raise RevertError(409, "До «черновика» не возвращаем: смена состава пакета — через «Вернуть в раскладку», пока ДС не подтверждены")
    if to not in targets(db, m):
        raise RevertError(409, f"Из «{m.status}» в «{to}» вернуть нельзя — только на более раннюю стадию: "
                               + (", ".join(targets(db, m)) or "некуда"))
    was = m.status
    kits = in_1c = ds = 0
    if to in (ST.WAIT_1C, ST.AGREE):
        kits, in_1c = _reset_kits(db, m, user, reason)
    if to == ST.AGREE:
        ds = _reissue_ds(db, m, user, reason)
    m.status, m.updated_at = to, datetime.utcnow()
    db.flush()
    deals = _deals_back(db, m, was, user)
    return {"was": was, "kits": kits, "in_1c": in_1c, "ds": ds, "deals": deals}


def _own_annexes(db: Session, m) -> list:
    from app.sales import annex_external as X
    from app.sales.models import SalesAnnex
    rows = (db.query(SalesAnnex).filter(SalesAnnex.master_deal_id == m.id)
            .order_by(SalesAnnex.sub_no.isnot(None), SalesAnnex.sub_no, SalesAnnex.id).all())
    return [a for a in rows if not X.is_external(a) and a.rows is not None]     # подписанный первичный без снимка — как был


def _kits_of(db: Session, m, annex_id: int) -> list:
    from app.master_deal.models import MasterDealUpd
    return (db.query(MasterDealUpd).filter(MasterDealUpd.master_deal_id == m.id, MasterDealUpd.annex_id == annex_id)
            .order_by(MasterDealUpd.upd_no).all())


def refresh(db: Session, m, user) -> dict:
    """«Обновить из сделки»: ДС и комплекты пакета — по текущим данным сделок и справочников, номера ДС, даты и номера УПД
    прежние; правленные руками основания остаются. Только на «согласовании». → {ds: [номера]}."""
    from app.annex_tpl import document as tpl_doc
    from app.master_deal import layout as LY
    from app.master_deal import to_annex as TA
    from app.models import Contract
    if m.status != ST.AGREE:
        raise RevertError(409, "Обновить из сделки можно на «согласовании» — сначала верните пакет на эту стадию")
    lay = LY.layout(db, m, with_src=True)
    own = _own_annexes(db, m)
    if len(own) != len(lay["ds"]) or any((a.kind == "addons") != (ds["kind"] == "addons") for a, ds in zip(own, lay["ds"])):
        raise RevertError(409, f"Состав ДС изменился (в пакете {len(own)}, по данным {len(lay['ds'])}) — обновить нельзя, "
                               "это смена состава пакета")
    c = db.get(Contract, m.contract_id)
    done = []
    for a, ds in zip(own, lay["ds"]):
        kits = _kits_of(db, m, a.id)
        if len(kits) != len(ds["upds"]):
            raise RevertError(409, f"{a.number or 'ДС'}: комплектов {len(kits)}, по данным {len(ds['upds'])} — обновить нельзя")
        a.rows, a.vat_rate = TA._snapshot(ds), lay["vat_rate"]
        deal_ids = TA.allocate(db, a, ds, lay["vat_rate"])
        for k, u in zip(kits, ds["upds"]):
            k.brand, k.service, k.net, k.vat, k.gross = u["brand"], u["service"], u["net"], u["vat"], u["gross"]
        db.flush()
        a.total_amount = tpl_doc.live(db, c, tpl_doc.version_row(db, a.template_version_id), a, deal_ids)["amount"]
        if a.no is not None:
            from app.routers.annexes import rebuild_frozen
            try:
                rebuild_frozen(db, a, c)
            except Exception as e:      # HTTPException сборки — понятным отказом
                raise RevertError(getattr(e, "status_code", 409), f"{a.number}: не пересобрался — {getattr(e, 'detail', e)}")
            DSG.issued(db, a, user, reason="обновлён из сделки")
        done.append(a.number or f"ДС id {a.id}")
    db.flush()
    return {"ds": done}


def agreed(db: Session, m) -> None:
    """«ДС проверены → в 1С»: после возврата на «согласование» ДС уже с номерами — подтверждать нечего, пакет идёт дальше."""
    from app.master_deal import to_annex as TA
    if m.status != ST.AGREE:
        raise RevertError(409, "Пакет не на «согласовании»")
    if not TA.after_confirm(db, m):
        raise RevertError(409, "Не все ДС пакета подтверждены — подтвердите их («Подтвердить ДС пакета»)")
    db.flush()


def unconfirmed(db: Session, m) -> int:
    return db.execute(text("SELECT count(*) FROM sales_annexes WHERE master_deal_id = :m AND no IS NULL"), {"m": m.id}).scalar() or 0


def redo_kit(db: Session, m, k, user, reason: str) -> dict:
    """«Вернуть на переделку» из «Закрывающих документов» (владелец 12.11.2026): ОДИН внесённый комплект снова у бухгалтера —
    ответ 1С и отметки отправки сняты, соседние внесённые не трогаем. Пакет дальше «ждём 1С» возвращается туда (очередь
    бухгалтера берёт пакеты от «ждём 1С»), сделки — на «Подготовку ДС»; внесёт заново — пакет пойдёт дальше сам."""
    reason = (reason or "").strip()
    if not reason:
        raise RevertError(400, "Вернуть на переделку — с причиной: что не так в документах")
    if k.onec_at is None and k.onec_state is None:
        raise RevertError(409, f"УПД № {k.upd_no} ещё не внесён в 1С — переделывать нечего")
    _retire_scans(db, m, upd_nos=[k.upd_no])
    was = m.status
    k.onec_state, k.onec_at = None, None
    if k.sign_state is not None:
        DSG._write_event(db, k, state=EVENT, channel=k.sign_channel, source="вручную", reason=reason, file_id=None,
                         by_user=getattr(user, "id", None))
    k.sign_state, k.sign_channel = None, None
    deals = {"moved": [], "skipped": []}
    if was in (ST.ISSUE, ST.WAIT_PAY, ST.WAIT_SCANS, ST.ARCHIVE):
        m.status, m.updated_at = ST.WAIT_1C, datetime.utcnow()
        db.flush()
        deals = _deals_back(db, m, was, user)
    db.flush()
    return {"was": was, "kits": 1, "in_1c": 1, "ds": 0, "deals": deals}
