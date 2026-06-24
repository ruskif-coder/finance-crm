# Одноразовый скрипт: переставляет sort_order статей так, чтобы порядок совпадал
# с порядком, в котором статьи сейчас выводятся в отчёте P&L (app/routers/reports.py):
#   1) группа — в порядке PL_GROUPS_ORDER (ВЫРУЧКА, СЕБЕСТОИМОСТЬ, ОПЕРАЦИОННЫЕ, МАРКЕТИНГ, НАЛОГИ),
#      затем статьи с группой, не входящей в этот список, затем "НЕ В P&L", затем без группы;
#   2) внутри группы — подгруппа по алфавиту (без подгруппы — первой);
#   3) внутри подгруппы — статья по алфавиту.
# Запускается один раз внутри контейнера backend: python resort_articles_pl.py

import sys
sys.path.insert(0, "/app")

from app.database import SessionLocal
from app.models import Article

PL_GROUPS_ORDER = ['ВЫРУЧКА', 'СЕБЕСТОИМОСТЬ', 'ОПЕРАЦИОННЫЕ', 'МАРКЕТИНГ', 'НАЛОГИ']


def group_rank(g):
    if g is None:
        return 100
    if g == 'НЕ В P&L':
        return 99
    if g in PL_GROUPS_ORDER:
        return PL_GROUPS_ORDER.index(g)
    return 50  # незнакомая группа — между известными группами и "НЕ В P&L"


def main():
    db = SessionLocal()
    try:
        articles = db.query(Article).all()
        articles.sort(key=lambda a: (group_rank(a.group), a.subgroup or '', a.name or ''))
        for i, a in enumerate(articles, start=1):
            a.sort_order = i
        db.commit()
        print(f"OK: sort_order обновлён для {len(articles)} статей")
    finally:
        db.close()


if __name__ == "__main__":
    main()
