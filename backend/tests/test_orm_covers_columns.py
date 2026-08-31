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
from app.cabinet.models import (Cabinet, CabinetAccount, CabinetAccountPublisher,
                                CabinetLog, CabinetOurContact, CabinetPublisher)
from app.publisher_requests import PublisherRecon, PublisherRequest

# Расширено 30.08.2026 на остальные таблицы внешнего контура и тикетов. Причина та же,
# что была у `decided_email`: в эти таблицы пишет не только ядро, а часть полей несёт
# снимок стороннего лица — потеря там не видна ни в логах, ни на экране.
WATCHED = [LaunchPrepReview, LaunchPrepPair, LaunchPrepPairFile, LaunchPrepTarget,
           LaunchPrepCreativeSet,
           Cabinet, CabinetPublisher, CabinetAccount, CabinetAccountPublisher,
           # Журнал кабинета попадает сюда по той же причине, что и остальные: в него
           # пишут обе стороны, и его читает ВНЕШНИЙ контур — потерянное поле означает
           # не пустую ячейку, а строку, которую площадка увидит без автора или без тона.
           CabinetLog, CabinetOurContact,
           PublisherRequest, PublisherRecon]


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
