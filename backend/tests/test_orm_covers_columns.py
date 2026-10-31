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
from app.models import Contract
from app.sales.models import SalesAdvertiser, SalesAnnex

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
           PublisherRequest, PublisherRecon,
           # Расширено 31.10.2026. Договор, рекламодатель и приложение порождают
           # ЮРИДИЧЕСКИЙ документ, и потерянное поле здесь — не пустая ячейка, а неверные
           # реквизиты в подписанном. Поймано на себе: `contracts.annex_word`,
           # `sales_advertisers.legal_name` и `sales_annexes.doc_kind` завели миграцией и не
           # добавили в модели. Сборка читала `getattr(contract, "annex_word", None)` —
           # тумблер «Приложение / ДС» молча возвращал бы None всегда, и ни один тест
           # этого не видел: юр. названия шли сырым SQL, а вид документа — чистой функцией.
           Contract, SalesAdvertiser, SalesAnnex]


# Колонки вне модели НАМЕРЕННО — исключены поимённо, а не ослаблен весь прибор: любая
# НОВАЯ колонка договора, забытая в модели, по-прежнему валит тест.
#
# Пять колонок `contracts` (`doc_type`, `edo_signed_at`, `edo_status`, `nds`,
# `own_legal_role`) заведены мимо кода и в ORM их нет. `migrations/README.md` записывает
# их как мёртвые («ни одна строка кода их не читает… эта запись и есть заморозка») —
# **но это устарело**: с 28.10.2026 их читает карточка договора, сырым SQL в
# `app/contract_card/service.py::head()` («есть в таблице, но не в модели — читаем таблицу
# напрямую»). Найдено 31.10.2026 при расширении этого прибора.
#
# Исключение от этого верно и остаётся: их ЧИТАЮТ, но через ORM не ПИШУТ, а прибор ловит
# ровно потерянную запись через модель. Маппить их сейчас — отдельное решение, не эта
# правка; прибор `test_frozen_list_does_not_rot` скажет, если их однажды замаппят.
FROZEN = {
    "contracts": {"doc_type", "edo_signed_at", "edo_status", "nds", "own_legal_role"},
}


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
    missing = in_db - in_model - FROZEN.get(model.__tablename__, set())
    assert not missing, (
        f"{model.__tablename__}: колонки есть в базе, но не в модели — {sorted(missing)}. "
        "Присваивание такому полю не падает и не сохраняется.")


def test_frozen_list_does_not_rot():
    """Каждая замороженная колонка всё ещё есть в базе и всё ещё НЕ в модели.

    Иначе список превращается в слепое пятно: колонку замаппят или удалят, а исключение
    останется и будет молча прикрывать то, чего уже нет.
    """
    by_name = {m.__tablename__: m for m in WATCHED}
    db = SessionLocal()
    try:
        for table, cols in FROZEN.items():
            in_db = {c for (c,) in db.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t"), {"t": table})}
            in_model = {c.name for c in inspect(by_name[table]).columns}
            gone = cols - in_db
            mapped = cols & in_model
            assert not gone, f"{table}: заморожены, но в базе их уже нет — {sorted(gone)}"
            assert not mapped, f"{table}: заморожены, но уже в модели — убрать из FROZEN: {sorted(mapped)}"
    finally:
        db.close()
