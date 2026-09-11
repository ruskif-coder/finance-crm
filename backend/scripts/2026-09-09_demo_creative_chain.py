# -*- coding: utf-8 -*-
"""Демо-цепочка согласования креативов на ОДНОЙ сделке.

Зачем: реального материала через конвейер прошло две пары на всю базу, и смотреть, куда
встраивать индикацию пикселя Weborama, не на чем. Экран согласования, карточка сделки и
расхлоп РК на дашборде должны показывать живую картинку: часть площадок согласована,
часть у площадки, часть на доработке.

ЗАПУСК (только на локальном стенде):
    docker exec finance_backend python -m scripts.2026-09-09_demo_creative_chain
    docker exec finance_backend python -m scripts.2026-09-09_demo_creative_chain --undo

ОБРАТИМО ПОЛНОСТЬЮ — требование к любому демо здесь: локальная база копия боевой, и
цифры, которые нельзя отличить от настоящих, однажды будут приняты за настоящие.

  · комплекты нумеруются от DEMO_NO и по этому же номеру удаляются;
  · откат удаляет ТОЛЬКО свои цели — те, на которые смотрят пары нашего комплекта.
    Первый вариант сносил все цели сделки и однажды унёс шесть чужих, оставленных
    прогоном тестов;
  · если у сделки появятся НАСТОЯЩИЕ цели до установки демо — скрипт откажется работать,
    а не затрёт их;
  · пары и вердикты уходят каскадом за комплектом и целью;
  · строки РК пересобираются штатным `build.sync_creatives`, а не пишутся руками:
    демо не должно знать о правилах больше, чем боевой код;
  · источники вердиктов берутся ИЗ СЛОВАРЯ (`REVIEW_SOURCES`), а не выдумываются. Первый
    прогон записал `source='демо'`, и это поймал прибор `test_vocabularies` — демо-данные
    обязаны быть неотличимы от настоящих по форме, иначе они ломают гейты.

ВЫБОР СДЕЛКИ. `F99A73` — у её РК 19 площадок и пустая цепочка. Ищем по КОДУ, а не по id:
код одинаков везде, id — нет.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta

from sqlalchemy import text

sys.stdout.reconfigure(encoding="utf-8")

from app import models as _core_models  # noqa: F401,E402 — таблица users нужна FK комплекта
from app.ad import build                                    # noqa: E402
from app.ad.models import (AdCampaign, AdCampaignCreative,   # noqa: E402
                           AdCampaignPlacement)
from app.database import SessionLocal                       # noqa: E402
from app.launch_prep.models import (LaunchPrepCreativeFile,  # noqa: E402
                                    LaunchPrepCreativeSet, LaunchPrepPair,
                                    LaunchPrepReview, LaunchPrepSetTarget,
                                    LaunchPrepTarget)
from app.sales.models import SalesDeal, SalesPublisher       # noqa: E402

DEAL_CODE = "F99A73"
DEMO_NO = 8500              # выше демо-витрины (8000…8002) и ниже приборов (9000+)
UPLOADS = "/app/uploads"
CREATIVES_DIR = "creatives"

# Раскладка состояний. Подобрана так, чтобы на экране встретились ВСЕ, ради которых он и
# нужен: согласованные (им пиксель нужен уже сейчас), ждущие площадку, ждущие трафик и
# отправленные на доработку. Числа — сколько площадок в каждом состоянии.
PLAN = [("согласована", 6), ("у площадки", 4), ("у трафика", 3), ("на доработку", 2)]

# Состояние площадки в РК под каждое состояние пары. Без этого демо-витрина (она ставит
# всем «запущен») скрывает всю цепочку: на экране 19 одинаковых строк, и куда встраивать
# индикацию — не видно. «На доработку» возвращает мяч нам, поэтому «у трафика».
PLACEMENT_BY_STATE = {"согласована": "ждёт запуска", "у площадки": "у площадки",
                      "у трафика": "у трафика", "на доработку": "у трафика"}

BANNER = ('<html><head><meta charset="utf-8">'
          '<meta name="ad.size" content="width={w},height={h}">'
          '<title>ДЕМО {ratio}</title></head>'
          '<body style="margin:0;font:14px sans-serif;display:flex;align-items:center;'
          'justify-content:center;width:{w}px;height:{h}px;background:#0f4c81;color:#fff">'
          '<a href="{{LINK_UNESC}}" style="color:#fff">ДЕМО {ratio}</a>{{RID}}</body></html>')

RATIOS = [("240x400", 240, 400), ("300x250", 300, 250), ("970x250", 970, 250)]


def _deal(db):
    d = db.query(SalesDeal).filter(SalesDeal.code == DEAL_CODE).first()
    if not d:
        raise SystemExit(f"Сделки с кодом {DEAL_CODE} нет — демо не на что вешать")
    return d


def _campaign(db, deal_id):
    c = db.query(AdCampaign).filter(AdCampaign.deal_id == deal_id).first()
    if not c:
        raise SystemExit("У сделки нет РК — сначала синк из сделок")
    return c


def undo(db, deal):
    """Снять демо. Порядок: файлы с диска, потом строки — иначе путь взять неоткуда."""
    sets = (db.query(LaunchPrepCreativeSet)
            .filter(LaunchPrepCreativeSet.deal_id == deal.id,
                    LaunchPrepCreativeSet.no >= DEMO_NO).all())
    doomed = [f.path for s in sets for f in
              db.query(LaunchPrepCreativeFile).filter(LaunchPrepCreativeFile.set_id == s.id)]
    n_sets = len(sets)
    # Строки РК ссылаются на комплект через `root_set_id`, и у этого ключа НЕТ каскада:
    # удалить комплект «просто так» нельзя. Снимаем сначала их — те же грабли, что
    # разбирались 09.09.2026 в orm-autoflush-and-server-default.
    ids = [s.id for s in sets]
    n_cr = 0
    if ids:
        n_cr = (db.query(AdCampaignCreative)
                .filter(AdCampaignCreative.root_set_id.in_(ids))
                .delete(synchronize_session=False))
        db.flush()
    for s in sets:
        db.delete(s)
    # Только НАШИ цели — те, на которые смотрят пары нашего комплекта. Первый вариант
    # сносил все цели сделки, и прогон тестов, оставивший на ней шесть своих, потерял бы
    # их молча. Чужое не трогаем, даже если это тоже демо.
    mine_ids = [r[0] for r in db.execute(text("""
        SELECT DISTINCT pr.target_id FROM launch_prep_pair pr
          JOIN launch_prep_creative_set cs ON cs.id = pr.set_id
         WHERE cs.deal_id = :d AND cs.no >= :no
    """), {"d": deal.id, "no": DEMO_NO}).all()]
    n_targets = 0
    if mine_ids:
        n_targets = (db.query(LaunchPrepTarget)
                     .filter(LaunchPrepTarget.id.in_(mine_ids))
                     .delete(synchronize_session=False))
    # Возвращаем площадкам то, что стояло до нас, — «запущен» от демо-витрины. Это
    # упрощение и оно названо вслух: обе стороны здесь демо-данные, восстанавливать
    # нечего, кроме предыдущего демо.
    camp = db.query(AdCampaign).filter(AdCampaign.deal_id == deal.id).first()
    n_pl = 0
    if camp:
        n_pl = (db.query(AdCampaignPlacement)
                .filter(AdCampaignPlacement.campaign_id == camp.id)
                .update({"status": "запущен"}, synchronize_session=False))
    db.commit()
    gone = 0
    for rel in doomed:
        p = os.path.join(UPLOADS, rel)
        if os.path.exists(p):
            os.remove(p)
            gone += 1
    print(f"снято: комплектов {n_sets}, целей {n_targets}, файлов с диска {gone}, "
          f"строк РК {n_cr}, площадок возвращено в «запущен» {n_pl}")


def main(apply: bool):
    db = SessionLocal()
    try:
        deal = _deal(db)
        camp = _campaign(db, deal.id)
        print(f"сделка {deal.code} «{deal.title}» (id {deal.id}), РК {camp.id} {camp.status}")

        alien = (db.query(LaunchPrepTarget)
                 .filter(LaunchPrepTarget.deal_id == deal.id).count())
        mine = (db.query(LaunchPrepCreativeSet)
                .filter(LaunchPrepCreativeSet.deal_id == deal.id,
                        LaunchPrepCreativeSet.no >= DEMO_NO).count())
        if alien and not mine:
            raise SystemExit(
                f"У сделки уже {alien} целей, и они НЕ наши — демо их затрёт. Откажусь.")
        if mine:
            print("демо уже стоит — сначала снимаю, чтобы прогон был повторяемым")
            undo(db, deal)
        if not apply:
            print("СУХОЙ ПРОГОН: ничего не записано. Повторите с --apply")
            return

        pls = (db.query(AdCampaignPlacement)
               .filter(AdCampaignPlacement.campaign_id == camp.id)
               .order_by(AdCampaignPlacement.id).all())
        need = sum(n for _, n in PLAN)
        if len(pls) < need:
            raise SystemExit(f"В РК {len(pls)} площадок, а раскладке нужно {need}")

        # 1) цели — по одной на площадку
        os.makedirs(os.path.join(UPLOADS, CREATIVES_DIR), exist_ok=True)
        targets, i = [], 0
        for state, count in PLAN:
            for _ in range(count):
                p = pls[i]; i += 1
                svc = db.execute(text(
                    "SELECT service_id FROM sales_publisher_services "
                    "WHERE publisher_id = :p AND is_active LIMIT 1"), {"p": p.publisher_id}).scalar()
                if not svc:
                    svc = db.execute(text("SELECT id FROM sales_services ORDER BY id LIMIT 1")).scalar()
                t = LaunchPrepTarget(deal_id=deal.id, publisher_id=p.publisher_id,
                                     service_id=svc, surface_kind="web",
                                     state="согласован" if state == "согласована" else "согласование",
                                     period_from=camp.date_start, period_to=camp.date_end)
                db.add(t)
                db.flush()
                targets.append((t, state, p))
        print(f"целей заведено: {len(targets)}")

        # 2) комплект и его файлы
        cs = LaunchPrepCreativeSet(deal_id=deal.id, no=DEMO_NO, origin="первичный",
                                   form="баннер", description="ДЕМО — цепочка согласования")
        db.add(cs); db.flush()
        for ratio, w, h in RATIOS:
            rel = f"{CREATIVES_DIR}/demo-{DEMO_NO}-{ratio}.html"
            html = BANNER.format(w=w, h=h, ratio=ratio)
            with open(os.path.join(UPLOADS, rel), "w", encoding="utf-8") as fh:
                fh.write(html)
            db.add(LaunchPrepCreativeFile(
                set_id=cs.id, ratio=ratio, path=rel, original_name=f"demo-{ratio}.html",
                content_type="text/html", size_bytes=len(html.encode("utf-8"))))
        db.flush()

        # 3) адресация, пары и вердикты
        now = datetime.now()
        for t, state, p in targets:
            db.add(LaunchPrepSetTarget(set_id=cs.id, target_id=t.id))
            pub = db.query(SalesPublisher).get(p.publisher_id)
            code = f"{deal.code}-{(pub.code or str(pub.id))[:4]}"
            pair = LaunchPrepPair(code=code, set_id=cs.id, target_id=t.id,
                                  sent_at=now - timedelta(days=3))
            db.add(pair); db.flush()

            # первичная ТТ — всегда пройдена: без неё пара не ушла бы дальше
            db.add(LaunchPrepReview(set_id=cs.id, pair_id=pair.id, kind="первичная_тт",
                                    verdict="ок", source="аккаунт", decided_at=now,
                                    decided_by="ДЕМО"))
            if state == "у трафика":
                db.add(LaunchPrepReview(set_id=cs.id, pair_id=pair.id, kind="трафики",
                                        source="трафики"))
                continue
            db.add(LaunchPrepReview(set_id=cs.id, pair_id=pair.id, kind="трафики",
                                    verdict="ок", source="трафики", decided_at=now,
                                    decided_by="ДЕМО"))
            if state == "у площадки":
                db.add(LaunchPrepReview(set_id=cs.id, pair_id=pair.id, kind="площадка",
                                        source="кабинет"))
            elif state == "согласована":
                db.add(LaunchPrepReview(set_id=cs.id, pair_id=pair.id, kind="площадка",
                                        verdict="ок", source="кабинет", decided_at=now,
                                        decided_by="ДЕМО"))
                pair.agreed_at = now
            else:                       # на доработку
                db.add(LaunchPrepReview(set_id=cs.id, pair_id=pair.id, kind="площадка",
                                        verdict="на доработку", source="кабинет",
                                        decided_at=now, decided_by="ДЕМО",
                                        reason="ДЕМО: не проходит по ТТ площадки"))
        db.commit()

        # 4) состояние площадок РК под цепочку
        for _t, state, p in targets:
            p.status = PLACEMENT_BY_STATE[state]
        db.commit()
        print("площадкам РК проставлены состояния цепочки:",
              ", ".join(f"{k} — {sum(1 for _, s, _ in targets if PLACEMENT_BY_STATE[s] == k)}"
                        for k in dict.fromkeys(PLACEMENT_BY_STATE.values())))

        # 5) строки РК — штатным сборщиком, а не руками
        res = build.sync_creatives(db, camp, commit=True)
        print(f"креативов РК: создано {res.get('created')}, обновлено {res.get('updated')}")

        rows = db.execute(text("""
            SELECT COALESCE(pv.verdict, CASE WHEN tr.verdict IS NULL THEN 'у трафика'
                                             ELSE 'у площадки' END) AS состояние,
                   count(*)
              FROM launch_prep_pair pr
              JOIN launch_prep_creative_set cs ON cs.id = pr.set_id
              LEFT JOIN launch_prep_review tr ON tr.pair_id = pr.id AND tr.kind='трафики'
              LEFT JOIN launch_prep_review pv ON pv.pair_id = pr.id AND pv.kind='площадка'
             WHERE cs.deal_id = :d GROUP BY 1 ORDER BY 2 DESC
        """), {"d": deal.id}).all()
        print("раскладка пар:", ", ".join(f"{a} — {b}" for a, b in rows))
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="записать (иначе сухой прогон)")
    ap.add_argument("--undo", action="store_true", help="снять демо")
    a = ap.parse_args()
    if a.undo:
        db = SessionLocal()
        try:
            undo(db, _deal(db))
        finally:
            db.close()
    else:
        main(a.apply)
