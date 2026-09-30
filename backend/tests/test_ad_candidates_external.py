# -*- coding: utf-8 -*-
"""Кандидаты в РК: поверхность вне нашей DSP тоже площадка РК (30.09.2026).

Случай с прода: у услуги Polza площадка polza.ru ведётся вне контура (Adfox / «вне контура»),
в нашей DSP её нет и блоков нет — и фильтр «заведена в блоках» молча выкидывал её из РК,
а трафик видел только ту площадку, что была привязана к услуге по ошибке. Внешняя
поверхность, с которой мы работаем, обязана попадать в РК; с v2.6.48 она получает там
метку «не наш код» и галочку вместо старт/стоп.
"""
import app.models  # noqa: F401 — регистрирует counterparties для FK моделей продаж
from app.ad.build import candidates
from app.database import SessionLocal
from app.sales.models import (SalesPublisher, SalesPublisherService, SalesPublisherSurface,
                              SalesService)

SVC = "__test_ext_svc"


def _setup(db, channel, we_work):
    pub = SalesPublisher(name="__t_ext", domain="__t_ext.ru", status="СОТРУДНИЧАЕМ")
    db.add(pub)
    db.flush()
    db.add(SalesPublisherSurface(publisher_id=pub.id, kind="web", we_work=we_work,
                                 placement_channel=channel))
    svc = SalesService(name=SVC, group="SIMB-AD", sort_order=999, is_active=True)
    db.add(svc)
    db.flush()
    db.add(SalesPublisherService(publisher_id=pub.id, surface_kind="web", service_id=svc.id,
                                 is_active=True))
    db.flush()
    return pub.id


def _run(channel, we_work):
    db = SessionLocal()
    try:
        pub = _setup(db, channel, we_work)
        return pub, {c["publisher_id"] for c in candidates(db, [SVC], ["web"])}
    finally:
        db.rollback()
        db.close()


def test_external_working_surface_is_candidate():
    pub, got = _run("outside", True)
    assert pub in got, "площадка вне нашей DSP, с которой работаем, выпала из РК"
    pub, got = _run("adfox", True)
    assert pub in got


def test_external_surface_we_do_not_work_is_not_candidate():
    pub, got = _run("outside", False)
    assert pub not in got


def test_dsp_surface_without_blocks_still_excluded():
    pub, got = _run("dsp", True)
    assert pub not in got, "поверхность нашей DSP без блоков по-прежнему не кандидат"
