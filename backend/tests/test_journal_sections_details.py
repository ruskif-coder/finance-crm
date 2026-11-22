# -*- coding: utf-8 -*-
"""Журнал действий по макету design_handoff_journal (16.11.2026): разделы действий и человеческие детали.

Действие принадлежит ровно одному разделу; новое действие без правила попадает в «Ядро», а не пропадает. Детали
переписываются только по известным шаблонам — неизвестное остаётся как было (макет, допущение 5)."""
import pytest

from app.audit_labels import ACTION_LABELS
from app.journal import details as dt
from app.journal import sections as sc


def test_every_known_action_lands_in_exactly_one_known_section():
    ids = {s.id for s in sc.SECTIONS}
    for key in ACTION_LABELS:
        assert sc.section_of_staff(key) in ids, key


@pytest.mark.parametrize("key, section", [
    ("login_success", "login"), ("login_failed", "login"),
    ("year_plan_save", "sales"), ("year_plan_export", "sales"), ("move_deal", "sales"), ("create_media_plan", "sales"),
    ("create_targeting_item", "accounts"), ("deal_closing_confirm", "accounts"), ("deal_send_to_do", "accounts"),
    ("deal_from_mp", "accounts"), ("issue_erid", "accounts"), ("creative_pair_verdict", "accounts"),
    ("master_deal_start_no", "documents"), ("master_deal_settings", "documents"), ("master_deal_to_annex", "documents"),
    ("annex_confirm", "documents"), ("onec_desk_file", "documents"),
    ("ad_campaign_finish", "traffic"), ("traffic_realloc", "traffic"), ("dsp_provision", "traffic"), ("prio_send", "traffic"),
    ("update_contract", "directories"), ("update_counterparty", "directories"), ("patch_publisher", "directories"),
    ("bx_link", "directories"), ("update_sales_brand", "directories"),
    ("create_operation", "finance"), ("bulk_update_operation", "finance"), ("pay_plan_add", "finance"),
    ("cabinet_create", "cabinets"),
    ("update_role", "core"), ("create_user", "core"), ("drop_sales_override", "sales"), ("journal_export", "core"), ("никому_не_известное", "core"),
])
def test_sample_actions_by_meaning(key, section):
    assert sc.section_of_staff(key) == section


def test_cabinet_actions_login_apart_from_the_rest():
    assert sc.section_of_cabinet("вход") == "login"
    assert sc.section_of_cabinet("креатив_ок") == "cabinets"
    assert sc.label_of("cabinet", "креатив_ок") == "Согласован креатив"
    assert sc.label_of("staff", "login_success") == "Вход выполнен"
    assert sc.label_of("staff", "zz_unknown") == "zz_unknown"


@pytest.mark.parametrize("action, raw, want", [
    ("create_targeting_item", "interests: детские противовирусные", "интересы: детские противовирусные"),
    ("create_targeting_item", "buys: средства от герпеса", "покупки: средства от герпеса"),
    ("master_deal_settings",
     "M-0043: раскладка сохранена — addons_mode=separate, bonus_addons=hide, ds_by_brand=True, ds_by_service=True, "
     "upd_by_brand=True, upd_by_service=False, moved=[]",
     "M-0043: раскладка сохранена — допы отдельным ДС, бонусные допы скрыты, ДС по брендам и услугам, УПД по брендам"),
    ("master_deal_settings",
     "M-0044: раскладка сохранена — addons_mode=fold, bonus_addons=hide, ds_by_brand=True, ds_by_service=True, "
     "upd_by_brand=True, upd_by_service=False, moved=[]",
     "M-0044: раскладка сохранена — допы в стоимости базовой услуги, бонусные допы скрыты, ДС по брендам и услугам, УПД по брендам"),
    ("bulk_update_operation", "ids=[2691]; status=ОПЛАЧЕНО, date=2026-11-12, bank=Наличные",
     "записей: 1; статус ОПЛАЧЕНО, дата 12.11.2026, банк Наличные"),
    ("bulk_delete_operation", "ids=[2721, 2854]; удалено 2", "записей: 2; удалено 2"),
    ("bx_link", "ЭвоКом ↔ bx 410 (master=ours)", "ЭвоКом ↔ bx 410 (основная — наша запись)"),
    ("set_target_url", "креатив №3: https://site.ru/search/%D0%B8%D0%B1%D1%83", "креатив №3: https://site.ru/search/ибу"),
    ("update_role", "что-то своё без шаблона", "что-то своё без шаблона"),
    ("update_role", None, ""),
])
def test_details_are_humanized_only_by_known_patterns(action, raw, want):
    assert dt.humanize(action, raw) == want
