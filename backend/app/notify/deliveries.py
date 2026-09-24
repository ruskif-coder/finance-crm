# -*- coding: utf-8 -*-
"""Общий журнал отправок: всё, что ушло человеку, одной лентой.

До 16.09.2026 журналов было ДВА и лежали они на разных экранах: доставки сотрудникам
(`notification_deliveries`) в уведомлениях, письма наружу (`mail_log`) в почте. Вопрос
у человека при этом один и тот же — «ушло или нет» — и ответ на него требовал помнить,
кому именно мы писали, чтобы выбрать нужный экран.

Таблицы НЕ сливаются: у них разный адресат и разная цена ошибки. Внутренняя строка
адресует нашего пользователя (`user_id`), внешняя — адрес вне системы, и у неё есть
`reply_to`, `send_after`, разметка письма. Сливать их значило бы завести половину
пустых колонок у каждой второй строки. Объединяются они ЗДЕСЬ, на чтении.

Две оси, по которым лента читается:

    канал     панель · телеграм · почта · дайджест  — ЧЕМ доставляли
    контур    сотрудникам · площадкам               — КОМУ

Канал у внешних писем всегда «почта»: бот площадки пишет в свою таблицу привязок и в
журнал не попадает — это отдельный долг, и врать про него лента не должна.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

STAFF, PUB = "сотрудникам", "площадкам"

# Канал: ключ в базе → слово на экране. Порядок словаря = порядок в выпадашке.
CHANNELS = {
    "app": "панель",
    "tg": "телеграм",
    "mail": "почта",
    "digest": "дайджест",
}

STATUS = {
    "sent": "доставлено",
    "queued": "ждёт канала",
    "suppressed": "подавлено",
    "failed": "ошибка",
}

# Два источника одной формы. `kind` у письма наружу — вид письма, у уведомления —
# ключ события: в обоих случаях это ответ на вопрос «о чём было».
_UNION = """
SELECT 'n' || d.id            AS id,
       d.created_at           AS created_at,
       d.channel              AS channel,
       :staff                 AS contour,
       coalesce(u.name, u.email, '—') AS addressee,
       d.title                AS subject,
       d.status               AS status,
       d.suppress_reason      AS reason,
       d.error                AS error,
       d.event_key            AS kind
  FROM notification_deliveries d
  LEFT JOIN users u ON u.id = d.user_id
UNION ALL
SELECT 'm' || m.id, m.created_at, 'mail', :pub,
       coalesce(nullif(m.to_name, ''), m.to_email), m.subject, m.status,
       NULL, m.error, m.kind
  FROM mail_log m
"""


def query(db: Session, *, limit: int = 100, offset: int = 0,
          channel: Optional[str] = None, contour: Optional[str] = None,
          status: Optional[str] = None, q: Optional[str] = None) -> dict:
    """Лента с фильтрами. Отбор и счёт идут ОДНИМ запросом по объединению, а не двумя
    выборками с досортировкой в питоне: иначе вторая страница показывала бы дыры —
    пятьдесят строк одного источника, потом пятьдесят другого.
    """
    where, params = [], {"staff": STAFF, "pub": PUB}
    if channel:
        where.append("channel = :ch"); params["ch"] = channel
    if contour:
        where.append("contour = :co"); params["co"] = contour
    if status:
        where.append("status = :st"); params["st"] = status
    if (q or "").strip():
        where.append("(addressee ILIKE :q OR subject ILIKE :q)")
        params["q"] = f"%{q.strip()}%"
    cond = (" WHERE " + " AND ".join(where)) if where else ""

    total = db.execute(sa_text(f"SELECT count(*) FROM ({_UNION}) j{cond}"), params).scalar()
    params["lim"] = min(max(limit, 1), 500)
    params["off"] = max(offset, 0)
    rows = db.execute(sa_text(
        f"SELECT * FROM ({_UNION}) j{cond} "
        " ORDER BY created_at DESC, id DESC LIMIT :lim OFFSET :off"), params).fetchall()

    return {
        "total": total or 0,
        "channels": [{"key": k, "label": v} for k, v in CHANNELS.items()],
        "contours": [STAFF, PUB],
        "items": [{
            "id": r.id, "created_at": r.created_at,
            "channel": r.channel, "channel_label": CHANNELS.get(r.channel, r.channel),
            "contour": r.contour, "addressee": r.addressee, "subject": r.subject,
            "status": r.status,
            # «В очереди» с ошибкой — письмо на повторной попытке, а не «ждёт канала».
            "status_label": ("повтор по расписанию"
                             if r.status == "queued" and r.error
                             else STATUS.get(r.status, r.status)),
            "reason": r.reason, "error": r.error, "kind": r.kind,
        } for r in rows],
    }
