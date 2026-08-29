"""Модель ORM обязана покрывать колонки таблицы. Прибор на молчаливую ошибку.

Найдено 28.08.2026: `decided_email` завели миграцией, а в модель добавить забыли.
`rec.decided_email = ...` при этом НЕ падает — Python послушно кладёт атрибут на объект,
SQLAlchemy о нём ничего не знает, и значение просто не доезжает до базы. Ни ошибки, ни
исключения; узнать можно только заглянув в таблицу и увидев там NULL.

Проверяются таблицы, куда пишет не только ядро или где снимок автора несёт юридический
смысл: там цена такой потери выше всего. Список расширяется по мере надобности — это не
попытка покрыть все 78 таблиц, а страховка на самых дорогих.

Обратное направление (в модели есть, в базе нет) ловится само: первый же запрос падает.
"""
import pytest
from sqlalchemy import inspect, text

from app.database import SessionLocal
from app.launch_prep.models import (LaunchPrepCreativeSet, LaunchPrepPair,
                                    LaunchPrepPairFile, LaunchPrepReview,
                                    LaunchPrepTarget)
from app.cabinet.models import CabinetAccount

WATCHED = [LaunchPrepReview, LaunchPrepPair, LaunchPrepPairFile, LaunchPrepTarget,
           LaunchPrepCreativeSet, CabinetAccount]


@pytest.mark.parametrize("model", WATCHED, ids=[m.__tablename__ for m in WATCHED])
def test_model_maps_every_column(model):
    db = SessionLocal()
    try:
        in_db = {c for (c,) in db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t"),
            {"t": model.__tablename__})}
    finally:
        db.close()
    in_model = {c.name for c in inspect(model).columns}
    missing = in_db - in_model
    assert not missing, (
        f"{model.__tablename__}: колонки есть в базе, но не в модели — {sorted(missing)}. "
        "Присваивание такому полю не падает и не сохраняется.")
