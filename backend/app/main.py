import os
import logging
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.database import engine, Base, SessionLocal
from app.routers import (auth, operations, reports, counterparties, articles, settings,
                         users, roles, contracts, sales_directories, sales_dashboard,
                         sales_reconcile)

# Базовое логирование ошибок без внешних сервисов (Sentry и т.п.) — файл с ротацией
# внутри контейнера + дублирование в stdout (видно через "docker logs finance_backend").
# /app/logs смонтирован с хоста (см. docker-compose.yml backend.volumes), поэтому лог
# переживает "docker restart"; если контейнер когда-нибудь пересоздадут без этого тома
# (force-recreate без volumes), лог-файл начнётся с нуля — это тот же компромисс, что и
# у IMPORT_SYNC_CACHE в operations.py, осознанно принят пока система не на боевом сервере.
LOG_DIR = os.getenv("LOG_DIR", "/app/logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        RotatingFileHandler(os.path.join(LOG_DIR, "backend.log"), maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("finance")

from app.sales import models as sales_models  # noqa: F401,E402 — регистрирует таблицы дашборда продаж в Base.metadata

Base.metadata.create_all(bind=engine)

# Лёгкая миграция колонок: create_all не добавляет колонки в уже существующие
# таблицы. Идемпотентно (Postgres ADD COLUMN IF NOT EXISTS).
with engine.begin() as _conn:
    from sqlalchemy import text
    _conn.execute(text("ALTER TABLE role_permissions "
                       "ADD COLUMN IF NOT EXISTS deals_scope VARCHAR DEFAULT 'all'"))
    _conn.execute(text("ALTER TABLE sales_agencies ADD COLUMN IF NOT EXISTS bx_id VARCHAR"))
    _conn.execute(text("ALTER TABLE sales_advertisers ADD COLUMN IF NOT EXISTS bx_id VARCHAR"))
    _conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS bitrix_user_id VARCHAR"))
    _conn.execute(text("ALTER TABLE sales_agencies ADD COLUMN IF NOT EXISTS bx_master VARCHAR"))
    _conn.execute(text("ALTER TABLE sales_advertisers ADD COLUMN IF NOT EXISTS bx_master VARCHAR"))
    _conn.execute(text("ALTER TABLE sales_reps ADD COLUMN IF NOT EXISTS is_sales_head BOOLEAN NOT NULL DEFAULT FALSE"))
    _conn.execute(text("ALTER TABLE sales_agencies ADD COLUMN IF NOT EXISTS sk_percent DOUBLE PRECISION NOT NULL DEFAULT 30"))
    _conn.execute(text("ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS amount_with_vat DOUBLE PRECISION"))
    _conn.execute(text("ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS brief TEXT"))
    _conn.execute(text("ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS brief_synced_at TIMESTAMP"))
    _conn.execute(text("ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS sync_status VARCHAR"))
    _conn.execute(text("ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS sync_checked_at TIMESTAMP"))
    _conn.execute(text("ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS sync_report JSONB"))
    # Индексы под запросы витрины продаж (money-layer JOIN по (pipeline,bitrix_stage),
    # own-scope и GROUP BY по FK, срез по периоду). На проде уже есть — IF NOT EXISTS
    # делает это no-op; на чистой БД воссоздаёт (раньше индексы жили вне репозитория).
    for _ix, _cols in [
        ("idx_sales_deals_stage", "pipeline, bitrix_stage"),
        ("idx_sales_deals_rep", "sales_rep_id"),
        ("idx_sales_deals_acct", "account_manager_id"),
        ("idx_sales_deals_advertiser", "advertiser_id"),
        ("idx_sales_deals_agency", "agency_id"),
        ("idx_sales_deals_period", "period_from, period_to"),
    ]:
        _conn.execute(text(f"CREATE INDEX IF NOT EXISTS {_ix} ON sales_deals ({_cols})"))


def seed_article_groups():
    """Заполняет таблицу article_groups уникальными группами из существующих статей —
    чтобы после введения справочника групп строгий выпадающий список сразу содержал
    все уже используемые группы. Идемпотентно: добавляет только отсутствующие имена."""
    from app.models import Article, ArticleGroup
    db = SessionLocal()
    try:
        existing = {g.name for g in db.query(ArticleGroup).all()}
        used = {a.group for a in db.query(Article).filter(Article.group.isnot(None)).all() if (a.group or "").strip()}
        to_add = sorted(used - existing)
        if to_add:
            base_order = db.query(func.max(ArticleGroup.sort_order)).scalar() or 0
            for i, name in enumerate(to_add, start=1):
                db.add(ArticleGroup(name=name, sort_order=base_order + i))
            db.commit()
            logger.info(f"seed_article_groups: добавлено {len(to_add)} групп из статей")
    except Exception:
        logger.exception("seed_article_groups: ошибка сидирования групп")
        db.rollback()
    finally:
        db.close()


from sqlalchemy import func  # noqa: E402
seed_article_groups()


def seed_split_permissions():
    """Идемпотентно раскладывает права старых «связок» на новые per-page ключи,
    чтобы существующие роли не потеряли доступ после расщепления:
      sales_registry/sales_analytics ← sales_dashboard;
      dir_advertisers/dir_agencies   ← sales_directories;
      settings                       ← max(settings_balances, articles).
    Создаёт только отсутствующие строки — прогон повторно безопасен."""
    from app.models import Role, RolePermission
    db = SessionLocal()
    try:
        for role in db.query(Role).all():
            rows = {rp.section: rp for rp in db.query(RolePermission).filter_by(role_id=role.id).all()}

            def add(new_key, view, edit, create=0, delete=0, vop=0, scope="all"):
                if new_key in rows:
                    return
                db.add(RolePermission(role_id=role.id, section=new_key,
                    can_view=1 if view else 0, can_edit=1 if edit else 0,
                    can_create=1 if create else 0, can_delete=1 if delete else 0,
                    can_view_operations=1 if vop else 0, deals_scope=scope))

            sd = rows.get("sales_dashboard")
            if sd:
                add("sales_registry", sd.can_view, sd.can_edit, scope=(sd.deals_scope or "all"))
                add("sales_analytics", sd.can_view, sd.can_edit, scope=(sd.deals_scope or "all"))
            sdir = rows.get("sales_directories")
            if sdir:
                add("dir_advertisers", sdir.can_view, sdir.can_edit, delete=sdir.can_delete)
                add("dir_agencies", sdir.can_view, sdir.can_edit, delete=sdir.can_delete)
            sb, art = rows.get("settings_balances"), rows.get("articles")
            add("settings",
                (sb and sb.can_view) or (art and art.can_view),
                (sb and sb.can_edit) or (art and art.can_edit))
        db.commit()
        logger.info("seed_split_permissions: права per-page разложены")
    except Exception:
        logger.exception("seed_split_permissions: ошибка")
        db.rollback()
    finally:
        db.close()


seed_split_permissions()


def backfill_sales_scope():
    """Выравнивает deals_scope трёх sales-секций по строке sales_dashboard (источник
    отображения в UI). Раньше update_role писал scope только в sales_dashboard, а
    энфорсмент own-scope читает sales_registry/sales_analytics — старые роли с 'own'
    по факту показывали ВСЕ сделки. Идемпотентно: правит только расходящиеся строки."""
    from app.models import Role, RolePermission
    db = SessionLocal()
    try:
        for role in db.query(Role).all():
            rows = {rp.section: rp for rp in db.query(RolePermission).filter_by(role_id=role.id).all()}
            sd = rows.get("sales_dashboard")
            if not sd:
                continue
            scope = sd.deals_scope or "all"
            for sec in ("sales_registry", "sales_analytics"):
                r = rows.get(sec)
                if r and (r.deals_scope or "all") != scope:
                    r.deals_scope = scope
        db.commit()
        logger.info("backfill_sales_scope: deals_scope выровнен по sales_dashboard")
    except Exception:
        logger.exception("backfill_sales_scope: ошибка")
        db.rollback()
    finally:
        db.close()


backfill_sales_scope()

# В DEBUG=true (локальная разработка) Swagger UI доступен на /docs.
# В production (DEBUG не задан или false) документация закрыта — /docs, /redoc, /openapi.json
# возвращают 404, чтобы не раскрывать схему API без аутентификации (OWASP A6).
_debug = os.getenv("DEBUG", "false").lower() == "true"
app = FastAPI(
    title="Finance Management System",
    docs_url="/docs" if _debug else None,
    redoc_url="/redoc" if _debug else None,
    openapi_url="/openapi.json" if _debug else None,
)

# http://localhost:3000 остаётся всегда — это прямой доступ к фронтенду в обход Caddy
# (см. docker-compose.yml, порт смотрит на 127.0.0.1, доступен только с этой машины),
# полезно для отладки. https://{DOMAIN} добавляется, когда задан реальный домен (см.
# .env и Caddyfile) — без этого браузер на https://ваш-домен получал бы CORS-ошибку,
# хотя на практике после перехода фронтенда на относительный путь /api (см. Caddyfile)
# запросы идут с того же origin и CORS для них вообще не задействуется; этот источник
# остаётся как подстраховка для прямых cross-origin обращений к API.
_DOMAIN = os.getenv("DOMAIN", "localhost")
_allow_origins = ["http://localhost:3000"]
if _DOMAIN and _DOMAIN != "localhost":
    _allow_origins.append(f"https://{_DOMAIN}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ExceptionLoggingMiddleware(BaseHTTPMiddleware):
    """Логирует необработанные исключения (с traceback) перед тем, как FastAPI
    вернёт стандартный 500 — без этого падения видны только мимо пролетевшим
    "docker logs" в момент сбоя, а потом теряются без следа."""
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:
            logger.exception(f"Необработанное исключение: {request.method} {request.url.path}")
            raise

app.add_middleware(ExceptionLoggingMiddleware)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(operations.router, prefix="/api/operations", tags=["operations"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(counterparties.router, prefix="/api/counterparties", tags=["counterparties"])
app.include_router(articles.router, prefix="/api/articles", tags=["articles"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(roles.router, prefix="/api/roles", tags=["roles"])
app.include_router(contracts.router, prefix="/api/contracts", tags=["contracts"])
app.include_router(sales_directories.router, prefix="/api/sales/directories", tags=["sales"])
app.include_router(sales_reconcile.router, prefix="/api/sales/reconcile", tags=["sales"])
# Монтируется ПОСЛЕ справочников/сверки, чтобы их префиксы не перехватывались
app.include_router(sales_dashboard.router, prefix="/api/sales", tags=["sales"])

@app.get("/")
def root():
    return {"status": "ok", "message": "Finance API running"}