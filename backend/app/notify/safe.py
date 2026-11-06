# -*- coding: utf-8 -*-
"""«Сбой уведомления не роняет действие» — через savepoint, а не через глотание исключения (аудит 21.10.2026).

Поймать исключение мало: если внутри уведомления упал запрос к базе (flush строки панели, журнал отправок), транзакция
сессии уже отравлена, и `commit` вызывающего падает — откатывается само действие (перевод стадии, «Отправить в ДО»,
запуск). А `db.rollback()` в обработчике уносит заодно всё, что действие и соседние уведомления успели записать.
Savepoint откатывает только своё."""
import logging
from contextlib import contextmanager

log = logging.getLogger("finance.notify")


@contextmanager
def quiet(db, what: str):
    """Выполнить тело в savepoint; сбой — в лог, наружу не выходит. Без настоящей сессии (подмены в тестах) — просто try."""
    nested = getattr(db, "begin_nested", None)
    # Отложенные записи САМОГО действия — до savepoint и вне перехвата: begin_nested сбрасывает их внутри, и ошибка действия
    # (уникальный индекс, ограничение) иначе глоталась как «уведомление не ушло», а дальше падала PendingRollbackError (ревью 22.10.2026).
    flush = getattr(db, "flush", None)
    if nested is not None and flush is not None:
        flush()
    try:
        if nested is None:
            yield
        else:
            with nested():
                yield
    except Exception:  # noqa: BLE001
        log.exception("уведомление не ушло: %s", what)


def outward(db, what: str, send):
    """Уведомление площадке (`notify_publisher`) в savepoint БЕЗ контекст-менеджера.

    `notify_publisher` фиксирует базу сам (лента кабинета — первой). Внутри `with db.begin_nested()` такой `commit` закрывал
    savepoint, и следующая же команда падала «Can't operate on closed transaction inside context manager» — с 02.11.2026 сверка и
    приоритезация доходили до площадки только строкой ленты, без письма и бота (06.11.2026). Ручной savepoint после `commit`
    просто неактивен, работа идёт дальше. Сбой ДО коммита откатывает только savepoint — записи вызывающего целы (аудит 21.10.2026);
    сбой после — только то, что после коммита."""
    sp = db.begin_nested()
    try:
        out = send()
    except Exception as e:  # noqa: BLE001
        if sp.is_active:
            sp.rollback()
        else:
            db.rollback()
        log.warning("Площадке не ушло «%s»: %s", what, e)
        return {"status": "error", "why": str(e)[:200]}
    if sp.is_active:
        sp.commit()
    return out
