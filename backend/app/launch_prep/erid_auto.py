# -*- coding: utf-8 -*-
"""Автовыпуск ЕРИД и опрос статуса регистрации — крон раз в полчаса (владелец 27.09.2026).

Правило: маркер на комплект выпускается сам, когда его согласовали не меньше 20 % площадок,
которым он отправлен (`launch_prep.auto_need`: вверх, минимум одна; доля — настройка
`creatives_erid_threshold`). Кнопка в сборке остаётся: человек вправе выпустить раньше.

Прогон делает два дела:

1. **Выпуск.** Комплект нашего ОРД (`erid_source = 'наш'`) без маркера, порог взят,
   договорная цепочка и код ККТУ есть → та же функция, что у кнопки
   (`issue_marker_for_set`). Комплект, уже зарегистрированный без маркера, не
   регистрируется второй раз: функция в этом случае опрашивает статус и, если маркер
   пришёл, объявляет его (получатели, РК, уведомления).
2. **Опрос.** Комплекты с маркером, чья регистрация в ЕРИР ещё не дошла до конечного
   статуса, — статус обновляется. Это только чтение.

Чего нет в цепочке или ККТУ — комплект пропускается и называется в отчёте прогона: ЕРИР
без них креатив не примет, а отказ реестра необратимостью не грозит, но засоряет журнал.
Сделки в терминальной стадии не трогаются.

Запись в ЕРИР необратима, поэтому прогон держит те же замки, что кнопка: без разрешения
записи в боевой ОРД (`ORD_ALLOW_PROD_WRITE`) выпуск отказывает, и прогон это сообщает.

Запуск: `python -m app.launch_prep.erid_auto [--dry-run]`.
"""
import argparse
import logging
import sys

from fastapi import HTTPException

from app.database import SessionLocal

log = logging.getLogger("finance.ord")

# Статусы регистрации, после которых опрашивать нечего.
FINAL_STATUSES = ("Active", "Deleted", "Hidden")


def _deal_is_closed(db, deal) -> bool:
    from app.sales.models import SalesStage
    if not deal.our_stage_id:
        return False
    st = db.query(SalesStage).filter(SalesStage.id == deal.our_stage_id).first()
    return bool(st and (st.is_terminal or st.is_lost))


def _blockers(db, deal) -> list:
    """То же, что экран готовности называет блокерами, кроме «пустого комплекта»."""
    from app.launch_prep import erid_service as lp
    from app.sales.models import SalesBrand
    out = []
    final_ord_id, _ = lp._ord_chain(db, deal)
    if not final_ord_id:
        out.append("не собрана договорная цепочка ОРД")
    brand = (db.query(SalesBrand).filter(SalesBrand.id == deal.brand_id).first()
             if deal.brand_id else None)
    if not (brand and brand.kktu_code):
        out.append("не заполнен код ККТУ у бренда")
    return out


def issue_due(db, dry_run: bool = False) -> dict:
    """Выпустить маркер там, где порог взят. Сбой одного комплекта не останавливает остальных."""
    from app.launch_prep.models import LaunchPrepCreativeSet
    from app.launch_prep import erid_service as lp
    from app.sales.models import SalesDeal

    from app.ord import client as ord_client
    env = ord_client.env()
    share = lp.erid_threshold(db)
    issued, pending, waiting, blocked, failed = [], [], [], [], []
    sets = (db.query(LaunchPrepCreativeSet)
            .filter(LaunchPrepCreativeSet.erid.is_(None),
                    LaunchPrepCreativeSet.erid_source == "наш")
            .order_by(LaunchPrepCreativeSet.id).all())
    for s in sets:
        deal = db.query(SalesDeal).filter(SalesDeal.id == s.deal_id).first()
        if not deal or _deal_is_closed(db, deal):
            continue
        pairs = lp.active_pairs(db, s.id)
        if not pairs:
            continue
        st = lp.threshold_numbers(pairs)
        need = lp.auto_need(st["sent"], share)
        # Уже зарегистрированный без маркера — опрашивается без порога: регистрация
        # состоялась, осталось забрать маркер. Только на ТЕКУЩЕМ контуре: регистрация из
        # песочницы на боевом ничего не значит, и порог она не отменяет.
        registered = bool(s.ord_creative_id) and (s.ord_env or "") == env
        if not registered and st["agreed"] < need:
            waiting.append(s.id)
            continue
        why = _blockers(db, deal)
        if why:
            blocked.append({"set_id": s.id, "deal": deal.code, "why": why})
            continue
        if dry_run:
            issued.append({"set_id": s.id, "deal": deal.code, "dry_run": True})
            continue
        try:
            out = lp.issue_marker_for_set(db, s, deal, None)
        except HTTPException as e:
            db.rollback()
            failed.append({"set_id": s.id, "deal": deal.code, "error": str(e.detail)})
            continue
        except Exception as e:  # noqa: BLE001 — отчёт прогона, дальше следующий комплект
            db.rollback()
            log.exception("автовыпуск ЕРИД: комплект %s", s.id)
            failed.append({"set_id": s.id, "deal": deal.code, "error": str(e)})
            continue
        (issued if out.get("erid") else pending).append(
            {"set_id": s.id, "deal": deal.code, "erid": out.get("erid"),
             "status": out.get("status")})
    return {"share": share, "issued": issued, "pending": pending, "waiting": len(waiting),
            "blocked": blocked, "failed": failed}


def refresh_statuses(db, dry_run: bool = False) -> dict:
    """Опросить статус регистрации у комплектов с маркером, где он ещё не конечный."""
    from app.launch_prep.models import LaunchPrepCreativeSet
    from app.ord import client as ord_client
    from app.launch_prep import erid_service as lp
    from app.sales.models import SalesDeal

    # Только свой контур: маркер песочницы на боевом не опрашивается — ОРД ответил бы
    # отказом на каждом прогоне, и крон краснел бы каждые полчаса без причины.
    sets = (db.query(LaunchPrepCreativeSet)
            .filter(LaunchPrepCreativeSet.erid.isnot(None),
                    LaunchPrepCreativeSet.erid_source == "наш",
                    LaunchPrepCreativeSet.ord_env == ord_client.env(),
                    (LaunchPrepCreativeSet.ord_status.is_(None))
                    | (~LaunchPrepCreativeSet.ord_status.in_(FINAL_STATUSES)))
            .order_by(LaunchPrepCreativeSet.id).all())
    changed, failed = [], []
    for s in sets:
        if dry_run:
            continue
        before = s.ord_status
        try:
            # Опрос — через ту же функцию, что кнопка: маркер, ставший готовым, объявляется
            # (площадки — «ерид получен», маркер — в РК), а не оседает молча (02.10.2026).
            deal = db.query(SalesDeal).filter(SalesDeal.id == s.deal_id).first()
            out = lp.refresh_and_announce(db, s, deal, None)
        except Exception as e:  # noqa: BLE001 — отчёт прогона, дальше следующий комплект
            db.rollback()
            failed.append({"set_id": s.id, "error": str(e)})
            continue
        if out.get("status") != before:
            changed.append({"set_id": s.id, "from": before, "to": out.get("status")})
    return {"checked": len(sets), "changed": changed, "failed": failed}


# Итог последнего БОЕВОГО прогона — для строки «Автовыпуск ЕРИД» на экране «Статус
# системы» (`app/system/status.check_erid_auto`). Крон пишет в ЕРИР без человека: умри он
# или начни падать, маркеры перестанут выходить молча. Ключ в `company_settings`, как у
# режима обслуживания, — миграция не нужна. Пробный прогон не пишется: он ничего не
# выпускал, и засчитывать его за живой значило бы гасить сигнал о мёртвом кроне.
LAST_RUN_KEY = "erid_auto_last"


def refresh_errors(failed: list, limit: int = 5) -> list:
    """Ошибки опроса статусов — текстом, одинаковые склеены с числом комплектов (05.10.2026:
    «ошибок опроса: 11» без текста прятало, что ОРД отвечает 403 «нет прав»)."""
    from collections import Counter
    cnt = Counter(str(f.get("error") or "без текста")[:200] for f in failed)
    return [f"{e} — {n} компл." for e, n in cnt.most_common(limit)]


def record(db, out: dict) -> None:
    import json
    from datetime import datetime
    from sqlalchemy import text
    i, r = out["issue"], out["refresh"]
    value = json.dumps({
        "at": datetime.utcnow().isoformat(timespec="seconds"),
        "issued": len(i["issued"]), "pending": len(i["pending"]),
        "blocked": [f"{b['deal']}: {', '.join(b['why'])}" for b in i["blocked"]][:20],
        "failed": [f"{f['deal']}: {f['error']}"[:200] for f in i["failed"]][:20],
        "refresh_failed": len(r["failed"]),
        "refresh_errors": refresh_errors(r["failed"]),
    }, ensure_ascii=False)
    db.execute(text("INSERT INTO company_settings (key, value) VALUES (:k, :v) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"),
               {"k": LAST_RUN_KEY, "v": value})
    db.commit()


def _had_failures(last: dict | None) -> bool:
    return bool(last and (last.get("failed") or last.get("refresh_failed")))


def should_alert(prev: dict | None, out: dict) -> bool:
    """Тревога — на ПЕРЕХОДЕ «работает → падает», а не каждые полчаса: иначе через сутки
    уведомление выключат, и настоящая поломка утонет в повторах."""
    now_bad = bool(out["issue"]["failed"] or out["refresh"]["failed"])
    return now_bad and not _had_failures(prev)


def _previous(db) -> dict | None:
    import json
    from sqlalchemy import text
    raw = db.execute(text("SELECT value FROM company_settings WHERE key = :k"),
                     {"k": LAST_RUN_KEY}).scalar()
    try:
        return json.loads(raw) if raw else None
    except (TypeError, ValueError):
        return None


def _alert(db, out: dict) -> None:
    from app.notify.bus import emit
    i, r = out["issue"], out["refresh"]
    lines = [f"{f['deal']}: {f['error']}" for f in i["failed"]][:5]
    if r["failed"]:
        lines.append(f"ошибок опроса статуса: {len(r['failed'])} — "
                     + "; ".join(refresh_errors(r["failed"], 2)))
    emit(db, "cron_erid_auto_failed", title="Автовыпуск ЕРИД: ошибка",
         body="; ".join(lines)[:600], link="/settings/system",
         entity_type="cron", entity_id=1, actor=None)
    db.commit()


def catch_up(db, dry_run: bool = False) -> list:
    """Объявить готовые маркеры, которые не объявлены (`erid_service.announce_pending`)."""
    from app.launch_prep import erid_service
    return erid_service.announce_pending(db, dry_run=dry_run)


def run(dry_run: bool = False) -> dict:
    db = SessionLocal()
    try:
        issued = issue_due(db, dry_run=dry_run)
        refreshed = refresh_statuses(db, dry_run=dry_run)
        out = {"issue": issued, "refresh": refreshed, "dry_run": dry_run}
        try:
            out["caught_up"] = catch_up(db, dry_run=dry_run)
        except Exception:  # noqa: BLE001 — догон не должен ронять прогон
            db.rollback()
            log.exception("автовыпуск ЕРИД: догон объявлений не удался")
        if dry_run:
            db.rollback()
        else:
            prev = _previous(db)
            record(db, out)
            if should_alert(prev, out):
                try:
                    _alert(db, out)
                except Exception:  # noqa: BLE001 — тревога не должна ронять прогон
                    db.rollback()
                    log.exception("автовыпуск ЕРИД: тревога не отправлена")
        return out
    finally:
        db.close()


def _report(out: dict) -> str:
    i, r = out["issue"], out["refresh"]
    parts = [f"порог {round(i['share'] * 100)} %",
             f"ЕРИД выпущено: {len(i['issued'])}",
             f"зарегистрировано без маркера: {len(i['pending'])}",
             f"ждут согласований: {i['waiting']}",
             f"пропущено (нет цепочки/ККТУ): {len(i['blocked'])}",
             f"ошибок выпуска: {len(i['failed'])}",
             f"статусов опрошено: {r['checked']}, сменилось: {len(r['changed'])}, "
             f"ошибок опроса: {len(r['failed'])}"]
    lines = ["; ".join(parts) + (" (пробный прогон, ничего не записано)" if out["dry_run"] else "")]
    lines += [f"  пропущен комплект {b['set_id']} ({b['deal']}): {', '.join(b['why'])}"
              for b in i["blocked"]]
    lines += [f"  ошибка комплекта {f['set_id']} ({f['deal']}): {f['error']}" for f in i["failed"]]
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Автовыпуск ЕРИД по порогу и опрос статуса")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    res = run(dry_run=a.dry_run)
    print(_report(res))
    sys.exit(1 if res["issue"]["failed"] or res["refresh"]["failed"] else 0)
