import os
import logging
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.database import engine, Base, SessionLocal
from app.routers import (auth, operations, reports, counterparties, articles, settings,
                         users, roles, contracts, sales_directories, sales_dashboard,
                         sales_reconcile, media_plans, notifications, notify_settings,
                         year_plan, finreport, backlog, account_dashboard,
                         publishers, diadoc, ord, launch_prep, traffic, cabinets,
                         cabinet_gateway, traffic_catalog, traffic_balancer,
                         dsp_demo, weborama_demo, traffic_dashboard, annexes, directory_add,
                         exec_dashboard, system_status, mail_admin)

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
from app import diadoc_models  # noqa: F401,E402 — реестр документов Диадока (миграция 2026-08-20_diadoc_documents.sql)
from app.ord import models as ord_models          # noqa: F401,E402 — регистрирует таблицы в create_all
from app.launch_prep import models as launch_prep_models  # noqa: F401,E402 — модуль креативов (миграция 2026-08-26_launch_prep_creatives.sql)
from app.cabinet import models as cabinet_models  # noqa: F401,E402 — учётки кабинета (миграция 2026-08-28_publisher_cabinet.sql)
from app.ad import models as ad_models  # noqa: F401,E402 — дашборд трафика/РК (миграция 2026-09-01_ad_campaigns.sql)
from app.weborama import models as weborama_models  # noqa: F401,E402 — контур Weborama (миграция 2026-09-09_weborama.sql)

Base.metadata.create_all(bind=engine)

# Схемные ALTER/CREATE INDEX ВЫНЕСЕНЫ В МИГРАЦИЮ 31.08.2026
# (migrations/2026-08-31_startup_ddl_extracted.sql). Раньше здесь жил блок
# `with engine.begin()`, гонявший ~50 `ALTER TABLE … ADD COLUMN IF NOT EXISTS` при КАЖДОМ
# старте. На свежей базе первый старт заводил колонки под AccessExclusiveLock, а
# параллельные логины — под RowShareLock: Postgres ловил deadlock, зависшие bcrypt-воркеры
# исчерпывали пул, вход виснул. Схема теперь правится миграцией ДО старта кода (порядок
# «миграции до кода», навык deploying-to-prod), один раз и без конкуренции.
#
# На старте остаётся только `create_all` выше: он создаёт недостающие ОРМ-таблицы (CREATE
# TABLE IF NOT EXISTS — проверка каталога, не ALTER, эксклюзивных блокировок на
# существующие таблицы не берёт) и на свежей базе делает таблицы сразу полными. Добавлять
# сюда ALTER/CREATE INDEX нельзя — это запрещено тестом tests/test_startup_ddl.py.


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
      sales_dashboard   → sales_registry + sales_analytics;
      sales_directories → dir_advertisers + dir_agencies;
      settings          → settings_balances + settings_articles + settings_pipelines + settings_services.
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
            # Настройки: старое единое право `settings` → per-раздел (остатки/статьи/
            # воронки/услуги). settings_field_audit (раньше был под `settings`) и
            # settings_audit (раньше был admin-only) намеренно НЕ переносим: по новой
            # модели доступ к настройкам default-deny, выдаётся ролям точечно через
            # конструктор ролей (админ и так видит всё через bypass).
            st = rows.get("settings")
            if st:
                for k in ("settings_balances", "settings_articles", "settings_pipelines", "settings_services"):
                    add(k, st.can_view, st.can_edit)
        db.commit()
        logger.info("seed_split_permissions: права per-page разложены")
    except Exception:
        logger.exception("seed_split_permissions: ошибка")
        db.rollback()
    finally:
        db.close()


seed_split_permissions()


def seed_sales_formats():
    """Идемпотентно наполняет справочник форматов (sales_formats) базовым набором + любыми
    значениями SalesService.placement_type, и бэкфиллит связки услуга↔формат. Дефолтный
    формат остаётся строкой в placement_type (вариант B). Прогон повторно безопасен."""
    from app.sales.models import SalesService, SalesFormat, SalesServiceFormat
    CATALOG = [
        ("Медийка", ["Banners", "Rich Media", "Native", "Interstitial"]),
        ("Видео", ["OLV In-stream", "OLV Out-stream", "Rewarded video", "CTV/OTT"]),
        ("Аудио", ["Audio"]),
        ("In-App", ["Playable", "App install"]),
        ("Наружка", ["DOOH"]),
        ("Прочее", ["Push", "Pop-under", "Соцсети"]),
    ]
    db = SessionLocal()
    try:
        existing = {f.name: f for f in db.query(SalesFormat).all()}
        order = db.query(func.max(SalesFormat.sort_order)).scalar() or 0
        for group, names in CATALOG:
            for nm in names:
                if nm not in existing:
                    order += 1
                    f = SalesFormat(name=nm, group=group, sort_order=order)
                    db.add(f); db.flush(); existing[nm] = f
        svcs = db.query(SalesService).all()
        for s in svcs:                          # placement_type, которых нет в справочнике
            pt = (s.placement_type or "").strip()
            if pt and pt not in existing:
                order += 1
                f = SalesFormat(name=pt, sort_order=order)
                db.add(f); db.flush(); existing[pt] = f
        links = {(l.service_id, l.format_id) for l in db.query(SalesServiceFormat).all()}
        for s in svcs:                          # бэкфилл связок из placement_type
            pt = (s.placement_type or "").strip()
            if pt and (s.id, existing[pt].id) not in links:
                db.add(SalesServiceFormat(service_id=s.id, format_id=existing[pt].id))
                links.add((s.id, existing[pt].id))
        db.commit()
        logger.info("seed_sales_formats: форматы и связки засеяны")
    except Exception:
        logger.exception("seed_sales_formats: ошибка")
        db.rollback()
    finally:
        db.close()


seed_sales_formats()


def seed_targeting_and_geo():
    """Идемпотентно засевает каталог таргетинга (по группам) и справочник гео из шаблона."""
    from app.sales.models import SalesTargetingItem, SalesGeo
    TARGETING = {
        "audience": ["Ж/М 30–60"],
        "buys": ["витамины группы B", "препараты при нейропатии", "обезболивающие при болях в спине", "средства при диабетической полинейропатии"],
        "interests": ["неврология", "здоровье спины и суставов", "медицина и здоровье"],
        "behavior": ["сайты аптек", "онлайн-заказ лекарств", "медицинские порталы", "запись к неврологу"],
        "competitors": ["Комбилипен", "Нейромультивит", "Нейробион", "Бенфогамма", "Тиогамма"],
    }
    GEO = ["РФ", "Москва", "Санкт-Петербург", "Города 500K+", "Регионы"]
    db = SessionLocal()
    try:
        existing = {(t.group, t.value) for t in db.query(SalesTargetingItem).all()}
        for grp, vals in TARGETING.items():
            order = db.query(func.max(SalesTargetingItem.sort_order)).filter(SalesTargetingItem.group == grp).scalar() or 0
            for v in vals:
                if (grp, v) not in existing:
                    order += 1
                    db.add(SalesTargetingItem(group=grp, value=v, sort_order=order)); existing.add((grp, v))
        geo_existing = {g.name for g in db.query(SalesGeo).all()}
        gord = db.query(func.max(SalesGeo.sort_order)).scalar() or 0
        for nm in GEO:
            if nm not in geo_existing:
                gord += 1
                db.add(SalesGeo(name=nm, sort_order=gord)); geo_existing.add(nm)
        db.commit()
        logger.info("seed_targeting_and_geo: каталоги засеяны")
    except Exception:
        logger.exception("seed_targeting_and_geo: ошибка")
        db.rollback()
    finally:
        db.close()


seed_targeting_and_geo()


def assign_notification_profiles():
    """Разложить по профилям уведомлений тех, у кого профиль не проставлен.

    Идемпотентно: трогает только NULL, вручную назначенный профиль не перебивает.
    Нужен здесь, а не разовым скриптом: пока его никто не вызывал, все 15 человек
    сидели с NULL, и в настройках уведомлений каждый профиль показывал «0 человек».
    """
    try:
        from app.notify.seed_profiles import assign_profiles
        n = assign_profiles()
        if n:
            logger.info("assign_notification_profiles: назначено профилей %s", n)
    except Exception as e:
        logger.error("assign_notification_profiles: %s", e)


assign_notification_profiles()


def seed_stage_catalog():
    """Идемпотентно засевает НАШ каталог стадий (E1) из минимального набора CSV.
    Каждая стадия привязана к под-этапу 2/2/2 (STAGE_CATALOG key), из него выводится
    money_layer. Полный сев — только если каталог пуст; иначе бэкфиллит stage_key для
    строк, оставшихся с прошлой (money_layer-только) версии."""
    from app.sales.models import SalesStagePhase, SalesStage
    from app.sales.stages import STAGE_BY_KEY
    CATALOG = [
        ("Песочница", [
            # Стартовых стадий две. «МП согласование» убрана 2026-08-17 как бюрократия
            # (миграция 2026-08-17_drop_mp_approval_stage.sql) — не возвращать.
            ("МП Подготовка", "media_plan", False),
            ("МП Отправлено", "media_plan", False),
            ("Сделка не случилась", None, True),
        ]),
        ("Услуги", [
            ("Бронь", "booking", False),
            ("Готовятся к старту", "launch_prep", False),
            ("В размещении", "launch", False),
            # Сверка одна (миграции 2026-08-17_stage_final_reconcile + _merge_reconcile_stage):
            # предварительной и итоговой по отдельности не существует. Слой «реализуемые» —
            # сверка не закрытие, деньги на ней в работе, а не факт.
            ("Итоговая сверка", "launch", False),
            ("Сделка сорвалась", None, True),
        ]),
        ("Документооборот (ДО)", [
            ("Подготовка ДС", "closing", False),
            ("Согласование ДС", "closing", False),
            ("Подготовка закрывающих", "closing", False),
            # С ЭДО начинается вторая половина факта — документы в обороте
            # (миграция 2026-08-17_split_closing_layer.sql).
            ("ЭДО", "closing_fact", False),
            ("Отчёты в ОРД", "closing_fact", False),
            ("Оплата", "closing_fact", False),
            ("Архив успешных сделок", "archive", False),
        ]),
    ]
    layer_of = lambda key: (STAGE_BY_KEY[key]["money_layer"] if key in STAGE_BY_KEY else None)
    db = SessionLocal()
    try:
        if not db.query(SalesStagePhase).first():
            for pi, (pname, stages) in enumerate(CATALOG):
                ph = SalesStagePhase(name=pname, sort_order=pi)
                db.add(ph); db.flush()
                for si, (sname, key, term) in enumerate(stages):
                    # Точка входа каталога — первая стадия первого этапа: сделка на ней
                    # рождается, МП там ещё нет. Признак позиционный, а не по имени:
                    # стадию переименуют, и правило по имени сломает создание сделок.
                    entry = (pi == 0 and si == 0)
                    db.add(SalesStage(phase_id=ph.id, name=sname, sort_order=si,
                                      stage_key=key, money_layer=layer_of(key), is_terminal=term,
                                      requires_media_plan=(not term and not entry)))
            # этап «Услуги» — реализационный (воронка выбирается на сделке)
            for ph in db.query(SalesStagePhase).filter(SalesStagePhase.name == "Услуги").all():
                ph.is_realization = True
            db.commit()
            logger.info("seed_stage_catalog: каталог стадий засеян из CSV")
            return
        # каталог уже есть — бэкфилл stage_key по имени (миграция с money_layer-версии)
        name_to_key = {sname: key for _, stages in CATALOG for sname, key, _ in stages}
        changed = 0
        for s in db.query(SalesStage).filter(SalesStage.stage_key.is_(None)).all():
            key = name_to_key.get(s.name)
            if key:
                s.stage_key, s.money_layer, changed = key, layer_of(key), changed + 1
        # добиваем флаг реализации у «Услуги» (для БД, засеянных до его появления)
        for ph in db.query(SalesStagePhase).filter(SalesStagePhase.name == "Услуги",
                                                   SalesStagePhase.is_realization.is_(False)).all():
            ph.is_realization = True; changed += 1
        # requires_media_plan — РАЗОВАЯ инициализация для баз, засеянных до появления
        # флага. Раньше этот блок выполнялся на каждом старте и выводил флаг из имени
        # стадии: переименование «МП Подготовки» ломало создание сделок, а ручная
        # настройка флага откатывалась ближайшим рестартом. Теперь правило позиционное
        # (точка входа = первая нетерминальная стадия каталога), и если флаг уже кем-то
        # выставлен — не трогаем вовсе.
        all_stages = (db.query(SalesStage).join(SalesStagePhase)
                      .order_by(SalesStagePhase.sort_order, SalesStage.sort_order,
                                SalesStage.id).all())
        if not any(s.requires_media_plan for s in all_stages):
            entry = next((s for s in all_stages if not s.is_terminal), None)
            for s in all_stages:
                want = (not s.is_terminal) and (entry is None or s.id != entry.id)
                if bool(s.requires_media_plan) != want:
                    s.requires_media_plan = want; changed += 1
        if changed:
            db.commit()
            logger.info(f"seed_stage_catalog: backfill {changed} стадий/этапов")
    except Exception:
        logger.exception("seed_stage_catalog: ошибка")
        db.rollback()
    finally:
        db.close()


seed_stage_catalog()


def backfill_deal_our_stage():
    """Сидирует our_stage_id сделкам без него: (pipeline, bitrix_stage) → stage_key
    (через sales_bitrix_stage_map) → первая наша стадия с этим stage_key. Работает
    со всеми сделками независимо от происхождения; фолбэк — не трогаем (остаётся NULL)."""
    from app.sales.models import SalesDeal, SalesStage, SalesBitrixStageMap
    from app.sales.normalize import normalize_name
    db = SessionLocal()
    try:
        stages = db.query(SalesStage).all()
        if not stages:
            return
        # первая (по phase/sort) стадия на каждый stage_key
        from app.sales.catalog import Catalog
        cat = Catalog(db)
        first_by_key = {}
        for s in cat.stages:
            if s.stage_key and s.stage_key not in first_by_key:
                first_by_key[s.stage_key] = s.id
        # карта (воронка, стадия) → stage_key
        rows = db.query(SalesBitrixStageMap).all()
        key_by_pair = {(normalize_name(r.pipeline), normalize_name(r.bitrix_stage)): r.stage_key for r in rows}
        changed = 0
        for d in db.query(SalesDeal).filter(SalesDeal.our_stage_id.is_(None)).all():
            key = key_by_pair.get((normalize_name(d.pipeline or ""), normalize_name(d.bitrix_stage or "")))
            sid = first_by_key.get(key) if key else None
            if sid:
                d.our_stage_id = sid; changed += 1
        if changed:
            db.commit()
            logger.info(f"backfill_deal_our_stage: проставлено {changed} сделкам")
    except Exception:
        logger.exception("backfill_deal_our_stage: ошибка")
        db.rollback()
    finally:
        db.close()


backfill_deal_our_stage()


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


# Внешние ключи ВЫНЕСЕНЫ В МИГРАЦИЮ 31.08.2026 вместе с остальным стартовым DDL
# (migrations/2026-08-31_startup_ddl_extracted.sql). `add_missing_foreign_keys()`
# добавлял их при каждом старте через ADD CONSTRAINT FOREIGN KEY — тот же класс блокировок,
# что деадлочил вход. Теперь это часть миграции, которая идёт до старта кода.

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


@app.middleware("http")
async def _neutralize_ad_query(request: Request, call_next):
    """Блокировщики рекламы (uBlock/AdGuard) режут запросы с "advertiser" в URL.
    Фронт шлёт нейтральные producer_id и /reconcile/producers — здесь возвращаем
    исходные имена, чтобы эндпоинты/фильтры не менять (единая точка на бэке).

    Путь понадобился отдельно от параметра: сверка справочников адресуется как
    /api/sales/reconcile/{kind}/…, и при kind=advertisers блокировщик резал
    /advertisers/link, /advertisers/deal-counts и остальные операции. Запрос при
    этом не доходит до сервера вообще: в браузере ошибка без ответа, в логах —
    ничего. Адрес, ЗАКАНЧИВАЮЩИЙСЯ на advertisers, проходил, поэтому список
    загружался, а любое действие над ним — нет (проверено на проде 2026-08-23).
    """
    qs = request.scope.get("query_string", b"")
    if b"producer_id" in qs:
        request.scope["query_string"] = qs.replace(b"producer_id", b"advertiser_id")
    path = request.scope.get("path", "")
    if "/reconcile/producers" in path:
        request.scope["path"] = path.replace("/reconcile/producers", "/reconcile/advertisers")
        raw = request.scope.get("raw_path")
        if raw:
            request.scope["raw_path"] = raw.replace(b"/reconcile/producers",
                                                    b"/reconcile/advertisers")
    return await call_next(request)


app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(operations.router, prefix="/api/operations", tags=["operations"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(finreport.router, prefix="/api/finreport", tags=["reports"])
app.include_router(counterparties.router, prefix="/api/counterparties", tags=["counterparties"])
app.include_router(articles.router, prefix="/api/articles", tags=["articles"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(roles.router, prefix="/api/roles", tags=["roles"])
app.include_router(contracts.router, prefix="/api/contracts", tags=["contracts"])
app.include_router(sales_directories.router, prefix="/api/sales/directories", tags=["sales"])
app.include_router(publishers.router, prefix="/api/publishers", tags=["publishers"])
app.include_router(media_plans.router, prefix="/api/sales/media-plans", tags=["sales"])
# Настройки монтируются ПЕРЕД колокольчиком: у notifications есть @router.get(""),
# и вложенный префикс не должен им перехватываться.
app.include_router(notify_settings.router, prefix="/api/notifications/settings",
                   tags=["notifications"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(sales_reconcile.router, prefix="/api/sales/reconcile", tags=["sales"])
# Монтируется ПОСЛЕ справочников/сверки, чтобы их префиксы не перехватывались
app.include_router(sales_dashboard.router, prefix="/api/sales", tags=["sales"])
# Очередь аккаунта — тот же префикс: адреса /api/sales/account-* не менялись при выносе
# в отдельный роутер (app/routers/account_dashboard.py).
app.include_router(account_dashboard.router, prefix="/api/sales", tags=["sales"])
app.include_router(year_plan.router, prefix="/api/sales/year-plan", tags=["sales"])
app.include_router(backlog.router, prefix="/api/backlog", tags=["backlog"])
app.include_router(diadoc.router, prefix="/api/diadoc", tags=["diadoc"])
app.include_router(ord.router, prefix="/api/ord", tags=["ord"])
# Модуль креативов: сбор запуска. Живёт на карточке сделки, отдельного экрана
# не имеет, поэтому записи в карте навигации у него нет — только право.
app.include_router(launch_prep.router, prefix="/api/launch-prep", tags=["creatives"])
# Контур «Траффики»: очередь проверки материала перед отправкой площадкам.
# У него, в отличие от модуля креативов, СВОЙ экран — и запись в карте навигации.
app.include_router(traffic.router, prefix="/api/traffic", tags=["traffic"])
app.include_router(traffic_catalog.router, prefix="/api/traffic-catalog", tags=["traffic_catalog"])
app.include_router(traffic_balancer.router, prefix="/api/traffic-catalog", tags=["traffic_balancer"])
app.include_router(traffic_dashboard.router, prefix="/api/traffic-dashboard", tags=["traffic_dashboard"])
app.include_router(dsp_demo.router, prefix="/api/dsp-demo", tags=["dsp_demo"])
app.include_router(weborama_demo.router, prefix="/api/weborama-demo", tags=["weborama_demo"])
# Приложения к договору (ДС): сборка, подтверждение номера, шаблоны формулировок.
app.include_router(annexes.router, prefix="/api/annexes", tags=["annexes"])
# «Добавить данные» — вход на экран и набор доступных блоков. Писателей у него нет:
# сохраняет он существующими ручками справочников.
app.include_router(directory_add.router, prefix="/api/directory-add", tags=["directory_add"])
# Дашборд руководителя. Закрыт require_admin, а не правом: экран сквозной и для одного
# человека, а секция в конструкторе ролей могла бы быть выдана по неосторожности.
app.include_router(exec_dashboard.router, prefix="/api/exec", tags=["exec_dashboard"])
# Состояние системы. Тоже require_admin: показывает инфраструктуру, а не бизнес-данные.
app.include_router(system_status.router, prefix="/api/system", tags=["system_status"])
# Почтовый гейт: журнал писем наружу, шаблоны, проверка канала (13.09.2026).
app.include_router(mail_admin.router, prefix="/api/mail", tags=["mail"])
# Учётки внешнего кабинета — администрирование со стороны ядра. Сам кабинет живёт
# отдельным сервисом (`cabinet/`) и ходит в базу под своей ролью.
app.include_router(cabinets.router, prefix="/api/cabinets", tags=["cabinets"])
# Вход для СЕРВИСА кабинета: два действия под общим секретом, не под правом роли.
# Снаружи здесь стоит не человек, а наш же процесс во внешнем контуре.
app.include_router(cabinet_gateway.router, prefix="/api/cabinet-gw", tags=["cabinet-gw"])
# Вебхук бота площадок — ОТДЕЛЬНЫМ префиксом: `/api/cabinet-gw/*` закрыт на Caddy, а сюда
# стучится Телеграм из интернета. Разбор в шапке `webhook_router`.
app.include_router(cabinet_gateway.webhook_router, prefix="/api/pub-bot", tags=["pub-bot"])

@app.get("/")
def root():
    return {"status": "ok", "message": "Finance API running"}