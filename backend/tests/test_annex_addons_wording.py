# -*- coding: utf-8 -*-
"""Стандартные формулировки допов (владелец 21.10.2026): подстановка {услуга}, пункт 1 ДС допов, основание по составу ДС."""
from app.annex_tpl import assemble as AS
from app.annex_tpl.subs import SUBS


class _DB:
    """Поддельная база: формулировки справочника доп. услуг и услуги сделок."""
    def __init__(self, phrases, services=()):
        self.phrases, self.services = phrases, list(services)

    def execute(self, q, params=None):
        sql = str(q)
        rows = list(self.phrases.items()) if "sales_addon_services" in sql else [(s,) for s in self.services]

        class R:
            def all(self_):
                return rows

            def scalars(self_):
                class S:
                    def all(s2):
                        return [r[0] for r in rows]
                return S()
        return R()


def test_substitution_is_registered():
    assert "услуга" in SUBS


def test_addons_only_lists_phrases_then_name_lowercased():
    db = _DB({"Комплект рекламных материалов": "изготовление комплекта рекламных материалов"})
    rows = [{"kind": "extra", "position": "Комплект рекламных материалов"}, {"kind": "extra", "position": "Sales-Lift"},
            {"kind": "discount", "position": "Скидка СК 5 %"}]
    assert AS.service_text(db, [1], rows) == "изготовление комплекта рекламных материалов, Sales-Lift"


def test_deal_service_is_not_listed_only_addons():
    db = _DB({"Sales-Lift": "проведение исследования Sales-Lift"}, services=["еФарм"])
    assert AS.service_text(db, [1], [{"kind": "base", "position": "еФарм"}, {"kind": "extra", "position": "Sales-Lift"}])         == "проведение исследования Sales-Lift"
    assert AS.service_text(db, [1], [{"kind": "base", "position": "еФарм"}]) == ""


def test_closing_template_by_composition():
    assert AS.closing_template_for([{"kind": "base"}]) == AS.CLOSING_DEFAULT
    addons = AS.closing_template_for([{"kind": "extra"}, {"kind": "discount"}])
    assert addons.startswith("Оказание дополнительных услуг ({услуга}) для бренда") and "{сеть}" not in addons
    assert AS.closing_template_for([{"kind": "base"}, {"kind": "extra"}]).startswith(
        "Размещение рекламных материалов и оказание дополнительных услуг ({услуга})")


def test_addons_p1_uses_service_substitution():
    assert "{услуга}" in AS.P1_ADDONS and AS.composition([{"kind": "extra"}]) == "addons"
