# -*- coding: utf-8 -*-
"""Область видимости кабинета: SQL и Python обязаны отвечать одинаково.

Правило «какие площадки относятся к этой учётке» записано в системе ДВАЖДЫ, и свести
записи в одну нельзя: кабинет ходит в базу отдельной ролью без доступа к `public`,
поэтому читает представление `pub.account_publisher_v1`, а ядро проверяет запись на
Python (`app/cabinet/scope.py`).

Именно на такой паре система уже расходилась: до 30.08.2026 чтение шло от кабинета, а
запись — по личному списку `cabinet_account_publisher`, и заметить это можно было
только начав раздавать площадки. Поэтому прибор спрашивает у обоих про КАЖДУЮ пару и
требует одинакового ответа.

Стенд строится свой: единственная живая учётка сидит в служебном кабинете, который видит
всё, и на нём любое правило выглядит верным. Проверяются три случая, ради которых
правило и существует: обычный кабинет, служебный и приостановленный.
"""
import pytest
from sqlalchemy import text

from app.cabinet.models import Cabinet, CabinetAccount, CabinetPublisher
from app.cabinet.scope import account_sees_publisher
from app.database import SessionLocal
# Не «лишний импорт»: `cabinet.manager_id` ссылается на `sales_reps`, и без моделей
# продаж в том же реестре SQLAlchemy не соберёт внешний ключ — падает на первом flush.
from app.sales.models import SalesPublisher


@pytest.fixture
def stand():
    """Три кабинета: обычный с одной площадкой, служебный, приостановленный."""
    db = SessionLocal()
    free = [i for (i,) in db.execute(text(
        "SELECT p.id FROM sales_publishers p WHERE NOT EXISTS ("
        "  SELECT 1 FROM cabinet_publisher cp WHERE cp.publisher_id = p.id)"
        " ORDER BY p.id LIMIT 2")).all()]
    if len(free) < 2:
        db.close()
        pytest.skip('нужны две площадки вне кабинетов')

    made = []
    accounts = {}
    # У каждого кабинета СВОЯ площадка: `cabinet_publisher` держит первичный ключ на
    # `publisher_id`, потому что площадка живёт ровно в одном кабинете. Первая редакция
    # стенда привязала одну и ту же к двум — и правило само себя защитило.
    own = {'обычный': free[0], 'пауза': free[1]}
    for tag, kind, state in (('обычный', 'площадка', 'активен'),
                             ('служебный', 'служебный', 'активен'),
                             ('пауза', 'площадка', 'приостановлен')):
        cab = Cabinet(name=f'__область {tag}__', kind=kind, state=state)
        db.add(cab)
        db.flush()
        a = CabinetAccount(email=f'scope-{tag}@lk.local', name=f'Проба {tag}',
                           cabinet_id=cab.id)
        db.add(a)
        db.flush()
        # Служебный связей не хранит по построению — привязка только там, где она уместна.
        if kind != 'служебный':
            db.add(CabinetPublisher(cabinet_id=cab.id, publisher_id=own[tag]))
        made.append(cab.id)
        accounts[tag] = a.id
    db.commit()

    yield type('S', (), dict(db=db, acc=accounts, free=free, own=own))

    db.rollback()
    for cid in made:
        db.execute(text("DELETE FROM cabinet_account WHERE cabinet_id = :c"), {"c": cid})
        db.execute(text("DELETE FROM cabinet_publisher WHERE cabinet_id = :c"), {"c": cid})
        db.execute(text("DELETE FROM cabinet WHERE id = :c"), {"c": cid})
    db.commit()
    db.close()


def _view_says(db, account_id, publisher_id) -> bool:
    return db.execute(text(
        "SELECT 1 FROM pub.account_publisher_v1 "
        " WHERE account_id = :a AND publisher_id = :p"),
        {"a": account_id, "p": publisher_id}).first() is not None


def test_view_and_python_agree_on_every_pair(stand):
    """Главный прибор: по каждой паре оба источника дают один ответ."""
    db = stand.db
    pubs = [p.id for p in db.query(SalesPublisher).order_by(SalesPublisher.id).all()]
    assert pubs, 'на стенде нет площадок — сравнивать нечего'

    checked = 0
    for tag, aid in stand.acc.items():
        acc = db.query(CabinetAccount).filter(CabinetAccount.id == aid).first()
        for pid in pubs:
            sql = _view_says(db, aid, pid)
            py = account_sees_publisher(db, acc, pid)
            assert sql == py, (
                f'кабинет «{tag}», площадка {pid}: представление говорит {sql}, '
                f'проверка записи — {py}. Правило разъехалось.')
            checked += 1
    assert checked >= 3, 'проверено подозрительно мало пар'


def test_ordinary_cabinet_sees_only_its_own(stand):
    """Обычный кабинет видит привязанную площадку и не видит соседнюю."""
    db, own, alien = stand.db, stand.own['обычный'], stand.own['пауза']
    acc = db.query(CabinetAccount).filter(
        CabinetAccount.id == stand.acc['обычный']).first()
    assert account_sees_publisher(db, acc, own)
    assert not account_sees_publisher(db, acc, alien)


def test_service_cabinet_sees_everything_without_links(stand):
    """Служебный видит всё и при этом НЕ хранит связей.

    Подмена его на список всех площадок выглядела бы так же на сегодняшних данных и
    разошлась бы на первой новой площадке — она бы в нём не появилась.
    """
    db = stand.db
    acc = db.query(CabinetAccount).filter(
        CabinetAccount.id == stand.acc['служебный']).first()
    assert account_sees_publisher(db, acc, stand.free[0])
    assert account_sees_publisher(db, acc, stand.free[1])
    assert db.execute(text(
        "SELECT count(*) FROM cabinet_publisher WHERE cabinet_id = :c"),
        {"c": acc.cabinet_id}).scalar() == 0


def test_suspended_cabinet_sees_nothing(stand):
    """У приостановленного не видно даже собственной площадки.

    Приостановка отключает кабинет целиком, и это правило обязано быть в обоих
    источниках: иначе человек перестал бы видеть задания, но мог бы по ним отвечать.
    """
    db = stand.db
    acc = db.query(CabinetAccount).filter(CabinetAccount.id == stand.acc['пауза']).first()
    assert not account_sees_publisher(db, acc, stand.own['пауза'])
    assert not _view_says(db, acc.id, stand.own['пауза'])


def test_frozen_personal_list_is_read_by_nobody():
    """`cabinet_account_publisher` заморожен — и обязан остаться непрочитанным.

    Таблица не удалена (устаревшее в проекте замораживается, а не дропается), но её уже
    один раз начали читать заново: выключатели уведомлений, написанные 30.08, проверяли
    принадлежность по ней, хотя в шапке модели с 28.08 стоит «не читается». Прибор
    ловит именно этот возврат — грепом по коду, потому что в базе он выглядит как
    обычная живая таблица.
    """
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / 'app'
    hits = []
    for f in root.rglob('*.py'):
        if f.name == 'models.py' and f.parent.name == 'cabinet':
            continue          # объявление модели — это не чтение
        tree = ast.parse(f.read_text(encoding='utf-8'))
        # Строки документации и комментарии сюда не попадают: комментариев в дереве нет
        # вовсе, а докстроки снимаются отдельно. Ищем ИМЯ класса в коде и имя таблицы
        # внутри строковых литералов, то есть в сыром SQL.
        docs = {id(n.value) for n in ast.walk(tree)
                if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                and isinstance(n.value.value, str)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == 'CabinetAccountPublisher':
                hits.append(f'{f.relative_to(root)}: класс')
            elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in docs
                    and 'cabinet_account_publisher' in node.value):
                hits.append(f'{f.relative_to(root)}: SQL')
    assert not hits, (
        'личный список площадок снова читают: ' + ', '.join(sorted(set(hits))) +
        '. Правило одно и живёт в app/cabinet/scope.py')
