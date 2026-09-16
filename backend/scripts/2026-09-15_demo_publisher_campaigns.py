# -*- coding: utf-8 -*-
"""Демо-размещения в кабинете площадки — ТОЛЬКО ДЛЯ СТЕНДА.

    docker exec finance_backend python -m scripts.2026-09-15_demo_publisher_campaigns
    docker exec finance_backend python -m scripts.2026-09-15_demo_publisher_campaigns --undo

Зачем. Блок «Актуальные кампании» собран из настоящих данных, но на стенде у Максавита их
четыре строки и три состояния из шести: посмотреть, как блок выглядит живым, не на чем.
Скрипт добавляет одиннадцать размещений по составу макета — все шесть состояний, разные
периоды, часть с ЕРИД, часть без факта.

## Почему это скрипт, а не руками в psql

Потому что его надо будет СНЯТЬ. Демо-данные, залитые вручную, отличаются от настоящих
только в памяти того, кто их лил, — и живут годами. Здесь у них есть метка и есть `--undo`.

## Метка и почему она невидима площадке

Сделки заводятся с `bitrix_id` из зарезервированного диапазона 8_800_000+, а строки факта
— с `source = 'demo'` (тот же приём, что у демо-витрины трафика). В кабинете площадка
видит «Рекламодатель · Бренд» и не видит ни `bitrix_id`, ни источника — то есть метка
не мозолит глаза тому, для кого блок рисуется, и при этом однозначна для нас.

Рекламодатели, бренды и услуги берутся НАСТОЯЩИЕ из наших справочников: выдуманные имена
в списке сразу выдают демо, а задача — посмотреть, как блок выглядит с живыми данными.

## На проде не запускается, и проверка закрывается при сомнении

Пропускается только явное `DOMAIN=localhost`. Пустое значение — это НЕ стенд, а
«неизвестно где», и скрипт отказывается: он заводит поддельные сделки, а не убирает свои
строки. Разбор в `_stand_only`.

## Перед выкладкой — снять

`--undo` убирает всё заведённое: сделки диапазона, их пары, комплекты, вердикты, кампании,
размещения и строки факта. Шаг записан в `docs/ВЫКЛАДКА_*`, чтобы демо не дожило до
релиза незамеченным.
"""
import os
import sys
from datetime import date, timedelta

from sqlalchemy import text

from app.database import SessionLocal

PUB_ID = 6                    # Maksavit.ru
BX_BASE = 8_800_000           # зарезервированный диапазон демо-сделок
DEMO_SOURCE = 'demo'

# (рекламодатель, бренд, услуга, поверхность, старт, финиш, план, факт, состояние)
# Состояние задаётся ЯВНО, а не подбирается датами: витрина выводит его из статуса
# кампании, стадии пары и вердикта, и подгонять всё это датами значило бы проверять
# случайность вместо состава.
# Пары «рекламодатель · бренд» взяты из НАШИХ справочников и встречаются в живых сделках.
# Первая редакция списка копировала имена из макета, и трёх из них у нас не оказалось
# («AB-BIOTICS», «Но-шпа», «Кросс-сеть») — витрина честно нарисовала «— · Бифистим» и
# «Sanofi» без бренда. Заводить недостающие имена в справочник ради демо нельзя: это уже
# не демо, а мусор в общих данных, который переживёт `--undo`.
ROWS = [
    ('Woerwag',      'Мильгамма',   'еФарм',          'web', (0, 15), (0, 45), 620000,      0, 'ждёт согласования'),
    ('Abbott',       'Дюспаталин',  'еФарм',          'app', (0, 20), (0, 46), 410000,      0, 'ждёт согласования'),
    ('BINNO',        'Венапрокт',   'Альфарм-Таргет', 'web', (0, 77), (0, 107), 260000,     0, 'ждёт старта'),
    ('Alfasigma',    'Альфазокс',   'еФарм',          'web', (-10, 0), (0, 15), 540000, 318400, 'в размещении'),
    ('Zambon',       'Метеоспазмил', 'Альфарм-Таргет', 'web', (-3, 0), (0, 15), 300000,  96200, 'в размещении'),
    ('Ферон',        'Виферон',     'еФарм',          'app', (-14, 0), (0, 10), 360000, 214800, 'в размещении'),
    ('Dr. Reddy’s',  'Найз',        'Приоритезация',  'web', (-7, 0), (0, 15), 180000,  41300, 'пауза'),
    ('Bausch',       'Антигриппин', 'Альфарм-Таргет', 'web', (-14, 0), (0, 15), 200000,     0, 'отказ'),
    ('Sanofi',       'Маалокс',     'еФарм',          'web', (-45, 0), (-15, 0), 720000, 706400, 'завершён'),
    ('BINNO',        'Кагоцел',     'Альфарм-Таргет', 'web', (-45, 0), (-15, 0), 480000, 492100, 'завершён'),
    ('Ферон',        'Виферон',     'еФарм',          'app', (-45, 0), (-20, 0), 360000, 351800, 'завершён'),
]


# Статус кампании, дающий нужное состояние витрины. «ждёт согласования» и «ждёт старта»
# различаются стадией ПАРЫ, а не кампании, поэтому у них статус один.
CAMP_STATUS = {
    'ждёт согласования': 'ожидает сборки', 'ждёт старта': 'готова',
    'в размещении': 'запущена', 'пауза': 'пауза',
    'завершён': 'окончена', 'отказ': 'ожидает сборки',
}


def _stand_only() -> bool:
    """Разрешено ТОЛЬКО на стенде, и проверка ЗАКРЫВАЕТСЯ при сомнении.

    Здесь намеренно строже, чем у уборки журналов в `tests/conftest.py`: та сравнивает
    домен со списком `("", "localhost")`, то есть пустое значение считает стендом. Для
    уборки это допустимо — она удаляет свои же строки. Здесь наоборот: скрипт ЗАВОДИТ
    поддельные сделки, и «домен не задан» означает не «стенд», а «неизвестно где».

    Разница не теоретическая. В этом проекте трижды случалось, что значение есть в `.env`,
    а до процесса не доходит — переменную забыли пробросить в `docker-compose.yml`
    (готча `env-not-reaching-container`, прибор `tests/test_env_passthrough`). Пустой
    `DOMAIN` на боевом сервере выглядел бы для мягкой проверки как стенд, и демо-сделки
    уехали бы в кабинет настоящей площадки.

    Поэтому пропускается только ЯВНОЕ `localhost`.
    """
    return (os.getenv("DOMAIN") or "").strip() == "localhost"


def _day(pair):
    a, b = pair
    return date.today() + timedelta(days=a + b)


def undo(db) -> None:
    # УДАЛЕНИЕ АДРЕСУЕТСЯ ТОЧНО, а не шаблоном. Первая редакция брала `LIKE '88000%'`, и
    # это ошибка того сорта, которая не проявляется, пока не станет дорогой: `bitrix_id` —
    # СТРОКА, и на стенде уже лежит настоящая сделка с номером `888`. Сегодня она под
    # шаблон не попадает, а сделка `880001234` попала бы — и `--undo` снёс бы чужие данные
    # вместе со своими.
    #
    # Поэтому список идентификаторов строится ровно из того, что скрипт заводит, и к нему
    # добавлено второе условие — метка в названии. Два признака вместо одного: удаление
    # должно быть уже, чем создание, а не шире.
    keys = [str(BX_BASE + n) for n in range(len(ROWS))]
    ids = [i for (i,) in db.execute(text(
        "SELECT id FROM sales_deals "
        " WHERE bitrix_id = ANY(:b) AND title LIKE :m"),
        {"b": keys, "m": "[демо]%"})]
    if not ids:
        print("демо-размещений нет")
        return
    # Порядок ручной: каскады есть не везде, а полагаться на них при удалении —
    # значит однажды оставить сирот, которых потом никто не свяжет с этим скриптом.
    db.execute(text("DELETE FROM ad_campaign_stat WHERE campaign_id IN "
                    "(SELECT id FROM ad_campaign WHERE deal_id = ANY(:i))"), {"i": ids})
    db.execute(text("DELETE FROM ad_campaign_placement WHERE campaign_id IN "
                    "(SELECT id FROM ad_campaign WHERE deal_id = ANY(:i))"), {"i": ids})
    db.execute(text("DELETE FROM ad_campaign WHERE deal_id = ANY(:i)"), {"i": ids})
    db.execute(text("DELETE FROM launch_prep_review WHERE pair_id IN (SELECT p.id "
                    "FROM launch_prep_pair p JOIN launch_prep_target t ON t.id = p.target_id "
                    "WHERE t.deal_id = ANY(:i))"), {"i": ids})
    db.execute(text("DELETE FROM launch_prep_pair WHERE target_id IN "
                    "(SELECT id FROM launch_prep_target WHERE deal_id = ANY(:i))"), {"i": ids})
    db.execute(text("DELETE FROM launch_prep_creative_set WHERE deal_id = ANY(:i)"), {"i": ids})
    db.execute(text("DELETE FROM launch_prep_target WHERE deal_id = ANY(:i)"), {"i": ids})
    db.execute(text("DELETE FROM sales_deals WHERE id = ANY(:i)"), {"i": ids})
    db.commit()
    print(f"снято демо-сделок: {len(ids)}")


def seed(db) -> None:
    made = 0
    for n, (adv, brand, service, surface, d1, d2, plan, fact, state) in enumerate(ROWS):
        bx = BX_BASE + n
        if db.execute(text("SELECT 1 FROM sales_deals WHERE bitrix_id = :b"),
                      {"b": str(bx)}).scalar():
            continue                     # повторный прогон не плодит дублей

        adv_id = db.execute(text(
            "SELECT id FROM sales_advertisers WHERE short_name = :n OR name = :n LIMIT 1"),
            {"n": adv}).scalar()
        brand_id = db.execute(text(
            "SELECT id FROM sales_brands WHERE name = :n LIMIT 1"), {"n": brand}).scalar()
        svc_id = db.execute(text(
            "SELECT id FROM sales_services WHERE name = :n LIMIT 1"), {"n": service}).scalar()
        if not svc_id:
            print(f"  пропуск «{brand}»: нет услуги «{service}»")
            continue
        # Имени нет в справочнике — говорим вслух. Молчаливый пропуск даёт строку вида
        # «— · Бифистим», и это выглядит дефектом витрины, а не пробелом демо-списка.
        if not adv_id or not brand_id:
            print(f"  ВНИМАНИЕ «{adv} · {brand}»: "
                  f"{'нет рекламодателя' if not adv_id else ''}"
                  f"{' и ' if not adv_id and not brand_id else ''}"
                  f"{'нет бренда' if not brand_id else ''} — строка будет неполной")

        start, end = _day(d1), _day(d2)
        # КОД СДЕЛКИ ОБЯЗАТЕЛЕН: по нему её резолвят экраны и ссылки (`_deal_by_ref`), и
        # сделка без кода отвечает 404 там, где реальная открывается. Первая редакция его
        # не ставила — падение поймали приборы карточки РК, а не глаза.
        from app.sales.deal_code import gen_code
        code = gen_code()
        while db.execute(text("SELECT 1 FROM sales_deals WHERE code = :c"),
                         {"c": code}).scalar():
            code = gen_code()

        deal_id = db.execute(text("""
            INSERT INTO sales_deals (bitrix_id, code, title, product, advertiser_id,
                                     brand_id, period_from, period_to, currency, synced_at)
            VALUES (:bx, :c, :t, :p, :a, :b, :f, :o, 'RUB', now()) RETURNING id"""),
            {"bx": str(bx), "c": code, "t": f"[демо] {adv} · {brand}", "p": service,
             "a": adv_id, "b": brand_id,
             # Период сделки — ПЕРВОЕ ЧИСЛО МЕСЯЦА старта: у нас это финансовый период,
             # а не дата (правило владельца 15.09.2026).
             "f": start.replace(day=1), "o": end}).scalar()

        db.execute(text("""
            INSERT INTO launch_prep_target (deal_id, publisher_id, service_id, surface_kind,
                                            state, period_from, period_to)
            VALUES (:d, :p, :s, :k, :st, :f, :o)"""),
            {"d": deal_id, "p": PUB_ID, "s": svc_id, "k": surface,
             "st": 'согласование' if state == 'ждёт согласования' else 'согласован',
             "f": start, "o": end})
        target_id = db.execute(text(
            "SELECT id FROM launch_prep_target WHERE deal_id = :d"), {"d": deal_id}).scalar()

        # Комплект креативов: он же носитель ЕРИД. Без факта показов номер не выпускаем —
        # в жизни он появляется к старту, и «ЕРИД есть, показов нет» выглядело бы странно.
        db.execute(text("""
            INSERT INTO launch_prep_creative_set (deal_id, publisher_id, no, origin, erid)
            VALUES (:d, :p, 1, 'первичный', :e)"""),
            {"d": deal_id, "p": PUB_ID,
             "e": f"Kra{200 + n}{'abcdefghijk'[n]}Qm" if fact else None})

        if state == 'отказ':
            set_id = db.execute(text(
                "SELECT id FROM launch_prep_creative_set WHERE deal_id = :d"),
                {"d": deal_id}).scalar()
            db.execute(text("INSERT INTO launch_prep_pair (code, set_id, target_id, sent_at) "
                            "VALUES (:c, :s, :t, now())"),
                       {"c": f"DEMO{bx}", "s": set_id, "t": target_id})
            pair_id = db.execute(text(
                "SELECT id FROM launch_prep_pair WHERE target_id = :t"),
                {"t": target_id}).scalar()
            # `set_id` у вердикта обязателен: отзыв относится к КОМПЛЕКТУ, а не только к
            # паре — комплектов у пары может быть несколько (доработка, замена).
            # `kind = 'площадка'` — вердикт САМОЙ ПЛОЩАДКИ, а не нашей проверки трафика
            # и не первичной ТТ: витрина считает отказом только его.
            #
            # `source = 'кабинет'` — значение ИЗ СЛОВАРЯ. Первая редакция ставила «демо», и
            # прибор словарей это поймал: сравнение в коде буквальное, и такая строка молча
            # выпала бы из всех выборок. Демо-данные обязаны быть ВАЛИДНЫМИ данными.
            #
            # Вердикт трафика ставится ВМЕСТЕ с вердиктом площадки: инвариант порядка —
            # «у пары с вердиктом площадки всегда есть вердикт трафика», на нём стоит право
            # не перепроверять трафик в расчёте порога ЕРИД. Прибор ловит это по всей базе,
            # а не по своим строкам, поэтому демо его тоже обязано соблюдать.
            db.execute(text("INSERT INTO launch_prep_review "
                            "  (pair_id, set_id, kind, verdict, reason, source) "
                            "VALUES (:p, :s, 'площадка', 'отказ', "
                            "        'демо: площадка отказала', 'кабинет')"),
                       {"p": pair_id, "s": set_id})
            db.execute(text("INSERT INTO launch_prep_review "
                            "  (pair_id, set_id, kind, verdict, reason, source) "
                            "VALUES (:p, :s, 'трафики', 'ок', "
                            "        'демо: трафик проверен', 'трафики')"),
                       {"p": pair_id, "s": set_id})

        db.execute(text("""
            INSERT INTO ad_campaign (deal_id, month, status, date_start, date_end, plan_show)
            VALUES (:d, :m, :s, :f, :o, :pl)"""),
            {"d": deal_id, "m": start.replace(day=1), "s": CAMP_STATUS[state],
             "f": start, "o": end, "pl": plan})
        camp_id = db.execute(text("SELECT id FROM ad_campaign WHERE deal_id = :d"),
                             {"d": deal_id}).scalar()
        db.execute(text("""
            INSERT INTO ad_campaign_placement (campaign_id, publisher_id, plan_show, status)
            VALUES (:c, :p, :pl, 'вкл')"""),
            {"c": camp_id, "p": PUB_ID, "pl": plan})
        place_id = db.execute(text(
            "SELECT id FROM ad_campaign_placement WHERE campaign_id = :c"),
            {"c": camp_id}).scalar()

        if fact:
            # Факт размазывается по дням флайта, а не кладётся одной строкой: витрина
            # суммирует по дням, и один «мешок» проверял бы не тот путь.
            days = max(1, (min(end, date.today()) - start).days)
            per = fact // days
            for i in range(days):
                db.execute(text("""
                    INSERT INTO ad_campaign_stat (campaign_id, placement_id, date, shows,
                                                  clicks, source)
                    VALUES (:c, :pl, :d, :s, 0, :src)"""),
                    {"c": camp_id, "pl": place_id, "d": start + timedelta(days=i),
                     "s": per + (fact - per * days if i == days - 1 else 0),
                     "src": DEMO_SOURCE})
        made += 1
    db.commit()
    print(f"заведено демо-размещений: {made}")


def main() -> None:
    if not _stand_only():
        print("ОТКАЗ: скрипт только для стенда (DOMAIN=localhost). "
              f"Сейчас DOMAIN={os.getenv('DOMAIN')!r}. "
              "На проде демо-сделки — это чужие деньги в чужом кабинете.")
        return
    db = SessionLocal()
    try:
        if "--undo" in sys.argv:
            undo(db)
            return
        seed(db)
        ids = [str(i) for (i,) in db.execute(text("SELECT id FROM sales_publishers"))]
        db.execute(text("SELECT set_config('app.publisher_ids', :v, true)"),
                   {"v": ",".join(ids)})
        for st, n in db.execute(text(
                "SELECT status, count(*) FROM pub.campaign_v1 WHERE publisher_id = :p "
                " GROUP BY 1 ORDER BY 2 DESC"), {"p": PUB_ID}):
            print(f"  {st}: {n}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
