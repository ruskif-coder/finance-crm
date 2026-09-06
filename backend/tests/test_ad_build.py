"""Порождение РК из сделок (этап 3a) — правила, согласованные с владельцем 02.09.2026.

Проверяем на РЕАЛЬНОЙ локальной базе через flush+rollback: инварианты правил, а не выдуманные
данные. Живой DSP не трогаем — этот слой вообще не ходит наружу.
"""
import pytest
from datetime import date

from sqlalchemy import text

import app.launch_prep.models  # noqa: F401
import app.models  # noqa: F401
from app.ad import build
from app.ad.models import AdCampaign, AdCampaignPlacement
from app.database import SessionLocal


def test_assembly_stages_start_at_launch_prep_and_skip_terminal():
    """«Сборка и всё после неё», без терминальных — иначе въедет архив (569 сделок)."""
    db = SessionLocal()
    try:
        ids = build.assembly_stage_ids(db)
        assert ids, "стадия сборки не найдена по stage_key=launch_prep"
        names = {r[0] for r in db.execute(text(
            "SELECT name FROM sales_stages WHERE id = ANY(:i)"), {"i": ids}).all()}
        assert "Готовятся к старту" in names          # сама Сборка
        assert "В размещении" in names                # и всё после неё
        assert "Архив успешных сделок" not in names   # терминальные — нет
        assert "Сделка сорвалась" not in names
        assert "Бронь" not in names                   # до Сборки — тоже нет
        assert "МП Подготовка" not in names
    finally:
        db.close()


def test_stage_order_uses_phase_and_sort_not_sort_alone():
    """sort_order нумеруется ВНУТРИ фазы — сравнение только по нему поймало бы чужие стадии."""
    db = SessionLocal()
    try:
        dupes = db.execute(text(
            "SELECT sort_order, count(DISTINCT phase_id) FROM sales_stages "
            "GROUP BY sort_order HAVING count(DISTINCT phase_id) > 1")).all()
        assert dupes, "если sort_order станет сквозным, правило можно упростить"
    finally:
        db.close()


def test_deal_plan_reads_service_surface_and_volume_from_media_plan():
    """У сделки нет ни услуги, ни поверхности — они лежат в строке МП (position/inventory).

    Готча: у части медиапланов `deal_id` пустой — выборка обязана это учитывать.
    """
    db = SessionLocal()
    try:
        row = db.execute(text("""
            SELECT mp.deal_id FROM sales_media_plans mp
            JOIN sales_media_plan_rows r ON r.plan_id = mp.id
            WHERE r.volume > 0 AND r.position IS NOT NULL
              AND mp.deal_id IS NOT NULL AND mp.status <> 'rejected' LIMIT 1
        """)).first()
        if not row:
            return
        plan = build.deal_plan(db, row[0])
        assert plan["has_plan"] and plan["plan_show"] > 0
        assert plan["services"], "услуга берётся из position строки МП"
        assert set(plan["surfaces"]) <= {"web", "app"}
    finally:
        db.close()


def test_inventory_cross_means_both_surfaces():
    assert build.INVENTORY_SURFACES["cross"] == ("web", "app")
    assert build.INVENTORY_SURFACES["web"] == ("web",)


def test_deal_without_media_plan_still_gets_campaign_with_empty_plan():
    """Владелец: РК заводится и без МП — пустой план ВИДИМЫЙ сигнал, что МП не сгенерирован."""
    db = SessionLocal()
    try:
        res = build.sync_campaigns(db, commit=False)
        assert res["deals"] > 0
        empty = db.execute(text("""
            SELECT count(*) FROM ad_campaign c
            WHERE c.plan_show IS NULL
              AND NOT EXISTS (SELECT 1 FROM sales_media_plans mp WHERE mp.deal_id = c.deal_id)
        """)).scalar()
        assert empty == res["no_media_plan"], "сделки без МП должны быть РК с пустым планом"
    finally:
        db.rollback()
        db.close()


def test_candidates_filtered_by_service_surface_and_exclude_archived():
    """Кандидаты — по услуге+поверхности; архивные и незаведённые поверхности отсекаются."""
    db = SessionLocal()
    try:
        svc = db.execute(text(
            "SELECT sv.name, ps.surface_kind FROM sales_publisher_services ps "
            "JOIN sales_services sv ON sv.id = ps.service_id WHERE ps.is_active LIMIT 1")).first()
        if not svc:
            return
        cands = build.candidates(db, [svc[0]], [svc[1]])
        assert all(c["surface_kind"] == svc[1] for c in cands)
        if cands:
            ids = [c["publisher_id"] for c in cands]
            bad = db.execute(text(
                "SELECT count(*) FROM sales_publishers "
                "WHERE id = ANY(:i) AND (status = 'АРХИВ' OR NOT is_active)"),
                {"i": ids}).scalar()
            assert bad == 0, "архивные площадки в кандидаты не попадают"
        assert build.candidates(db, [], ["web"]) == []      # нет услуги — нет кандидатов
        assert build.candidates(db, [svc[0]], []) == []     # нет поверхности — тоже
    finally:
        db.close()


def test_shares_are_split_among_places_that_are_in_the_plan():
    """Доля — от суммы весов участвующих в ПЛАНЕ, и это ДОЛЯ (0…1), а не проценты.

    Правило сменилось 04.09.2026 вместе с шестью статусами: раньше объём делился между
    всеми, у кого есть вес, независимо от того, крутят они или нет. Теперь выключенная
    площадка отдаёт свой объём остальным — иначе план стоял бы на строках, которые
    физически ничего не откручивают.

    Снимок в базе обязан совпадать с тем, что считает `flight.distribute`: расчёт один,
    и второго выражения с той же формулой в проекте быть не должно.
    """
    db = SessionLocal()
    try:
        cid = db.execute(text("""
            SELECT p.campaign_id FROM ad_campaign_placement p
            WHERE p.weight IS NOT NULL GROUP BY p.campaign_id LIMIT 1
        """)).scalar()
        if not cid:
            return
        pls = db.query(AdCampaignPlacement).filter_by(campaign_id=cid).all()
        for p in pls:                       # включаем всех с весом — иначе делить нечего
            if p.weight:
                p.status = "запущен"
        db.flush()
        build.recompute_shares(db, cid)
        db.flush()

        pls = db.query(AdCampaignPlacement).filter_by(campaign_id=cid).all()
        total = sum(p.share or 0 for p in pls)
        assert abs(total - 1) < 0.0001, f"сумма долей {total}, ожидали 1"
        for p in pls:
            if not p.weight:
                assert p.share is None and p.plan_show is None  # без веса ничего не выдумываем

        # ПАУЗА долю сохраняет: «из суточного плана площадка не исключается».
        first = next(p for p in pls if p.weight)
        was = next(p for p in pls if p.id == first.id).share
        first.status = "пауза"
        db.flush()
        build.recompute_shares(db, cid)
        db.flush()
        pls = db.query(AdCampaignPlacement).filter_by(campaign_id=cid).all()
        assert next(p for p in pls if p.id == first.id).share == was, (
            'пауза перекроила раскладку — а она обязана оставить долю за площадкой'
        )

        # ОТКЛЮЧЕНИЕ выводит из раскладки: объём уходит остальным, а не пропадает.
        first.status = "завершена"
        db.flush()
        build.recompute_shares(db, cid)
        db.flush()
        pls = db.query(AdCampaignPlacement).filter_by(campaign_id=cid).all()
        assert next(p for p in pls if p.id == first.id).share is None
        rest = sum(p.share or 0 for p in pls)
        assert abs(rest - 1) < 0.0001 or rest == 0, f"после отключения сумма {rest}"
    finally:
        db.rollback()
        db.close()


def test_sync_is_idempotent_and_keeps_placement_status():
    """Повторный прогон не плодит и НЕ трогает статусы: их ставит трафик по согласованию."""
    db = SessionLocal()
    try:
        before_c = db.query(AdCampaign).count()
        before_p = db.query(AdCampaignPlacement).count()
        pl = db.query(AdCampaignPlacement).first()
        if pl:
            pl.status = "запущен"      # трафик включил площадку руками
            db.flush()
            pid = pl.id
        res = build.sync_all(db, commit=False)
        assert res["created"] == 0 and res["placements_added"] == 0
        assert db.query(AdCampaign).count() == before_c
        assert db.query(AdCampaignPlacement).count() == before_p
        if pl:
            assert db.query(AdCampaignPlacement).get(pid).status == "запущен", (
                'синк перетёр ручной статус — он принадлежит трафику, а не конвейеру'
            )
    finally:
        db.rollback()
        db.close()


def test_campaign_dates_and_month_come_from_deal_period():
    db = SessionLocal()
    try:
        c = (db.query(AdCampaign).filter(AdCampaign.date_start.isnot(None)).first())
        if not c:
            return
        d = db.execute(text("SELECT period_from, period_to FROM sales_deals WHERE id=:i"),
                       {"i": c.deal_id}).first()
        assert c.date_start == d[0] and c.date_end == d[1]
        assert c.month == d[0].replace(day=1)
    finally:
        db.close()


def test_new_campaign_starts_as_waiting():
    """Свежий кандидат встаёт в «у трафика»: материал ещё никому не отправляли.

    Отдельного «ещё не начинали» в словаре из шести статусов нет (владелец 04.09.2026),
    и «у трафика» здесь не заглушка, а верное по смыслу состояние — мяч у трафика.
    """
    assert build.STATUS_WAITING == "ожидает сборки"
    assert build.PLACEMENT_NEW == "у трафика"


def test_month_of_handles_none():
    assert build.month_of(None) is None
    assert build.month_of(date(2026, 9, 17)) == date(2026, 9, 1)


def test_goals_come_from_the_same_media_plan_as_the_plan_shows():
    """KPI приёмки и план показов берутся из ОДНОГО медиаплана.

    Два отдельных запроса «последнего МП» разъехались бы на первой же новой версии:
    показы приехали бы из версии 3, цель — из версии 2, и расхождение выглядело бы как
    ошибка расчёта, а не как две выборки. Поэтому условие выбора одно (`LATEST_PLAN_SQL`)
    и оно подставляется в оба запроса.
    """
    import inspect
    from app.ad import build as b
    assert "status <> 'rejected'" in b.LATEST_PLAN_SQL, (
        'отклонённый план не обязательство — условие обязано остаться'
    )
    for fn in (b.deal_plan, b.deal_goals):
        src = inspect.getsource(fn)
        assert 'LATEST_PLAN_SQL' in src, f'{fn.__name__} выбирает план по своему условию'
        assert "status <> 'rejected'" not in src, f'{fn.__name__} завёл вторую копию условия'


def test_goals_are_returned_as_written_and_empties_dropped():
    """Значения — СТРОКИ из свободного ввода: «до 10 %» и «10» разные утверждения.

    Приводить их к числам нельзя, а пустые поля отдавать наружу незачем: экран рисовал
    бы строку без значения и обещал цель, которой нет.
    """
    from app.ad import build as b
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT deal_id, goals FROM sales_media_plans "
            "WHERE goals IS NOT NULL AND goals::text <> '{}' AND status <> 'rejected' "
            "ORDER BY deal_id LIMIT 1")).mappings().first()
        if not rows:
            pytest.skip('на стенде нет медиапланов с заполненными KPI')
        got = b.deal_goals(db, rows['deal_id'])
        assert all(isinstance(v, str) for v in got.values()), got
        assert all(str(v).strip() for v in got.values()), 'пустые значения не отдаются'
        assert set(got) <= {'freq', 'ctr', 'cr', 'volume', 'weborama'}, got
    finally:
        db.close()
