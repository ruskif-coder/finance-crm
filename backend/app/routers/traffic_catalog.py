"""Контур «Траффики»: каталог площадок и блоков (справочник для DSP).

Экран-справочник в админ-кабинете трафиков. Первичное наполнение — импорт из
«Площадки и блоки.xlsx» (scripts.import_publisher_blocks), дальше правится здесь.

Модель переиспользует иерархию модуля паблишеров, а не плодит свою:
  · поверхность площадки — `sales_publisher_surfaces` (web|app). На ней МС-реквизиты:
    `ms_publisher_id` (id паблишера в DSP) и `default_ms_block_id` («кукуха2» —
    блок по умолчанию, авто-цепляется к креативу, но скрыт из статистики кабинета);
  · рекламные блоки — `publisher_block`, вешаются на поверхность через `surface_id`.
ios/android (платформы `sales_publisher_surface_platforms`) — на будущее: в файле app пока
не разделён, DSP отдаёт его одним id.

Право — `traffic_catalog` (view/create/edit/delete), доступ по умолчанию мастера + админ.
Миграция `2026-09-01_traffic_catalog.sql`.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.ad.models import PublisherBlock
from app.audit import log_action
from app.database import get_db
from app.models import User
from app.permissions import require_permission
from app.sales.models import (PUBLISHER_ARCHIVE_STATUS, SalesPublisher,
                              SalesPublisherSurface)

router = APIRouter()

VIEW = require_permission("traffic_catalog", "view")
CREATE = require_permission("traffic_catalog", "create")
EDIT = require_permission("traffic_catalog", "edit")
DELETE = require_permission("traffic_catalog", "delete")

SURFACE_KINDS = ("web", "app")
# Типовые разделы страниц — курируемая основа; накопитель пополняется фактически
# использованными значениями (кнопка «+ тип» на экране). Отдельную таблицу-справочник не
# заводим: значение хранится строкой на блоке, список собирается из употреблений.
DEFAULT_PAGE_TYPES = ["главная", "каталог", "карточка товара", "корзина", "статьи", "акции", "лк"]


# ============================== схемы ==============================

class SurfaceMS(BaseModel):
    ms_publisher_id: Optional[str] = None
    default_ms_block_id: Optional[str] = None


class SurfaceNew(BaseModel):
    kind: str                       # web | app


class PublisherCode(BaseModel):
    code: Optional[str] = None


class BlockIn(BaseModel):
    ms_block_id: Optional[str] = None
    name: Optional[str] = None
    page_type: Optional[str] = None
    network: Optional[str] = None
    is_active: Optional[bool] = True


def _block_out(b: PublisherBlock) -> dict:
    return dict(id=b.id, ms_block_id=b.ms_block_id, name=b.name, page_type=b.page_type,
               network=b.network, is_active=bool(b.is_active))


def _surface_out(db: Session, s: SalesPublisherSurface) -> dict:
    blocks = (db.query(PublisherBlock)
              .filter(PublisherBlock.surface_id == s.id)
              .order_by(PublisherBlock.page_type, PublisherBlock.ms_block_id).all())
    return dict(id=s.id, kind=s.kind, ms_publisher_id=s.ms_publisher_id,
               default_ms_block_id=s.default_ms_block_id,
               blocks=[_block_out(b) for b in blocks])


# ============================== чтение ==============================

@router.get("/publishers")
def list_publishers(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Реестр площадок для левой колонки: код, домен, число поверхностей с МС и блоков."""
    surf = dict(db.query(SalesPublisherSurface.publisher_id,
                         sa_func.count(SalesPublisherSurface.id))
                .filter(SalesPublisherSurface.ms_publisher_id.isnot(None))
                .group_by(SalesPublisherSurface.publisher_id).all())
    blk = dict(db.query(PublisherBlock.publisher_id, sa_func.count(PublisherBlock.id))
               .group_by(PublisherBlock.publisher_id).all())
    # Архивные площадки в админке трафика не показываем (решение владельца 02.09.2026).
    rows = (db.query(SalesPublisher)
            .filter(SalesPublisher.status != PUBLISHER_ARCHIVE_STATUS)
            .order_by(sa_func.lower(SalesPublisher.name)).all())
    return [dict(id=p.id, code=p.code, name=p.name, domain=p.domain,
                 ms_surfaces=surf.get(p.id, 0), blocks=blk.get(p.id, 0)) for p in rows]


@router.get("/page-types")
def page_types(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Типовые разделы для выбора: курируемые дефолты + фактически использованные (накопитель)."""
    used = [r[0] for r in db.query(PublisherBlock.page_type).distinct().all() if r[0]]
    extra = sorted(set(used) - set(DEFAULT_PAGE_TYPES))
    return DEFAULT_PAGE_TYPES + extra


@router.get("/publisher/{publisher_id}")
def get_publisher(publisher_id: int, db: Session = Depends(get_db), user: User = Depends(VIEW)):
    p = db.query(SalesPublisher).get(publisher_id)
    if not p:
        raise HTTPException(404, "Площадка не найдена")
    surfaces = (db.query(SalesPublisherSurface)
                .filter(SalesPublisherSurface.publisher_id == publisher_id)
                .order_by(SalesPublisherSurface.kind).all())
    return dict(id=p.id, code=p.code, name=p.name, domain=p.domain,
               surfaces=[_surface_out(db, s) for s in surfaces])


# ============================== поверхность ==============================

@router.put("/publisher/{publisher_id}/code")
def edit_publisher_code(publisher_id: int, payload: PublisherCode,
                        db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Код площадки (`SalesPublisher.code`) — средняя часть кода пары размещения в DSP.
    Дубль настройки из реестра паблишеров; правится здесь под «карандашом». Уникален."""
    p = db.query(SalesPublisher).get(publisher_id)
    if not p:
        raise HTTPException(404, "Площадка не найдена")
    code = (payload.code or "").strip().upper() or None
    if code and len(code) > 8:
        raise HTTPException(400, "Код не длиннее 8 символов")
    if code:
        dup = (db.query(SalesPublisher)
               .filter(SalesPublisher.code == code, SalesPublisher.id != publisher_id).first())
        if dup:
            raise HTTPException(409, f"Код «{code}» уже у площадки {dup.name}")
    old = p.code
    p.code = code
    db.commit()
    log_action(db, user, "traffic_catalog_code_edit", "sales_publisher", p.id,
               f"код {old or '—'} → {code or '—'}")
    return {"id": p.id, "code": p.code}


@router.post("/publisher/{publisher_id}/surface")
def add_surface(publisher_id: int, payload: SurfaceNew,
                db: Session = Depends(get_db), user: User = Depends(CREATE)):
    if payload.kind not in SURFACE_KINDS:
        raise HTTPException(400, f"Поверхность бывает {SURFACE_KINDS}")
    if not db.query(SalesPublisher).get(publisher_id):
        raise HTTPException(404, "Площадка не найдена")
    exists = (db.query(SalesPublisherSurface)
              .filter_by(publisher_id=publisher_id, kind=payload.kind).first())
    if exists:
        raise HTTPException(409, "Поверхность уже есть")
    s = SalesPublisherSurface(publisher_id=publisher_id, kind=payload.kind)
    db.add(s)
    db.commit()
    log_action(db, user, "traffic_catalog_surface_add", "sales_publisher", publisher_id,
               f"поверхность {payload.kind}")
    return _surface_out(db, s)


@router.put("/surface/{surface_id}")
def edit_surface(surface_id: int, payload: SurfaceMS,
                 db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Правка МС-реквизитов поверхности. Другие поля поверхности — в модуле паблишеров."""
    s = db.query(SalesPublisherSurface).get(surface_id)
    if not s:
        raise HTTPException(404, "Поверхность не найдена")
    s.ms_publisher_id = (payload.ms_publisher_id or None)
    s.default_ms_block_id = (payload.default_ms_block_id or None)
    db.commit()
    log_action(db, user, "traffic_catalog_surface_edit", "sales_publisher", s.publisher_id,
               f"{s.kind}: ms={s.ms_publisher_id} default={s.default_ms_block_id}")
    return _surface_out(db, s)


# ============================== блоки ==============================

@router.post("/surface/{surface_id}/block")
def add_block(surface_id: int, payload: BlockIn,
              db: Session = Depends(get_db), user: User = Depends(CREATE)):
    s = db.query(SalesPublisherSurface).get(surface_id)
    if not s:
        raise HTTPException(404, "Поверхность не найдена")
    if payload.ms_block_id and (db.query(PublisherBlock)
                                .filter_by(surface_id=surface_id,
                                           ms_block_id=payload.ms_block_id).first()):
        raise HTTPException(409, "Блок с таким id уже есть на поверхности")
    b = PublisherBlock(surface_id=surface_id, publisher_id=s.publisher_id, surface=s.kind,
                       ms_block_id=payload.ms_block_id, name=payload.name,
                       page_type=payload.page_type, network=payload.network,
                       is_active=bool(payload.is_active))
    db.add(b)
    db.commit()
    log_action(db, user, "traffic_catalog_block_add", "sales_publisher", s.publisher_id,
               f"{s.kind}/{payload.ms_block_id}: {payload.name}")
    return _block_out(b)


@router.put("/block/{block_id}")
def edit_block(block_id: int, payload: BlockIn,
               db: Session = Depends(get_db), user: User = Depends(EDIT)):
    b = db.query(PublisherBlock).get(block_id)
    if not b:
        raise HTTPException(404, "Блок не найден")
    b.ms_block_id = payload.ms_block_id
    b.name = payload.name
    b.page_type = payload.page_type
    b.network = payload.network
    if payload.is_active is not None:
        b.is_active = bool(payload.is_active)
    db.commit()
    log_action(db, user, "traffic_catalog_block_edit", "sales_publisher", b.publisher_id,
               f"блок {b.ms_block_id}: {b.name}")
    return _block_out(b)


@router.delete("/block/{block_id}")
def delete_block(block_id: int, db: Session = Depends(get_db), user: User = Depends(DELETE)):
    b = db.query(PublisherBlock).get(block_id)
    if not b:
        raise HTTPException(404, "Блок не найден")
    pub_id, msid = b.publisher_id, b.ms_block_id
    db.delete(b)
    db.commit()
    log_action(db, user, "traffic_catalog_block_delete", "sales_publisher", pub_id,
               f"блок {msid}")
    return {"ok": True}


# ── Скрипт, вшиваемый в креатив ──────────────────────────────────────────────
#
# Уточнение владельца 06.09.2026: скрипт вшивается В КРЕАТИВ перед отправкой в DSP —
# внутрь его `<head>`, — а НЕ ставится площадкой на сайт. Первая версия этой вкладки
# понимала задачу наоборот.
#
# Скриптов ДВА: свой для площадок, где наш код на сайте уже стоит, и свой для тех, где
# его нет. Выбор делает `creative_script()` — одна точка на всю систему: если бы его
# делали и здесь, и в конвейере креатива, две ветки разошлись бы, и часть креативов
# уехала бы в DSP с чужим счётчиком.
#
# Признак «код стоит» — `sales_publishers.our_code`, тот же, что в карточке паблишера.
# Второго флага для того же факта нет и быть не должно.

SCRIPT_OUR_CODE = "traffic_creative_script_our_code"     # площадка с нашим кодом
SCRIPT_NO_CODE = "traffic_creative_script_no_code"       # площадка без нашего кода

# Строка, которую владелец назвал 06.09.2026. К какой колонке она относится — решает он
# сам на экране: подставить её в обе значило бы вшить один счётчик всем, а это ровно то
# разделение, ради которого вкладка и заводилась.
SUGGESTED_SCRIPT = '<script src="https://simbtech.ru/afcar/qq.js"></script>'


def _setting(db: Session, key: str) -> str:
    from sqlalchemy import text as sa_text
    return (db.execute(sa_text("SELECT value FROM company_settings WHERE key = :k"),
                       {"k": key}).scalar() or "")


def creative_script(db: Session, our_code: bool) -> str:
    """Какой скрипт вшивать в креатив для этой площадки. ЕДИНСТВЕННАЯ точка выбора."""
    return _setting(db, SCRIPT_OUR_CODE if our_code else SCRIPT_NO_CODE).strip()


@router.get("/site-script")
def get_site_script(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Два скрипта и разделение площадок: у кого наш код на сайте есть, у кого нет.

    Архивные площадки не показываем: вшивать счётчик под тех, с кем мы не работаем,
    незачем, а список из 41 строки вместо 26 делает вкладку нечитаемой.
    """
    rows = (db.query(SalesPublisher)
            .filter(SalesPublisher.status != PUBLISHER_ARCHIVE_STATUS)
            .order_by(SalesPublisher.name).all())
    out = lambda p: {"id": p.id, "name": p.name, "domain": p.domain,   # noqa: E731
                     "code": p.code, "status": p.status, "our_code": bool(p.our_code)}
    return {
        "with_code": {"script": _setting(db, SCRIPT_OUR_CODE),
                      "publishers": [out(p) for p in rows if p.our_code]},
        "without_code": {"script": _setting(db, SCRIPT_NO_CODE),
                         "publishers": [out(p) for p in rows if not p.our_code]},
        "suggested": SUGGESTED_SCRIPT,
        "where": "<head> креатива, перед отправкой в DSP",
    }


class SiteScriptIn(BaseModel):
    """Пусто — законное значение: «в эту колонку ничего не вшиваем»."""
    with_code: Optional[str] = None
    without_code: Optional[str] = None


@router.put("/site-script")
def set_site_script(payload: SiteScriptIn, db: Session = Depends(get_db),
                    user: User = Depends(EDIT)):
    """Сохранить скрипты колонок.

    Присланное непустым обязано быть тегом скрипта: строка вида «https://…/a.js» попадёт
    в `<head>` креатива как текст и молча ничего не сделает.
    """
    from sqlalchemy import text as sa_text
    pairs = ((SCRIPT_OUR_CODE, payload.with_code), (SCRIPT_NO_CODE, payload.without_code))
    for key, val in pairs:
        if val is None:
            continue
        v = val.strip()
        if v and "<script" not in v.lower():
            raise HTTPException(400, "Это не тег скрипта: ожидается <script …></script>")
        db.execute(sa_text(
            "INSERT INTO company_settings (key, value) VALUES (:k, :v) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"), {"k": key, "v": v})
    db.commit()
    log_action(db, user, "traffic_creative_script", "settings", None,
               f"с кодом: {(payload.with_code or '')[:80]} | без: {(payload.without_code or '')[:80]}")
    return get_site_script(db, user)
