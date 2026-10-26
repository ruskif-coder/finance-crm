# -*- coding: utf-8 -*-
"""Запись сверок: отправить, ответить, напомнить, согласовать итог; ответ площадки из кабинета.

Коммитит вызывающий (ручка), чтобы журнал действий ехал той же транзакцией.
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.publisher_recon import board as B
from app.publisher_requests import (PublisherRecon, PublisherReconLine, PublisherRequest, PublisherRequestFile,
                                    PublisherRequestMessage)

ANSWER_WORKDAYS = 2                    # срок ответа площадки после активации и после нашего ответа (владелец 26.10)
FILE_DIR = "publisher_recon"
FILE_MAX = 20 * 1024 * 1024
FILE_EXT = {".xlsx", ".xls", ".csv", ".pdf", ".png", ".jpg", ".jpeg", ".zip"}
BODY_MAX = 4000


class ReconError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def add_workdays(d: date, n: int) -> date:
    """`n` рабочих дней после `d` (выходные не считаются — как `launch_prep.matrix.workdays_between`)."""
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def _dm(d: date) -> str:
    return d.strftime("%d.%m")


def _num(n: int) -> str:
    return f"{int(n):,}".replace(",", " ")


def _msg(db: Session, req: PublisherRequest, side: str, body: Optional[str] = None, volume: Optional[int] = None,
         author: Optional[str] = None, email: Optional[str] = None) -> PublisherRequestMessage:
    m = PublisherRequestMessage(request_id=req.id, side=side, body=body, volume=volume,
                                author_name=author, author_email=email)
    db.add(m)
    db.flush()
    return m


def _open(req: Optional[PublisherRequest]) -> PublisherRequest:
    if req is None or req.kind != "сверка":
        raise ReconError(404, "Сверка не найдена")
    if req.verdict == B.AGREED:
        raise ReconError(409, "Сверка уже согласована — итог зафиксирован без возврата")
    return req


def _last_side(db: Session, req: PublisherRequest) -> Optional[str]:
    return db.execute(text("""SELECT side FROM publisher_request_message WHERE request_id = :r AND side <> 'система'
                              ORDER BY id DESC LIMIT 1"""), {"r": req.id}).scalar()


def _clean(body: Optional[str]) -> Optional[str]:
    body = (body or "").strip()
    if len(body) > BODY_MAX:
        raise ReconError(400, f"Сообщение длиннее {BODY_MAX} символов")
    return body or None


VOLUME_MAX = 10 ** 12


def _volume(v) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        raise ReconError(400, "Показы — целое неотрицательное число")
    if v > VOLUME_MAX:   # опечатка в лишних нулях давала 500 на записи в базу (ревью 26.10.2026)
        raise ReconError(400, f"Показов больше {VOLUME_MAX:,} — проверьте число".replace(",", " "))
    return v


# ── наша сторона ──────────────────────────────────────────────────────────────────────────────────────

def send(db: Session, publisher_id: int, period: str, user, today: Optional[date] = None) -> PublisherRequest:
    """«Отправить»: активирует карточку в кабинете площадки, срок ответа — 2 рабочих дня."""
    today = today or date.today()
    if not B.period_ok(period):
        raise ReconError(400, "Месяц — в виде ГГГГ-ММ")
    if period < B.START:
        raise ReconError(400, "Сверки ведутся с октября 2026")
    row = next((r for r in B.month_rows(db, period, today) if r["publisher_id"] == publisher_id), None)
    if row is None:
        raise ReconError(404, "У площадки нет размещений за этот месяц")
    if row["status"] != B.READY:
        raise ReconError(409, "Сверку можно отправить, когда окончены все кампании площадки за месяц"
                         if row["status"] == B.WAIT else "Сверка уже отправлена")
    req = PublisherRequest(kind="сверка", publisher_id=publisher_id, period=period,
                           due_at=add_workdays(today, ANSWER_WORKDAYS), sent_by=user.name or user.email)
    db.add(req)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ReconError(409, "Сверка уже отправлена")
    db.add(PublisherRecon(request_id=req.id, our_volume=row["ours"]))
    _msg(db, req, "система", f"SIMB-AD отправил сверку · {_num(row['ours'])} показов · ответить до {_dm(req.due_at)}")
    return req


def send_all(db: Session, period: str, user, today: Optional[date] = None) -> List[PublisherRequest]:
    """«Отправить все готовые» — только строки «готово»."""
    return [send(db, r["publisher_id"], period, user, today)
            for r in B.month_rows(db, period, today) if r["status"] == B.READY]


def reply(db: Session, req: PublisherRequest, user, body: Optional[str], volume=None,
          today: Optional[date] = None) -> PublisherRequestMessage:
    """«Ответить площадке»: ход переходит к площадке, срок снова +2 рабочих дня (дизайн 26.10)."""
    today = today or date.today()
    _open(req)
    body, volume = _clean(body), _volume(volume)
    if not body and volume is None:
        raise ReconError(400, "Напишите ответ или предложите цифру")
    m = _msg(db, req, "мы", body, volume, user.name, user.email)
    due = add_workdays(today, ANSWER_WORKDAYS)
    if req.due_at != due:
        req.due_at = due
        _msg(db, req, "система", f"срок ответа продлён · до {_dm(due)}")
    req.our_seen_at = datetime.utcnow()
    db.flush()
    return m


def remind(db: Session, req: PublisherRequest, today: Optional[date] = None) -> PublisherRequestMessage:
    """«Напомнить» — строка в переписке, не чаще раза в рабочий день; статус и срок не меняются (предложение
    дизайна 26.10)."""
    today = today or date.today()
    _open(req)
    if _last_side(db, req) == "площадка":
        raise ReconError(409, "Площадка уже ответила — ход за нами")
    sent = db.execute(text("""SELECT 1 FROM publisher_request_message WHERE request_id = :r AND side = 'система'
                              AND body LIKE 'напомнили%' AND created_at::date = :d"""),
                      {"r": req.id, "d": today}).first()
    if sent:
        raise ReconError(409, "Сегодня уже напоминали")
    return _msg(db, req, "система", f"напомнили {_dm(today)}")


def spread(total: int, weights: Dict[int, int]) -> Dict[int, int]:
    """Итог по размещениям пропорционально нашему факту; остаток округления — наибольшим дробным частям.
    Без факта — поровну. Сумма всегда равна `total`."""
    keys = sorted(weights)
    if not keys:
        return {}
    base = sum(weights.values())
    raw = {k: (total * weights[k] / base if base else total / len(keys)) for k in keys}
    out = {k: int(raw[k]) for k in keys}
    rest = total - sum(out.values())
    for k in sorted(keys, key=lambda k: (-(raw[k] - out[k]), k))[:rest]:
        out[k] += 1
    return out


def agree(db: Session, req: PublisherRequest, user, volume, today: Optional[date] = None) -> PublisherRequest:
    """«Согласовать итог N» — финальное решение менеджера: пишем нашу цифру, цифру площадки и итог, CPM на сейчас
    и разнесение по размещениям. Без возврата."""
    # Два «Согласовать» разом: второй ждёт первого на замке строки и видит уже зафиксированный итог — 409, а не
    # нарушение ключа строк разнесения (500) (ревью 26.10.2026).
    if req is not None:
        db.execute(text("SELECT id FROM publisher_request WHERE id = :r FOR UPDATE"), {"r": req.id})
        db.refresh(req)
    _open(req)
    volume = _volume(volume)
    if volume is None:
        raise ReconError(400, "Укажите итог показов")
    facts = B.target_facts(db, req.publisher_id, req.period)
    cpm = db.execute(text("SELECT cpm_contract FROM sales_publishers WHERE id = :p"),
                     {"p": req.publisher_id}).scalar()
    rc = req.recon or PublisherRecon(request_id=req.id)
    rc.our_volume, rc.agreed_volume, rc.cpm = sum(facts.values()), volume, cpm
    db.add(rc)
    for tid, v in spread(volume, facts).items():
        db.add(PublisherReconLine(request_id=req.id, target_id=tid, our_volume=facts[tid], agreed_volume=v))
    req.verdict, req.decided_at = B.AGREED, datetime.utcnow()
    req.decided_by, req.decided_email = user.name or user.email, user.email
    req.our_seen_at = datetime.utcnow()     # решение принято по прочитанному — «новое» в строке гаснет
    _msg(db, req, "система", f"Итог согласован: {_num(volume)} показов")
    db.flush()
    return req


def mark_seen(req: PublisherRequest, side: str) -> None:
    now = datetime.utcnow()
    if side == "площадка":
        req.pub_seen_at = now
    else:
        req.our_seen_at = now


# ── сторона площадки (через шлюз кабинета) ───────────────────────────────────────────────────────────

def publisher_answer(db: Session, req: PublisherRequest, author: str, email: Optional[str], agree: bool,
                     volume=None, body: Optional[str] = None, free: bool = False) -> PublisherRequestMessage:
    """Ответ площадки. «Согласен» — с цифрой, которую мы предложили последним сообщением, а если не
    предлагали — с нашими данными. «Есть расхождение» — без своей цифры не отправляется (дизайн 26.10).
    `free` — просто сообщение в переписке (вопрос, уточнение, своя цифра по желанию): текст обязателен."""
    _open(req)
    body = _clean(body)
    if free:
        volume = _volume(volume)
        if not body:
            raise ReconError(400, "Напишите сообщение")
    elif agree:
        offer = None
        if _last_side(db, req) == "мы":
            offer = db.execute(text("""SELECT volume FROM publisher_request_message WHERE request_id = :r
                                       AND side = 'мы' ORDER BY id DESC LIMIT 1"""), {"r": req.id}).scalar()
        # Не предлагали — соглашается с нашими данными НА СЕЙЧАС: снимок при отправке мог отстать от досчёта DSP.
        volume = offer if offer is not None else sum(B.target_facts(db, req.publisher_id, req.period).values())
        body = body or "Согласны"
    else:
        volume = _volume(volume)
        if volume is None:
            raise ReconError(400, "Укажите показы по вашим данным за месяц")
    m = _msg(db, req, "площадка", body, volume, author, email)
    if volume is not None:
        rc = req.recon or PublisherRecon(request_id=req.id)
        rc.their_volume = volume
        db.add(rc)
    req.pub_seen_at = datetime.utcnow()
    db.flush()                         # доска читает сырым SQL — без flush она не видит цифру площадки
    return m


# ── вложения ─────────────────────────────────────────────────────────────────────────────────────────

def save_file(db: Session, message: PublisherRequestMessage, original: str, content_type: Optional[str],
              content: bytes, root: str = "/app/uploads") -> PublisherRequestFile:
    # После итога сверка закрыта и для файлов (ревью 26.10.2026): иначе рядом с зафиксированным итогом появлялись бы
    # «подтверждения», которые уже ничего не меняют.
    _open(db.get(PublisherRequest, message.request_id))
    original = original or "file"
    ext = os.path.splitext(original)[1].lower()
    if ext not in FILE_EXT:
        raise ReconError(415, f"Разрешены: {', '.join(sorted(FILE_EXT))}")
    if len(content) > FILE_MAX:
        raise ReconError(413, f"Файл больше {FILE_MAX // 1024 // 1024} МБ")
    safe = re.sub(r"[^\w.\-]", "_", original)
    stored = f"m{message.id}_{uuid.uuid4().hex[:8]}_{safe}"   # тот же файл дважды — две копии, а не перезапись
    os.makedirs(os.path.join(root, FILE_DIR), exist_ok=True)
    with open(os.path.join(root, FILE_DIR, stored), "wb") as fh:
        fh.write(content)
    f = PublisherRequestFile(message_id=message.id, path=f"{FILE_DIR}/{stored}", original_name=original,
                             content_type=content_type, size_bytes=len(content))
    db.add(f)
    db.flush()
    return f
