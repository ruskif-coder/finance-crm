"""Фаза 1 обвязки ОРД: чтение из кабинета в наши справочники. Записи в ОРД здесь нет.

Читает API и проставляет ТОЛЬКО наши колонки (`ord_client_id`, `ord_env`, `ord_status`,
`ord_synced_at`). Ничего не создаёт в ОРД и потому безопасна на любом контуре —
в отличие от фазы 2, где отправка необратима.

ЗАЧЕМ ЭТО ПЕРВЫМ. `clientId` обязателен при регистрации договора, а `ord_client_id` у нас
заполнен у 0 из 211 контрагентов (мерено 26.08.2026): выгрузка кабинета идентификаторов
юрлиц не содержит вовсе. Пока их нет, фаза 2 невозможна физически. По API же они берутся
точным запросом `GET /clients?Inn=`.

СОПОСТАВЛЕНИЕ ТОЛЬКО ПО ИНН И ТОЛЬКО ОДНОЗНАЧНОЕ. Нашлось ровно одно юрлицо — берём;
ноль или несколько — пропускаем и называем в отчёте. Имя для сопоставления не годится:
«OKKAM» в ОРД это три разных юрлица, а наш справочник маркетинговый, не юридический.
Подставленный не тот идентификатор уедет в ЕРИР внутри договора и не отзовётся.

ПИСАТЕЛЬ ЗЕРКАЛА ОБЩИЙ С ИМПОРТОМ ФАЙЛОВ. Договоры отдаются в `importer.upsert_rows`.
Второй писатель не заводится намеренно: у него внутри порядок разметки, поиск нашего
договора со сведением латиницы (РМ 09-01-25 и PM-09-01-25 — один договор) и создание
связей. Три места, которые в двух копиях разошлись бы молча, а расхождение проявилось
бы только на сдаче отчётности.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Contract, Counterparty
from app.ord import client, importer
from app.ord.models import OrdKktu


def _digits(value: Optional[str]) -> str:
    return ''.join(ch for ch in (value or '') if ch.isdigit())


def sync_clients(db: Session, limit: Optional[int] = None) -> dict:
    """Проставить `ord_client_id` контрагентам, у которых он пуст, по ИНН.

    `limit` — для первой пробы: прогнать десяток и посмотреть глазами, прежде чем
    трогать две сотни. Отчёт возвращается целиком, а не пишется в лог: его показывает
    экран, и «сколько не сошлось и почему» — единственное, ради чего этот прогон
    запускают повторно.
    """
    rows = (db.query(Counterparty)
              .filter(Counterparty.ord_client_id.is_(None),
                      Counterparty.inn.isnot(None), Counterparty.inn != '')
              .order_by(Counterparty.name).all())
    if limit:
        rows = rows[:limit]

    env = client.env()
    now = datetime.utcnow()
    report = {'env': env, 'looked': 0, 'matched': 0,
              'not_in_ord': [], 'ambiguous': [], 'failed': []}

    for cp in rows:
        inn = _digits(cp.inn)
        if len(inn) not in (10, 12):
            report['failed'].append({'name': cp.name, 'why': f'ИНН «{cp.inn}» не похож на ИНН'})
            continue
        report['looked'] += 1
        try:
            found = client.get('/webapi/v3/clients', {'Inn': inn}) or []
        except client.OrdError as e:
            report['failed'].append({'name': cp.name, 'why': e.message})
            continue
        if not isinstance(found, list):
            found = [found]

        if len(found) == 1:
            cp.ord_client_id = found[0].get('id')
            cp.ord_env = env
            cp.ord_synced_at = now
            report['matched'] += 1
        elif not found:
            # Не поломка: юрлицо просто ещё не заведено в кабинете. Это список работы,
            # а не список ошибок, — поэтому отдельно от `failed`.
            report['not_in_ord'].append({'name': cp.name, 'inn': inn})
        else:
            report['ambiguous'].append({
                'name': cp.name, 'inn': inn, 'count': len(found),
                'ids': [f.get('id') for f in found][:5]})

    db.commit()
    return report


# ── Вторая половина фазы 1: договоры ─────────────────────────────────────────

def _as_date(value):
    """ISO-строка из ответа → date. ОРД отдаёт с временем, нам нужна дата."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).date()
    except ValueError:
        return None


class _Clients:
    """Резолвер «id юрлица в ОРД → (ИНН, название)».

    У доходного и расходного договоров в ответе есть только `clientId`/`contractorId`,
    без ИНН — а наш договор ищется по номеру С УТОЧНЕНИЕМ ПО ИНН, и без него совпадение
    номеров у разных контрагентов разрешалось бы наугад (ровно эта ошибка была найдена
    ревью 25.08.2026: одна отметка стояла на договоре контрагента, чьего ИНН в ОРД нет
    вообще). Сначала смотрим в свой справочник, где id проставил `sync_clients`, потом
    спрашиваем ОРД. Ответы кэшируются на прогон: заказчик повторяется у многих договоров.
    """

    def __init__(self, db: Session):
        self.db = db
        self.cache: dict = {}

    def get(self, ord_client_id):
        if not ord_client_id:
            return (None, None)
        if ord_client_id in self.cache:
            return self.cache[ord_client_id]
        cp = (self.db.query(Counterparty)
                .filter(Counterparty.ord_client_id == ord_client_id).first())
        if cp is not None:
            self.cache[ord_client_id] = (cp.inn, cp.name)
            return self.cache[ord_client_id]
        try:
            found = client.get('/webapi/v3/clients', {'Id': ord_client_id}) or []
        except client.OrdError:
            found = []
        if not isinstance(found, list):
            found = [found]
        value = ((found[0].get('inn'), found[0].get('name')) if found else (None, None))
        self.cache[ord_client_id] = value
        return value


def _final_row(item: dict, clients: _Clients) -> dict:
    """Ответ `FinalContractResponse` → строка в форме `importer.parse_final`."""
    inn, name = clients.get(item.get('clientId'))
    return {
        'ord_id': item.get('id'),
        'ord_cid': item.get('cid'),
        'number': item.get('number'),
        'date': _as_date(item.get('date')),
        'expiration_date': _as_date(item.get('expirationDate')),
        'type': item.get('type'),
        'client_inn': inn,
        'client_name': name,
        'parent_number': None,
        'is_agent_acting_for_publisher': bool(item.get('isAgentActingForPublisher')),
        'status': item.get('status'),
        'status_at': None,
        'error_text': item.get('erirValidationError'),
        'warnings': [],
    }


def _outer_row(item: dict, clients: _Clients) -> dict:
    """Расходный: сторона — исполнитель (площадка), а не заказчик."""
    row = _final_row(item, clients)
    inn, name = clients.get(item.get('contractorId'))
    row['client_inn'] = inn
    row['client_name'] = name
    return row


def _initial_row(item: dict) -> dict:
    """У изначального ИНН обеих сторон приходят прямо в ответе — резолвер не нужен."""
    return {
        'ord_id': item.get('id'),
        'ord_cid': item.get('cid'),
        'number': item.get('number'),
        'date': _as_date(item.get('date')),
        'expiration_date': _as_date(item.get('expirationDate')),
        'amount': item.get('amount'),
        'type': item.get('type'),
        'subject_type': item.get('subjectType'),
        'action_type': item.get('actionType'),
        'is_agent_acting_for_publisher': bool(item.get('isAgentActingForPublisher')),
        'client_inn': item.get('clientInn'),
        'client_name': item.get('clientName'),
        'contractor_inn': item.get('contractorInn'),
        'contractor_name': item.get('contractorName'),
        'final_ord_id': item.get('finalContractId'),
        'status': item.get('status'),
        'status_at': None,
        'error_text': item.get('erirValidationError'),
        'warnings': [],
    }


def sync_contracts(db: Session) -> dict:
    """Прочитать договоры из ОРД и обновить зеркало. В ОРД ничего не пишет.

    Заменяет ручную выгрузку кабинета: `GET /contracts/*` отдаёт то же самое, только
    без файла. Отказ по одному виду не роняет остальные — иначе один битый ответ
    останавливал бы всю сверку.
    """
    env = client.env()
    clients = _Clients(db)
    report: dict = {'env': env, 'read': {}, 'failed': []}
    rows: dict = {'final': [], 'outer': [], 'initial': []}

    for kind, path, build in (
        ('final', '/webapi/v3/contracts/final', lambda i: _final_row(i, clients)),
        ('outer', '/webapi/v3/contracts/outer', lambda i: _outer_row(i, clients)),
        ('initial', '/webapi/v3/contracts/initial', _initial_row),
    ):
        try:
            items = client.get(path) or []
        except client.OrdError as e:
            report['failed'].append({'kind': kind, 'why': e.message})
            continue
        if not isinstance(items, list):
            items = [items]
        report['read'][kind] = len(items)
        rows[kind] = [build(i) for i in items if i.get('id')]

    stat = importer.upsert_rows(db, initial=rows['initial'], final=rows['final'],
                                outer=rows['outer'])
    # Контур ставим ТОЛЬКО тем записям, которые эта выгрузка и принесла. Идентификаторы
    # у нас на руках — они пришли ответом ОРД, второй раз их искать не надо.
    _stamp_env(db, env,
               ids=[r.get('ord_id') for r in rows['final'] + rows['outer'] if r.get('ord_id')],
               initial_ids=[r.get('ord_id') for r in rows['initial'] if r.get('ord_id')])
    db.commit()
    report['written'] = {k: stat[k] for k in ('contracts', 'initial', 'links')}
    report['warnings'] = stat['warnings']
    return report


def _stamp_env(db: Session, env: str, *, ids=None, initial_ids=None) -> None:
    """Проставить контур записям, которые ПРИНЕСЛА ЭТА выгрузка.

    Отдельным шагом, а не внутри писателя: писатель общий с импортом файлов, а файл
    приходит из кабинета, чей контур известен только снаружи.

    ⚠ РАНЬШЕ ЗДЕСЬ БЫЛ ГЛОБАЛЬНЫЙ UPDATE по всем строкам с пустым контуром — и это
    ПЕРЕВОРАЧИВАЛО чужие записи. Пустой контур читается как боевой
    (`registry.ENV_WHEN_UNKNOWN = 'prod'`: выгрузка кабинета приехала до появления
    колонки, и все её идентификаторы боевые). Значит один синк на демо-контуре молча
    объявлял демовыми все записи, пришедшие из боевого кабинета файлом, — и цепочки
    договоров рвались, потому что искать их начинали не на том контуре
    (находка F2-03 внешнего аудита 11.09.2026).

    Теперь метится только то, чьи идентификаторы пришли в ЭТОМ ответе. Условие
    «контур пуст» остаётся: уже размеченное не трогаем — перештамповка чужого контура
    и была бедой.
    """
    from app.ord.models import OrdInitialContract
    if ids:
        (db.query(Contract)
           .filter(Contract.ord_contract_id.in_(list(ids)), Contract.ord_env.is_(None))
           .update({Contract.ord_env: env}, synchronize_session=False))
    if initial_ids:
        (db.query(OrdInitialContract)
           .filter(OrdInitialContract.ord_id.in_(list(initial_ids)),
                   OrdInitialContract.origin == 'ord',
                   OrdInitialContract.ord_env.is_(None))
           .update({OrdInitialContract.ord_env: env}, synchronize_session=False))


def sync_kktu(db: Session) -> dict:
    """Залить справочник ККТУ из ОРД в наше зеркало. В ОРД не пишет.

    Апсерт по коду, без удаления пропавших строк. Классификатор чужой: код, исчезнувший
    из выдачи, мог быть выведен из обращения — но он уже проставлен у брендов и уехал в
    ЕРИР внутри зарегистрированных креативов. Стереть его у себя значило бы потерять
    расшифровку того, что уже отправлено. Пропажу видно по `synced_at`, отставшему от
    остальных, и это разговор с человеком, а не работа скрипта.
    """
    items = client.get('/webapi/v3/dictionaries/kktu') or []
    now = datetime.utcnow()
    report = {'env': client.env(), 'read': len(items),
              'added': 0, 'updated': 0, 'by_level': {}, 'skipped': []}

    existing = {row.code: row for row in db.query(OrdKktu).all()}
    for item in items:
        code = (item.get('code') or '').strip()
        name = (item.get('name') or '').strip()
        level = item.get('level')
        if not code or not name or not isinstance(level, int):
            # Строка без кода, имени или уровня — не «пустая», а непонятная: положив её
            # в справочник, мы предложили бы человеку выбрать неизвестно что.
            report['skipped'].append(item)
            continue
        report['by_level'][level] = report['by_level'].get(level, 0) + 1
        row = existing.get(code)
        if row is None:
            db.add(OrdKktu(code=code, level=level, name=name,
                           parent_code=(item.get('parentCode') or '').strip() or None,
                           synced_at=now))
            report['added'] += 1
        else:
            changed = (row.name != name or row.level != level)
            row.name, row.level = name, level
            row.parent_code = (item.get('parentCode') or '').strip() or None
            row.synced_at = now
            if changed:
                report['updated'] += 1
    db.commit()
    report['total'] = db.query(OrdKktu).count()
    return report

