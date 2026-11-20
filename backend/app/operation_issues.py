# -*- coding: utf-8 -*-
"""Проблемные операции (владелец 20.11.2026): у операции есть то, что надо разобрать руками, — значок в реестре и плитка-фильтр
«Проблемные», а не поиск по базе. Таблица `operation_issues` (миграция 2026-11-20_operation_issues.sql): строка — одна проблема;
закрывается сама (причина снята событием) или человеком с комментарием.

Здесь же ОДНО правило «комплект УПД уходит → что с его операцией» (`retire_kits`). Его зовут все места, где комплекты удаляются
(возврат в раскладку, пересборка строк ДС, стартовый пакет на подписанном ДС), — иначе база молча обнуляла ссылку
(`ondelete=SET NULL`), операция «план поступлений» висела сиротой, а пересобранный пакет рождал вторую — дубль в дебиторке.
  · неоплаченная («план поступлений» без частей оплаты и без сканов) — удаляется вместе с комплектом;
  · оплаченная или поправленная бухгалтером — НЕ удаляется (владелец 20.11.2026): проблема «пакет удалён» и уведомление."""
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, exists, func, text
from sqlalchemy.orm import Session

from app.database import Base
from app.models import PLAN_INCOME, Operation

KINDS = ("пакет удалён", "на переделке", "расхождение с 1С")
DELETED, REDO, MISMATCH = KINDS
NOTIFY = (DELETED, MISMATCH)          # «на переделке» — рабочее состояние, о нём не звоним


class OperationIssue(Base):
    """Таблица создаётся миграцией 2026-11-20_operation_issues.sql — там смысл полей."""
    __tablename__ = "operation_issues"
    id = Column(Integer, primary_key=True)
    operation_id = Column(Integer, ForeignKey("operations.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(30), nullable=False)
    text = Column(Text)
    master_deal_upd_id = Column(Integer)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at = Column(DateTime)
    resolved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    resolution = Column(Text)


class IssueError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def _open(db: Session, op_id: int, kind: str) -> Optional[OperationIssue]:
    return (db.query(OperationIssue).filter(OperationIssue.operation_id == op_id, OperationIssue.kind == kind,
                                            OperationIssue.resolved_at.is_(None)).first())


def raise_issue(db: Session, op, kind: str, text_: str, kit_id: Optional[int] = None, user=None) -> OperationIssue:
    """Открыть проблему. Такая же уже открыта — обновить текст (повторная переделка не плодит строки), уведомить снова."""
    if kind not in KINDS:
        raise ValueError(f"Вид проблемы «{kind}» не из словаря")
    row = _open(db, op.id, kind)
    same = row is not None and row.text == text_          # то же самое ещё раз — не звоним повторно
    if row is None:
        row = OperationIssue(operation_id=op.id, kind=kind, master_deal_upd_id=kit_id, created_by=getattr(user, "id", None))
        db.add(row)
    row.text = text_
    db.flush()
    if kind in NOTIFY and not same:
        from app.notify import closing as CN
        CN.operation_issue(db, op, kind, text_, user)
    return row


def close_kind(db: Session, op_id: int, kind: str, resolution: str, user=None) -> bool:
    """Причина снята событием (документы внесли заново) — закрыть сама. True — было что закрывать."""
    row = _open(db, op_id, kind)
    if row is None:
        return False
    row.resolved_at, row.resolved_by, row.resolution = datetime.utcnow(), getattr(user, "id", None), resolution
    db.flush()
    return True


def resolve(db: Session, issue_id: int, resolution: Optional[str], user) -> OperationIssue:
    """Закрыть руками — только с комментарием: что сделали (как запись бэклога)."""
    resolution = (resolution or "").strip()
    if not resolution:
        raise IssueError(400, "Закрыть проблему — с комментарием: что сделали")
    row = db.get(OperationIssue, issue_id)
    if row is None:
        raise IssueError(404, "Проблема не найдена — обновите операцию")
    if row.resolved_at is not None:
        raise IssueError(409, "Проблема уже закрыта")
    row.resolved_at, row.resolved_by, row.resolution = datetime.utcnow(), getattr(user, "id", None), resolution
    db.flush()
    return row


def open_cond():
    """Условие «у операции есть открытая проблема» — для плитки и фильтра реестра."""
    return exists().where(OperationIssue.operation_id == Operation.id, OperationIssue.resolved_at.is_(None))


def open_by_op(db: Session, op_ids: Iterable[int]) -> dict:
    """Открытые проблемы страницы реестра одним запросом: {op_id: [{id, kind, text, at}]}."""
    ids = list(op_ids)
    out: dict = {}
    if not ids:
        return out
    for r in (db.query(OperationIssue).filter(OperationIssue.operation_id.in_(ids), OperationIssue.resolved_at.is_(None))
              .order_by(OperationIssue.id)):
        out.setdefault(r.operation_id, []).append(
            {"id": r.id, "kind": r.kind, "text": r.text, "at": r.created_at.isoformat(timespec="seconds") + "Z"})
    return out


# ── комплект уходит ───────────────────────────────────────────────────────────────────────────────

def _deletable(db: Session, op) -> bool:
    """Удалить вместе с комплектом можно только нетронутый план: не оплачен, без частей оплаты, без приложенных сканов."""
    if op.status != PLAN_INCOME:
        return False
    if db.query(Operation.id).filter(Operation.parent_operation_id == op.id).first():
        return False
    return not db.execute(text("SELECT 1 FROM operation_files WHERE operation_id = :o LIMIT 1"), {"o": op.id}).first()


def retire_kits(db: Session, m, kit_ids: Iterable[int], user=None, why: str = "") -> dict:
    """Комплекты пакета `m` сейчас удалят — решить судьбу их операций ДО удаления. → {deleted: [id], kept: [id]}."""
    from app.master_deal.models import MasterDealUpd
    from app.models import AuditLog
    ids = [i for i in kit_ids if i]
    out = {"deleted": [], "kept": []}
    if not ids:
        return out
    upd_no = {k.id: k.upd_no for k in db.query(MasterDealUpd).filter(MasterDealUpd.id.in_(ids))}
    for op in db.query(Operation).filter(Operation.master_deal_upd_id.in_(ids)).order_by(Operation.id).all():
        where = f"пакет {m.code}, УПД № {upd_no.get(op.master_deal_upd_id, '?')}"
        if _deletable(db, op):
            # строкой журнала, а не log_action: тот коммитит, а здесь середина чужой транзакции (возврат пакета)
            db.add(AuditLog(user_id=getattr(user, "id", None), user_name=getattr(user, "name", None), action="delete_operation",
                            entity_type="operation", entity_id=op.id,
                            details=f"вместе с комплектом: {where}" + (f" — {why}" if why else "")))
            out["deleted"].append(op.id)
            db.delete(op)
            continue
        kit = op.master_deal_upd_id
        op.master_deal_upd_id = None                          # ссылку снимаем сами: комплекта не будет, а операция остаётся
        raise_issue(db, op, DELETED,
                    f"Комплект удалён ({where}{', ' + why if why else ''}), а операция {op.status.lower()} — разберите: "
                    "оплата осталась без документов.", kit_id=kit, user=user)
        out["kept"].append(op.id)
    db.flush()
    return out


def retire_package(db: Session, m, user=None, why: str = "") -> dict:
    """Все комплекты пакета уходят (возврат в раскладку, пересборка)."""
    from app.master_deal.models import MasterDealUpd
    return retire_kits(db, m, [k.id for k in db.query(MasterDealUpd.id).filter(MasterDealUpd.master_deal_id == m.id)], user, why)
