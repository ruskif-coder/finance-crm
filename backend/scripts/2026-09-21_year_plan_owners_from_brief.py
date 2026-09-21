# -*- coding: utf-8 -*-
"""Переставить владельца уже сохранённых строк годового плана по их брифу.

Зачем отдельный скрипт. Миграция `2026-09-21_year_plan_account_manager.sql` развела
две оси владения, но СТАРЫЕ строки она не трогает: у них в обеих осях стоит создатель.
То есть план, заведённый аккаунтом до 21.09.2026, продолжит лежать в корзине аккаунта
до первого пересохранения — а человек, который его ищет, пересохранять не будет, он
просто снова его не найдёт.

Что делает: у каждой строки читает продавца из брифа (`brief.sales_rep_id`) и, если он
задан и отличается от текущего, ставит его продавцом. Ведущим аккаунтом при этом
остаётся тот, кто там уже есть, — это и есть создатель, то есть верное значение.

ВАЖНО: в брифе ответственные хранятся УЧЁТКАМИ, а колонки владения ссылаются на
`sales_reps`. Числа из разных множеств, и подстановка без перевода почти всегда
попадёт в существующий, но ЧУЖОЙ профиль — молча. Перевод здесь тот же, что в коде.

Без `--apply` только показывает, что собирается сделать. Повторный прогон безопасен:
строки, где продавец уже совпал, пропускаются.

    docker exec finance_backend python -m scripts.2026-09-21_year_plan_owners_from_brief
    docker exec finance_backend python -m scripts.2026-09-21_year_plan_owners_from_brief --apply
"""
import sys

from app.database import SessionLocal
from app.sales.models import SalesAdvertiser, SalesRep, SalesYearPlanLine


def main(apply: bool) -> int:
    db = SessionLocal()
    try:
        rep_by_user, rep_name = {}, {}
        for r in db.query(SalesRep).all():
            rep_name[r.id] = r.name
            if r.user_id is not None:
                rep_by_user.setdefault(r.user_id, r.id)
        adv_name = {a.id: (a.short_name or a.name)
                    for a in db.query(SalesAdvertiser).all()}

        moved = same = no_brief = unknown = 0
        for line in db.query(SalesYearPlanLine).order_by(SalesYearPlanLine.id).all():
            uid = (line.brief or {}).get("sales_rep_id")
            if not uid:
                no_brief += 1
                continue
            seller = rep_by_user.get(uid)
            if seller is None:
                # Учётка из брифа без профиля в справочнике — не выдумываем, оставляем
                # как есть и показываем: это повод завести профиль, а не чинить данные.
                unknown += 1
                print("  ? строка %-5s %-28s учётка %s без профиля"
                      % (line.id, adv_name.get(line.advertiser_id, "—")[:28], uid))
                continue
            if seller == line.sales_rep_id:
                same += 1
                continue
            print("  → строка %-5s %-4s %-28s продавец %s → %s (ведёт %s)"
                  % (line.id, line.year, adv_name.get(line.advertiser_id, "—")[:28],
                     rep_name.get(line.sales_rep_id, "—"), rep_name.get(seller, "—"),
                     rep_name.get(line.account_manager_id, "—")))
            if apply:
                line.sales_rep_id = seller
            moved += 1

        if apply:
            db.commit()
        print("\nпереставлено: %d, уже верно: %d, без продавца в брифе: %d, "
              "учётка без профиля: %d%s"
              % (moved, same, no_brief, unknown,
                 "" if apply else "   [ВХОЛОСТУЮ, ничего не записано]"))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
