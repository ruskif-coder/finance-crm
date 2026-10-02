"""Таргетинги РК в DSP: что ставим кампании и каждому креативу (документ «таргеты симбад»,
сверено с каталогами боевого кабинета 28.09.2026 — docs/DSP_что_передаём_2026-09-28.md).

Уровни — как в кабинете: у кампании общие настройки (источник, регион, соцдем, частота),
у креатива — свои блоки площадки: креатив у нас заводится на площадку, и показываться он
должен только в её блоках. Демо-прогон 28.09.2026 подтвердил: наследование у креатива —
по каждому таргету отдельно, свои блоки не отключают источник и регион кампании.

Решения владельца 28.09.2026 (§8 документа): ставка источника 100; первая версия —
источник, регион, блоки, частота, соцдем; частота больше 5 → ещё `6p` (6–10); соцдем — из
медиаплана, иначе М/Ж 25–55. Отправку можно выключить настройкой `dsp_targeting_enabled` = `0`.

Ключи каталога DSP — строками здесь, а не угадываются: в документе нумерация возрастов
сдвинута на один (там `age2` — 25–30, в кабинете 18–24), и ошибка молча сузила бы
аудиторию до другой.
"""
import re
from typing import Dict, Iterable, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

ENABLED_SETTING = "dsp_targeting_enabled"
BID_SETTING = "dsp_source_bid"
DEFAULT_SOURCE_BID = 100                     # решение владельца 28.09.2026

# Регион по умолчанию: вся РФ и отдельно Крым — гео-база DSP (MaxMind) Крым в РФ не кладёт.
GEO_DEFAULT = (("2017370", "Россия"), ("68681200", "Республика Крым"))

# Каталог `socdem` боевого кабинета (чтение 28.09.2026): группа → ключ и её середина. По
# середине решается, входит ли группа в диапазон медиаплана: «30–60» не берёт 25–30.
AGE_KEYS = ((0, 17, "age1", 12), (18, 24, "age2", 21), (25, 30, "age3", 27.5),
            (31, 35, "age4", 33), (36, 40, "age5", 38), (41, 45, "age6", 43),
            (46, 50, "age7", 48), (51, 55, "age8", 53), (56, 60, "age9", 58),
            (61, 200, "age10", 63))
SOCDEM_DEFAULT = {"age_from": 25, "age_to": 55, "sexes": ("man", "woman")}

FREQ_DEFAULT = 5                             # номера показа 1–5 — умолчание документа


def _checked(bid_key: str = "bid_rate", bid=1, name: Optional[str] = None) -> dict:
    out = {"is_checked": True, bid_key: bid}
    if name:
        out["name"] = name
    return out


def source_items(keys: Iterable[str], bid) -> dict:
    """Источники. Ставка — `bid_start` (так в образце документа для источников), и
    `bid_rate: 1`, как у остальных таргетингов: без него DSP читает коэффициент как 0
    (правка DSP 02.10.2026)."""
    return {k: {**_checked(), "bid_start": bid} for k in sorted(set(keys)) if k}


def geo_items(regions=GEO_DEFAULT) -> dict:
    return {gid: _checked(name=name) for gid, name in regions}


def placement_items(block_ids: Iterable[str]) -> dict:
    return {str(b).strip(): _checked() for b in block_ids if str(b or "").strip()}


def frequency_keys(freq) -> List[str]:
    """Частота N из медиаплана → номера показа `1`…`N`. Пусто — по умолчанию 5.
    Больше пяти — `1`…`5` и `6p` (6–10): так решил владелец 28.09.2026."""
    try:
        n = int(round(float(freq)))
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        n = FREQ_DEFAULT
    keys = [str(i) for i in range(1, min(n, 5) + 1)]
    if n > 5:
        keys.append("6p")
    return keys


def frequency_items(freq) -> dict:
    return {k: _checked() for k in frequency_keys(freq)}


def socdem_keys(age_from: int, age_to: int, sexes=("man", "woman")) -> List[str]:
    """Пол плюс возрастные группы, чья середина в диапазоне. 25–55 → age3…age8."""
    ages = [k for _lo, _hi, k, mid in AGE_KEYS if age_from <= mid <= age_to]
    return list(sexes) + ages


def socdem_items(age_from=25, age_to=55, sexes=("man", "woman")) -> dict:
    return {k: _checked() for k in socdem_keys(age_from, age_to, sexes)}


_WOMAN = re.compile(r"(^|[^А-Яа-яЁё])ж([^А-Яа-яЁё]|$)|женщ", re.I)
_MAN = re.compile(r"(^|[^А-Яа-яЁё])м([^А-Яа-яЁё]|$)|мужч", re.I)
_RANGE = re.compile(r"(\d{1,2})\s*[-–—]\s*(\d{1,2})")
_PLUS = re.compile(r"(\d{1,2})\s*\+")
_UPTO = re.compile(r"до\s*(\d{1,2})", re.I)


def parse_audience(texts) -> Optional[dict]:
    """Аудитория медиаплана свободным текстом → {age_from, age_to, sexes}. Не разобралось — None.

    «Ж/М 30–60», «Ж 25-45», «М 18+», «до 45». Несколько строк — объединение: самая младшая
    нижняя граница и самая старшая верхняя; пол — все упомянутые, не упомянут — оба."""
    lows, highs, sexes = [], [], set()
    for t in texts or []:
        s = str(t or "")
        if _WOMAN.search(s):
            sexes.add("woman")
        if _MAN.search(s):
            sexes.add("man")
        m = _RANGE.search(s)
        if m:
            lows.append(int(m.group(1)))
            highs.append(int(m.group(2)))
            continue
        m = _PLUS.search(s)
        if m:
            lows.append(int(m.group(1)))
            highs.append(200)
            continue
        m = _UPTO.search(s)
        if m:
            lows.append(0)
            highs.append(int(m.group(1)))
    if not lows and not sexes:
        return None
    return {"age_from": min(lows) if lows else SOCDEM_DEFAULT["age_from"],
            "age_to": max(highs) if highs else SOCDEM_DEFAULT["age_to"],
            "sexes": tuple(x for x in ("man", "woman") if x in sexes) or SOCDEM_DEFAULT["sexes"]}


def data(items: dict, invert: bool = False) -> dict:
    """Тело `targeting_data` для `Targeting.setUserSetting`."""
    return {"is_invert_mode": invert, "items": items}


# ─────────────────────────────── из базы ───────────────────────────────

def _setting(db: Session, key: str) -> str:
    return (db.execute(text("SELECT value FROM company_settings WHERE key = :k"),
                       {"k": key}).scalar() or "").strip()


def enabled(db: Session) -> bool:
    """Отправка таргетингов. Включена, пока настройка не `0` (состав согласован владельцем
    28.09.2026). Настройка не прочиталась — «выключено»: запись в чужой кабинет вслепую
    не делается."""
    try:
        return _setting(db, ENABLED_SETTING) != "0"
    except Exception:  # noqa: BLE001
        return False


def _media_plan(db: Session, deal_id: int) -> tuple:
    """(частота — наибольшая по строкам, аудитория) последнего неотклонённого плана сделки."""
    row = db.execute(text("""
        SELECT (SELECT max(NULLIF(r.forecast->>'freq', '')::float)
                  FROM sales_media_plan_rows r WHERE r.plan_id = p.id),
               p.targeting->'audience'
          FROM sales_media_plans p
         WHERE p.deal_id = :d AND p.status <> 'rejected'
         ORDER BY p.version DESC LIMIT 1
    """), {"d": deal_id}).first()
    if not row:
        return None, None
    aud = row[1]
    return row[0], (aud if isinstance(aud, list) else ([aud] if aud else None))


def _blocks(db: Session, publisher_ids) -> Dict[tuple, list]:
    """(площадка, поверхность) → id блоков DSP: активные блоки реестра и блок по умолчанию
    поверхности («кукуха2» — DSP цепляет его к креативу сам; выпади он из белого списка,
    креатив перестал бы показываться и там)."""
    ids = list(publisher_ids)
    if not ids:
        return {}
    out: Dict[tuple, list] = {}
    for pid, kind, bid in db.execute(text("""
        SELECT s.publisher_id, s.kind, b.ms_block_id
          FROM sales_publisher_surfaces s
          JOIN publisher_block b ON b.surface_id = s.id
         WHERE s.publisher_id = ANY(:p) AND b.is_active AND coalesce(b.ms_block_id, '') <> ''
         UNION
        SELECT s.publisher_id, s.kind, s.default_ms_block_id
          FROM sales_publisher_surfaces s
         WHERE s.publisher_id = ANY(:p) AND coalesce(s.default_ms_block_id, '') <> ''
    """), {"p": ids}).all():
        out.setdefault((pid, kind), []).append(str(bid))
    return {k: sorted(set(v), key=lambda x: (len(x), x)) for k, v in out.items()}


def plan_for(db: Session, camp, rows: list) -> dict:
    """Что уйдёт: {campaign: {target_key: targeting_data}, creatives: {creative_id: {...}},
    summary}. `rows` — строки выгрузки (`provision._rows`)."""
    from app.dsp.sources import source_key
    from app.launch_prep.models import LaunchPrepPair, LaunchPrepTarget

    pair_ids = {r["creative"].pair_id for r in rows if r["creative"].pair_id}
    surf_of_pair = {}
    if pair_ids:
        for pid, kind in (db.query(LaunchPrepPair.id, LaunchPrepTarget.surface_kind)
                          .join(LaunchPrepTarget, LaunchPrepTarget.id == LaunchPrepPair.target_id)
                          .filter(LaunchPrepPair.id.in_(pair_ids)).all()):
            surf_of_pair[pid] = (kind or "web").lower()
    blocks = _blocks(db, {r["placement"].publisher_id for r in rows})

    surfaces = set()
    creatives, no_blocks = {}, []
    for r in rows:
        cre, pl = r["creative"], r["placement"]
        kind = surf_of_pair.get(cre.pair_id, "web")
        surfaces.add(kind)
        ids = blocks.get((pl.publisher_id, kind), [])
        if not ids:
            no_blocks.append(cre.id)
            continue
        creatives[cre.id] = {"placement": data(placement_items(ids))}

    try:
        bid = int(_setting(db, BID_SETTING) or DEFAULT_SOURCE_BID)
    except ValueError:
        bid = DEFAULT_SOURCE_BID
    freq, audience = _media_plan(db, camp.deal_id)
    parsed = parse_audience(audience)
    socdem = parsed or dict(SOCDEM_DEFAULT)
    campaign = {
        "source": data(source_items([source_key(db, k) for k in (surfaces or {"web"})], bid)),
        "geo_id": data(geo_items()),
        "uniq_show_creative": data(frequency_items(freq)),
        "socdem": data(socdem_items(**socdem)),
    }
    return {
        "enabled": enabled(db),
        "campaign": campaign,
        "creatives": creatives,
        "summary": {
            "sources": sorted(campaign["source"]["items"]),
            "source_bid": bid,
            "geo": [n for _, n in GEO_DEFAULT],
            "frequency": frequency_keys(freq),
            "frequency_from_plan": freq,
            "socdem": socdem_keys(**socdem),
            # Откуда соцдем: строка аудитории медиаплана или «по умолчанию» (None).
            "socdem_from_plan": ", ".join(map(str, audience)) if parsed else None,
            "creatives_with_blocks": len(creatives),
            "blocks": sum(len(v["placement"]["items"]) for v in creatives.values()),
            "creatives_without_blocks": no_blocks,
        },
    }


def apply(client, plan: dict, campaign_xxhash: str, creative_hash: Dict[int, str]) -> dict:
    """Поставить таргеты. Кампания — по её хешу, блоки — креативам, у которых хеш есть.
    Отказ по одному таргету не отменяет остальных: причина уходит в отчёт."""
    from app.dsp.client import MsError
    done, failed = [], []
    for key, body in plan["campaign"].items():
        try:
            client.targeting_set(campaign_xxhash, key, body["items"], body["is_invert_mode"])
            done.append(f"кампания: {key}")
        except MsError as e:
            failed.append({"what": f"кампания: {key}", "error": str(e)})
    for cid, targets in plan["creatives"].items():
        xx = creative_hash.get(cid)
        if not xx:
            continue
        for key, body in targets.items():
            try:
                client.targeting_set(xx, key, body["items"], body["is_invert_mode"])
                done.append(f"креатив {cid}: {key}")
            except MsError as e:
                failed.append({"what": f"креатив {cid}: {key}", "error": str(e)})
    return {"done": done, "failed": failed}
