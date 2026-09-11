# -*- coding: utf-8 -*-
"""Где в WCM живут НАШИ размещения. Чистая логика.

⚠ ЭТОТ МОДУЛЬ БЫЛ НАПИСАН ПОД ДРУГУЮ МОДЕЛЬ И ПЕРЕПИСАН 09.09.2026 ПОСЛЕ ЖИВОГО ВЫЗОВА.

Сначала я считал, что `ad_space` — это площадка, и строил сопоставление «наш паблишер →
их ad_space» по домену, с правилом «ноль или два кандидата — не угадываем». Первый живой
запрос показал, что задачи такой нет:

  · каталог `ad_spaces` у них ГЛОБАЛЬНЫЙ — 1080 записей, включая французские сайты
    (`Biba`, `Autojournal.Fr`), у большинства `site_url` пуст;
  · **ни одного из наших 19 доменов там нет**;
  · зато есть ОДИН ad_space `SIMB-AD` (id 1080, тип Site, сеть 106), и ВСЕ наши вставки
    висят на нём.

Значит `ad_space_id` и `ad_network_id` — константы аккаунта, а «какая площадка» несёт
ТОЛЬКО метка вставки (`SIMB-AD_banner_Desktop_<кампания>_<домен>`). Отсюда два следствия,
которые дороже всего было бы выяснить потом: уникальность метки — не формальность шаблона,
а единственный различитель площадок; и никакого «завести площадку в Weborama» не бывает.

Урок метода: правило «не угадывать при двух кандидатах» было верным, а задача — выдуманной.
Проверять надо не только КАК решаем, но и ЧТО решаем ([[measure-before-claiming]]).
"""
from typing import Any, Optional

# Метка нашего ad_space в их каталоге. Не id: id проверяем по метке, а не наоборот, —
# у нового аккаунта он будет другим, а имя останется тем же.
OUR_AD_SPACE_LABEL = "SIMB-AD"

_ID_KEYS = ("id", "ad_space_id")
_LABEL_KEYS = ("label", "name", "title", "external_name")


def _rows(payload: Any) -> list:
    """Список из ответа. У них обёртка `{start_index, items_per_page, total_result, list}`;
    остальные варианты оставлены на случай, если другая ручка ответит иначе."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("list", "ad_spaces", "adspaces", "data", "items", "result", "results"):
            v = payload.get(key)
            if isinstance(v, list):
                return [r for r in v if isinstance(r, dict)]
        vals = [v for v in payload.values() if isinstance(v, dict)]
        if vals:
            return vals
    return []


def total_result(payload: Any) -> Optional[int]:
    """Сколько записей ВСЕГО. Ответ постраничный (`items_per_page` по умолчанию 50), и
    без этого числа легко решить, что у них полсотни площадок, а не тысяча."""
    if isinstance(payload, dict):
        v = payload.get("total_result")
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    return None


def _field(row: dict, keys) -> Optional[str]:
    for k in keys:
        v = row.get(k)
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v).strip()
    return None


def ad_space_index(payload: Any) -> list:
    """`{id, label, network, kind}` по каждой записи страницы."""
    out = []
    for row in _rows(payload):
        wid = _field(row, _ID_KEYS)
        if not wid:
            continue
        out.append({"id": wid,
                    "label": _field(row, _LABEL_KEYS) or "",
                    "network": row.get("ad_network_id"),
                    "kind": row.get("ad_space_type"),
                    "status": row.get("status")})
    return out


def find_our_ad_space(payload: Any, label: str = OUR_AD_SPACE_LABEL) -> dict:
    """Найти НАШ ad_space по метке. Возвращает `{id, network}` либо `{id: None, reason}`.

    Сравнение по метке без учёта регистра — как и у позиций: их имена набирает человек.
    Два совпадения не выбираем сами: в чужом каталоге одноимённые записи означают, что
    кто-то завёл вторую, и решать это должен человек.
    """
    want = (label or "").strip().lower()
    hits = [r for r in ad_space_index(payload) if r["label"].strip().lower() == want]
    if len(hits) == 1:
        return {"id": hits[0]["id"], "network": hits[0]["network"],
                "label": hits[0]["label"]}
    if not hits:
        return {"id": None, "reason": f"в каталоге нет ad_space с меткой «{label}» — "
                                      f"проверьте, всю ли страницу выгрузили"}
    return {"id": None, "reason": f"под меткой «{label}» найдено {len(hits)} записей — "
                                  f"выберите руками"}


__all__ = ["ad_space_index", "find_our_ad_space", "total_result", "OUR_AD_SPACE_LABEL"]
