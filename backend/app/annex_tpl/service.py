# -*- coding: utf-8 -*-
"""Операции над шаблонами ДС: базовые шаблоны и их форматы, сохранение версии, откат, кастомный под договор, «базовый изменился».

Версии только добавляются. Каждая операция берёт блокировку строки шаблона (`FOR UPDATE`), поэтому две
параллельные правки не получат один номер версии; номер к тому же держит `UNIQUE (template_id, version)`.
Коммит — за вызывающим: ручка коммитит одним куском вместе с записью в журнал.
"""
import copy
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.annex_tpl.check import check, check_transition
from app.annex_tpl.diff import diff
from app.annex_tpl.formats import clean
from app.annex_tpl.models import AnnexTplBrandMemory, AnnexTplFormat, AnnexTplTemplate, AnnexTplVersion


class AnnexTplError(Exception):
    def __init__(self, status: int, message: str, issues: Optional[list] = None):
        super().__init__(message)
        self.status, self.message, self.issues = status, message, issues or []


def current(db: Session, template_id: int) -> Optional[AnnexTplVersion]:
    return (db.query(AnnexTplVersion).filter_by(template_id=template_id)
            .order_by(AnnexTplVersion.version.desc()).first())


def version_of(db: Session, template_id: int, version: int) -> Optional[AnnexTplVersion]:
    return db.query(AnnexTplVersion).filter_by(template_id=template_id, version=version).first()


def custom_of(db: Session, contract_id: int) -> Optional[AnnexTplTemplate]:
    """Основной шаблон договора (до 27.10.2026 шаблон договора был один — это он)."""
    return main_of(db, contract_id)


def customs_of(db: Session, contract_id: int) -> list:
    """Шаблоны договора: основной первым, остальные по имени."""
    return (db.query(AnnexTplTemplate).filter_by(scope="custom", contract_id=contract_id)
            .order_by(AnnexTplTemplate.is_main.desc(), func.lower(AnnexTplTemplate.title), AnnexTplTemplate.id).all())


def main_of(db: Session, contract_id: int) -> Optional[AnnexTplTemplate]:
    return db.query(AnnexTplTemplate).filter_by(scope="custom", contract_id=contract_id, is_main=True).first()


def base_by_title(db: Session, title: str) -> Optional[AnnexTplTemplate]:
    return (db.query(AnnexTplTemplate)
            .filter(AnnexTplTemplate.scope == "base", func.lower(AnnexTplTemplate.title) == (title or "").strip().lower())
            .first())


def base_for_format(db: Session, fmt: Optional[str]) -> Optional[AnnexTplTemplate]:
    """Базовый шаблон, обслуживающий формат сотрудничества договора. Пустой или не заведённый формат — None."""
    f = clean(fmt)
    row = db.query(AnnexTplFormat).filter_by(format=f).first() if f else None
    return db.query(AnnexTplTemplate).filter_by(id=row.template_id).first() if row else None


def formats_of(db: Session, template_id: int) -> list:
    return sorted(r.format for r in db.query(AnnexTplFormat).filter_by(template_id=template_id))


def _lock(db: Session, template_id: int) -> AnnexTplTemplate:
    t = db.query(AnnexTplTemplate).filter_by(id=template_id).with_for_update().first()
    if t is None:
        raise AnnexTplError(404, "Шаблон не найден")
    return t


def _add(db: Session, tpl: AnnexTplTemplate, blocks: list, user_id, user_name: str, *,
         base_version: Optional[int] = None, restored_from: Optional[int] = None,
         changes: Optional[list] = None) -> AnnexTplVersion:
    cur = current(db, tpl.id)
    issues = check(blocks) + check_transition(cur.blocks if cur else None, blocks)
    if issues:
        raise AnnexTplError(422, "Шаблон не прошёл проверку — версия не сохранена", issues)
    if changes is None:
        n = sum(1 for b in blocks if not b.get("sys"))
        changes = diff(cur.blocks, blocks) if cur else [["+", "шаблон создан", f"пунктов: {n}"]]
    row = AnnexTplVersion(
        template_id=tpl.id, version=(cur.version + 1) if cur else 1, blocks=copy.deepcopy(blocks),
        changes=changes, base_version=base_version, restored_from=restored_from,
        author_id=user_id, author_name=user_name)
    db.add(row)
    db.flush()
    return row


# ── базовые шаблоны и их форматы ─────────────────────────────────────────────────────────────

def set_formats(db: Session, template_id: int, formats: Iterable[str]) -> list:
    """Шаблон обслуживает РОВНО эти форматы. Формат, занятый другим шаблоном, переходит к этому;
    формат, которого нет в списке, освобождается (договор с ним остаётся без шаблона, пока формат не назначат)."""
    tpl = _lock(db, template_id)
    if tpl.scope != "base":
        raise AnnexTplError(400, "Форматы назначаются только базовому шаблону")
    want = {clean(f) for f in formats if clean(f)}
    for row in db.query(AnnexTplFormat).filter_by(template_id=tpl.id):
        if row.format not in want:
            db.delete(row)
    for f in want:
        row = db.query(AnnexTplFormat).filter_by(format=f).first()
        if row is None:
            db.add(AnnexTplFormat(format=f, template_id=tpl.id))
        elif row.template_id != tpl.id:
            row.template_id = tpl.id
    db.flush()
    return formats_of(db, tpl.id)


def create_base(db: Session, title: str, blocks: list, user_id, user_name: str, formats: Iterable[str] = ()) -> AnnexTplVersion:
    """Новый базовый шаблон (вариант договора): название уникально; v1 проходит ту же проверку, что любое сохранение."""
    title = (title or "").strip()
    if not title:
        raise AnnexTplError(400, "У шаблона должно быть название")
    if base_by_title(db, title):
        raise AnnexTplError(409, f"Базовый шаблон «{title}» уже есть")
    tpl = AnnexTplTemplate(scope="base", title=title, created_by=user_id)
    db.add(tpl)
    db.flush()
    v = _add(db, tpl, blocks, user_id, user_name)
    set_formats(db, tpl.id, formats)
    return v


def seed_base(db: Session, title: str, blocks: list, author_name: str, formats: Iterable[str] = ()) -> AnnexTplVersion:
    """Заводит базовый шаблон и его v1. Повторный вызов ничего не делает (возвращает текущую версию)."""
    tpl = base_by_title(db, title)
    if tpl:
        return current(db, tpl.id)
    return create_base(db, title, blocks, None, author_name, formats)


# ── версии ───────────────────────────────────────────────────────────────────────────────────

def _base_version(db: Session, tpl: AnnexTplTemplate) -> int:
    cur = current(db, tpl.base_template_id) if tpl.base_template_id else None
    if not cur:
        raise AnnexTplError(409, "У кастомного шаблона нет базового")
    return cur.version


def save_version(db: Session, template_id: int, blocks: list, user, adopt_base: bool = False) -> AnnexTplVersion:
    tpl = _lock(db, template_id)
    cur = current(db, tpl.id)
    if cur is None:
        raise AnnexTplError(409, "У шаблона нет версий")
    bv = cur.base_version
    if tpl.scope == "custom" and adopt_base:
        bv = _base_version(db, tpl)
    elif tpl.scope == "base":
        bv = None
    if blocks == cur.blocks and bv == cur.base_version:
        raise AnnexTplError(400, "Изменений нет — новая версия не нужна")
    changes = diff(cur.blocks, blocks)
    if bv != cur.base_version:
        changes.append(["≡", "базовый шаблон", f"принята версия v{bv}"])
    return _add(db, tpl, blocks, user.id, user.name or "—", base_version=bv, changes=changes)


def restore(db: Session, template_id: int, version: int, user) -> AnnexTplVersion:
    """Откат создаёт НОВУЮ версию с текстом старой; история не стирается."""
    tpl = _lock(db, template_id)
    cur, old = current(db, tpl.id), version_of(db, tpl.id, version)
    if old is None:
        raise AnnexTplError(404, f"Версии v{version} нет")
    if cur and old.version == cur.version:
        raise AnnexTplError(400, "Это текущая версия")
    if cur and old.blocks == cur.blocks:
        raise AnnexTplError(400, f"Текст v{version} совпадает с текущим — откатывать нечего")
    return _add(db, tpl, old.blocks, user.id, user.name or "—",
                base_version=cur.base_version if tpl.scope == "custom" else None,
                restored_from=old.version, changes=diff(cur.blocks, old.blocks))


# ── кастомный под договор ────────────────────────────────────────────────────────────────────

MAX_TITLE = 120


def _title(db: Session, contract_id: int, title, skip_id: Optional[int] = None) -> str:
    """Имя шаблона договора: не пустое, не длиннее MAX_TITLE, не повторяется внутри договора (без учёта регистра)."""
    t = " ".join(str(title or "").split())
    if not t:
        raise AnnexTplError(400, "Дайте шаблону имя — под ним его выбирают в ДС")
    if len(t) > MAX_TITLE:
        raise AnnexTplError(400, f"Имя шаблона длиннее {MAX_TITLE} знаков")
    q = db.query(AnnexTplTemplate).filter(AnnexTplTemplate.scope == "custom", AnnexTplTemplate.contract_id == contract_id,
                                          func.lower(AnnexTplTemplate.title) == t.lower())
    if skip_id:
        q = q.filter(AnnexTplTemplate.id != skip_id)
    same = q.first()
    if same:
        raise AnnexTplError(409, f"Шаблон «{same.title}» у этого договора уже есть — выберите другое имя")
    return t


def _source(db: Session, contract, source_id: Optional[int]) -> AnnexTplTemplate:
    """Откуда копировать: указанный шаблон (базовый или шаблон ЭТОГО договора), иначе базовый формата договора."""
    if source_id is not None:
        src = db.query(AnnexTplTemplate).filter_by(id=source_id).first()
        if src is None or (src.scope == "custom" and src.contract_id != contract.id):
            raise AnnexTplError(400, "Копировать можно базовый шаблон или шаблон этого же договора")
        return src
    fmt = clean(getattr(contract, "cooperation_format", None))
    if not fmt:
        raise AnnexTplError(400, "У договора не указан «Формат сотрудничества» — шаблон не определён")
    base = base_for_format(db, fmt)
    if base is None:
        raise AnnexTplError(409, f"Для формата «{fmt}» не задан базовый шаблон")
    return base


def fork_custom(db: Session, contract, user, title=None, source_id: Optional[int] = None, blocks: Optional[list] = None,
                main: bool = False) -> AnnexTplVersion:
    """Новый именованный шаблон договора, v1: копия текущей версии источника (базовый формата, указанный базовый или другой шаблон
    договора) либо переданные блоки (сохранение из конструктора ДС). Запоминает базу и её версию — для «базовый изменился»."""
    name = _title(db, contract.id, title)
    src = _source(db, contract, source_id)
    base = src if src.scope == "base" else db.query(AnnexTplTemplate).filter_by(id=src.base_template_id).first()
    bcur = current(db, base.id) if base else None
    scur = current(db, src.id)
    if not (bcur and scur):
        raise AnnexTplError(409, "У шаблона-источника нет версий")
    if main:
        _unset_main(db, contract.id)
    tpl = AnnexTplTemplate(scope="custom", contract_id=contract.id, base_template_id=base.id, title=name, is_main=bool(main),
                           created_by=getattr(user, "id", None))
    db.add(tpl)
    db.flush()
    origin = "из конструктора ДС" if blocks is not None else f"копия «{src.title}» v{scur.version}"
    return _add(db, tpl, blocks if blocks is not None else scur.blocks, getattr(user, "id", None),
                getattr(user, "name", None) or "—", base_version=bcur.version,
                changes=[["+", "шаблон создан", f"«{name}»: {origin}"]])


def _custom(db: Session, template_id: int) -> AnnexTplTemplate:
    t = _lock(db, template_id)
    if t.scope != "custom":
        raise AnnexTplError(400, "Только у шаблона договора")
    return t


def rename(db: Session, template_id: int, title) -> AnnexTplTemplate:
    t = _custom(db, template_id)
    t.title = _title(db, t.contract_id, title, skip_id=t.id)
    db.flush()
    return t


def _unset_main(db: Session, contract_id: int) -> None:
    db.query(AnnexTplTemplate).filter_by(contract_id=contract_id, is_main=True).update({"is_main": False})
    db.flush()                       # иначе частичный уникальный индекс «основной один» споткнётся о прежний основной


def set_main(db: Session, template_id: int, on: bool) -> AnnexTplTemplate:
    """Основной шаблон договора: подставляется в новый ДС, если для его брендов шаблон ещё не выбирали. Основной — один."""
    t = _custom(db, template_id)
    if on:
        _unset_main(db, t.contract_id)
    t.is_main = bool(on)
    db.flush()
    return t


def keep_own(db: Session, template_id: int, user) -> AnnexTplVersion:
    """«Оставить свой»: текст не меняется, версия базы принимается. Это новая версия (версии не правятся),
    с пометкой `≡` в истории."""
    tpl = _lock(db, template_id)
    if tpl.scope != "custom":
        raise AnnexTplError(400, "Только у кастомного шаблона")
    cur = current(db, tpl.id)
    bv = _base_version(db, tpl)
    if bv == cur.base_version:
        raise AnnexTplError(409, "Базовый шаблон не менялся")
    return _add(db, tpl, cur.blocks, user.id, user.name or "—", base_version=bv,
                changes=[["≡", "базовый шаблон", f"принята версия v{bv}, текст оставлен"]])


def base_state(db: Session, tpl: AnnexTplTemplate) -> Optional[dict]:
    """Для кастомного: изменилась ли база с момента согласования. Для базового — None."""
    if tpl.scope != "custom":
        return None
    cur = current(db, tpl.id)
    bcur = current(db, tpl.base_template_id)
    if not (cur and bcur):
        return {"changed": False, "known": cur.base_version if cur else None, "now": None}
    return {"changed": bcur.version > (cur.base_version or 0), "known": cur.base_version, "now": bcur.version}


def base_changes(db: Session, tpl: AnnexTplTemplate) -> list:
    """Что изменилось в базе между известной шаблону договора версией и текущей."""
    st = base_state(db, tpl)
    if not st or not st["changed"]:
        return []
    known = version_of(db, tpl.base_template_id, st["known"])
    return diff(known.blocks, current(db, tpl.base_template_id).blocks) if known else []


def customs_behind(db: Session, base_template_id: Optional[int] = None) -> list:
    """Кастомные шаблоны договоров, отставшие от своей базы (база сохранена новее, чем версия, с которой согласован кастомный).
    Для «Юр запросов», реестра договоров и уведомления юристам (владелец 14.10.2026)."""
    q = db.query(AnnexTplTemplate).filter(AnnexTplTemplate.scope == "custom")
    if base_template_id:
        q = q.filter(AnnexTplTemplate.base_template_id == base_template_id)
    out = []
    for t in q.order_by(AnnexTplTemplate.id).all():
        st = base_state(db, t)
        if st and st["changed"]:
            out.append({"template_id": t.id, "title": t.title, "contract_id": t.contract_id, "known": st["known"], "now": st["now"]})
    return out


def _usable(db: Session, contract, template_id: Optional[int]) -> Optional[AnnexTplTemplate]:
    t = db.query(AnnexTplTemplate).filter_by(id=template_id).first() if template_id else None
    if t is None or (t.scope == "custom" and t.contract_id != contract.id):
        return None
    return t


def _by_brands(db: Session, contract, brand_ids) -> Optional[AnnexTplTemplate]:
    """Шаблон из памяти брендов ДС: все бренды, для которых шаблон выбирали, указывают на один и тот же. Разошлись — памяти нет."""
    ids = [b for b in set(brand_ids or ()) if b]
    if not ids:
        return None
    got = {r.template_id for r in db.query(AnnexTplBrandMemory)
           .filter(AnnexTplBrandMemory.contract_id == contract.id, AnnexTplBrandMemory.brand_id.in_(ids)).all()}
    return _usable(db, contract, got.pop()) if len(got) == 1 else None


def resolve_for_contract(db: Session, contract, brand_ids=(), chosen_id: Optional[int] = None) -> dict:
    """Какой шаблон собирает ДС: выбранный руками → память брендов ДС → основной договора → базовый его формата.
    `why` — откуда он взялся (chosen / brand / main / format); шаблона нет — `template=None` и причина."""
    if chosen_id is not None:
        t = _usable(db, contract, chosen_id)
        if t is None:
            raise AnnexTplError(400, "Этот шаблон не относится к договору приложения")
        return {"source": t.scope, "template": t, "reason": None, "why": "chosen"}
    for why, t in (("brand", _by_brands(db, contract, brand_ids)), ("main", main_of(db, contract.id))):
        if t is not None:
            return {"source": t.scope, "template": t, "reason": None, "why": why}
    fmt = clean(getattr(contract, "cooperation_format", None))
    if not fmt:
        return {"source": "none", "template": None, "why": None,
                "reason": "У договора не указан «Формат сотрудничества» — шаблон не определён, ДС не собирается"}
    base = base_for_format(db, fmt)
    if base is None:
        return {"source": "none", "template": None, "why": None,
                "reason": f"Для формата «{fmt}» не задан базовый шаблон — ДС не собирается"}
    return {"source": "base", "template": base, "reason": None, "why": "format"}


def choices(db: Session, contract) -> list:
    """Из чего выбирают шаблон в ДС: шаблоны договора (основной первым) и базовый шаблон его формата."""
    out = list(customs_of(db, contract.id))
    fmt = clean(getattr(contract, "cooperation_format", None))
    base = base_for_format(db, fmt) if fmt else None
    return out + ([base] if base else [])


def remember(db: Session, contract_id: int, brand_ids, template_id: int, user_id) -> None:
    """Память «договор + бренд → шаблон»: пишется при подтверждении ДС для каждого его бренда."""
    for b in {x for x in (brand_ids or ()) if x}:
        row = db.query(AnnexTplBrandMemory).filter_by(contract_id=contract_id, brand_id=b).first()
        if row is None:
            db.add(AnnexTplBrandMemory(contract_id=contract_id, brand_id=b, template_id=template_id, updated_by=user_id))
        else:
            row.template_id, row.updated_by, row.updated_at = template_id, user_id, func.now()
    db.flush()


def blocks_from_model(blocks: list, model_blocks: list) -> list:
    """Блоки нового шаблона из документа на экране конструктора: текст пункта — тот, что видит аккаунт (своя правка или унаследованная
    из прошлого ДС, С подстановками), остальное — как в шаблоне, по которому собран документ."""
    shown = {b.get("id"): b.get("source_text") for b in model_blocks or [] if not b.get("sys") and b.get("source_text")}
    return [dict(b, text=shown[b["id"]]) if not b.get("sys") and b.get("id") in shown else copy.deepcopy(b) for b in blocks]


def usage_by_contract(db: Session, contract_id: int) -> dict:
    """{id шаблона: {n, last}} — сколько ДС договора собрано по каждому шаблону и дата последнего (карточка договора, 28.10.2026).
    Шаблон ДС — тот, чьей версией заморожен документ, иначе выбранный в черновике."""
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT coalesce(v.template_id, a.tpl_template_id) AS tpl, count(*) AS n, max(a.date) AS last
          FROM sales_annexes a LEFT JOIN annex_tpl_versions v ON v.id = a.template_version_id
         WHERE a.contract_id = :c AND coalesce(v.template_id, a.tpl_template_id) IS NOT NULL
         GROUP BY 1"""), {"c": contract_id}).mappings().all()
    return {r["tpl"]: r for r in rows}
