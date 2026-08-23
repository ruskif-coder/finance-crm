"""
Обход блокировщиков рекламы: слово «advertiser» в адресе режется браузером.

uBlock/AdGuard с EasyList вырезают запросы, в адресе которых есть «advertiser».
Запрос при этом не доходит до сервера вообще: в браузере ошибка без ответа, в
логах бэкенда — пусто, и поломка выглядит как «кнопка просто не работает».

В проекте это уже обходили дважды: параметр advertiser_id ездит как producer_id,
а справочник рекламодателей называется /producers. Сверка справочников осталась
на прямом имени и сломалась 2026-08-23: адрес /api/sales/reconcile/advertisers
проходил (кончается на слово), а /advertisers/link и /advertisers/deal-counts —
нет. Список грузился, любое действие над ним молча не работало.

Тесты держат обе стороны обхода: нейтральный адрес доходит до обработчика
рекламодателей, а прямой продолжает работать (им ходят открытые вкладки).
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.auth import get_current_user
import app.routers.sales_reconcile as rec


class _FakeRole:
    key = "admin"


class _FakeAdmin:
    id = None
    name = "test"
    role = _FakeRole()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(rec, "_fetch_companies", lambda kind, refresh=False: [])
    monkeypatch.setattr(rec, "_deal_counts_map", lambda refresh=False: {})
    app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_neutral_path_reaches_advertisers_handler(client):
    r = client.get("/api/sales/reconcile/producers")
    assert r.status_code == 200
    assert set(r.json()) >= {"linked", "candidates", "only_ours", "only_bitrix"}


def test_neutral_path_works_for_subroutes(client):
    """Резалось именно то, что ПОСЛЕ слова: /advertisers/deal-counts и /link."""
    assert client.get("/api/sales/reconcile/producers/deal-counts").status_code == 200


def test_direct_path_still_works(client):
    """Прямой адрес не ломаем: по нему ходят уже открытые вкладки и наши скрипты."""
    assert client.get("/api/sales/reconcile/advertisers").status_code == 200


def test_unknown_kind_still_rejected(client):
    """Подмена не должна превращать мусорный kind в валидный."""
    assert client.get("/api/sales/reconcile/producersXX").status_code == 400
