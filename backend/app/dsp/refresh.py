# -*- coding: utf-8 -*-
"""«Обновить данные в DSP» — перезаписать у УЖЕ заведённой РК ссылки, пиксели и таргеты
по текущим данным системы (владелец 02.10.2026).

Зачем отдельно от выгрузки (`provision`). Выгрузка заводит НЕДОСТАЮЩЕЕ и заведённое не
трогает; правила же меняются после заведения — домен кириллицей, `bid_rate`, посадочная
площадки, пиксель. Эта кнопка приводит уже заведённое к тому, что система отправила бы
сейчас, и ничего не создаёт.

Два шага, потому что запись в боевой кабинет: `plan` читает состояние ИЗ DSP и
показывает «было → станет», `apply_item` пишет по одному пункту — экран рисует ход
«3 из 14» настоящим прогрессом, а не анимацией по таймеру.

Пишет только туда, куда пишет выгрузка: строки, которые отказал бы `provision._blocker`
(площадка крутит сама, внешний канал, креатив без ЕРИД, отозванный, не согласованный),
не трогает и называет причину (ревью 02.10.2026).

Не делает: не заводит креативы и кампании, не меняет статусы запуска, не перезаливает
баннер. Копии нацеливания трогает только если у комплекта появился ЕРИД, которого у
копии нет (владелец 02.10.2026: «только РК, если не добавились ериды»).
"""
from __future__ import annotations

import html
import logging
from typing import Optional

from sqlalchemy.orm import Session

log = logging.getLogger("finance.dsp")

# Кто видит кнопку: Администратор и «Админ Трафик» (владелец 02.10.2026). «Мастер
# траффик» — нет, хотя признак мастера у него тот же, поэтому — по ключу роли.
REFRESH_ROLES = ("admin", "role_14")

CREATIVE_FIELDS = ("link", "adomain", "pixel")


def may_refresh(user) -> bool:
    return getattr(getattr(user, "role", None), "key", None) in REFRESH_ROLES


# ── сравнение «как в DSP» с «как надо» ───────────────────────────────────────

def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _flag(v) -> bool:
    """Флаг из ответа DSP: бывает bool, число или строка «0»/«1» — `bool("0")` это True."""
    return str(v).strip().lower() in ("1", "true")


def _checked(items: Optional[dict]) -> dict:
    return {k: (v or {}) for k, v in (items or {}).items() if _flag((v or {}).get("is_checked"))}


def same_items(a: Optional[dict], b: Optional[dict]) -> bool:
    """Совпадают ли пункты таргетинга по смыслу: ОТМЕЧЕННЫЕ ключи и ставки. Имя пункта —
    подпись кабинета, его DSP дописывает сама; неотмеченные пункты справочника не в счёт;
    ставки — числами (DSP может отдать строкой)."""
    a, b = _checked(a), _checked(b)
    return set(a) == set(b) and all(
        (_num(a[k].get("bid_rate")), _num(a[k].get("bid_start")))
        == (_num(b[k].get("bid_rate")), _num(b[k].get("bid_start"))) for k in a)


def _items_of(got) -> tuple:
    """(пункты, инверсия) из ответа `Targeting.getUserSetting`."""
    if not isinstance(got, dict):
        return {}, False
    d = got.get("targeting_data") if isinstance(got.get("targeting_data"), dict) else got
    items = d.get("items")
    # Инверсию DSP отдаёт в `settings` (замер 02.10.2026), а принимает плоско.
    inv = (d.get("settings") or {}).get("is_invert_mode", d.get("is_invert_mode"))
    return (items if isinstance(items, dict) else {}), _flag(inv)


def _same_str(have, want) -> bool:
    """Пробелы по краям и html-сущности (`&amp;` в пикселе) — не разница: иначе каждое
    нажатие писало бы то же самое заново."""
    return html.unescape(str(have or "")).strip() == html.unescape(str(want or "")).strip()


def _size(info: dict):
    """Размер из `Creative.getInfo` — поле `size` «WxH», у адаптивного «0x0» (замер
    02.10.2026). Не распознан — (None, None): тогда пиксель не трогаем."""
    w, _, h = str(info.get("size") or "").partition("x")
    return (int(w), int(h)) if (w.isdigit() and h.isdigit()) else (None, None)


def _short(v, n=90):
    v = "" if v is None else str(v)
    return v if len(v) <= n else v[:n] + "…"


def _summary(items: dict) -> str:
    on = _checked(items)
    zero = sum(1 for x in on.values() if not _num(x.get("bid_rate")))
    return f"{len(on)} отмечено" + (f", bid_rate 0 у {zero}" if zero else "")


# ── креатив ──────────────────────────────────────────────────────────────────

def creative_wants(row: dict) -> dict:
    """Что должно стоять у креатива в `link` / `adomain` — тем же правилом, что выгрузка."""
    from app.dsp import creatives as cr
    from app.launch_prep import pub_rules
    web = pub_rules.web_url(getattr(row.get("target"), "advertiser_url", None))
    return {"link": cr.landing_link(web), "adomain": cr.landing_adomain(web)}


def _skip_reason(row: dict, want_pixel: bool, ext_tag) -> Optional[str]:
    """Почему строку НЕ трогаем — правило выгрузки (`provision._blocker`)."""
    from app.dsp import provision as P
    try:
        return P._blocker(row, want_pixel, ext_tag)
    except P.DspProvisionError as e:
        return str(e)


def _creative_edit(row: dict, info: dict, want_pixel: bool, ext_tag) -> tuple:
    """(правка, заметка): только разошедшиеся поля. Пиксель не собрался или размер не
    распознан — пиксель не трогаем, ссылки пишем."""
    from app.dsp import provision as P
    want, note = creative_wants(row), None
    if want_pixel:
        w, h = _size(info)
        if w is None:
            note = "размер баннера в DSP не распознан — пиксель не трогаем"
        else:
            try:
                want["pixel"] = P.pixel_url(row, w, h, ext_tag, row["creative"].erid)
            except (ValueError, KeyError, AttributeError) as e:
                note = f"пиксель не собран — {e}"
    edit = {f: want[f] for f in CREATIVE_FIELDS
            if want.get(f) and not _same_str(info.get(f), want[f])}
    return edit, note


# ── план ─────────────────────────────────────────────────────────────────────

def plan(db: Session, camp, client=None) -> dict:
    """Что изменится, по состоянию ИЗ DSP. Ничего не пишет."""
    from app.ad.build import pixel_setup
    from app.dsp import provision as P
    from app.dsp import targeting as tg
    from app.dsp.client import MsClient, MsError

    if not camp.ms_campaign_xxhash:
        return {"items": [], "unchanged": 0,
                "notes": ["РК ещё не выгружена в DSP — сначала «В DSP»"]}
    c = client or MsClient()
    px = pixel_setup(db, camp.deal_id)
    want_pixel, ext_tag = px["needed"], px["tag"]
    all_rows = P._rows(db, camp)
    rows = [r for r in all_rows if (r["creative"].ms_creative_xxhash or "").strip()]
    items, notes, unchanged = [], [], 0

    for r in rows:
        cre, pub = r["creative"], r["publisher"]
        name = f"{cre.ms_title or cre.id} · {pub.name if pub else '?'}"
        why = _skip_reason(r, want_pixel, ext_tag)
        if why:
            notes.append(f"{name}: не трогаем — {why}")
            continue
        try:
            info = c.creative_get_info(cre.ms_creative_xxhash) or {}
        except MsError as e:
            items.append({"kind": "creative", "ref": cre.id, "what": name,
                          "error": str(e), "changes": []})
            continue
        edit, note = _creative_edit(r, info, want_pixel, ext_tag)
        if note:
            notes.append(f"{name}: {note}")
        if edit:
            items.append({"kind": "creative", "ref": cre.id, "what": name,
                          "changes": [{"field": f, "was": _short(info.get(f)), "will": _short(v)}
                                      for f, v in edit.items()]})
        else:
            unchanged += 1

    if tg.enabled(db):
        try:
            tplan = tg.plan_for(db, camp, all_rows)
        except Exception as e:  # noqa: BLE001 — план — строка отчёта, не 500
            tplan = None
            notes.append(f"таргетинги не посчитаны: {e}")
        if tplan:
            hashes = {r["creative"].id: r["creative"].ms_creative_xxhash for r in rows}
            targets = [("campaign", camp.ms_campaign_xxhash, key, body, "кампания")
                       for key, body in tplan["campaign"].items()]
            targets += [("creative", hashes[cid], key, body, f"креатив {cid}")
                        for cid, t in tplan["creatives"].items() if hashes.get(cid)
                        for key, body in t.items()]
            for owner, xx, key, body, label in targets:
                try:
                    have, inv = _items_of(c.targeting_get(xx, key))
                except MsError as e:
                    items.append({"kind": "targeting", "ref": f"{owner}:{xx}:{key}",
                                  "what": f"{label}: {key}", "error": str(e), "changes": []})
                    continue
                if same_items(have, body["items"]) and inv == _flag(body["is_invert_mode"]):
                    unchanged += 1
                    continue
                items.append({"kind": "targeting", "ref": f"{owner}:{xx}:{key}",
                              "what": f"{label}: {key}",
                              "changes": [{"field": key, "was": _summary(have),
                                           "will": _summary(body["items"])}]})
    else:
        notes.append("таргетинги не отправляются — выключатель dsp_targeting_enabled")

    try:
        items += _erid_copies(db, camp)
    except Exception as e:  # noqa: BLE001 — копии нацеливания не должны ронять план
        notes.append(f"копии нацеливания не проверены: {e}")
    return {"items": items, "unchanged": unchanged, "notes": notes}


def _erid_copies(db: Session, camp) -> list:
    """Копии нацеливания, у которых ЕРИД комплекта ещё не стоит (боевой появился позже)."""
    from app.dsp import targeting_creative as tc
    from app.dsp.client import MsError
    from app.launch_prep.models import LaunchPrepCreativeSet
    from app.routers.traffic_catalog import targeting_cabinet
    sets = (db.query(LaunchPrepCreativeSet)
            .filter(LaunchPrepCreativeSet.deal_id == camp.deal_id,
                    LaunchPrepCreativeSet.ms_targeting_creative_xxhash.isnot(None)).all())
    if not sets:
        return []
    partner, _ = targeting_cabinet(db)
    c = tc._client(partner or "")
    out = []
    for s in sets:
        erid = tc.erid_of(s)
        if erid == tc.TEST_ERID:
            continue
        try:
            have = ((c.creative_get_info(s.ms_targeting_creative_xxhash) or {})
                    .get("erid") or "").strip()
        except MsError as e:
            out.append({"kind": "erid", "ref": s.id, "what": f"копия нацеливания №{s.no}",
                        "error": str(e), "changes": []})
            continue
        if have != erid:
            out.append({"kind": "erid", "ref": s.id, "what": f"копия нацеливания №{s.no}",
                        "changes": [{"field": "erid", "was": have or "—", "will": erid}]})
    return out


# ── запись ───────────────────────────────────────────────────────────────────

def apply_item(db: Session, camp, kind: str, ref: str, client=None) -> dict:
    """Записать ОДИН пункт плана — под тем же замком, что выгрузка: параллельная выгрузка
    или второе окно не пишут те же объекты одновременно (ревью 02.10.2026)."""
    from app.dsp.provision import DSP_PROVISION, only_one
    with only_one(DSP_PROVISION, camp.id, ValueError, "Выгрузка или обновление в DSP"):
        return _apply_item(db, camp, kind, ref, client)


def _apply_item(db: Session, camp, kind: str, ref: str, client=None) -> dict:
    """Желаемое считается заново — не из того, что прислал экран: между планом и записью
    данные могли измениться, а клиенту верить нельзя."""
    from app.ad.build import pixel_setup
    from app.dsp import provision as P
    from app.dsp import targeting as tg
    from app.dsp.client import MsClient

    if kind == "erid":
        from app.dsp import targeting_creative as tc
        from app.launch_prep.models import LaunchPrepCreativeSet
        from app.routers.traffic_catalog import targeting_cabinet
        s = db.get(LaunchPrepCreativeSet, int(ref))
        if not s or s.deal_id != camp.deal_id or not s.ms_targeting_creative_xxhash:
            raise ValueError("копия нацеливания не найдена у этой РК")
        partner, _ = targeting_cabinet(db)
        c = tc._client(partner or "")
        info = c.creative_get_info(s.ms_targeting_creative_xxhash) or {}
        return {"changed": ["erid"] if tc._upgrade_erid(
            c, s.ms_targeting_creative_xxhash, s, info, f"tgt{s.id}") else []}

    c = client or MsClient()
    rows = P._rows(db, camp)
    if kind == "creative":
        r = next((x for x in rows if str(x["creative"].id) == str(ref)
                  and (x["creative"].ms_creative_xxhash or "").strip()), None)
        if r is None:
            raise ValueError("креатив не найден у этой РК или не выгружен в DSP")
        px = pixel_setup(db, camp.deal_id)
        why = _skip_reason(r, px["needed"], px["tag"])
        if why:
            raise ValueError(f"не трогаем — {why}")
        xx = r["creative"].ms_creative_xxhash
        info = c.creative_get_info(xx) or {}
        edit, note = _creative_edit(r, info, px["needed"], px["tag"])
        if edit:
            c.creative_edit(xx, edit, local_ref=f"cr{r['creative'].id}")
        return {"changed": sorted(edit), "note": note}

    if kind == "targeting":
        owner, xx, key = str(ref).split(":", 2)
        tplan = tg.plan_for(db, camp, rows)
        if owner == "campaign":
            if xx != camp.ms_campaign_xxhash:
                raise ValueError("таргетинг не этой РК")
            body = tplan["campaign"].get(key)
        else:
            cid = next((r["creative"].id for r in rows
                        if r["creative"].ms_creative_xxhash == xx), None)
            body = (tplan["creatives"].get(cid) or {}).get(key) if cid else None
        if body is None:
            raise ValueError(f"в текущем плане таргетинга нет «{key}»")
        c.targeting_set(xx, key, body["items"], body["is_invert_mode"])
        return {"changed": [key]}

    raise ValueError(f"неизвестный пункт: {kind}")
