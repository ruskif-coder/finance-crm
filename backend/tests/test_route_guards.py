"""Инвентарь охраны эндпоинтов.

Право на раздел объявляется шестью разными способами (`require_permission`,
`require_admin`, `require_any_permission` — в зависимостях; `_guard_owned`,
`_has_perm`, прямой `get_permissions_for_user` — в теле функции). Три последних
невидимы снаружи, поэтому «закрыт ли этот эндпоинт» нельзя было ответить иначе,
чем чтением 288 функций подряд.

Тест отвечает на этот вопрос машиной и, главное, **роняет сборку на новом
незакрытом эндпоинте**. Ровно тот же приём, что `test_permissions_groups`
(пиннинг ключей прав) и `scripts/check-nav.mjs` (пиннинг адресов страниц).

`OWN_DATA` — единственный список исключений: эндпоинты, где пользователь работает
со СВОИМИ данными (свои уведомления, свои подписки, свой пароль). Права на раздел
там быть не должно — право отвечает на вопрос «чьё это», а тут ответ всегда «моё».

Замер 2026-08-23 после закрытия долга волны 1: 268 роутов под правом, 13 своих
данных, 4 с проверкой в теле, 3 открытых. До закрытия было 232 под правом и 32
незакрытых.
"""
import inspect

import pytest
from fastapi.routing import APIRoute

from app.main import app

# Зависимости, которые сами по себе означают проверку права.
GUARD_DEPS = {
    "require_permission.<locals>.checker",
    "require_any_permission.<locals>.checker",
    "require_admin",
    # Вход для сервиса кабинета (2026-08-28). Права роли здесь неприменимы: снаружи
    # стоит не человек, а наш процесс во внешнем контуре. Это ОХРАНА, а не исключение —
    # общий секрет из окружения, пустой секрет закрывает вход насовсем.
    "require_cabinet_service",
}

# Признаки проверки права ВНУТРИ тела функции. Не идеальны, но это и есть цена
# трёх невидимых идиом — когда волна 1 сведёт их к зависимостям, эвристика уйдёт.
BODY_MARKS = ("get_permissions_for_user", "_has_perm", "_guard_owned",
              "deals_scope", "_own_", "_is_master")

# Без аутентификации вообще — и это правильно.
OPEN_BY_DESIGN = {
    ("POST", "/api/auth/login"),                                    # вход
    ("POST", "/api/notifications/settings/telegram/webhook/{secret}"),  # секрет в адресе
    # Вебхук бота КАБИНЕТА. Открыт по той же причине и закрыт тем же способом: стучится
    # Телеграм, у него нет ни нашей сессии, ни сервисного токена. Секрет свой, отдельный
    # от внутреннего — общий означал бы, что апдейт одного бота принимается адресом другого.
    ("POST", "/api/pub-bot/webhook/{secret}"),
    ("GET", "/"),                                                   # корень, отдаёт статус
}

# Свои собственные данные: право на раздел здесь не нужно.
OWN_DATA = {
    ("POST", "/api/auth/verify-password"),
    ("POST", "/api/auth/accept-consent"),
    ("GET", "/api/notifications"),
    ("GET", "/api/notifications/count"),
    ("POST", "/api/notifications/read"),
    ("GET", "/api/notifications/settings/catalog"),
    ("GET", "/api/notifications/settings/me"),
    ("PUT", "/api/notifications/settings/me/subscriptions"),
    ("DELETE", "/api/notifications/settings/me/subscriptions/{event_key}"),
    ("PUT", "/api/notifications/settings/me/channels"),
    ("POST", "/api/notifications/settings/me/telegram/link"),
    ("DELETE", "/api/notifications/settings/me/telegram"),
    ("POST", "/api/notifications/settings/me/telegram/test"),
    # ЗАЯВКА О СБОЕ — своё свидетельство, а не раздел системы. Подача сознательно НЕ
    # закрыта правом `settings_bugs`: закрыв её, мы получили бы ровно то состояние, ради
    # выхода из которого всё и затевалось — человек видит сбой и не может о нём сказать.
    # Аутентификация при этом обязательна (анонимных заявок не бывает), а дополнять и
    # «досылать» можно только СВОЮ заявку — проверка по автору внутри ручек.
    # Журнал, статусы и чужие снимки закрыты правом, как и положено.
    ("POST", "/api/bugs"),
    ("POST", "/api/bugs/{report_id}/file"),
    ("POST", "/api/bugs/{report_id}/sent"),
    # СОСТОЯНИЕ ТЕХОБСЛУЖИВАНИЯ читает каждый вошедший, и права здесь быть не должно:
    # по этому ответу экран рисует полосу «через N минут» и заглушку. Закрой его правом —
    # человек без права увидел бы пустую ошибку вместо объяснения, почему всё закрыто.
    # Объявление и снятие (POST/DELETE) закрыты `require_admin`.
    ("GET", "/api/maintenance"),
}

# Долг волны 1 ЗАКРЫТ 2026-08-23: девятнадцать общих реестров (контрагенты,
# статьи, рекламодатели, агентства, бренды, услуги, воронки, стадии, сотрудники,
# гео, таргетинги, периоды отчётов) читались по одному факту входа. Теперь у
# каждого стоит require_any_permission по набору разделов, которые этот список
# реально дёргают; набор снят с фронта, а не придуман.
#
# Список намеренно НЕ заменён пустым множеством: если реестр снова окажется
# незакрытым, он попадёт в общий отчёт test_no_new_ungated_route, и это будет
# видно как новая находка, а не как «вернулось в долг».


def _dep_names(dependant, acc=None):
    """Все зависимости роута по дереву, по полному имени функции."""
    acc = set() if acc is None else acc
    call = getattr(dependant, "call", None)
    if call is not None:
        acc.add(getattr(call, "__qualname__", str(call)))
    for sub in getattr(dependant, "dependencies", []):
        _dep_names(sub, acc)
    return acc


def _routes():
    for r in app.routes:
        if isinstance(r, APIRoute):
            for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
                yield (m, r.path), r


def _classify(route):
    names = _dep_names(route.dependant)
    if names & GUARD_DEPS:
        return "guarded"
    if "get_current_user" not in names:
        return "open"
    try:
        src = inspect.getsource(route.endpoint)
    except OSError:                                    # pragma: no cover
        src = ""
    return "body" if any(m in src for m in BODY_MARKS) else "ungated"


@pytest.fixture(scope="module")
def inventory():
    out = {"guarded": set(), "body": set(), "open": set(), "ungated": set()}
    for key, route in _routes():
        out[_classify(route)].add(key)
    return out


def test_open_routes_are_the_three_we_know(inventory):
    """Роут без аутентификации — всегда осознанное решение, не побочный эффект."""
    assert inventory["open"] == OPEN_BY_DESIGN


def test_no_new_ungated_route(inventory):
    """Главная проверка: новый эндпоинт без права дальше не проходит.

    Если тест упал на вашем роуте — повесьте `Depends(require_permission(...))`,
    а для списка, который кормит несколько экранов, — `require_any_permission` по
    набору их разделов. Дополнять OWN_DATA можно только с ответом на вопрос
    «почему права здесь не надо».
    """
    unexpected = inventory["ungated"] - OWN_DATA
    assert not unexpected, (
        "эндпоинты без проверки права: "
        + ", ".join(f"{m} {p}" for m, p in sorted(unexpected))
    )


def test_every_route_is_accounted_for(inventory):
    """Сумма классов равна числу роутов — иначе классификация врёт молча."""
    total = sum(len(v) for v in inventory.values())
    assert total == len(list(_routes()))
    assert total > 250, "роутов стало подозрительно мало — сломался обход"


# ── проверка на живых ролях ─────────────────────────────────────────────────
# Объявить зависимость мало: набор разделов может оказаться таким широким, что
# гейт не отсекает никого. Тест берёт РЕАЛЬНЫЕ роли из базы и проверяет, что
# разделение контуров действительно работает.

def _sections(db, role_key):
    from app.models import Role, RolePermission
    r = db.query(Role).filter(Role.key == role_key).first()
    if not r:
        return None
    return {p.section for p in db.query(RolePermission)
            .filter(RolePermission.role_id == r.id, RolePermission.can_view == 1).all()}


def _passes(sections, allowed):
    """Повторяет решение require_any_permission: хватает одного совпадения."""
    return bool(sections & set(allowed))


def test_finance_role_cannot_read_the_sales_directories():
    """Финансовая роль не должна перечислять рекламодателей, агентства и бренды."""
    from app.database import SessionLocal
    from app.routers.sales_directories import PARTY_READ  # noqa: F401 — проверяем набор ниже
    db = SessionLocal()
    try:
        fin = _sections(db, "manager")
        if fin is None:
            import pytest as _p
            _p.skip("роли manager нет в этой базе")
        party = ("dir_advertisers", "dir_agencies", "media_plans", "media_plans_editor",
                 "sales_dashboard", "sales_registry", "year_plan", "accounts_dashboard")
        assert not _passes(fin, party), "финансовая роль всё ещё видит справочники продаж"
        # но контрагентов — видит, иначе сломается форма операций
        cp = ("counterparties", "contracts", "operations",
              "dir_advertisers", "dir_agencies", "dir_publishers")
        assert _passes(fin, cp), "финансовая роль потеряла доступ к списку контрагентов"
    finally:
        db.close()


def test_sales_role_keeps_the_dropdowns_it_needs():
    """Обратная сторона: продажам нельзя сломать выпадающие списки."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        sales = _sections(db, "role_7")
        if sales is None:
            import pytest as _p
            _p.skip("роли role_7 нет в этой базе")
        party = ("dir_advertisers", "dir_agencies", "media_plans", "media_plans_editor",
                 "sales_dashboard", "sales_registry", "year_plan", "accounts_dashboard")
        stage = ("settings_pipelines", "sales_dashboard", "sales_registry",
                 "accounts_dashboard", "year_plan")
        assert _passes(sales, party), "продажи потеряли справочник рекламодателей"
        assert _passes(sales, stage), "продажи потеряли каталог стадий"
    finally:
        db.close()
