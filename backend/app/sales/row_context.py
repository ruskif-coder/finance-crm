"""Общие куски строки сделки для всех витрин.

Реестр сделок и очередь аккаунта отдают разные наборы полей, но несколько полей у них
обязаны совпадать: цвет услуги, поверхность (web/app), гео и список приложенных
документов. Пока они считались
на месте в каждом сериализаторе, выражение было продублировано дословно — а третий
экран скопировал бы его в третий раз, и первая же правка (например «Акт тоже считать
закрывающим») разъехалась бы по копиям.

Здесь одна загрузка контекста на страницу и одна функция, которая кладёт эти поля
в строку. Выборки ограничены переданными id — таблицы файлов и планов растут вместе
с архивом, и читать их целиком ради двадцати строк незачем.
"""
from typing import Dict, Iterable, List, Set

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.sales.colors import service_color_map, auto_color


class RowContext:
    """Справочные данные под страницу сделок: цвета услуг, поверхности и документы."""

    def __init__(self, colors: Dict[str, str], docs: Dict[int, Set[str]],
                 surfaces: Dict[int, Dict[str, str]] | None = None,
                 separate_price: Set[str] | None = None,
                 geos: Dict[int, str] | None = None):
        self.colors = colors
        self.docs = docs
        # {deal_id: {название услуги: 'web'|'app'|'cross'}} — из строк медиаплана.
        self.surfaces = surfaces or {}
        self.separate_price = separate_price or set()
        # {deal_id: 'РФ'} — из ШАПКИ медиаплана: своего гео у сделки нет.
        self.geos = geos or {}

    def color(self, product: str | None) -> str:
        """Цвет услуги. Имени нет в справочнике (услуга удалена или не сматчена
        синком) — отдаём авто-цвет: маркер должен быть у любой строки."""
        return self.colors.get(product) or auto_color(product or "")

    def doc_kinds(self, deal_id: int) -> List[str]:
        return sorted(self.docs.get(deal_id, ()))

    def inventory(self, deal_id: int, product: str | None) -> str | None:
        """Поверхность услуги сделки: 'web' | 'app' | 'cross' либо None.

        Показываем ТОЛЬКО у услуг с раздельным прайсом (решение владельца 03.09.2026):
        у остальных поверхность на продукт не влияет, и метка была бы шумом. Сегодня
        таких услуг одна — еФарм, но признак читается из справочника, а не зашит сюда.

        Источник — строки последнего непринятого-отказом медиаплана, потому что другого
        источника нет: у сделки поверхности своим полем не существует. Берутся строки
        ИМЕННО этой услуги: в медиаплане бывают и другие (измерено 03.09.2026 — есть
        сделка с еФармом в продукте и Приоритезацией в строке).
        """
        if not product or product not in self.separate_price:
            return None
        return (self.surfaces.get(deal_id) or {}).get(product)

    def geo(self, deal_id: int) -> str | None:
        """Гео сделки = гео её медиаплана. Своего поля у сделки НЕТ.

        Заводить его отдельной колонкой было бы вторым ответом на тот же вопрос: гео
        задаётся в плане, оттуда же его печатает документ ДС (`app/sales/annex.py`),
        и разойтись двум значениям ничего не мешало бы.

        До 15.09.2026 на карточке сделки стоял ЗАШИТЫЙ прочерк — строка «Гео —»
        отрисовывалась всегда, чем бы ни был заполнен план. Жалоба владельца: «гео не
        тянется с МП в сделку». Данные при этом были на месте: 35 планов из 36
        привязанных с заполненным гео, и в ДС оно печаталось верно.

        Несколько планов с РАЗНЫМ гео — показываем оба через «·», а не выбираем
        победителя молча: молчаливый выбор здесь и есть то, на что жалуются.
        """
        return self.geos.get(deal_id)

    def apply(self, row: dict, deal) -> dict:
        """Дописывает в строку общие поля. Возвращает ту же строку — удобно в цепочке."""
        row["product_color"] = self.color(deal.product)
        row["inventory"] = self.inventory(deal.id, deal.product)
        row["docs"] = self.doc_kinds(deal.id)
        return row


# Свод набора поверхностей в одно значение. 'cross' в строке уже означает обе, поэтому
# он же и результат при встрече web с app: третьего слова для этого заводить незачем.
def merge_inventory(values: Iterable[str]) -> str | None:
    vals = {(v or "").strip().lower() for v in values} - {""}
    if not vals:
        return None
    if "cross" in vals or vals == {"web", "app"}:
        return "cross"
    return next(iter(vals))


def load_row_context(db: Session, deal_ids: Iterable[int]) -> RowContext:
    from app.sales.models import SalesDealFile, SalesService

    ids = list(deal_ids)
    docs: Dict[int, Set[str]] = {}
    raw: Dict[int, Dict[str, Set[str]]] = {}
    if ids:
        for did, kind in (db.query(SalesDealFile.deal_id, SalesDealFile.kind)
                          .filter(SalesDealFile.deal_id.in_(ids)).all()):
            docs.setdefault(did, set()).add(kind)
        # Последний медиаплан сделки, отклонённые не в счёт — то же правило, что у
        # плана показов в `app/ad/build.deal_plan`. Одним запросом на страницу.
        for r in db.execute(text("""
            SELECT mp.deal_id, r.position, r.inventory
              FROM sales_media_plan_rows r
              JOIN sales_media_plans mp ON mp.id = r.plan_id
             WHERE mp.deal_id = ANY(:ids)
               AND mp.id = (SELECT id FROM sales_media_plans x
                             WHERE x.deal_id = mp.deal_id
                               AND coalesce(x.status, '') <> 'rejected'
                             ORDER BY x.version DESC, x.id DESC LIMIT 1)
        """), {"ids": ids}).mappings():
            name = (r["position"] or "").strip()
            if name:
                raw.setdefault(r["deal_id"], {}).setdefault(name, set()).add(r["inventory"])

    # Гео из шапки планов сделки: старшая версия каждой группы (как и суммы —
    # app/sales/mp_amounts.py). Одна выборка на страницу.
    geos: Dict[int, str] = {}
    if ids:
        from app.sales.models import SalesGeo, SalesMediaPlan
        names = dict(db.query(SalesGeo.id, SalesGeo.name).all())
        per_deal: Dict[int, list] = {}
        seen_groups: Dict[int, Set[int]] = {}
        for pl in (db.query(SalesMediaPlan.deal_id, SalesMediaPlan.group_id,
                            SalesMediaPlan.geo_id)
                   .filter(SalesMediaPlan.deal_id.in_(ids))
                   .order_by(SalesMediaPlan.group_id, SalesMediaPlan.version.desc()).all()):
            groups = seen_groups.setdefault(pl.deal_id, set())
            if pl.group_id in groups:
                continue
            groups.add(pl.group_id)
            name = names.get(pl.geo_id)
            if name and name not in per_deal.setdefault(pl.deal_id, []):
                per_deal[pl.deal_id].append(name)
        geos = {did: " · ".join(vals) for did, vals in per_deal.items() if vals}

    surfaces = {did: {name: merge_inventory(vals) for name, vals in by_name.items()}
                for did, by_name in raw.items()}
    separate = {n for (n,) in db.query(SalesService.name)
                .filter(SalesService.separate_price.is_(True)).all()}
    return RowContext(service_color_map(db), docs, surfaces, separate, geos)
