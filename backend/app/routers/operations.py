from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, case, or_
from app.files_safe import existing_upload_path, remove_upload
from app.database import get_db
from app.xlsx_safe import xlsx_safe
from app.models import Operation, Article, Counterparty, User
from app import own_company
from app.audit import log_action
from app.permissions import require_permission
from app.routers.reports import (_due_date, _aging_bucket, _term_days_for_counterparty,
                                 DEFAULT_TERM_DAYS)
from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import date, datetime
from datetime import date as _Date  # alias: see OperationCreate note below
from collections import deque
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.datavalidation import DataValidation
import pandas as pd
import io
import re
import uuid

router = APIRouter()

# Потолок выгрузки. Не «сколько влезет в Excel», а сколько мы готовы держать один
# поток и одно соединение: 3 048 строк это 957 мс, дальше линейно.
EXPORT_MAX_ROWS = 20000

# Словарь статусов операции. Раньше сервер принимал ЛЮБУЮ строку, а интерфейс предлагал
# только эти три — и расхождение выяснялось бы на отчётах, которые фильтруют по точному
# совпадению: строка с опечаткой в статусе просто выпадает из всех сводок, оставаясь в
# журнале. Замер 11.09.2026: в базе ровно три значения, дырой пока не пользовались.
OPERATION_STATUSES = ("ОПЛАЧЕНО", "ПЛАН ПОСТУПЛЕНИЙ", "ПЛАН ОПЛАТ")


def _operation_problem(op) -> str | None:
    """Что не так со СТРОКОЙ ЖУРНАЛА ДЕНЕГ, или `None`, если всё в порядке.

    Инварианты проверяются на ИТОГОВОМ объекте, а не на теле запроса: при частичной
    правке в теле лежит не вся операция.

    Отдельной функцией — а не только исключением — потому что у правил ЧЕТЫРЕ входа, и
    ведут они себя по-разному. Ручное создание и правка обязаны отказать сразу (400 на
    одну строку). Импорт разбирает СОТНИ строк за раз: там бросить на первой негодной
    значит написать «не получилось» и не сказать, на чём именно, — поэтому он собирает
    список и отказывает целиком, одним понятным сообщением.

    Два из этих четырёх входов проверок не имели вовсе (найдено 11.09.2026): `/import` и
    `/import/apply` строили `Operation(...)` напрямую, а массовая правка — через
    `setattr` в цикле. То есть правила, заведённые в тот же день «чтобы у API не было
    второго набора правил», обходились ровно тем путём, которым в базу попадает больше
    всего строк сразу.
    """
    if op.status not in OPERATION_STATUSES:
        return (f"Неизвестный статус «{op.status}». Допустимы: "
                + ", ".join(OPERATION_STATUSES))
    if (op.income or 0) > 0 and (op.expense or 0) > 0:
        return ("У операции не может быть одновременно дохода и расхода: обе стороны "
                "попадут в отчёты, и обороты раздуются вдвое. Заведите две строки.")
    if not op.article_id:
        return ("Не выбрана статья. Без неё операция не попадёт ни в P&L, ни в ДДС — "
                "деньги будут в журнале и нигде больше.")
    if not (op.period or "").strip():
        return ("Не указан период. Отчёты строятся по нему, и строка без периода из "
                "них выпадает.")
    return None


def _assert_operation_valid(op) -> None:
    """Одна строка: либо проходит, либо 400 с объяснением."""
    problem = _operation_problem(op)
    if problem:
        raise HTTPException(status_code=400, detail=problem)


# Сколько негодных строк перечислять в ответе импорта. Полный список на тысячу строк —
# это стена текста, по которой ничего не найти; десяти хватает, чтобы понять ХАРАКТЕР
# ошибки, а общее число говорит о масштабе.
_IMPORT_PROBLEMS_SHOWN = 10


def _assert_import_rows_valid(db, problems: list) -> None:
    """Импорт либо встаёт целиком, либо не встаёт вовсе.

    Частичный импорт денег — худший из исходов: половина строк в базе, человек видит
    «ошибка» и запускает заново, получая дубли по уже вставленному. Поэтому откат.
    """
    if not problems:
        return
    db.rollback()
    head = "; ".join(problems[:_IMPORT_PROBLEMS_SHOWN])
    tail = (f" … и ещё {len(problems) - _IMPORT_PROBLEMS_SHOWN}"
            if len(problems) > _IMPORT_PROBLEMS_SHOWN else "")
    raise HTTPException(
        status_code=400,
        detail=f"Импорт отменён целиком — в файле {len(problems)} негодных строк. "
               f"Ничего не записано. {head}{tail}")

# Проверка схемы ссылки — общая для договоров, операций и реестра Диадока,
# живёт в app/links.py (раньше была двумя почти одинаковыми копиями).
from app.links import validate_link as _validate_link  # noqa: E402
from app import timez

# Временное in-memory хранилище для шага preview→apply при синхронизации импорта.
# Переживает только до перезапуска backend-контейнера — сознательно временное решение.
#
# Три ограничителя, добавленные 11.09.2026 (F2-25 внешнего аудита). Каждый закрывает свой
# случай, и все три раньше отсутствовали:
#   · СРОК — непринятое превью висело вечно. Разобранный файл это сотни строк с суммами
#     и контрагентами в памяти процесса, и держать их до перезапуска незачем;
#   · ПОТОЛОК — число сессий ничем не ограничивалось: каждый повторный разбор добавлял
#     ещё одну, а `mem_limit` у контейнера 512 МБ;
#   · ВЛАДЕЛЕЦ — `user_id` в сессию клали, но при применении не сверяли. Чужой
#     `import_id` применялся бы как свой, а это запись денег.
IMPORT_SYNC_TTL_MINUTES = 60
IMPORT_SYNC_MAX_SESSIONS = 20
IMPORT_SYNC_CACHE = {}


def _prune_import_cache() -> None:
    """Выбросить протухшие сессии, а если их всё равно много — самые старые."""
    now = datetime.utcnow()
    for k in [k for k, v in IMPORT_SYNC_CACHE.items()
              if (now - v['created_at']).total_seconds() > IMPORT_SYNC_TTL_MINUTES * 60]:
        del IMPORT_SYNC_CACHE[k]
    if len(IMPORT_SYNC_CACHE) > IMPORT_SYNC_MAX_SESSIONS:
        oldest = sorted(IMPORT_SYNC_CACHE.items(), key=lambda kv: kv[1]['created_at'])
        for k, _ in oldest[:len(IMPORT_SYNC_CACHE) - IMPORT_SYNC_MAX_SESSIONS]:
            del IMPORT_SYNC_CACHE[k]

def _sort_map():
    """Колонки, по которым можно сортировать список операций и выгрузку.

    Один словарь на два эндпоинта (список и export) — раньше он был скопирован дважды
    и успел разойтись бы при первой же правке. Все ключи совпадают с именами колонок
    на фронте, кроме «Действий»: там сортировать нечего.

    Период приводится к сортируемому виду («Q2 2026» → «2026-04»), иначе кварталы
    встают между месяцами по алфавиту. ДЗ сортируется по СРОКУ ОПЛАТЫ, а не по метке:
    метка (просрочка/текущая/план) — функция срока и сегодняшней даты, поэтому порядок
    по сроку и есть порядок по «возрасту долга», и правила старения не приходится
    повторять в SQL — они остаются в reports.py в одном экземпляре.
    """
    period_ym = case(
        (Operation.period.like('Q1 %'), func.concat(func.substring(Operation.period, 4, 4), '-01')),
        (Operation.period.like('Q2 %'), func.concat(func.substring(Operation.period, 4, 4), '-04')),
        (Operation.period.like('Q3 %'), func.concat(func.substring(Operation.period, 4, 4), '-07')),
        (Operation.period.like('Q4 %'), func.concat(func.substring(Operation.period, 4, 4), '-10')),
        else_=Operation.period
    )
    # Срок оплаты = первый день месяца после периода + отсрочка контрагента.
    # Квартал длится три месяца — иначе срок по «Q2 2026» считался бы от апреля.
    months = case((Operation.period.like('Q_ %'), 3), else_=1)
    term = func.coalesce(Counterparty.term_days, DEFAULT_TERM_DAYS)
    due = (func.to_date(func.concat(period_ym, '-01'), 'YYYY-MM-DD')
           + func.make_interval(0, months, 0, term))
    # ДЗ есть только у плановых поступлений — у остальных строк колонка пустая,
    # и в сортировке они должны вести себя как пустые, а не как «срок в 1970-м».
    dz = case(((Operation.status == 'ПЛАН ПОСТУПЛЕНИЙ') & (Operation.income > 0), due), else_=None)
    return {
        'date': Operation.date,
        'status': Operation.status,
        'income': Operation.income,
        'expense': Operation.expense,
        'bank': Operation.bank,
        'article': Article.name,
        'counterparty': Counterparty.name,
        'period': period_ym,
        'dz': dz,
        'vat_rate': Operation.vat_rate,
        'vat_fact': Operation.vat_fact,
        'ds_num': Operation.ds_num,
        'invoice': Operation.invoice,
        'invoice_date': Operation.invoice_date,
        'doc': Operation.document_link,
        'description': Operation.description,
    }


def _apply_gaps(query, gaps):
    """Фильтр «Незаполненные»: строки, где не хватает выбранных полей.

    Условия объединяются по ИЛИ — человек ищет, что дозаполнить, и выбрав «нет статьи»
    и «нет периода», хочет увидеть обе дыры, а не их пересечение (оно почти всегда
    пусто). Тот же приём и тот же смысл, что в реестре сделок (_apply_extra_filters).

    Пустая строка считается дырой наравне с NULL: банк и период приходят из импорта
    и правки формой, где «не заполнено» — это ''. Проверка только на NULL прятала бы
    ровно те строки, ради которых фильтр и заводился.
    """
    if not gaps:
        return query
    columns = {'article': Operation.article_id, 'counterparty': Operation.counterparty_id,
               'period': Operation.period, 'bank': Operation.bank}
    conds = []
    for g in gaps:
        col = columns.get(g)
        if col is None:
            continue
        conds.append(col.is_(None) if g in ('article', 'counterparty') else or_(col.is_(None), col == ''))
    return query.filter(or_(*conds)) if conds else query


def _order_by(sort_col, sort_dir):
    """Выражение ORDER BY для списка и выгрузки — одно на двоих, чтобы файл всегда
    совпадал с экраном.

    Пустые значения у ДАТЫ идут первыми в обе стороны — намеренно: операции без даты
    («план поступлений» из импорта, где заполнен только период) должны быть видны сразу
    на первой странице, а не похоронены в хвосте из тысяч строк. Так и был найден баг,
    когда такие строки проваливались на последнюю страницу под sort_dir=desc.

    Для остальных колонок правило обратное: пустые уходят в конец. Иначе сортировка по
    «№ счёта» или «Описанию» открывалась бы страницей сплошных прочерков — формально
    отсортированной, практически бесполезной.
    """
    column = _sort_map().get(sort_col, Operation.date)
    ordered = column.asc() if sort_dir == 'asc' else column.desc()
    return ordered.nulls_first() if sort_col in ('date', None) else ordered.nulls_last()


# Статус дебиторки в списке операций — переиспользует ту же логику возраста долга
# (срок оплаты = период + отсрочка контрагента, редактируемая в реестре + буфер), что и
# /reports/receivables, чтобы статус в /operations всегда совпадал с тем, что показывает отчёт по дебиторке.
RECEIVABLE_STATUS_LABELS = {'overdue': 'Просрочка', 'current': 'Текущая', 'future': 'План'}

def _receivable_status(op):
    """Возвращает ключ статуса дебиторки ('overdue'/'current'/'future') только для операций
    'План поступлений' с income > 0 — остальные (в т.ч. 'unknown', когда срок не определить)
    возвращают None, и колонка в /operations остаётся пустой."""
    if op.status != 'ПЛАН ПОСТУПЛЕНИЙ' or not op.income or op.income <= 0:
        return None
    term_days = _term_days_for_counterparty(op.counterparty)
    due_date = _due_date(op.period, term_days)
    bucket = _aging_bucket(due_date, date.today())
    return bucket if bucket in RECEIVABLE_STATUS_LABELS else None

def compute_vat_fact(income: float, expense: float, vat_rate: float) -> float:
    """Сумма НДС, выделенная из дохода/расхода по ставке vat_rate (НДС "в том числе",
    а не сверху). Используется при создании/редактировании операции (одиночном и
    массовом) и при импорте — выделена в отдельную функцию, т.к. раньше эта формула
    была продублирована в 4 местах по отдельности и однажды уже расходилась
    (см. историю фикса "НДС не пересчитывается при редактировании")."""
    if income and income > 0 and vat_rate and vat_rate > 0:
        return income * vat_rate / (100 + vat_rate)
    if expense and expense > 0 and vat_rate and vat_rate > 0:
        return expense * vat_rate / (100 + vat_rate)
    return 0

class OperationCreate(BaseModel):
    # ВАЖНО: поле "date" ниже маскирует имя типа "date" (datetime.date) внутри
    # тела этого класса после своей строки — Python связывает локальное имя
    # "date" со значением по умолчанию (None) в namespace класса. Из-за этого
    # invoice_date: Optional[date] на самом деле резолвился в Optional[None]
    # (т.е. только None разрешён) — это и было причиной 422 "Input should be
    # None" при попытке передать дату счёта. Поэтому здесь используется алиас
    # _Date вместо голого "date" для типов, объявленных после поля "date".
    date: Optional[_Date] = None
    status: str
    income: float = 0
    expense: float = 0
    bank: Optional[str] = None
    period: Optional[str] = None
    vat_rate: float = 0
    article_id: Optional[int] = None
    counterparty_id: Optional[int] = None
    ds_num: Optional[str] = None
    invoice: Optional[str] = None
    invoice_date: Optional[_Date] = None
    description: Optional[str] = None
    document_link: Optional[str] = None

    # Пентест 2026-07-18 (раздел 9): API принимал отрицательные income/expense и
    # vat_rate=999 (фронт ограничивает дропдауном, но прямой вызов API — нет), что
    # искажало P&L и сумму НДС. Валидируем на входе. vat_fact в модель не входит —
    # считается сервером (compute_vat_fact), клиентское значение игнорируется.
    @field_validator("income", "expense")
    @classmethod
    def _non_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError("Сумма не может быть отрицательной")
        return v

    @field_validator("vat_rate")
    @classmethod
    def _vat_in_range(cls, v):
        if v is not None and not (0 <= v <= 100):
            raise ValueError("Ставка НДС должна быть в диапазоне 0–100")
        return v

@router.get("/")
def get_operations(
    skip: int = 0,
    limit: int = 300,
    status: Optional[List[str]] = Query(None),
    bank: Optional[List[str]] = Query(None),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    article_id: Optional[List[int]] = Query(None),
    counterparty_id: Optional[List[int]] = Query(None),
    period: Optional[List[str]] = Query(None),
    gaps: Optional[List[str]] = Query(None),
    # Точечный показ конкретных операций по id. Нужен для ссылок «открыть операцию»
    # из импорта документов Диадока: без него на операцию нельзя сослаться никак,
    # у реестра нет ни карточки, ни адреса строки.
    ids: Optional[List[int]] = Query(None),
    sort_col: Optional[str] = 'date',
    sort_dir: Optional[str] = 'desc',
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operations", "view"))
):
    query = db.query(Operation)

    if ids:
        query = query.filter(Operation.id.in_(ids))
    if status:
        query = query.filter(Operation.status.in_(status))
    if bank:
        query = query.filter(Operation.bank.in_(bank))
    if date_from:
        query = query.filter(Operation.date >= date_from)
    if date_to:
        query = query.filter(Operation.date <= date_to)
    if article_id:
        query = query.filter(Operation.article_id.in_(article_id))
    if counterparty_id:
        query = query.filter(Operation.counterparty_id.in_(counterparty_id))
    if period:
        query = query.filter(Operation.period.in_(period))
    query = _apply_gaps(query, gaps)

    query = query.outerjoin(Article, Operation.article_id == Article.id)\
                 .outerjoin(Counterparty, Operation.counterparty_id == Counterparty.id)

    total = query.count()

    query = query.order_by(_order_by(sort_col, sort_dir))

    operations = query.offset(skip).limit(limit).all()

    # Приложенные файлы — ОДНИМ запросом на страницу, а не по строке: реестр отдаёт
    # до сотни операций за раз.
    #
    # В колонке «Документы» файл равноправен со ссылкой. До 22.09.2026 строка ничего о
    # файлах не знала, и пиктограмма зависела только от `document_link`: человек
    # прикладывал скан, файл ложился в базу и на диск — а в реестре оставался прочерк.
    # Снаружи это выглядело как «файл не прикрепился», хотя он был на месте: открыть
    # его из реестра было просто нечем.
    op_ids = [op.id for op in operations]
    files_by_op: dict = {}
    if op_ids:
        from app.models import OperationFile
        for f in (db.query(OperationFile)
                  .filter(OperationFile.operation_id.in_(op_ids))
                  .order_by(OperationFile.id).all()):
            files_by_op.setdefault(f.operation_id, []).append(
                {"id": f.id, "name": f.original_name})

    return {
        "total": total,
        "items": [
            {
                "id": op.id,
                "date": op.date,
                "status": op.status,
                "income": op.income,
                "expense": op.expense,
                "bank": op.bank,
                "period": op.period,
                "vat_rate": op.vat_rate,
                "vat_fact": op.vat_fact,
                "article": op.article.name if op.article else None,
                "article_id": op.article_id,
                "counterparty": op.counterparty.name if op.counterparty else None,
                "counterparty_id": op.counterparty_id,
                "ds_num": op.ds_num,
                "invoice": op.invoice,
                "invoice_date": op.invoice_date,
                "description": op.description,
                "document_link": op.document_link,
                "files": files_by_op.get(op.id, []),
                "receivable_status": _receivable_status(op),
            }
            for op in operations
        ]
    }

@router.get("/periods")
def get_periods(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operations", "view"))
):
    """Список уникальных периодов операций, отсортированный по времени (новые сверху).
    Кварталы (Q3 2025) упорядочиваются по первому месяцу квартала наравне с месяцами."""
    sort_key = case(
        (Operation.period.like('Q1 %'), func.concat(func.substring(Operation.period, 4, 4), '-01')),
        (Operation.period.like('Q2 %'), func.concat(func.substring(Operation.period, 4, 4), '-04')),
        (Operation.period.like('Q3 %'), func.concat(func.substring(Operation.period, 4, 4), '-07')),
        (Operation.period.like('Q4 %'), func.concat(func.substring(Operation.period, 4, 4), '-10')),
        else_=Operation.period,
    )
    rows = (
        db.query(Operation.period, sort_key.label('sk'))
        .filter(Operation.period.isnot(None), Operation.period != '')
        .distinct()
        .order_by(sort_key.desc())
        .all()
    )
    return {"periods": [r[0] for r in rows]}

@router.get("/export")
def export_operations(
    status: Optional[List[str]] = Query(None),
    bank: Optional[List[str]] = Query(None),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    article_id: Optional[List[int]] = Query(None),
    counterparty_id: Optional[List[int]] = Query(None),
    period: Optional[List[str]] = Query(None),
    gaps: Optional[List[str]] = Query(None),
    sort_col: Optional[str] = 'date',
    sort_dir: Optional[str] = 'desc',
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operations", "view"))
):
    """Выгружает в XLSX ВСЕ операции, соответствующие текущим фильтрам и
    сортировке страницы /operations — без учёта пагинации (skip/limit), т.е.
    весь отфильтрованный список, а не только видимую страницу. Параметры
    фильтрации/сортировки повторяют GET /operations/, чтобы кнопка "Скачать"
    на фронтенде выгружала ровно то, что выбрано текущими фильтрами."""
    query = db.query(Operation)

    if status:
        query = query.filter(Operation.status.in_(status))
    if bank:
        query = query.filter(Operation.bank.in_(bank))
    if date_from:
        query = query.filter(Operation.date >= date_from)
    if date_to:
        query = query.filter(Operation.date <= date_to)
    if article_id:
        query = query.filter(Operation.article_id.in_(article_id))
    if counterparty_id:
        query = query.filter(Operation.counterparty_id.in_(counterparty_id))
    if period:
        query = query.filter(Operation.period.in_(period))
    query = _apply_gaps(query, gaps)

    query = query.outerjoin(Article, Operation.article_id == Article.id)\
                 .outerjoin(Counterparty, Operation.counterparty_id == Counterparty.id)

    # Порядок общий со списком (см. _order_by): выгрузка обязана совпадать с экраном.
    query = query.order_by(_order_by(sort_col, sort_dir))

    # ПОТОЛОК на выгрузку. Замер 11.09.2026: выгрузка 3 048 операций занимает 957 мс —
    # на порядок дороже самого тяжёлого отчёта и в тридцать раз дороже списка. Всё это
    # время занят и поток, и соединение с базой, а соединений в пуле пятнадцать.
    #
    # Отказ вместо молчаливого обрезания: файл с частью строк выглядит полным, и по нему
    # сведут отчётность, не заметив пропажи. Лучше сказать «сузьте период».
    total = query.count()
    if total > EXPORT_MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=(f"Под фильтры попало {total} операций, а выгрузка отдаёт не более "
                    f"{EXPORT_MAX_ROWS}. Сузьте период или добавьте фильтр — иначе файл "
                    f"пришлось бы обрезать, а обрезанную выгрузку от полной не отличить."))
    operations = query.all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Операции"

    # Колонки выгрузки читаются обратно импортом (_CF_BEST_COLUMN_MAP), поэтому
    # переименование любой из них ломает круг «выгрузил → поправил → загрузил».
    # ИНН добавлен 2026-08-25 именно ради этого круга: без него импорт сопоставляет
    # контрагента по имени, а имя в справочнике живёт в разных формах
    # («ООО "Ромашка"» / «РОМАШКА ООО») — и вместо совпадения заводится дубль.
    #
    # ID — внутренний номер операции. Импорт читает его как НЕСТРОГУЮ подсказку:
    # сам по себе он ничего не сопоставляет (между стендами один номер
    # принадлежит разным операциям), но помогает выбрать нужную из нескольких,
    # уже совпавших по всем содержательным полям. См. _take_from_pool.
    export_columns = [
        ('ID', 9),
        ('Дата', 14), ('Статус', 18), ('Поступления', 14), ('Списания', 14),
        ('Банк', 14), ('Период', 14), ('Статья', 22), ('Контрагент', 28),
        ('ИНН', 14), ('НДС %', 8), ('НДС сумма', 14), ('№ ДС', 14), ('Счет', 14),
        ('Счет от дата', 14), ('Документ', 32), ('Назначение', 35),
        ('Статус ДЗ', 14),
    ]
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for col_idx, (title, width) in enumerate(export_columns, start=1):
        cell = ws.cell(row=1, column=col_idx, value=title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        ws.column_dimensions[cell.column_letter].width = width
    ws.row_dimensions[1].height = 26
    ws.freeze_panes = "A2"

    # Номера колонок с датами считаются из состава, а не проставлены числом:
    # вставка колонки посередине сдвигает их, и формат даты молча уехал бы
    # на соседнюю колонку.
    titles = [t for t, _w in export_columns]
    date_col_idx = titles.index('Дата') + 1
    invoice_date_col_idx = titles.index('Счет от дата') + 1
    for row_idx, op in enumerate(operations, start=2):
        values = [
            op.id,
            op.date, op.status, op.income or None, op.expense or None,
            op.bank, op.period, op.article.name if op.article else None,
            op.counterparty.name if op.counterparty else None,
            op.counterparty.inn if op.counterparty else None,
            op.vat_rate or None, op.vat_fact or None, op.ds_num, op.invoice,
            op.invoice_date, op.document_link, op.description,
            RECEIVABLE_STATUS_LABELS.get(_receivable_status(op)),
        ]
        for col_idx, value in enumerate(values, start=1):
            ws.cell(row=row_idx, column=col_idx, value=xlsx_safe(value))
        ws.cell(row=row_idx, column=date_col_idx).number_format = 'DD.MM.YYYY'
        ws.cell(row=row_idx, column=invoice_date_col_idx).number_format = 'DD.MM.YYYY'

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"operacii_{timez.msk_now().strftime('%Y%m%d_%H%M')}.xlsx"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )

@router.post("/")
def create_operation(
    op: OperationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operations", "create"))
):
    vat_fact = compute_vat_fact(op.income, op.expense, op.vat_rate)

    operation = Operation(
        date=op.date,
        status=op.status,
        income=op.income,
        expense=op.expense,
        bank=op.bank,
        period=op.period,
        vat_rate=op.vat_rate,
        vat_fact=vat_fact,
        article_id=op.article_id,
        counterparty_id=op.counterparty_id,
        ds_num=op.ds_num,
        invoice=op.invoice,
        invoice_date=op.invoice_date,
        description=op.description,
        document_link=_validate_link(op.document_link),
        own_company_id=own_company.sole_id(db),
        created_by=current_user.id
    )
    # Проверка ДО записи: отказать дешевле, чем потом искать строку, выпавшую из отчётов.
    _assert_operation_valid(operation)
    db.add(operation)
    db.commit()
    db.refresh(operation)

    _learn_counterparty_defaults(db, operation)

    log_action(db, current_user, "create_operation", entity_type="operation", entity_id=operation.id,
               details=f"{op.status}, доход {op.income}, расход {op.expense}, банк {op.bank}")
    return {"id": operation.id, "message": "Операция создана"}


def _learn_counterparty_defaults(db: Session, operation: Operation):
    """Самообучение реестра контрагентов (2026-07-16): первая операция направления
    (приход/расход) фиксирует НДС и статью контрагента как значения по умолчанию —
    дальше они автоподставляются в форме операций (см. applyCpDefaults в operations.js).
    Пишем ТОЛЬКО в NULL — заполненное бэкфиллом или руками в карточке не перетирается,
    поэтому ошибка первой операции правится в карточке и больше не возвращается."""
    if not operation.counterparty_id:
        return
    cp = db.query(Counterparty).filter(Counterparty.id == operation.counterparty_id).first()
    if not cp:
        return
    direction = "income" if (operation.income or 0) > 0 else "expense" if (operation.expense or 0) > 0 else None
    if not direction:
        return
    vat_field = f"vat_rate_{direction}"
    art_field = f"default_article_{direction}_id"
    changed = False
    if getattr(cp, vat_field) is None and operation.vat_rate is not None:
        setattr(cp, vat_field, operation.vat_rate)
        changed = True
    if getattr(cp, art_field) is None and operation.article_id is not None:
        setattr(cp, art_field, operation.article_id)
        changed = True
    if changed:
        db.commit()

@router.put("/{op_id}")
def update_operation(
    op_id: int,
    op: OperationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operations", "edit"))
):
    operation = db.query(Operation).filter(Operation.id == op_id).first()
    if not operation:
        raise HTTPException(status_code=404, detail="Операция не найдена")
    # `exclude_unset` — НЕ украшение. Без него `op.dict()` отдаёт ВСЕ поля модели,
    # включая неприсланные, а у них умолчание `None`: PUT без `bank`/`period`/
    # `article_id` молча обнулял их, и операция выпадала и из баланса, и из P&L.
    # Канон проекта на этот случай уже есть — массовая правка ниже давно ходит через
    # `exclude_unset=True`; одиночная просто до него не дошла (11.09.2026).
    data = op.dict(exclude_unset=True)
    for key, value in data.items():
        setattr(operation, key, value)
    # document_link проверяем на безопасную схему (setattr выше записал сырое значение).
    # Только если он действительно прислан — иначе проверка затёрла бы чужую ссылку.
    if "document_link" in data:
        operation.document_link = _validate_link(op.document_link)

    # Пересчёт суммы НДС при сохранении. vat_fact не входит в OperationCreate,
    # поэтому цикл setattr выше его не трогает — без этого блока сумма НДС
    # оставалась прежней (с момента создания операции), даже если при
    # редактировании меняли доход/расход или ставку НДС. Логика та же, что
    # и при создании операции (см. create_operation выше).
    #
    # Считаем от ИТОГОВОЙ строки, а не от присланного тела: при частичном PUT в теле
    # лежат умолчания (нули), и расчёт по ним обнулил бы НДС у нетронутой суммы.
    operation.vat_fact = compute_vat_fact(
        operation.income, operation.expense, operation.vat_rate)

    # Итоговая строка обязана быть валидной — независимо от того, что прислали. Частичная
    # правка может увести операцию из отчётов, ничего не «сломав» на вид.
    _assert_operation_valid(operation)

    db.commit()

    # В журнал — тоже итоговые значения: иначе частичная правка запишет нули,
    # которых в операции нет.
    log_action(db, current_user, "update_operation", entity_type="operation", entity_id=op_id,
               details=f"{operation.status}, доход {operation.income}, "
                       f"расход {operation.expense}, банк {operation.bank}")
    return {"message": "Операция обновлена"}

class OperationBulkUpdate(BaseModel):
    # Поле "date" типизировано через алиас _Date (а не голым "date"), иначе оно
    # маскирует само себя: Python сначала присваивает имени "date" в namespace
    # класса значение None, и только потом резолвит аннотацию "Optional[date]" —
    # к этому моменту "date" уже означает None, и аннотация превращается в
    # Optional[None], из-за чего pydantic требует "date" строго = None (422
    # "Input should be None" при любой реальной дате). См. тот же фикс и более
    # подробное объяснение в OperationCreate выше.
    ids: List[int]
    status: Optional[str] = None
    date: Optional[_Date] = None
    bank: Optional[str] = None
    article_id: Optional[int] = None
    counterparty_id: Optional[int] = None
    period: Optional[str] = None
    vat_rate: Optional[float] = None

class OperationBulkDelete(BaseModel):
    ids: List[int]

@router.patch("/bulk")
def bulk_update_operations(
    payload: OperationBulkUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operations", "edit"))
):
    """Массовое изменение статуса/даты/банка у списка операций одним запросом.
    В отличие от update_operation (PUT, полная перезапись), здесь — частичное
    обновление: меняются только явно переданные поля (exclude_unset), остальные
    поля затронутых операций не трогаются."""
    if not payload.ids:
        raise HTTPException(status_code=400, detail="Не указаны id операций")

    fields = payload.dict(exclude={"ids"}, exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="Не указаны поля для изменения")

    operations = db.query(Operation).filter(Operation.id.in_(payload.ids)).all()
    if not operations:
        raise HTTPException(status_code=404, detail="Операции не найдены")

    for operation in operations:
        for key, value in fields.items():
            setattr(operation, key, value)
        # Если меняется ставка НДС, сумма НДС (vat_fact) пересчитывается тут же —
        # иначе она осталась бы рассчитанной по старой ставке. Та же формула,
        # что и при создании/одиночном редактировании операции (см. выше).
        if 'vat_rate' in fields:
            operation.vat_fact = compute_vat_fact(operation.income, operation.expense, operation.vat_rate)
        # Те же инварианты, что и у одиночной правки. Массовая правка их не проверяла
        # вовсе, то есть строгий путь (PUT) отказывал, а быстрый (выделить сто строк и
        # поменять статус) — пропускал. Отказ адресный: без номера операции человек,
        # выделивший сотню строк, не найдёт виноватую.
        problem = _operation_problem(operation)
        if problem:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=f"Операция #{operation.id}: {problem} Ничего не изменено.")
    db.commit()

    changed_desc = ", ".join(f"{k}={v}" for k, v in fields.items())
    log_action(db, current_user, "bulk_update_operation", entity_type="operation", entity_id=None,
               details=f"ids={payload.ids}; {changed_desc}")

    return {"message": f"Обновлено {len(operations)} операций", "updated": len(operations)}

@router.delete("/bulk")
def bulk_delete_operations(
    payload: OperationBulkDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operations", "delete"))
):
    """Массовое удаление операций по списку id. Зарегистрирован выше
    @router.delete("/{op_id}"), иначе FastAPI пытался бы матчить
    DELETE /operations/bulk в delete_operation(op_id="bulk") и падал
    с 422 на валидации int, не доходя до этого хендлера."""
    if not payload.ids:
        raise HTTPException(status_code=400, detail="Не указаны id операций")

    operations = db.query(Operation).filter(Operation.id.in_(payload.ids)).all()
    if not operations:
        raise HTTPException(status_code=404, detail="Операции не найдены")

    count = len(operations)
    for operation in operations:
        db.delete(operation)
    db.commit()

    log_action(db, current_user, "bulk_delete_operation", entity_type="operation", entity_id=None,
               details=f"ids={payload.ids}; удалено {count}")

    return {"message": f"Удалено {count} операций", "deleted": count}

@router.delete("/{op_id}")
def delete_operation(
    op_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operations", "delete"))
):
    operation = db.query(Operation).filter(Operation.id == op_id).first()
    if not operation:
        raise HTTPException(status_code=404, detail="Операция не найдена")
    details = f"{operation.status}, доход {operation.income}, расход {operation.expense}, банк {operation.bank}"
    db.delete(operation)
    db.commit()

    log_action(db, current_user, "delete_operation", entity_type="operation", entity_id=op_id, details=details)
    return {"message": "Операция удалена"}

_CF_BEST_COLUMN_MAP = {
    'дата': 'date',
    'статус': 'status',
    'поступления': 'income',
    'списания': 'expense',
    'банк': 'bank',
    'период': 'period',
    'ндс': 'vat_rate',
    'ндс факт': 'vat_fact',
    'статья': 'article',
    'контрагент': 'counterparty',
    'инн': 'inn',
    '№ дс': 'ds_num',
    'счет': 'invoice',
    'счет от дата': 'invoice_date',
    'просрочка дней': 'overdue_days',
    'назначение': 'description',
    'ссылка на документ': 'document_link',
    # Синонимы из выгрузки (/operations/export). Она пишет те же поля под другими
    # заголовками, и без этих трёх строк система не читает собственную выгрузку:
    # vat_rate обязателен, а "Документ" молча терял бы все ссылки на первичку.
    'ндс %': 'vat_rate',
    'ндс сумма': 'vat_fact',
    'документ': 'document_link',
    # Внутренний номер операции. Ключом НЕ является и сам по себе ничего не
    # сопоставляет: id уникален внутри стенда, между локалкой и продом один
    # номер принадлежит разным операциям. Используется только как подсказка при
    # выборе из уже совпавших по всем содержательным полям — см. _take_from_pool.
    'id': 'op_id',
}
# Поля без которых парсинг не имеет смысла. overdue_days нигде не используется ниже;
# inn и document_link — новые опциональные поля (см. шаблон массового импорта),
# их отсутствие в старом файле формата CF BEST не должно блокировать импорт.
# vat_fact тоже сделан опциональным: если колонки нет (как в новом шаблоне), сумма
# НДС вычисляется автоматически из дохода/расхода и ставки — так же, как при
# ручном добавлении операции через форму (см. create_operation/update_operation).
_CF_BEST_REQUIRED_FIELDS = set(_CF_BEST_COLUMN_MAP.values()) - {
    'overdue_days', 'inn', 'document_link', 'vat_fact', 'op_id'}

_PERIOD_MONTHS = {
    'январь': 1, 'февраль': 2, 'март': 3, 'апрель': 4,
    'май': 5, 'июнь': 6, 'июль': 7, 'август': 8,
    'сентябрь': 9, 'октябрь': 10, 'ноябрь': 11, 'декабрь': 12,
}

# Квартальный формат план-строк без даты (ПЛАН ОПЛАТ/ПОСТУПЛЕНИЙ): договорились
# хранить такие периоды как "Q1 2026", "Q4 2025" и т.п. Во входящем файле он
# записан по-русски ("1 квартал 2026"), поэтому распознаём оба варианта и
# приводим к единому каноническому виду "QN YYYY" (с заглавной Q и пробелом —
# именно так его ждут reports.py/QUARTER_MONTHS и сортировка в get_operations).
_QUARTER_EN_RE = re.compile(r'q([1-4])\D{0,3}(\d{4})')
_QUARTER_RU_RE = re.compile(r'([1-4])\s*-?\s*(?:[йi]\s*)?кварт\w*\D{0,10}(\d{4})')


def _normalize_period(period: Optional[str], op_date: Optional[date]) -> Optional[str]:
    """Приводит период к формату YYYY-MM — тому же, в котором уже хранятся периоды
    в БД (см. одноразовый скрипт scripts/fix_periods.py (корневая, не публикуемая папка), которым они были нормализованы).
    Без этого синхронизация считала смену формата записи периода ("июль 2024" вместо
    "2024-07") реальным изменением и заводила ложный конфликт почти на каждой строке.

    Исключение — квартальный формат у строк без даты (план/прогноз): если есть
    реальная дата операции, она всегда важнее квартальной "вилки" (актуально для
    исторических операций с протухшей квартальной меткой, см. _normalize_period
    в существующих данных). Но если даты нет вообще, единственная содержательная
    информация о периоде — это квартал, и её нельзя терять, сворачивая в None,
    иначе пропадает сама возможность увидеть смену квартала как конфликт."""
    if not period:
        return op_date.strftime('%Y-%m') if op_date else None
    p = str(period).lower().strip()
    if re.match(r'^\d{4}-\d{2}$', p):
        return p
    for name, num in _PERIOD_MONTHS.items():
        if name in p:
            year_match = re.search(r'\d{4}', p)
            year = int(year_match.group()) if year_match else (op_date.year if op_date else None)
            return f"{year}-{num:02d}" if year else None
    if op_date:
        return op_date.strftime('%Y-%m')
    qm = _QUARTER_EN_RE.search(p) or _QUARTER_RU_RE.search(p)
    if qm:
        return f"Q{qm.group(1)} {qm.group(2)}"
    return None


def _clean_inn(value) -> Optional[str]:
    """ИНН в Excel часто попадает как число (например 7712345678.0), если ячейка
    отформатирована как "Общий" — без этой очистки в БД улетел бы хвост ".0"."""
    if pd.isna(value):
        return None
    s = str(value).strip()
    if s.endswith('.0') and s[:-2].isdigit():
        s = s[:-2]
    return s or None


def _map_header_row(header) -> dict:
    """Сопоставление ячеек одной строки с полями операции: {индекс колонки: поле}.

    Первое вхождение поля выигрывает: файл может нести и "НДС", и "НДС %" —
    оба ведут в vat_rate, и без этого правила в выборку попали бы две колонки
    с одинаковым именем, на чём pandas и ломается."""
    col_map = {}
    for col_idx, value in header.items():
        if pd.isna(value):
            continue
        field = _CF_BEST_COLUMN_MAP.get(str(value).strip().lower())
        if field and field not in col_map.values():
            col_map[col_idx] = field
    return col_map


def _find_import_sheet(contents: bytes):
    """Лист и строка заголовка, которые парсер способен разобрать.

    Имя листа НЕ фиксировано. Раньше здесь стояло pd.read_excel(sheet_name="CF BEST"),
    и система не читала собственную выгрузку: /operations/export пишет лист
    "Операции". Файл при этом содержал ровно те же данные.

    Лист выбирается не по имени, а по тому, все ли обязательные колонки в нём
    нашлись. Имя "CF BEST" (лист шаблона) проверяется первым — не как требование,
    а чтобы на файле шаблона не тратить время на остальные листы.

    Угадывать по одной ячейке "статус" нельзя: на листе "Инструкция" того же
    шаблона есть строка с таким текстом (описание колонки), и такой поиск выбрал
    бы её. Поэтому признак листа — полный набор обязательных колонок.

    Если ни один лист не подошёл, в ошибку идёт ближайший промах: имя листа,
    номер строки и чего именно не хватило. "Не найден лист CF BEST" на файле,
    где не хватает одной колонки, отправляет искать не там."""
    xls = pd.ExcelFile(io.BytesIO(contents))
    names = xls.sheet_names
    order = ([n for n in names if n == "CF BEST"] + [n for n in names if n != "CF BEST"])

    best = None                      # (сколько не хватило, лист, строка, чего нет)
    for name in order:
        raw = pd.read_excel(xls, sheet_name=name, header=None)
        for idx in range(min(len(raw), 30)):
            col_map = _map_header_row(raw.iloc[idx])
            if not col_map:
                continue
            missing = _CF_BEST_REQUIRED_FIELDS - set(col_map.values())
            if not missing:
                return raw, idx, col_map
            if best is None or len(missing) < best[0]:
                best = (len(missing), name, idx + 1, sorted(missing))

    if best:
        _, name, row, missing = best
        raise ValueError(
            f'На листе "{name}" (строка заголовка {row}) не найдены обязательные '
            f'колонки: {missing}')
    raise ValueError('Не найдена строка заголовка ни на одном листе файла. '
                     'Скачайте шаблон импорта и заполните его.')


def _parse_cf_best_rows(contents: bytes) -> List[dict]:
    """Парсит Excel-файл с листом CF BEST в список словарей (без обращения к БД).
    Логика идентична исходному /import — вынесена в helper, чтобы её могли
    использовать и блайнд-импорт, и preview/apply синхронизация.

    Заголовок ищется динамически, а колонки сопоставляются по названию, а не по
    фиксированной позиции. Это позволяет обрабатывать разные варианты выгрузки:
    со служебной шапкой-дашбордом сверху или без неё, с лишними колонками
    (например, "Кредит"/"Дебет") — такие нераспознанные колонки просто
    игнорируются. Имя листа тоже не фиксировано, см. _find_import_sheet."""
    raw, header_row_idx, col_map = _find_import_sheet(contents)

    df = raw.iloc[header_row_idx + 1:].rename(columns=col_map)
    df = df[list(col_map.values())]
    df = df[df['status'].astype(str).str.strip().str.lower() != 'статус'].copy()
    df['date'] = pd.to_datetime(df['date'], errors='coerce')

    rows = []
    for _, row in df.iterrows():
        parsed_date = row['date'].date() if pd.notna(row.get('date')) else None
        raw_period = str(row['period']) if pd.notna(row.get('period')) else None
        parsed_income = float(row['income']) if pd.notna(row.get('income')) else 0
        parsed_expense = float(row['expense']) if pd.notna(row.get('expense')) else 0
        parsed_vat_rate = float(row['vat_rate']) if pd.notna(row.get('vat_rate')) else 0
        if pd.notna(row.get('vat_fact')):
            parsed_vat_fact = float(row['vat_fact'])
        else:
            parsed_vat_fact = compute_vat_fact(parsed_income, parsed_expense, parsed_vat_rate)
        try:
            parsed_op_id = int(float(row['op_id'])) if pd.notna(row.get('op_id')) else None
        except (TypeError, ValueError):
            parsed_op_id = None          # в колонке текст — подсказки просто не будет
        rows.append({
            'op_id': parsed_op_id,
            'date': parsed_date,
            'status': str(row['status']).strip().upper() if pd.notna(row.get('status')) else 'ОПЛАЧЕНО',
            'income': parsed_income,
            'expense': parsed_expense,
            'bank': str(row['bank']) if pd.notna(row.get('bank')) else None,
            'period': _normalize_period(raw_period, parsed_date),
            'vat_rate': parsed_vat_rate,
            'vat_fact': parsed_vat_fact,
            'article': str(row['article']) if pd.notna(row.get('article')) else None,
            'counterparty': str(row['counterparty']) if pd.notna(row.get('counterparty')) else None,
            'inn': _clean_inn(row.get('inn')),
            'ds_num': str(row['ds_num']) if pd.notna(row.get('ds_num')) else None,
            'invoice': str(row['invoice']) if pd.notna(row.get('invoice')) else None,
            'invoice_date': pd.to_datetime(row['invoice_date']).date() if pd.notna(row.get('invoice_date')) else None,
            'description': str(row['description']) if pd.notna(row.get('description')) else None,
            'document_link': _validate_link(row.get('document_link'), raise_on_bad=False),
        })
    return rows


def _get_or_create_article(db: Session, name: Optional[str], created: Optional[list] = None):
    """Статья по имени; неизвестное имя заводит новую.

    Новая статья создаётся БЕЗ разметки `pl_line`, и её деньги попадают в «Требует
    разметки» — не теряются, но и не входят ни в EBITDA, ни в чистую прибыль. Само по
    себе это законное состояние (правило проекта: неразмеченная статья — не ошибка).

    Плохо было другое: создание происходило МОЛЧА. Файл заводил статьи, никто об этом не
    узнавал, и деньги оседали в «Требует разметки» до следующего разбора отчёта. Поэтому
    отказываться не стали — импорт с новой статьёй законная операция, — а имена
    складываем в `created` и показываем в итоге загрузки (F2-21 аудита 11.09.2026).
    """
    if not name:
        return None
    article = db.query(Article).filter(Article.name == name).first()
    if not article:
        article = Article(name=name, type='expense')
        db.add(article)
        db.flush()
        if created is not None:
            created.append(name)
    return article


def _get_or_create_counterparty(db: Session, name: Optional[str], inn: Optional[str] = None):
    """Сопоставление контрагента. ИНН — более надёжный ключ, чем название (которое
    в файлах встречается с разными кавычками/регистром/формой "ООО"/"OOO" и т.п.),
    поэтому при наличии ИНН он проверяется первым. Если контрагент найден по ИНН,
    его карточка не переименовывается даже при расхождении в названии — иначе один
    "плохой" импорт может массово переписать справочник. Если контрагент найден по
    имени, а в файле указан ИНН, которого в карточке ещё нет — ИНН подтягивается
    (обогащение справочника), но существующий ИНН никогда не перезаписывается."""
    if inn:
        by_inn = db.query(Counterparty).filter(Counterparty.inn == inn).first()
        if by_inn:
            return by_inn
    if not name:
        return None
    counterparty = db.query(Counterparty).filter(Counterparty.name == name).first()
    if not counterparty:
        counterparty = Counterparty(name=name, inn=inn)
        db.add(counterparty)
        db.flush()
    elif inn and not counterparty.inn:
        counterparty.inn = inn
    return counterparty


# Порядок и заголовки колонок шаблона массового импорта — заголовки должны совпадать
# (без учёта регистра) с ключами _CF_BEST_COLUMN_MAP, чтобы файл, скачанный отсюда
# и затем заполненный пользователем, корректно распознавался _parse_cf_best_rows.
# НДС факт и Просрочка дней не включены — оба поля опциональны/вычисляются автоматически.
_TEMPLATE_COLUMNS = [
    ('Дата', 16),
    ('Статус', 20),
    ('Поступления', 14),
    ('Списания', 14),
    ('Банк', 14),
    ('Период', 12),
    ('НДС', 8),
    ('Статья', 22),
    ('Контрагент', 28),
    ('ИНН', 14),
    ('№ ДС', 14),
    ('Счет', 14),
    ('Счет от дата', 16),
    ('Ссылка на документ', 28),
    ('Назначение', 30),
]


@router.get("/import/template")
async def download_import_template(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operations", "create"))
):
    """Генерирует XLSX-шаблон для массового импорта операций. Лист с данными
    называется ровно "CF BEST" (регистрозависимо) — это требование парсера
    (_parse_cf_best_rows читает pd.read_excel с sheet_name="CF BEST"). Пояснения
    и пример заполнения вынесены на отдельный лист "Инструкция", чтобы они не
    могли быть случайно прочитаны как настоящая строка операции.

    Статус/Банк/НДС/Статья — выпадающие списки с жёстким запретом свободного
    ввода (showErrorMessage + errorStyle="stop"): если вписать значение не из
    списка, Excel покажет ошибку и не даст покинуть ячейку. Список статей не
    хардкодится, а читается из текущего справочника статей (Article) и кладётся
    на скрытый лист "Справочники" — он не влезает в инлайн-список формулы
    (ограничение Excel ~255 символов), и так список всегда актуален без правки
    кода при добавлении новых статей через Настройки → Справочники → Статьи."""
    wb = Workbook()
    ws = wb.active
    ws.title = "CF BEST"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for col_idx, (title, width) in enumerate(_TEMPLATE_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        ws.column_dimensions[cell.column_letter].width = width

    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "A2"

    last_row = 500
    status_col = next(i for i, (t, _) in enumerate(_TEMPLATE_COLUMNS, start=1) if t == 'Статус')
    bank_col = next(i for i, (t, _) in enumerate(_TEMPLATE_COLUMNS, start=1) if t == 'Банк')
    vat_col = next(i for i, (t, _) in enumerate(_TEMPLATE_COLUMNS, start=1) if t == 'НДС')
    article_col = next(i for i, (t, _) in enumerate(_TEMPLATE_COLUMNS, start=1) if t == 'Статья')
    status_letter = ws.cell(row=1, column=status_col).column_letter
    bank_letter = ws.cell(row=1, column=bank_col).column_letter
    vat_letter = ws.cell(row=1, column=vat_col).column_letter
    article_letter = ws.cell(row=1, column=article_col).column_letter

    def _strict_list_dv(formula1):
        return DataValidation(
            type="list", formula1=formula1, allow_blank=True,
            showErrorMessage=True, errorStyle="stop",
            errorTitle="Недопустимое значение",
            error="Выберите значение строго из выпадающего списка — свободный ввод не поддерживается.",
        )

    # НДС — список ставок должен совпадать с VAT_OPTIONS на фронте (frontend/pages/finance/operations.js).
    vat_options = [0, 5, 7, 10, 20, 22]
    status_dv = _strict_list_dv('"ОПЛАЧЕНО,ПЛАН ОПЛАТ,ПЛАН ПОСТУПЛЕНИЙ"')
    bank_dv = _strict_list_dv('"АльфаБанк,ОПТ Банк,Совкомбанк,Наличные"')
    vat_dv = _strict_list_dv('"' + ','.join(str(v) for v in vat_options) + '"')
    ws.add_data_validation(status_dv)
    ws.add_data_validation(bank_dv)
    ws.add_data_validation(vat_dv)
    status_dv.add(f"{status_letter}2:{status_letter}{last_row}")
    bank_dv.add(f"{bank_letter}2:{bank_letter}{last_row}")
    vat_dv.add(f"{vat_letter}2:{vat_letter}{last_row}")

    # Статья — список слишком длинный для инлайн-формулы, поэтому через скрытый
    # лист-справочник, на который ссылается список (см. docstring выше).
    article_names = [a.name for a in db.query(Article).order_by(Article.sort_order, Article.id).all()]
    if article_names:
        lists_ws = wb.create_sheet("Справочники")
        for i, name in enumerate(article_names, start=1):
            lists_ws.cell(row=i, column=1, value=xlsx_safe(name))
        lists_ws.sheet_state = "hidden"
        article_dv = _strict_list_dv(f"'Справочники'!$A$1:$A${len(article_names)}")
        ws.add_data_validation(article_dv)
        article_dv.add(f"{article_letter}2:{article_letter}{last_row}")

    date_cols = [i for i, (t, _) in enumerate(_TEMPLATE_COLUMNS, start=1) if t in ('Дата', 'Счет от дата')]
    for row in range(2, last_row + 1):
        for col in date_cols:
            ws.cell(row=row, column=col).number_format = 'DD.MM.YYYY'

    instr = wb.create_sheet("Инструкция")
    instr.column_dimensions['A'].width = 22
    instr.column_dimensions['B'].width = 90
    instr_font_title = Font(bold=True, size=13)
    instr.cell(row=1, column=1, value="Инструкция по заполнению шаблона").font = instr_font_title

    rows = [
        ("Лист CF BEST", "Заполняйте операции на этом листе, начиная со 2-й строки. Не переименовывайте лист и не меняйте заголовки — иначе файл не распознается при импорте."),
        ("Дата", "Дата операции, формат ДД.МM.ГГГГ."),
        ("Статус", "Один из: ОПЛАЧЕНО / ПЛАН ОПЛАТ / ПЛАН ПОСТУПЛЕНИЙ (выбирается из выпадающего списка)."),
        ("Поступления / Списания", "Сумма по операции. Заполняется только одно из полей в зависимости от типа операции."),
        ("Банк", "Один из: АльфаБанк / ОПТ Банк / Совкомбанк / Наличные (выпадающий список)."),
        ("Период", "Период, к которому относится операция, например: Январь 2026 или 1 квартал 2026."),
        ("НДС", "Ставка НДС в процентах — строго из выпадающего списка: 0 / 5 / 7 / 10 / 20 / 22. Свободный ввод заблокирован. Сумма НДС вычисляется автоматически — отдельную колонку заполнять не нужно."),
        ("Статья", "Название статьи ДДС — строго из выпадающего списка текущего справочника статей. Свободный ввод заблокирован. Если нужной статьи нет в списке — добавьте её в Настройки → Справочники → Статьи и заново скачайте шаблон."),
        ("Контрагент", "Название контрагента. Если контрагент не найден — будет создана новая карточка в справочнике контрагентов."),
        ("ИНН", "ИНН контрагента — необязательно, но настоятельно рекомендуется: по ИНН контрагенты сопоставляются надёжнее, чем по названию (которое может отличаться кавычками/регистром/формой ООО). Если контрагент уже есть в справочнике под другим написанием названия, но с тем же ИНН — система не создаст дубликат, а сопоставит с существующей карточкой."),
        ("№ ДС", "Номер документа списания/счёта на оплату (если есть) — используется для сопоставления при повторной синхронизации."),
        ("Счет", "Номер счёта."),
        ("Счет от дата", "Дата счёта, формат ДД.ММ.ГГГГ."),
        ("Ссылка на документ", "Ссылка (URL) на скан/копию документа — необязательно."),
        ("Назначение", "Назначение платежа / комментарий."),
        ("Повторный импорт (синхронизация)", "Тот же файл можно загрузить повторно через раздел Импорт → Синхронизация: система найдёт совпадающие операции по № ДС + Счёт (либо по набору полей, если эти номера не указаны) и покажет, что изменилось, перед применением."),
    ]
    for i, (label, hint) in enumerate(rows, start=3):
        instr.cell(row=i, column=1, value=label).font = Font(bold=True)
        instr.cell(row=i, column=1).alignment = Alignment(vertical="top")
        c = instr.cell(row=i, column=2, value=hint)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        instr.row_dimensions[i].height = 32

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    headers = {"Content-Disposition": "attachment; filename=shablon_operaciy.xlsx"}
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


def _values_equal(a, b) -> bool:
    """Сравнение значений для диффа.

    float сравниваются с округлением до 2 знаков, чтобы погрешности округления
    в Excel не создавали ложных конфликтов.

    Пустота имеет два написания: None и пустая строка. Форма операции шлёт
    description: f.description || '' (пустую строку), импорт кладёт None — и
    сравнение «как есть» помечало конфликтом КАЖДУЮ строку с незаполненным
    назначением, хотя менять там нечего. Очистка непустого значения при этом
    остаётся изменением: пусто сходится только с пустым."""
    if isinstance(a, float) or isinstance(b, float):
        try:
            return round(float(a or 0), 2) == round(float(b or 0), 2)
        except (TypeError, ValueError):
            return a == b
    if a in (None, '') and b in (None, ''):
        return True
    return a == b




def _serialize_for_json(row: dict) -> dict:
    out = dict(row)
    for f in ('date', 'invoice_date'):
        if isinstance(out.get(f), date):
            out[f] = out[f].isoformat()
    return out


MAX_IMPORT_FILE_SIZE = 10 * 1024 * 1024  # 10 МБ


def _validate_import_file(file: UploadFile, contents: bytes):
    filename = (file.filename or '').lower()
    if not filename.endswith('.xlsx'):
        raise HTTPException(status_code=400, detail="Ожидается файл .xlsx")
    if len(contents) > MAX_IMPORT_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Файл слишком большой (максимум 10 МБ)")


@router.post("/import")
async def import_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    # ПИШЕТ ДЕНЬГИ, поэтому спрашивает право на правку операций, а не `import:view`
    # (решение владельца 11.09.2026: «права оставь тем, у кого есть доступ к
    # редактированию»). Секция `import` объявлена с единственным действием `view`, и
    # до этой правки на нём висели все три ручки импорта — то есть роль с правом
    # ТОЛЬКО СМОТРЕТЬ операции меняла файлом суммы и статусы уже проведённых.
    # Второго права «можно писать деньги» заводить не стали: оно уже есть, и вторая
    # его копия неизбежно разошлась бы с первой.
    current_user: User = Depends(require_permission("operations", "edit"))
):
    contents = await file.read()
    _validate_import_file(file, contents)
    rows = _parse_cf_best_rows(contents)

    imported = 0
    problems = []
    for n, row in enumerate(rows, start=1):
        article = _get_or_create_article(db, row['article'])
        counterparty = _get_or_create_counterparty(db, row['counterparty'], row.get('inn'))

        op = Operation(
            date=row['date'],
            status=row['status'],
            income=row['income'],
            expense=row['expense'],
            bank=row['bank'],
            period=row['period'],
            vat_rate=row['vat_rate'],
            vat_fact=row['vat_fact'],
            article_id=article.id if article else None,
            counterparty_id=counterparty.id if counterparty else None,
            ds_num=row['ds_num'],
            invoice=row['invoice'],
            invoice_date=row['invoice_date'],
            description=row['description'],
            document_link=_validate_link(row.get('document_link'), raise_on_bad=False),
            created_by=current_user.id
        )
        problem = _operation_problem(op)
        if problem:
            problems.append(f"строка {n}: {problem}")
            continue
        db.add(op)
        imported += 1

    _assert_import_rows_valid(db, problems)
    db.commit()
    return {"message": f"Импортировано {imported} операций"}


# Поля, которые сравниваются между файлом и существующей операцией для определения конфликта.
# 'period' исключён намеренно — это легитимно изменяемое поле (например, перенос платежа),
# включение его в ключ или в сравнение как блокирующего привело бы к ложным конфликтам.
# Здесь оно как раз участвует в сравнении (чтобы показать пользователю изменение), но НЕ в ключе.
_SYNC_COMPARE_FIELDS = ['date', 'status', 'income', 'expense', 'bank', 'period',
                        'vat_rate', 'vat_fact', 'article', 'counterparty',
                        'invoice_date', 'description', 'document_link']

# document_link сравнивается мягко: пустое значение в файле НЕ считается изменением
# (старый формат CF BEST без этой колонки иначе помечал бы конфликтом каждую строку
# с уже заполненной вручную ссылкой). Конфликт показывается только если в файле
# реально указана ссылка, отличающаяся от той, что сохранена в БД.
def _field_equal(field: str, existing_val, incoming_val) -> bool:
    if field == 'document_link' and not incoming_val:
        return True
    return _values_equal(existing_val, incoming_val)


def _is_blank(col):
    """«Пусто» в SQL — это и NULL, и ПУСТАЯ СТРОКА.

    Пустота записана в базе двумя способами: форма операции шлёт
    ds_num: f.ds_num || '' (пустую строку), импорт кладёт None. Проверка только
    на NULL выбрасывала из пула сопоставления всё, что заведено руками и имеет
    номер счёта, но не имеет № ДС, — 222 операции на стенде и 246 на проде.

    Для таких строк не работал ни составной ключ (в файле № ДС пуст, значит путь
    не тот), ни естественный (записи попросту нет в пуле). Повторная загрузка
    того же файла показывала их «новыми» — и создавала дубли.
    """
    return or_(col.is_(None), col == '')


def _take_from_pool(pool, invoice, op_id=None):
    """Из пула одинаковых по естественному ключу берём наиболее вероятного.

    Естественный ключ намеренно не включает номер счёта: он рассчитан на
    операции, где счёта нет вовсе (зарплата, налоги, банк). Но в пул попадают и
    строки, у которых пуст только № ДС, а счёт есть. У повторяющихся платежей
    одного контрагента на одну сумму (ежемесячный счёт) ключ совпадает сразу у
    нескольких записей, и без уточнения бралась просто самая старая — правка
    уезжала не в ту операцию, а расхождение показывалось конфликтом периода и
    ссылки, будто данные поменялись.

    Вторая подсказка — ID из выгрузки, нестрогая. Она смотрится только после
    счёта и только внутри пула, то есть среди записей, УЖЕ совпавших по дате,
    статусу, банку, суммам, статье и контрагенту. Поэтому даже случайное
    совпадение номера между стендами способно выбрать лишь одну из операций,
    неотличимых по всем содержательным полям. Сам по себе ID не сопоставляет
    ничего и несовпадение ID не отменяет совпадения.

    РАЗНЫЕ номера счетов — это разные операции, а не одна изменившаяся. Если в
    строке счёт есть, а в пуле лежат записи с ДРУГИМИ номерами, совпадения нет
    вовсе: строка новая. Без этого правила счёт 1778 за июль «совпадал» со
    счётом 1345 за июнь, и подтверждение такого конфликта переписало бы июньскую
    операцию июльскими данными — то есть стёрло бы запись, а не завело новую.

    Кандидатами при непустом счёте остаются только записи БЕЗ счёта: это случай
    «файл дописывает номер операции, у которой его ещё не было», и он должен
    остаться рабочим.

    Если счёта в строке нет, поведение прежнее: подсказка по ID, иначе самая
    ранняя запись."""
    if not pool:
        return None
    want = (invoice or '').strip()
    if want:
        for i, op in enumerate(pool):
            if (op.invoice or '').strip() == want:
                del pool[i]
                return op
        candidates = [i for i, op in enumerate(pool) if not (op.invoice or '').strip()]
        if not candidates:
            return None
    else:
        candidates = list(range(len(pool)))

    if op_id:
        for i in candidates:
            if pool[i].id == op_id:
                op = pool[i]
                del pool[i]
                return op
    i = candidates[0]
    op = pool[i]
    del pool[i]
    return op


@router.post("/import/preview")
async def import_preview(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    # Остаётся на `import:view` НАМЕРЕННО: разбор ничего не пишет, а посмотреть, что
    # файл сделает с журналом, полезно и тому, кто применять его не вправе.
    current_user: User = Depends(require_permission("import", "view"))
):
    """Шаг 1 синхронизации: парсит файл и сопоставляет строки с уже существующими
    операциями по составному ключу (№ ДС + № Счёта). Ничего не пишет в БД —
    результат кэшируется в памяти под import_id для последующего /import/apply."""
    contents = await file.read()
    _validate_import_file(file, contents)
    rows = _parse_cf_best_rows(contents)

    keyed_rows = [r for r in rows if r['ds_num'] and r['invoice']]
    ds_nums = list({r['ds_num'] for r in keyed_rows})
    invoices = list({r['invoice'] for r in keyed_rows})

    existing_map = {}
    if ds_nums and invoices:
        # order_by(id) — в данных встречаются операции с одинаковым (ds_num, invoice)
        # (дубликаты от прошлых "слепых" импортов без дедупликации). При совпадении
        # ключа детерминированно берём запись с наибольшим id (последнюю созданную).
        candidates = db.query(Operation).filter(
            Operation.ds_num.in_(ds_nums),
            Operation.invoice.in_(invoices)
        ).order_by(Operation.id).all()
        for op in candidates:
            existing_map[(op.ds_num, op.invoice)] = op

    # Большинство операций (зарплата, банк, налоги и т.п.) не имеют № ДС / Счёта —
    # для них составного ключа нет, и раньше они ВСЕГДА считались "новыми" при каждой
    # синхронизации, даже если уже были загружены. Чтобы это исправить, такие строки
    # дополнительно сопоставляются по "естественному" ключу: дата + статус + банк +
    # сумма + статья + контрагент — набору полей, который и так не входит в сравнение
    # изменений (см. _SYNC_COMPARE_FIELDS), то есть совпадение по нему не "угадывание",
    # а просто более полное описание той же самой операции. Сопоставление мультисетовое
    # (deque на каждый ключ), чтобы N одинаковых старых строк не съели один и тот же
    # существующий id — каждая использованная запись из пула берётся только один раз.
    articles_by_id = {a.id: a.name for a in db.query(Article).all()}
    counterparties_by_id = {c.id: c.name for c in db.query(Counterparty).all()}

    unkeyed_existing = db.query(Operation).filter(
        or_(_is_blank(Operation.ds_num), _is_blank(Operation.invoice))
    ).order_by(Operation.id).all()

    def _natural_key(d, status, bank, income, expense, article, counterparty):
        return (d, status, bank, round(income or 0, 2), round(expense or 0, 2), article, counterparty)

    natural_pool = {}
    for op in unkeyed_existing:
        nk = _natural_key(op.date, op.status, op.bank, op.income, op.expense,
                           articles_by_id.get(op.article_id), counterparties_by_id.get(op.counterparty_id))
        natural_pool.setdefault(nk, deque()).append(op)

    new_rows = []
    conflicts = []
    unchanged_count = 0
    cache_rows = []

    for r in rows:
        has_key = bool(r['ds_num'] and r['invoice'])
        existing = None

        if has_key:
            key = f"{r['ds_num']}||{r['invoice']}"
            existing = existing_map.get((r['ds_num'], r['invoice']))
        else:
            nk = _natural_key(r['date'], r['status'], r['bank'], r['income'], r['expense'],
                               r['article'], r['counterparty'])
            existing = _take_from_pool(natural_pool.get(nk), r.get('invoice'), r.get('op_id'))
            key = f"nk:{existing.id}" if existing else None

        if not existing:
            new_rows.append(_serialize_for_json(r))
            cache_rows.append({'status': 'new', 'key': key, 'data': r, 'existing_id': None})
            continue

        existing_view = {
            'date': existing.date,
            'status': existing.status,
            'income': existing.income,
            'expense': existing.expense,
            'bank': existing.bank,
            # Период приводится тем же правилом, что и у входящих строк (_normalize_period).
            # В БД остались операции с ненормализованным периодом в квартальном формате
            # ("Q1 2024") — это записи, попавшие туда уже ПОСЛЕ разового скрипта
            # fix_periods.py (например, через старый "слепой" /import без нормализации),
            # а не осознанный формат для план-строк. Без повторной нормализации здесь
            # такие записи всегда конфликтовали бы с файлом из-за разницы в формате,
            # хотя реального изменения периода нет.
            'period': _normalize_period(existing.period, existing.date),
            'vat_rate': existing.vat_rate,
            'vat_fact': existing.vat_fact,
            'article': existing.article.name if existing.article else None,
            'counterparty': existing.counterparty.name if existing.counterparty else None,
            'invoice_date': existing.invoice_date,
            'description': existing.description,
            'document_link': existing.document_link,
        }
        diff_fields = [f for f in _SYNC_COMPARE_FIELDS if not _field_equal(f, existing_view.get(f), r.get(f))]

        if not diff_fields:
            unchanged_count += 1
            cache_rows.append({'status': 'unchanged', 'key': key, 'data': r, 'existing_id': existing.id})
            continue

        conflicts.append({
            'key': key,
            'existing': _serialize_for_json(existing_view),
            'incoming': _serialize_for_json(r),
            'diff_fields': diff_fields,
        })
        cache_rows.append({'status': 'conflict', 'key': key, 'data': r, 'existing_id': existing.id})

    import_id = uuid.uuid4().hex
    _prune_import_cache()
    IMPORT_SYNC_CACHE[import_id] = {
        'rows': cache_rows,
        'created_at': datetime.utcnow(),
        'user_id': current_user.id,
    }

    return {
        'import_id': import_id,
        'summary': {
            'new': len(new_rows),
            'conflict': len(conflicts),
            'unchanged': unchanged_count,
        },
        'new_rows': new_rows,
        'conflicts': conflicts,
    }


class ImportApplyRequest(BaseModel):
    import_id: str
    confirmed_keys: List[str] = []


@router.post("/import/apply")
async def import_apply(
    payload: ImportApplyRequest,
    db: Session = Depends(get_db),
    # Пишет и ПЕРЕЗАПИСЫВАЕТ операции — то же право, что у одиночной правки.
    # Подробности решения — в комментарии у `/import` выше.
    current_user: User = Depends(require_permission("operations", "edit"))
):
    """Шаг 2 синхронизации («Перепровести»): новые строки добавляются всегда,
    конфликтные строки обновляются только если их key есть в confirmed_keys —
    остальное (неподтверждённые конфликты, unchanged) пропускается."""
    _prune_import_cache()
    cached = IMPORT_SYNC_CACHE.get(payload.import_id)
    if not cached:
        raise HTTPException(status_code=400, detail="Сессия импорта истекла или не найдена — загрузите файл повторно")
    # Применяет ТОТ ЖЕ человек, который разбирал файл. Админа не исключаем — он проходит
    # везде, — но чужую сессию не применяет и он: превью показывали не ему, и что именно
    # он подтверждает, он не видел.
    if cached.get('user_id') != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Эту загрузку разбирал другой пользователь. Применить её может только "
                   "он: подтверждение относится к тому, что он видел на экране.")

    confirmed = set(payload.confirmed_keys)
    inserted = updated = skipped = 0
    new_articles = []          # какие статьи файл завёл — покажем человеку

    problems = []
    for n, row in enumerate(cached['rows'], start=1):
        data = row['data']

        if row['status'] == 'new':
            article = _get_or_create_article(db, data['article'], new_articles)
            counterparty = _get_or_create_counterparty(db, data['counterparty'], data.get('inn'))
            op = Operation(
                date=data['date'],
                status=data['status'],
                income=data['income'],
                expense=data['expense'],
                bank=data['bank'],
                period=data['period'],
                vat_rate=data['vat_rate'],
                vat_fact=data['vat_fact'],
                article_id=article.id if article else None,
                counterparty_id=counterparty.id if counterparty else None,
                ds_num=data['ds_num'],
                invoice=data['invoice'],
                invoice_date=data['invoice_date'],
                description=data['description'],
                document_link=_validate_link(data.get('document_link'), raise_on_bad=False),
                own_company_id=own_company.sole_id(db),
                created_by=current_user.id,
            )
            problem = _operation_problem(op)
            if problem:
                problems.append(f"строка {n}: {problem}")
                continue
            db.add(op)
            inserted += 1

        elif row['status'] == 'conflict' and row['key'] in confirmed:
            existing = db.query(Operation).filter(Operation.id == row['existing_id']).first()
            if not existing:
                skipped += 1
                continue
            article = _get_or_create_article(db, data['article'], new_articles)
            counterparty = _get_or_create_counterparty(db, data['counterparty'], data.get('inn'))
            existing.date = data['date']
            existing.status = data['status']
            existing.income = data['income']
            existing.expense = data['expense']
            existing.bank = data['bank']
            existing.period = data['period']
            existing.vat_rate = data['vat_rate']
            existing.vat_fact = data['vat_fact']
            existing.article_id = article.id if article else None
            existing.counterparty_id = counterparty.id if counterparty else None
            existing.invoice_date = data['invoice_date']
            existing.description = data['description']
            # document_link не затирается пустым значением: старый формат файла
            # (без колонки "Ссылка на документ") иначе бы каждый раз стирал ссылку,
            # вручную добавленную в приложении.
            if data.get('document_link'):
                existing.document_link = _validate_link(data['document_link'], raise_on_bad=False)
            # Правку существующей строки проверяем ТОЖЕ: файл может увести годную
            # операцию в негодное состояние — стереть статью, подменить статус.
            problem = _operation_problem(existing)
            if problem:
                problems.append(f"строка {n} (правка операции #{existing.id}): {problem}")
                continue
            updated += 1

        else:
            skipped += 1

    _assert_import_rows_valid(db, problems)
    db.commit()
    # `pop`, а не `del`: при двух одновременных применениях одного import_id второй
    # получал KeyError вместо понятного отказа.
    IMPORT_SYNC_CACHE.pop(payload.import_id, None)

    # ЖУРНАЛ ДЕЙСТВИЙ. Массовая запись денег — единственный путь в системе, который его
    # не оставлял: одиночная правка, массовая и удаление пишут, импорт молчал. Вопрос
    # «кто перезаписал эти сорок операций» не имел ответа вовсе (F2-24 аудита 11.09.2026).
    log_action(db, current_user, "import_apply", entity_type="operation", entity_id=None,
               details=(f"импорт {payload.import_id}: добавлено {inserted}, "
                        f"обновлено {updated}, пропущено {skipped}"
                        + (f"; заведено статей: {', '.join(sorted(set(new_articles)))}"
                           if new_articles else "")))

    return {
        "message": f"Добавлено {inserted}, обновлено {updated}, пропущено {skipped}",
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        # Новые статьи заводятся БЕЗ разметки, и их деньги уходят в «Требует разметки».
        # Молчать нельзя: иначе это выясняется при следующем разборе P&L.
        "new_articles": sorted(set(new_articles)),
    }


# ===================== Экспорт платёжных поручений в Альфа-Банк =====================

class AlfaExportRequest(BaseModel):
    ids: List[int]       # id операций для выгрузки
    bank: str            # наш банк-плательщик (напр. "АльфаБанк")

@router.post("/export/alfa")
def export_to_alfa(
    payload: AlfaExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operations", "view"))
):
    """Генерирует файл платёжных поручений в формате 1CClientBankExchange
    для загрузки в Альфа-Банк (меню Импорт → Рублёвые платежи).

    Перед выгрузкой проверяет:
    - операции являются расходными (expense > 0)
    - у контрагента заполнены банковские реквизиты (хотя бы БИК и расчётный счёт)
    - у нашего банка-плательщика заполнены реквизиты в Настройках

    Возвращает .txt файл; счётчик номера платёжного поручения инкрементируется в company_settings."""
    from sqlalchemy import text as _text

    if not payload.ids:
        raise HTTPException(status_code=400, detail="Не указаны операции")
    if payload.bank not in ['АльфаБанк', 'ОПТ Банк', 'Совкомбанк', 'Наличные']:
        raise HTTPException(status_code=400, detail="Неизвестный банк")

    # Реквизиты нашей компании для выбранного банка.
    # Если bank_balances привязан к own_company — имя/ИНН/КПП берём из реестра контрагентов
    # (более актуально, т.к. это единый источник данных юрлица); RS/БИК/КС всегда из bank_balances.
    company_row = db.execute(_text("""
        SELECT bb.company_name, bb.inn, bb.kpp, bb.rs, bb.bik, bb.bank_full_name, bb.bank_city, bb.ks,
               cp.name  AS own_name,
               cp.inn   AS own_inn,
               cp.kpp   AS own_kpp
        FROM bank_balances bb
        LEFT JOIN counterparties cp ON cp.id = bb.own_company_id AND cp.is_own_company = TRUE
        WHERE bb.bank = :bank
    """), {"bank": payload.bank}).fetchone()

    if not company_row or not company_row.rs or not company_row.bik:
        raise HTTPException(
            status_code=400,
            detail=f"Реквизиты компании для банка «{payload.bank}» не заполнены. "
                   f"Заполните их в Настройках → Остатки по банкам."
        )
    # Подставляем данные из реестра контрагентов, если юрлицо привязано (приоритет выше bank_balances)
    _payer_name = company_row.own_name or company_row.company_name or ''
    _payer_inn  = company_row.own_inn  or company_row.inn  or ''
    _payer_kpp  = company_row.own_kpp  or company_row.kpp  or '0'
    if not _payer_inn:
        raise HTTPException(
            status_code=400,
            detail=f"ИНН компании для банка «{payload.bank}» не заполнен. "
                   f"Заполните реквизиты в Настройках → Остатки по банкам."
        )

    # Следующий номер платёжного поручения
    num_row = db.execute(_text(
        "SELECT value FROM company_settings WHERE key = 'payment_number_last'"
    )).fetchone()
    next_num = int(num_row.value if num_row else 0) + 1

    # Загружаем операции с контрагентами и их банковскими счетами
    operations = (
        db.query(Operation)
        .filter(Operation.id.in_(payload.ids))
        .all()
    )

    if not operations:
        raise HTTPException(status_code=404, detail="Операции не найдены")

    errors = []
    blocks = []

    for op in operations:
        if not op.expense or op.expense <= 0:
            errors.append(f"Операция #{op.id}: не является расходной (expense = {op.expense})")
            continue

        cp = op.counterparty
        if not cp:
            errors.append(f"Операция #{op.id}: контрагент не указан")
            continue

        # Берём первый банковский счёт контрагента с заполненным БИК и РС
        ba = None
        for b in (cp.bank_accounts or []):
            if b.bik and b.rs:
                ba = b
                break

        if not ba:
            errors.append(
                f"Операция #{op.id} ({cp.name}): не заполнены банковские реквизиты контрагента"
            )
            continue

        today_str = op.date.strftime('%d.%m.%Y') if op.date else date.today().strftime('%d.%m.%Y')
        purpose = (op.description or "Оплата по договору. НДС не облагается.")[:210]

        block = "\n".join([
            "СекцияДокумент=Платежное поручение",
            f"Номер={next_num}",
            f"Дата={today_str}",
            f"Сумма={op.expense:.2f}",
            f"ПлательщикСчет={company_row.rs}",
            f"Плательщик=ИНН {_payer_inn} {_payer_name}",
            f"ПлательщикИНН={_payer_inn}",
            f"ПлательщикКПП={_payer_kpp}",
            f"Плательщик1={_payer_name}",
            f"ПлательщикБанк1={company_row.bank_full_name or ''}",
            f"ПлательщикБанк2={company_row.bank_city or ''}",
            f"ПлательщикБИК={company_row.bik}",
            f"ПлательщикКорсчет={company_row.ks or ''}",
            f"ПолучательСчет={ba.rs}",
            f"Получатель={cp.name}",
            f"ПолучательИНН={cp.inn or '0'}",
            f"ПолучательКПП={cp.kpp or '0'}",
            f"Получатель1={cp.name}",
            f"ПолучательБанк1={ba.bank_name or ''}",
            f"ПолучательБанк2={ba.bank_city or ''}",
            f"ПолучательБИК={ba.bik}",
            f"ПолучательКорсчет={ba.ks or ''}",
            "ВидПлатежа=",
            "Очередность=5",
            "Код=0",
            f"НазначениеПлатежа={purpose}",
            "КонецДокумента",
        ])

        blocks.append(block)
        next_num += 1

    if errors and not blocks:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    # Обновляем счётчик
    actual_next = next_num - 1  # последний использованный
    db.execute(_text(
        "INSERT INTO company_settings (key, value) VALUES ('payment_number_last', :v) "
        "ON CONFLICT (key) DO UPDATE SET value = :v"
    ), {"v": str(actual_next)})
    db.commit()

    content = "1CClientBankExchange\n\n" + "\n\n".join(blocks) + "\n\nКонецФайла"
    if errors:
        # Добавляем предупреждения о пропущенных операциях в начало как комментарий
        warn_block = "// ПРОПУЩЕНО:\n" + "\n".join(f"// {e}" for e in errors) + "\n\n"
        content = "1CClientBankExchange\n\n" + warn_block + "\n\n".join(blocks) + "\n\nКонецФайла"

    from datetime import date as _d
    filename = f"alfa_payments_{_d.today().isoformat()}.txt"

    log_action(db, current_user, "export_alfa", entity_type="operation", entity_id=None,
               details=f"Выгружено {len(blocks)} п/п, пропущено {len(errors)}, банк={payload.bank}")

    return StreamingResponse(
        io.BytesIO(content.encode("cp1251")),  # Альфа-Банк ожидает Windows-1251
        media_type="text/plain; charset=windows-1251",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

# ---------------------------------------------------------------------------
# Приложенные файлы операции (сканы)
# ---------------------------------------------------------------------------
# Часть первички существует только на бумаге: в реестр Диадока такой документ не
# попадает, а `document_link` указывает наружу. Файлы лежат в /app/uploads/operations,
# в базе — относительный ключ от корня хранилища (соглашение от 2026-08-23), таблица
# заведена миграцией 2026-08-24_operation_files.sql.

UPLOADS_ROOT = "/app/uploads"
OP_FILES_SUBDIR = "operations"
OP_FILE_MAX_BYTES = 20 * 1024 * 1024
OP_FILE_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg",
                      ".png", ".tif", ".tiff", ".heic", ".zip"}


def _op_file_out(f):
    return {
        "id": f.id, "original_name": f.original_name, "size_bytes": f.size_bytes,
        "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None,
        "uploaded_by_name": f.uploaded_by_name,
    }


@router.get("/{op_id}/files")
def list_operation_files(
    op_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operations", "view")),
):
    from app.models import OperationFile
    rows = (db.query(OperationFile).filter(OperationFile.operation_id == op_id)
            .order_by(OperationFile.id).all())
    return [_op_file_out(f) for f in rows]


@router.post("/{op_id}/files")
async def upload_operation_file(
    op_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operations", "edit")),
):
    import os
    import re as _re
    import uuid
    from app.models import OperationFile

    op = db.query(Operation).filter(Operation.id == op_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Операция не найдена")

    original_name = file.filename or "документ"
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in OP_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Недопустимый тип файла. Разрешены: {', '.join(sorted(OP_FILE_EXTENSIONS))}")

    content = await file.read()
    if len(content) > OP_FILE_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Файл слишком большой (максимум {OP_FILE_MAX_BYTES // 1024 // 1024} МБ)")
    if not content:
        raise HTTPException(status_code=400, detail="Файл пустой")

    # Имя на диске несёт вид сущности и случайный суффикс. Вид — потому что каталог
    # общий и «7_akt.pdf» от разных подсистем затирали бы друг друга (готча реестра
    # площадок). Суффикс — потому что к одной операции кладут несколько сканов, и
    # одинаковые имена файлов у них обычное дело.
    safe = _re.sub(r'[^\w.\-]', '_', original_name)[-80:]
    stored = f"op{op_id}_{uuid.uuid4().hex[:8]}_{safe}"
    target_dir = os.path.join(UPLOADS_ROOT, OP_FILES_SUBDIR)
    os.makedirs(target_dir, exist_ok=True)
    with open(os.path.join(target_dir, stored), "wb") as fh:
        fh.write(content)

    row = OperationFile(
        operation_id=op_id,
        path=f"{OP_FILES_SUBDIR}/{stored}",
        original_name=original_name,
        size_bytes=len(content),
        uploaded_by=getattr(current_user, "id", None),
        uploaded_by_name=(getattr(current_user, "name", None)
                          or getattr(current_user, "email", None)),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    log_action(db, current_user, "upload_operation_file", entity_type="operation",
               entity_id=op_id, details=f"Приложен файл: {original_name}")
    return _op_file_out(row)


@router.get("/{op_id}/files/{file_id}")
def download_operation_file(
    op_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operations", "view")),
):
    from fastapi.responses import FileResponse
    from app.models import OperationFile

    row = (db.query(OperationFile)
           .filter(OperationFile.id == file_id, OperationFile.operation_id == op_id)
           .first())
    if not row:
        raise HTTPException(status_code=404, detail="Файл не найден")

    # Ключ из базы — относительный, и склеивать его с корнем можно только после
    # проверки: подделанный путь с '..' иначе уводит за пределы хранилища.
    # Та самая проверка, что была здесь с самого начала, — теперь общей функцией
    # (`app/files_safe`). Она же сузила границу до подпапки операций: файл договора
    # не должен отдаваться этой ручкой, даже если путь формально внутри хранилища.
    full = existing_upload_path(row.path, subdir=OP_FILES_SUBDIR)

    return FileResponse(full, filename=row.original_name,
                        media_type="application/octet-stream")


@router.delete("/{op_id}/files/{file_id}")
def delete_operation_file(
    op_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("operations", "edit")),
):
    from app.models import OperationFile

    row = (db.query(OperationFile)
           .filter(OperationFile.id == file_id, OperationFile.operation_id == op_id)
           .first())
    if not row:
        raise HTTPException(status_code=404, detail="Файл не найден")

    # Была местная копия проверки на `normpath` + `startswith`. Держала `..`, но не
    # держала символическую ссылку (её снимает только `realpath`) и, главное, была
    # ВТОРЫМ описанием одного правила — тем самым расхождением, ради которого заведён
    # `app/files_safe`. `subdir` сохраняет сужение до папки файлов операций.
    remove_upload(row.path, subdir=OP_FILES_SUBDIR)
    name = row.original_name
    db.delete(row)
    db.commit()

    log_action(db, current_user, "delete_operation_file", entity_type="operation",
               entity_id=op_id, details=f"Удалён файл: {name}")
    return {"ok": True}
