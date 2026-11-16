# -*- coding: utf-8 -*-
"""Приоритезация в сверке с площадкой (владелец 16.11.2026, путь 1): площадка приоритезации — площадка РК сделки, её показы
(источник `prio`) — строка сверки месяца «p<id>» рядом со строками РК «t<id>»; согласованный итог разносится и на неё
(`publisher_recon_prio_line`), разаллокация берёт её с договором ОРД сделки. Сделка стенда, всё в транзакции с откатом:
commit — flush, API приоритезации — подделка."""
from datetime import date

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.ad import build
from app.prio import launch as L
from app.publisher_recon import board as B
from app.publisher_recon import razaloc as RZ
from app.publisher_recon import service as S
from tests.test_prio import FakeApi, _approved, env  # noqa: F401 — фикстура стенда


class _U:
    name, email, id = "Менеджер тест", "m@test", None


@pytest.fixture
def launched(env, monkeypatch):  # noqa: F811
    db, d, _ = env
    monkeypatch.setattr(db, "commit", db.flush)
    # архивные площадки в РК не идут (правило «архивные не считаем») — берём действующую
    # и без других кампаний и сверки за ноябрь — иначе сверку месяца не отправить
    pub = db.execute(text("""
        SELECT p.id FROM sales_publishers p WHERE p.is_active AND p.status <> 'АРХИВ'
           AND NOT EXISTS (SELECT 1 FROM publisher_placement_v v WHERE v.publisher_id = p.id
                            AND to_char(v.date_from, 'YYYY-MM') = '2026-11')
           AND NOT EXISTS (SELECT 1 FROM publisher_request q WHERE q.publisher_id = p.id AND q.period = '2026-11')
         ORDER BY p.id LIMIT 1""")).scalar()
    if pub is None:
        pytest.skip("на стенде нет действующей площадки без ноябрьских кампаний")
    db.execute(text("UPDATE sales_publishers SET prio_site_id = 7000 + id WHERE id = :p"), {"p": pub})
    p = _approved(db, d, pub)
    L.launch(db, d, p.id, client=FakeApi())
    camp = db.execute(text("SELECT id FROM ad_campaign WHERE deal_id = :d ORDER BY id DESC LIMIT 1"), {"d": d.id}).scalar()
    if camp is None:
        pytest.skip("у сделки стенда РК не завелась (стадия вне сборки)")
    return db, d, p, camp


def test_prio_publisher_is_a_campaign_publisher(launched):
    """Уронит: `deal_publishers` снова только из сборки баннеров — показы площадки лягут «на РК целиком»."""
    db, d, p, camp = launched
    assert p.publisher_id in build.deal_publishers(db, d.id)
    assert db.execute(text("SELECT 1 FROM ad_campaign_placement WHERE campaign_id = :c AND publisher_id = :p"),
                      {"c": camp, "p": p.publisher_id}).scalar(), "строка площадки в РК заводится при запуске"


def test_prio_shows_reach_the_month_recon_and_are_agreed(launched):
    """Показы источника prio по строке площадки → строка сверки «p<id>»; итог разносится и на неё; разаллокация её видит.
    Уронит: сверка снова читает только размещения сборки (строки нет) или итог не пишет строку приоритезации."""
    db, d, p, camp = launched
    pl = db.execute(text("SELECT id FROM ad_campaign_placement WHERE campaign_id = :c AND publisher_id = :p"),
                    {"c": camp, "p": p.publisher_id}).scalar()
    # сверки ведутся с октября 2026 (`board.START`) — период запроса в тесте ноябрьский
    db.execute(text("UPDATE prio_requests SET date_start = '2026-11-01', date_end = '2026-11-30' WHERE id = :r"),
               {"r": p.request_id})
    r = date(2026, 11, 1)
    period = r.strftime("%Y-%m")
    db.execute(text("""INSERT INTO ad_campaign_stat (campaign_id, placement_id, date, shows, clicks, source, imported_at)
                       VALUES (:c, :p, :d, 12345, 10, 'prio', now())"""), {"c": camp, "p": pl, "d": r})
    key = f"p{p.id}"
    facts = B.target_facts(db, p.publisher_id, period)
    assert facts.get(key) == 12345, f"строки приоритезации нет в сверке месяца: {facts}"
    # сверка — когда кампании месяца окончены: площадка выполнила план и остановлена
    db.execute(text("UPDATE prio_placements SET status = 'остановлено', goal_reached_at = now() WHERE id = :p"), {"p": p.id})
    others = [x for x in B._placements(db, period, p.publisher_id) if x["key"] != key and x["status"] not in (B.DONE_STATUS, B.REFUSED)]
    if others:
        pytest.skip("у площадки стенда в этом месяце идут другие кампании — сверку не отправить")
    req = S.send(db, p.publisher_id, period, _U(), date.today())
    total = sum(facts.values()) + 100
    S.agree(db, req, _U(), total, mode="target", target_id=key)
    got = db.execute(text("SELECT our_volume, agreed_volume FROM publisher_recon_prio_line WHERE request_id = :r "
                          "AND prio_placement_id = :p"), {"r": req.id, "p": p.id}).first()
    assert tuple(got) == (12345, 12445), "вся дельта — на выбранную строку приоритезации"
    assert any(x["deal_code"] == d.code and x["agreed_volume"] == 12445 for x in RZ.lines_of(db, req.id))
    row = next(x for x in B.month_rows(db, period) if x["publisher_id"] == p.publisher_id)
    assert row["agreed"] == total and not row["changed"], "состав строк после итога тот же — без пометки «изменилось»"


def test_old_numeric_target_still_means_campaign_line():
    """Экран до 16.11.2026 слал номер размещения числом — это строка РК."""
    assert S.line_key(17) == "t17" and S.line_key("p3") == "p3" and S.line_key(None) is None
    assert S.distribute(10, {"t1": 4, "p2": 4}, "target", 1) == {"t1": 6, "p2": 4}
