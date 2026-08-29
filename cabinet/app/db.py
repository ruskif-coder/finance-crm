"""Подключение кабинета к базе — под ролью `cabinet`, и это главное в этом файле.

Разделение контуров держится не на коде, а на том, ПОД КАКОЙ РОЛЬЮ открыто соединение.
Роль `cabinet` не имеет `USAGE` на схему `public`: таблица, которую заведёт `create_all`
ядра при следующем запуске, для этого процесса физически невидима. Поэтому кабинет —
отдельный процесс, а не второй роутер внутри финансового бэкенда: один процесс держит
один пул под одной ролью, и роутер внутри ядра ходил бы под `finance_user`, который
видит все 78 таблиц.
"""
import os
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("CABINET_DATABASE_URL")
if not DATABASE_URL:
    # Падаем на старте, а не при первом запросе: контур без своей роли молча ходил бы
    # под чужой, и вся конструкция изоляции превратилась бы в комментарий.
    raise RuntimeError("CABINET_DATABASE_URL не задан — контур кабинета не поднимается")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@contextmanager
def scoped_session(publisher_ids):
    """Сессия с УСТАНОВЛЕННОЙ областью видимости площадок.

    **`set_config(..., is_local => true)`, а не `SET`.** Это та самая готча, которая
    убивает весь контур: обычный `SET` живёт до конца соединения, а соединение
    возвращается в пул и достаётся следующему запросу — уже другого паблишера. Ошибка не
    ловится глазами и не воспроизводится под нагрузкой в одно лицо; ловит её только тест
    на два запроса в одном соединении пула.

    Параметром, а не склейкой строки: `SET` не принимает параметров, и именно поэтому
    вокруг него обычно вырастает конкатенация — прямая дорога к инъекции в имя роли.
    `set_config` параметры принимает.

    Пустой список превращается в пустую строку, а её `pub.allowed_publisher_ids()`
    читает как пустой массив: забытая установка показывает НИЧЕГО, а не всё.
    """
    ids = ",".join(str(int(i)) for i in (publisher_ids or []))
    db = SessionLocal()
    try:
        db.execute(text("SELECT set_config('app.publisher_ids', :ids, true)"), {"ids": ids})
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def plain_session():
    """Сессия без области видимости — только для входа и списка площадок учётки.

    Обе эти вещи спрашиваются ДО того, как область известна: по ним она и вычисляется.
    Ни один запрос к заданиям сюда попадать не должен — их view без установленной
    области вернут ноль строк, и это правильное поведение, а не ошибка.
    """
    return SessionLocal()
