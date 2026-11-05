# -*- coding: utf-8 -*-
"""Отчёт Weborama по ссылке — РК с ВНЕШНИМ пикселем (владелец 05.11.2026).

Пиксель ставил не наш аккаунт, API к нему у нас нет; клиент делится «постоянной ссылкой» на отчёт. Ссылка открывает
гостевой просмотр, и тот же интерфейс отдаёт суточные показы по фильтру ссылки (кампания × площадка) за любые даты.
Что ловят тесты:
  · принимаем только ссылку их отчётного центра — иначе поле стало бы дверью для запросов куда угодно с нашего сервера;
  · фильтр берётся из переадресации ссылки — именно им с нами поделились, свой не подставляем;
  · суточные строки ложатся одной строкой на день (перезабор не удваивает) и как ИЗМЕРИТЕЛЬ — в факт не идут;
  · есть данные по ссылке — ручной итог (`weborama_manual`) в сверку не идёт: это то же число из того же отчёта.
Проход по базе — в транзакции с откатом: на стенде ничего не остаётся.
"""
from datetime import date

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.ad import stat_sources as SS
from app.database import SessionLocal
from app.weborama import permalink as P

LINK = "https://adap-interface.wbrm.ru/9796/reportcenter/permalink/link/hash/9bdjz9X5J9AuXtPeletQh0b9"
LOCATION = ("/9796/reportcenter/reporting/index/guest/1/#/dashboard/dimensions/campaign,site_offer/sub_dimension/"
            "display_insertion/dimension_filters/campaign==121,site_offer==1161/campaign_channel/display/metrics/"
            "impression/table/table/time_unit/day/start_date/2026-10-06/end_date/2026-10-16")


def test_only_their_report_center_permalink_is_accepted():
    assert P.check_url(f"  {LINK}  ") == LINK
    for bad in ("http://adap-interface.wbrm.ru/9796/reportcenter/permalink/link/hash/abc",
                "https://evil.example/9796/reportcenter/permalink/link/hash/abc",
                "https://adap-interface.wbrm.ru.evil.example/9796/reportcenter/permalink/link/hash/abc",
                "https://adap-interface.wbrm.ru/9796/reportcenter/reporting/table",
                "javascript:alert(1)", ""):
        with pytest.raises(P.LinkError):
            P.check_url(bad)


def test_filter_is_taken_from_the_link_redirect():
    assert P.filters_from_location(LOCATION) == "campaign==121,site_offer==1161"
    # разрезы — ровно те, что у ссылки (+ день): иначе их сервер отвечает «Unauthorized parameters» (проверено 05.11.2026)
    assert P.dimensions_from_location(LOCATION) == "campaign,site_offer,display_insertion,day"
    with pytest.raises(P.LinkError):
        P.filters_from_location("/9796/reportcenter/reporting/index/guest/1/")


def test_daily_shows_are_parsed_and_zero_days_kept():
    payload = {"items": [{"day": "2026-10-18", "insertion": 0}, {"day": "2026-10-19", "insertion": 157692},
                         {"day": "2026-10-20", "insertion": "125193"}], "labels": ["All Insertions"]}
    assert P.parse_days(payload) == {date(2026, 10, 18): 0, date(2026, 10, 19): 157692, date(2026, 10, 20): 125193}


def test_source_is_a_verifier_never_fact():
    assert P.SOURCE in SS.VERIFIER and P.SOURCE not in SS.fact_sources()
    assert len(P.SOURCE) <= 16                     # ad_campaign_stat.source — varchar(16)


@pytest.fixture
def db_campaign():
    db = SessionLocal()
    cid = db.execute(text("SELECT id FROM ad_campaign ORDER BY id DESC LIMIT 1")).scalar()
    if cid is None:
        db.close()
        pytest.skip("на стенде нет РК")
    yield db, cid
    db.rollback()
    db.close()


def test_store_is_one_row_per_day_and_refetch_does_not_double(db_campaign):
    db, cid = db_campaign
    P.store(db, cid, {date(2099, 1, 1): 100, date(2099, 1, 2): 50})
    P.store(db, cid, {date(2099, 1, 2): 70})                          # перезабор дня — замена, не сумма
    rows = dict(db.execute(text("SELECT date, shows FROM ad_campaign_stat WHERE campaign_id = :c AND source = :s "
                                "AND placement_id IS NULL AND date >= '2099-01-01'"), {"c": cid, "s": P.SOURCE}).all())
    assert rows == {date(2099, 1, 1): 100, date(2099, 1, 2): 70}


def test_link_data_supersedes_the_manual_total_in_the_reconciliation(db_campaign):
    from app.routers.traffic_dashboard import _verifier
    db, cid = db_campaign
    db.execute(text("DELETE FROM ad_campaign_stat WHERE campaign_id = :c AND source = ANY(:s)"),
               {"c": cid, "s": list(SS.VERIFIER)})
    db.execute(text("INSERT INTO ad_campaign_stat (campaign_id, placement_id, date, shows, clicks, source) "
                    "VALUES (:c, NULL, '2099-01-31', 1000, 0, 'weborama_manual')"), {"c": cid})
    assert _verifier(db, [cid])[cid]["shows"] == 1000                 # только ручной — он и считается
    P.store(db, cid, {date(2099, 1, 1): 300, date(2099, 1, 2): 400})
    assert _verifier(db, [cid])[cid]["shows"] == 700                  # есть ссылка — ручной итог не складывается


def test_account_wide_link_without_campaign_filter_is_refused_with_a_reason():
    # Ссылка 10509 (57ULHY и FMRS34) открывает весь аккаунт — проекты и кампании без фильтра: её сумма смешала бы
    # чужие РК. Не принимаем и говорим, какая ссылка нужна.
    loc = ("/10509/reportcenter/reporting/index/guest/1/#/dashboard/dimensions/project/sub_dimension/campaign/"
           "dimension_filters//metrics/impression/table/table/time_unit/day/start_date/2026-10-01/end_date/2026-10-23")
    with pytest.raises(P.LinkError, match="одной кампании"):
        P.filters_from_location(loc)


def test_assembly_modal_refuses_a_bad_report_link_and_changes_nothing():
    """Окно «Загрузить внешний» на сборке (05.11.2026): ссылка проверяется ДО сохранения пикселя — неверная
    не должна ни лечь в РК, ни поменять тег/вставку сделки."""
    from fastapi import HTTPException

    from app.models import User
    from app.routers import sales_dashboard as SD
    from app.sales.models import SalesDeal
    db = SessionLocal()
    try:
        deal = db.query(SalesDeal).filter(SalesDeal.weborama_pixel_mode == "external",
                                          SalesDeal.weborama_pixel_tag.isnot(None)).first()
        admin = db.query(User).filter(User.is_active == 1).order_by(User.id).first()
        if deal is None or admin is None:
            pytest.skip("на стенде нет сделки с внешним пикселем")
        tag, ins = deal.weborama_pixel_tag, deal.weborama_ext_insertion
        with pytest.raises(HTTPException) as e:
            SD.save_deal_campaign_extra(deal.id, SD.CampaignExtraIn(weborama_pixel=True, mode="external", tag=tag,
                                                                    insertion="другая вставка",
                                                                    report_url="https://evil.example/x"),
                                        db=db, current_user=admin)
        assert e.value.status_code == 400 and "Weborama" in e.value.detail
        db.refresh(deal)
        assert (deal.weborama_pixel_tag, deal.weborama_ext_insertion) == (tag, ins)
    finally:
        db.rollback()
        db.close()
