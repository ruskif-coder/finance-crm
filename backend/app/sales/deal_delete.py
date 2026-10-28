# -*- coding: utf-8 -*-
"""Удаление сделок — одни правила для реестра и для удаления воронки.

Решение владельца 23.09.2026 и аудит 3.H3 / 3.M9. Удаление сделки каскадом снимает
кампании, разнесения по приложениям, сборку запуска и историю стадий, а медиапланы
оставляет без сделки. Поэтому сделка с привязанной работой не удаляется ни из реестра, ни
вместе с воронкой: сначала отвязать — тогда удаление осознанное.

Два внешних ключа без каскада (комментарии и «продление от») роняли удаление с 500 —
`purge_links` снимает их явно.
"""
from __future__ import annotations


def holders(db, deal_ids) -> dict:
    """{id сделки: [что к ней привязано]} — пусто, если удалять можно."""
    from app.ad.models import AdCampaign
    from app.launch_prep.models import LaunchPrepTarget
    from app.sales.models import SalesDealAnnexAllocation, SalesMediaPlan
    ids = list(deal_ids or [])
    if not ids:
        return {}
    held: dict = {}
    for what, col in (("приложение к договору", SalesDealAnnexAllocation.deal_id),
                      ("кампания трафика", AdCampaign.deal_id),
                      ("медиаплан", SalesMediaPlan.deal_id),
                      ("сборка запуска", LaunchPrepTarget.deal_id)):
        for (did,) in db.query(col).filter(col.in_(ids)).distinct().all():
            held.setdefault(did, []).append(what)
    return held


# ── Удаление админом со всей цепочкой (владелец 23.10.2026) ──────────────────────────────────────────────────────────
# Решение 23.09 «сделку с работой не удаляет никто» для админа заменено: наше (медиаплан, РК без DSP, сборка, сверка,
# комментарии, файлы) стирается вместе со сделкой. Но то, что УЖЕ ушло наружу, у нас не стереть — сотрём запись, а снаружи
# останется живое без хозяина. Поэтому внешний след — отказ с перечнем («внешнее — блок»).
_EXTERNAL = (
    ("РК в DSP", "SELECT deal_id FROM ad_campaign WHERE deal_id = ANY(:ids) AND ms_campaign_xxhash IS NOT NULL"),
    ("креатив в DSP", """SELECT c.deal_id FROM ad_campaign_creative x JOIN ad_campaign c ON c.id = x.campaign_id
                          WHERE c.deal_id = ANY(:ids) AND x.ms_creative_xxhash IS NOT NULL"""),
    ("креатив нацеливания в DSP", """SELECT deal_id FROM launch_prep_creative_set
                                      WHERE deal_id = ANY(:ids) AND ms_targeting_creative_xxhash IS NOT NULL"""),
    ("ЕРИД в ОРД", "SELECT deal_id FROM launch_prep_creative_set WHERE deal_id = ANY(:ids) AND erid IS NOT NULL"),
    ("ЕРИД в ОРД", """SELECT c.deal_id FROM ad_campaign_creative x JOIN ad_campaign c ON c.id = x.campaign_id
                       WHERE c.deal_id = ANY(:ids) AND x.erid IS NOT NULL"""),
    ("креатив в ОРД", """SELECT s.deal_id FROM ord_creatives o JOIN launch_prep_creative_set s ON s.id = o.creative_set_id
                          WHERE s.deal_id = ANY(:ids) AND (o.ord_id IS NOT NULL OR o.erid IS NOT NULL)"""),
    ("задача в кабинете площадки", """SELECT t.deal_id FROM launch_prep_pair p JOIN launch_prep_target t ON t.id = p.target_id
                                       WHERE t.deal_id = ANY(:ids) AND p.sent_at IS NOT NULL"""),
    ("запрос в кабинете площадки", "SELECT deal_id FROM publisher_request WHERE deal_id = ANY(:ids)"),
    ("приоритезация у площадки", """SELECT r.deal_id FROM prio_placements p JOIN prio_requests r ON r.id = p.request_id
                                     WHERE r.deal_id = ANY(:ids) AND (p.sent_at IS NOT NULL OR p.erid IS NOT NULL)"""),
    ("мастер-сделка", """SELECT i.deal_id FROM master_deal_items i WHERE i.deal_id = ANY(:ids)"""),
    # ДС (приложение) — документ, который уже у клиента; удаление сделки оставило бы его без сделки (ревью 23.10.2026)
    ("ДС к договору", "SELECT deal_id FROM sales_deal_annex_allocation WHERE deal_id = ANY(:ids)"),
    # ревью 27.10.2026: сверка, ушедшая в документооборот, — сумма уже у бухгалтерии; сделку, отвязанную от пакета после
    # «Отправить в ДО», удаление стирало вместе с замороженной суммой
    ("сверка отправлена в ДО", "SELECT deal_id FROM final_recon_deals WHERE deal_id = ANY(:ids) AND sent_at IS NOT NULL"),
    # СК, начисленная в закрытом месяце, — снимок расчёта; ключ без каскада ронял удаление с 500
    ("СК начислена в закрытом месяце", "SELECT deal_id FROM sk_accruals WHERE deal_id = ANY(:ids)"),
)


def external(db, deal_ids) -> dict:
    """{id сделки: [что ушло наружу]} — пусто, если цепочку можно стереть целиком."""
    from sqlalchemy import text
    ids = list(deal_ids or [])
    held: dict = {}
    if not ids:
        return held
    for what, sql in _EXTERNAL:
        for (did,) in db.execute(text(sql), {"ids": ids}).all():
            if what not in held.setdefault(did, []):
                held[did].append(what)
    return held


def purge_chain(db, deal_ids) -> list:
    """Стирает нашу цепочку сделок; сами сделки и то, что уходит каскадом по ключам, удаляет вызывающий.
    Возвращает уборку диска — звать ПОСЛЕ commit: файл без строки — сирота, строка без файла — битая ссылка."""
    from sqlalchemy import text
    ids = list(deal_ids or [])
    if not ids:
        return []
    p = {"ids": ids}
    files = [(r[0], r[1], "creative") for r in db.execute(text(
        """SELECT f.path, f.sandbox_token FROM launch_prep_creative_file f JOIN launch_prep_creative_set s ON s.id = f.set_id
            WHERE s.deal_id = ANY(:ids)"""), p).all()]
    files += [(r[0], None, "plain") for r in db.execute(text(
        """SELECT f.path FROM launch_prep_pair_file f JOIN launch_prep_pair x ON x.id = f.pair_id
             JOIN launch_prep_target t ON t.id = x.target_id WHERE t.deal_id = ANY(:ids)
           UNION ALL SELECT rights_letter_path FROM launch_prep_creative_set WHERE deal_id = ANY(:ids) AND rights_letter_path IS NOT NULL
           UNION ALL SELECT path FROM sales_deal_files WHERE deal_id = ANY(:ids)"""), p).all()]
    files += [(r[0], None, "brief") for r in db.execute(text(
        "SELECT filename FROM sales_deal_brief_files WHERE deal_id = ANY(:ids)"), p).all()]
    # Удаление — через ORM, а не сырым SQL (прибор test_startup_ddl). Без внешних ключей к сделке: черновики ОРД по комплекту
    # и медиапланы (строки и допы уходят каскадом от плана); ключ без каскада — итоговая сверка (строки факта — каскадом от сделки).
    from app.final_recon.models import FinalReconDeal
    from app.launch_prep.models import LaunchPrepCreativeSet
    from app.ord.models import OrdCreative
    from app.sales.models import SalesMediaPlan
    sets = [i for (i,) in db.query(LaunchPrepCreativeSet.id).filter(LaunchPrepCreativeSet.deal_id.in_(ids)).all()]
    if sets:
        db.query(OrdCreative).filter(OrdCreative.creative_set_id.in_(sets)).delete(synchronize_session=False)
    db.query(SalesMediaPlan).filter(SalesMediaPlan.deal_id.in_(ids)).delete(synchronize_session=False)
    db.query(FinalReconDeal).filter(FinalReconDeal.deal_id.in_(ids)).delete(synchronize_session=False)
    db.flush()
    purge_links(db, ids)
    return files


def clean_disk(files) -> None:
    from app.files_safe import remove_upload
    from app.routers.launch_prep import _remove_file
    from app.routers.sales_dashboard import BRIEF_UPLOADS_DIR
    for path, token, kind in files:
        if kind == "creative":
            _remove_file(path, token)
        elif kind == "brief":
            remove_upload(path, root=BRIEF_UPLOADS_DIR)
        else:
            remove_upload(path)


def describe(db, held: dict) -> str:
    from app.sales.models import SalesDeal
    codes = {d.id: d.code or str(d.id) for d in
             db.query(SalesDeal).filter(SalesDeal.id.in_(list(held))).all()}
    return "; ".join(f"{codes.get(i, i)} — {', '.join(w)}" for i, w in sorted(held.items()))


def purge_links(db, deal_ids) -> None:
    """Внешние ключи без каскада: комментарии уходят со сделкой, ссылку «продление от» у
    ДРУГИХ сделок снимаем, а не удаляем сами сделки."""
    from app.sales.models import SalesDeal, SalesDealComment
    ids = list(deal_ids or [])
    if not ids:
        return
    db.query(SalesDealComment).filter(SalesDealComment.deal_id.in_(ids)).delete(
        synchronize_session=False)
    db.query(SalesDeal).filter(SalesDeal.prolonged_from_id.in_(ids)).update(
        {SalesDeal.prolonged_from_id: None}, synchronize_session=False)
