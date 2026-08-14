import os
import logging
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.database import engine, Base, SessionLocal
from app.routers import (auth, operations, reports, counterparties, articles, settings,
                         users, roles, contracts, sales_directories, sales_dashboard,
                         sales_reconcile, media_plans, notifications, year_plan)

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
    # T3: светофор вероятности (наша ручная разметка): grey|orange|green
    _conn.execute(text("ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS probability_color VARCHAR"))
    # E1/E2: движение сделки по нашему каталогу
    _conn.execute(text("ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS our_stage_id INTEGER"))
    # Метка сделки (наш 6-значный код) — на неё завязаны интерфейс и ссылки.
    _conn.execute(text("ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS code VARCHAR(6)"))
    _conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_sales_deals_code ON sales_deals (code)"))
    # Жёсткий линк сделки на ячейку годового плана: строка × месяц × номер сделки в месяце.
    _conn.execute(text("ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS year_plan_line_id INTEGER"))
    _conn.execute(text("ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS plan_month INTEGER"))
    _conn.execute(text("ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS plan_deal_idx INTEGER DEFAULT 0"))
    _conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sales_deals_year_plan_line ON sales_deals (year_plan_line_id)"))
    _conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sales_deals_plan_link "
                       "ON sales_deals (year_plan_line_id, plan_month, plan_deal_idx)"))
    _conn.execute(text("UPDATE sales_deals SET plan_deal_idx = 0 "
                       "WHERE year_plan_line_id IS NOT NULL AND plan_deal_idx IS NULL"))
    # Годовой план как пакет: строка принадлежит плану, бриф и прогноз живут на строке.
    _conn.execute(text("ALTER TABLE sales_year_plan_lines ADD COLUMN IF NOT EXISTS plan_id INTEGER"))
    _conn.execute(text("ALTER TABLE sales_year_plan_lines ADD COLUMN IF NOT EXISTS brief JSONB NOT NULL DEFAULT '{}'::jsonb"))
    _conn.execute(text("ALTER TABLE sales_year_plan_lines ADD COLUMN IF NOT EXISTS service_forecast JSONB NOT NULL DEFAULT '{}'::jsonb"))
    _conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sales_year_plan_lines_plan ON sales_year_plan_lines (plan_id)"))
    # Легаси-строки без плана: под каждую уникальную (рекламодатель, год, сейлз) заводим
    # план с автозаголовком и привязываем. Идемпотентно — работает только по plan_id IS NULL.
    _conn.execute(text("""
        INSERT INTO sales_year_plans (advertiser_id, year, sales_rep_id, title, created_at)
        SELECT DISTINCT l.advertiser_id, l.year, l.sales_rep_id,
               COALESCE(a.short_name, a.name, 'Без рекламодателя') || ' · ' || l.year::text, now()
          FROM sales_year_plan_lines l
          LEFT JOIN sales_advertisers a ON a.id = l.advertiser_id
         WHERE l.plan_id IS NULL
    """))
    _conn.execute(text("""
        UPDATE sales_year_plan_lines l SET plan_id = p.id
          FROM sales_year_plans p
         WHERE l.plan_id IS NULL
           AND p.advertiser_id IS NOT DISTINCT FROM l.advertiser_id
           AND p.year = l.year
           AND p.sales_rep_id IS NOT DISTINCT FROM l.sales_rep_id
    """))
    _conn.execute(text("ALTER TABLE sales_deals ADD COLUMN IF NOT EXISTS realization_pipeline_id INTEGER"))
    _conn.execute(text("ALTER TABLE sales_stage_phases ADD COLUMN IF NOT EXISTS is_realization BOOLEAN NOT NULL DEFAULT FALSE"))
    _conn.execute(text("ALTER TABLE sales_stages ADD COLUMN IF NOT EXISTS requires_media_plan BOOLEAN NOT NULL DEFAULT FALSE"))
    # Справочник услуг: параметры для конструктора МП. sales_addon_services создаётся
    # через create_all. Промежуточная таблица вариантов больше не нужна.
    _conn.execute(text("DROP TABLE IF EXISTS sales_service_variants"))
    _conn.execute(text("ALTER TABLE sales_services DROP COLUMN IF EXISTS platform"))
    _conn.execute(text("ALTER TABLE sales_services DROP COLUMN IF EXISTS currency"))
    for _col, _type in [("placement_type", "VARCHAR"), ("calc_form", "VARCHAR"),
                        ("unit_price", "DOUBLE PRECISION"), ("unit_price_web", "DOUBLE PRECISION"),
                        ("unit_price_app", "DOUBLE PRECISION")]:
        _conn.execute(text(f"ALTER TABLE sales_services ADD COLUMN IF NOT EXISTS {_col} {_type}"))
    _conn.execute(text("ALTER TABLE sales_services ADD COLUMN IF NOT EXISTS separate_price BOOLEAN NOT NULL DEFAULT FALSE"))
    _conn.execute(text("ALTER TABLE sales_services ADD COLUMN IF NOT EXISTS constants JSONB"))
    # Привязка услуги к элементу СП 1050 Битрикса (синк по bx_id, не по имени).
    _conn.execute(text("ALTER TABLE sales_services ADD COLUMN IF NOT EXISTS bx_id VARCHAR"))
    _conn.execute(text("ALTER TABLE sales_services ADD COLUMN IF NOT EXISTS bx_title VARCHAR"))
    # E0: маппинг услуга → статья выручки (мост «сделка → операция»)
    _conn.execute(text("ALTER TABLE sales_services ADD COLUMN IF NOT EXISTS revenue_article_id INTEGER"))
    # E1: под-этап 2/2/2 у наших стадий (STAGE_CATALOG key); money_layer выводится из него
    _conn.execute(text("ALTER TABLE sales_stages ADD COLUMN IF NOT EXISTS stage_key VARCHAR"))
    _conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sales_services_bx_id ON sales_services (bx_id)"))
    _conn.execute(text("ALTER TABLE sales_addon_services ADD COLUMN IF NOT EXISTS period VARCHAR"))
    # Рабочая группа + мастер — на РОЛИ (классификация продавец/аккаунт/трафик для
    # пикеров ответственных в конструкторе МП; наследуется пользователем через роль).
    _conn.execute(text("ALTER TABLE roles ADD COLUMN IF NOT EXISTS staff_group VARCHAR"))
    _conn.execute(text("ALTER TABLE roles ADD COLUMN IF NOT EXISTS is_master BOOLEAN NOT NULL DEFAULT FALSE"))
    # Инвентарь строки МП (web/app/cross) — выбор при раздельном прайсе услуги.
    _conn.execute(text("ALTER TABLE sales_media_plan_rows ADD COLUMN IF NOT EXISTS inventory VARCHAR"))
    # Статус-воркфлоу МП: причина отклонения + кто/когда принял решение (approve/reject/archive).
    _conn.execute(text("ALTER TABLE sales_media_plans ADD COLUMN IF NOT EXISTS reject_reason TEXT"))
    _conn.execute(text("ALTER TABLE sales_media_plans ADD COLUMN IF NOT EXISTS decided_by INTEGER"))
    _conn.execute(text("ALTER TABLE sales_media_plans ADD COLUMN IF NOT EXISTS decided_at TIMESTAMPTZ"))
    # Право согласования МП (approve/reject/archive) — новое действие RBAC.
    _conn.execute(text("ALTER TABLE role_permissions ADD COLUMN IF NOT EXISTS can_approve INTEGER DEFAULT 0"))
    # Индекс под выборку непрочитанных уведомлений пользователя.
    _conn.execute(text("CREATE INDEX IF NOT EXISTS ix_notifications_user_unread ON notifications (user_id, is_read, created_at DESC)"))
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


def seed_stage_catalog():
    """Идемпотентно засевает НАШ каталог стадий (E1) из минимального набора CSV.
    Каждая стадия привязана к под-этапу 2/2/2 (STAGE_CATALOG key), из него выводится
    money_layer. Полный сев — только если каталог пуст; иначе бэкфиллит stage_key для
    строк, оставшихся с прошлой (money_layer-только) версии."""
    from app.sales.models import SalesStagePhase, SalesStage
    from app.sales.stages import STAGE_BY_KEY
    CATALOG = [
        ("Песочница", [
            ("МП Подготовка", "media_plan", False),
            ("МП согласование", "media_plan", False),
            ("МП Отправлено", "media_plan", False),
            ("Сделка не случилась", None, True),
        ]),
        ("Услуги", [
            ("Бронь", "booking", False),
            ("Готовятся к старту", "launch_prep", False),
            ("В размещении", "launch", False),
            ("Предварительная сверка", "launch", False),
            ("Сделка сорвалась", None, True),
        ]),
        ("Документооборот (ДО)", [
            ("Подготовка ДС", "closing", False),
            ("Согласование ДС", "closing", False),
            ("Подготовка закрывающих", "closing", False),
            ("ЭДО", "closing", False),
            ("Отчёты в ОРД", "closing", False),
            ("Оплата", "closing", False),
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
    from app.sales.stages import build_stage_index
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


def add_missing_foreign_keys():
    """Внешние ключи — ОТДЕЛЬНО от блока колонок и каждый в своей транзакции.

    ADD CONSTRAINT падает, если в данных есть висячие ссылки. Внутри общего
    `with engine.begin()` такая ошибка отравила бы транзакцию и уронила импорт модуля,
    то есть контейнер не поднялся бы вовсе — цена за недостающий ключ несоразмерна.
    Здесь неудача только пишется в лог: приложение стартует, ключ просто не создан,
    а расчистить висячие ссылки можно спокойно и потом.
    """
    from sqlalchemy import text as _t
    fks = [
        ("sales_deals_our_stage_id_fkey", "sales_deals", "our_stage_id", "sales_stages(id)"),
        ("sales_deals_year_plan_line_id_fkey", "sales_deals", "year_plan_line_id", "sales_year_plan_lines(id)"),
        ("sales_year_plan_lines_plan_id_fkey", "sales_year_plan_lines", "plan_id", "sales_year_plans(id)"),
    ]
    for name, table, col, ref in fks:
        try:
            with engine.begin() as c:
                if c.execute(_t("SELECT 1 FROM pg_constraint WHERE conname = :n"), {"n": name}).first():
                    continue
                c.execute(_t(f"ALTER TABLE {table} ADD CONSTRAINT {name} "
                             f"FOREIGN KEY ({col}) REFERENCES {ref}"))
                logger.info(f"add_missing_foreign_keys: {name} создан")
        except Exception:
            logger.exception(f"add_missing_foreign_keys: {name} не создан — "
                             "вероятно, есть висячие ссылки; старт продолжается")


add_missing_foreign_keys()

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
    Фронт шлёт нейтральный producer_id — здесь возвращаем имя параметра обратно
    в advertiser_id, чтобы эндпоинты/фильтры не меняли (единая точка на бэке)."""
    qs = request.scope.get("query_string", b"")
    if b"producer_id" in qs:
        request.scope["query_string"] = qs.replace(b"producer_id", b"advertiser_id")
    return await call_next(request)


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
app.include_router(media_plans.router, prefix="/api/sales/media-plans", tags=["sales"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(sales_reconcile.router, prefix="/api/sales/reconcile", tags=["sales"])
# Монтируется ПОСЛЕ справочников/сверки, чтобы их префиксы не перехватывались
app.include_router(sales_dashboard.router, prefix="/api/sales", tags=["sales"])
app.include_router(year_plan.router, prefix="/api/sales/year-plan", tags=["sales"])

@app.get("/")
def root():
    return {"status": "ok", "message": "Finance API running"}