# -*- coding: utf-8 -*-
"""Сопоставление строки Excel продаж («Клиент / Производитель») с нашим справочником (владелец 22.10.2026).

В Excel клиент записан не по канону: «BIOCAD (БИОКАД)», «Валента (Ингавирин, Граммидин)», «Акрихин аквадетрим»,
«ANTELIOS (Антелиос) - Roche». Правила:
- строка режется на части: основное, в скобках, через запятую / « - » / «/»;
- рекламодатель — по всем его написаниям (имя, краткое, англ., рус.), латиница и кириллица сравниваются через
  транслитерацию, с допуском на опечатку (сходство ≥ 0,88 для слов длиннее 4 букв);
- бренды — внутри найденного рекламодателя: все, чьё название встречается в строке;
- рекламодатель не нашёлся — бренд по всему справочнику (название ≥ 4 букв), рекламодатель — его.
Результат — `Match(advertiser_id, brand_ids, how)`; `None` — не сопоставилось. Чистая функция над справочником: базу не трогает."""
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import List, Optional

_TR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
               ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "i", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f",
                "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))
_LAT = [("ph", "f"), ("ck", "k"), ("w", "v"), ("x", "ks"), ("q", "k"), ("c", "k"), ("j", "i"), ("y", "i"), ("ts", "s"), ("kh", "h")]


def norm(s) -> str:
    return re.sub(r"[^a-zа-я0-9]+", " ", str(s or "").lower().replace("ё", "е")).strip()


def latin(s: str) -> str:
    """Одно написание на латиницу и кириллицу: «Биокад» и «Biocad» сходятся в «biokad»."""
    t = "".join(_TR.get(ch, ch) for ch in norm(s))
    for a, b in _LAT:
        t = t.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", t)          # «Novartiss» / «Novartis»


def parts(client: str) -> List[str]:
    s = str(client or "")
    out = [s]
    out += re.findall(r"\(([^)]*)\)", s)
    base = re.sub(r"\([^)]*\)", " ", s)
    out += re.split(r",|/| - | – |;", base)
    for inner in re.findall(r"\(([^)]*)\)", s):
        out += re.split(r",|/|;", inner)
    return [p for p in (norm(x) for x in out) if p]


@dataclass
class Match:
    advertiser_id: int
    brand_ids: List[int] = field(default_factory=list)
    how: str = ""


def _contains(hay: str, needle: str) -> bool:
    return bool(needle) and f" {needle} " in f" {hay} "


def _similar(a: str, b: str) -> bool:
    """Допуск на опечатку — только для ОДНОГО слова: в многословных «леовит онко» / «леовит окно» общий префикс даёт
    высокое сходство при разном смысле (сверка 22.10.2026). Многословное название должно войти в строку целиком."""
    if " " in a or " " in b:
        return False
    return len(a) > 4 and len(b) > 4 and SequenceMatcher(None, a, b).ratio() >= 0.88


class Directory:
    """advertisers: [(id, [написания])]; brands: [(id, advertiser_id, название)]."""

    def __init__(self, advertisers, brands):
        self.adv = [(aid, {latin(n) for n in names if n and len(latin(n)) >= 2}) for aid, names in advertisers]
        self.brands = [(bid, aid, latin(name)) for bid, aid, name in brands if name]

    def _adv_hits(self, client: str):
        ps = [latin(p) for p in parts(client)]
        whole = latin(client)
        hits = []
        for aid, names in self.adv:
            best = 0
            for n in names:
                if any(p == n for p in ps):
                    best = max(best, 100 + len(n))
                elif len(n) >= 6 and any(p.replace(" ", "") == n.replace(" ", "") for p in ps):
                    best = max(best, 90 + len(n))         # «материамедика» = «Materia Medica», «Астра Зенека» = «AstraZeneca»
                elif len(n) >= 4 and _contains(whole, n):
                    best = max(best, 50 + len(n))
                elif any(_similar(p, n) for p in ps) or any(_similar(w, n) for w in whole.split()):
                    best = max(best, 20 + len(n))
            if best:
                hits.append((best, aid))
        return sorted(hits, reverse=True)

    def _brands_of(self, client: str, aid: Optional[int]):
        whole = latin(client)
        ps = [latin(p) for p in parts(client)]
        out = []
        for bid, baid, b in self.brands:
            if aid is not None and baid != aid:
                continue
            if aid is None and len(b) < 4:
                continue
            if _contains(whole, b) or any(p == b or _similar(p, b) for p in ps):
                out.append((bid, baid))
        return out

    def match(self, client: str) -> Optional[Match]:
        hits = self._adv_hits(client)
        if hits:
            aid = hits[0][1]
            bs = [b for b, _ in self._brands_of(client, aid)]
            return Match(aid, bs, "рекламодатель" + (" и бренды" if bs else ""))
        bs = self._brands_of(client, None)
        advs = {a for _, a in bs}
        if len(advs) == 1:
            return Match(advs.pop(), [b for b, _ in bs], "бренд")
        return None

    def suggest(self, client: str, names: dict, n: int = 3) -> List[str]:
        """Ближайшие рекламодатели по сходству — подсказка в Excel несопоставленного."""
        w = latin(client)
        scored = sorted(((max((SequenceMatcher(None, w, x).ratio() for x in xs), default=0), aid) for aid, xs in self.adv), reverse=True)
        return [names.get(aid, str(aid)) for s, aid in scored[:n] if s >= 0.45]
