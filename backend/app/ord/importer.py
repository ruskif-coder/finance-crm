"""Разбор выгрузок кабинета ОРД в зеркало.

Кабинет отдаёт три файла: изначальные, доходные, расходные договоры. В каждом основной
лист и лист контрагентов. Имена листов фиксированы кабинетом — в отличие от импорта
операций, где лист ищется по содержимому, здесь файл приходит из чужой системы
неизменённым, и другое имя листа означает, что загрузили не тот файл.

Наши договоры в зеркале НЕ заводятся — только помечаются на существующей строке основного
справочника (`Contract.ord_contract_id`). Юрлица не помечаются вовсе: настоящего id ОРД в
выгрузке кабинета нет (только ИНН и название), а `Counterparty.ord_client_id` ждёт этот id
с этапа 2 (API) — писать в него раньше нечего (находка ревью I2, 2026-08-25). У изначального
договора своя таблица: это первое звено ЧУЖОЙ цепочки (рекламодатель → исполнитель), про
которую мы знаем лишь часть, и заводить 87 из 91 рекламодателя контрагентами не нужно —
стороны хранятся атрибутами прямо на строке.
"""
import io
import re
from collections import namedtuple
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy.orm import Session

from app.models import Contract, Counterparty
from app.ord.enums import ACTION_TYPES, CONTRACT_TYPES, SUBJECT_TYPES, code_by_label
from app.ord.registry import ENV_WHEN_UNKNOWN
from app.ord.models import OrdFinalMirror, OrdInitialContract, OrdInitialFinalLink

SHEET_INITIAL = "Изначальные договоры"
SHEET_FINAL = "Доходные договоры"
SHEET_OUTER = "Расходные договоры"


def _sheet(contents: bytes, name: str) -> pd.DataFrame:
    xls = pd.ExcelFile(io.BytesIO(contents))
    if name not in xls.sheet_names:
        raise ValueError(
            f'В файле нет листа «{name}». Есть: {", ".join(xls.sheet_names)}. '
            f'Похоже, загружена не та выгрузка.')
    return pd.read_excel(xls, sheet_name=name)


def _sheet_row_count(contents: bytes, name: str) -> int:
    """Сколько строк в листе — включая те, что parse_* отбросит по пустому id.

    Нужен отдельно от parse_*: те пропускают строку без идентификатора молча
    (`continue`), и «прочитано 0» (не тот файл, кабинет переименовал колонку)
    снаружи неотличимо от «прочитано 152, заведено 0» (обычная повторная
    загрузка) — см. warnings в upsert().
    """
    return len(_sheet(contents, name))


def _text(v: Any) -> Optional[str]:
    """Пустота одна: и NaN, и пустая строка дают None."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s or None


def _inn(v: Any) -> Optional[str]:
    """ИНН приезжает числом, если ячейка «Общий»: 7700000001.0 → «7700000001»."""
    s = _text(v)
    if not s:
        return None
    if s.endswith('.0') and s[:-2].isdigit():
        s = s[:-2]
    return s


def _date(v: Any) -> Optional[date]:
    """Кабинет пишет даты как «01.02.2025», иногда со временем."""
    s = _text(v)
    if not s:
        return None
    for fmt in ('%d.%m.%Y %H:%M', '%d.%m.%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    if isinstance(v, datetime):
        return v.date()
    return None


def _dt(v: Any) -> Optional[datetime]:
    s = _text(v)
    if not s:
        return None
    for fmt in ('%d.%m.%Y %H:%M', '%d.%m.%Y'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _amount(v: Any) -> Optional[float]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _enum(mapping, label, field: str, warnings: List[str]) -> Optional[str]:
    """Подпись → код. Незнакомая подпись пишется в warnings, а не угадывается."""
    text = _text(label)
    if not text:
        return None
    code = code_by_label(mapping, text)
    if code is None:
        warnings.append(f'{field}: неизвестное значение «{text}»')
    return code


def parse_initial(contents: bytes) -> List[Dict[str, Any]]:
    df = _sheet(contents, SHEET_INITIAL)
    out = []
    for _, r in df.iterrows():
        ord_id = _text(r.get('Id изначального договора'))
        if not ord_id:
            continue
        w: List[str] = []
        out.append({
            'ord_id': ord_id,
            'ord_cid': _text(r.get('Cid изначального договора')),
            'number': _text(r.get('Номер изначального договора')),
            'date': _date(r.get('Дата изначального договора')),
            'expiration_date': _date(r.get('Дата окончания срока действия договора')),
            'amount': _amount(r.get('Стоимость услуг по договору')),
            'type': _enum(CONTRACT_TYPES, r.get('Тип договора'), 'Тип договора', w),
            'subject_type': _enum(SUBJECT_TYPES, r.get('Вид договора'), 'Вид договора', w),
            'action_type': _enum(ACTION_TYPES,
                                 r.get('Вид деятельности посреднического договора'),
                                 'Вид деятельности', w),
            'is_agent_acting_for_publisher': _text(r.get('Агент действует')) is not None,
            'client_inn': _inn(r.get('Рекламодатель ИНН/Номер налогоплательщика/'
                                     'Регистрационный номер')),
            'client_name': _text(r.get('Рекламодатель')),
            'contractor_inn': _inn(r.get('Исполнитель ИНН/Номер налогоплательщика/'
                                         'Регистрационный номер')),
            'contractor_name': _text(r.get('Исполнитель')),
            'final_ord_id': _text(r.get('Id доходного договора')),
            # Лист изначальных несёт ещё и ДОХОДНОГО — четырьмя колонками. До
            # 21.09.2026 читался только его идентификатор (ради связи), а номер, ИНН и
            # имя заказчика пропадали. Из-за этого выгрузка, состоящая из одного этого
            # листа, не помечала ни одного нашего договора: 41 доходный в файле
            # владельца от 18.09 и ноль пометок.
            'final_number': _text(r.get('Номер доходного договора')),
            'final_client_inn': _inn(r.get('ИНН заказчика')),
            'final_client_name': _text(r.get('Заказчик')),
            'status': _text(r.get('Статус изначального договора')),
            'status_at': _dt(r.get('Дата статуса изначального договора')),
            'error_text': _text(r.get('Текст ошибки')),
            'warnings': w,
        })
    return out


def parse_final(contents: bytes) -> List[Dict[str, Any]]:
    df = _sheet(contents, SHEET_FINAL)
    out = []
    for _, r in df.iterrows():
        ord_id = _text(r.get('Id доходного договора/ДС'))
        if not ord_id:
            continue
        w: List[str] = []
        out.append({
            'ord_id': ord_id,
            'ord_cid': _text(r.get('Сid договора/ДС')) or _text(r.get('Cid договора/ДС')),
            'number': _text(r.get('Номер доходного договора/ДС')),
            'date': _date(r.get('Дата доходного договора/ДС')),
            'expiration_date': _date(r.get('Дата окончания срока действия договора')),
            'type': _enum(CONTRACT_TYPES, r.get('Тип'), 'Тип', w),
            'client_inn': _inn(r.get('ИНН заказчика')),
            'client_name': _text(r.get('Заказчик')),
            'parent_number': _text(r.get('Номер основного договора')),
            'is_agent_acting_for_publisher': _text(r.get('Агент действует')) is not None,
            'status': _text(r.get('Статус')),
            'status_at': _dt(r.get('Дата статуса')),
            'error_text': _text(r.get('Текст ошибок')),
            'warnings': w,
        })
    return out


def finals_from_initial(initial_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Доходные, о которых рассказывает лист изначальных договоров.

    Строк на один доходный бывает несколько (у него несколько изначальных) — сводим по
    идентификатору. Полей здесь меньше, чем на своём листе: дата, тип и статус доходного
    в этом листе не приходят вовсе. Поэтому строка отсюда НИКОГДА не затирает то, что
    принёс собственный лист доходных, — см. слияние в `upsert_rows`.
    """
    by_id: Dict[str, Dict[str, Any]] = {}
    for r in initial_rows:
        ord_id = r.get('final_ord_id')
        if not ord_id or ord_id in by_id:
            continue
        by_id[ord_id] = {
            'ord_id': ord_id, 'ord_cid': None,
            'number': r.get('final_number'),
            'date': None, 'expiration_date': None, 'type': None,
            'client_inn': r.get('final_client_inn'),
            'client_name': r.get('final_client_name'),
            'parent_number': None, 'is_agent_acting_for_publisher': None,
            'status': None, 'status_at': None, 'error_text': None,
            'partial': True,     # пришёл из чужого листа: не затирает полные данные
            'warnings': [],
        }
    return list(by_id.values())


def parse_outer(contents: bytes) -> List[Dict[str, Any]]:
    df = _sheet(contents, SHEET_OUTER)
    out = []
    for _, r in df.iterrows():
        ord_id = _text(r.get('Id расходного договора/ДС'))
        if not ord_id:
            continue
        w: List[str] = []
        out.append({
            'ord_id': ord_id,
            'ord_cid': _text(r.get('Cid расходного договора/ДС')),
            'number': _text(r.get('Номер расходного договора/ДС')),
            'date': _date(r.get('Дата расходного договора/ДС')),
            'expiration_date': _date(r.get('Дата окончания срока действия договора')),
            'type': _enum(CONTRACT_TYPES, r.get('Тип договора'), 'Тип договора', w),
            'subject_type': _enum(SUBJECT_TYPES, r.get('Вид договора'), 'Вид договора', w),
            'action_type': _enum(ACTION_TYPES, r.get('Вид деятельности'),
                                 'Вид деятельности', w),
            'is_agent_acting_for_publisher': _text(r.get('Агент действует')) is not None,
            'contractor_inn': _inn(r.get('ИНН исполнителя')),
            'contractor_name': _text(r.get('Исполнитель')),
            'status': _text(r.get('Статус расходного договора/ДС')),
            'status_at': _dt(r.get('Дата статуса расходного договора/ДС')),
            'error_text': _text(r.get('Текст ошибок')),
            'warnings': w,
        })
    return out


def _fold(s):
    """Свести кириллические двойники к латинице и убрать разделители.

    В ОРД номер договора пишут и латиницей (`PM-05-12-2023`), и кириллицей
    (`РМ 05-12-2023`), и через пробел вместо дефиса. Без сведения совпадало 28 из 52,
    со сведением — 36.
    """
    CYR, LAT = 'АВЕКМНОРСТУХ', 'ABEKMHOPCTYX'
    table = str.maketrans(CYR + CYR.lower(), LAT + LAT.lower())
    return re.sub(r'[^A-Z0-9]', '', str(s or '').upper().translate(table))


MatchResult = namedtuple('MatchResult', 'contract warning')


def _match_contract(db: Session, number: Optional[str], inn: Optional[str],
                    env: str = ENV_WHEN_UNKNOWN) -> MatchResult:
    """Найти наш договор для пометки среди ещё не помеченных — по номеру, а
    неоднозначность разрешать по ИНН из этой же строки, не угадывать.

    До 2026-08-25 при неудаче номера был фолбэк: если у контрагента (по ИНН) ровно
    один договор без ord_contract_id, помечался он. На боевых данных из 48
    проставленных меток 37 держались на совпадении номера и 11 — на этой догадке:
    единственность договора у контрагента не значит, что это ТОТ договор из ОРД,
    только то, что других вариантов не заведено. Решение владельца: система не
    подбирает соответствие сама — она показывает только то, что совпало буквально.

    Ревью 25.08.2026, находка C1: «буквальное совпадение» само оказалось догадкой —
    свёрнутый номер (см. _fold) не всегда единственен. На боевых данных нашлось
    шесть пар договоров с одинаковым свёрнутым номером (в четырёх — разные
    контрагенты), а старый код брал первого попавшегося кандидата без проверки, что
    он единственный — один раз доказуемо неверно. При двух и более кандидатах
    теперь помечается только тот случай, когда ровно один из них принадлежит
    контрагенту с ИНН из этой же строки выгрузки (`inn` — ИНН заказчика для
    доходных, исполнителя для расходных, см. вызов в _tag_contract): это не
    догадка, а точное совпадение по двум независимым признакам сразу. Не
    разрешилось и так — отказ и предупреждение со списком кандидатов; связь
    расставляет человек через форму сборки.

    Кандидаты каждый раз перечитываются из базы (после db.flush() в upsert только
    что помеченные contract_id больше не попадают в выборку), поэтому одна и та же
    строка дважды не разбирается.

    Возвращает MatchResult(contract, warning): `warning` заполнен, только когда
    кандидатов несколько и неоднозначность НЕ разрешилась — иначе вызывающий код
    (_tag_contract) не смог бы отличить эту ситуацию от «кандидатов вовсе нет»
    (там тоже contract is None, но текст предупреждения другой).
    """
    if not number:
        return MatchResult(None, None)
    folded = _fold(number)
    if not folded:
        return MatchResult(None, None)
    # Кандидат — договор без отметки ИЛИ с отметкой ЧУЖОГО контура, когда пришла боевая
    # выгрузка. Асимметрия та же, что в `app/ord/registry.py`: прод вытесняет песочницу,
    # песочница прод — никогда. Без этого условия боевая загрузка на проде объявила бы
    # «нет у нас» 34 договора из 35, у которых уже стоял демовский идентификатор:
    # демовский и боевой id одного договора выглядят как разные записи, а искать наш
    # договор было негде — все помеченные из выборки исключались (замер 21.09.2026).
    pool = db.query(Contract).filter(Contract.ord_contract_id.is_(None)).all()
    if env == 'prod':
        pool += (db.query(Contract)
                   .filter(Contract.ord_contract_id.isnot(None),
                           Contract.ord_env == 'demo').all())
    candidates = [c for c in pool
                  if c.contract_number and _fold(c.contract_number) == folded]
    if not candidates:
        return MatchResult(None, None)
    if len(candidates) == 1:
        return MatchResult(candidates[0], None)
    if inn:
        by_inn = [c for c in candidates if c.inn == inn]
        if len(by_inn) == 1:
            return MatchResult(by_inn[0], None)
    who = '; '.join(f'{c.counterparty_name or c.inn or "без ИНН"} (id {c.id})'
                    for c in candidates)
    return MatchResult(None, (
        f'номеру «{number}» соответствуют несколько наших договоров без отметки '
        f'ОРД — {who} — не помечен ни один, свяжите вручную в реестре договоров'))


def upsert(db: Session, *, initial: Optional[bytes] = None,
           final: Optional[bytes] = None, outer: Optional[bytes] = None) -> Dict[str, Any]:
    """Наполнить зеркало из ФАЙЛОВ выгрузки кабинета.

    Разбирает листы и передаёт строки общему писателю `upsert_rows`. Второй читатель —
    синк по API (`app/ord/sync.py`): он строит строки той же формы из ответов
    `GET /contracts/*`. Писатель обязан быть один: у него внутри порядок разметки,
    поиск нашего договора со сведением латиницы и создание связей — три места, которые
    в двух копиях разошлись бы молча.
    """
    final_rows = parse_final(final) if final else []
    outer_rows = parse_outer(outer) if outer else []
    initial_rows = parse_initial(initial) if initial else []

    read = {}
    warnings: List[str] = []
    # ── Прочитанные строки по листу — отдельно от заведённых (находка I1) ──
    # parse_* пропускает строку без идентификатора молча (`continue`). Без этого
    # счётчика «прочитано 0» (приложен не тот файл, или кабинет переименовал
    # колонку) снаружи неотличимо от «прочитано 152, заведено 0» (обычная
    # повторная загрузка — импорт идемпотентен): нули везде и ни одного
    # предупреждения. По API такого счётчика нет и не нужно — там длина списка.
    for bytes_, name, rows, key in (
        (final, SHEET_FINAL, final_rows, 'read_final'),
        (outer, SHEET_OUTER, outer_rows, 'read_outer'),
        (initial, SHEET_INITIAL, initial_rows, 'read_initial'),
    ):
        if not bytes_:
            continue
        read[key] = _sheet_row_count(bytes_, name)
        if read[key] and not rows:
            warnings.append(
                f'лист «{name}»: прочитано строк {read[key]}, ни одной с '
                f'распознанным идентификатором — похоже, приложен не тот файл или '
                f'кабинет переименовал колонку')

    stat = upsert_rows(db, initial=initial_rows, final=final_rows, outer=outer_rows)

    # КОНТУР ставим явно — 'prod'. Выгрузку берут руками из БОЕВОГО кабинета, другого у
    # нас нет: тренировочного клиента ОРД не заводили. Оставлять пусто нельзя — пустое
    # значение означает «неизвестно», а неизвестное потом дометит первый попавшийся синк
    # своим контуром. Именно так демо-прогон переворачивал боевые идентификаторы
    # в демовые (F2-03 внешнего аудита 11.09.2026).
    #
    # Уже размеченное не трогаем: если запись когда-то пришла по API демо-контура, её
    # контур — факт, а не догадка.
    from app.models import Contract
    from app.ord.models import OrdInitialContract
    fids = [r.get('ord_id') for r in final_rows + outer_rows if r.get('ord_id')]
    iids = [r.get('ord_id') for r in initial_rows if r.get('ord_id')]
    if fids:
        (db.query(Contract)
           .filter(Contract.ord_contract_id.in_(fids), Contract.ord_env.is_(None))
           .update({Contract.ord_env: 'prod'}, synchronize_session=False))
    if iids:
        (db.query(OrdInitialContract)
           .filter(OrdInitialContract.ord_id.in_(iids), OrdInitialContract.ord_env.is_(None))
           .update({OrdInitialContract.ord_env: 'prod'}, synchronize_session=False))

    stat.update(read)
    stat['warnings'] = warnings + stat['warnings']
    return stat


def upsert_rows(db: Session, *, initial: Optional[List[Dict[str, Any]]] = None,
                final: Optional[List[Dict[str, Any]]] = None,
                outer: Optional[List[Dict[str, Any]]] = None,
                env: Optional[str] = None) -> Dict[str, Any]:
    """Записать зеркало по уже разобранным строкам. Повторный прогон обновляет, а не плодит.

    Единственный писатель зеркала. Источников у него два — файлы выгрузки и API, — и
    форма строк у них общая (см. `parse_initial`/`parse_final`/`parse_outer`).

    Наши договоры помечаются на существующей строке основного справочника (Contract) —
    не заводятся. Порядок обязателен: доходные и расходные размечаются раньше
    изначальных, потому что `ord_initial_final_links.contract_id` ищет уже помеченный
    `Contract.ord_contract_id` — без этого порядка связи находили бы договор только со
    второго прогона.
    """
    stat: Dict[str, Any] = {'clients': 0, 'contracts': 0, 'initial': 0, 'links': 0,
                            'final_seen': 0, 'final_unmatched': 0,
                            'read_initial': 0, 'read_final': 0, 'read_outer': 0,
                            'warnings': []}
    now = datetime.utcnow()

    outer_rows = outer or []
    initial_rows = initial or []
    env = env or ENV_WHEN_UNKNOWN

    # Доходные приходят из ДВУХ мест: своего листа (полные) и листа изначальных
    # (номер + заказчик, без даты и статуса). Неполная строка не затирает полную —
    # иначе загрузка одного листа изначальных стёрла бы статусы, пришедшие раньше.
    final_rows = list(final or [])
    have = {r['ord_id'] for r in final_rows}
    final_rows += [r for r in finals_from_initial(initial_rows) if r['ord_id'] not in have]

    # ── 1. Юрлица: контрагент встретился в выгрузке ОРД ────────────────────────
    # Counterparty.ord_client_id не пишем — в выгрузке кабинета настоящего id
    # юрлица нет вовсе, только ИНН и название (находка I2: суррогат 'xlsx:<ИНН>'
    # под условием «если пусто» намертво занимал колонку, предназначенную для
    # настоящего id ОРД этапа 2, — и не нёс при этом никакой информации сверх
    # самого факта совпадения). Факт «контрагент встретился в этой выгрузке»
    # выводится из данных в любой момент и хранения не требует; здесь только
    # считаем, сколько ИНН выгрузки сопоставились с нашим реестром контрагентов.
    inns = set()
    for r in final_rows:
        if r['client_inn']:
            inns.add(r['client_inn'])
    for r in outer_rows:
        if r['contractor_inn']:
            inns.add(r['contractor_inn'])
    for r in initial_rows:
        if r['client_inn']:
            inns.add(r['client_inn'])
        if r['contractor_inn']:
            inns.add(r['contractor_inn'])

    for inn in inns:
        if db.query(Counterparty).filter(Counterparty.inn == inn).first() is not None:
            stat['clients'] += 1

    # ── 2. Доходные и расходные: пометка Contract.ord_* ────────────────────────
    def _tag_contract(r: Dict[str, Any], kind: str, name_key: str, inn_key: str) -> None:
        """Пометить наш договор отметкой ОРД по одной строке выгрузки.

        Кэша повторного ord_id внутри файла больше нет: db.flush() ниже уже делает
        только что помеченный договор видимым обычному db.query(...).first(), и
        второй заход на тот же ord_id находит его сам — отдельный кэш был мёртвым
        кодом (комментарий обещал обход ещё-не-сброшенного объекта, а по факту
        просто присваивал переменную и ничего с ней не делал — мелочь ревью
        25.08.2026).
        """
        label = 'доходный' if kind == 'final' else 'расходный'
        stat['warnings'] += [f"{label} {r['ord_id']}: {x}" for x in r['warnings']]
        ord_id = r['ord_id']
        row = db.query(Contract).filter(Contract.ord_contract_id == ord_id).first()
        if row is None:
            match = _match_contract(db, r['number'], r.get(inn_key), env)
            row = match.contract
            if row is None:
                note = match.warning or (
                    f"№ «{r['number'] or 'б/н'}» ({r[name_key] or 'без заказчика'}) — "
                    f"такого договора нет в нашем реестре")
                stat['warnings'].append(f"{label} {r['ord_id']}: {note}")
                return note
            row.ord_contract_id = ord_id
            # Контур ставим здесь же: иначе боевой идентификатор лёг бы на строку, всё
            # ещё помеченную как демовая, и следующий прогон счёл бы её чужой.
            row.ord_env = env
            stat['contracts'] += 1
        row.ord_kind = kind
        row.ord_status = r['status']
        row.ord_synced_at = now
        db.flush()
        return None

    def _mirror_final(r: Dict[str, Any], note: Optional[str]) -> None:
        """Записать доходный в зеркало. Причина несовпадения хранится строкой, а не
        живёт предупреждением в отчёте: по отчёту разбирать нельзя, он умирает вместе
        с загрузкой, а список «есть в ОРД, нет у нас» нужен каждый день.

        Разбор человека (`review_*`) загрузка НЕ трогает вовсе: отложенное с
        объяснением не должно всплывать заново после каждой выгрузки. Список «на
        разбор» = `match_note` заполнен И `review_state = 'new'`; сошедшийся уходит из
        него сам, потому что причина обнуляется."""
        row = (db.query(OrdFinalMirror)
                 .filter(OrdFinalMirror.ord_id == r['ord_id'],
                         OrdFinalMirror.ord_env == env).first())
        if row is None:
            row = OrdFinalMirror(ord_id=r['ord_id'], ord_env=env, first_seen_at=now,
                                 review_state='new')
            db.add(row)
        for f in ('ord_cid', 'number', 'date', 'expiration_date', 'type',
                  'client_inn', 'client_name', 'status', 'status_at', 'error_text'):
            v = r.get(f)
            # Неполная строка (из листа изначальных) только дозаполняет; своего листа
            # пустое значение — это факт, и оно перезаписывает.
            if v is not None or not r.get('partial'):
                setattr(row, f, v)
        row.match_note = note
        row.synced_at = now
        stat['final_seen'] += 1
        if note is not None:
            stat['final_unmatched'] += 1
        db.flush()

    for r in final_rows:
        _mirror_final(r, _tag_contract(r, 'final', 'client_name', 'client_inn'))
    for r in outer_rows:
        _tag_contract(r, 'outer', 'contractor_name', 'contractor_inn')

    # ── 3. Изначальные + связи с доходными ──────────────────────────────────
    seen_initial: Dict[str, OrdInitialContract] = {}
    for r in initial_rows:
        stat['warnings'] += [f"изначальный {r['ord_id']}: {x}" for x in r['warnings']]
        ord_id = r['ord_id']
        if ord_id in seen_initial:
            row = seen_initial[ord_id]
        else:
            row = (db.query(OrdInitialContract)
                     .filter(OrdInitialContract.ord_id == ord_id).first())
            if row is None:
                row = OrdInitialContract(ord_id=ord_id)
                db.add(row)
                stat['initial'] += 1
            seen_initial[ord_id] = row
        for f in ('ord_cid', 'number', 'date', 'expiration_date', 'amount', 'type',
                  'subject_type', 'action_type', 'is_agent_acting_for_publisher',
                  'status', 'status_at', 'error_text'):
            setattr(row, f, r[f])
        row.advertiser_inn = r['client_inn']
        row.advertiser_name = r['client_name']
        row.contractor_inn = r['contractor_inn']
        row.contractor_name = r['contractor_name']
        row.synced_at = now
        db.flush()   # нужен row.id для связи ниже

        final_ord_id = r['final_ord_id']
        if not final_ord_id:
            stat['warnings'].append(
                f"изначальный {r['ord_id']}: нет Id доходного договора — связь не создана")
            continue

        link = (db.query(OrdInitialFinalLink)
                  .filter(OrdInitialFinalLink.initial_contract_id == row.id,
                          OrdInitialFinalLink.final_ord_id == final_ord_id)
                  .first())
        if link is None:
            link = OrdInitialFinalLink(initial_contract_id=row.id, final_ord_id=final_ord_id)
            db.add(link)
            stat['links'] += 1
        contract = (db.query(Contract)
                      .filter(Contract.ord_contract_id == final_ord_id).first())
        link.contract_id = contract.id if contract else None
        link.synced_at = now

    db.commit()
    return stat
