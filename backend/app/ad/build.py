"""Порождение РК из сделок (этап 3a) — пропущенное звено между сделкой и DSP.

Правила согласованы с владельцем 02.09.2026:

1. **Триггер — «Сборка и всё после неё».** «Сборка» = стадия `stage_key='launch_prep'`
   («Готовятся к старту»). Последовательность стадий — это пара `(phase_id, sort_order)`,
   а НЕ один `sort_order` (он нумеруется внутри фазы заново). Терминальные исключены —
   иначе в дашборд въехал бы «Архив успешных сделок» (569 сделок), плюс сорвавшиеся.
2. **План показов — из медиаплана.** В строке МП лежит и услуга (`position`), и поверхность
   (`inventory` = web | app | cross), и объём (`volume`). У сделки самой ни услуги, ни
   поверхности нет. Сделка без МП РК всё равно получает — с пустым планом: это ВИДИМЫЙ сигнал,
   что медиаплан не заведён (владелец: «сделка на этапе сборки безусловно должна обладать
   сгенерированным медиапланом»).
3. **Кандидаты площадок — фильтр «услуга + поверхность»** по `sales_publisher_services`
   (услуга сопоставляется по имени: `position` строки МП ↔ `sales_services.name`).
   Отсекаются архивные площадки и поверхности, не заведённые во вкладке «Настройка блоков»
   (нет ни `ms_publisher_id`, ни блоков — значит нет ни подключения к МС, ни инвентаря).
4. **Подключение — по мере согласования креативов.** Кандидат заводится со статусом `выкл`;
   `вкл` ставится, когда согласован креатив (конвейер `launch_prep`). Поэтому повторный
   прогон — идемпотентный: он ДОБАВЛЯЕТ новых кандидатов и не трогает статусы существующих.
5. **Вес — индекс балансировщика** (`publisher_balance_index`, действующий =
   `COALESCE(index_manual, index_auto)`). Площадка без индекса включается, но доля ей не
   считается — в строке это видно как «нет индекса» (владелец: «к релизу заполним данные»).
   Доли считаются от суммы весов ТОЛЬКО тех, у кого вес есть.

Схема не меняется — всё ложится в накатанные `ad_campaign` / `ad_campaign_placement`.
"""
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.sales import mp_row

from app.ad.balance import SCOPES, SCOPE_SURFACE
from app.ad.flight import (PLACEMENT_NEW, PLACEMENT_READY, as_placement_scale,
                           best_chain_status, chain_status, distribute, effective_status,
                           effective_status_creative)
from app.ad.models import AdCampaign, AdCampaignCreative, AdCampaignPlacement
from app.sales.models import PUBLISHER_ARCHIVE_STATUS

ASSEMBLY_STAGE_KEY = "launch_prep"      # «Готовятся к старту» = Сборка
STATUS_WAITING = "ожидает сборки"
# Статус свежего кандидата. Шесть статусов площадки (владелец 04.09.2026) не содержат
# отдельного «ещё не начинали»: первые три ставит конвейер согласования, и «у трафика»
# среди них — самое раннее. Оно же верно по смыслу: пока материал никому не отправлен,
# мяч действительно у трафика. Словарь целиком — в `app/ad/flight.py`.
# inventory строки МП → поверхности справочника (sales_publisher_services.surface_kind)
INVENTORY_SURFACES = {"web": ("web",), "app": ("app",), "cross": ("web", "app")}


# ── стадии ────────────────────────────────────────────────────────────────

def assembly_stage_ids(db: Session) -> list:
    """Стадии «Сборка и всё после неё», кроме терминальных.

    Порядок — пара (phase_id, sort_order): `sort_order` внутри фазы начинается заново,
    поэтому сравнивать только по нему нельзя.
    """
    a = db.execute(text(
        "SELECT phase_id, sort_order FROM sales_stages WHERE stage_key = :k "
        "ORDER BY phase_id, sort_order LIMIT 1"), {"k": ASSEMBLY_STAGE_KEY}).first()
    if not a:
        return []
    return [r[0] for r in db.execute(text(
        "SELECT id FROM sales_stages "
        "WHERE NOT is_terminal AND (phase_id, sort_order) >= (:ph, :so)"),
        {"ph": a[0], "so": a[1]}).all()]


# ── план из медиаплана ────────────────────────────────────────────────────

# КАКОЙ медиаплан считается планом сделки — одно определение на всех потребителей.
# Отклонённый (`rejected`) не берём: его объём не обязательство. Второй экземпляр этого
# условия означал бы, что план показов и KPI приёмки могут приехать из РАЗНЫХ версий МП,
# и расхождение выглядело бы как ошибка расчёта, а не как две выборки.
LATEST_PLAN_SQL = ("SELECT id FROM sales_media_plans "
                   "WHERE deal_id = :d AND status <> 'rejected' "
                   "ORDER BY version DESC, id DESC LIMIT 1")


def deal_plan(db: Session, deal_id: int) -> dict:
    """Услуги, поверхности и план показов сделки — из строк последнего медиаплана."""
    rows = db.execute(text(f"""
        SELECT r.position, r.inventory, r.volume, r.unit_price, r.model,
               r.discount, r.forecast
        FROM sales_media_plan_rows r
        JOIN sales_media_plans mp ON mp.id = r.plan_id
        WHERE mp.deal_id = :d AND mp.id = ({LATEST_PLAN_SQL})
    """), {"d": deal_id}).mappings().all()

    services, surfaces, shows, budget = set(), set(), 0.0, 0.0
    for r in rows:
        if (r["position"] or "").strip():
            services.add(r["position"].strip())
        for s in INVENTORY_SURFACES.get((r["inventory"] or "").strip().lower(), ()):
            surfaces.add(s)
        # Показы и деньги — по общей арифметике строки (app/sales/mp_row.py). Здесь
        # стояло безусловное «объём = показы» и «/1000», то есть строка Фикса давала
        # РК лимит в 1 показ и бюджет 80 ₽ вместо 80 000.
        shows += mp_row.row_imp(r["model"], r["volume"], r["forecast"])
        budget += mp_row.row_net(r["model"], r["volume"], r["unit_price"], r["discount"])
    return {"services": sorted(services), "surfaces": sorted(surfaces),
            "plan_show": shows or None, "plan_budget": budget or None,
            "has_plan": bool(rows)}


def deal_goals(db: Session, deal_id: int) -> dict:
    """KPI приёмки размещения из ТОГО ЖЕ медиаплана, что дал план показов.

    Пять значений (частота, CTR, CR, показы/клики, расхождение с Weborama) лежат в
    `sales_media_plans.goals` СТРОКАМИ: в конструкторе МП это поля свободного ввода
    («до 10 %», «0,8»), и приводить их к числам здесь нельзя — «до 10 %» и «10» разные
    утверждения, а превращать одно в другое значило бы решать за аккаунта.

    Поэтому трафику они и ПОКАЗЫВАЮТСЯ как есть, рядом с фактом, без автоматического
    вердикта «уложились / не уложились». Сверку делает человек.
    """
    row = db.execute(text(f"SELECT goals FROM sales_media_plans WHERE id = ({LATEST_PLAN_SQL})"),
                     {"d": deal_id}).first()
    goals = (row[0] if row else None) or {}
    return {k: v for k, v in goals.items() if str(v or "").strip()}


def pixel_setup(db: Session, deal_id: int) -> dict:
    """Как устроен пиксель у этой сделки: заказан ли, свой или внешний, и сам тег.

    Одним запросом и одной функцией, потому что спрашивают это три контура сразу
    (карточка, DSP, разметка стадий) и спрашивают ВМЕСТЕ: «нужен ли» без «какой» уже
    недостаточно с 14.09.2026, когда появился внешний тег.

    `tag` не пустой только у внешнего: у своего пиксель живёт на КАЖДОМ размещении
    отдельно, потому что вставка там на площадку. У внешнего вставка одна на всю сеть,
    и тег один на кампанию.
    """
    row = db.execute(text(
        "SELECT weborama_pixel, weborama_pixel_mode, weborama_pixel_tag "
        "FROM sales_deals WHERE id = :d"), {"d": deal_id}).first()
    if not row:
        return {"needed": False, "mode": "own", "tag": None}
    needed = bool(row[0])
    mode = (row[1] or "own") if needed else "own"
    return {"needed": needed, "mode": mode,
            "tag": (row[2] or None) if (needed and mode == "external") else None}


def needs_pixel(db: Session, deal_id: int) -> bool:
    """Заказан ли по этой сделке пиксель верификатора (Weborama).

    Живёт ЗДЕСЬ, а не в одном из коннекторов, потому что читают его двое: контур
    Weborama (заводить ли вставки) и контур DSP (требовать ли пиксель перед выгрузкой и
    вшивать ли тег в разметку). Держать признак у одного из них значило бы, что второй
    ходит к соседу за правилом — и однажды они разойдутся.

    Признак на СДЕЛКЕ, а не на РК: у `ad_campaign` `deal_id` с UNIQUE, а ставится
    галочка на сборке, когда строки РК может ещё не быть (миграция 2026-09-14).
    """
    return pixel_setup(db, deal_id)["needed"]


def month_of(d: Optional[date]) -> Optional[date]:
    return d.replace(day=1) if d else None


# ── порождение РК ─────────────────────────────────────────────────────────

def sync_campaigns(db: Session, commit: bool = True) -> dict:
    """Заводит РК недостающим сделкам и подтягивает план у существующих.

    Статус РК НЕ трогаем у уже заведённых: им управляет трафик (и запуск по событию).
    """
    stage_ids = assembly_stage_ids(db)
    if not stage_ids:
        return {"created": 0, "updated": 0, "no_media_plan": 0, "stages": 0}

    deals = db.execute(text(
        "SELECT id, code, period_from, period_to FROM sales_deals "
        "WHERE our_stage_id = ANY(:st) ORDER BY id"), {"st": stage_ids}).mappings().all()
    existing = {c.deal_id: c for c in db.query(AdCampaign).all()}

    created = updated = no_mp = 0
    for d in deals:
        plan = deal_plan(db, d["id"])
        if not plan["has_plan"]:
            no_mp += 1
        camp = existing.get(d["id"])
        if camp is None:
            camp = AdCampaign(deal_id=d["id"], status=STATUS_WAITING)
            db.add(camp)
            created += 1
        else:
            updated += 1
        camp.month = month_of(d["period_from"])
        camp.date_start = d["period_from"]
        camp.date_end = d["period_to"]
        camp.plan_show = plan["plan_show"]
        camp.plan_budget = plan["plan_budget"]
    db.flush()
    if commit:
        db.commit()
    return {"created": created, "updated": updated, "no_media_plan": no_mp,
            "stages": len(stage_ids), "deals": len(deals)}


# ── разворот площадок ─────────────────────────────────────────────────────

def candidates(db: Session, services: list, surfaces: list) -> list:
    """Площадки под услугу+поверхность: активные, не архив, поверхность заведена в блоках."""
    if not services or not surfaces:
        return []
    return db.execute(text("""
        SELECT DISTINCT ps.publisher_id, ps.surface_kind
        FROM sales_publisher_services ps
        JOIN sales_services sv ON sv.id = ps.service_id
        JOIN sales_publishers p ON p.id = ps.publisher_id
        JOIN sales_publisher_surfaces s ON s.publisher_id = p.id AND s.kind = ps.surface_kind
        WHERE ps.is_active AND sv.name = ANY(:svc) AND ps.surface_kind = ANY(:surf)
          AND p.is_active AND p.status <> :arch
          AND (s.ms_publisher_id IS NOT NULL
               OR EXISTS (SELECT 1 FROM publisher_block b WHERE b.surface_id = s.id))
    """), {"svc": services, "surf": surfaces,
           "arch": PUBLISHER_ARCHIVE_STATUS}).mappings().all()


def publisher_weights(db: Session, surfaces: list) -> dict:
    """Действующий индекс площадки, сложенный по поверхностям РК (web / app→android+ios)."""
    scopes = [sc for sc in SCOPES if SCOPE_SURFACE[sc] in surfaces]
    if not scopes:
        return {}
    out = {}
    for r in db.execute(text(
        "SELECT publisher_id, COALESCE(index_manual, index_auto) AS w "
        "FROM publisher_balance_index WHERE scope = ANY(:sc)"),
            {"sc": scopes}).mappings().all():
        if r["w"]:
            out[r["publisher_id"]] = out.get(r["publisher_id"], 0.0) + float(r["w"])
    return out


def recompute_shares(db: Session, campaign_id: int) -> None:
    """Доли и планы площадок — снимок текущего распределения.

    Считает НЕ здесь: правило живёт в `app/ad/flight.distribute` вместе с тем, что
    рисует экран. Второе выражение с той же формулой разошлось бы с первым на первой
    правке — а расходятся такие вещи молча, цифрами, которые выглядят правдоподобно.

    Доля — ДОЛЯ (0…1), а не проценты: до 04.09.2026 здесь хранились проценты, и рядом
    с долей из `distribute()` они читались бы как одно и то же число в сто раз больше.

    Пересчитывать надо после КАЖДОЙ смены статуса площадки: доля считается по крутящим,
    и выключенная площадка отдаёт свой объём остальным.
    """
    pls = (db.query(AdCampaignPlacement)
           .filter(AdCampaignPlacement.campaign_id == campaign_id).all())
    camp = db.query(AdCampaign).get(campaign_id)
    out = distribute(camp.plan_show if camp else None, None, None,
                     [{"id": p.id, "status": p.status, "weight": p.weight} for p in pls])
    by_id = {r["id"]: r for r in out["rows"]}
    for p in pls:
        r = by_id[p.id]
        p.share = r["share"] or None
        p.plan_show = r["plan_show"]


def sync_placements(db: Session, camp: AdCampaign, commit: bool = True) -> dict:
    """Добавляет недостающих кандидатов в РК. Существующие не трогает (статусы — за трафиком)."""
    plan = deal_plan(db, camp.deal_id)
    cands = candidates(db, plan["services"], plan["surfaces"])
    weights = publisher_weights(db, plan["surfaces"])
    have = {p.publisher_id for p in db.query(AdCampaignPlacement)
            .filter(AdCampaignPlacement.campaign_id == camp.id).all()}

    added = 0
    for c in cands:
        pid = c["publisher_id"]
        if pid in have:
            continue
        db.add(AdCampaignPlacement(campaign_id=camp.id, publisher_id=pid,
                                   weight=weights.get(pid), status=PLACEMENT_NEW))
        have.add(pid)
        added += 1
    db.flush()
    # вес мог появиться у уже заведённых (балансировщик наполняется) — обновляем и пересчитываем
    for p in db.query(AdCampaignPlacement).filter(
            AdCampaignPlacement.campaign_id == camp.id).all():
        w = weights.get(p.publisher_id)
        if w is not None:
            p.weight = w
    recompute_shares(db, camp.id)
    db.flush()
    if commit:
        db.commit()
    return {"candidates": len(cands), "added": added,
            "without_weight": sum(1 for c in cands if not weights.get(c["publisher_id"]))}


def root_set_map(db: Session, deal_id: int) -> dict:
    """Комплект → корень его цепочки доработок.

    Доработка рождает НОВЫЙ комплект со ссылкой `replaces_set_id` на предыдущий. Для нас
    креатив — рекламное СООБЩЕНИЕ (владелец 04.09.2026), а правки технические, поэтому
    личностью служит корень цепочки, а не конкретная версия.

    Цикл в ссылках разорвать нечем, но и завестись ему неоткуда: замена всегда ссылается
    на уже существующий комплект. Ограничитель на глубину всё равно стоит — бесконечный
    цикл здесь означал бы висящий запрос, а не заметную ошибку.
    """
    rows = db.execute(text(
        "SELECT id, replaces_set_id FROM launch_prep_creative_set WHERE deal_id = :d"),
        {"d": deal_id}).mappings().all()
    parent = {r["id"]: r["replaces_set_id"] for r in rows}
    out = {}
    for sid in parent:
        cur, seen = sid, 0
        while parent.get(cur) and seen < 20:
            cur, seen = parent[cur], seen + 1
        out[sid] = cur
    return out


def sync_creatives(db: Session, camp: AdCampaign, commit: bool = True) -> dict:
    """Заводит креативы РК по парам «креатив × площадка» и обновляет их состояние.

    Строка на пару РЕКЛАМНОГО СООБЩЕНИЯ и площадки, а не на каждую отправку: доработка
    переставляет `pair_id` у существующей строки, и ЕРИД с хешом МС переживают правку
    (решение владельца 04.09.2026: «ерид на строку»).

    Строка появляется в момент ОТПРАВКИ пары, а не схождения: счётчик в интерфейсе
    показывает «всего / согласовано / запущено», и без несогласованных «всего» равнялось
    бы «согласовано» — то есть не значило бы ничего. Хеш в DSP при этом получают только
    сросшиеся пары, и его отсутствие как раз и отличает третье число от второго.

    Статус НЕ перетирается, если его уже поставил трафик: `effective_status` отдаёт
    предпочтение ручному — иначе запущенный креатив возвращался бы в «согласован» при
    каждом синке.
    """
    pls = {p.publisher_id: p for p in db.query(AdCampaignPlacement)
           .filter(AdCampaignPlacement.campaign_id == camp.id).all()}
    if not pls:
        return {"created": 0, "updated": 0}

    roots = root_set_map(db, camp.deal_id)
    pairs = db.execute(text("""
        SELECT pr.id AS pair_id, pr.code AS pair_code, pr.sent_at,
               cs.id AS set_id, cs.no AS set_no, cs.title, cs.erid,
               t.publisher_id,
               tr.verdict AS traffic_verdict,
               pv.verdict AS platform_verdict
          FROM launch_prep_pair pr
          JOIN launch_prep_creative_set cs ON cs.id = pr.set_id
          JOIN launch_prep_target t ON t.id = pr.target_id
          LEFT JOIN launch_prep_review tr ON tr.pair_id = pr.id AND tr.kind = 'трафики'
          LEFT JOIN launch_prep_review pv ON pv.pair_id = pr.id AND pv.kind = 'площадка'
         WHERE cs.deal_id = :d
         ORDER BY pr.id
    """), {"d": camp.deal_id}).mappings().all()

    have = {(c.placement_id, c.root_set_id): c for c in db.query(AdCampaignCreative)
            .filter(AdCampaignCreative.campaign_id == camp.id).all()}
    # Номера считаются в пределах ПЛОЩАДКИ и не переиспользуются: на них ссылается
    # сквозное имя в DSP, и сдвиг номера означал бы переименование креатива.
    next_no = {}
    for (pid, _), c in have.items():
        next_no[pid] = max(next_no.get(pid, 0), c.creative_no)

    created = updated = 0
    for r in pairs:
        pl = pls.get(r["publisher_id"])
        if pl is None:
            continue                      # площадки нет в этой РК — пара не наша
        root = roots.get(r["set_id"], r["set_id"])
        chain = chain_status(r["traffic_verdict"], r["platform_verdict"], has_pair=True)
        # Словари площадки и креатива различаются одним словом: у креатива согласованное
        # состояние зовётся «согласован», а не «ждёт запуска».
        chain = "согласован" if chain == PLACEMENT_READY else chain

        row = have.get((pl.id, root))
        if row is None:
            next_no[pl.id] = next_no.get(pl.id, 0) + 1
            row = AdCampaignCreative(
                campaign_id=camp.id, placement_id=pl.id, root_set_id=root,
                creative_no=next_no[pl.id], status=chain)
            db.add(row)
            have[(pl.id, root)] = row
            created += 1
        elif row.status != effective_status_creative(row.status, chain):
            row.status = effective_status_creative(row.status, chain)
            updated += 1
        # Ссылка всегда на ПОСЛЕДНЮЮ пару цепочки: запрос отсортирован по id.
        row.pair_id = r["pair_id"]
        # МАРКЕР переносим с комплекта, по которому пара согласована, а не с корня
        # цепочки: корень мог быть отвергнут и заменён, а маркер выдан на действующий.
        #
        # Колонка `erid` читалась в двух местах — экран трафика и выгрузка в DSP — и НЕ
        # ЗАПОЛНЯЛАСЬ НИКЕМ (замер 17.09.2026: 0 из 1 на проде). Это не косметика:
        # `dsp/provision` подставляет её в `wrap_html` и в тело креатива, то есть баннер
        # уезжал бы в сеть БЕЗ МАРКИРОВКИ.
        #
        # Пустым не затираем: маркер может прийти позже согласования, и «ещё нет» не
        # должно стирать уже перенесённое.
        if r["erid"]:
            row.erid = r["erid"]
        row.ms_title = creative_title(db, camp, pl, row.creative_no)

    # СТАТУС ПЛОЩАДКИ ПЕРЕСЧИТЫВАЕМ ЗДЕСЬ ЖЕ, из её креативов.
    #
    # Экран трафика считал его на лету (`best_chain_status` по креативам), а в колонке
    # `ad_campaign_placement.status` оставалось то, что записали при создании строки, —
    # «у трафика». Пока на колонку никто не смотрел, расхождение было невидимым. Но по
    # ней считают ДЕЙСТВИЯ: и заведение вставок Weborama, и выгрузка в DSP берут
    # «готовые» площадки именно оттуда.
    #
    # Отсюда 17.09.2026 и вышло: на экране площадка «ждёт запуска», а кнопка «ПИКСЕЛЬ WR»
    # честно отвечает «0 заведённых» — она смотрит в колонку, которую никто не обновлял.
    # Ручной статус не трогаем: `effective_status` пропускает решения человека вперёд.
    by_pl: dict = {}
    for (pid, _), c in have.items():
        by_pl.setdefault(pid, []).append(c.status)
    for pl in pls.values():
        mine = by_pl.get(pl.id)
        if not mine:
            continue
        chain = best_chain_status(as_placement_scale(x) for x in mine)
        nxt = effective_status(pl.status, chain)
        if nxt != pl.status:
            pl.status = nxt
            updated += 1

    db.flush()
    if commit:
        db.commit()
    return {"created": created, "updated": updated}


def creative_title(db: Session, camp: AdCampaign, pl: AdCampaignPlacement, no: int) -> str:
    """Сквозное имя креатива в МС: `<код сделки>-<код площадки>-cr<№>`.

    По НАШИМ кодам, а не по идентификаторам DSP — решение владельца: имя должно читаться
    в кабинете DSP теми же кодами, что у нас на экране.
    """
    row = db.execute(text("""
        SELECT d.code AS deal_code, pub.code AS pub_code
          FROM ad_campaign c
          JOIN sales_deals d ON d.id = c.deal_id
          JOIN sales_publishers pub ON pub.id = :pid
         WHERE c.id = :cid
    """), {"cid": camp.id, "pid": pl.publisher_id}).mappings().first()
    if not row:
        return f"cr{no}"
    return f"{row['deal_code'] or camp.deal_id}-{row['pub_code'] or pl.publisher_id}-cr{no}"


def sync_all(db: Session, commit: bool = True) -> dict:
    """Полный прогон: РК по сделкам + площадки-кандидаты. Идемпотентно."""
    res = sync_campaigns(db, commit=False)
    added = cands = no_w = cr_new = cr_upd = 0
    for camp in db.query(AdCampaign).all():
        r = sync_placements(db, camp, commit=False)
        added += r["added"]
        cands += r["candidates"]
        no_w += r["without_weight"]
        # Креативы — ПОСЛЕ площадок: строка креатива живёт под площадкой, и до её
        # появления привязывать пару не к чему.
        c = sync_creatives(db, camp, commit=False)
        cr_new += c["created"]
        cr_upd += c["updated"]
    if commit:
        db.commit()
    return {**res, "placements_added": added, "placement_candidates": cands,
            "placements_without_weight": no_w,
            "creatives_added": cr_new, "creatives_updated": cr_upd}


# ── «в размещении» пишет ЗАПУСК, а не человек ────────────────────────────────

# Состояние получателя после запуска. Оно же — единственное место, где эта строка
# ставится: до 18.09.2026 её ставили кнопкой на карточке сделки, и карточка говорила
# «в размещении» о площадке, у которой РК не собрана, площадка ждёт запуска, а срок ещё
# не наступил. Два источника правды об одном факте разошлись ровно так, как расходятся
# всегда: обе надписи выглядели правдой.
TARGET_PLACED = "в размещении"

# Ступени, после которых двигать уже некуда: назад состояние не ходит.
_TARGET_AFTER = ("в размещении", "завершён", "сверка завершена", "архив", "отказ площадки")


def mark_target_placed(db: Session, pl: AdCampaignPlacement, commit: bool = False) -> int:
    """Площадка РК запущена → её пара в сборе запуска переходит «в размещении».

    Связь по (сделка, площадка): у получателя нет ссылки на строку РК, и заводить её
    ради этого не нужно — пара уникальна и так.

    Возвращает число изменённых строк, чтобы вызывающий мог сказать это словами, а не
    «готово».
    """
    camp = db.query(AdCampaign).filter(AdCampaign.id == pl.campaign_id).first()
    if not camp:
        return 0
    rows = db.execute(text("""
        SELECT id, state FROM launch_prep_target
         WHERE deal_id = :d AND publisher_id = :p AND archived_at IS NULL
    """), {"d": camp.deal_id, "p": pl.publisher_id}).mappings().all()
    n = 0
    for r in rows:
        if (r["state"] or "") in _TARGET_AFTER:
            continue
        db.execute(text("UPDATE launch_prep_target SET state = :s WHERE id = :i"),
                   {"s": TARGET_PLACED, "i": r["id"]})
        n += 1
    if commit and n:
        db.commit()
    return n
