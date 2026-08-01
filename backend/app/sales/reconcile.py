"""Матчинг наших справочников с компаниями Битрикса. Чистая логика (без БД/сети)."""
from app.sales.normalize import normalize_name

TYPE_ID = {"agencies": "SUPPLIER", "advertisers": "UC_S19G49"}

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
}
# Правовые формы и «шумовые» слова — выкидываем перед сравнением.
# ВАЖНО: токены проверяются ПОСЛЕ транслита, поэтому здесь — латинские формы.
_LEGAL = {
    "ooo", "oao", "zao", "ao", "pao", "nao", "ip", "chou", "ano",
    "llc", "ltd", "inc", "gmbh", "co", "corp", "company", "group", "groupp",
    "gruppa", "grupp", "holding", "holdings",
}


def translit(s: str) -> str:
    out = []
    for ch in (s or "").lower():
        out.append(_TRANSLIT.get(ch, ch))
    return "".join(out)


def name_tokens(raw: str) -> set[str]:
    base = translit(normalize_name(raw))
    cleaned = "".join(c if c.isalnum() else " " for c in base)
    tokens = {t for t in cleaned.split() if len(t) >= 2 and t not in _LEGAL}
    return tokens


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def score_names(our_variants: list[str], bx_title: str) -> float:
    bx = name_tokens(bx_title)
    best = 0.0
    for v in our_variants:
        if not v:
            continue
        best = max(best, _jaccard(name_tokens(v), bx))
        if best == 1.0:
            break
    return best


def _variants(row: dict) -> list[str]:
    return [row.get("short_name"), row.get("name"), row.get("name_en"), row.get("name_ru")]


def _full_label(row: dict) -> str:
    """Полное название из нашего справочника: «краткое | ENG | Рус» (что заполнено)."""
    parts = [row.get("short_name") or row.get("name"), row.get("name_en"), row.get("name_ru")]
    seen, uniq = set(), []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            uniq.append(p)
    return " | ".join(uniq)


def _bx_ids(row: dict) -> list[str]:
    return [str(x).strip() for x in (row.get("bx_ids") or []) if str(x).strip()]


def standard_name(row: dict) -> str:
    """«Наш стандарт» для переименования компании в Битриксе: Short | ENG | Рус | Холдинг.
    Short не пишем, если он совпадает с одним из полных имён (ENG/Рус). Дедуп без регистра."""
    short = row.get("short_name") or row.get("name")
    en, ru, holding = row.get("name_en"), row.get("name_ru"), row.get("holding")
    fulls_lower = {x.lower() for x in (en, ru) if x}
    parts = []
    if short and short.lower() not in fulls_lower:
        parts.append(short)
    for x in (en, ru, holding):
        if x:
            parts.append(x)
    seen, uniq = set(), []
    for p in parts:
        k = p.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return " | ".join(uniq)


def build_buckets(our_rows: list[dict], bx_companies: list[dict]) -> dict:
    all_bitrix = [{"id": str(c["id"]), "title": c.get("title") or ""} for c in bx_companies]
    bx_by_id = {c["id"]: c for c in all_bitrix}
    linked, candidates, only_ours = [], [], []

    # Сначала собираем ВСЕ уже привязанные компании, чтобы они не предлагались как
    # кандидаты другим записям. Кандидатов матчим только против свободных (available).
    linked_bx_ids = {i for row in our_rows for i in _bx_ids(row)}
    available = [c for c in all_bitrix if c["id"] not in linked_bx_ids]

    for row in our_rows:
        ids = _bx_ids(row)
        short = row.get("short_name") or row["name"]
        full = _full_label(row)
        if ids:
            linked.append({
                "our_id": row["id"], "our_name": short, "our_full": full,
                "our_holding": row.get("holding"), "our_deal_count": row.get("deal_count"),
                "our_standard": standard_name(row), "bx_master": row.get("bx_master"),
                "companies": [{"bx_id": i, "bx_title": (bx_by_id.get(i) or {}).get("title", "")}
                              for i in ids],
            })
            continue
        variants = _variants(row)
        scored = sorted(
            ((c, score_names(variants, c["title"])) for c in available),
            key=lambda t: t[1], reverse=True,
        )
        scored = [(c, s) for c, s in scored if s > 0.0]
        if scored:
            best_c, best_s = scored[0]
            candidates.append({
                "our_id": row["id"], "our_name": short, "our_full": full,
                "our_holding": row.get("holding"), "our_deal_count": row.get("deal_count"),
                "best": {"bx_id": best_c["id"], "bx_title": best_c["title"], "score": round(best_s, 3)},
                "alternates": [
                    {"bx_id": c["id"], "bx_title": c["title"], "score": round(s, 3)}
                    for c, s in scored[1:6]
                ],
            })
        else:
            only_ours.append({
                "our_id": row["id"], "our_name": short, "our_full": full,
                "our_holding": row.get("holding"), "our_deal_count": row.get("deal_count"),
                "pending_create": row.get("bx_master") == "ours",
            })

    # «Только в Битриксе» = компании без нашей пары: не связаны И не предложены
    # как лучший кандидат кому-либо (иначе одна компания попала бы в две корзины).
    claimed = linked_bx_ids | {c["best"]["bx_id"] for c in candidates}
    # dict(c) — независимые копии: роутер дописывает deal_count, не пачкая all_bitrix.
    only_bitrix = [dict(c) for c in all_bitrix if c["id"] not in claimed]
    return {
        "linked": linked, "candidates": candidates,
        "only_ours": only_ours, "only_bitrix": only_bitrix, "all_bitrix": all_bitrix,
    }


def plan_auto_link(candidates: list[dict], threshold: float, taken_bx_ids: set[str]) -> dict:
    to_link, skipped = [], []
    used = set(taken_bx_ids)
    # Сначала самые уверенные — чтобы при коллизии bx_id победил максимальный score.
    for cand in sorted(candidates, key=lambda c: c["best"]["score"], reverse=True):
        bxid, score = cand["best"]["bx_id"], cand["best"]["score"]
        if score < threshold:
            skipped.append({"our_id": cand["our_id"], "reason": "below_threshold"})
        elif bxid in used:
            skipped.append({"our_id": cand["our_id"], "reason": "bx_id_taken"})
        else:
            used.add(bxid)
            to_link.append({"our_id": cand["our_id"], "bx_id": bxid})
    return {"to_link": to_link, "skipped": skipped}
