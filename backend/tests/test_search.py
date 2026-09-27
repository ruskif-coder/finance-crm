# -*- coding: utf-8 -*-
"""Глобальный поиск — приборы из спецификации (docs/SPEC_глобальный_поиск.md).

Поиск — маршрутизатор поверх реестров: находит объект и отдаёт ссылку на его экран.
Главные риски не в том, что он чего-то не найдёт, а в том, что найдёт ЛИШНЕЕ:
чужую сделку, тип без права, удалённое. Поэтому большая часть приборов — про
видимость, и каждый писался до кода и падал на пустой ручке.
"""
import time

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal, get_db
from app.main import app
from app.models import AuditLog, Role, RolePermission, User
from app.routers.auth import get_current_user
from app.sales.models import SalesDeal, SalesPublisher, SalesRep
from app.search import classify, engine

ITEM_KEYS = {"id", "title", "subtitle", "href", "archived"}
TAG = "Пзкт"   # метка тестовых строк: такого слова в данных нет


@pytest.fixture
def db():
    s = SessionLocal()
    s.commit = s.flush
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture(autouse=True)
def fresh_limiter():
    engine.reset_rate_limit()
    yield
    engine.reset_rate_limit()


def _role(db, key, perms, scope="all"):
    """Роль с правами `perms` = {section: can_view}. Строки нет — права нет вовсе."""
    r = Role(key=f"{key}_{time.time_ns()}", label=f"Роль {key}")
    db.add(r)
    db.flush()
    for section, view in perms.items():
        db.add(RolePermission(role_id=r.id, section=section, can_view=int(view),
                              deals_scope=scope))
    db.flush()
    return r


def _user(db, role):
    u = User(name="Поиск тест", email=f"search_{time.time_ns()}@test.local",
             hashed_password="x", role_id=role.id, is_active=1)
    db.add(u)
    db.flush()
    db.refresh(u)
    return u


def _deal(db, title, rep_id=None):
    n = time.time_ns()
    code = format(n % 36 ** 6, "X")[-6:].rjust(6, "Z")
    d = SalesDeal(bitrix_id=f"search-test-{n}", code=code, title=title, sales_rep_id=rep_id)
    db.add(d)
    db.flush()
    return d


def _types(res):
    return {g["type"] for g in res["groups"] if g["items"]}


def _admin(db):
    return (db.query(User).join(Role, Role.id == User.role_id)
            .filter(Role.key == "admin").first())


# ── распознавание строки ────────────────────────────────────────────────────────

def test_classify_patterns():
    assert classify.classify("DEMO09")["kind"] == "deal_code"
    assert classify.classify("DEMO09")["types"] == ["deal"]
    assert classify.classify("7701234567")["kind"] == "inn"
    assert classify.classify("770123456789")["kind"] == "inn"
    assert set(classify.classify("7701234567")["types"]) == {"counterparty", "contract",
                                                             "ord_contract"}
    assert classify.classify("12345")["kind"] == "digits"
    assert set(classify.classify("12345")["types"]) == {"deal", "contract"}
    assert classify.classify("2VtzqwXyZ1a")["kind"] == "erid"
    assert classify.classify("2VtzqwXyZ1a")["types"] == ["erid"]
    assert classify.classify("оккам")["kind"] == "text"
    assert classify.classify("оккам")["types"] is None, "текст — все разрешённые типы"
    # слово латиницей из шести букв — не код сделки: иначе «berlin» искал бы одни сделки
    assert classify.classify("berlin")["kind"] == "text"


# ── состав строки выдачи ────────────────────────────────────────────────────────

def test_search_dto_pin(db):
    """Ключи строки — ровно пять. Лишнее поле (сумма, ИНН в чужом типе) роняет тест."""
    _deal(db, f"{TAG} состав строки")
    res = engine.run(db, _admin(db), TAG)
    assert res["groups"], "тестовая сделка не нашлась"
    for g in res["groups"]:
        assert set(g) == {"type", "items", "more"}
        assert isinstance(g["more"], bool), "more — флаг, не число"
        for it in g["items"]:
            assert set(it) == ITEM_KEYS, it


def test_exact_code_goes_first(db):
    d = _deal(db, f"{TAG} точный код")
    _deal(db, f"{TAG} {d.code} упомянут в названии")
    items = next(g for g in engine.run(db, _admin(db), d.code)["groups"]
                 if g["type"] == "deal")["items"]
    assert items[0]["id"] == d.id
    assert items[0]["href"] == f"/sales/deals/{d.code}"


def test_more_is_a_flag_not_a_count(db):
    for i in range(3):
        _deal(db, f"{TAG} много {i}")
    g = next(g for g in engine.run(db, _admin(db), TAG, per_type=2)["groups"]
             if g["type"] == "deal")
    assert len(g["items"]) == 2 and g["more"] is True


# ── права и область ─────────────────────────────────────────────────────────────

def test_search_matrix(db, monkeypatch):
    """Каждая живая роль: типы в выдаче — ровно те, на которые у неё есть `view`."""
    assert set(engine.SEARCHERS) == {"deal", "counterparty", "contract", "publisher",
                                     "advertiser", "agency", "brand", "media_plan",
                                     "ord_contract", "erid"}
    def fake(t):
        return lambda db_, q, limit, offset, ctx: [
            {"id": 1, "title": t, "subtitle": "", "href": "/", "archived": False}]
    monkeypatch.setattr(engine, "SEARCHERS",
                        {t: (sec, fake(t)) for t, (sec, _) in engine.SEARCHERS.items()})
    from app.permissions import get_permissions_for_user
    roles = db.query(Role).all()
    assert roles
    for role in roles:
        u = db.query(User).filter(User.role_id == role.id).first() or _user(db, role)
        perms = get_permissions_for_user(db, u)
        allowed = {t for t, (sec, _) in engine.SEARCHERS.items()
                   if perms.get(sec, {}).get("view")}
        got = _types(engine.run(db, u, "запрос"))
        assert got == allowed, f"роль {role.key}: {got ^ allowed}"


def test_search_own_scope(db):
    role = _role(db, "own_sales", {"sales_registry": True}, scope="own")
    u = _user(db, role)
    rep = SalesRep(name="Поиск тест", user_id=u.id)
    db.add(rep)
    db.flush()
    mine = _deal(db, f"{TAG} своя", rep_id=rep.id)
    other = _deal(db, f"{TAG} чужая")
    ids = {it["id"] for g in engine.run(db, u, TAG)["groups"] for it in g["items"]}
    assert mine.id in ids
    assert other.id not in ids, "сейлз с областью «свои» нашёл чужую сделку"


def test_search_no_row_is_nothing(db):
    """Нет строки `sales_registry` — сделок нет, а не «все» (F1-05)."""
    role = _role(db, "no_row", {"counterparties": True})
    u = _user(db, role)
    _deal(db, f"{TAG} без строки")
    assert "deal" not in _types(engine.run(db, u, TAG))
    assert engine.deal_scope(db, u) == [], "область без строки права должна быть пустой"


def test_erid_follows_deal_scope(db):
    """ЕРИД ведёт на сделку — значит и видимость у него сделочная."""
    role = _role(db, "own_ord", {"ord": True, "sales_registry": True}, scope="own")
    u = _user(db, role)
    ctx = engine.context(db, u)
    assert ctx["deals"] == [], "у роли «свои» без сейлза своих сделок нет"


# ── HTTP: валидация, молчание скрытого, журнал ─────────────────────────────────

@pytest.fixture
def client_as(db):
    def make(user):
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: db
        return TestClient(app)
    yield make
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


def test_search_validation(db, client_as):
    c = client_as(_admin(db))
    assert c.post("/api/search", json={"q": "а"}).status_code == 400
    assert c.post("/api/search", json={"q": "   а   "}).status_code == 400
    assert c.post("/api/search", json={"q": "а" * 101}).status_code == 400
    r = c.post("/api/search", json={"q": TAG, "types": ["нет_такого", "deal"]})
    assert r.status_code == 200, "неизвестный тип отбрасывается молча"
    assert "нет_такого" not in r.text
    assert c.post("/api/search", json={"q": TAG, "per_type": 0}).status_code in (400, 422)
    assert c.post("/api/search", json={"q": TAG, "per_type": 51}).status_code in (400, 422)


def test_search_hidden_is_silent(db, client_as):
    """Совпало только со скрытым типом — ответ тот же, что «ничего не нашлось»."""
    role = _role(db, "only_cp", {"counterparties": True})
    c = client_as(_user(db, role))
    _deal(db, f"{TAG} скрытая")
    hidden = c.post("/api/search", json={"q": TAG})
    nothing = c.post("/api/search", json={"q": "ъъъъъъъъ"})
    assert hidden.status_code == nothing.status_code == 200
    assert hidden.json() == nothing.json()
    for word in ("скрыт", "доступ", "прав"):
        assert word not in hidden.text.lower()


def test_search_no_audit(db, client_as):
    c = client_as(_admin(db))
    before = db.query(AuditLog).count()
    assert c.post("/api/search", json={"q": TAG}).status_code == 200
    assert db.query(AuditLog).count() == before


def test_rate_limit(db, client_as):
    c = client_as(_admin(db))
    codes = [c.post("/api/search", json={"q": TAG}).status_code for _ in range(6)]
    assert codes[:5] == [200] * 5
    assert codes[5] == 429


# ── архив и удалённое ───────────────────────────────────────────────────────────

def test_search_deleted_excluded(db):
    d = _deal(db, f"{TAG} удалённая")
    code, bid = d.code, d.bitrix_id
    admin = _admin(db)
    assert any(it["id"] == d.id for g in engine.run(db, admin, code)["groups"]
               for it in g["items"])
    db.delete(d)
    from sqlalchemy import text
    db.execute(text("INSERT INTO sales_deleted_deals (bitrix_id) VALUES (:b)"), {"b": bid})
    db.flush()
    for q in (code, f"{TAG} удалённая"):
        assert not any(g["items"] for g in engine.run(db, admin, q)["groups"]
                       if g["type"] == "deal")


def test_archived_publisher_marked_and_after_live(db):
    live = SalesPublisher(name=f"{TAG} площадка живая", domain=f"live{time.time_ns()}.test",
                          status="ПЕРЕГОВОРЫ")
    arch = SalesPublisher(name=f"{TAG} площадка архивная", domain=f"arch{time.time_ns()}.test",
                          status="АРХИВ")
    db.add_all([arch, live])
    db.flush()
    items = next(g for g in engine.run(db, _admin(db), f"{TAG} площадка")["groups"]
                 if g["type"] == "publisher")["items"]
    by_id = {it["id"]: it for it in items}
    assert by_id[arch.id]["archived"] is True and by_id[live.id]["archived"] is False
    assert [it["id"] for it in items].index(live.id) < [it["id"] for it in items].index(arch.id)


def test_no_money_in_the_answer(db):
    """Суммы не выдаём (решение 4): ни ключа, ни «₽» в тексте строк."""
    _deal(db, f"{TAG} деньги")
    res = engine.run(db, _admin(db), TAG)
    assert res["groups"], "сделка не нашлась — проверять нечего"
    blob = str(res)
    assert "amount" not in blob and "₽" not in blob


def test_pattern_narrows_types(db):
    """Код сделки ищет только сделки — даже если он встречается в имени контрагента."""
    from app.models import Counterparty
    d = _deal(db, f"{TAG} шаблон")
    db.add(Counterparty(name=f"{d.code} {TAG} ООО"))
    db.flush()
    assert _types(engine.run(db, _admin(db), d.code)) == {"deal"}


def test_capital_word_falls_back_to_text(db):
    """Шесть заглавных без видимой сделки с таким кодом — это слово, ищем везде."""
    from app.models import Counterparty
    word = "QXQXQX"
    assert not db.query(SalesDeal).filter(SalesDeal.code == word).count()
    db.add(Counterparty(name=f"{word} {TAG} ООО"))
    db.flush()
    assert "counterparty" in _types(engine.run(db, _admin(db), word))


# ── ревью 27.09.2026 ─────────────────────────────────────────────────────────────

def test_erid_needs_deal_registry_too():
    """ЕРИД показывает код сделки и ведёт на её карточку — без права на реестр сделок нельзя."""
    only_ord = {"ord": {"view": True}}
    assert "erid" not in engine.allowed_types(only_ord)
    assert "ord_contract" in engine.allowed_types(only_ord)
    both = {"ord": {"view": True}, "sales_registry": {"view": True}}
    assert "erid" in engine.allowed_types(both)


def test_erid_is_found_where_it_lives(db):
    """Живые ЕРИД — у креатива РК, а не в пустом зеркале ОРД."""
    from app.ad.models import AdCampaign, AdCampaignCreative, AdCampaignPlacement
    d = _deal(db, f"{TAG} ерид")
    pub = db.query(SalesPublisher.id).order_by(SalesPublisher.id).first()[0]
    camp = AdCampaign(deal_id=d.id, status="запущена")
    db.add(camp)
    db.flush()
    pl = AdCampaignPlacement(campaign_id=camp.id, publisher_id=pub, status="ждёт запуска")
    db.add(pl)
    db.flush()
    erid = "2SDnjeTst9Qz"
    db.add(AdCampaignCreative(campaign_id=camp.id, placement_id=pl.id, creative_no=1,
                              status="согласован", erid=erid))
    db.flush()
    groups = engine.run(db, _admin(db), erid)["groups"]
    assert [g["type"] for g in groups] == ["erid"]
    it = groups[0]["items"][0]
    assert it["title"] == erid and it["href"] == f"/sales/deals/{d.code}"


def test_numeric_pattern_falls_back_to_text(db):
    """Десять цифр — не обязательно ИНН. Не нашлось по подсказке — ищем по всем типам."""
    pub = SalesPublisher(name=f"{TAG} 9876543210", domain=f"n{time.time_ns()}.test",
                         status="ПЕРЕГОВОРЫ")
    db.add(pub)
    db.flush()
    assert "publisher" in _types(engine.run(db, _admin(db), "9876543210"))
