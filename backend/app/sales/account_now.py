# -*- coding: utf-8 -*-
"""Блок «Сейчас» расхлопа и модалки «Моих сделок» (v5, 13.11.2026; хендофф design_handoff_account_dashboard_v5, `detailOf`).

Шаги стадий и виджет текущей стадии — одним запросом при раскрытии строки:
  · песочница и бронь — плитки (возраст МП / старт / бюджет / медиаплан / бронь);
  · «Готовятся к старту» — «Сборка» по шагам: креативы (аккаунт) → проверка комплекта (трафик) → согласование баннера
    (площадки) → ЕРИД (система) → РК (трафик); у шага — прогресс и статус;
  · «В размещении» — «Рекламная кампания»: план, факт, переходы, потенциал недокрута, крутит площадок; полоса открутки
    с отметкой плана на сегодня (`deal_delivery`, то же, что дашборд трафика);
  · «Итоговая сверка» — здесь не считается: расхлоп показывает блок сверки карточки целиком (`ClosingBlock`, владелец 13.11.2026).
Своих правил здесь нет: всё — из существующих расчётов; модуль только собирает их в форму экрана."""
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.final_recon import flow as FLOW
from app.final_recon.money import r2
from app.sales import account_turn as AT
from app.sales import stage_slots as SS

WORK_STEPS = [SS.BOOKING, SS.PREP, SS.LIVE, SS.RECON, "Документы"]
SANDBOX_STEPS = [SS.MP_PREP, SS.MP_SENT, SS.BOOKING]
SLOT_STEP = {"booking": 0, "prep": 1, "live": 2, "recon": 3}


def _r(v) -> Optional[float]:
    return None if v is None else r2(v)


def assembly(sets: int, checked: int, pairs_ok: int, pairs: int, erid_sets: int, rk_ready: bool) -> list:
    """Строки «Сборки». Комплект креативов есть — значит загружен. Состояние шага: ok — готово, go — идёт,
    warn — стоит и это ход аккаунта, wait — ещё рано (предыдущий шаг не закрыт)."""
    cr = sets > 0
    ch = cr and checked >= sets
    agreed = bool(pairs) and pairs_ok >= pairs
    erid_all = cr and erid_sets >= sets
    return [
        {"key": "creatives", "label": "Креативы", "who": "аккаунт", "state": "ok" if cr else "warn",
         "text": f"загружены · комплектов {sets}" if cr else "не загружены — запуск стоит", "done": sets, "total": sets},
        {"key": "check", "label": "Проверка комплекта", "who": "трафик", "state": "wait" if not cr else ("ok" if ch else "go"),
         "text": "после загрузки креативов" if not cr else ("проверен" if ch else f"проверено {checked} из {sets}"),
         "done": checked, "total": sets},
        {"key": "sites", "label": "Согласование баннера", "who": "площадки", "state": "wait" if not checked else ("ok" if agreed else "go"),
         "text": "после проверки трафиком" if not checked else ("баннер ещё не ушёл площадкам" if not pairs else
                                                                 "все площадки согласовали" if agreed else f"согласовали {pairs_ok} из {pairs}"),
         "done": pairs_ok, "total": pairs},
        {"key": "erid", "label": "ЕРИД", "who": "система", "state": "ok" if erid_all else ("go" if erid_sets else "wait"),
         "text": "получен по всем комплектам" if erid_all else (f"получен {erid_sets} из {sets}" if erid_sets else "после согласования"),
         "done": erid_sets, "total": sets},
        {"key": "rk", "label": "РК", "who": "трафик", "state": "ok" if rk_ready else ("go" if erid_all else "wait"),
         "text": "заведена" if rk_ready else ("трафик заводит РК" if erid_all else "после ЕРИД"), "done": 0, "total": 0},
    ]


LAUNCH_KEYS = {"creatives_accepted", "placements_approved", "erid_issued", "campaign_ready", "one_pair_ready",
               "weborama_pixel", "prio_live"}
EXTRAS = {"weborama_pixel": ("pixel", "Пиксель Weborama"), "one_pair_ready": ("pair", "Площадка собрана к запуску")}
ANCHOR = {"erid": "#sec-ord", "sent": "#sec-prio", "approved": "#sec-prio", "live": "#sec-prio"}


def doc_rows(lines: list) -> list:
    """Незакрытые требования-документы стадии (договор, плательщик, виза МП…) — [(key, title, state, detail, link)].
    Закрытые и неприменимые не показываем; шаги запуска считает `assembly`, здесь их нет."""
    return [{"key": k, "label": t, "who": "аккаунт", "state": "warn", "text": d or "не закрыто", "link": ln, "done": 0, "total": 0}
            for k, t, st, d, ln in lines if k not in LAUNCH_KEYS and st in ("not_yet", "unknown")]


def launch_extras(lines: list) -> list:
    """Два шага запуска сверх «Сборки»: пиксель Weborama (где заказан) и «хотя бы одна площадка собрана к запуску»."""
    out = []
    for k, _t, st, d, _ln in lines:
        if k in EXTRAS and st in ("ok", "not_yet"):
            key, label = EXTRAS[k]
            out.append({"key": key, "label": label, "who": "трафик", "state": "ok" if st == "ok" else "go",
                        "text": d or ("готово" if st == "ok" else "не готово"), "done": 0, "total": 0})
    return out


def _anchor(link: str) -> str:
    """Якорь карточки: секция раскрывается только по `#sec-<id>` (`components/deal/Section.js`)."""
    if not link:
        return "#sec-creatives"
    return "#sec-" + link[1:] if link.startswith("#") and not link.startswith("#sec-") else link


def assembly_head(docs: list, rows: list) -> dict:
    """Шапка «Сборки» — первый незакрытый пункт (сначала документы, потом запуск) и куда в карточке продолжать."""
    if not docs and not rows:
        return {"text": "сборка не требуется — запуск кнопкой «Запустить» в карточке", "href": "#sec-head"}
    if docs:
        return {"text": f"{docs[0]['label']}: {docs[0]['text']}", "href": _anchor(docs[0]["link"])}
    for r in rows:
        if r["state"] in ("warn", "go"):
            return {"text": f"{r['label']}: {r['text']}", "href": ANCHOR.get(r["key"], "#sec-creatives")}
    return {"text": "собрано — можно в размещение", "href": "#sec-prio" if rows and rows[0]["key"] == "sent" else "#sec-creatives"}


ORD_KEYS = ("payer_set", "final_contract", "ord_initial_contract", "erid_issued")


def _chip(key, label, value, tone, href):
    return {"key": key, "label": label, "value": value, "tone": tone, "href": href}


def assembly_chips(lines: list, counts: tuple, flow: str, pixel: tuple, ds: list) -> list:
    """Сборка в расхлопе — четыре плашки: ОРД · креативы · пиксель · ДС (владелец 13.11.2026).

    `lines` — требования стадии [(key, title, state, detail, link)]; `counts` — (комплектов, проверено, пар согласовано,
    пар всего); `pixel` — (заказан, решение принято); `ds` — ДС сделки (`master_deal.deal_docs`). Тон: ok / warn / off."""
    by = {k: (t, st, d) for k, t, st, d, _ in lines}
    need = [k for k in ORD_KEYS if k in by and by[k][1] != "n/a"]
    done = [k for k in need if by[k][1] == "ok"]
    if need and len(done) == len(need):
        ordc = _chip("ord", "ОРД", "цепочка сошлась", "ok", "#sec-ord")
    else:
        ordc = _chip("ord", "ОРД", f"{len(done)} из {len(need)}" if need else "не проверено", "warn", "#sec-ord")

    sets, checked, pairs_ok, pairs = counts
    # Матрица требований по услугам (Справочники → Услуги): креативы, согласование и ЕРИД — пункты полного цикла; у контура аккаунта
    # (OLV, Альфарм-Таргет, Polza) их нет — плашка не показывается (владелец 14.11.2026: «под OLV нам ничего не требуется»).
    need_cr = any(k in by for k in ("creatives_accepted", "placements_approved", "one_pair_ready"))
    if not sets:
        cr = ("не загружены", "warn")
    elif flow != FLOW.ACCOUNT and checked < sets:
        cr = (f"проверено {checked} из {sets}", "warn")
    elif pairs and pairs_ok < pairs:
        cr = (f"площадки {pairs_ok} из {pairs}", "warn")
    elif not pairs and flow != FLOW.ACCOUNT:
        cr = ("баннер не ушёл площадкам", "warn")
    else:
        cr = ("готовы", "ok")

    ordered, decided = pixel
    px = by.get("weborama_pixel")
    need_px = px is not None or flow == FLOW.FULL     # решение по пикселю — у полного цикла всегда
    if not decided:
        pxv = ("решение не принято", "warn")
    elif not ordered:
        pxv = ("не нужен", "off")
    elif px is None:
        pxv = ("заказан", "off")
    elif px[1] == "ok":
        pxv = ("получен" + (f" · {px[2]}" if px[2] else ""), "ok")
    else:
        pxv = (px[2] or "не получен", "warn")

    issued = [x for x in ds if not x["is_draft"]]
    if issued:
        x = issued[0]
        dsv = (f"№ {x['no'] or x['number']}" + (f" · {x['sign_state']}" if x.get("sign_state") else ""),
               "ok" if x.get("sign_state") == "подписан" else "warn")
    elif ds:
        dsv = ("черновик", "warn")
    else:
        dsv = ("не выпущен", "off")
    chips = [ordc] if need else []
    if need_cr:
        chips.append(_chip("creatives", "Креативы", *cr, "#sec-creatives"))
    if need_px:
        chips.append(_chip("pixel", "Пиксель", *pxv, "#sec-campaign-extra"))
    if ds or flow == FLOW.FULL:           # ДС на старте — по желанию; у контура аккаунта плашка только если ДС уже есть
        chips.append(_chip("ds", "ДС", *dsv, "#sec-docs"))
    return chips


def own_run(plan, plan_sum, d_from, d_to, today: date) -> dict:
    """«Рекламная кампания» сделки, которую аккаунт запускает сам (контур аккаунта, приоритезация): РК в нашей DSP нет,
    статистики нет — показываем план из медиаплана и ход периода; факт аккаунт вносит на итоговой сверке."""
    days = (d_to - d_from).days + 1 if d_from and d_to else None
    day = min(days, max(0, (today - d_from).days + 1)) if days else None
    return {"plan": plan, "plan_sum": plan_sum, "day": day, "days": days,
            "left": max(0, (d_to - today).days) if d_to else None, "over": bool(d_to and today > d_to),
            "elapsed_pct": round(day / days * 100, 1) if days else None}


def diff_cell(pct, bad: int, total: int, why: str) -> dict:
    """Плитка «Расхождение» кампании (макет v5): процент нашего факта против Weborama — `rk_check.check_wr_mismatch`,
    то же, что дашборд трафика. Нечем сверять — прочерк и причина, а не «0 %»."""
    if pct is None:
        return {"v": "—", "s": why or "сверка после окончания", "bad": False}
    v = ("+" if pct > 0 else "−" if pct < 0 else "") + f"{abs(pct):g}".replace(".", ",") + " %"
    return {"v": v, "s": f"по {bad} из {total} площадок" if bad else "в пределах допустимого", "bad": bool(bad)}


def _diff(db: Session, campaign_id: int, today: date) -> dict:
    from app.ad import rk_check as RC
    camps = RC.load(db, today, campaign_id=campaign_id)
    if not camps:
        return diff_cell(None, 0, 0, "")
    r = RC.check_wr_mismatch(camps[0])
    pct = (r.value or {}).get("pct")
    return diff_cell(pct, len(r.items or []), len((camps[0].ver or {}).get("by_placement") or {}), r.message.replace("Сверять нечем: ", "") if pct is None else "")


def for_flow(rows: list, external: bool) -> list:
    """Шаги «Сборки». У внешнего запуска (`account_turn.external_launch`) шагов нет: матрица не требует креативов и ЕРИД, запуск —
    во внешней системе и подтверждается кнопкой (владелец 14.11.2026)."""
    return [] if external else rows


def prio_assembly(statuses: list) -> list:
    """«Сборка» приоритезации — по площадкам запроса: отправлено → согласовано (площадки) → ЕРИД (система) → запущено (аккаунт).
    `statuses` — [(статус площадки, ЕРИД готов)]."""
    live = ("идёт", "остановлено")
    n = len([s for s, _ in statuses if s != "отказ"])
    sent = sum(1 for s, _ in statuses if s not in ("черновик", "отказ"))
    ok = sum(1 for s, _ in statuses if s in ("согласовано",) + live)
    erid = sum(1 for s, e in statuses if e and s != "отказ")
    run = sum(1 for s, _ in statuses if s in live)

    def row(key, label, who, done, ready_text, wait_text, prev_done):
        state = "ok" if n and done >= n else ("go" if done else ("warn" if key == "sent" else "wait"))
        if not prev_done and state == "wait":
            text = wait_text
        else:
            text = ready_text if state == "ok" else f"{done} из {n}"
        return {"key": key, "label": label, "who": who, "state": state, "text": text, "done": done, "total": n}
    return [row("sent", "Запрос площадкам", "аккаунт", sent, "отправлен всем", "не отправлен", True),
            row("approved", "Согласование", "площадки", ok, "все согласовали", "после отправки", sent > 0),
            row("erid", "ЕРИД", "система", erid, "получен по всем", "после согласования", ok > 0),
            row("live", "Запуск", "аккаунт", run, "все запущены", "после ЕРИД", erid > 0)]


def _prio(db: Session, deal) -> list:
    from app.ord import readiness
    from app.prio import models as PM
    rows = (db.query(PM.PrioPlacement).join(PM.PrioRequest, PM.PrioRequest.id == PM.PrioPlacement.request_id)
            .filter(PM.PrioRequest.deal_id == deal.id).all())
    return prio_assembly([(p.status, readiness.erid_ready(p)) for p in rows])


def _check_lines(db: Session, deal) -> list:
    """Требования текущей и следующей стадии сделки — тем же расчётом, что карточка (`stage_checks.evaluate`)."""
    from app.sales import stage_checks as SC
    from app.sales.stage_move import checks_for, next_stage
    rows = list(checks_for(db, deal.our_stage_id))
    nxt = next_stage(db, deal)
    if nxt is not None:
        rows += checks_for(db, nxt.id)
    seen, out = set(), []
    for ln in SC.evaluate(db, deal, rows):
        if ln.key not in seen:
            seen.add(ln.key)
            out.append((ln.key, ln.title, ln.result.state, ln.result.detail, ln.link))
    return out


def _applies(db: Session, deal) -> set:
    from app.sales.models import SalesStageCheck
    from app.sales.stage_checks import applicable_keys
    return applicable_keys(db.query(SalesStageCheck).all(), deal)


def _with_extras(rows: list, extras: list) -> list:
    """Пиксель — перед РК, «площадка собрана» — последним."""
    by = {r["key"]: r for r in extras}
    out = []
    for r in rows:
        if r["key"] == "rk" and "pixel" in by:
            out.append(by["pixel"])
        out.append(r)
    return out + ([by["pair"]] if "pair" in by else [])


def _counts(db: Session, deal) -> tuple:
    """(комплектов, проверено трафиком, пар согласовано, пар всего, комплектов с ЕРИД, РК в DSP)."""
    from app.ord import readiness
    from app.sales.stage_checks import OK, REGISTRY, Ctx
    c = Ctx(db, deal)
    sets = c.sets
    passed = {r["set_id"] for r in c.first_reviews if r["verdict"] == "ок"}
    pairs = c.pairs
    return (len(sets), len(passed), sum(1 for p in pairs if p.get("agreed_at")), len(pairs),
            sum(1 for st in sets if readiness.erid_ready(st)), REGISTRY["campaign_ready"].fn(c).state == OK)


def _campaign(db: Session, deal, today: date) -> Optional[dict]:
    from app.sales.deal_delivery import campaigns_by_deal, delivery_by_deal
    from app.ad import build
    dl = delivery_by_deal(db, campaigns_by_deal(db, [deal.id]), today).get(deal.id)
    if not dl:
        return None
    from app.ad.stat_sources import fact_sources
    # Только наш счётчик: строки верификатора лежат в той же таблице, и без фильтра клики удваиваются.
    clicks = db.execute(text("""SELECT coalesce(sum(s.clicks), 0) FROM ad_campaign_stat s
                                 WHERE s.campaign_id = :c AND s.source = ANY(:src)"""),
                        {"c": dl["campaign_id"], "src": fact_sources()}).scalar()
    plan, fact = dl.get("plan_show") or 0, dl.get("fact_shows")
    pace, done = dl.get("closed_pace"), dl.get("done_pct")
    gap = round(max(0.0, plan * (pace or 0) - (fact or 0))) if plan and fact is not None and pace is not None else None
    price = (dl.get("plan_budget") or 0) / plan if plan else None
    return {"plan": plan, "plan_sum": _r(dl.get("plan_budget")), "fact": fact,
            "fact_sum": _r(fact * price) if fact is not None and price else None,
            "clicks": int(clicks or 0), "ctr": round(clicks / fact * 100, 2) if fact else None,
            "gap": gap, "forecast": (plan - gap) if gap is not None else None,
            "on": dl.get("placements_on", 0), "placements": dl.get("placements", 0),
            "done_pct": done, "today_pct": round(pace * 100, 1) if pace is not None else None,
            "flight_over": bool(dl.get("flight_over")),
            "diff": _diff(db, dl["campaign_id"], today),
            "goals": build.deal_goals(db, deal.id)}


def now(db: Session, deal, today: date) -> dict:
    from app.sales.catalog import Catalog
    from app.sales.stage_slots import slot_of
    cat = Catalog(db)
    stage = cat.by_id.get(deal.our_stage_id)
    slot = slot_of(stage) if stage else None
    sandbox = slot in ("mp_prep", "mp_sent")
    steps = SANDBOX_STEPS if sandbox else WORK_STEPS
    at = (0 if slot == "mp_prep" else 1) if sandbox else SLOT_STEP.get(slot, 4)
    out = {"slot": slot, "stage": stage.name if stage else None, "steps": steps, "at": at,
           "start_in": (deal.period_from - today).days if deal.period_from else None,
           "end_in": (deal.period_to - today).days if deal.period_to else None,
           "period_from": deal.period_from, "period_to": deal.period_to}
    fl = FLOW.of_deal(db, deal)
    out["flow"] = fl
    if slot == "prep":
        lines = _check_lines(db, deal)
        from app.master_deal.deal_docs import for_deal
        cnt = _counts(db, deal)
        external = AT.external_launch(fl, _applies(db, deal))
        rows = _prio(db, deal) if fl == FLOW.PRIO else for_flow(_with_extras(assembly(*cnt), launch_extras(lines)), external)
        out["chips"] = assembly_chips(lines, cnt[:4], fl, (bool(deal.weborama_pixel), deal.weborama_pixel_decided_at is not None),
                                      for_deal(db, deal)["ds"])
        out["docs"] = doc_rows(lines)
        out["assembly"] = rows
        out["head"] = assembly_head(out["docs"], rows)
        out["external_launch"] = external                    # «Запуск во внешней системе — подтвердите запуск»
    elif slot == "live":
        out["campaign"] = _campaign(db, deal, today)
        if out["campaign"] is None:
            from app.final_recon import closing as CL
            st = CL.compute(db, deal)
            out["own"] = own_run(st.get("plan_shows"), _r(st.get("base_plan_net")), deal.period_from, deal.period_to, today)
    return out
