"""Балансировщик: расчётная ёмкость площадки на поверхность (показов/мес).

Вкладка «Трафики → Админка → Балансировщик». Согласовано с владельцем 02.09.2026.

Зерно — `(площадка × scope)`, scope ∈ web | app_android | app_ios: веса web и app правятся
отдельно (услуги привязаны к поверхности, объём подключений различается сильно). Строки
разворачиваются из существующих поверхностей площадки (`sales_publisher_surfaces`):
поверхность web даёт одну строку, поверхность app — две (android и ios).

Формула (`index_auto`) — каскад по полноте данных (владелец 30.09.2026, вариант «A + D»):
    A  запросы рекламного кода; если есть и SimilarWeb — зажаты в коридор ×3 от оценки SW
       (Swtraffic × k_sw): выброс в обе стороны правится независимым источником
                                                           → 'ad_requests' / 'req_sw_clamp'
    B  нет запросов, SW полный: Swtraffic × k_sw           → 'similarweb'
    C  нет ни того, ни другого: объём площадки × k_vol (свой для web и app) → 'estimate'
Swtraffic = SW visits × PpV × (100 − BR) / 100. Коэффициенты k НЕ задаются руками: это
медианы отношений «запросы / Swtraffic» и «запросы / объём» по площадкам, где есть оба
числа (самокалибровка; до 30.09 были пустые `balance_k` / `balance_depth_default`).
Глубина в формулу больше не входит — она зашита в калибровку объёма; колонка справочная.
Флаг расхождения — отношение запросов к оценке SW вне ×3: индекс зажат, строка подсвечена.
Действующий индекс = COALESCE(index_manual, index_auto): ручной перекрывает всё, включая
потолок доли в РК (`share_cap`, `flight.capped_shares`). `is_locked` защищает ручную правку.

Площадки в статусе «АРХИВ» игнорируются (решение владельца 02.09.2026) — ни строк, ни пересчёта.
Поверхность попадает в балансировщик, если заведена во вкладке «Настройка блоков» (есть
`ms_publisher_id` или хотя бы один блок) — либо ведётся вне нашей DSP и мы с ней работаем:
у таких блоков нет по определению, а индекс им нужен (30.09.2026, как `build.candidates`).

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

SETTING_K = "balance_k"                    # до 30.09.2026; не читается — k калибруется сам
SETTING_DEPTH = "balance_depth_default"    # до 30.09.2026; не читается
SETTING_CAP = "balance_share_cap"          # потолок доли одной площадки в РК, %
DEFAULT_CAP_PCT = 15.0
# SimilarWeb — замеры web-поверхности в той же таблице, отдельными scope (владелец 30.09.2026)
SW_SCOPES = {"visits": "sw_visits", "ppv": "sw_ppv", "br": "sw_br"}
SW_CORRIDOR = 3.0                          # коридор и порог флага: ×3 от оценки SW


# ── настройки ─────────────────────────────────────────────────────────────

def _num(v) -> Optional[float]:
    try:
        s = str(v).strip().replace(",", ".")
        return float(s) if s else None
    except (TypeError, ValueError):
        return None


def _cap_pct(db: Session) -> float:
    """Потолок доли, %. Не задан — 15 по умолчанию; 0 — без потолка."""
    cap = _num(db.execute(text("SELECT value FROM company_settings WHERE key = :k"),
                          {"k": SETTING_CAP}).scalar())
    return DEFAULT_CAP_PCT if cap is None else cap


def get_coefficients(db: Session, raw: Optional[list] = None) -> dict:
    """Настройки балансировщика: потолок доли (%) и откалиброванные k (для показа).
    `raw` — уже собранные строки, чтобы экран не собирал их дважды."""
    return {"share_cap_pct": _cap_pct(db), **calibrate(_raw_rows(db) if raw is None else raw)}


def set_coefficients(db: Session, share_cap_pct) -> dict:
    v = "" if share_cap_pct in (None, "") else str(share_cap_pct)
    db.execute(text(
        "INSERT INTO company_settings (key, value) VALUES (:k, :v) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"), {"k": SETTING_CAP, "v": v})
    db.commit()
    return get_coefficients(db)


def share_cap(db: Session) -> Optional[float]:
    """Потолок доли для `flight.distribute` — доля 0…1; 0 или пусто = без потолка."""
    pct = _cap_pct(db)          # только настройка: калибровка k здесь не нужна
    return (pct / 100.0) if pct and pct > 0 else None


def manual_scopes(db: Session) -> dict:
    """{площадка: {поверхности с ручным индексом}} — потолок снимается ПО ПОВЕРХНОСТИ
    (владелец 30.09.2026): ручной индекс на app не освобождает web той же площадки."""
    out: dict = {}
    for pid, scope in db.execute(text(
            "SELECT publisher_id, scope FROM publisher_balance_index "
            "WHERE index_manual IS NOT NULL")):
        out.setdefault(pid, set()).add(scope)
    return out


def is_capless(manual: dict, publisher_id, surfaces) -> bool:
    """Свободна ли площадка от потолка в РК с поверхностями `surfaces` (web / app).
    Поверхности сделки неизвестны (нет медиаплана) — смотрим на любую ручную."""
    mine = manual.get(publisher_id) or set()
    if not surfaces:
        return bool(mine)
    return bool(mine & {sc for sc in SCOPES if SCOPE_SURFACE[sc] in set(surfaces)})


def mark_capless(db: Session, placements, surfaces, manual: Optional[dict] = None) -> None:
    """Проставить `capless` строкам размещений (dict с `publisher_id`) перед `distribute`.
    `surfaces` — поверхности сделки РК; `manual` — заранее прочитанный `manual_scopes`,
    чтобы цикл по РК не ходил в базу."""
    manual = manual_scopes(db) if manual is None else manual
    for p in placements:
        p["capless"] = is_capless(manual, p.get("publisher_id"), surfaces)


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

def swtraffic(visits, ppv, br) -> Optional[float]:
    """SW visits × PpV × (100 − BR) / 100; неполные данные — None (не выдумываем)."""
    if not visits or not ppv or br is None:
        return None
    return float(visits) * float(ppv) * (100.0 - float(br)) / 100.0


def _median(xs):
    xs = sorted(x for x in xs if x and x > 0)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def calibrate(raw: list) -> dict:
    """k по площадкам, где есть оба числа: медиана устойчива к выбросам, которые мы и ловим."""
    return {
        "k_sw": _median([r["requests"] / r["sw"] for r in raw if r["requests"] and r["sw"]]),
        "k_vol_web": _median([r["requests"] / r["volume"] for r in raw
                              if r["requests"] and r["volume"] and r["scope"] == "web"]),
        "k_vol_app": _median([r["requests"] / r["volume"] for r in raw
                              if r["requests"] and r["volume"] and r["scope"] != "web"]),
    }


def compute_index(requests, sw, volume, scope: str, k: dict) -> dict:
    """→ {value, source, confidence, flag}. value None = посчитать нечем (честный прочерк)."""
    est = (float(sw) * k["k_sw"]) if (sw and k.get("k_sw")) else None
    if requests:
        req = float(requests)
        if est:
            lo, hi = est / SW_CORRIDOR, est * SW_CORRIDOR
            flag = "high" if req > hi else "low" if req < lo else None
            val = min(max(req, lo), hi)
            return {"value": val, "source": "req_sw_clamp" if flag else "ad_requests",
                    "confidence": "A", "flag": flag}
        return {"value": req, "source": "ad_requests", "confidence": "A", "flag": None}
    if est:
        return {"value": est, "source": "similarweb", "confidence": "B", "flag": None}
    kv = k.get("k_vol_web") if scope == "web" else k.get("k_vol_app")
    if volume and kv:
        return {"value": float(volume) * kv, "source": "estimate", "confidence": "C", "flag": None}
    return {"value": None, "source": None, "confidence": None, "flag": None}


# ── строки балансировщика ─────────────────────────────────────────────────

_SURFACES_SQL = """
    SELECT s.publisher_id, s.kind, s.ms_publisher_id, s.we_work, s.placement_channel,
           p.code, p.name, p.domain, p.has_dsp
    FROM sales_publisher_surfaces s
    JOIN sales_publishers p ON p.id = s.publisher_id
    WHERE p.is_active AND p.status <> :arch AND (
          s.ms_publisher_id IS NOT NULL
          OR EXISTS (SELECT 1 FROM publisher_block b WHERE b.surface_id = s.id)
          OR (s.we_work AND s.placement_channel = ANY(:ext)))
    ORDER BY lower(p.name), s.kind
"""


def _raw_rows(db: Session) -> list:
    """Сырьё строк: поверхность × scope + последние замеры (объём, запросы, SimilarWeb)."""
    from app.launch_prep.pub_rules import EXTERNAL_CHANNELS
    surfaces = db.execute(text(_SURFACES_SQL), {
        "arch": PUBLISHER_ARCHIVE_STATUS, "ext": list(EXTERNAL_CHANNELS)}).mappings().all()
    meas = latest_measurements(db)
    out = []
    for s in surfaces:
        pid = s["publisher_id"]
        for scope in [sc for sc in SCOPES if SCOPE_SURFACE[sc] == s["kind"]]:
            m = meas.get((pid, scope)) or {}
            req = meas.get((pid, REQ_SCOPE[scope])) or {}
            if not req and scope == "web":
                req = meas.get((pid, LEGACY_REQ_SCOPE)) or {}   # унаследованный общий замер
            sw = {k: (meas.get((pid, sc)) or {}).get("value") for k, sc in SW_SCOPES.items()}                 if scope == "web" else {k: None for k in SW_SCOPES}
            out.append({"surface": dict(s), "publisher_id": pid, "scope": scope,
                        "volume": m.get("value"), "depth": m.get("depth"),
                        "measured_at": m.get("measured_at"), "requests": req.get("value"),
                        "sw_visits": sw["visits"], "sw_ppv": sw["ppv"], "sw_br": sw["br"],
                        "sw": swtraffic(sw["visits"], sw["ppv"], sw["br"])})
    return out


def rows(db: Session, raw: Optional[list] = None) -> list:
    """Строка = (площадка × поверхность). Разворачиваем из заведённых поверхностей.
    `raw` — уже собранное сырьё (экран передаёт его и сюда, и в `get_coefficients`)."""
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
    raw = _raw_rows(db) if raw is None else raw
    k = calibrate(raw)
    out = []
    for r in raw:
        s, pid, scope = r["surface"], r["publisher_id"], r["scope"]
        calc = compute_index(r["requests"], r["sw"], r["volume"], scope, k)
        i = idx.get((pid, scope)) or {}
        manual = i.get("index_manual")
        auto = i.get("index_auto") if i else calc["value"]
        out.append({
            "publisher_id": pid, "scope": scope, "scope_label": SCOPE_LABEL[scope],
            "code": s["code"], "name": s["name"], "domain": s["domain"],
            "ms_publisher_id": s["ms_publisher_id"], "we_work": bool(s["we_work"]),
            "has_dsp": bool(s["has_dsp"]), "channel": s["placement_channel"],
            "services": services.get((pid, s["kind"]), []),
            "volume": r["volume"], "depth": r["depth"],
            "measured_at": r["measured_at"].isoformat() if r["measured_at"] else None,
            "requests": r["requests"],
            "sw_visits": r["sw_visits"], "sw_ppv": r["sw_ppv"], "sw_br": r["sw_br"],
            "swtraffic": r["sw"],
            "index_auto": auto, "index_preview": calc["value"], "index_manual": manual,
            "index_effective": manual if manual is not None else auto,
            "source": "manual" if manual is not None else (i.get("source") or calc["source"]),
            "confidence": "ручной" if manual is not None else calc["confidence"],
            "flag": calc["flag"],
            "is_locked": bool(i.get("is_locked")), "note": i.get("note"),
        })
    return out


def recalc(db: Session, user_id: Optional[int] = None) -> dict:
    """Пересчёт index_auto по всем строкам. Запертые (is_locked) не трогаем."""
    idx = {(r["publisher_id"], r["scope"]): dict(r) for r in db.execute(text(
        "SELECT * FROM publisher_balance_index")).mappings().all()}
    raw = _raw_rows(db)
    k = calibrate(raw)
    upd = skipped = empty = 0
    for r in raw:
        pid, scope = r["publisher_id"], r["scope"]
        cur = idx.get((pid, scope))
        if cur and cur.get("is_locked"):
            skipped += 1
            continue
        calc = compute_index(r["requests"], r["sw"], r["volume"], scope, k)
        if calc["value"] is None:
            empty += 1
        db.execute(text("""
            INSERT INTO publisher_balance_index
                (publisher_id, scope, index_auto, source, calculated_at, updated_at, updated_by)
            VALUES (:p, :s, :a, :src, now(), now(), :u)
            ON CONFLICT (publisher_id, scope) DO UPDATE
            SET index_auto = EXCLUDED.index_auto, source = EXCLUDED.source,
                calculated_at = now(), updated_at = now(), updated_by = EXCLUDED.updated_by
        """), {"p": pid, "s": scope, "a": calc["value"], "src": calc["source"], "u": user_id})
        upd += 1
    db.commit()
    return {"updated": upd, "locked_skipped": skipped, "no_data": empty,
            "coefficients": get_coefficients(db), "calculated_at": datetime.utcnow().isoformat()}
