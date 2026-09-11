"""Вход для СЕРВИСА кабинета. Два действия, и больше здесь ничего не появится.

Кабинет не пишет в базу — он зовёт ядро. Разбор решения целиком в шапке миграции
`2026-08-28_publisher_cabinet_verdict.sql`; коротко: правила вердикта нетривиальны, и
вторая их реализация на стороне кабинета разошлась бы с первой.

**Это не пользовательский эндпоинт.** Права роли здесь не при чём: снаружи стоит не
человек, а наш же процесс во внешнем контуре. Пропуск — общий секрет из окружения, и он
свой, отдельный и от `SECRET_KEY` ядра, и от `CABINET_SECRET_KEY`: тот подписывает
сессии паблишеров, этот пускает процесс к процессу.

Чего секрет НЕ даёт: он не удостоверяет, кто именно нажал кнопку. Имя и почта автора
приходят в теле, и ядро кладёт их СНИМКОМ. Доверие здесь ровно то же, что у любого
сервисного вызова: скомпрометированный кабинет может записать вердикт от чужого имени —
но он и так стоит между площадкой и нами. Важно, что читать финансовые данные он при
этом не может: роль `cabinet` в базе прав на `public` не имеет.
"""
import hmac
import os
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.files_safe import existing_upload_path
from app.database import get_db
from app.launch_prep.models import LaunchPrepPair, LaunchPrepPairFile, LaunchPrepTarget
from app.routers.launch_prep import apply_platform_verdict, url_state
from app.cabinet import journal
from app.sales.models import SalesPublisher

router = APIRouter()

SERVICE_TOKEN = os.getenv("CABINET_SERVICE_TOKEN", "")


def require_cabinet_service(x_cabinet_token: Optional[str] = Header(default=None)):
    """Пропуск сервиса кабинета. Сравнение постоянным временем — секрет длинный, но
    побитовое сравнение всё равно рассказывает о нём по времени ответа.

    Пустой секрет в окружении закрывает вход НАСОВСЕМ, а не открывает всем: забытая
    переменная должна ломать функцию, а не защиту.
    """
    if not SERVICE_TOKEN or not x_cabinet_token or not hmac.compare_digest(
            x_cabinet_token, SERVICE_TOKEN):
        raise HTTPException(status_code=403, detail="Сервисный доступ закрыт")
    return True


def _actor(db: Session, account_id: int, publisher_id: int):
    """Кто действует и в чьей ленте это окажется.

    До 30.08.2026 шлюз не знал действующего вовсе: у вердикта проверялось только, что
    пара принадлежит НАЗВАННОЙ площадке, а имеет ли право вызывающий говорить за неё —
    оставалось на кабинете. Ровно то, что в шапке соседней ручки названо «отсутствием
    проверки». Журналу всё равно понадобилась учётка, и вместе с ней проверка стала
    возможной — поэтому поле обязательное, а не «по возможности».
    """
    from app.cabinet.models import CabinetAccount
    from app.cabinet.scope import account_sees_publisher

    acc = db.query(CabinetAccount).filter(CabinetAccount.id == account_id).first()
    if acc is None or not account_sees_publisher(db, acc, publisher_id):
        # 404 везде: 403 отвечал бы на вопрос «а есть ли такая связка».
        raise HTTPException(status_code=404, detail="Задание не найдено")
    return acc


def _creative_subject(db: Session, pair) -> Optional[str]:
    """«№4 · Мильгамма» — то, что видно в ленте рядом с действием.

    Бренд, а не название сделки: сделка — наша внутренняя единица, а лента у площадки
    на виду. Правило «в subject не попадает лишнее» начинается здесь.
    """
    from app.launch_prep.models import LaunchPrepCreativeSet
    from app.sales.models import SalesBrand, SalesDeal

    s = db.query(LaunchPrepCreativeSet).filter(
        LaunchPrepCreativeSet.id == pair.set_id).first()
    if s is None:
        return None
    brand = None
    deal = db.query(SalesDeal).filter(SalesDeal.id == s.deal_id).first()
    if deal is not None and deal.brand_id:
        brand = db.query(SalesBrand).filter(SalesBrand.id == deal.brand_id).first()
    return f"№{s.no}" + (f" · {brand.name}" if brand and brand.name else "")


class CabinetVerdictIn(BaseModel):
    publisher_id: int          # чью площадку представляет вызывающий
    account_id: int            # кто именно — им же подписана строка журнала
    verdict: str
    reason: Optional[str] = None
    author_name: str
    author_email: Optional[str] = None


@router.post("/pair/{pair_id}/verdict", dependencies=[Depends(require_cabinet_service)])
def cabinet_verdict(pair_id: int, payload: CabinetVerdictIn,
                    db: Session = Depends(get_db)):
    """Вердикт, поставленный САМОЙ площадкой в кабинете.

    Пара сверяется с заявленной площадкой ЗДЕСЬ, а не только в кабинете: проверка,
    оставленная на вызывающей стороне, — это отсутствие проверки.
    """
    pair = db.query(LaunchPrepPair).filter(LaunchPrepPair.id == pair_id).first()
    if not pair:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    target = db.query(LaunchPrepTarget).filter(
        LaunchPrepTarget.id == pair.target_id).first()
    if not target or target.publisher_id != payload.publisher_id:
        raise HTTPException(status_code=404, detail="Задание не найдено")

    acc = _actor(db, payload.account_id, payload.publisher_id)
    out = apply_platform_verdict(db, pair_id, payload.verdict, payload.reason,
                                 payload.author_name, payload.author_email,
                                 "кабинет", actor=None)
    journal.write(db, {'ок': 'креатив_ок', 'на доработку': 'креатив_доработка',
                       'отказ': 'креатив_отказ'}[payload.verdict],
                  cabinet_id=acc.cabinet_id, account_id=acc.id,
                  publisher_id=payload.publisher_id, actor_name=payload.author_name,
                  subject=_creative_subject(db, pair),
                  entity_type='launch_prep_pair', entity_id=pair_id)
    db.commit()
    return {"verdict": out["verdict"], "code": out["code"]}


class CabinetUrlIn(BaseModel):
    publisher_id: int
    account_id: int
    url: str
    author_name: str


@router.put("/target/{target_id}/url", dependencies=[Depends(require_cabinet_service)])
def cabinet_target_url(target_id: int, payload: CabinetUrlIn,
                       db: Session = Depends(get_db)):
    """Посадочная страница, присланная площадкой в ответ на наш запрос.

    Ссылка живёт на ПОЛУЧАТЕЛЕ (сделка × площадка), а не на креативе: страница одна на
    всю кампанию у этого сайта, и у второго креатива она та же.

    Схема проверяется, как у ссылки на документ договора: `javascript:` и `data:` в
    кликаемом поле — известный вектор, и то, что поле заполняет внешнее лицо, делает
    проверку не формальностью, а условием.
    """
    target = db.query(LaunchPrepTarget).filter(LaunchPrepTarget.id == target_id).first()
    if not target or target.publisher_id != payload.publisher_id:
        raise HTTPException(status_code=404, detail="Размещение не найдено")

    url = (payload.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Укажите ссылку")
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400,
                            detail="Ссылка должна начинаться с http:// или https://")
    if len(url) > 512:
        raise HTTPException(status_code=400, detail="Ссылка длиннее 512 знаков")

    acc = _actor(db, payload.account_id, payload.publisher_id)
    target.advertiser_url = url
    journal.write(db, 'посадочная', cabinet_id=acc.cabinet_id, account_id=acc.id,
                  publisher_id=payload.publisher_id, actor_name=payload.author_name,
                  entity_type='launch_prep_target', entity_id=target.id)
    db.commit()
    return {"target_id": target.id, "url_state": url_state(target)}


@router.get("/notify-kinds", dependencies=[Depends(require_cabinet_service)])
def cabinet_notify_kinds():
    """Каталог видов уведомлений — ОДИН на оба контура.

    Кабинет мог бы держать свой список меток, и это была бы третья копия словаря после
    `url_state` и списка типовых размеров баннера. Здесь копии не нужно: список
    статический, запрашивается редко, и один сетевой вызов дешевле расхождения, которое
    видно только площадке.
    """
    from app.cabinet.notify_kinds import KINDS
    return {"kinds": [{"key": k.key, "label": k.label, "hint": k.hint,
                       "can_mute": k.can_mute} for k in KINDS]}


class CabinetMuteIn(BaseModel):
    publisher_id: int              # чью площадку представляет вызывающий
    kind: str
    muted: bool
    author_name: Optional[str] = None


@router.put("/account/{account_id}/mute", dependencies=[Depends(require_cabinet_service)])
def cabinet_mute(account_id: int, payload: CabinetMuteIn, db: Session = Depends(get_db)):
    """Выключить или вернуть вид уведомления. Пишет ЯДРО, а не кабинет.

    Тот же порядок, что у вердикта и посадочной ссылки: у таблицы один писатель, и
    внешний процесс к нему обращается, а не пишет сам. Здесь это не формальность —
    `cabinet_account_mute` ссылается на учётку каскадом, и право на запись означало бы
    право удалить чужую строку подбором номера.

    Принадлежность площадки учётке проверяется ЗДЕСЬ, а не только в кабинете: проверка,
    оставленная на вызывающей стороне, — это отсутствие проверки.
    """
    from app.cabinet.models import CabinetAccount
    from app.cabinet.notify_kinds import KINDS, MUTABLE_KEYS
    from app.cabinet.scope import account_sees_publisher

    acc = db.query(CabinetAccount).filter(CabinetAccount.id == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Учётка не найдена")

    # Правило берётся из `scope`, а не пишется здесь: до 30.08.2026 запись проверялась по
    # личному списку `cabinet_account_publisher`, а чтение шло от кабинета — два ответа на
    # один вопрос, которые разошлись бы при первой же раздаче площадок.
    if not account_sees_publisher(db, acc, payload.publisher_id):
        # 404, а не 403: 403 подтвердил бы, что такая связка существует.
        raise HTTPException(status_code=404, detail="Учётка не найдена")

    known = {k.key for k in KINDS}
    if payload.kind not in known:
        raise HTTPException(status_code=400, detail="Неизвестный вид уведомления")
    if payload.muted and payload.kind not in MUTABLE_KEYS:
        raise HTTPException(
            status_code=400,
            detail="Это уведомление выключить нельзя: пропущенное здесь означает "
                   "сорванный запуск")

    from sqlalchemy import text as sa_text
    if payload.muted:
        db.execute(sa_text(
            "INSERT INTO cabinet_account_mute (account_id, kind, muted_by) "
            "VALUES (:a, :k, :w) ON CONFLICT (account_id, kind) DO NOTHING"),
            {"a": account_id, "k": payload.kind,
             "w": (payload.author_name or "").strip() or "кабинет"})
    else:
        db.execute(sa_text(
            "DELETE FROM cabinet_account_mute WHERE account_id = :a AND kind = :k"),
            {"a": account_id, "k": payload.kind})

    # Строка журнала едет ТОЙ ЖЕ транзакцией, что и сам выключатель (правило `journal`):
    # разошедшийся с фактом журнал хуже отсутствующего. `subject` — человеческое имя вида
    # из словаря, а не ключ: ленту читает и площадка тоже.
    label = next((k.label for k in KINDS if k.key == payload.kind), payload.kind)
    journal.write(db, 'уведомление_выкл' if payload.muted else 'уведомление_вкл',
                  cabinet_id=acc.cabinet_id, account_id=acc.id,
                  publisher_id=payload.publisher_id,
                  actor_name=(payload.author_name or "").strip() or acc.name or "кабинет",
                  subject=label, entity_type="cabinet_account_mute", entity_id=acc.id)
    db.commit()
    return {"kind": payload.kind, "muted": payload.muted}


# Медиакит — презентация площадки. Только PDF и PPTX (владелец 28.08.2026): это документ
# для чтения, а не архив и не картинка, и открытый список расширений во внешнем контуре
# означал бы приём чего угодно от того, кто нам не сотрудник.
MEDIA_KIT_EXT = {".pdf", ".pptx"}
MEDIA_KIT_MAX = 30 * 1024 * 1024
MEDIA_KIT_DIR = "mediakit"


@router.get("/task/{pair_id}/rights-letter",
            dependencies=[Depends(require_cabinet_service)])
def cabinet_rights_letter(pair_id: int, account_id: int, publisher_id: int,
                          db: Session = Depends(get_db)):
    """Письмо о правах — площадке, по её заданию.

    Отдаёт ЯДРО, а не кабинет: тома `uploads` у контейнера кабинета нет вовсе, он видит
    только `pub.*`. Через песочницу тоже нельзя — она раздаётся БЕЗ авторизации (иначе
    баннер не откроется в рамке), и документ о правах туда класть незачем.

    Право проверяется дважды и по-разному: `_actor` — что учётка вправе говорить за эту
    площадку, а запрос ниже — что задание действительно её. Первое без второго пустило бы
    к чужому креативу по подобранному номеру пары.
    """
    from app.launch_prep.models import LaunchPrepCreativeSet
    _actor(db, account_id, publisher_id)
    row = (db.query(LaunchPrepCreativeSet)
           .join(LaunchPrepPair, LaunchPrepPair.set_id == LaunchPrepCreativeSet.id)
           .join(LaunchPrepTarget, LaunchPrepTarget.id == LaunchPrepPair.target_id)
           .filter(LaunchPrepPair.id == pair_id,
                   LaunchPrepTarget.publisher_id == publisher_id).first())
    # 404 и на «нет задания», и на «нет письма»: разные коды отвечали бы на вопрос,
    # существует ли пара с таким номером.
    if row is None or not row.rights_letter_path:
        raise HTTPException(status_code=404, detail="Письмо не найдено")
    # Путь из базы — через общую проверку границы хранилища (`app/files_safe`).
    # До 11.09.2026 она была ровно в одном месте из десяти.
    full = existing_upload_path(row.rights_letter_path)
    return FileResponse(full, filename=row.rights_letter_name or "rights-letter",
                        media_type="application/octet-stream")


@router.post("/publisher/{publisher_id}/media-kit",
             dependencies=[Depends(require_cabinet_service)])
async def cabinet_media_kit(publisher_id: int, account_id: int,
                            file: UploadFile = File(...),
                            db: Session = Depends(get_db)):
    """Медиакит, присланный самой площадкой.

    Колонки под него в реестре были с самого начала, но ручки загрузки не существовало —
    поле стояло пустым у всех 41 площадки (замер 28.08.2026). Теперь его заполняет тот,
    кому оно принадлежит.

    Файл пишет ЯДРО, а не кабинет: том с загрузками смонтирован сюда, и давать внешнему
    процессу право писать в общее хранилище значило бы отдать ему то, ради чего он и
    вынесен отдельно.

    Новый файл ЗАМЕЩАЕТ старый — версий у медиакита нет: у площадки он один, и «версия
    от 03.07» это дата загрузки, а не отдельная запись.
    """
    # ИСПРАВЛЕНО 30.08.2026: раньше принадлежность здесь не проверялась вовсе — «её не
    # из чего вывести, номер площадки и есть весь запрос». Теперь запрос несёт ещё и
    # учётку, и проверка стала возможной. Прежний текст оставлен ниже как история того,
    # почему дыра выглядела неизбежной. У вердикта иначе: там пара сама указывает на
    # площадку, и ядро сверяет независимо. Разница честная, и делать вид, что проверка
    # есть, добавив в тело то же число, было бы хуже её отсутствия.
    p = db.query(SalesPublisher).filter(SalesPublisher.id == publisher_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Площадка не найдена")
    acc = _actor(db, account_id, publisher_id)

    original = file.filename or "mediakit"
    ext = os.path.splitext(original)[1].lower()
    if ext not in MEDIA_KIT_EXT:
        raise HTTPException(status_code=415,
                            detail="Медиакит принимается в PDF или PPTX")
    content = await file.read()
    if len(content) > MEDIA_KIT_MAX:
        raise HTTPException(status_code=413,
                            detail=f"Файл больше {MEDIA_KIT_MAX // 1024 // 1024} МБ")

    safe = re.sub(r"[^\w.\-]", "_", original)
    # Имя несёт вид сущности: медиакит площадки №7 и файл комплекта №7 в общем каталоге
    # иначе затрут друг друга — это уже случалось с документами площадок.
    stored = f"pub{publisher_id}_{safe}"
    root = os.path.join("/app/uploads", MEDIA_KIT_DIR)
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, stored), "wb") as fh:
        fh.write(content)

    p.media_kit_filename = original
    p.media_kit_path = f"{MEDIA_KIT_DIR}/{stored}"
    p.media_kit_uploaded_at = datetime.utcnow()
    journal.write(db, 'медиакит', cabinet_id=acc.cabinet_id, account_id=acc.id,
                  publisher_id=publisher_id, actor_name=acc.name, subject=original,
                  entity_type='sales_publisher', entity_id=publisher_id)
    db.commit()
    return {"name": original, "uploaded_at": p.media_kit_uploaded_at}


# Картинка к доработке. Форматы те же, что у скриншотов размещения: это тоже снимок
# экрана, просто снятый с другой стороны и с другой целью.
REWORK_EXT = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}
REWORK_MAX = 10 * 1024 * 1024
REWORK_MAX_FILES = 5
REWORK_DIR = "rework"


@router.post("/pair/{pair_id}/rework-file",
             dependencies=[Depends(require_cabinet_service)])
async def cabinet_rework_file(pair_id: int, account_id: int,
                              file: UploadFile = File(...),
                              db: Session = Depends(get_db)):
    """Приложение площадки к объяснению, что не так с креативом.

    Кладётся в ту же таблицу, что скриншоты размещения, но ВИДОМ `доработка`. Без вида
    очередь трафика посчитала бы чужие картинки своими доказательствами, а уборка по
    срокам стёрла бы их вместе: у доказательства и у приложенной к правкам картинки
    разная судьба.

    Имя НЕ переименовывается по цепочке, в отличие от скриншотов размещения: те уходят
    клиенту архивом и должны говорить, где стояли, а это — вложение к переписке, и
    исходное имя в нём осмысленно («меню_перекрыто.png»).
    """
    pair = db.query(LaunchPrepPair).filter(LaunchPrepPair.id == pair_id).first()
    if not pair:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    # Площадка здесь не приходит запросом, а берётся у получателя пары: подставить её
    # снаружи означало бы разрешить прикладывать файл к чужому заданию.
    target = db.query(LaunchPrepTarget).filter(
        LaunchPrepTarget.id == pair.target_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    acc = _actor(db, account_id, target.publisher_id)

    n = (db.query(LaunchPrepPairFile)
         .filter(LaunchPrepPairFile.pair_id == pair_id,
                 LaunchPrepPairFile.kind == "доработка").count())
    if n >= REWORK_MAX_FILES:
        raise HTTPException(status_code=400,
                            detail=f"К одной доработке можно приложить {REWORK_MAX_FILES} файлов")

    original = file.filename or "file"
    ext = os.path.splitext(original)[1].lower()
    if ext not in REWORK_EXT:
        raise HTTPException(status_code=415,
                            detail=f"Разрешены: {', '.join(sorted(REWORK_EXT))}")
    content = await file.read()
    if len(content) > REWORK_MAX:
        raise HTTPException(status_code=413,
                            detail=f"Файл больше {REWORK_MAX // 1024 // 1024} МБ")

    safe = re.sub(r"[^\w.\-]", "_", original)
    stored = f"rw{pair_id}_{n + 1}_{safe}"
    root = os.path.join("/app/uploads", REWORK_DIR)
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, stored), "wb") as fh:
        fh.write(content)

    rec = LaunchPrepPairFile(pair_id=pair_id, path=f"{REWORK_DIR}/{stored}",
                             original_name=original, content_type=file.content_type,
                             size_bytes=len(content), kind="доработка")
    db.add(rec)
    journal.write(db, 'файл_доработки', cabinet_id=acc.cabinet_id, account_id=acc.id,
                  publisher_id=target.publisher_id, actor_name=acc.name,
                  subject=_creative_subject(db, pair),
                  entity_type='launch_prep_pair', entity_id=pair_id)
    db.commit()
    return {"id": rec.id, "name": original, "size_bytes": len(content)}
