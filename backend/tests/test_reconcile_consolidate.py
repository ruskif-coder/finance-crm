"""
Склейка компаний Битрикса — шаг 1 сверки: переброс сделок на якорь, переименование
якоря под наш стандарт, пометка лишних как «XXX_старое имя».

Тестов не было вовсе, хотя это самая разрушительная операция сценария: она правит
чужую систему без транзакций и без корзины. У шага 2 (удаления) тестов восемь, у
шага 1 — ноль; покрыт был самый осторожный шаг и не покрыт самый опасный.

Покрываем ровно те решения, ценой ошибки в которых будет сделка, уехавшая не туда,
или компания, переименованная до того, как стало ясно, что переезд вообще возможен.
"""
import pytest
from fastapi import HTTPException

from app.routers import sales_reconcile as sr


class _FakeQuery:
    def __init__(self, sink):
        self.sink = sink

    def filter(self, *a, **k):
        return self

    def delete(self, synchronize_session=False):
        self.sink.append("links_deleted")
        return 0


class _FakeDb:
    """Достаточно для consolidate: он снимает лишние связи и коммитит."""
    def __init__(self):
        self.calls = []

    def query(self, *a, **k):
        return _FakeQuery(self.calls)

    def add(self, *a, **k):
        pass

    def flush(self):
        self.calls.append("flush")

    def commit(self):
        self.calls.append("commit")


@pytest.fixture
def bitrix(monkeypatch, tmp_path):
    """Подменяет Битрикс и справочник: запись, привязки, компании, сделки, запись."""
    state = {
        "companies": [],
        "row": {"short_name": "MI", "name": "MI", "name_en": "Media Instinct",
                "name_ru": "Медиа инстинкт", "holding": None},
        "links": [],
        "deals": {},          # bx_id -> [id сделок]
        "written": [],        # ("deal"|"company", id, значение) в порядке вызова
        "fail_on_path": None,  # путь, на котором Битрикс отвечает ошибкой
    }
    monkeypatch.setattr(sr, "CONSOLIDATE_BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(sr, "log_action", lambda *a, **k: None)
    monkeypatch.setattr(sr, "_sync_primary", lambda *a, **k: None)
    monkeypatch.setattr(sr, "_fetch_companies", lambda kind, refresh=False: state["companies"])
    monkeypatch.setattr(sr, "_record_and_links",
                        lambda db, model, kind, our_id: (None, state["row"], state["links"]))
    monkeypatch.setattr(sr, "list_deal_ids_for_company",
                        lambda cid: list(state["deals"].get(str(cid), [])))

    def _patch(path, body):
        if state["fail_on_path"] and path == state["fail_on_path"]:
            raise RuntimeError("Битрикс отклонил")
        if path.startswith("/deals/"):
            state["written"].append(("deal", path.rsplit("/", 1)[-1], body.get("companyId")))
        else:
            state["written"].append(("company", path.rsplit("/", 1)[-1], body.get("title")))
        return {"success": True}
    monkeypatch.setattr(sr, "vibecode_patch", _patch)
    return state


def _co(bx_id, title):
    return {"id": str(bx_id), "title": title}


def _run(state, primary="10"):
    return sr.consolidate("agencies", sr.ConsolidateIn(our_id=1, primary_bx_id=primary),
                          db=_FakeDb(), current_user=None)


# ---- что вообще разрешено склеивать ----

def test_primary_must_be_among_links(bitrix):
    """Якорь не из привязок записи — это чужая компания. Переброс сделок на неё
    увёл бы их в другое агентство, и заметить это было бы уже поздно."""
    bitrix["links"] = ["10", "20"]
    bitrix["companies"] = [_co(10, "A"), _co(20, "B"), _co(30, "Чужая")]
    with pytest.raises(HTTPException) as e:
        _run(bitrix, primary="30")
    assert e.value.status_code == 400


def test_needs_at_least_two_companies(bitrix):
    """Склеивать нечего: для одной привязки есть отдельная кнопка переименования,
    и она не трогает сделки."""
    bitrix["links"] = ["10"]
    bitrix["companies"] = [_co(10, "A")]
    with pytest.raises(HTTPException) as e:
        _run(bitrix)
    assert e.value.status_code == 400


# ---- порядок записи в Битрикс ----

def test_deals_move_before_any_rename(bitrix):
    """Сначала сделки, потом имена — и это не косметика.

    Битрикс без транзакций: если сорвётся переброс, при обратном порядке компании
    уже переименованы, и оператор видит «склеенные» имена при неслеенных сделках —
    состояние, по которому невозможно понять, что произошло.
    """
    bitrix["links"] = ["10", "20"]
    bitrix["companies"] = [_co(10, "Якорь"), _co(20, "Лишняя")]
    bitrix["deals"] = {"20": ["101", "102"]}
    _run(bitrix)
    kinds = [w[0] for w in bitrix["written"]]
    assert kinds == ["deal", "deal", "company", "company"]
    assert [w[1] for w in bitrix["written"][:2]] == ["101", "102"]
    assert all(w[2] == 10 for w in bitrix["written"][:2])


def test_primary_renamed_to_standard_and_rest_marked(bitrix):
    bitrix["links"] = ["10", "20"]
    bitrix["companies"] = [_co(10, "Media Instinct Group / Уайт Бокс"), _co(20, "Media Instinct Group")]
    res = _run(bitrix)
    companies = [w for w in bitrix["written"] if w[0] == "company"]
    assert companies[0] == ("company", "10", "MI | Media Instinct | Медиа инстинкт")
    assert companies[1] == ("company", "20", "XXX_Media Instinct Group")
    assert res["retired"] == 1


def test_retired_prefix_is_not_doubled(bitrix):
    """Повторная склейка не должна плодить XXX_XXX_: префикс — признак «помечено
    к удалению», а не счётчик попыток."""
    bitrix["links"] = ["10", "20"]
    bitrix["companies"] = [_co(10, "Якорь"), _co(20, "XXX_Уже помечена")]
    _run(bitrix)
    marked = [w for w in bitrix["written"] if w[0] == "company" and w[1] == "20"]
    assert marked[0][2] == "XXX_Уже помечена"


# ---- бэкап и сбой на середине ----

def test_backup_written_before_first_write(bitrix):
    """Бэкап — единственный путь отката: id всех перебрасываемых сделок и старые
    имена компаний. Он обязан лечь на диск до первого запроса в Битрикс."""
    import json
    bitrix["links"] = ["10", "20"]
    bitrix["companies"] = [_co(10, "Якорь"), _co(20, "Лишняя")]
    bitrix["deals"] = {"20": ["101"]}
    res = _run(bitrix)
    saved = json.loads(open(res["backup"], encoding="utf-8").read())
    assert saved["primary_old_title"] == "Якорь"
    assert saved["redundant"][0]["old_title"] == "Лишняя"
    assert saved["redundant"][0]["deal_ids"] == ["101"]


def test_partial_failure_keeps_local_links_untouched(bitrix):
    """Сорвалось на середине — локальные связи не трогаем.

    Иначе у записи останется одна связь, а в Битриксе сделки будут висеть на двух
    компаниях, и повторить склейку станет нечем: лишняя компания уже отвязана.
    """
    bitrix["links"] = ["10", "20"]
    bitrix["companies"] = [_co(10, "Якорь"), _co(20, "Лишняя")]
    bitrix["deals"] = {"20": ["101"]}
    bitrix["fail_on_path"] = "/companies/10"
    db = _FakeDb()
    with pytest.raises(HTTPException) as e:
        sr.consolidate("agencies", sr.ConsolidateIn(our_id=1, primary_bx_id="10"),
                       db=db, current_user=None)
    assert e.value.status_code == 502
    assert "links_deleted" not in db.calls
    assert "переброшено 1" in e.value.detail


def test_success_drops_every_link_but_the_anchor(bitrix):
    bitrix["links"] = ["10", "20", "30"]
    bitrix["companies"] = [_co(10, "Якорь"), _co(20, "Лишняя"), _co(30, "Ещё")]
    db = _FakeDb()
    sr.consolidate("agencies", sr.ConsolidateIn(our_id=1, primary_bx_id="10"),
                   db=db, current_user=None)
    assert "links_deleted" in db.calls
    assert db.calls.index("links_deleted") < db.calls.index("commit")
