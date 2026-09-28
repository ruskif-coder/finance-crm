"""Отвязать РК от объектов DSP, заведённых под прежним клиентом кабинета (28.09.2026).

Что случилось: боевые РК выгрузили в DSP, когда в настройках стоял клиент демо-кабинета
(`DSP_PARTNER_XXHASH`). Клиента сменили на боевой, а хеши кампании и креативов остались
записаны за РК — выгрузка считает их заведёнными и в новый кабинет ничего не шлёт.

Скрипт стирает эти хеши у названных РК (кампания и все её креативы), а прежние значения
пишет в журнал действий — чтобы найти оставшиеся объекты в демо-кабинете. После него
обычная кнопка «D» на дашборде трафика заведёт РК заново под текущим клиентом: защита
от дублей с 28.09.2026 ищет в журнале DSP только хеши своего клиента.

В самом DSP скрипт ничего не трогает и никуда не ходит: объекты под демо-клиентом
остаются там как есть (удалить их по API нельзя).

Запуск: сначала посмотреть —
    docker exec finance_backend python -m scripts.2026-09-28_dsp_partner_reset 45 46
потом применить —
    docker exec finance_backend python -m scripts.2026-09-28_dsp_partner_reset 45 46 --apply
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import app.main  # noqa: F401,E402 — все модели в реестре
from app.ad.models import AdCampaign, AdCampaignCreative  # noqa: E402
from app.audit import log_action  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.sales.models import SalesDeal  # noqa: E402

ADMIN = "d.makarov@simb-ad.com"


def main(argv):
    apply = "--apply" in argv
    ids = [int(a) for a in argv if a.isdigit()]
    if not ids:
        print("Укажите id РК: python -m scripts.2026-09-28_dsp_partner_reset 45 46 [--apply]")
        return 1
    db = SessionLocal()
    admin = db.query(User).filter(User.email == ADMIN).first()
    for cid in ids:
        camp = db.get(AdCampaign, cid)
        if camp is None:
            print(f"РК {cid}: нет такой — пропуск")
            continue
        deal = db.get(SalesDeal, camp.deal_id)
        cres = (db.query(AdCampaignCreative)
                .filter(AdCampaignCreative.campaign_id == cid,
                        AdCampaignCreative.ms_creative_xxhash.isnot(None))
                .order_by(AdCampaignCreative.id).all())
        old = {"campaign": camp.ms_campaign_xxhash,
               "creatives": {c.id: c.ms_creative_xxhash for c in cres}}
        print(f"РК {cid} ({deal.code if deal else '?'}): кампания {old['campaign'] or '—'}, "
              f"креативов с хешем {len(cres)}")
        for c in cres:
            print(f"    креатив {c.id}: {c.ms_creative_xxhash}")
        if not apply:
            continue
        # Сначала след в журнале, потом стирание: без следа объекты в демо-кабинете
        # останется искать только по журналу вызовов DSP.
        log_action(db, admin, "dsp_partner_reset", "ad_campaign", cid,
                   f"отвязано от DSP (клиент кабинета сменён): {old}")
        camp.ms_campaign_xxhash = None
        camp.ms_synced_at = None
        for c in cres:
            c.ms_creative_xxhash = None
        db.commit()
        print("    → отвязано")
    if not apply:
        print("\nСухой прогон: ничего не изменено. Применить — добавьте --apply")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
