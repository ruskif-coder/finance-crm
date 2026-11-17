"""Ручной запуск фоновых заданий с экрана статуса: «Запустить» / «Перезапустить» (хендофф 16.11.2026, только админ).

Задание запускается ОТДЕЛЬНЫМ ПРОЦЕССОМ — тем же `python -m <модуль>`, что и крон: в процессе бэкенда тяжёлый
пересчёт съел бы память воркера (см. заметку «кроны отдельным процессом»). Ждёт его фоновая нить; по завершении
строка `system_job_run` закрывается итогом, а запустившему, если задание упало, уходит уведомление.

Параллельный запуск того же задания запрещает база (уникальный индекс по незакрытым строкам). Строка, оставшаяся
открытой после перезапуска бэкенда посреди задания, через `STALE_HOURS` считается оборвавшейся и не блокирует.
"""
import logging
import subprocess
import sys
import threading
from typing import Dict, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

log = logging.getLogger("finance.status")

# Ключ проверки → (модуль задания, как в кроне docs/CRON_после_релиза.md). Ключи — те же, что у строк экрана.
JOBS: Dict[str, str] = {
    "job_notify": "app.notify.scanner",
    "job_erid": "app.launch_prep.erid_auto",
    "job_dsp_stat": "app.dsp.stat_daily",
    "job_bidder": "app.ad.daily_shares",
    "job_outward_digest": "app.notify.outward.digest",
}
STALE_HOURS = 3
TIMEOUT_S = 3600


class AlreadyRunning(Exception):
    pass


def running(db: Session) -> Dict[str, dict]:
    """{ключ задания: {started_at, by}} — что сейчас выполняется по ручному запуску."""
    return {r[0]: {"started_at": r[1], "by": r[2]} for r in db.execute(text(f"""
        SELECT j.job_key, j.started_at, u.name FROM system_job_run j LEFT JOIN users u ON u.id = j.started_by
         WHERE j.finished_at IS NULL AND j.started_at > now() - interval '{STALE_HOURS} hours'""")).all()}


def _close_stale(db: Session, key: Optional[str] = None) -> None:
    db.execute(text(f"""UPDATE system_job_run SET finished_at = now(), ok = false,
                          error = 'оборвался: бэкенд перезапустился, итога нет'
                         WHERE finished_at IS NULL AND started_at <= now() - interval '{STALE_HOURS} hours'
                           AND (CAST(:k AS varchar) IS NULL OR job_key = :k)"""), {"k": key})


def start(db: Session, key: str, user_id: Optional[int], spawn: bool = True, title: Optional[str] = None) -> int:
    """Открыть строку запуска и (по умолчанию) запустить процесс. Идёт уже — `AlreadyRunning`."""
    _close_stale(db, key)
    try:
        run_id = db.execute(text("INSERT INTO system_job_run (job_key, started_by) VALUES (:k, :u) RETURNING id"),
                            {"k": key, "u": user_id}).scalar()
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AlreadyRunning(key)
    if spawn:
        threading.Thread(target=_run, args=(run_id, key, user_id, title or key), daemon=True).start()
    return run_id


def _run(run_id: int, key: str, user_id: Optional[int], title: str) -> None:
    ok, err = False, None
    try:
        p = subprocess.run([sys.executable, "-m", JOBS[key]], cwd="/app", capture_output=True, text=True,
                           timeout=TIMEOUT_S)
        ok = p.returncode == 0
        if not ok:
            err = ((p.stderr or "") + (p.stdout or "")).strip()[-600:] or f"код выхода {p.returncode}"
    except subprocess.TimeoutExpired:
        err = f"не уложилось в {TIMEOUT_S // 60} мин"
    except Exception as e:  # noqa: BLE001 — итог пишется в строку, а не теряется в нити
        err = str(e)[:600]
    finish(run_id, title, user_id, ok, err)


def finish(run_id: int, title: str, user_id: Optional[int], ok: bool, err: Optional[str]) -> None:
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        db.execute(text("UPDATE system_job_run SET finished_at = now(), ok = :ok, error = :e WHERE id = :i"),
                   {"ok": ok, "e": err, "i": run_id})
        db.commit()
        if not ok and user_id:
            from app.notify import bus
            bus.emit(db, "system_job_failed", title=f"Задание упало после ручного запуска: {title}",
                     body=(err or "")[:400], link="/settings/system", tone="bad", user_ids=[user_id])
            db.commit()
    except Exception:  # noqa: BLE001
        log.exception("итог ручного запуска %s не записан", title)
    finally:
        db.close()
