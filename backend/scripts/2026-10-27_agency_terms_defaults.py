# -*- coding: utf-8 -*-
"""«Агентские условия»: основное правило СК по умолчанию каждой связке «агентство / рекламодатель × договор», где его нет
(владелец 27.10.2026: «по умолчанию 30 % постоплата», исключения — по юрлицу договора).

Исключения передаются аргументами — имён контрагентов в репозитории нет:

    docker exec finance_backend python -m scripts.2026-10-27_agency_terms_defaults \\
        --except "<ЮРЛИЦО>=скидка в счёт:44.8" --except "<ЮРЛИЦО 2>=скидка в счёт:45"            # пробный прогон
    … --apply                                                                                    # записать

Правило: договор + агентство (или рекламодатель при прямом договоре), без уточнений, с `--from` (по умолчанию 01.01.2026),
бессрочно. Связка, у которой уже есть основное правило любой точности, не трогается. Повторный запуск ничего не дублирует.
Каждое созданное правило — строкой в журнал действий."""
import argparse
from datetime import date

import app.model_registry  # noqa: F401
from app.agency_terms import rules as R
from app.agency_terms import service as S
from app.audit import log_action
from app.database import SessionLocal


def parse_except(items):
    out = {}
    for it in items or []:
        name, _, rest = it.partition("=")
        mode, _, pct = rest.rpartition(":")
        if not name.strip() or mode not in R.MODES:
            raise SystemExit(f"Исключение «{it}»: формат «ЮРЛИЦО=способ:процент», способ — {' или '.join(R.MODES)}")
        out[name.strip().upper()] = (mode, float(pct.replace(",", ".")))
    return out


def plan(db, default, exceptions, valid_from):
    """[(side_key, owner_id, owner, contract_id, entity, mode, percent)] — связки без основного правила."""
    rules = [r for r in S.all_rules(db) if r["kind"] == R.MAIN]
    todo, seen = [], set()
    for side, key in (("agency", "agency_id"), ("advertiser", "advertiser_id")):
        for o in S.tree(db, side):
            for e in o["entities"]:
                mode, pct = exceptions.get(str(e["name"]).strip().upper(), default)
                for c in e["contracts"]:
                    pair = (key, o["id"], c["id"])
                    if pair in seen or any(r["contract_id"] == c["id"] and r.get(key) == o["id"] for r in rules):
                        continue
                    seen.add(pair)
                    todo.append((key, o["id"], o["name"], c["id"], e["name"], mode, pct))
    return todo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--percent", type=float, default=30.0)
    ap.add_argument("--mode", default="постоплата", choices=R.MODES)
    ap.add_argument("--except", dest="exc", action="append")
    ap.add_argument("--from", dest="valid_from", default="2026-01-01")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    exceptions = parse_except(a.exc)
    db = SessionLocal()
    try:
        todo = plan(db, (a.mode, a.percent), exceptions, a.valid_from)
        by = {}
        for t in todo:
            by[(t[5], t[6])] = by.get((t[5], t[6]), 0) + 1
        print(f"связок без основного правила: {len(todo)}; по условиям: {by}")
        for t in todo:
            if (t[5], t[6]) != (a.mode, a.percent):
                print(f"  исключение: {t[2]} · {t[4]} → {t[5]} {t[6]:g} %")
        if not a.apply:
            print("пробный прогон — ничего не записано; запись — с --apply")
            return
        n = 0
        for key, oid, owner, cid, entity, mode, pct in todo:
            r = S.save_rule(db, {"kind": R.MAIN, "contract_id": cid, key: oid, "mode": mode, "percent": pct,
                                 "valid_from": date.fromisoformat(a.valid_from), "note": "по умолчанию (27.10.2026)"}, None)
            db.commit()
            log_action(db, None, "agency_terms_rule_save", "sk_rule", r.id,
                       f"СК основная по умолчанию: {owner} · {entity} — {mode} {pct:g} % с {a.valid_from}")
            n += 1
        print(f"записано правил: {n}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
