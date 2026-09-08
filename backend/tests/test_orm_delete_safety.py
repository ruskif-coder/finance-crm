# -*- coding: utf-8 -*-
"""Родитель с обязательным ребёнком обязан уметь удаляться.

ПРОИСШЕСТВИЕ 08.09.2026, прод: «Не удалось удалить» на креативе сделки ZCBPLS. У
дочерней таблицы `set_id` объявлен `NOT NULL`, а relationship — без `passive_deletes` и
без `delete-orphan`. SQLAlchemy в такой связке не отдаёт удаление каскаду базы: он сам
грузит детей и проставляет им внешний ключ `NULL`. Колонка это запрещает — `IntegrityError`,
500-я и сообщение без причины.

Обход по всем моделям нашёл ПЯТЬ мест с этой формой. Два стреляли, одно держалось на
ручной проверке в единственной точке вызова, два ждали своего часа. Глазами такое не
ищется: связей в проекте под сорок, а признак составной — он в модели РЕБЁНКА.

Правило, которое держит этот прибор: **если внешний ключ ребёнка `NOT NULL`, у связи
должен быть либо `delete-orphan` (ORM удалит детей), либо `passive_deletes=True` (удалит
база каскадом).** Любой третий вариант — «удалить нельзя» в интерфейсе.

Исключения перечислены поимённо и с причиной. Пустой список исключений был бы враньём:
у `SalesAdvertiser.brands` в базе НЕТ каскада, и лечить его этим правилом нельзя.
"""
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import RelationshipProperty

import app.ad.models           # noqa: F401
import app.backlog_models      # noqa: F401
import app.cabinet.models      # noqa: F401
import app.diadoc_models       # noqa: F401
import app.launch_prep.models  # noqa: F401
import app.notify.models       # noqa: F401
import app.ord.models          # noqa: F401
import app.publisher_requests  # noqa: F401
import app.sales.models        # noqa: F401
from app.database import Base

# Связь → почему ей позволено быть без каскада и без passive_deletes.
ALLOWED = {
    # У `sales_brands.advertiser_id` в базе стоит NO ACTION, а не CASCADE, поэтому
    # `passive_deletes` здесь был бы ЛОЖЬЮ: база детей не удалит. А `delete-orphan`
    # означал бы «удаляя рекламодателя, стираем его бренды» — это решение о данных,
    # а не о технике. Рекламодателя и не удаляют: реестр гасит его флагом, а склейка
    # (sales_directories.merge_advertiser) обходит ORM bulk-запросами и объясняет
    # почему прямо в комментарии. Трогать связь — значит менять смысл склейки.
    'SalesAdvertiser.brands': 'в базе NO ACTION; удаление рекламодателя — soft-delete и склейка bulk-запросами',
}


def _child_fk_is_required(rel: RelationshipProperty) -> bool:
    """У ребёнка есть колонка внешнего ключа, объявленная NOT NULL."""
    for pair in rel.local_remote_pairs or ():
        remote = pair[1]
        if remote is not None and remote.nullable is False and remote.foreign_keys:
            return True
    return False


def test_every_parent_of_a_required_child_can_be_deleted():
    """Обход всех связей «родитель → коллекция детей» во всех моделях проекта."""
    broken = []
    for mapper in Base.registry.mappers:
        for rel in mapper.relationships:
            if rel.direction.name != 'ONETOMANY':
                continue
            name = f'{mapper.class_.__name__}.{rel.key}'
            if name in ALLOWED or not _child_fk_is_required(rel):
                continue
            cascade = str(rel.cascade)
            if 'delete-orphan' in cascade or rel.passive_deletes:
                continue
            broken.append(f'{name} → {rel.mapper.class_.__name__} (cascade={cascade})')

    assert not broken, (
        'связь без delete-orphan и без passive_deletes при NOT NULL у ребёнка — '
        'удаление родителя упадёт 500-й, а человек увидит «не удалось удалить» '
        'без причины:\n  ' + '\n  '.join(sorted(broken))
    )


def test_the_exception_list_does_not_rot():
    """Исключение живёт, пока живёт связь. Переименовали — список обязан упасть."""
    known = {f'{m.class_.__name__}.{r.key}'
             for m in Base.registry.mappers for r in m.relationships}
    stale = set(ALLOWED) - known
    assert not stale, f'в списке исключений связи, которых больше нет: {stale}'


def test_the_incident_relationship_is_covered():
    """Именно та связь, на которой всё сломалось, обязана остаться защищённой.

    Общее правило выше её и так покрывает, но эта проверка называет виновника по имени:
    если однажды кто-то снимет `passive_deletes`, падение объяснит себя само.
    """
    from app.launch_prep.models import LaunchPrepCreativeSet

    rel = sa_inspect(LaunchPrepCreativeSet).relationships['files']
    assert rel.passive_deletes, 'удаление комплекта снова не отдано каскаду базы'
    assert 'delete-orphan' in str(rel.cascade)
