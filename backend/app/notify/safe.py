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
