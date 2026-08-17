"""Общие куски строки сделки для всех витрин.

Реестр сделок и очередь аккаунта отдают разные наборы полей, но два поля у них
обязаны совпадать: цвет услуги и список приложенных документов. Пока они считались
на месте в каждом сериализаторе, выражение было продублировано дословно — а третий
экран скопировал бы его в третий раз, и первая же правка (например «Акт тоже считать
закрывающим») разъехалась бы по копиям.

Здесь одна загрузка контекста на страницу и одна функция, которая кладёт эти поля
в строку. Выборки ограничены переданными id — таблицы файлов и планов растут вместе
с архивом, и читать их целиком ради двадцати строк незачем.
"""
from typing import Dict, Iterable, List, Set

from sqlalchemy.orm import Session

from app.sales.colors import service_color_map, auto_color


class RowContext:
    """Справочные данные под страницу сделок: цвета услуг и документы по сделкам."""

    def __init__(self, colors: Dict[str, str], docs: Dict[int, Set[str]]):
        self.colors = colors
        self.docs = docs

    def color(self, product: str | None) -> str:
        """Цвет услуги. Имени нет в справочнике (услуга удалена или не сматчена
        синком) — отдаём авто-цвет: маркер должен быть у любой строки."""
        return self.colors.get(product) or auto_color(product or "")

    def doc_kinds(self, deal_id: int) -> List[str]:
        return sorted(self.docs.get(deal_id, ()))

    def apply(self, row: dict, deal) -> dict:
        """Дописывает в строку общие поля. Возвращает ту же строку — удобно в цепочке."""
        row["product_color"] = self.color(deal.product)
        row["docs"] = self.doc_kinds(deal.id)
        return row


def load_row_context(db: Session, deal_ids: Iterable[int]) -> RowContext:
    from app.sales.models import SalesDealFile

    ids = list(deal_ids)
    docs: Dict[int, Set[str]] = {}
    if ids:
        for did, kind in (db.query(SalesDealFile.deal_id, SalesDealFile.kind)
                          .filter(SalesDealFile.deal_id.in_(ids)).all()):
            docs.setdefault(did, set()).add(kind)
    return RowContext(service_color_map(db), docs)
