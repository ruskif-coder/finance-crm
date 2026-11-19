# -*- coding: utf-8 -*-
"""Пиксель Weborama и выгрузка в DSP — сами, по мере движения РК (трафики согласовали 19.11.2026).

КАК БЫЛО. Обе цепочки запускались только кнопками дашборда трафика: «ПИКСЕЛЬ WR», потом «В DSP». Площадка согласовала
креатив, ЕРИД выпущен — и всё стояло, пока человек не нажмёт.

КАК СТАЛО. Площадка готова (согласовала креатив, у комплекта ЕРИД) — по её РК сначала заводится вставка Weborama и
забирается пиксель, затем креатив уходит в DSP. Делают это те же функции, что у кнопок (`weborama.provision`,
`dsp.provision`), со всеми их заслонами: без ЕРИД пикселя нет, без пикселя (когда он заказан) нет DSP, неизвестный исход
запирает повтор до сверки человеком, замки `only_one` не пускают второй проход параллельно с кнопкой.

КОГДА. Крон раз в 5 минут (`python -m app.ad.auto_external`) и сразу после автовыпуска ЕРИД (`launch_prep.erid_auto`):
ЕРИД обычно приходит последним. Фоновых потоков из запроса нет намеренно — процесс, умерший посреди вызова Weborama или
DSP, оставил бы «исход неизвестен» и запер площадку.

ВЫКЛЮЧАТЕЛЬ. `company_settings.traffic_auto_external` = «1» — сами; иначе — только кнопки, как раньше. Ставится на экране
настроек трафика. `EXTERNAL_WRITES=off` (стенд) — тоже ничего: транспорт отказал бы всё равно.

СБОЙ. Отказы по площадкам — уведомлением трафику (`traffic_auto_external_failed`); тот же текст по той же сделке — не чаще
раза в сутки, иначе крон раз в 5 минут завалил бы колокольчик. И алертом в пульте раскрытой РК (шаг «Заведение»), пока не
устранено: итог последнего прохода по РК лежит строкой `company_settings` `auto_external:<id РК>` (владелец 19.11.2026) —
прошёл чисто или РК выпала из работы — строка удаляется, алерт гаснет.
"""
import argparse
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import external_writes
from app.ad.flight import PLACEMENT_IN_PLAN, PLACEMENT_READY
from app.ad.models import AdCampaign
from app.audit import log_action

log = logging.getLogger("finance.ad")

SETTING = "traffic_auto_external"
STATE_PREFIX = "auto_external:"          # + id РК: итог последнего прохода с отказами — для алерта в пульте РК
FAIL_ACTION = "auto_external_failed"
REPEAT_AFTER = timedelta(hours=24)
DONE_STATUSES = ("окончена", "архив")


def enabled(db: Session) -> bool:
    v = db.execute(text("SELECT value FROM company_settings WHERE key = :k"), {"k": SETTING}).scalar()
    return (v or "").strip() == "1"


def set_enabled(db: Session, on: bool) -> None:
    db.execute(text("INSERT INTO company_settings (key, value) VALUES (:k, :v) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"), {"k": SETTING, "v": "1" if on else "0"})


def candidates(db: Session, deal_ids: Optional[list] = None) -> list:
    """РК, где есть что делать: готовая площадка без пикселя или креатив готовой площадки без хеша DSP.

    Грубый отбор одним запросом — точный отбор делают `plan` обеих цепочек, ровно как перед подтверждением кнопки."""
    ok = (PLACEMENT_READY,) + tuple(PLACEMENT_IN_PLAN)
    q = """SELECT DISTINCT c.id FROM ad_campaign c
             JOIN ad_campaign_placement p ON p.campaign_id = c.id
            WHERE c.status <> ALL(:done) AND p.status = ANY(:ok) AND NOT coalesce(p.is_direct, false)
              AND (p.weborama_pixel IS NULL
                   OR EXISTS (SELECT 1 FROM ad_campaign_creative cr WHERE cr.placement_id = p.id
                               AND coalesce(cr.ms_creative_xxhash, '') = ''))"""
    params = {"done": list(DONE_STATUSES), "ok": list(ok)}
    if deal_ids is not None:
        q += " AND c.deal_id = ANY(:deals)"
        params["deals"] = list(deal_ids) or [0]
    return [r[0] for r in db.execute(text(q + " ORDER BY c.id"), params)]


def _label(db: Session, camp: AdCampaign) -> str:
    from app.routers.traffic_dashboard import rk_label
    return rk_label(db, camp.id)


def _weborama(db: Session, camp: AdCampaign, deal_id: int, out: dict) -> None:
    from app.weborama import provision as wb
    plan = wb.plan(db, camp)
    if not plan.get("todo"):
        return
    try:
        res = wb.provision(db, camp, wb.default_landing(db, camp))
    except wb.ProvisionError as e:
        db.rollback()
        out["failed"].append(f"Weborama: {e}")
        return
    out["weborama"] = len(res["done"])
    # «нет ЕРИД» — не сбой, а ожидание: площадка получит пиксель, когда автовыпуск выдаст маркер. Уведомлять о нём —
    # звонить по каждой ждущей площадке раз в 5 минут.
    real = [f for f in res["failed"] if f.get("error") != wb.NO_ERID]
    out["failed"] += [f"Weborama, {f.get('name') or f.get('placement_id')}: {f.get('error')}" for f in real]
    log_action(db, None, "weborama_provision", "sales_deal", deal_id,
               f"{_label(db, camp)}: автоматически — пикселей получено {len(res['done'])}, отказов {len(real)}")


def _dsp(db: Session, camp: AdCampaign, deal_id: int, out: dict) -> None:
    from app.dsp import provision as dsp
    from app.launch_prep import volumes
    plan = dsp.plan(db, camp)
    if not plan.get("todo"):
        return
    vol = volumes.check(db, deal_id)
    if vol["blocked"]:                      # тот же запрет, что у кнопки «В DSP» (27.09.2026)
        out["failed"].append(f"DSP: {vol['message']}")
        return
    try:
        res = dsp.provision(db, camp)
    except dsp.DspProvisionError as e:
        db.rollback()
        out["failed"].append(f"DSP: {e}")
        return
    out["dsp"] = len(res["done"])
    out["failed"] += [f"DSP, {f.get('name') or f.get('creative_id')}: {f.get('error')}" for f in res["failed"]]
    log_action(db, None, "dsp_provision", "sales_deal", deal_id,
               f"{_label(db, camp)}: автоматически — креативов заведено {len(res['done'])}, отказов {len(res['failed'])}")


def _dash_link(db: Session, deal_id: int) -> str:
    """Дашборд трафика с раскрытой РК: дашборд открывает её по коду сделки (`?open=`)."""
    code = db.execute(text("SELECT code FROM sales_deals WHERE id = :d"), {"d": deal_id}).scalar()
    return f"/traffic/dashboard?open={code}" if code else "/traffic/dashboard"


def _notify_once(db: Session, camp: AdCampaign, deal_id: int, failed: list) -> bool:
    """Уведомить трафик, если ровно такого же отказа по сделке за сутки не было. True — ушло."""
    details = f"{_label(db, camp)}: " + "; ".join(failed)
    seen = db.execute(text("""SELECT 1 FROM audit_log WHERE action = :a AND entity_type = 'sales_deal' AND entity_id = :d
                                AND details = :t AND created_at > :since LIMIT 1"""),
                      {"a": FAIL_ACTION, "d": deal_id, "t": details, "since": datetime.utcnow() - REPEAT_AFTER}).first()
    if seen:
        return False
    log_action(db, None, FAIL_ACTION, "sales_deal", deal_id, details)
    try:
        from app.notify import bus
        bus.emit(db, "traffic_auto_external_failed", title=f"Пиксель / DSP сами не прошли · {_label(db, camp)}",
                 body="; ".join(failed) + ". Повторить можно кнопками «ПИКСЕЛЬ WR» и «В DSP» в расхлопе РК.",
                 link=_dash_link(db, deal_id), entity_type="ad_campaign", entity_id=camp.id)
        db.commit()
    except Exception:  # noqa: BLE001 — уведомление справка; отказ уже записан в журнал
        db.rollback()
        log.exception("РК %s: уведомление об отказе автоматики не отправлено", camp.id)
    return True


def _remember(db: Session, campaign_id: int, failed: list) -> None:
    """Итог прохода для пульта РК: отказы — строкой, чисто — строки нет."""
    key = f"{STATE_PREFIX}{campaign_id}"
    if failed:
        val = json.dumps({"at": datetime.utcnow().isoformat(timespec="seconds"), "failed": failed}, ensure_ascii=False)
        db.execute(text("INSERT INTO company_settings (key, value) VALUES (:k, :v) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"), {"k": key, "v": val})
    else:
        db.execute(text("DELETE FROM company_settings WHERE key = :k"), {"k": key})
    db.commit()


def _forget_except(db: Session, keep: list) -> None:
    """Снять алерты РК, которые выпали из работы (всё заведено, РК окончена) или все — когда автоматика выключена."""
    db.execute(text("DELETE FROM company_settings WHERE key LIKE :p AND NOT (key = ANY(:keep))"),
               {"p": STATE_PREFIX + "%", "keep": [f"{STATE_PREFIX}{i}" for i in keep]})
    db.commit()


def alerts(db: Session) -> dict:
    """{id РК: текст} — что автоматика не смогла по РК в последнем проходе. Для сводки пульта (`/rk-check/summary`)."""
    out = {}
    for key, val in db.execute(text("SELECT key, value FROM company_settings WHERE key LIKE :p"), {"p": STATE_PREFIX + "%"}):
        try:
            out[int(key[len(STATE_PREFIX):])] = "; ".join(json.loads(val)["failed"])
        except (ValueError, KeyError, TypeError):
            continue
    return out


def overlay(summary: dict, message: str) -> dict:
    """Наложить алерт автоматики на шаг «Заведение» сводки РК (`rk_check.build_summary`): красный, текст отказа,
    ссылка — к кнопкам «ПИКСЕЛЬ WR» / «В DSP». Новый словарь — сводку не мутируем."""
    # счёт «7 из 7» ночных проверок рядом с красным алертом читается как противоречие — при алерте его не показываем
    groups = [({**g, "level": "red", "text": f"Автоматика: {message}", "ok": 0, "total": 0,
                "action": {"label": "повторить вручную", "target": "dsp", "check": "auto_external"}}
               if g["key"] == "setup" else g) for g in summary["groups"]]
    return {**summary, "groups": groups, "worst": "red", "all_ok": False}


def run_campaign(db: Session, camp: AdCampaign) -> dict:
    """Один проход по РК: пиксель, затем DSP. Сбой не роняет вызывающего — отчёт."""
    out = {"campaign_id": camp.id, "weborama": 0, "dsp": 0, "failed": [], "notified": False}
    deal_id = camp.deal_id
    try:
        _weborama(db, camp, deal_id, out)
        db.expire_all()                     # пиксель записан провижнингом — DSP читает свежие строки
        camp = db.get(AdCampaign, out["campaign_id"])
        _dsp(db, camp, deal_id, out)
    except Exception as e:  # noqa: BLE001 — одна РК не останавливает обход остальных
        db.rollback()
        log.exception("РК %s: автоматика пиксель/DSP упала", out["campaign_id"])
        out["failed"].append(f"сбой: {e}")
    if out["failed"]:
        out["notified"] = _notify_once(db, camp, deal_id, out["failed"])
    _remember(db, out["campaign_id"], out["failed"])
    return out


def run(db: Session, deal_ids: Optional[list] = None, dry_run: bool = False) -> dict:
    """Обход РК. Выключено или запись наружу запрещена — ничего не делает и говорит почему."""
    if not enabled(db):
        if deal_ids is None:
            _forget_except(db, [])          # выключили — автоматических отказов больше нет, алерты гаснут
        return {"skipped": "выключено в настройках трафика", "campaigns": []}
    if not external_writes.allowed():
        return {"skipped": external_writes.REFUSAL, "campaigns": []}
    ids = candidates(db, deal_ids)
    if dry_run:
        return {"candidates": ids, "campaigns": []}
    done = []
    for cid in ids:
        camp = db.get(AdCampaign, cid)
        if camp is not None:
            done.append(run_campaign(db, camp))
    if deal_ids is None:
        _forget_except(db, ids)
    return {"campaigns": [r for r in done if r["weborama"] or r["dsp"] or r["failed"]], "checked": len(ids)}


def run_quietly(db: Session, deal_ids: Optional[list] = None) -> Optional[dict]:
    """Для вызова из чужого процесса (крон ЕРИД): сбой автоматики не роняет вызывающего."""
    try:
        return run(db, deal_ids)
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("автоматика пиксель/DSP не прошла")
        return None


def main() -> None:
    from app.database import SessionLocal
    import app.model_registry  # noqa: F401
    ap = argparse.ArgumentParser(description="Пиксель Weborama и выгрузка в DSP по готовым площадкам")
    ap.add_argument("--dry-run", action="store_true", help="только показать РК-кандидаты")
    a = ap.parse_args()
    db = SessionLocal()
    try:
        print(json.dumps(run(db, dry_run=a.dry_run), ensure_ascii=False, default=str))
    finally:
        db.close()


if __name__ == "__main__":
    main()
