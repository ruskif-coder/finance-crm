# -*- coding: utf-8 -*-
"""Проба API Adfox — ТОЛЬКО ЧТЕНИЕ: готовые отчёты учётки и отчёт «По кампаниям» за день (колонки и первые строки).
В Adfox ничего не пишет. `python -m app.adfox.probe [ГГГГ-ММ-ДД]`"""
import sys
from datetime import date, timedelta

from app.adfox.client import AdfoxClient, AdfoxError


def main() -> None:
    day = sys.argv[1] if len(sys.argv) > 1 else (date.today() - timedelta(days=1)).isoformat()
    try:
        cl = AdfoxClient()
        print("отчёты owner:", cl.reports("owner"))
        rows = cl.report_v2("campaigns", "owner", day, day)
        print(f"«По кампаниям» за {day}: строк {len(rows)}, показов {sum(int(r.get('impressions_commercial') or 0) for r in rows)}")
        for r in rows[:5]:
            print("  ", r)
    except AdfoxError as e:
        print(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
