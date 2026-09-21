# -*- coding: utf-8 -*-
"""Область видимости сделок: перепись как тест.

`deals_scope` («свои» / «все») решает, видит ли продавец чужие сделки, то есть
чужие деньги. Реализован он не одним механизмом, а несколькими — и это нормально
(проверка списка, проверка одной сделки, владение планом устроены по-разному), —
но означает, что «применена ли здесь область» глазами не проверить: запросов к
`SalesDeal` в коде сорок пять.

Тест проходит по дереву исходников, находит все роуты, которые обращаются к
`SalesDeal`, и требует, чтобы каждый либо применял один из известных механизмов,
либо был в списке исключений — с причиной. Новый эндпоинт, забывший про область,
роняет сборку, а не доживает до прода.

Разбор 2026-08-23 нашёл этим способом три места и починил их:

* `year_plan.update_plan` и `year_plan.delete_plan` брали план по id и владельца
  не проверяли. Сейлз с `year_plan:edit` и областью «свои» мог переименовать
  чужой план, переназначить его на себя (`PlanPatch.sales_rep_id`) или удалить —
  а удаление ещё и отвязывает все сделки строк, то есть рвёт связь с фактом.
* `media_plans.mp_deal_prefill` отдавал бриф ЛЮБОЙ сделки по id: право
  конструктора МП открывает конструктор, а не чужие сделки.

Ложные тревоги, которые тест обязан не поднимать (проверено вручную): пять
эндпоинтов вокруг `_deal_by_ref` защищены `_assert_deal_in_scope`, конвейер
годового плана — через `_resolve_rep`, бонусы — собственной проверкой
`is_head`/`is_admin`.
"""
import ast
import io
import os


from app import models as _anchor          # у пакета app нет __init__.py, берём модуль
from app.routers.sales_dashboard import _deal_owned

ROOT = os.path.dirname(os.path.abspath(_anchor.__file__))

# Известные механизмы области. Их несколько, потому что задачи разные: ограничить
# выборку, проверить одну сделку, определить «своего» сейлза, проверить владение
# планом или медиапланом.
SCOPE_HELPERS = (
    "_assert_deal_in_scope",   # одна сделка по прямому id
    "_apply_own_scope",        # ограничение выборки
    "_scope_deal_ids",         # массовые операции
    "_own_rep_ids_or_all",
    "_pick_scope_section",
    "_guard_owned",            # медиаплан
    "_guard_plan_owner",       # годовой план
    "_guard_deal_owner",       # сделка в терминах годового плана
    "_resolve_rep",            # конвейер: не-мастер прижат к своему сейлзу
    # Годовой план, с 21.09.2026: у строки две оси владения — продавец и ведущий
    # аккаунт. `_scope_reps` считает, чьи строки показываем, `_mine` сужает выборку.
    # Заменили собой `_resolve_rep` в пяти местах, и прибор это заметил: выгрузка
    # в Excel осталась без единого знакомого ему механизма и была названа дырой.
    "_scope_reps",
    "_mine",
    "_is_master",
)

# Роуты, обращающиеся к SalesDeal без области — намеренно. Причина обязательна:
# без неё список превращается в свалку, и тест перестаёт что-либо значить.
EXEMPT = {
    # Обслуживание справочников. Каскад по сделкам — следствие правки справочника,
    # а не просмотр чужих сделок; закрыты правами dir_* / settings_pipelines.
    "delete_pipeline": "каскад переименования воронки",
    "merge_advertiser": "слияние рекламодателей",
    "merge_agency": "слияние агентств",
    "move_brands": "перенос брендов",
    "merge_brands": "слияние брендов",
    "delete_brand_hard": "жёсткое удаление бренда",
    # Агрегаты: наружу уходит ЧИСЛО сделок на стадии, не их содержание.
    "pipeline_stages": "счётчики сделок по стадиям воронки",
    "save_stage_catalog": "счётчик занятости стадий перед удалением",
    # Собственные проверки, не совпадающие ни с одним общим механизмом.
    "dashboard_bonus": "своя проверка is_admin/is_head, по умолчанию — свой сейлз",
    "field_audit_deal": "диагностика сверки с Битриксом, право settings_field_audit",
    # Реестр медиапланов: область считается по ПЛАНАМ (_mp_own_only/_plan_owned выше
    # по функции), а сделка читается только у тех планов, которые уже прошли этот
    # отбор — код и стадия для колонки «Сделка». Чужая сделка так не покажется:
    # чтобы её увидеть, нужен доступ к её медиаплану.
    "list_media_plans": "область по планам, сделка — только у видимых",
    # Глобальная операция под правом уровня продавца — вопрос к владельцу, не дыра:
    # заливает в Битрикс накопленные правки всех, но наружу данных не отдаёт.
    "push_edits_to_bitrix": "разовая заливка накопленных правок, вопрос владельцу",
}


def _routes_touching_deals():
    out = []
    for dirpath, _, files in os.walk(ROOT):
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(dirpath, f)
            src = io.open(path, encoding="utf-8").read()
            if "SalesDeal" not in src:
                continue
            try:
                tree = ast.parse(src)
            except SyntaxError:                       # pragma: no cover
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                deco = " ".join(ast.dump(d) for d in node.decorator_list)
                if "router" not in deco:
                    continue
                body = ast.get_source_segment(src, node) or ""
                # Форм обращения к сделке несколько, и слепое пятно тут дорого стоит:
                # первая версия обхода знала только `query(SalesDeal)` и пропустила
                # `detach_deal`, который берёт сделку через `db.get(SalesDeal, id)`.
                touches = ("query(SalesDeal)", "get(SalesDeal,", "get(SalesDeal ",
                           "filter(SalesDeal.", "query(SalesYearPlan)",
                           "get(SalesYearPlan", "query(SalesYearPlanLine)")
                if not any(t in body for t in touches):
                    continue
                rel = os.path.relpath(path, ROOT).replace("\\", "/")
                out.append((rel, node.name, body))
    return out


def test_every_deal_route_applies_scope_or_is_listed():
    naked = []
    for rel, name, body in _routes_touching_deals():
        if any(h in body for h in SCOPE_HELPERS):
            continue
        if name in EXEMPT:
            continue
        naked.append(f"{rel}::{name}")
    assert not naked, (
        "роуты трогают сделки без проверки области видимости:\n  "
        + "\n  ".join(sorted(naked))
        + "\n\nЛибо примените механизм из SCOPE_HELPERS, либо внесите в EXEMPT с причиной."
    )


def test_exemptions_are_all_still_real():
    """Исключение, потерявшее свой роут, — мусор: список должен сокращаться."""
    names = {name for _, name, _ in _routes_touching_deals()}
    stale = sorted(set(EXEMPT) - names)
    assert not stale, f"в EXEMPT остались несуществующие роуты: {stale}"


def test_the_census_actually_finds_something():
    """Страховка от молчаливой поломки обхода."""
    assert len(_routes_touching_deals()) >= 20


# --- предикат владения ------------------------------------------------------

def test_deal_is_own_for_both_seller_and_account():
    assert _deal_owned(7, None, [7])          # продавец
    assert _deal_owned(None, 7, [7])          # аккаунт
    assert _deal_owned(3, 7, [7])             # аккаунт при чужом продавце


def test_someone_elses_deal_is_not_own():
    assert not _deal_owned(1, 2, [7])
    assert not _deal_owned(None, None, [7])


def test_user_without_a_rep_link_owns_nothing():
    """Пустой список — это «ничего», а не «всё»: иначе роль без привязки к сейлзу
    получила бы полный доступ вместо пустой выдачи."""
    assert not _deal_owned(1, 2, [])
    assert not _deal_owned(1, 2, None)
