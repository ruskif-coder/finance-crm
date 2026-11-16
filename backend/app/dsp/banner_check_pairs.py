# -*- coding: utf-8 -*-
"""Проверка баннера на отправке на согласование — этап пары «креатив × площадка» (владелец 16.11.2026).

Боевого креатива в DSP ещё нет, поэтому разметку собираем имитацией загрузчика (`banner_emulate`) из подготовленного архива
в песочнице и прогоняем через ту же обёртку и ту же проверку в браузере, что и после заливки (`banner_check`). Файлы
баннера уходят браузеру сайдкара в запросе — он отдаёт их по условному адресу `BASE`, в сеть за ними не ходит.

В очередь — только пары нашей DSP с HTML5-архивом: у Adfox и «вне контура» разметку собирает не DSP, тизер — картинка.
Ссылка, куда ведёт клик, в базе не хранится: экран считает её на лету (`banner_emulate.click_link`).
"""
import logging
import os
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dsp import banner_emulate as be

log = logging.getLogger("finance.dsp")

BASE = "https://banner.invalid/"
FILES_CAP = 12 * 1024 * 1024        # файлы баннера в одном запросе к сайдкару; больше — проверка пропускается словами
UPLOADS_ROOT = "/app/uploads"          # как в targeting_creative и launch_prep: том загрузок в контейнере

_ARCHIVE = ("SELECT f.sandbox_token, f.entry_path FROM launch_prep_creative_file f "
            " WHERE f.set_id = p.set_id AND f.is_archive AND f.sandbox_token IS NOT NULL ORDER BY f.id LIMIT 1")


def eligible(db: Session, pair_ids: list) -> list:
    """Пары, которые есть чем проверить: наша DSP, формат HTML, архив разложен в песочнице, пара не отозвана."""
    if not pair_ids:
        return []
    return db.execute(text(f"""
        SELECT p.id FROM launch_prep_pair p
          JOIN launch_prep_target t ON t.id = p.target_id
          LEFT JOIN sales_publisher_surfaces s ON s.publisher_id = t.publisher_id AND s.kind = t.surface_kind
         WHERE p.id = ANY(:i) AND p.withdrawn_at IS NULL
           AND coalesce(s.placement_channel, 'dsp') = 'dsp' AND coalesce(s.creative_format, 'HTML') = 'HTML'
           AND EXISTS ({_ARCHIVE})
         ORDER BY p.id"""), {"i": list(pair_ids)}).scalars().all()


def enqueue_pairs(db: Session, pair_ids: list) -> list:
    """Пары отправлены на согласование — в очередь проверки. Возвращает поставленные."""
    ids = eligible(db, pair_ids)
    for pid in ids:
        db.execute(text("INSERT INTO dsp_banner_check (pair_id) VALUES (:p) "
                        "ON CONFLICT (pair_id) DO UPDATE SET checked_at = NULL, ok = NULL, problems = NULL"), {"p": pid})
    db.commit()
    return ids


def queue(db: Session, limit: int, only: Optional[list]) -> list:
    return db.execute(text(f"""
        SELECT b.id, b.pair_id, p.set_id, s.deal_id, d.code AS deal_code, pub.name AS publisher, a.sandbox_token,
               a.entry_path
          FROM dsp_banner_check b
          JOIN launch_prep_pair p ON p.id = b.pair_id
          JOIN launch_prep_creative_set s ON s.id = p.set_id
          JOIN sales_deals d ON d.id = s.deal_id
          JOIN launch_prep_target t ON t.id = p.target_id
          LEFT JOIN sales_publishers pub ON pub.id = t.publisher_id
          JOIN LATERAL ({_ARCHIVE}) a ON true
         WHERE b.checked_at IS NULL
           AND (CAST(:only AS integer[]) IS NULL OR b.pair_id = ANY(:only))
         ORDER BY b.id LIMIT :n"""), {"n": limit, "only": only}).mappings().all()


def _markup(db: Session, row) -> tuple:
    """(обёрнутая разметка, файлы баннера, ЕРИД) — как увидела бы площадка после заливки в DSP."""
    from app.dsp import creatives as cr
    from app.dsp.config import viewability_src
    from app.dsp.targeting_creative import erid_of
    from app.launch_prep.models import LaunchPrepCreativeSet
    from app.launch_prep.sandbox import SANDBOX_DIR
    from app.ord.advertiser_label import advertiser_label
    root = os.path.join(UPLOADS_ROOT, SANDBOX_DIR, row["sandbox_token"])
    files = be.sandbox_files(root, FILES_CAP)
    with open(os.path.join(root, row["entry_path"] or "index.html"), encoding="utf-8", errors="ignore") as fh:
        entry = fh.read()
    erid = erid_of(db.get(LaunchPrepCreativeSet, row["set_id"]))
    label = advertiser_label(db, row["deal_id"]) or (None, None)
    vsrc = viewability_src(db)
    html = be.emulate_loader(entry, base=BASE, erid=erid, ord_name=label[1], ord_inn=label[0], viewability_src=vsrc)
    return cr.wrap_html(html, erid=erid, viewability_src=vsrc), files, erid


def check_pair(db: Session, row, opts: dict) -> dict:
    from app.dsp import banner_check as bc
    try:
        html, files, erid = _markup(db, row)
    except be.TooBig as e:
        return {"html": "", "problems": {"разметка": [f"{e} — проверка в браузере пропущена, проверится после заливки в DSP"]}}
    except OSError as e:
        raise bc.BannerCheckError(f"файлы баннера в песочнице не читаются: {e}") from e
    return {"html": html, "problems": bc.problems_of(bc.render(html, erid, opts, files=files, base=BASE), html)}


def _notify_pair(db: Session, row, problems: dict) -> None:
    from app.notify import bus
    lines = [f"{k}: {'; '.join(v)}" for k, v in problems.items()]
    try:
        bus.emit(db, "dsp_banner_check_failed",
                 title=f"Баннер не прошёл проверку на отправке: {row['deal_code'] or row['deal_id']} × {row['publisher'] or '?'}",
                 body="Проверка показа в браузере (разметка как у DSP): " + " · ".join(lines)
                      + ". Отправка не заблокирована.",
                 link="/traffic/queue", entity_type="launch_prep_pair", entity_id=row["pair_id"])
    except Exception:  # noqa: BLE001 — уведомление справка, итог проверки уже записан
        log.exception("уведомление о проверке баннера пары %s не отправлено", row["pair_id"])


def state_of_pairs(db: Session, pair_ids: list) -> dict:
    """Для экранов: {pair_id: {"state": "ok"|"bad"|"queued", "problems", "checked_at"}}."""
    if not pair_ids:
        return {}
    rows = db.execute(text("SELECT pair_id, checked_at, ok, problems FROM dsp_banner_check WHERE pair_id = ANY(:i)"),
                      {"i": list(pair_ids)}).mappings().all()
    return {r["pair_id"]: {"state": "queued" if r["checked_at"] is None else ("ok" if r["ok"] else "bad"),
                           "problems": r["problems"], "checked_at": r["checked_at"]} for r in rows}
