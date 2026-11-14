# -*- coding: utf-8 -*-
"""Итоговая статистика площадки файлом — цикл «приоритезация», итоговая сверка (владелец 13.11.2026: «часть услуги идёт на основании
движков площадок, а не нашего кода»; «переключатель уже на итоговой сверке, у аккаунта решение подгружать или нет»).

Шаблон — как отчёт Adfox, только без номера креатива: `День · Название кампании · Показы · Переходы · Уникальные показы`, где
название кампании — `КОДСДЕЛКИ-КОДПЛОЩАДКИ`. Разбор — тот же, что у импорта Adfox (`traffic/adfox_import.parse`: перевод строки
в ячейке, служебные строки, «Всего»). Правила записи — тоже его: по дням; повтор дня перезаписывает; дня нет в файле — «нет
данных», не ноль. Пишется в факт РК сделки источником `prio` по площадке; площадке ставится `fact_source = 'файл'`, и ночной сбор
её факт больше не трогает."""
from io import BytesIO
from typing import Dict, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.prio import models as M
from app.prio.service import PrioError
from app.traffic import adfox_import as AF
from app.xlsx_safe import save_workbook

SOURCE = "prio"
HEAD = ["День", "Название кампании", "Показы", "Переходы", "Уникальные показы"]


def _placements(db: Session, deal) -> Dict[str, dict]:
    """Код площадки (в верхнем регистре) → площадка запроса сделки."""
    rows = db.execute(text("""
        SELECT pp.id, pp.publisher_id, sp.name, upper(sp.code) AS code
          FROM prio_placements pp JOIN prio_requests r ON r.id = pp.request_id
          JOIN sales_publishers sp ON sp.id = pp.publisher_id
         WHERE r.deal_id = :d AND coalesce(sp.code, '') <> ''"""), {"d": deal.id}).mappings().all()
    return {r["code"]: dict(r) for r in rows}


def _campaign(db: Session, deal) -> int:
    cid = db.execute(text("SELECT id FROM ad_campaign WHERE deal_id = :d ORDER BY id LIMIT 1"), {"d": deal.id}).scalar()
    if cid is None:
        raise PrioError(409, "У сделки нет РК — факт некуда записать. РК заводится при входе в «Готовятся к старту» "
                             "(или ночным прогоном); обновите страницу утром или обратитесь к администратору")
    return cid


def _rk_placement(db: Session, campaign_id: int, publisher_id: int):
    return db.execute(text("""SELECT id FROM ad_campaign_placement WHERE campaign_id = :c AND publisher_id = :p
                               ORDER BY id LIMIT 1"""), {"c": campaign_id, "p": publisher_id}).scalar()


def apply(db: Session, deal, data: bytes, user) -> dict:
    """Записать итог файла. → {written: строк факта (площадка × день), placements: [имена], unknown: [названия],
    days: [первый, последний]}. Без commit — его делает ручка."""
    try:
        rows = AF.parse(data)
    except AF.ImportError_ as e:
        raise PrioError(400, str(e).replace("отчёта Adfox", "итогового файла").replace("отчёт Adfox", "итоговый файл"))
    by_code = _placements(db, deal)
    camp = _campaign(db, deal)
    prefix = f"{deal.code}-".upper()
    agg: Dict[Tuple[int, object], dict] = {}
    hit, unknown = set(), []
    for r in rows:
        name = r["name"].strip()
        up = name.upper()
        p = by_code.get(up[len(prefix):]) if up.startswith(prefix) else None
        if p is None:
            if name.lower() not in AF.SERVICE_NAMES and name not in unknown:
                unknown.append(name)
            continue
        hit.add(p["id"])
        a = agg.setdefault((p["id"], r["day"]), {"shows": 0, "clicks": 0, "uniques": [], "pub": p["publisher_id"]})
        a["shows"] += r["shows"]
        a["clicks"] += r["clicks"]
        a["uniques"].append(r["uniques"])
    if not agg:
        raise PrioError(400, f"В файле нет строк этой сделки: название кампании — «{deal.code}-КОДПЛОЩАДКИ»")
    for (pid, day), a in agg.items():
        u = a["uniques"]
        uniques = u[0] if len(u) == 1 else None          # уники двух строк одного дня не складываются (правило импорта Adfox)
        db.execute(text("""
            INSERT INTO ad_campaign_stat (campaign_id, placement_id, date, shows, clicks, uniques, source, imported_at)
            VALUES (:c, :p, :d, :s, :k, :u, :src, now())
            ON CONFLICT ON CONSTRAINT uq_ad_stat DO UPDATE
               SET shows = EXCLUDED.shows, clicks = EXCLUDED.clicks, uniques = EXCLUDED.uniques, imported_at = now()"""),
            {"c": camp, "p": _rk_placement(db, camp, a["pub"]), "d": day, "s": a["shows"], "k": a["clicks"], "u": uniques,
             "src": SOURCE})
    names = []
    for pid in hit:
        pl = db.get(M.PrioPlacement, pid)
        pl.fact_source = "файл"
        names.append(next(p["name"] for p in by_code.values() if p["id"] == pid))
    db.flush()
    days = sorted({d for _, d in agg})
    return {"written": len(agg), "placements": sorted(names), "unknown": unknown,
            "days": [days[0].isoformat(), days[-1].isoformat()]}


def set_source(db: Session, deal, pid: int, source: str) -> None:
    """Вернуть площадку к факту из сервиса (файл больше не нужен). Переключить на «файл» можно только загрузкой."""
    if source != "сервис":
        raise PrioError(400, "На «файл» площадка переключается загрузкой итогового файла")
    from app.prio.service import placement
    p = placement(db, deal, pid)
    p.fact_source = "сервис"
    db.flush()


def template(db: Session, deal) -> bytes:
    """Шаблон итогового файла: шапка и по строке на каждую площадку запроса с готовым названием кампании."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Итог"
    ws.append(HEAD)
    for code, p in sorted(_placements(db, deal).items(), key=lambda x: x[1]["name"]):
        ws.append([None, f"{deal.code}-{code}", None, None, None])
    for col, w in zip("ABCDE", (12, 26, 12, 12, 18)):
        ws.column_dimensions[col].width = w
    buf = BytesIO()
    save_workbook(wb, buf)                     # единая точка сохранения .xlsx (защита от формул в ячейках)
    return buf.getvalue()

