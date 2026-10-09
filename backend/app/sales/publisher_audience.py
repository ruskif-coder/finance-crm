# -*- coding: utf-8 -*-
"""«Паблишеры → Аудитория»: заявленное площадкой рядом с измеренным нами.

Две половины намеренно разного происхождения:

* **заявлено** — `sales_publisher_audience` (миграция 2026-10-09_publisher_audience.sql):
  замеры с датой и источником, по каждой метрике берётся последний по `measured_at`;
* **подтверждено нами** — считается из `ad_campaign_stat` за окно и нигде не хранится.
  Показы — ТОЛЬКО наш счётчик (`stat_sources.OWN`); верификатор — отдельная цифра
  (решение владельца 10.09.2026, прибор tests/test_stat_sources.py).

Что из «подтверждённого» честно, а что оценка:
* `uniques` — сумма СУТОЧНЫХ уников Adfox: один человек за 30 дней посчитан столько раз,
  сколько дней заходил. Это верхняя оценка охвата, и экран обязан так её и подписывать.
  Weborama `reach_impression` в базу не пишется (стат-съём хранит показы/клики) — когда
  появится, охват станет измеренным, а не оценочным.
* `fill_pct` — показы DSP / предложено DSP; только по строкам, где `offered` известно.
"""
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.orm import Session

from app.ad.stat_sources import OWN, VERIFIER
from app.database import Base
from app import models as _core_models  # noqa: F401 — FK на users/sales_publishers требуют зарегистрированных таблиц
from app.sales import models as _sales_models  # noqa: F401

# Каталог метрик — закрытый: экран рисует подписи по нему, фильтр «подобрать под бриф»
# будет считать по нему же. Доли (`share`) — в процентах, с сегментом.
METRICS = {
    "mau":       {"label": "MAU",            "unit": "чел.",  "kind": "count"},
    "dau":       {"label": "DAU",            "unit": "чел.",  "kind": "count"},
    "wau":       {"label": "WAU",            "unit": "чел.",  "kind": "count"},
    "sessions":  {"label": "Визиты / мес.",  "unit": "шт.",   "kind": "count"},
    "installs":  {"label": "Установки",      "unit": "шт.",   "kind": "count"},
    "share":     {"label": "Доля сегмента",  "unit": "%",     "kind": "share"},
    "affinity":  {"label": "Affinity",       "unit": "индекс", "kind": "index"},
    "avg_time":  {"label": "Время сессии",   "unit": "мин.",  "kind": "count"},
}
SURFACES = (None, "web", "app")


class SalesPublisherAudience(Base):
    __tablename__ = "sales_publisher_audience"
    id = Column(Integer, primary_key=True)
    publisher_id = Column(Integer, ForeignKey("sales_publishers.id", ondelete="CASCADE"), nullable=False)
    surface_kind = Column(String(8))
    metric = Column(String(32), nullable=False)
    segment = Column(String(64))
    value = Column(Numeric(18, 4), nullable=False)
    source = Column(String(64), nullable=False)
    measured_at = Column(Date, nullable=False)
    note = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, server_default=func.now())


# Поля, которые заводятся руками и через Excel: (ключ в `declared`, подпись колонки, метрика,
# поверхность, сегмент). Один каталог на сетку экрана, выгрузку и загрузку — иначе подписи
# колонок Excel и поля сетки разойдутся, и файл перестанет читаться обратно.
FIELDS = [
    ("mau", "MAU", "mau", None, None),
    ("dau", "DAU", "dau", None, None),
    ("wau", "WAU", "wau", None, None),
    ("avg_time", "Время сессии, мин", "avg_time", None, None),
    ("mau@web", "MAU web", "mau", "web", None),
    ("mau@app", "MAU app", "mau", "app", None),
    ("installs@app", "Установки app", "installs", "app", None),
    ("share:Ж", "Доля Ж, %", "share", None, "Ж"),
    ("share:25–54", "Доля 25–54, %", "share", None, "25–54"),
    ("share:Москва и МО", "Доля Москва и МО, %", "share", None, "Москва и МО"),
    ("share:доход B+", "Доля доход B+, %", "share", None, "доход B+"),
    ("affinity:фарма", "Affinity фарма", "affinity", None, "фарма"),
    ("affinity:FMCG", "Affinity FMCG", "affinity", None, "FMCG"),
]
FIELD_BY_KEY = {f[0]: f for f in FIELDS}
FIELD_BY_LABEL = {f[1]: f for f in FIELDS}
PCT_METRICS = {"share"}


# Поля, которые в системе УЖЕ ЕСТЬ у площадки (карточка площадки, балансировщик) и на этом экране
# не заводятся заново, а привязаны к тем же таблицам (владелец 09.10.2026): замеры трафика
# `sales_publisher_traffic` (месяц, перезаписываются как в карточке) и покрытие поверхности
# `sales_publisher_surfaces.coverage_percent`. Ключ: (подпись, тип, scope/поверхность, колонка).
SYS_FIELDS = [
    ("tr:web", "Визиты WEB в мес", "traffic", "web", "value"),
    ("tr:web_depth", "Глубина WEB", "traffic", "web", "depth"),
    ("tr:app_android", "Визиты APP Android в мес", "traffic", "app_android", "value"),
    ("tr:app_ios", "Визиты APP iOS в мес", "traffic", "app_ios", "value"),
    ("tr:sw_visits", "SimilarWeb visits", "traffic", "sw_visits", "value"),
    ("tr:sw_ppv", "SimilarWeb страниц за визит", "traffic", "sw_ppv", "value"),
    ("tr:sw_br", "SimilarWeb отказы, %", "traffic", "sw_br", "value"),
    ("tr:ad_requests_web", "Запросы кода web", "traffic", "ad_requests_web", "value"),
    ("tr:ad_requests_app_android", "Запросы кода app Android", "traffic", "ad_requests_app_android", "value"),
    ("tr:ad_requests_app_ios", "Запросы кода app iOS", "traffic", "ad_requests_app_ios", "value"),
    ("cov:web", "Покрытие web, %", "coverage", "web", "coverage_percent"),
    ("cov:app", "Покрытие app, %", "coverage", "app", "coverage_percent"),
]
SYS_BY_KEY = {f[0]: f for f in SYS_FIELDS}
SYS_BY_LABEL = {f[1]: f for f in SYS_FIELDS}
SOURCE_SYSTEM = "карточка площадки"
PCT_SYS = {"tr:sw_br", "cov:web", "cov:app"}


def label_of(key: str) -> str:
    return (FIELD_BY_KEY.get(key) or SYS_BY_KEY[key])[1]


def check_metric(metric: str) -> str:
    if metric not in METRICS:
        raise ValueError(f"Неизвестная метрика «{metric}». Допустимые: {', '.join(METRICS)}")
    return metric


def add_measure(db: Session, publisher_id: int, *, metric: str, value: float, source: str,
                measured_at: date, surface_kind: Optional[str], segment: Optional[str],
                note: Optional[str], user_id: Optional[int]) -> SalesPublisherAudience:
    check_metric(metric)
    if surface_kind not in SURFACES:
        raise ValueError("Поверхность — web, app или пусто")
    if not (source or "").strip():
        raise ValueError("Источник обязателен: без него цифра не стоит ничего")
    row = SalesPublisherAudience(publisher_id=publisher_id, metric=metric, value=value,
                                 source=source.strip(), measured_at=measured_at,
                                 surface_kind=surface_kind, segment=(segment or None),
                                 note=(note or None), created_by=user_id)
    db.add(row)
    return row


def _row(r: SalesPublisherAudience) -> dict:
    return {"id": r.id, "metric": r.metric, "value": float(r.value), "source": r.source,
            "measured_at": r.measured_at, "surface_kind": r.surface_kind, "segment": r.segment,
            "note": r.note}


def declared(db: Session, publisher_ids: Iterable[int]) -> Dict[int, dict]:
    """{площадка: {метрика: последний замер}} — для долей ключ «share:<сегмент>»."""
    ids = list(publisher_ids)
    out: Dict[int, dict] = {i: {} for i in ids}
    if not ids:
        return out
    rows = (db.query(SalesPublisherAudience)
            .filter(SalesPublisherAudience.publisher_id.in_(ids))
            .order_by(SalesPublisherAudience.measured_at.desc(), SalesPublisherAudience.id.desc()).all())
    for r in rows:
        key = f"{r.metric}:{r.segment}" if r.segment else r.metric
        if r.surface_kind:
            key = f"{key}@{r.surface_kind}"
        out[r.publisher_id].setdefault(key, _row(r))
    return out


def history(db: Session, publisher_id: int) -> List[dict]:
    rows = (db.query(SalesPublisherAudience).filter_by(publisher_id=publisher_id)
            .order_by(SalesPublisherAudience.measured_at.desc(), SalesPublisherAudience.id.desc()).all())
    return [_row(r) for r in rows]


def measured(db: Session, day_from: date, day_to: date) -> Dict[int, dict]:
    """{площадка: показы наши / верификатора, уники Adfox, fill DSP, клики, РК, дни}.
    Площадки без строк в окне в словаре нет."""
    rows = db.execute(text("""
        SELECT p.publisher_id,
               sum(s.shows)   FILTER (WHERE s.source = ANY(:own))                     AS shows,
               sum(s.clicks)  FILTER (WHERE s.source = ANY(:own))                     AS clicks,
               sum(s.shows)   FILTER (WHERE s.source = ANY(:ver))                     AS ver_shows,
               sum(s.uniques) FILTER (WHERE s.source = 'adfox')                       AS uniques,
               sum(s.shows)   FILTER (WHERE s.source = 'dsp' AND s.offered IS NOT NULL) AS dsp_shows,
               sum(s.offered) FILTER (WHERE s.source = 'dsp')                         AS offered,
               count(DISTINCT s.campaign_id) FILTER (WHERE s.source = ANY(:own))      AS campaigns,
               count(DISTINCT s.date)        FILTER (WHERE s.source = ANY(:own))      AS days,
               bool_or(s.source NOT IN ('dsp', 'adfox') AND s.source = ANY(:own))     AS non_combat
          FROM ad_campaign_stat s
          JOIN ad_campaign_placement p ON p.id = s.placement_id
         WHERE s.date BETWEEN :a AND :b
         GROUP BY p.publisher_id
    """), {"own": list(OWN), "ver": list(VERIFIER), "a": day_from, "b": day_to}).all()
    out = {}
    for pid, shows, clicks, ver, uniq, dsp_shows, offered, camps, days, non_combat in rows:
        shows = int(shows or 0)
        out[pid] = {
            "shows": shows, "clicks": int(clicks or 0),
            "verifier_shows": int(ver) if ver is not None else None,
            "uniques": int(uniq) if uniq is not None else None,
            "ctr_pct": round(100 * (clicks or 0) / shows, 3) if shows else None,
            "fill_pct": round(100 * dsp_shows / offered, 1) if offered else None,
            "campaigns": camps, "days": days, "non_combat": bool(non_combat),
        }
    return out


_EMPTY = {"shows": None, "clicks": None, "verifier_shows": None, "uniques": None,
          "ctr_pct": None, "fill_pct": None, "campaigns": 0, "days": 0, "non_combat": False}


def _publishers(db: Session) -> List[dict]:
    rows = db.execute(text("""
        SELECT p.id, p.name, p.domain, p.kind, p.network, p.status, p.has_dsp, p.deal_type,
               p.media_kit_uploaded_at::date,
               (SELECT json_object_agg(s.kind, s.coverage_percent)
                  FROM sales_publisher_surfaces s WHERE s.publisher_id = p.id) AS coverage
          FROM sales_publishers p WHERE p.is_active ORDER BY p.name
    """)).all()
    return [{"id": r[0], "name": r[1], "domain": r[2], "kind": r[3], "network": r[4], "status": r[5],
             "has_dsp": r[6], "deal_type": r[7], "media_kit_at": r[8], "coverage": r[9] or {}}
            for r in rows]


def _gap(dec: dict, mea: dict) -> Optional[float]:
    """Уники под рекламой / заявленный MAU, %. Нет одного из двух — нет разрыва."""
    mau = (dec.get("mau") or {}).get("value")
    u = mea.get("uniques")
    return round(100 * u / mau, 1) if mau and u is not None else None


def overview(db: Session, days: int = 30, today: Optional[date] = None) -> dict:
    today = today or date.today()
    day_from, day_to = today - timedelta(days=days), today
    pubs = _publishers(db)
    dec = declared(db, [p["id"] for p in pubs])
    mea = measured(db, day_from, day_to)
    sysmap = system_values(db, [p["id"] for p in pubs])
    out = []
    for p in pubs:
        d, m = dec[p["id"]], mea.get(p["id"], _EMPTY)
        mau, dau = (d.get("mau") or {}).get("value"), (d.get("dau") or {}).get("value")
        sysv = sysmap.get(p["id"], {})
        req = sum(sysv.get(k, {}).get("value", 0) for k in ("tr:ad_requests_web", "tr:ad_requests_app_android", "tr:ad_requests_app_ios"))
        # «Загрузка запросов» = наши показы ÷ запросы рекламного кода, приведённые к окну: запросы
        # замеряются на МЕСЯЦ. Оценка, а не факт (замер запросов может быть старше окна).
        load = round(100 * (m["shows"] or 0) / (req * days / 30), 1) if req and m.get("shows") else None
        # ВИЗИТЫ, заявленные площадкой в карточке (web + app, в месяц), и их сверка с независимым
        # SimilarWeb по web: «заявлено ÷ SW». Это визиты, а не люди: с MAU они не смешиваются.
        visits = sum(sysv.get(k, {}).get("value", 0) for k in ("tr:web", "tr:app_android", "tr:app_ios")) or None
        sw = sysv.get("tr:sw_visits", {}).get("value")
        web_v = sysv.get("tr:web", {}).get("value")
        vs_sw = round(web_v / sw, 2) if web_v and sw else None
        out.append({**p, "declared": d, "measured": m, "gap_pct": _gap(d, m), "system": sysv, "load_pct": load,
                    "visits": visits, "visits_vs_sw": vs_sw,
                    "stickiness": round(dau / mau, 2) if mau and dau is not None else None,
                    "media_kit_stale": bool(p["media_kit_at"] and (today - p["media_kit_at"]).days > 180)})
    with_decl = [p for p in out if p["declared"]]
    with_meas = [p for p in out if p["measured"]["shows"] is not None]
    st = [p["stickiness"] for p in out if p["stickiness"] is not None]
    return {
        "window": {"from": day_from, "to": day_to, "days": days},
        "publishers": out,
        "totals": {
            "publishers": len(out), "with_declared": len(with_decl), "with_measured": len(with_meas),
            "mau_sum": sum((p["declared"].get("mau") or {}).get("value", 0) for p in with_decl) or None,
            "uniques_sum": sum(p["measured"]["uniques"] or 0 for p in with_meas) or None,
            "shows_sum": sum(p["measured"]["shows"] or 0 for p in with_meas) or None,
            "stickiness_avg": round(sum(st) / len(st), 2) if st else None,
        },
        "metrics": METRICS,
    }


def sources(db: Session) -> List[str]:
    """Накопительный список источников — для ValuePopover на экране."""
    rows = db.execute(text("SELECT source, count(*) FROM sales_publisher_audience GROUP BY 1 ORDER BY 2 DESC, 1")).all()
    seen = [r[0] for r in rows]
    for s in ("медиакит", "Mediascope", "AppMetrica", "LiveInternet", "Яндекс Метрика", "слова площадки"):
        if s not in seen:
            seen.append(s)
    return seen


def grid(db: Session, only_active: bool = True) -> dict:
    """Сетка заполнения: площадки × поля, в ячейке — ПОСЛЕДНЕЕ значение (значение, источник, дата).
    Две группы: «аудитория» (замеры этого экрана) и «из карточки площадки» (поля, что в системе уже
    есть: трафик, SimilarWeb, запросы кода, покрытие). Пустая ячейка — значения нет (не ноль)."""
    pubs = _publishers(db)
    if only_active:
        pubs = [p for p in pubs if p["status"] == ACTIVE_STATUS]
    ids = [p["id"] for p in pubs]
    dec, sysv = declared(db, ids), system_values(db, ids)
    rows = []
    for p in pubs:
        vals = {}
        for key, *_ in FIELDS:
            m = dec[p["id"]].get(key)
            if m:
                vals[key] = {"value": m["value"], "source": m["source"], "measured_at": m["measured_at"]}
        vals.update(sysv[p["id"]])
        rows.append({"id": p["id"], "name": p["name"], "kind": p["kind"], "status": p["status"], "values": vals})
    fields = ([{"key": f[0], "label": f[1], "metric": f[2], "pct": f[2] in PCT_METRICS, "group": "audience"} for f in FIELDS]
              + [{"key": f[0], "label": f[1], "metric": f[2], "pct": f[0] in PCT_SYS, "group": "system"} for f in SYS_FIELDS])
    return {"fields": fields, "publishers": rows}


ACTIVE_STATUS = "СОТРУДНИЧАЕМ"


def _same(a, b) -> bool:
    return a is not None and abs(float(a) - float(b)) < 1e-9


def apply_items(db: Session, items: List[dict], *, source: str, measured_at: date,
                user_id: Optional[int], commit_rows: bool = True) -> dict:
    """Записать пачку значений: каждое отличное от последнего замера становится НОВОЙ строкой
    (история остаётся). Одинаковое с последним — пропускается, чтобы повторная загрузка того же
    файла не плодила дубли. → {written, skipped_same, publishers}."""
    if not (source or "").strip():
        raise ValueError("Источник обязателен: без него цифра не стоит ничего")
    ids = sorted({i["publisher_id"] for i in items})
    dec, sysv = declared(db, ids), system_values(db, ids)
    written, same, touched = 0, 0, set()
    for it in items:
        key, v = it["key"], float(it["value"])
        label = label_of(key)
        if v < 0:
            raise ValueError(f"{label}: значение не может быть отрицательным")
        if key in SYS_BY_KEY:
            if (key in PCT_SYS) and v > 100:
                raise ValueError(f"{label}: не может быть больше 100 %")
            cur = sysv.get(it["publisher_id"], {}).get(key)
            if cur and _same(cur["value"], v):
                same += 1
                continue
            if commit_rows:
                write_system(db, it["publisher_id"], key, v)
            written += 1
            touched.add(it["publisher_id"])
            continue
        f = FIELD_BY_KEY[key]
        if f[2] in PCT_METRICS and v > 100:
            raise ValueError(f"{label}: доля не может быть больше 100 %")
        cur = dec.get(it["publisher_id"], {}).get(f[0])
        if cur and _same(cur["value"], v):
            same += 1
            continue
        if commit_rows:
            add_measure(db, it["publisher_id"], metric=f[2], value=v, source=source, measured_at=measured_at,
                        surface_kind=f[3], segment=f[4], note=None, user_id=user_id)
        written += 1
        touched.add(it["publisher_id"])
    return {"written": written, "skipped_same": same, "publishers": len(touched)}


def export_xlsx(db: Session) -> bytes:
    """Книга для заполнения: строка — активная площадка, колонки — поля каталога с ПОСЛЕДНИМИ
    значениями, плюс «Источник» и «Дата замера» (общие на строку). Пустая ячейка — замера нет."""
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from app.xlsx_safe import save_workbook

    data = grid(db)
    wb = Workbook()
    ws = wb.active
    ws.title = "Аудитория"
    heads = ["ID", "Площадка", "Вид"] + [f[1] for f in FIELDS] + [f[1] for f in SYS_FIELDS] + ["Источник", "Дата замера"]
    ws.append(heads)
    for p in data["publishers"]:
        row = [p["id"], p["name"], p["kind"] or ""]
        for key in [f[0] for f in FIELDS] + [f[0] for f in SYS_FIELDS]:
            row.append((p["values"].get(key) or {}).get("value"))
        row += ["", ""]
        ws.append(row)
    head_fill = PatternFill("solid", fgColor="ECEFFD")
    lock_fill = PatternFill("solid", fgColor="F6F7FB")
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = head_fill
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for r in ws.iter_rows(min_row=2, max_col=3):
        for c in r:
            c.fill = lock_fill
    ws.freeze_panes = "D2"
    ws.column_dimensions["A"].width = 7
    ws.column_dimensions["B"].width = 26
    ws.column_dimensions["C"].width = 14
    for i in range(4, len(heads) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 15
    ws.row_dimensions[1].height = 34
    info = wb.create_sheet("Как заполнять")
    for line in (
        "Лист «Аудитория»: ID, Площадка и Вид не меняются — по ID строка находится при загрузке.",
        "Впишите новые значения в колонки аудитории. Пустая ячейка — «не знаем», она ничего не стирает.",
        "Заполните «Источник» (медиакит, Mediascope, AppMetrica…) и, если нужно, «Дата замера» (ДД.ММ.ГГГГ).",
        "Строки, где источник не указан, при загрузке отклоняются: цифра без источника ничего не стоит.",
        "Значение, равное последнему замеру, пропускается; отличное — становится новым замером, история остаётся.",
        "Колонки с «Трафик», «SimilarWeb», «Запросы кода» и «Покрытие» — поля карточки площадки: они пишутся в те же таблицы и ПЕРЕЗАПИСЫВАЮТ замер текущего месяца (как в карточке), без истории.",
        "Доли — в процентах (57,5), не в долях единицы. MAU/DAU/WAU — числом, без «тыс.» и «млн».",
    ):
        info.append([line])
    info.column_dimensions["A"].width = 120
    buf = BytesIO()
    save_workbook(wb, buf)   # единая точка сохранения: текст площадок с «=» не станет формулой (аудит 23.09.2026)
    return buf.getvalue()


def parse_xlsx(db: Session, contents: bytes) -> dict:
    """Разбор загруженной книги → {items, errors, rows}. Ничего не пишет.
    items — то, что надо внести (`apply_items`), каждый с `source`/`measured_at` строки."""
    from io import BytesIO
    from datetime import datetime
    from openpyxl import load_workbook

    try:
        wb = load_workbook(BytesIO(contents), data_only=True, read_only=True)
    except Exception:
        raise ValueError("Файл не открывается как .xlsx")
    ws = wb["Аудитория"] if "Аудитория" in wb.sheetnames else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("Лист пустой")
    head = [str(h).strip() if h is not None else "" for h in rows[0]]
    if "ID" not in head or "Источник" not in head:
        raise ValueError("Не найдены колонки «ID» и «Источник» — возьмите файл из выгрузки этого экрана")
    col = {h: i for i, h in enumerate(head)}
    unknown = [h for h in head if h and h not in FIELD_BY_LABEL and h not in SYS_BY_LABEL
               and h not in ("ID", "Площадка", "Вид", "Источник", "Дата замера")]
    valid_ids = {r[0] for r in db.execute(text("SELECT id FROM sales_publishers")).all()}
    items, errors, today = [], [], date.today()
    for n, r in enumerate(rows[1:], start=2):
        if not r or all(v is None or str(v).strip() == "" for v in r):
            continue
        pid_raw = r[col["ID"]]
        try:
            pid = int(pid_raw)
        except (TypeError, ValueError):
            errors.append(f"Строка {n}: ID «{pid_raw}» не число")
            continue
        if pid not in valid_ids:
            errors.append(f"Строка {n}: площадки с ID {pid} нет")
            continue
        values = []
        for label, key in [(f[1], f[0]) for f in FIELDS] + [(f[1], f[0]) for f in SYS_FIELDS]:
            if label not in col:
                continue
            v = r[col[label]]
            if v is None or str(v).strip() == "":
                continue
            try:
                num = float(str(v).replace("\xa0", "").replace(" ", "").replace(",", "."))
            except ValueError:
                errors.append(f"Строка {n}, «{label}»: «{v}» не число")
                continue
            if num < 0:
                errors.append(f"Строка {n}, «{label}»: отрицательное значение")
                continue
            if (key in PCT_SYS or (key in FIELD_BY_KEY and FIELD_BY_KEY[key][2] in PCT_METRICS)) and num > 100:
                errors.append(f"Строка {n}, «{label}»: значение больше 100 %")
                continue
            values.append({"publisher_id": pid, "key": key, "value": num})
        # Выгрузка уже содержит последние значения во всех ячейках, поэтому неизменённое — не повод
        # требовать источник: он нужен только строкам, где что-то реально поменяли.
        cur = {**declared(db, [pid])[pid], **system_values(db, [pid])[pid]}
        values = [v for v in values if not (cur.get(v["key"]) and _same(cur[v["key"]]["value"], v["value"]))]
        if not values:
            continue
        src = r[col["Источник"]]
        src = str(src).strip() if src is not None else ""
        if not src:
            errors.append(f"Строка {n}: не указан источник — значения не загружены")
            continue
        when = today
        if "Дата замера" in col and r[col["Дата замера"]] not in (None, ""):
            raw = r[col["Дата замера"]]
            if isinstance(raw, datetime):
                when = raw.date()
            elif isinstance(raw, date):
                when = raw
            else:
                try:
                    when = datetime.strptime(str(raw).strip(), "%d.%m.%Y").date()
                except ValueError:
                    errors.append(f"Строка {n}: дата «{raw}» — ожидается ДД.ММ.ГГГГ")
                    continue
        if when > today:
            errors.append(f"Строка {n}: дата замера в будущем")
            continue
        for v in values:
            items.append({**v, "source": src, "measured_at": when})
    return {"items": items, "errors": errors, "unknown_columns": unknown}


def system_values(db: Session, publisher_ids: Iterable[int]) -> Dict[int, dict]:
    """{площадка: {ключ SYS_FIELDS: {value, source, measured_at}}} — ПОСЛЕДНИЙ замер трафика по scope
    и покрытие поверхностей. Читает те же таблицы, что карточка площадки."""
    ids = list(publisher_ids)
    out: Dict[int, dict] = {i: {} for i in ids}
    if not ids:
        return out
    rows = db.execute(text(
        "SELECT DISTINCT ON (publisher_id, scope) publisher_id, scope, value, depth, measured_at, source "
        "FROM sales_publisher_traffic WHERE publisher_id = ANY(:ids) "
        "ORDER BY publisher_id, scope, measured_at DESC"), {"ids": ids}).all()
    latest = {(r[0], r[1]): r for r in rows}
    for key, _label, kind, scope, col in SYS_FIELDS:
        if kind != "traffic":
            continue
        for pid in ids:
            r = latest.get((pid, scope))
            if not r:
                continue
            v = r[3] if col == "depth" else r[2]
            if v is not None:
                out[pid][key] = {"value": float(v), "source": SOURCE_SYSTEM, "measured_at": r[4]}
    for pid, sk, cov in db.execute(text(
            "SELECT publisher_id, kind, coverage_percent FROM sales_publisher_surfaces "
            "WHERE publisher_id = ANY(:ids) AND coverage_percent IS NOT NULL"), {"ids": ids}).all():
        out[pid][f"cov:{sk}"] = {"value": float(cov), "source": SOURCE_SYSTEM, "measured_at": None}
    return out


def _month_start() -> date:
    from app import timez
    t = timez.msk_now()
    return date(t.year, t.month, 1)


def write_system(db: Session, publisher_id: int, key: str, value: float) -> None:
    """Записать системное поле ТАК ЖЕ, как карточка площадки: замер текущего месяца перезаписывается
    (`upsert_traffic`), покрытие — в поверхность. Нет поверхности — отказ с текстом, а не молчание."""
    _k, _label, kind, scope, col = SYS_BY_KEY[key]
    if kind == "coverage":
        surf = db.execute(text("SELECT id FROM sales_publisher_surfaces WHERE publisher_id = :p AND kind = :k"),
                          {"p": publisher_id, "k": scope}).first()
        if not surf:
            raise ValueError(f"{_label}: у площадки нет поверхности {scope} — заведите её в карточке")
        db.execute(text("UPDATE sales_publisher_surfaces SET coverage_percent = :v WHERE id = :i"),
                   {"v": value, "i": surf[0]})
        return
    month = _month_start()
    cur = db.execute(text("SELECT id FROM sales_publisher_traffic WHERE publisher_id = :p AND scope = :s AND measured_at = :m"),
                     {"p": publisher_id, "s": scope, "m": month}).first()
    if cur:
        db.execute(text(f"UPDATE sales_publisher_traffic SET {col} = :v, source = 'manual' WHERE id = :i"),
                   {"v": value, "i": cur[0]})
        return
    # Замера этого месяца нет. Карточка показывает ПОСЛЕДНИЙ замер, и строка с одним NULL перекрыла бы
    # реальную цифру прошлого месяца — поэтому вторую колонку берём из последнего замера.
    prev = db.execute(text("SELECT value, depth FROM sales_publisher_traffic WHERE publisher_id = :p AND scope = :s "
                           "ORDER BY measured_at DESC LIMIT 1"), {"p": publisher_id, "s": scope}).first()
    val = value if col == "value" else (prev[0] if prev else None)
    dep = value if col == "depth" else (prev[1] if prev else None)
    db.execute(text("INSERT INTO sales_publisher_traffic (publisher_id, scope, value, depth, measured_at, source) "
                    "VALUES (:p, :s, :v, :d, :m, 'manual')"), {"p": publisher_id, "s": scope, "v": val, "d": dep, "m": month})
