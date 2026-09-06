"""Демо-наполнение дашборда трафика: месяц открутки на 10 РК.

Зачем: до подключения коннектора (этап 2c) факта нет ни у одной РК, и экран честно
показывает прочерки. Проверить на нём стену дней, виновников, прогноз, недокрут и
раскладку по креативам не на чем — а посмотреть, как это выглядит с данными, надо
до выкладки, а не после.

ЗАПУСК (только на локальном стенде):
    docker exec finance_backend python -m scripts.2026-09-04_demo_traffic_month
    docker exec finance_backend python -m scripts.2026-09-04_demo_traffic_month --undo

ОБРАТИМО ПОЛНОСТЬЮ, и это главное требование к скрипту: локальная база — копия боевой,
и демо-цифры, которые нельзя отличить от настоящих, однажды будут приняты за настоящие.
Поэтому:

  · факт пишется с `source = 'demo'`, а не 'ms'. Уникальность `ad_campaign_stat` включает
    источник, так что демо-строки не столкнутся с будущими настоящими и убираются одним
    DELETE по источнику;
  · комплекты креативов заводятся с номерами от DEMO_SET_NO — по ним же и удаляются;
  · даты и план РК откат восстанавливает ПЕРЕСИНКОМ из медиапланов (`sync_campaigns`),
    веса площадок — из балансировщика (`publisher_weights`), то есть из тех же
    источников, что и обычно. Ничего не запоминаем «на всякий случай»: восстановление
    из первоисточника надёжнее сохранённой копии.

КАЛЕНДАРЬ. Сегодня 04.09.2026, и месячный флайт от 1 сентября дал бы четыре отчитанных
дня — на такой картинке не видно ни стены дней, ни просадок. Поэтому основной флайт
начинается 24 августа: сегодня — 12-й день из 30, ровно та точка, на которой рисовался
макет. Даты настоящие, подкручен только выбор окна.
"""
import argparse
import math
import random
from datetime import date, timedelta

from sqlalchemy import text

from app.ad import build
from app.ad.models import AdCampaign, AdCampaignCreative, AdCampaignPlacement
from app.database import SessionLocal
from app.launch_prep.models import LaunchPrepCreativeSet

DEMO_SOURCE = "demo"
# Номера комплектов от этого значения — демонстрационные.
#
# Диапазон ВЫШЕ 9000 занят приборами: четыре файла тестов заводят свои комплекты с
# `NO_BASE` 9000 / 9500 / 9700 и убирают за собой запросом `no >= NO_BASE`, то есть
# сносят ВСЁ, что лежит выше их отметки. Демо, поселившееся там, ломало прогон: уборка
# упиралась во внешний ключ `ad_campaign_creative.root_set_id`.
#
# Поэтому демо живёт НИЖЕ приборов: 8000 выше любых рабочих номеров (у живых сделок они
# однозначные) и ниже 9000. Занимать 9000+ нельзя — это территория тестов.
DEMO_SET_NO = 8000
TODAY = date(2026, 9, 4)

# Профиль каждой РК: (сдвиг старта от 24.08, длина флайта, статус, доля выполнения плана,
# «щербатая» ли раскладка — есть ли площадка без индекса и выключенная).
# Набор подобран так, чтобы на экране встретились ВСЕ состояния, ради которых он и сделан:
# опережение, ровный темп, просадка, провал, ещё не стартовала, флайт уже закончился.
# Щербатую раскладку оставляем ТОЛЬКО у двух РК. Если сделать её везде, часть объёма
# нигде не распределена, и недокрут появляется у всех подряд — экран становится ровно
# красным, а на ровном экране не видно, кто действительно проваливается.
PROFILES = [
    (0,  30, "запущена",       1.06, False),   # идёт с опережением
    (0,  30, "запущена",       0.98, False),   # ровно по темпу
    (0,  30, "запущена",       0.87, False),   # лёгкая просадка
    (0,  30, "запущена",       0.62, True),    # недокрут + дыры в раскладке
    (2,  28, "запущена",       0.41, True),    # провал — попадёт в «виновников»
    (5,  26, "пауза",          0.78, False),   # на паузе, темп подсел
    (0,  12, "окончена",       0.94, False),   # флайт закончился 04.09
    (12, 30, "готова",         0.0,  False),   # стартует 05.09 — фактов ещё нет
    (23, 30, "ожидает сборки", 0.0,  False),   # старт 16.09, отчитанных дней ноль
    (0,  30, "остановлена",    0.55, False),   # остановлена на середине
]

BASE_START = date(2026, 8, 24)


def _weights(seed: int) -> float:
    """Псевдослучайный, но ВОСПРОИЗВОДИМЫЙ вес площадки: повторный прогон даёт то же."""
    rnd = random.Random(seed)
    return float(rnd.choice([1_740_000, 1_520_000, 1_120_000, 980_000, 860_000,
                             640_000, 520_000, 480_000, 380_000, 180_000]))


def _day_factor(d: date, rnd: random.Random) -> float:
    """Дневная неровность: выходные проседают, плюс небольшая волна.

    Ровная линия факта выглядит нарисованной — и она нарисованная. Смысл демо в том,
    чтобы на стене дней были видны ПАТТЕРНЫ: провалы по выходным, начало просадки.
    """
    weekend = 0.82 if d.weekday() >= 5 else 1.0
    return weekend * (1 + math.sin(d.toordinal() * 1.1) * 0.18) * rnd.uniform(0.93, 1.07)


def seed(db):
    camps = (db.query(AdCampaign)
             .filter(AdCampaign.plan_show.isnot(None), AdCampaign.date_start.isnot(None))
             .order_by(AdCampaign.id).all())
    camps = [c for c in camps
             if db.query(AdCampaignPlacement).filter_by(campaign_id=c.id).count() >= 4]
    camps = camps[:len(PROFILES)]
    if not camps:
        print("нет подходящих РК: нужны план, даты и хотя бы четыре площадки")
        return

    made_stats = made_creatives = 0
    for camp, (shift, length, status, done_ratio, ragged) in zip(camps, PROFILES):
        rnd = random.Random(camp.id)
        camp.date_start = BASE_START + timedelta(days=shift)
        camp.date_end = camp.date_start + timedelta(days=length - 1)
        camp.month = camp.date_start.replace(day=1)
        camp.status = status

        pls = (db.query(AdCampaignPlacement).filter_by(campaign_id=camp.id)
               .order_by(AdCampaignPlacement.id).all())
        # У «щербатых» РК одна площадка без индекса и одна выключена: состояния «нет
        # индекса» и «объём ушёл остальным» должны быть видны на экране, а не только
        # в тестах. У остальных раскладка полная.
        last = len(pls) - 1
        for i, p in enumerate(pls):
            if p.weight is None and not (ragged and i == last):
                p.weight = _weights(p.publisher_id)
            if status in ("запущена", "пауза", "окончена", "остановлена"):
                p.status = ("завершена" if ragged and i == 0 and len(pls) > 3
                            else "пауза" if ragged and i == 1 and len(pls) > 4
                            else "запущен")
            else:
                p.status = "ждёт запуска" if i % 2 else "у площадки"
        db.flush()
        build.recompute_shares(db, camp.id)
        db.flush()

        # Креативы: одно-три сообщения на площадку. Часть уже в кабинете МС (есть хеш),
        # часть только согласована — ради того самого счётчика «всего/согласовано/запущено».
        for p in pls:
            n = rnd.choice([1, 2, 2, 3])
            for k in range(n):
                st = db.query(LaunchPrepCreativeSet).filter_by(
                    deal_id=camp.deal_id, no=DEMO_SET_NO + k).first()
                if st is None:
                    st = LaunchPrepCreativeSet(
                        deal_id=camp.deal_id, no=DEMO_SET_NO + k,
                        title=rnd.choice(["Баннер 300×250", "Баннер 728×90",
                                          "Нативный блок", "Мобильный 320×50"]))
                    db.add(st)
                    db.flush()
                exists = db.query(AdCampaignCreative).filter_by(
                    placement_id=p.id, root_set_id=st.id).first()
                if exists:
                    continue
                # На части площадок крутятся ДВА креатива: иначе деление «поровну между
                # работающими» на экране не увидеть — у одного креатива доля всегда 100 %.
                runs = 2 if (p.id % 3 == 0 and n >= 2) else 1
                live = p.status == "запущен" and k < runs
                # «Ждёт запуска» тоже согласована: без согласованного креатива РК не
                # считается «готовой», и демо-состояние «готова» на экране не появилось бы.
                agreed = p.status in ("запущен", "пауза", "завершена", "ждёт запуска")
                db.add(AdCampaignCreative(
                    campaign_id=camp.id, placement_id=p.id, root_set_id=st.id,
                    creative_no=k + 1,
                    ms_title=build.creative_title(db, camp, p, k + 1),
                    status="запущен" if live else "согласован" if agreed else "у площадки",
                    ms_creative_xxhash=(f"{rnd.getrandbits(64):016X}" if live else None),
                    erid=(f"2Vtzq{rnd.getrandbits(28):07X}" if agreed else None)))
                made_creatives += 1
        db.flush()

        # Суточный факт по КАЖДОЙ площадке: экран считает недокрут в разрезе площадок,
        # и общий факт по РК без разреза оставил бы виджет виновников пустым.
        fl_len = length
        elapsed = max(0, min((TODAY - camp.date_start).days + 1, fl_len))
        if not elapsed or not done_ratio:
            continue
        for p in pls:
            if not p.share:
                continue
            per_day = (camp.plan_show * p.share) / fl_len
            for i in range(elapsed):
                d = camp.date_start + timedelta(days=i)
                shows = int(per_day * done_ratio * _day_factor(d, rnd))
                if shows <= 0:
                    continue
                clicks = int(shows * rnd.uniform(0.004, 0.007))
                db.add_all([])
                db.execute(text(
                    "INSERT INTO ad_campaign_stat "
                    "(campaign_id, placement_id, date, shows, clicks, source) "
                    "VALUES (:c, :p, :d, :s, :k, :src) ON CONFLICT DO NOTHING"),
                    {"c": camp.id, "p": p.id, "d": d, "s": shows, "k": clicks,
                     "src": DEMO_SOURCE})
                made_stats += 1
        db.flush()

    db.commit()
    print(f"РК наполнено: {len(camps)}")
    print(f"креативов заведено: {made_creatives}")
    print(f"строк суточного среза: {made_stats}")
    print("источник факта: 'demo' — откат убирает их одним запросом")


def undo(db):
    stats = db.execute(text("DELETE FROM ad_campaign_stat WHERE source = :s"),
                       {"s": DEMO_SOURCE}).rowcount
    crs = db.execute(text(
        "DELETE FROM ad_campaign_creative WHERE root_set_id IN "
        "(SELECT id FROM launch_prep_creative_set WHERE no >= :n)"),
        {"n": DEMO_SET_NO}).rowcount
    sets = db.execute(text("DELETE FROM launch_prep_creative_set WHERE no >= :n"),
                      {"n": DEMO_SET_NO}).rowcount
    # Статусы площадок — обратно в исходное «у трафика»: конвейер согласования на стенде
    # пуст, и именно это состояние он и даёт.
    pl = db.execute(text("UPDATE ad_campaign_placement SET status = 'у трафика' "
                         "WHERE status <> 'у трафика'")).rowcount
    db.commit()

    # Веса и даты восстанавливаем ИЗ ПЕРВОИСТОЧНИКА, а не из сохранённой копии.
    build.sync_campaigns(db, commit=False)
    for camp in db.query(AdCampaign).all():
        plan = build.deal_plan(db, camp.deal_id)
        w = build.publisher_weights(db, plan["surfaces"])
        for p in db.query(AdCampaignPlacement).filter_by(campaign_id=camp.id).all():
            p.weight = w.get(p.publisher_id)
        build.recompute_shares(db, camp.id)
    db.commit()
    print(f"убрано: срез {stats}, креативов {crs}, комплектов {sets}, "
          f"статусов площадок сброшено {pl}")
    print("даты, планы и веса восстановлены пересинком из медиапланов и балансировщика")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--undo", action="store_true", help="убрать демо-данные")
    args = ap.parse_args()
    db = SessionLocal()
    try:
        undo(db) if args.undo else seed(db)
    finally:
        db.close()
