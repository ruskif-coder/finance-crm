"""Порождение РК из сделок (этап 3a) — правила, согласованные с владельцем 02.09.2026.

Проверяем на РЕАЛЬНОЙ локальной базе через flush+rollback: инварианты правил, а не выдуманные
данные. Живой DSP не трогаем — этот слой вообще не ходит наружу.
"""
import pytest
from datetime import date, timedelta

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
        # Модель ЗАДАЁТСЯ явно, а не берётся первой попавшейся: показы гарантированы
        # объёмом только у CPM, у Фикса и Пакета их вводит аккаунт, у CPC они выводятся
        # из кликов. `LIMIT 1` без сортировки отдаёт строку в физическом порядке, и на
        # данных прода 16.09.2026 сюда попал не-CPM план — тест падал на «plan_show is
        # None», хотя это ровно то поведение, которое мы и закладывали (см. mp_row).
        row = db.execute(text("""
            SELECT mp.deal_id FROM sales_media_plans mp
            JOIN sales_media_plan_rows r ON r.plan_id = mp.id
            WHERE r.volume > 0 AND r.position IS NOT NULL
              AND upper(trim(r.model)) = 'CPM'
              AND mp.deal_id IS NOT NULL AND mp.status <> 'rejected'
            ORDER BY mp.id DESC LIMIT 1
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
            JOIN sales_deals d ON d.id = c.deal_id LEFT JOIN sales_services s ON s.id = d.service_id
            LEFT JOIN sales_pipelines p ON p.id = COALESCE(d.realization_pipeline_id, s.realization_pipeline_id)
            WHERE c.plan_show IS NULL
              AND NOT EXISTS (SELECT 1 FROM sales_media_plans mp WHERE mp.deal_id = c.deal_id)
              -- контур аккаунта (14.10.2026): прогон таким РК не заводит; заведённые раньше в подсчёт не идут
              AND p.closing_flow IS DISTINCT FROM 'контур аккаунта'
              -- 15.11.2026: считаем только сделки, которые прогон и обходит (стадии сборки и дальше).
              -- РК сорвавшейся сделки (ZJRAU3, «Сделка не случилась») остаётся с пустым планом,
              -- но прогон её не видит — сравнивать её с no_media_plan было ошибкой теста.
              AND d.our_stage_id = ANY(:st)
        """), {"st": build.assembly_stage_ids(db)}).scalar()
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
        # Идемпотентность — свойство ВТОРОГО прогона, а не первого. Раньше тест требовал
        # нуля сразу, то есть молча предполагал, что витрина уже наполнена. На копии прода
        # 16.09.2026 она пуста (строки `sync_ad_campaigns` нет в кроне прода вовсе), и
        # первый же прогон создал 88 пар — падение говорило про состояние данных, а не
        # про то, ради чего тест написан.
        build.sync_all(db, commit=False)
        db.flush()
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
    """Свежий кандидат встаёт в «ждёт сборки»: креативов по нему ещё нет вовсе.

    До 18.09.2026 отдельного состояния не было, и кандидат рождался «у трафика» — «мяч
    у нас». На экране это выглядело как очередь работы: двадцать площадок звали трафик
    к задачам, которых не существует. Владелец назвал порог прямо: «у трафика» — только
    после отправки хотя бы одного креатива по этой площадке.
    """
    assert build.STATUS_WAITING == "ожидает сборки"
    assert build.PLACEMENT_WAIT == "ждёт сборки"


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


# ── единица объёма РК (22.11.2026, кликовые объёмы в биддере) ──────────────────
#
# Страница «Биддер» и DSP делят план РК между площадками, и у CPC-сделки объём — КЛИКИ.
# Единицу РК берём из формы расчёта услуги сделки: справочник услуг заполняется руками,
# поэтому сравнение обязано быть регистронезависимым («CPC», «cpc», « CPC »). База этим
# тестам не нужна вовсе — правило чистое.

def test_unit_for_cpc():
    from app.ad.build import unit_for
    assert unit_for("CPC") == "click"
    assert unit_for("cpc") == "click"          # регистронезависимо
    assert unit_for(" CPC ") == "click"        # справочник заполняется руками — с пробелами тоже


def test_unit_for_show():
    from app.ad.build import unit_for
    assert unit_for("CPM") == "show"
    assert unit_for("Фикс") == "show"
    assert unit_for(None) == "show"


# ── раскладка в единице РК: клики у click-РК, показы у остальных (22.11.2026) ──
#
# `distribute` единицу не знает — он делит одно число. Знание единицы живёт в вызывающем
# (`build.campaign_layout`) и в чтении факта (`bidder/facts`), поэтому проверяется именно
# сквозной результат раскладки: сумма планов площадок и то, из какой колонки взят факт.
#
# Числа подобраны так, чтобы перепутанная единица была ВИДНА в сумме, а не в подписи:
# факт одной площадки больше её доли по весам, поэтому раскладка поднимает её план до
# факта, и «не та» колонка даёт вместо плана РК её величину.

def _layout_env(db):
    """РК и ровно ДВЕ площадки в раскладке — чтобы сумма планов не ловила округление.

    Остальные площадки РК выводятся из раскладки (вес снят): на трёх и более площадках
    деление даёт 333/333/333 и `sum(планы) == план` проверялось бы с оговоркой на
    округление, то есть перестало бы быть проверкой единицы.
    """
    cid = db.execute(text(
        "SELECT campaign_id FROM ad_campaign_placement "
        "GROUP BY campaign_id HAVING count(*) >= 2 ORDER BY campaign_id LIMIT 1")).scalar()
    if not cid:
        pytest.skip("на стенде нет РК с двумя и более площадками")
    camp = db.query(AdCampaign).get(cid)
    pls = (db.query(AdCampaignPlacement)
           .filter(AdCampaignPlacement.campaign_id == cid)
           .order_by(AdCampaignPlacement.id).all())
    keep = pls[:2]
    for p in keep:
        p.weight = 1.0            # равные веса: делим ровно пополам
        p.status = "запущен"
        p.fixed_plan = 0          # ручной план главнее объёма по креативам — иначе план не по весам
        p.share = None
        p.plan_show = None
    for p in pls[2:]:
        p.weight = None           # вне раскладки — иначе деление не на две доли
        p.status = "ждёт сборки"
        p.fixed_plan = 0
    # Флайт за пределами удержания (первые 5 дней): только с 6-го дня факт участвует в раскладке.
    camp.date_start = date.today() - timedelta(days=10)
    camp.date_end = date.today() + timedelta(days=20)
    db.flush()
    return camp, keep


def _stat_rows(db, campaign_id, values):
    """Свои строки факта РК: values = [(площадка, показы, клики), …].

    Дата — сегодня и источник `ms` (боевой, `stat_sources.COMBAT`): со старым срезом
    `fact_as_of` отдал бы устаревшую дату, `is_stale` погасил факт, и тест молча проверял
    бы раскладку без факта. Всё это откатывается транзакцией теста.
    """
    db.execute(text("DELETE FROM ad_campaign_stat WHERE campaign_id = :c"), {"c": campaign_id})
    for p, shows, clicks in values:
        db.execute(text(
            "INSERT INTO ad_campaign_stat (campaign_id, placement_id, date, shows, clicks, source) "
            "VALUES (:c, :p, :d, :s, :k, 'ms')"),
            {"c": campaign_id, "p": p.id, "d": date.today(), "s": shows, "k": clicks})
    db.flush()


def test_layout_show_unit_unchanged():
    """Регрессия CPM: у РК с `unit="show"` раскладка делит `plan_show`, факт — из `shows`.

    Клики в тех же строках нарочно огромные: если бы факт читался из `clicks`, площадка
    была бы поднята до них (правило «план не ниже факта») и сумма планов ушла бы с 1000
    на 5000. Именно это и ловит сумма, а не отдельная проверка колонки.
    """
    from app.bidder.facts import placement_facts
    db = SessionLocal()
    try:
        camp, keep = _layout_env(db)
        camp.unit = "show"
        camp.plan_show = 1000
        camp.plan_click = 9000          # впятеро больше: перепутанная единица видна сразу
        db.flush()
        _stat_rows(db, camp.id, [(keep[0], 5, 5000), (keep[1], 3, 4000)])

        # факт по умолчанию — показы; клики лежат отдельной колонкой той же строки
        shows = placement_facts(db, [camp.id])
        clicks = placement_facts(db, [camp.id], "click")
        assert shows[camp.id][keep[0].id] == 5
        assert clicks[camp.id][keep[0].id] == 5000

        _, out = build.campaign_layout(db, camp.id, cap_ctx=(None, {}), with_boost=False)
        rows = [r for r in out["rows"] if r.get("in_plan")]
        total = sum(r["plan_show"] or 0 for r in rows)
        assert len(rows) == 2
        assert total == 1000, f"сумма планов площадок {total}, ожидали plan_show=1000"
        assert out["facts_used"] is True, "факт не попал в раскладку — тест проверял бы не то"
        assert all(r["plan_show"] == 500 for r in rows), [r["plan_show"] for r in rows]
    finally:
        db.rollback()
        db.close()


def test_layout_click_unit_distributes_clicks():
    """У РК с `unit="click"` раскладка делит `plan_click`, а факт читается из `clicks`.

    Числа: план 1000, доли по весам 500/500, клики 900 и 3 — площадка с 900 поднимается
    до факта, второй уходит остаток 100. Сумма остаётся 1000, то есть делится план в
    КЛИКАХ. Прочитай вызывающий `shows` (5000/4000) — сумма стала бы 9000, а план
    площадки — 5000; прочитай `plan_show` вместо `plan_click` — сумма стала бы 5000.
    """
    from app.bidder.facts import placement_facts
    db = SessionLocal()
    try:
        camp, keep = _layout_env(db)
        camp.unit = "click"
        camp.plan_click = 1000
        camp.plan_show = 5000           # показов впятеро больше — единицу видно по сумме
        db.flush()
        _stat_rows(db, camp.id, [(keep[0], 5000, 900), (keep[1], 4000, 3)])

        shows = placement_facts(db, [camp.id])
        clicks = placement_facts(db, [camp.id], "click")
        assert clicks[camp.id][keep[0].id] == 900
        assert shows[camp.id][keep[0].id] == 5000

        _, out = build.campaign_layout(db, camp.id, cap_ctx=(None, {}), with_boost=False)
        by_id = {r["id"]: r for r in out["rows"]}
        rows = [r for r in out["rows"] if r.get("in_plan")]
        total = sum(r["plan_show"] or 0 for r in rows)
        assert len(rows) == 2
        assert total == 1000, f"сумма планов площадок {total}, ожидали plan_click=1000"
        assert out["facts_used"] is True, "факт не попал в раскладку — тест проверял бы не то"
        # факт площадки = её клики, и план поднят до факта (правило 05.10.2026)
        assert by_id[keep[0].id]["plan_show"] == 900
        assert by_id[keep[1].id]["plan_show"] == 100
        assert all(r["plan_show"] < shows[camp.id][r["id"]] for r in rows), (
            "план площадки оказался в показах — единица РК не прошита"
        )
    finally:
        db.rollback()
        db.close()
