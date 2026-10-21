# -*- coding: utf-8 -*-
"""ДС по шаблону: какой шаблон взять, живая модель черновика, замороженный документ подтверждённого (спринт 2, 14.10.2026).

Три состояния приложения:
  · черновик — модель собирается ЖИВОЙ по текущей версии шаблона договора (аккаунт видит то, что будет, и «базовый изменился»);
  · подтверждённое — документ ЗАМОРОЖЕН в `sales_annexes.blocks` целиком (тексты, таблица, значения, стороны, суммы) вместе
    с `template_version_id`: правка шаблона собранные ДС не меняет;
  · собранное до конструктора (подтверждено, снимка нет) — «legacy»: показывается прежним документом, новая сборка к нему не применяется.
"""
from datetime import date
from typing import Optional

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.annex_tpl import service as S
from app.annex_tpl.assemble import assemble
from app.annex_tpl.models import AnnexTplTemplate, AnnexTplVersion
from app.sales.models import SalesAnnex

OLD_NO_TEMPLATE = "не задан шаблон формулировки услуги"   # требование старого модуля: шаблон по плательщику (заменён конструктором)
LEGACY_REASON = "Собрано до конструктора шаблонов — документ показан прежним расчётом и не пересобирается"


def resolve(db: Session, contract) -> tuple:
    """(текущая версия шаблона договора, причина отказа). Кастомный договора, иначе базовый его формата."""
    r = S.resolve_for_contract(db, contract)
    if r["template"] is None:
        return None, r["reason"]
    v = S.current(db, r["template"].id)
    return (v, None) if v else (None, "У шаблона нет версий")


def is_frozen(annex) -> bool:
    """Замороженный документ — полная модель в `blocks`; у черновика там только правки аккаунта `{"edits": {...}}`."""
    return isinstance(annex.blocks, dict) and "blocks" in annex.blocks


def edits_of(annex) -> dict:
    return dict((annex.blocks or {}).get("edits") or {}) if isinstance(annex.blocks, dict) else {}


def previous_defaults(db: Session, annex, contract, limit: int = 30) -> dict:
    """Тексты по умолчанию из ПРОШЛЫХ ДС этого договора: {ключ: {text, from}}. Берётся самая свежая правка каждого ключа (пункт зоны аккаунта или
    `closing_basis`); явный сброс «по шаблону» (None) обрывает наследование — старее него не смотрим. Привязка по id пункта шаблона."""
    aid = getattr(annex, "id", None)
    if aid is None:
        return {}
    out, stop = {}, set()
    rows = (db.query(SalesAnnex).filter(SalesAnnex.contract_id == contract.id, SalesAnnex.id < aid)
            .order_by(SalesAnnex.id.desc()).limit(limit).all())
    for a in rows:
        for k, v in edits_of(a).items():
            if k in out or k in stop:
                continue
            if v is None:
                stop.add(k)
            elif isinstance(v, str) and v.strip():
                out[k] = {"text": v, "from": a.number or f"черновик #{a.id}"}
    return out


def live(db: Session, contract, version, annex, deal_ids) -> dict:
    return assemble(db, contract, version, period_from=annex.period_from, period_to=annex.period_to,
                    deal_ids=deal_ids, amount=annex.total_amount, no=annex.no or _master_no(db, annex), edits=edits_of(annex),
                    doc_date=annex.date, defaults=previous_defaults(db, annex, contract),
                    rows_override=getattr(annex, "rows", None), sub_no=getattr(annex, "sub_no", None))


def _master_code(db: Session, annex):
    """Код мастер-сделки ДС — в колонтитул каждой страницы (владелец 19.10.2026): бумажный экземпляр и скан сами находят свой пакет."""
    mid = getattr(annex, "master_deal_id", None)
    if not mid:
        return None
    from app.master_deal.models import MasterDeal
    m = db.get(MasterDeal, mid)
    return m.code if m else None


def _master_no(db: Session, annex):
    """Номер ДС пакета до подтверждения — из раскладки: последний актуальный по договору + 1."""
    mid = getattr(annex, "master_deal_id", None)
    if not mid:
        return None
    from app.master_deal.models import MasterDeal
    m = db.get(MasterDeal, mid)
    return (m.start_no + 1) if m and m.start_no is not None else None


def freeze(model: dict) -> dict:
    """Документ для хранения: даты и числа приводятся к JSON один раз, при подтверждении."""
    return jsonable_encoder(model)


def template_state(db: Session, contract) -> Optional[dict]:
    """Для кастомного шаблона договора: изменилась ли база (уведомление при генерации, п. 46 плана)."""
    own = S.custom_of(db, contract.id)
    if not own:
        return None
    st = S.base_state(db, own)
    return {**st, "changes": S.base_changes(db, own) if st["changed"] else [], "template_id": own.id}


def upgrade_frozen(db: Session, annex, contract, deal_ids) -> dict:
    """Замороженный документ в виде, который понимает экран. Документы, замороженные до появления «основания закрывающих» (14.10.2026),
    не несут `closing_basis`, `edits` и коротких значений: их достраиваем по текущим данным сделки — текст самого ДС при этом не трогается."""
    m = dict(annex.blocks)
    # Текст пункта С подстановками для редактора: у документов, замороженных раньше, поля `source_text`/`edited` не было — окно правки открывалось пустым.
    edits = m.get("edits") or {}
    m["blocks"] = [b if b.get("sys") or "source_text" in b else
                   {**b, "source_text": edits.get(b.get("id"), b.get("template_text") or b.get("text") or ""),
                    "edited": b.get("id") in edits and b.get("zone") == "acc"} for b in m.get("blocks", [])]
    if "closing_basis" in m and "edits" in m:
        return m
    version = version_row(db, annex.template_version_id) or resolve(db, contract)[0]
    if version is None:
        return m
    lv = live(db, contract, version, annex, deal_ids)
    m["values"] = {**lv["values"], **(m.get("values") or {})}
    m["edits"] = edits
    m["closing_basis"] = lv["closing_basis"]
    return m


def model_of(db: Session, annex, contract, deal_ids) -> dict:
    """Что показать на экране: {model, frozen, legacy, reason, template_state}."""
    if is_frozen(annex):
        return {"model": jsonable_encoder(upgrade_frozen(db, annex, contract, deal_ids)), "frozen": True, "legacy": False, "reason": None, "template_state": None}
    if annex.no is not None:                                   # подтверждено до конструктора
        return {"model": None, "frozen": False, "legacy": True, "reason": LEGACY_REASON, "template_state": None}
    version, reason = resolve(db, contract)
    if version is None:
        return {"model": None, "frozen": False, "legacy": False, "reason": reason, "template_state": None}
    return {"model": jsonable_encoder(live(db, contract, version, annex, deal_ids)), "frozen": False, "legacy": False,
            "reason": None, "template_state": template_state(db, contract)}


def version_row(db: Session, version_id: Optional[int]) -> Optional[AnnexTplVersion]:
    return db.query(AnnexTplVersion).filter_by(id=version_id).first() if version_id else None


def template_labels(db: Session, version_ids) -> dict:
    """{id версии: {title, version, scope}} — для колонки «Шаблон» реестра одним запросом."""
    ids = [i for i in set(version_ids) if i]
    if not ids:
        return {}
    out = {}
    for v, t in (db.query(AnnexTplVersion, AnnexTplTemplate).join(AnnexTplTemplate, AnnexTplTemplate.id == AnnexTplVersion.template_id)
                 .filter(AnnexTplVersion.id.in_(ids)).all()):
        base = db.query(AnnexTplTemplate).filter_by(id=t.base_template_id).first() if t.base_template_id else None
        out[v.id] = {"title": t.title or (base.title if base else None), "version": v.version, "scope": t.scope}
    return out


def bridge_old_doc(db: Session, annex, contract, doc: dict, deal_ids) -> dict:
    """Старые PDF и DOCX строятся из `annex.build`, пока генерация не переписана (п. 57–63 плана). Мост: пункт 1 берётся из шаблона ДС
    (замороженного у подтверждённого, живого у остальных), устаревшее требование «шаблон формулировки по плательщику» снимается, а чего не
    хватает по новому документу, добавляется к списку. Без шаблона у договора документ остаётся как был — со старым замечанием."""
    if is_frozen(annex):
        model, live_model = upgrade_frozen(db, annex, contract, deal_ids), False
    else:
        version, _ = resolve(db, contract)
        model = jsonable_encoder(live(db, contract, version, annex, deal_ids)) if version else None
        live_model = True
    if not model:
        return doc
    texts = [b.get("text") for b in model.get("blocks", []) if not b.get("sys")]
    doc["body"] = texts[0] if texts else ""
    # Основание для закрывающих документов — в тот же словарь: файл «для клиента» печатает его после ДС (одним документом на согласование).
    doc["closing_basis"] = ((model.get("closing_basis") or {}).get("text")) or ""
    if getattr(annex, "rows", None) is not None:
        doc = _master_doc(db, annex, contract, doc, model)
    doc["master_code"] = _master_code(db, annex)
    doc["missing"] = [m for m in (doc.get("missing") or []) if m != OLD_NO_TEMPLATE]
    if live_model:
        doc["missing"] += [m["text"] for m in model.get("missing", []) if m["text"] not in doc["missing"]]
    return doc


MP_MISMATCH = "сумма приложения "


def _master_doc(db: Session, annex, contract, doc: dict, model: dict) -> dict:
    """ДС мастер-сделки в выгрузке (15.10.2026): строки — снимок раскладки из модели (а не МП заново), заголовки групп строкой,
    номер «ДС № N» / «N-01», суммы — документа, текст — «ДС» вместо «Приложения», основания — по одному на каждую УПД этого ДС."""
    from app.master_deal.models import MasterDealUpd
    from app.sales.annex import rub_phrase
    groups = (model.get("table") or {}).get("groups") or []
    rows = []
    for g in groups:
        if len(groups) > 1 or g.get("brand"):
            rows.append({"group_title": g.get("brand") or "весь пакет"})
        for r in g.get("rows") or []:        # модель прошла через JSON — даты строк вернуть датами для генератора файла
            rows.append({**r, **{k: date.fromisoformat(r[k][:10]) for k in ("date_from", "date_to") if isinstance(r.get(k), str) and r.get(k)}})
    amount, vat = float(model.get("amount") or 0), float(model.get("vat") or 0)
    doc.update({"rows": rows, "number": model.get("number"), "amount": amount, "vat": vat,
                "amount_words": rub_phrase(amount), "vat_words": rub_phrase(vat), "is_master": True})
    # Сверка «сумма ↔ медиаплан» старой сборки к ДС пакета не относится: его строки — снимок итоговой сверки (по факту, со скидкой СК),
    # а не МП. Сумма ДС пакета сверяется со своей таблицей (`consistency` модели). Без этого черновик ДС пакета не скачивался (21.10.2026).
    doc["missing"] = [x for x in (doc.get("missing") or []) if not str(x).startswith(MP_MISMATCH)]
    doc["missing"] += list((model.get("consistency") or {}).get("details") or [])
    upds = db.query(MasterDealUpd).filter(MasterDealUpd.annex_id == annex.id).order_by(MasterDealUpd.upd_no).all()
    if upds:
        sep = chr(10) * 2
        doc["closing_basis"] = sep.join(
            f"УПД № {k.upd_no}" + (f" ({' · '.join(x for x in (k.brand, k.service) if x)})" if (k.brand or k.service) else "")
            + f": {upd_closing(model, k, annex.rows)['text']}" for k in upds)
    return doc


def _closing_template_for(rows) -> str:
    """Шаблон основания по составу ДС — одна функция с конструктором (`assemble.closing_template_for`)."""
    from app.annex_tpl.assemble import closing_template_for
    return closing_template_for(rows)


def upd_closing(model: dict, k, rows=None) -> dict:
    """Основание УПД мастер-сделки — то же «основание для закрывающих», что в конструкторе ДС (владелец 19.10.2026): шаблон с подстановками,
    значения — своего ДС, бренд — свой у каждого УПД. Порядок: свой текст УПД → основание, поправленное в конструкторе этого ДС или
    унаследованное от прошлого ДС договора → шаблон по составу ДС."""
    from app.annex_tpl.assemble import closing_resolve
    cb = model.get("closing_basis") or {}
    values = dict(model.get("values") or {})
    if getattr(k, "brand", None):
        values["бренд_название"] = k.brand.split(" / ")[-1].strip()      # «Grindeks / Милдронат» → «Милдронат», как в конструкторе
    if getattr(k, "basis_text", None):
        return closing_resolve(k.basis_text, values, True)
    if cb.get("edited") or cb.get("inherited_from"):
        return closing_resolve(cb["template"], values, False, cb.get("inherited_from") or "основание этого ДС")
    return closing_resolve(_closing_template_for(rows), values, False)
