# -*- coding: utf-8 -*-
"""ДС по шаблону: какой шаблон взять, живая модель черновика, замороженный документ подтверждённого (спринт 2, 14.10.2026).

Три состояния приложения:
  · черновик — модель собирается ЖИВОЙ по текущей версии шаблона договора (аккаунт видит то, что будет, и «базовый изменился»);
  · подтверждённое — документ ЗАМОРОЖЕН в `sales_annexes.blocks` целиком (тексты, таблица, значения, стороны, суммы) вместе
    с `template_version_id`: правка шаблона собранные ДС не меняет;
  · собранное до конструктора (подтверждено, снимка нет) — «legacy»: показывается прежним документом, новая сборка к нему не применяется.
"""
import re
from datetime import date
from typing import Optional

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.annex_tpl import doc_kind as DK
from app.annex_tpl import service as S
from app.annex_tpl.assemble import assemble
from app.annex_tpl.models import AnnexTplTemplate, AnnexTplVersion
from app.sales.models import SalesAnnex

OLD_NO_TEMPLATE = "не задан шаблон формулировки услуги"   # требование старого модуля: шаблон по плательщику (заменён конструктором)
LEGACY_REASON = "Собрано до конструктора шаблонов — документ показан прежним расчётом и не пересобирается"


def brand_ids(db: Session, annex) -> list:
    """Бренды сделок, которые закрывает ДС — для памяти «бренд → шаблон»."""
    from app.sales.models import SalesDeal, SalesDealAnnexAllocation
    aid = getattr(annex, "id", None)
    if aid is None:
        return []
    return sorted({b for (b,) in db.query(SalesDeal.brand_id).join(SalesDealAnnexAllocation, SalesDealAnnexAllocation.deal_id == SalesDeal.id)
                   .filter(SalesDealAnnexAllocation.annex_id == aid, SalesDeal.brand_id.isnot(None)).all()})


def pick(db: Session, contract, annex=None) -> dict:
    """Шаблон ДС (27.10.2026): выбранный в приложении → память его брендов → основной договора → базовый формата. Без приложения —
    умолчание договора. Выбранный шаблон, который к договору не относится (договор сменили), — как невыбранный."""
    chosen = getattr(annex, "tpl_template_id", None) if annex is not None else None
    brands = brand_ids(db, annex) if annex is not None else []
    if chosen is not None:
        try:
            return S.resolve_for_contract(db, contract, brand_ids=brands, chosen_id=chosen)
        except S.AnnexTplError:
            pass
    return S.resolve_for_contract(db, contract, brand_ids=brands)


def resolve(db: Session, contract, annex=None) -> tuple:
    """(текущая версия шаблона, причина отказа) — шаблона, который собирает это приложение (`pick`)."""
    r = pick(db, contract, annex)
    if r["template"] is None:
        return None, r["reason"]
    v = S.current(db, r["template"].id)
    return (v, None) if v else (None, "У шаблона нет версий")


WHY = {"chosen": "выбран в этом ДС", "brand": "последний для бренда", "main": "основной шаблон договора", "format": "базовый формата договора"}


def choice(db: Session, contract, annex) -> dict:
    """Выбор шаблона на экране сборки: варианты (шаблоны договора и базовый формата), что собирает сейчас и почему, что было бы по умолчанию."""
    r = pick(db, contract, annex)
    cur = r["template"]
    default = S.resolve_for_contract(db, contract, brand_ids=brand_ids(db, annex))["template"]
    return {"current_id": cur.id if cur else None, "why": WHY.get(r["why"]), "chosen": r["why"] == "chosen",
            "default_id": default.id if default else None,
            "options": [{"id": t.id, "title": t.title, "scope": t.scope, "is_main": bool(t.is_main)} for t in S.choices(db, contract)]}


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


def template_state(db: Session, contract, annex=None) -> Optional[dict]:
    """Для шаблона договора, который собирает ДС: изменилась ли база (уведомление при генерации, п. 46 плана)."""
    own = pick(db, contract, annex)["template"]
    if not own or own.scope != "custom":
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
    version = version_row(db, annex.template_version_id) or resolve(db, contract, annex)[0]
    if version is None:
        return m
    lv = live(db, contract, version, annex, deal_ids)
    m["values"] = {**lv["values"], **(m.get("values") or {})}
    m["edits"] = edits
    m["closing_basis"] = lv["closing_basis"]
    return m


def model_of(db: Session, annex, contract, deal_ids) -> dict:
    """Что показать на экране: {model, frozen, legacy, reason, template_state, choice}. `choice` у черновика — выбор шаблона сборки, у
    замороженного — шаблон для «Пересоздать» (владелец 02.11.2026), текущим — тот, по которому документ заморожен."""
    if is_frozen(annex):
        model = jsonable_encoder(upgrade_frozen(db, annex, contract, deal_ids))
        model = rebrand_model(model, DK.resolve(model.get("kind") or getattr(annex, "doc_kind", None), None,
                                                is_master=bool(getattr(annex, "master_deal_id", None))))
        frozen_choice = {**choice(db, contract, annex), "current_id": (model.get("template") or {}).get("template_id"),
                         "why": "в документе"}
        return {"model": model, "frozen": True, "legacy": False, "reason": None,
                "template_state": None, "choice": frozen_choice}
    if annex.no is not None:                                   # подтверждено до конструктора
        return {"model": None, "frozen": False, "legacy": True, "reason": LEGACY_REASON, "template_state": None, "choice": None}
    pick_ = choice(db, contract, annex)
    version, reason = resolve(db, contract, annex)
    if version is None:
        return {"model": None, "frozen": False, "legacy": False, "reason": reason, "template_state": None, "choice": pick_}
    return {"model": jsonable_encoder(live(db, contract, version, annex, deal_ids)), "frozen": False, "legacy": False,
            "reason": None, "template_state": template_state(db, contract, annex), "choice": pick_}


def basis_model(db: Session, annex, contract, deal_ids) -> dict:
    """Модель ДС для основания УПД. Свой ДС — его модель (`model_of`). ДС, подписанный вне системы, своей модели не имеет (текст —
    чужой файл), и основание собирается по ближайшему шаблону той же цепочкой, что в конструкторе: память бренда → основной
    договора → базовый формата; правленое основание прошлых ДС договора наследуется (владелец 05.11.2026: «генерим по шаблону
    наиболее близкому — если есть прикреплённый к бренду — или исторически который был»). Шаблона нет — пусто."""
    model = (model_of(db, annex, contract, deal_ids) or {}).get("model") or {}
    if model or getattr(annex, "origin", None) != "загружен":
        return model
    version, _ = resolve(db, contract, annex)
    return jsonable_encoder(live(db, contract, version, annex, deal_ids)) if version is not None else {}


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


def rebrand_model(model: dict, kind) -> dict:
    """Замороженная модель для ЭКРАНА — как в файле: подстановки слова документа заново по виду (подписанные до 02.11.2026
    модели хранят в них «Доп. соглашение»), текст, вписанный в шаблон руками, — как написан (владелец 07.11.2026).
    Возвращает копию: модель в базе остаётся, какой её заморозили."""
    def block(b):
        if b.get("sys") or not b.get("parts"):
            return b
        return {**b, "text": DK.text_of(b, kind), "parts": DK.refill(b["parts"], kind)}

    out = {**model, "number": DK.renumber(model.get("number"), kind), "blocks": [block(b) for b in model.get("blocks") or []]}
    cb = model.get("closing_basis")
    if isinstance(cb, dict) and cb.get("parts"):
        out["closing_basis"] = {**cb, "text": DK.text_of(cb, kind), "parts": DK.refill(cb["parts"], kind)}
    return out


def preamble_of(model: dict, kind) -> Optional[str]:
    """Текст преамбулы из шаблона (02.11.2026) — словом документа в полной форме; None — шаблон её не задал, печатается
    прежняя формула."""
    pre = next((b for b in model.get("blocks") or [] if b.get("sys") == "pre"), None)
    text = DK.text_of(pre, kind) if pre else ""
    return text.strip() or None


# Пункт шаблона, который сам служит заголовком подписей: «Подписи Сторон:», «Реквизиты:», «Реквизиты и подписи Сторон».
_SIGN_HEADING = re.compile(r"^\s*(подписи|реквизиты)(\s+и\s+(подписи|реквизиты))?(\s+сторон)?\s*:?\s*$", re.I)


def clauses_of(model: dict, kind) -> list:
    """Блоки конструктора — файлу, по порядку (владелец 02.11.2026: файл печатает ровно то, что собрано в конструкторе).

    Системные блоки (шапка, место и дата, преамбула, таблица, подписи) рисует генератор файла — у них нет текста; текстовые
    идут с номером и текстом шаблона. Подстановки слова документа — по виду (замороженные до 02.11.2026 хранят в них
    «Доп. соглашение»), вписанное в шаблон руками — как написано (владелец 07.11.2026)."""
    out = []
    for b in model.get("blocks") or []:
        if b.get("sys") == "sign":
            # Свой заголовок «Подписи Сторон:» блок подписей печатает, только если шаблон не поставил перед ним свой пункт-заголовок
            # («6. Подписи Сторон:», «Реквизиты:») — иначе в файле он выходил дважды (владелец 02.11.2026).
            prev = out[-1] if out else {}
            out.append({"sys": "sign", "heading": not (not prev.get("sys") and _SIGN_HEADING.match(prev.get("text") or ""))})
        elif b.get("sys"):
            out.append({"sys": "table" if b["sys"] == "table" else b["sys"]})
        else:
            out.append({"num": b.get("num") or "", "sub": bool(b.get("sub")),
                        "text": DK.text_of(b, kind).strip()})
    return out


def bridge_old_doc(db: Session, annex, contract, doc: dict, deal_ids) -> dict:
    """Старые PDF и DOCX строятся из `annex.build`, пока генерация не переписана (п. 57–63 плана). Мост: пункт 1 берётся из шаблона ДС
    (замороженного у подтверждённого, живого у остальных), устаревшее требование «шаблон формулировки по плательщику» снимается, а чего не
    хватает по новому документу, добавляется к списку. Без шаблона у договора документ остаётся как был — со старым замечанием."""
    if is_frozen(annex):
        model, live_model = upgrade_frozen(db, annex, contract, deal_ids), False
    else:
        version, _ = resolve(db, contract, annex)
        model = jsonable_encoder(live(db, contract, version, annex, deal_ids)) if version else None
        live_model = True
    if not model:
        return with_words({**doc, "kind": fixed_kind(annex, contract, None)})
    texts = [b.get("text") for b in model.get("blocks", []) if not b.get("sys")]
    doc["body"] = texts[0] if texts else ""
    # Основание для закрывающих документов — в тот же словарь: файл «для клиента» печатает его после ДС (одним документом на согласование).
    doc["closing_basis"] = DK.text_of(model.get("closing_basis"),
                                      DK.resolve(fixed_kind(annex, contract, model.get("kind")), None, is_master=bool(getattr(annex, "master_deal_id", None))))
    # Вид документа — генератору файла: DOCX называет документ тем же словом, что конструктор
    # («синхронизировать», 31.10.2026). До развилки на мастер-сделку — получают обе ветки.
    doc["kind"] = fixed_kind(annex, contract, model.get("kind"))
    if getattr(annex, "rows", None) is not None:
        doc = _master_doc(db, annex, contract, doc, model)
    doc["master_code"] = _master_code(db, annex)
    doc["missing"] = [m for m in (doc.get("missing") or []) if m != OLD_NO_TEMPLATE]
    if live_model:
        doc["missing"] += [m["text"] for m in model.get("missing", []) if m["text"] not in doc["missing"]]
    kind = DK.resolve(doc.get("kind"), None, is_master=bool(doc.get("is_master")))
    doc["clauses"] = clauses_of(model, kind)
    doc["preamble"] = preamble_of(model, kind)
    # Заголовок и «место и дата», если их правили (05.11.2026); иначе файл рисует их как раньше.
    for key, field in (("head", "head_text"), ("place", "place_text")):
        b = model.get(key) or {}
        doc[field] = DK.text_of(b, kind).strip() if b.get("custom") and (b.get("text") or "").strip() else None
    return with_words(doc)


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
            + f": {upd_closing(model, k, annex.rows, db)['text']}" for k in upds)
    return doc


def _closing_template_for(rows) -> str:
    """Шаблон основания по составу ДС — одна функция с конструктором (`assemble.closing_template_for`)."""
    from app.annex_tpl.assemble import closing_template_for
    return closing_template_for(rows)


def upd_rows(rows, brand_of: dict, brand, service, *, by_service: bool, service_of: dict | None = None) -> list:
    """Строки снимка ДС, которые закрывает этот комплект УПД, — тем же ключом, что раскладка (`layout._key`): бренд сделки, а при
    «УПД по услугам» размещение и допы бренда — разные комплекты (у допов услуга не делит). Строка без денег (бонус 0 ₽) комплекта
    не образует — и в его основание не попадает (владелец 03.11.2026).

    При «УПД по услугам» размещение берётся только СВОЕЙ услуги — «услуга сделки · площадка строки» (`layout.service_label`):
    «еФарм · WEB» и «еФарм · APP» — разные УПД (28.10.2026). Без этого в обе УПД M-0001 попадали обе строки — и сумма, и основание
    УПД считались по чужой площадке (06.11.2026). `service_of` — услуга сделки по deal_id; нет — проверка как раньше."""
    from app.master_deal.layout import service_label
    out = []
    for r in rows or []:
        if not r.get("amount") or r.get("kind") == "discount":
            continue
        if brand and (brand_of.get(r.get("deal_id")) or "без бренда") != brand:
            continue
        if by_service and (r.get("kind") == "extra") != (service is None):
            continue
        own = (service_of or {}).get(r.get("deal_id"))      # услуга сделки неизвестна — по услуге не делим (как до 06.11.2026)
        if by_service and service is not None and own and service_label(own, r.get("device")) != service:
            continue
        out.append(r)
    return out


def _upd_own(db, k, rows, values: dict) -> list:
    """Строки своей УПД, её {услуга} и {бренд_название} — названия брендов её сделок из справочника, как у конструктора
    (`_brands_only`): УПД без деления по брендам называет только свои бренды, а не все бренды ДС, и имя бренда с « / » внутри
    («Эспумизан (взрослый) / Espumisan (adults)») не режется. Без базы (старые вызовы и тесты) — как раньше, по переданным строкам."""
    if db is None or not getattr(k, "master_deal_id", None):
        if getattr(k, "brand", None):
            values["бренд_название"] = k.brand.split(" / ")[-1].strip()      # «Grindeks / Милдронат» → «Милдронат»
        return rows
    from app.annex_tpl.assemble import _brands_only, service_text
    from app.master_deal.models import MasterDeal
    from app.sales.annex import deal_brand
    m = db.get(MasterDeal, k.master_deal_id)
    from app.sales.models import SalesDeal, SalesService
    ids = [i for i in dict.fromkeys(r.get("deal_id") for r in rows or []) if i]
    brand_of = {i: deal_brand(db, [i]) for i in ids}
    service_of = {}
    for i in ids:                       # через get, как бренд: тесты зовут с поддельной базой без query
        d = db.get(SalesDeal, i)
        sv = db.get(SalesService, d.service_id) if d is not None and getattr(d, "service_id", None) else None
        service_of[i] = getattr(sv, "name", None)
    own = upd_rows(rows, brand_of, k.brand, k.service, by_service=bool(getattr(m, "upd_by_service", False)), service_of=service_of)
    values["услуга"] = service_text(db, None, own)
    names = _brands_only(db, list(dict.fromkeys(r.get("deal_id") for r in own)))
    if names:
        values["бренд_название"] = names
    return own


def upd_closing(model: dict, k, rows=None, db=None) -> dict:
    """Основание УПД мастер-сделки — то же «основание для закрывающих», что в конструкторе ДС (владелец 19.10.2026): шаблон с подстановками,
    значения — своего ДС, бренд — свой у каждого УПД. Порядок: свой текст УПД → основание, поправленное в конструкторе этого ДС или
    унаследованное от прошлого ДС договора → шаблон по составу ДС. С базой состав и {услуга} — по строкам СВОЕЙ УПД (03.11.2026):
    у УПД размещения не «и оказание дополнительных услуг», у УПД допа — не «размещение рекламных материалов»."""
    from app.annex_tpl.assemble import closing_resolve
    cb = model.get("closing_basis") or {}
    values = dict(model.get("values") or {})
    rows = _upd_own(db, k, rows, values)
    sep = separate_price(db)
    values = with_device(values, rows, sep)    # один девайс у всей УПД — он в основании (06.11.2026)
    if getattr(k, "basis_text", None):
        out = closing_resolve(k.basis_text, values, True)
    elif cb.get("edited") or cb.get("inherited_from"):
        out = closing_resolve(cb["template"], values, False, cb.get("inherited_from") or "основание этого ДС")
    else:
        out = closing_resolve(_closing_template_for(rows), values, False)
    # строки УПД — каждая со своим основанием (06.11.2026); у УПД из одной строки оно и есть основание УПД
    lines = line_bases(out["template"], values, rows, sep) if len(rows or []) > 1 else \
        [{"row_id": r.get("row_id"), "text": out["text"]} for r in rows or []]
    return {**out, "values": values, "lines": lines}   # подстановки этой УПД — экрану пакета, чтобы подсказка правки совпадала с печатью


def fixed_kind(annex, contract, model_kind: Optional[str]) -> Optional[str]:
    """Вид документа для печати: записанный в ДС при подтверждении → вид модели сборки → у черновика тумблер
    договора → у подписанного до 31.10.2026 — ничего (тогда `with_words` берёт прежнее умолчание).

    Подписанный документ не переименовывается тумблером, выбранным позже (ревью 31.10.2026); черновик
    без шаблона называется так же, как в предпросмотре.
    """
    if getattr(annex, "doc_kind", None):
        return annex.doc_kind
    if model_kind:
        return model_kind
    if is_frozen(annex) or getattr(annex, "status", None) == "подтверждён":
        return None
    return DK.resolve(None, getattr(contract, "annex_word", None), is_master=bool(getattr(annex, "master_deal_id", None)))


def with_words(doc: dict) -> dict:
    """Слово документа — странице печати PDF (ревью 31.10.2026).

    Вид — тот же, что у DOCX (`annex_docx._kind`): зафиксированный в модели, иначе у
    мастер-сделки «дс», иначе «приложение». Формы и номер в дательном отдаются готовыми,
    чтобы страница не считала их сама: своя таблица форм на странице однажды уже разошлась
    с тумблером договора («Доп. соглашение № 68» в заголовке, «настоящим Приложением» в пунктах).
    """
    kind = DK.resolve(doc.get("kind"), None, is_master=bool(doc.get("is_master")))
    # Номер в заголовке собран по ТЕКУЩЕМУ тумблеру договора (`annex.build`), а вид подписанного — зафиксирован:
    # слово перед номером приводится к виду, иначе заголовок и пункты разошлись бы (ревью 31.10.2026).
    number = DK.renumber(doc.get("number"), kind)
    return {**doc, "kind": kind, "number": number, "words": DK.forms(kind), "number_dat": DK.to_dative(number, kind)}


DEVICES = ("WEB", "APP")


def _device_of(r: dict, separate) -> str:
    """WEB/APP строки ДС — только у услуг с раздельным прайсом (то же правило, что метка в имени сделки, 03.09.2026); иначе пусто."""
    dev = r.get("device")
    return dev if dev in DEVICES and (r.get("position") or "").strip() in (separate or ()) else ""


def with_device(values: dict, rows, separate) -> dict:
    """{сеть} с девайсом (владелец 06.11.2026: «в сети SIMB-AD (WEB)»), когда у всех строк УПД один девайс; разные — без метки:
    тогда девайс назовёт основание своей строки (`line_bases`)."""
    devs = {_device_of(r, separate) for r in rows or []}
    if len(devs) != 1 or "" in devs:
        return values
    return {**values, "сеть": f"{values.get('сеть') or 'SIMB-AD'} ({devs.pop()})"}


def line_bases(template: str, values: dict, rows, separate) -> list:
    """Основание каждой строки УПД (владелец 06.11.2026, «вариант 3»): тот же шаблон, подстановки — по своей строке: девайс в
    {сеть} и период строки. Строка без дат (доп) берёт период УПД."""
    from app.annex_tpl.assemble import _date, closing_resolve, placement_span
    out = []
    for r in rows or []:
        v = with_device(values, [r], separate)
        f, t = placement_span([r], None, None)
        if f and t:
            v = {**v, "период_с": _date(f), "период_по": _date(t)}
        out.append({"row_id": r.get("row_id"), "text": closing_resolve(template, v, False)["text"]})
    return out


def separate_price(db) -> set:
    """Услуги с раздельным прайсом WEB/APP — по справочнику услуг."""
    if db is None or not hasattr(db, "query"):       # поддельная база тестов — услуг с раздельным прайсом нет
        return set()
    from app.sales.models import SalesService
    return {n for (n,) in db.query(SalesService.name).filter(SalesService.separate_price.is_(True)).all()}
