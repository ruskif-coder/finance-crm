"""Контур «Траффики» → Админка → вкладка «Балансировщик».

Расчётная ёмкость площадки на поверхность (показов/мес) + ввод замеров трафика с листа.
Разбор формулы и зерна строки — в `app/ad/balance.py`. Замеры пишутся в
`sales_publisher_traffic` — те же данные, что в карточке площадки: правятся и там, и здесь.

Право то же, что у каталога блоков — `traffic_catalog` (общая админка трафика), поэтому
отдельного ключа НЕ заводим: раздача доступа к двум вкладкам одна.
Монтируется тем же префиксом `/api/traffic-catalog`.
"""
import io
import logging
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ad import balance, build
from app.audit import log_action
from app.database import get_db
from app.models import User
from app.permissions import require_permission
from app.sales.models import PUBLISHER_ARCHIVE_STATUS, SalesPublisher

router = APIRouter()
log = logging.getLogger(__name__)


def _push_to_campaigns(db):
    """Индекс — сразу в незавершённые РК: веса площадок и их объёмы (владелец 27.09.2026).

    Зовётся ПОСЛЕ коммита индекса и после записи в журнал: сбой пересчёта РК не должен
    выглядеть как «индекс не сохранён» (он сохранён) и не должен терять запись журнала.
    Не пересчиталось сейчас — догонит ночной `app.ad.daily_shares`.
    """
    try:
        build.refresh_weights(db)
        return True
    except Exception:  # noqa: BLE001 — индекс сохранён, РК догонит ночной пересчёт
        db.rollback()
        log.exception("балансировщик: пересчёт РК после правки индекса не удался")
        return False

VIEW = require_permission("traffic_catalog", "view")
EDIT = require_permission("traffic_catalog", "edit")


class BalanceRowIn(BaseModel):
    volume: Optional[float] = None          # объём замера поверхности
    depth: Optional[float] = None           # глубина просмотра
    requests: Optional[float] = None        # запросы рекламного кода
    index_manual: Optional[float] = None    # ручная правка индекса
    is_locked: Optional[bool] = None        # не перетирать пересчётом
    note: Optional[str] = None
    # SimilarWeb (только web, владелец 30.09.2026) — заменили «Внешнюю оценку»;
    # колонка `external_score` заморожена: не читается и не пишется.
    sw_visits: Optional[float] = None
    sw_ppv: Optional[float] = None
    sw_br: Optional[float] = None


class CoefficientsIn(BaseModel):
    share_cap_pct: Optional[float] = None   # потолок доли одной площадки в РК, %


# ── чтение и правка ───────────────────────────────────────────────────────

@router.get("/balancer")
def balancer_rows(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    raw = balance._raw_rows(db)
    return {"rows": balance.rows(db, raw), "coefficients": balance.get_coefficients(db, raw),
            "month": balance.month_start().isoformat()}


@router.put("/balancer/row/{publisher_id}/{scope}")
def balancer_save_row(publisher_id: int, scope: str, payload: BalanceRowIn,
                      db: Session = Depends(get_db), user: User = Depends(EDIT)):
    if scope not in balance.SCOPES:
        raise HTTPException(400, f"Поверхность бывает {balance.SCOPES}")
    if not db.query(SalesPublisher).get(publisher_id):
        raise HTTPException(404, "Площадка не найдена")

    if payload.volume is not None or payload.depth is not None:
        balance.upsert_measurement(db, publisher_id, scope, payload.volume, payload.depth)
    if payload.requests is not None:
        balance.upsert_measurement(db, publisher_id, balance.REQ_SCOPE[scope], payload.requests)
    _save_sw(db, publisher_id, scope, payload.sw_visits, payload.sw_ppv, payload.sw_br)

    db.execute(text("""
        INSERT INTO publisher_balance_index
            (publisher_id, scope, index_manual, is_locked, note, updated_at, updated_by)
        VALUES (:p, :s, :im, COALESCE(:lk, FALSE), :n, now(), :u)
        ON CONFLICT (publisher_id, scope) DO UPDATE
        SET index_manual = EXCLUDED.index_manual,
            is_locked = COALESCE(:lk, publisher_balance_index.is_locked),
            note = EXCLUDED.note, updated_at = now(), updated_by = EXCLUDED.updated_by
    """), {"p": publisher_id, "s": scope, "im": payload.index_manual,
           "lk": payload.is_locked, "n": payload.note, "u": user.id})
    db.commit()
    log_action(db, user, "balancer_row_edit", "sales_publisher", publisher_id,
               f"{scope}: объём={payload.volume} глубина={payload.depth} "
               f"запросы={payload.requests} индекс_рука={payload.index_manual} "
               f"SW={payload.sw_visits}/{payload.sw_ppv}/{payload.sw_br}")
    pushed = _push_to_campaigns(db)
    return {"ok": True, "campaigns_updated": pushed, "rows": balance.rows(db)}


@router.post("/balancer/recalc")
def balancer_recalc(db: Session = Depends(get_db), user: User = Depends(EDIT)):
    res = balance.recalc(db, user.id)
    log_action(db, user, "balancer_recalc", "sales_publisher", None,
               f"пересчёт индексов: {res['updated']}, заперто {res['locked_skipped']}, "
               f"без данных {res['no_data']}")
    pushed = _push_to_campaigns(db)
    return {**res, "campaigns_updated": pushed, "rows": balance.rows(db)}


@router.put("/balancer/settings")
def balancer_settings(payload: CoefficientsIn, db: Session = Depends(get_db),
                      user: User = Depends(EDIT)):
    if payload.share_cap_pct is not None and not (0 <= payload.share_cap_pct <= 100):
        raise HTTPException(400, "Потолок доли — от 0 до 100 %; 0 — без потолка")
    coef = balance.set_coefficients(db, payload.share_cap_pct)
    log_action(db, user, "balancer_settings", "sales_publisher", None,
               f"потолок доли площадки в РК = {coef['share_cap_pct']} %")
    pushed = _push_to_campaigns(db)
    return {"coefficients": coef, "campaigns_updated": pushed, "rows": balance.rows(db)}


def _save_sw(db, publisher_id: int, scope: str, visits, ppv, br, source: str = "manual") -> None:
    """SimilarWeb — замеры web-поверхности месяца; у app их нет по природе источника."""
    vals = {"visits": visits, "ppv": ppv, "br": br}
    if all(v is None for v in vals.values()):
        return
    if scope != "web":
        raise HTTPException(400, "SimilarWeb бывает только у web-поверхности")
    for k, v in vals.items():
        if v is not None:
            if v < 0 or (k == "br" and v > 100):
                raise HTTPException(400, "SW: визиты и PpV ≥ 0, BR — от 0 до 100")
            balance.upsert_measurement(db, publisher_id, balance.SW_SCOPES[k], v, source=source)


# ── Excel: выгрузка и загрузка ────────────────────────────────────────────

BALANCE_COLS = [
    ("publisher_id", "ID"), ("scope", "Поверхность (код)"), ("code", "Наш код"),
    ("name", "Площадка"), ("domain", "Домен"), ("ms_publisher_id", "ID в МС"),
    ("scope_label", "Поверхность"), ("services", "Услуги"),
    ("volume", "Объём"), ("depth", "Глубина"), ("requests", "Запросы кода"),
    ("sw_visits", "SW visits"), ("sw_ppv", "PpV"), ("sw_br", "BR"), ("swtraffic", "Swtraffic"),
    ("index_auto", "Индекс расчётный"), ("index_manual", "Индекс ручной"),
    ("source", "Источник"), ("confidence", "Доверие"), ("is_locked", "Заперт"),
    ("note", "Примечание"),
]
# Импортом правятся только эти; остальные колонки справочные (из каталога паблишеров).
BALANCE_EDITABLE = ("volume", "depth", "requests", "sw_visits", "sw_ppv", "sw_br",
                    "index_manual", "is_locked", "note")

BLOCK_COLS = [("publisher", "Площадка"), ("code", "Наш код"), ("surface", "Поверхность"),
              ("platform", "Платформа"), ("ms_publisher_id", "ID паблишера в МС"), ("ms_block_id", "ID блока"),
              ("name", "Название в xoalt"), ("page_type", "Раздел"),
              ("network", "Сеть"), ("is_active", "Активен")]


def _xlsx(sheet_title: str, headers: List[str], rows: List[list]) -> bytes:
    import openpyxl
    from openpyxl.styles import Font
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append(r)
    ws.freeze_panes = "A2"
    for i, h in enumerate(headers, start=1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = max(10, min(38, len(str(h)) + 6))
    buf = io.BytesIO()
    from app.xlsx_safe import save_workbook   # формулы только наши (аудит, 1.L7)
    save_workbook(wb, buf)
    return buf.getvalue()


def _xlsx_response(data: bytes, filename: str) -> Response:
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(" ", "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


@router.get("/balancer/export")
def balancer_export(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    out = []
    for r in balance.rows(db):
        row = []
        for k, _ in BALANCE_COLS:
            if k == "services":
                row.append(", ".join(r["services"]))
            elif k == "is_locked":
                row.append("да" if r[k] else "")
            else:
                row.append(r.get(k))
        out.append(row)
    return _xlsx_response(_xlsx("Балансировщик", [t for _, t in BALANCE_COLS], out),
                          "Балансировщик.xlsx")


@router.post("/balancer/import")
def balancer_import(file: UploadFile = File(...), db: Session = Depends(get_db),
                    user: User = Depends(EDIT)):
    """Загрузка правок из выгруженного файла. Ключ строки — колонки «ID» и «Поверхность (код)»;
    берём только редактируемые поля, справочные колонки игнорируем."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(file.file.read()), data_only=True)
    ws = wb.active
    head = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]
    title_to_key = {t: k for k, t in BALANCE_COLS}
    pos = {title_to_key[t]: i for i, t in enumerate(head) if t in title_to_key}
    if "publisher_id" not in pos or "scope" not in pos:
        raise HTTPException(400, "В файле нет колонок «ID» и «Поверхность (код)» — "
                                 "загружайте файл, полученный выгрузкой")

    applied = skipped = 0
    valid_ids = {r[0] for r in db.execute(text("SELECT id FROM sales_publishers"))}
    for row in ws.iter_rows(min_row=2, values_only=True):
        def cell(key, _row=row):
            i = pos.get(key)
            return _row[i] if i is not None and i < len(_row) else None

        pid, scope = cell("publisher_id"), cell("scope")
        if not pid or scope not in balance.SCOPES:
            skipped += 1
            continue
        # Текст, дробь, «inf», ноль или чужой id в колонке ID — ряд пропускаем, а не роняем
        # весь файл 500-й и не пишем в чужую площадку (аудит 01.10.2026, С-11).
        try:
            f = float(str(pid).strip())
        except (ValueError, OverflowError):
            f = 0.0
        if not f.is_integer() or f <= 0 or int(f) not in valid_ids:
            skipped += 1
            continue
        pid = int(f)
        vol, dep, req = _num(cell("volume")), _num(cell("depth")), _num(cell("requests"))
        if vol is not None or dep is not None:
            balance.upsert_measurement(db, pid, scope, vol, dep, source="import")
        if req is not None:
            balance.upsert_measurement(db, pid, balance.REQ_SCOPE[scope], req, source="import")
        if scope == "web":
            _save_sw(db, pid, scope, _num(cell("sw_visits")), _num(cell("sw_ppv")),
                     _num(cell("sw_br")), source="import")
        locked_raw = str(cell("is_locked") or "").strip().lower()
        db.execute(text("""
            INSERT INTO publisher_balance_index
                (publisher_id, scope, index_manual, is_locked, note, updated_at, updated_by)
            VALUES (:p, :s, :im, :lk, :n, now(), :u)
            ON CONFLICT (publisher_id, scope) DO UPDATE
            SET index_manual = EXCLUDED.index_manual, is_locked = EXCLUDED.is_locked,
                note = EXCLUDED.note, updated_at = now(), updated_by = EXCLUDED.updated_by
        """), {"p": pid, "s": scope, "im": _num(cell("index_manual")),
               "lk": locked_raw in ("да", "yes", "true", "1", "y"),
               "n": (cell("note") or None), "u": user.id})
        applied += 1
    db.commit()
    log_action(db, user, "balancer_import", "sales_publisher", None,
               f"импорт балансировщика: применено {applied}, пропущено {skipped}")
    pushed = _push_to_campaigns(db)
    return {"applied": applied, "skipped": skipped, "campaigns_updated": pushed,
            "rows": balance.rows(db)}


@router.get("/blocks/export")
def blocks_export(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    rows = db.execute(text("""
        SELECT p.name AS publisher, p.code, s.kind AS surface, b.platform, s.ms_publisher_id,
               b.ms_block_id, b.name, b.page_type, b.network, b.is_active
        FROM publisher_block b
        JOIN sales_publisher_surfaces s ON s.id = b.surface_id
        JOIN sales_publishers p ON p.id = b.publisher_id
        WHERE p.status <> :arch
        ORDER BY lower(p.name), s.kind, b.platform NULLS LAST, b.page_type, b.ms_block_id
    """), {"arch": PUBLISHER_ARCHIVE_STATUS}).mappings().all()
    out = [[("да" if r["is_active"] else "") if k == "is_active" else r[k]
            for k, _ in BLOCK_COLS] for r in rows]
    return _xlsx_response(_xlsx("Блоки", [t for _, t in BLOCK_COLS], out), "Каталог блоков.xlsx")


# ── Доступность сайтов площадок (владелец 30.09.2026) ────────────────────────
# Вкладка админки трафика; правила и проверка — `app/traffic/site_monitor.py`.

class SiteSettingsIn(BaseModel):
    extra: Optional[str] = None          # доп. сайты: строка — адрес [browser]
    dsp_exclude: Optional[str] = None    # исключения «пропали из показов», строка — домен


class SiteModeIn(BaseModel):
    site_check: str                      # http | browser | off


class SiteRunIn(BaseModel):
    url: Optional[str] = None            # один адрес; пусто — все


def _site_rows(db: Session) -> list:
    from app.traffic import site_monitor as sm
    last, hist = sm.latest(db), sm.history(db)
    rows = []
    for t in sm.targets(db):
        c = last.get(t["url"]) or {}
        rows.append({**t, "status": c.get("status"), "http_status": c.get("http_status"),
                     "method": c.get("method"), "final_url": c.get("final_url"),
                     "message": c.get("message"), "checked_at": c.get("checked_at"),
                     "since": c.get("since"), "streak": c.get("streak"),
                     "history": hist.get(t["url"], [])})
    # Выключенные из проверки площадки реестра — тоже строкой, чтобы их можно было включить.
    off = db.execute(text("""
        SELECT DISTINCT ON (p.id) p.id, p.name, p.domain FROM sales_publisher_surfaces s
          JOIN sales_publishers p ON p.id = s.publisher_id
         WHERE s.kind = 'web' AND s.site_check = 'off' AND p.status <> :arch
         ORDER BY p.id"""), {"arch": PUBLISHER_ARCHIVE_STATUS}).mappings().all()
    for r in off:
        rows.append({"url": sm.site_url(r["domain"]), "mode": "off", "publisher_id": r["id"],
                     "name": r["name"], "status": None, "history": []})
    for line in sm._setting(db, sm.SETTING_EXTRA).splitlines():
        raw = line.split()
        if line.strip().startswith("#") and len(raw) > 1 and sm.site_url(raw[1]):
            rows.append({"url": sm.site_url(raw[1]), "mode": "off", "publisher_id": None,
                         "name": raw[1].split("://")[-1], "status": None, "history": []})
    return rows


def _log_rows(db: Session, system: str, limit: int, only_errors: bool, deal: Optional[str],
              prod_only: bool, full: bool = False) -> list:
    """Строки лога для экрана и для скачивания. `limit` 0 — все (владелец 01.10.2026:
    «500 / 1000 / все»)."""
    from app.traffic import logs
    lim = None if int(limit) <= 0 else int(limit)
    deal = (deal or "").strip() or None
    if system == "dsp":
        try:
            return logs.dsp_rows(db, lim, only_errors, deal, prod_only=prod_only, full=full)
        except Exception as e:  # noqa: BLE001 — журнал в другой базе; её недоступность не 500
            raise HTTPException(503, f"Журнал DSP недоступен: {e.__class__.__name__}")
    if system == "weborama":
        return logs.wr_rows(db, lim, only_errors, deal, full=full)
    raise HTTPException(400, "system: dsp | weborama")


@router.get("/logs")
def exchange_logs(system: str = "dsp", limit: int = 500, only_errors: bool = False,
                  deal: Optional[str] = None, prod_only: bool = True, db: Session = Depends(get_db),
                  user: User = Depends(VIEW)):
    """Вкладка «Логи» (владелец 01.10.2026): обмен с DSP или Weborama, каждая строка —
    сделка + площадка + креатив. Право — то же, что у админки трафика."""
    return {"system": system,
            "rows": _log_rows(db, system, limit, only_errors, deal, prod_only)}


@router.get("/logs/download")
def exchange_logs_download(system: str = "dsp", limit: int = 500, only_errors: bool = False,
                           deal: Optional[str] = None, prod_only: bool = True,
                           db: Session = Depends(get_db), user: User = Depends(VIEW)):
    """Тот же отбор, что на экране, — текстом, тела целиком, старые сверху."""
    import re
    from datetime import datetime
    from fastapi.responses import Response
    from app.traffic import logs
    rows = _log_rows(db, system, limit, only_errors, deal, prod_only, full=True)
    tag = re.sub(r"[^A-Z0-9]", "", (deal or "").upper())[:12] or "all"
    name = f"log_{system}_{tag}_{datetime.utcnow():%Y-%m-%d_%H%M}.txt"
    return Response(logs.as_text(system, rows), media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/site-monitor")
def site_monitor_rows(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    from app.traffic import site_monitor as sm
    return {"rows": _site_rows(db), "dsp": sm.dsp_state(db),
            "extra": sm._setting(db, sm.SETTING_EXTRA),
            "dsp_exclude": sm._setting(db, sm.SETTING_DSP_EXCLUDE)}


@router.post("/site-monitor/run")
def site_monitor_run(payload: SiteRunIn, background: BackgroundTasks,
                     db: Session = Depends(get_db), user: User = Depends(EDIT)):
    """Проверить сейчас. Один адрес — сразу; все — в фоне (проверка браузером медленная,
    на три десятка сайтов уходят минуты), экран перечитает список."""
    from app.traffic import site_monitor as sm
    if payload.url:
        if payload.url not in {t["url"] for t in sm.targets(db)}:
            raise HTTPException(404, "Такого сайта в списке проверки нет")
        res = sm.run(db, only_url=payload.url)
        return {"counts": res, "rows": _site_rows(db)}

    def _bg():
        from app.database import SessionLocal
        s = SessionLocal()
        try:
            sm.run(s)
        finally:
            s.close()
    background.add_task(_bg)
    log_action(db, user, "site_monitor_run", "sales_publisher", None, "проверка всех сайтов")
    return {"started": True}


@router.put("/site-monitor/settings")
def site_monitor_settings(payload: SiteSettingsIn, db: Session = Depends(get_db),
                          user: User = Depends(EDIT)):
    from app.traffic import site_monitor as sm
    for key, val in ((sm.SETTING_EXTRA, payload.extra), (sm.SETTING_DSP_EXCLUDE, payload.dsp_exclude)):
        if val is None:
            continue
        if len(val) > 5000:
            raise HTTPException(400, "Список длиннее 5000 символов")
        db.execute(text("INSERT INTO company_settings (key, value) VALUES (:k, :v) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"),
                   {"k": key, "v": val.strip()})
    db.commit()
    log_action(db, user, "site_monitor_settings", "sales_publisher", None,
               "списки доп. сайтов / исключений обновлены")
    return site_monitor_rows(db=db, user=user)


class SiteExtraModeIn(BaseModel):
    url: str
    site_check: str                      # http | browser | off


@router.put("/site-monitor/extra-mode")
def site_monitor_extra_mode(payload: SiteExtraModeIn, db: Session = Depends(get_db),
                            user: User = Depends(EDIT)):
    """Режим доп. сайта вне реестра: переписываем его строку в списке настроек
    («адрес» / «адрес browser»; «не проверять» — строка закомментирована `#`)."""
    from app.traffic import site_monitor as sm
    if payload.site_check not in ("http", "browser", "off"):
        raise HTTPException(400, "Режим проверки: http, browser или off")
    lines, hit = [], False
    for line in sm._setting(db, sm.SETTING_EXTRA).splitlines():
        raw = line.lstrip("#").split()
        if raw and sm.site_url(raw[0]) == payload.url:
            hit = True
            line = ("# " if payload.site_check == "off" else "") + raw[0] + (
                " browser" if payload.site_check == "browser" else "")
        lines.append(line)
    if not hit:
        raise HTTPException(404, "Такого доп. сайта в списке нет")
    db.execute(text("INSERT INTO company_settings (key, value) VALUES (:k, :v) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"),
               {"k": sm.SETTING_EXTRA, "v": chr(10).join(lines)})
    db.commit()
    log_action(db, user, "site_monitor_mode", "sales_publisher", None,
               f"доп. сайт {payload.url}: {payload.site_check}")
    return site_monitor_rows(db=db, user=user)


@router.put("/site-monitor/publisher/{publisher_id}")
def site_monitor_mode(publisher_id: int, payload: SiteModeIn, db: Session = Depends(get_db),
                      user: User = Depends(EDIT)):
    if payload.site_check not in ("http", "browser", "off"):
        raise HTTPException(400, "Режим проверки: http, browser или off")
    n = db.execute(text("""UPDATE sales_publisher_surfaces SET site_check = :m
                            WHERE publisher_id = :p AND kind = 'web'"""),
                   {"m": payload.site_check, "p": publisher_id}).rowcount
    if not n:
        raise HTTPException(404, "У площадки нет web-поверхности")
    db.commit()
    log_action(db, user, "site_monitor_mode", "sales_publisher", publisher_id,
               f"проверка сайта: {payload.site_check}")
    return {"rows": _site_rows(db)}
