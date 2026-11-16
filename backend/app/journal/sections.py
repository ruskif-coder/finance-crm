# -*- coding: utf-8 -*-
"""Разделы журнала действий (макет design_handoff_journal, 16.11.2026): «действие → раздел» одной картой в коде.

Действие принадлежит ровно одному разделу. Карта — правилами по ключу действия, первое совпадение побеждает; новое
действие без правила попадает в «Ядро», а не пропадает (так в макете). Ключи действий неизменяемы (записаны в журнале),
поэтому правила стоят на ключах, а не на подписях: подпись правят, ключ — нет.

Раздела «Финансы» в макете нет: там девять ключей демо, а на бою операции, импорт, план оплат и остатки — сотни записей,
и в «Ядре» они бы потерялись (решение 16.11.2026, названо в отчёте).
"""
import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    color: str        # метка раздела: только var(--*)


SECTIONS = (
    Section("login", "Вход", "var(--text-disabled)"),
    Section("sales", "Продажи", "var(--accent)"),
    Section("accounts", "Аккаунты", "var(--income)"),
    Section("documents", "Документы", "var(--warning)"),
    Section("traffic", "Трафик", "var(--accent-hover)"),
    Section("directories", "Справочники", "var(--text-muted)"),
    Section("finance", "Финансы", "var(--danger)"),
    Section("cabinets", "Кабинеты", "var(--text-primary)"),
    Section("core", "Ядро", "var(--text-cap)"),
)
BY_ID = {s.id: s for s in SECTIONS}
DEFAULT = "core"

# (раздел, шаблон ключа). Порядок важен: частные правила — выше общих.
_RULES = [
    ("login", r"^(login_|consent_accepted$)"),
    ("finance", r"(^|_)operations?(_|$)|^import_(apply|operations)$|^credit_line_|^pay_plan_|^export_alfa$|^update_bank_balance$|"
                r"^diadoc_|^update_counterparty_note$|^unlink_operation_parent$"),
    ("documents", r"^annex|^master_deal|^update_master_deal$|^onec_desk_|^(contract|counterparty)_signer$|^signer_|^legal_request_"),
    ("accounts", r"^deal_(closing|cost|fact|from_mp|send_to_do|closed_no_docs|account_|verifier|bonus|weborama|sk_set)|"
                 r"creative|^send_creative_set$|^set_target_|^request_target_url$|^issue_erid|^set_foreign_erid$|targeting|"
                 r"^rights_letter_|^ord_|^launch_target_state_fix$|^save_deal_traffic_brief$|^traffic_pair_|^delete_pair_file$"),
    ("traffic", r"^ad_|^balancer_|^bidder_|^dsp_|^adfox_|^weborama_|^traffic_|^prio_|^premod_|^rk_|^external_resolve$|"
                r"^set_traffic_manager$|^site_monitor_|^set_report_group$|^publisher_recon_"),
    ("cabinets", r"^cabinet_"),
    ("directories", r"counterparty|contract|publisher|^(create|update|delete|deactivate|restore)_sales_(advertiser|agency|brand|"
                    r"price|format|addon)|^merge_|^move_brands$|^delete_brand_hard$|^set_brand_marking$|^set_agency_sk$|"
                    r"^(attach|detach)_|^split_agency|^create_geo$|^create_contact_position$|^bx_|^(un)?map_stage$|"
                    r"^self_promo_|^set_advertiser_sales_rep$|^apply_brand_suggestions$"),
    ("sales", r"deal|media_plan|^mp_|^year_plan_|^sales_(status|target)|^status_reminder_|^agency_terms_|bitrix|^drop_sales_override$"),
]
_COMPILED = [(sid, re.compile(p)) for sid, p in _RULES]


def section_of_staff(key: Optional[str]) -> str:
    """Раздел действия сотрудника (журнал `audit_log`). Без правила — «Ядро»."""
    for sid, rx in _COMPILED:
        if key and rx.search(key):
            return sid
    return DEFAULT


def section_of_cabinet(key: Optional[str]) -> str:
    """Раздел действия площадки в кабинете (журнал `cabinet_log`): вход — к входам, остальное — «Кабинеты»."""
    return "login" if key == "вход" else "cabinets"


def section_of(source: str, key: Optional[str]) -> str:
    return section_of_cabinet(key) if source == "cabinet" else section_of_staff(key)


def label_of(source: str, key: Optional[str]) -> str:
    """Подпись действия. Неизвестный ключ показывается как есть — запись о действии важнее красоты."""
    if source == "cabinet":
        from app.cabinet.journal import BY_KEY
        a = BY_KEY.get(key)
        return a.label if a else (key or "")
    from app.audit_labels import ACTION_LABELS
    return ACTION_LABELS.get(key, key or "")
