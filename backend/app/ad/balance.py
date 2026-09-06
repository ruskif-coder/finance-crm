"""Балансировщик: расчётная ёмкость площадки на поверхность (показов/мес).

Вкладка «Трафики → Админка → Балансировщик». Согласовано с владельцем 02.09.2026.

Зерно — `(площадка × scope)`, scope ∈ web | app_android | app_ios: веса web и app правятся
отдельно (услуги привязаны к поверхности, объём подключений различается сильно). Строки
разворачиваются из существующих поверхностей площадки (`sales_publisher_surfaces`):
поверхность web даёт одну строку, поверхность app — две (android и ios).

Формула (`index_auto`):
    ёмкость = запросы рекламного кода                                    → source='ad_requests'
            = объём × COALESCE(глубина, balance_depth_default) × balance_k → source='estimate'
Действующий индекс = COALESCE(index_manual, index_auto); `is_locked` защищает ручную правку.

Коэффициенты `balance_k` / `balance_depth_default` живут в `company_settings` и заведены
ПУСТЫМИ: пока владелец их не задал, оценочная ветка НЕ считается (в строке прочерк, а не
выдуманное число). Наблюдаемые 9–23 запроса на уника — всего 2 точки, константу из них не выводим.

Площадки в статусе «АРХИВ» игнорируются (решение владельца 02.09.2026) — ни строк, ни пересчёта.
Поверхность попадает в балансировщик, ТОЛЬКО если заведена во вкладке «Настройка блоков»:
есть `ms_publisher_id` или хотя бы один блок. Иначе строка была бы гарантированно пустой —
у незаведённых поверхностей нет ни подключения к МС, ни инвентаря.

Замеры трафика читаются и пишутся в `sales_publisher_traffic` — те же данные, что в карточке
площадки (правится и там, и здесь). Запросы кода — на поверхность
(`ad_requests_web` / `ad_requests_app_android` / `ad_requests_app_ios`); старый общий
`ad_requests` (замеры до 2026) подхватывается для web как унаследованный.
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.sales.models import PUBLISHER_ARCHIVE_STATUS

SCOPES = ("web", "app_android", "app_ios")
SCOPE_LABEL = {"web": "Web", "app_android": "App Android", "app_ios": "App iOS"}
# поверхность справочника (sales_publisher_surfaces.kind / sales_publisher_services.surface_kind)
SCOPE_SURFACE = {"web": "web", "app_android": "app", "app_ios": "app"}
# scope замера «запросы рекламного кода» для этой поверхности
REQ_SCOPE = {s: f"ad_requests_{s}" if s != "web" else "ad_requests_web" for s in SCOPES}
LEGACY_REQ_SCOPE = "ad_requests"      # общий, до разреза по поверхностям

SETTING_K = "balance_k"
SETTING_DEPTH = "balance_depth_default"


# ── настройки ─────────────────────────────────────────────────────────────

def _num(v) -> Optional[float]:
    try:
        s = str(v).strip().replace(",", ".")
        return float(s) if s else None
    except (TypeError, ValueError):
        return None


def get_coefficients(db: Session) -> dict:
    rows = dict(db.execute(text(
        "SELECT key, value FROM company_settings WHERE key IN (:k, :d)"),
        {"k": SETTING_K, "d": SETTING_DEPTH}).all())
    return {"k": _num(rows.get(SETTING_K)), "depth_default": _num(rows.get(SETTING_DEPTH))}


def set_coefficients(db: Session, k, depth_default) -> dict:
    for key, val in ((SETTING_K, k), (SETTING_DEPTH, depth_default)):
        v = "" if val in (None, "") else str(val)
        db.execute(text(
            "INSERT INTO company_settings (key, value) VALUES (:k, :v) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"), {"k": key, "v": v})
    db.commit()
    return get_coefficients(db)


# ── замеры ────────────────────────────────────────────────────────────────

def month_start(d: Optional[date] = None) -> date:
    d = d or date.today()
    return d.replace(day=1)


def latest_measurements(db: Session) -> dict:
    """Последний замер по каждой паре (площадка, scope) — из sales_publisher_traffic."""
    rows = db.execute(text("""
        SELECT DISTINCT ON (publisher_id, scope) publisher_id, scope, value, depth, measured_at
        FROM sales_publisher_traffic
        ORDER BY publisher_id, scope, measured_at DESC
    """)).mappings().all()
    return {(r["publisher_id"], r["scope"]): dict(r) for r in rows}


def upsert_measurement(db: Session, publisher_id: int, scope: str, value, depth=None,
                       measured_at: Optional[date] = None, source: str = "manual") -> None:
    """Замер за месяц: повторный ввод ИСПРАВЛЯЕТ (уникум publisher+scope+measured_at)."""
    if value is None and depth is None:
        return
    db.execute(text("""
        INSERT INTO sales_publisher_traffic (publisher_id, scope, value, depth, measured_at, source)
        VALUES (:p, :s, :v, :d, :m, :src)
        ON CONFLICT (publisher_id, scope, measured_at)
        DO UPDATE SET value = COALESCE(EXCLUDED.value, sales_publisher_traffic.value),
                      depth = COALESCE(EXCLUDED.depth, sales_publisher_traffic.depth),
                      source = EXCLUDED.source
    """), {"p": publisher_id, "s": scope, "v": value, "d": depth,
           "m": measured_at or month_start(), "src": source})


# ── формула ───────────────────────────────────────────────────────────────

def compute_index(volume, depth, requests, k, depth_default):
    """→ (ёмкость, источник). None-ёмкость = посчитать нечем (честный прочерк)."""
    if requests:
        return float(requests), "ad_requests"
    if volume and k:
        d = depth if depth else depth_default
        if d:
            return float(volume) * float(d) * float(k), "estimate"
    return None, None


# ── строки балансировщика ─────────────────────────────────────────────────

def rows(db: Session) -> list:
    """Строка = (площадка × поверхность). Разворачиваем из заведённых поверхностей."""
    surfaces = db.execute(text("""
        SELECT s.publisher_id, s.kind, s.ms_publisher_id, s.we_work,
               p.code, p.name, p.domain, p.has_dsp
        FROM sales_publisher_surfaces s
        JOIN sales_publishers p ON p.id = s.publisher_id
        WHERE p.is_active AND p.status <> :arch AND (
              s.ms_publisher_id IS NOT NULL
              OR EXISTS (SELECT 1 FROM publisher_block b WHERE b.surface_id = s.id))
        ORDER BY lower(p.name), s.kind
    """), {"arch": PUBLISHER_ARCHIVE_STATUS}).mappings().all()

    services = {}
    for r in db.execute(text("""
        SELECT ps.publisher_id, ps.surface_kind, sv.name
        FROM sales_publisher_services ps
        JOIN sales_services sv ON sv.id = ps.service_id
        WHERE ps.is_active ORDER BY sv.name
    """)).mappings().all():
        services.setdefault((r["publisher_id"], r["surface_kind"]), []).append(r["name"])

    idx = {(r["publisher_id"], r["scope"]): dict(r) for r in db.execute(text(
        "SELECT * FROM publisher_balance_index")).mappings().all()}
    meas = latest_measurements(db)
    coef = get_coefficients(db)

    out = []
    for s in surfaces:
        pid = s["publisher_id"]
        for scope in [sc for sc in SCOPES if SCOPE_SURFACE[sc] == s["kind"]]:
            m = meas.get((pid, scope)) or {}
            req = meas.get((pid, REQ_SCOPE[scope])) or {}
            if not req and scope == "web":
                req = meas.get((pid, LEGACY_REQ_SCOPE)) or {}   # унаследованный общий замер
            i = idx.get((pid, scope)) or {}
            auto, src = compute_index(m.get("value"), m.get("depth"), req.get("value"),
                                      coef["k"], coef["depth_default"])
            manual = i.get("index_manual")
            out.append({
                "publisher_id": pid, "scope": scope, "scope_label": SCOPE_LABEL[scope],
                "code": s["code"], "name": s["name"], "domain": s["domain"],
                "ms_publisher_id": s["ms_publisher_id"], "we_work": bool(s["we_work"]),
                "has_dsp": bool(s["has_dsp"]),
                "services": services.get((pid, s["kind"]), []),
                "volume": m.get("value"), "depth": m.get("depth"),
                "measured_at": (m.get("measured_at").isoformat() if m.get("measured_at") else None),
                "requests": req.get("value"),
                "index_auto": i.get("index_auto") if i else auto,
                "index_preview": auto, "index_manual": manual,
                "index_effective": manual if manual is not None else (i.get("index_auto") if i else auto),
                "source": ("manual" if manual is not None else (i.get("source") or src)),
                "is_locked": bool(i.get("is_locked")), "note": i.get("note"),
            })
    return out


def recalc(db: Session, user_id: Optional[int] = None) -> dict:
    """Пересчёт index_auto по всем строкам. Запертые (is_locked) не трогаем."""
    coef = get_coefficients(db)
    meas = latest_measurements(db)
    idx = {(r["publisher_id"], r["scope"]): dict(r) for r in db.execute(text(
        "SELECT * FROM publisher_balance_index")).mappings().all()}
    surfaces = db.execute(text(
        "SELECT s.publisher_id, s.kind FROM sales_publisher_surfaces s "
        "JOIN sales_publishers p ON p.id = s.publisher_id "
        "WHERE p.is_active AND p.status <> :arch AND ("
        "  s.ms_publisher_id IS NOT NULL"
        "  OR EXISTS (SELECT 1 FROM publisher_block b WHERE b.surface_id = s.id))"),
        {"arch": PUBLISHER_ARCHIVE_STATUS}).mappings().all()

    upd = skipped = empty = 0
    for s in surfaces:
        pid = s["publisher_id"]
        for scope in [sc for sc in SCOPES if SCOPE_SURFACE[sc] == s["kind"]]:
            cur = idx.get((pid, scope))
            if cur and cur.get("is_locked"):
                skipped += 1
                continue
            m = meas.get((pid, scope)) or {}
            req = meas.get((pid, REQ_SCOPE[scope])) or {}
            if not req and scope == "web":
                req = meas.get((pid, LEGACY_REQ_SCOPE)) or {}
            auto, src = compute_index(m.get("value"), m.get("depth"), req.get("value"),
                                      coef["k"], coef["depth_default"])
            if auto is None:
                empty += 1
            db.execute(text("""
                INSERT INTO publisher_balance_index
                    (publisher_id, scope, index_auto, source, calculated_at, updated_at, updated_by)
                VALUES (:p, :s, :a, :src, now(), now(), :u)
                ON CONFLICT (publisher_id, scope) DO UPDATE
                SET index_auto = EXCLUDED.index_auto, source = EXCLUDED.source,
                    calculated_at = now(), updated_at = now(), updated_by = EXCLUDED.updated_by
            """), {"p": pid, "s": scope, "a": auto, "src": src, "u": user_id})
            upd += 1
    db.commit()
    return {"updated": upd, "locked_skipped": skipped, "no_data": empty,
            "coefficients": coef, "calculated_at": datetime.utcnow().isoformat()}
