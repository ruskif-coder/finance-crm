"""
Пакетный импорт компаний Битрикса к нам — третья колонка сверки.

У рекламодателей в «только в Битриксе» 220 компаний; по одной это неподъёмно.
В Битрикс импорт не пишет ничего — заводит наши записи и связи.

Отказы здесь штатные, а не аварийные: «запись с таким названием уже есть»
означает, что компанию надо СВЯЗАТЬ, а не заводить дублем. Если такие причины
не назвать поимённо, оператор увидит «заведено 180» и не заметит, что сорок
компаний требуют другого действия.
"""
import pytest
from fastapi import HTTPException

from app.routers import sales_reconcile as sr


class _FakeDb:
    def __init__(self):
        self.rolled_back = 0

    def rollback(self):
        self.rolled_back += 1


@pytest.fixture
def importer(monkeypatch):
    state = {"imported": [], "fail": {}, "companies": []}
    monkeypatch.setattr(sr, "_fetch_companies", lambda kind, refresh=False: state["companies"])
    monkeypatch.setattr(sr, "log_action", lambda *a, **k: None)

    def _do(db, model, kind, data, current_user):
        if data.bx_id in state["fail"]:
            raise HTTPException(status_code=409, detail=state["fail"][data.bx_id])
        state["imported"].append(data.bx_id)
        return {"ok": True, "id": 900 + int(data.bx_id)}
    monkeypatch.setattr(sr, "_do_import", _do)
    return state


def _co(bx_id, title):
    return {"id": str(bx_id), "title": title}


def test_all_selected_are_imported(importer):
    importer["companies"] = [_co(10, "Ромашка"), _co(20, "Лютик")]
    res = sr.import_many("agencies", sr.ImportManyIn(bx_ids=["10", "20"]),
                         db=_FakeDb(), current_user=None)
    assert importer["imported"] == ["10", "20"]
    assert [d["name"] for d in res["done"]] == ["Ромашка", "Лютик"]
    assert res["failed"] == []


def test_existing_record_is_reported_not_swallowed(importer):
    """«Такая запись уже есть» — сигнал связать, а не завести. Его нельзя терять."""
    importer["companies"] = [_co(10, "Ромашка"), _co(20, "Лютик")]
    importer["fail"] = {"20": "Запись «Лютик» уже есть — свяжите её, а не импортируйте"}
    res = sr.import_many("agencies", sr.ImportManyIn(bx_ids=["10", "20"]),
                         db=_FakeDb(), current_user=None)
    assert [d["name"] for d in res["done"]] == ["Ромашка"]
    assert res["failed"][0]["name"] == "Лютик"
    assert "свяжите" in res["failed"][0]["error"]


def test_failure_does_not_stop_the_rest(importer):
    importer["companies"] = [_co(10, "А"), _co(20, "Б"), _co(30, "В")]
    importer["fail"] = {"20": "Эта компания уже привязана"}
    db = _FakeDb()
    res = sr.import_many("agencies", sr.ImportManyIn(bx_ids=["10", "20", "30"]),
                         db=db, current_user=None)
    assert importer["imported"] == ["10", "30"]
    assert [f["name"] for f in res["failed"]] == ["Б"]
    assert db.rolled_back == 1


def test_company_missing_from_bitrix_list_is_named_by_id(importer):
    """Компании нет в списке — запись всё равно попадает в отчёт под своим id."""
    importer["companies"] = []
    importer["fail"] = {"77": "Компания не найдена в Битриксе"}
    res = sr.import_many("agencies", sr.ImportManyIn(bx_ids=["77"]),
                         db=_FakeDb(), current_user=None)
    assert res["failed"][0]["name"] == "#77"


def test_bitrix_is_not_touched():
    """Импорт заводит записи у нас. Запись в Битрикс здесь означала бы, что кнопка
    делает больше, чем обещает её название."""
    import inspect
    src = inspect.getsource(sr.import_many) + inspect.getsource(sr._do_import)
    for call in ("vibecode_post", "vibecode_patch", "vibecode_delete"):
        assert call not in src, f"{call} в импорте — он не должен писать в Битрикс"
