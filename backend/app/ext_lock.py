# -*- coding: utf-8 -*-
"""Один запуск на объект: необратимые вызовы наружу не идут параллельно.

Кнопки «DSP» и «ПИКСЕЛЬ WR» — обычные `def`, FastAPI исполняет их в пуле потоков, и
двойной клик означает два одновременных прохода по одной РК. Проверка «уже заведено?»
в каждом из них видит пустоту, и в чужом кабинете появляются две кампании и два
креатива на площадку, которые по API не удалить (аудит 23.09.2026, 4.H2).

ПОЧЕМУ ОТДЕЛЬНОЕ СОЕДИНЕНИЕ. Выгрузка коммитит после каждого креатива, а сессия при
`commit` возвращает соединение в пул — блокировка уровня сессии Postgres уехала бы
вместе с ним и осталась бы висеть на чужом запросе. Поэтому замок держит своё
соединение от входа до выхода и снимается ЯВНО: `close()` отдаёт соединение в пул
живым, а не закрывает его.

ПОЧЕМУ `try`, А НЕ ОЖИДАНИЕ. Второй клик не должен ждать минуту, пока первый заведёт
девятнадцать креативов, а потом пройти по уже заведённому: ему честнее сразу сказать
«идёт», и человек обновит экран.
"""
from contextlib import contextmanager

from sqlalchemy import text

# Первый ключ блокировки — вид операции. 7301 конвейер годового плана, 7302 дайджест.
DSP_PROVISION = 7303
WEBORAMA_PROVISION = 7304
MAIL_FLUSH = 7305          # досылка писем — один прогон за раз
OUTWARD_DIGEST = 7306      # дайджест площадкам — один прогон за раз
STAFF_DISPATCH = 7307      # досылка уведомлений сотрудникам — один прогон за раз


@contextmanager
def only_one(kind: int, obj_id: int, busy_error, what: str):
    """Пропустить внутрь один проход на `(kind, obj_id)`; второму — `busy_error`."""
    from app.database import engine

    conn = engine.connect()
    try:
        got = conn.execute(text("SELECT pg_try_advisory_lock(:a, :b)"),
                           {"a": kind, "b": int(obj_id)}).scalar()
        conn.commit()
        if not got:
            raise busy_error(f"{what} по этой РК уже идёт — дождитесь окончания "
                             f"и обновите экран")
        try:
            yield
        finally:
            try:
                conn.execute(text("SELECT pg_advisory_unlock(:a, :b)"),
                             {"a": kind, "b": int(obj_id)})
                conn.commit()
            except Exception:  # noqa: BLE001
                # Не снялась — соединение в пул НЕ возвращаем: с висящим замком оно
                # отвечало бы «уже идёт» каждому следующему нажатию. `invalidate`
                # закрывает его по-настоящему, и замок уходит вместе с сессией.
                conn.invalidate()
    finally:
        conn.close()


__all__ = ["only_one", "DSP_PROVISION", "WEBORAMA_PROVISION", "MAIL_FLUSH",
           "OUTWARD_DIGEST", "STAFF_DISPATCH"]
