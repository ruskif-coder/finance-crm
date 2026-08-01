import app.sales.bitrix.transport as bx


def test_list_companies_paginates_and_maps(monkeypatch):
    # Шаг пагинации = page_size (500). Ключи offset: 0 и 500.
    pages = {
        0: {"data": [{"id": 1, "title": "Alpha", "typeId": "SUPPLIER"}],
            "meta": {"total": 2, "hasMore": True}},
        500: {"data": [{"id": 2, "title": "Bravo", "typeId": "SUPPLIER"}],
              "meta": {"total": 2, "hasMore": False}},
    }
    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        return pages[params["offset"]]

    monkeypatch.setattr(bx, "vibecode_get", fake_get)
    out = bx.list_bitrix_companies("SUPPLIER")
    assert out == [{"id": "1", "title": "Alpha"}, {"id": "2", "title": "Bravo"}]
    assert calls[0][1]["filter[typeId]"] == "SUPPLIER"
    assert calls[0][1]["limit"] == 500


def test_list_companies_stops_by_total_despite_hasmore(monkeypatch):
    # Реальный баг Битрикса: meta.hasMore ВСЕГДА True. Останавливаемся по total. Шаг = 500.
    pages = {
        0: {"data": [{"id": i, "title": f"C{i}"} for i in range(500)],
            "meta": {"total": 510, "hasMore": True}},
        500: {"data": [{"id": i, "title": f"C{i}"} for i in range(500, 510)],
              "meta": {"total": 510, "hasMore": True}},  # len(out)=510>=total → конец
    }

    def fake_get(path, params=None):
        return pages[params["offset"]]

    monkeypatch.setattr(bx, "vibecode_get", fake_get)
    out = bx.list_bitrix_companies("SUPPLIER")
    assert len(out) == 510


def test_vibecode_post_calls_httpx(monkeypatch):
    captured = {}

    class R:
        def raise_for_status(self): pass
        def json(self): return {"data": {"id": 999}}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url; captured["json"] = json
        return R()

    monkeypatch.setattr(bx.httpx, "post", fake_post)
    monkeypatch.setattr(bx, "_api_key", lambda: "k")
    out = bx.vibecode_post("/deals", {"title": "x"})
    assert out["data"]["id"] == 999
    assert captured["json"] == {"title": "x"}
    assert captured["url"].endswith("/deals")


def test_list_companies_retries_transient_error(monkeypatch):
    attempts = {"n": 0}

    def flaky_get(path, params=None):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("HTTP 000")
        return {"data": [{"id": 9, "title": "Late"}], "meta": {"hasMore": False}}

    monkeypatch.setattr(bx, "vibecode_get", flaky_get)
    monkeypatch.setattr(bx.time, "sleep", lambda *_: None)
    out = bx.list_bitrix_companies("SUPPLIER")
    assert out == [{"id": "9", "title": "Late"}]
    assert attempts["n"] == 2
