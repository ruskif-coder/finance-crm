# -*- coding: utf-8 -*-
"""Общая часть уборки тестов сборки запуска: креативы кампаний на тестовых комплектах.

Репетиция на копии прода 23.09.2026: у тестовой сделки там есть НАСТОЯЩАЯ кампания, и
отправка тестового комплекта заводила в неё строку `ad_campaign_creative` со ссылкой на
комплект (`root_set_id`, удаление без каскада). Уборка тестов эти строки не знала — удаление
комплекта падало на внешнем ключе, и 66 тестов подряд спотыкались об мусор первого. На
стенде у тестовой сделки кампании нет, поэтому там этого не видно.

Зовётся В НАЧАЛЕ каждой уборки, до удаления комплектов.
"""
from app.ad.models import AdCampaignCreative
from app.launch_prep.models import LaunchPrepCreativeSet


def drop_campaign_creatives(db, min_no: int) -> None:
    """Снять креативы кампаний, заведённые на тестовые комплекты (номер ≥ `min_no`)."""
    ids = db.query(LaunchPrepCreativeSet.id).filter(LaunchPrepCreativeSet.no >= min_no)
    db.query(AdCampaignCreative).filter(
        AdCampaignCreative.root_set_id.in_(ids)).delete(synchronize_session=False)
