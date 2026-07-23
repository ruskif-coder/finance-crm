import os
import logging
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.database import engine, Base, SessionLocal
from app.routers import auth, operations, reports, counterparties, articles, settings, users, roles, contracts

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

@app.get("/")
def root():
    return {"status": "ok", "message": "Finance API running"}