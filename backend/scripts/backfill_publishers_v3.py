"""
Разовый добор данных паблишеров под миграцию 2026-08-19_publishers_v3.sql.

    docker cp "Аптеки - Рабочая.xlsx" finance_backend:/tmp/publishers.xlsx
    docker exec finance_backend python -m scripts.backfill_publishers_v3 /tmp/publishers.xlsx [--apply]

Два переноса:

1. **Приоритезация: флаг → услуга.** В каталоге услуг «Приоритезация» есть отдельной
   строкой, и в макете она показана плашкой услуги с указанием поверхностей. Держать
   параллельно флаг на площадке значит иметь две правды об одном.

2. **Цифры из Excel → замеры трафика.** Раньше им не было места в схеме, поэтому колонки
   с уникам и запросами остались в таблице. Теперь есть sales_publisher_traffic с датой
   замера — переносим то, что ложится на четыре показателя интерфейса:
       «Визиты/показы (web) 2025»  → scope web
       «Adfox запросы, с кукухой»  → scope ad_requests
   Уники (MAU) и органик-запросы Adfox НЕ переносятся: MAU — это уникальные пользователи,
   а не визиты, и подмешивать их в тот же показатель нельзя; для органики отдельного
   показателя в интерфейсе нет. Обе колонки остаются в Excel и попадают в отчёт скрипта.

Замер помечается месяцем декабря 2025: в исходнике цифры подписаны «факт 2025» без месяца.
"""
import re
import sys
from datetime import date

from app.database import SessionLocal
from app.sales.models import (SalesPublisher, SalesPublisherService, SalesPublisherTraffic, SalesService, normalize_domain)

MEASURED_AT = date(2025, 12, 1)
COL_SITE, COL_MAU, COL_VISITS, COL_ADFOX_ORGANIC, COL_ADFOX_COOKIE = 2, 16, 17, 18, 19

_MULT = {"тыс": 1_000, "тысяч": 1_000, "млн": 1_000_000, "млрд": 1_000_000_000}


def parse_number(raw):
    """«900 тыс» → 900000, «2,05 млн» → 2050000, «84 811 тыс» → 84811000, «1 030 000» →
    1030000. Числа в этих колонках записаны как придётся — без разбора половина потерялась бы."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip().lower().replace("\xa0", " ")
    if not s:
        return None
    mult = 1
    for word, factor in _MULT.items():
        if word in s:
            mult = factor
            s = s.replace(word, " ")
            break
    s = re.sub(r"[^\d,.\s]", " ", s).replace(",", ".").strip()
    # Пробелы внутри числа — разряды («84 811»), но только если дробной части нет.
    parts = s.split()
    if not parts:
        return None
    if len(parts) > 1 and all(p.isdigit() for p in parts):
        s = "".join(parts)
    else:
        s = parts[0]
    try:
        value = float(s) * mult
    except ValueError:
        return None
    # Заслон от склейки разрядов: месячный трафик аптечного сайта не бывает
    # триллионным, такая величина означает разбор мусора, а не рекорд.
    return value if 0 < value < 1e11 else None


def main(path, apply=False):
    import openpyxl
    ws = openpyxl.load_workbook(path, data_only=True).active
    db = SessionLocal()
    report = {"priority": 0, "priority_skipped": [], "traffic": 0,
              "unparsed": [], "mau_left": 0, "organic_left": 0, "no_publisher": []}

    prio = db.query(SalesService).filter(SalesService.name == "Приоритезация").first()
    if not prio:
        raise SystemExit("В каталоге нет услуги «Приоритезация» — перенос флага невозможен")

    # 1. Флаг приоритезации → услуга на поверхности.
    for p in db.query(SalesPublisher).filter(SalesPublisher.is_priority.is_(True)).all():
        kinds = [s.kind for s in p.surfaces]
        # Веб — основная поверхность; если её нет, отмечаем на той, что есть.
        kind = "web" if "web" in kinds else (kinds[0] if kinds else None)
        if not kind:
            report["priority_skipped"].append(p.domain)
            continue
        exists = (db.query(SalesPublisherService)
                  .filter(SalesPublisherService.publisher_id == p.id,
                          SalesPublisherService.surface_kind == kind,
                          SalesPublisherService.service_id == prio.id).first())
        if not exists:
            db.add(SalesPublisherService(publisher_id=p.id, surface_kind=kind,
                                         service_id=prio.id))
            report["priority"] += 1

    # 2. Цифры Excel → замеры трафика.
    by_domain = {p.domain: p for p in db.query(SalesPublisher).all()}
    seen = set()
    for r in range(2, ws.max_row + 1):
        site = ws.cell(r, COL_SITE).value
        if not site:
            continue
        domain = normalize_domain(site)
        p = by_domain.get(domain)
        if not p:
            report["no_publisher"].append(domain)
            continue
        for col, scope in [(COL_VISITS, "web"), (COL_ADFOX_COOKIE, "ad_requests")]:
            raw = ws.cell(r, col).value
            if raw in (None, ""):
                continue
            value = parse_number(raw)
            if value is None:
                report["unparsed"].append((domain, scope, str(raw)))
                continue
            key = (p.id, scope)
            if key in seen:      # у WEB/APP-дублей строки две, цифра одна
                continue
            seen.add(key)
            row = (db.query(SalesPublisherTraffic)
                   .filter(SalesPublisherTraffic.publisher_id == p.id,
                           SalesPublisherTraffic.scope == scope,
                           SalesPublisherTraffic.measured_at == MEASURED_AT).first())
            if row:
                continue
            db.add(SalesPublisherTraffic(publisher_id=p.id, scope=scope, value=value,
                                         measured_at=MEASURED_AT, source="manual"))
            report["traffic"] += 1
        if ws.cell(r, COL_MAU).value not in (None, ""):
            report["mau_left"] += 1
        if ws.cell(r, COL_ADFOX_ORGANIC).value not in (None, ""):
            report["organic_left"] += 1

    db.commit() if apply else db.rollback()

    print("ЗАПИСАНО" if apply else "ПРОГОН БЕЗ ЗАПИСИ")
    print(f"приоритезация перенесена в услугу: {report['priority']} площадок")
    if report["priority_skipped"]:
        print(f"   без поверхностей, перенести некуда: {', '.join(report['priority_skipped'])}")
    print(f"замеров трафика создано: {report['traffic']} (декабрь 2025)")
    if report["unparsed"]:
        print(f"не разобрано числами ({len(report['unparsed'])}):")
        for d, scope, raw in report["unparsed"]:
            print(f"   {d} · {scope}: «{raw}»")
    print(f"осталось в Excel без места в схеме: уники (MAU) — {report['mau_left']} значений, "
          f"Adfox органик — {report['organic_left']} значений")
    if report["no_publisher"]:
        print(f"нет такой площадки в справочнике: {', '.join(sorted(set(report['no_publisher'])))}")
    db.close()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0] if args else "/tmp/publishers.xlsx", apply="--apply" in sys.argv)
