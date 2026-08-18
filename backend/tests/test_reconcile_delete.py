"""
Удаление ретайрнутых компаний Битрикса — шаг 2 склейки.

Почему это отдельный шаг, а не хвост склейки: Битрикс без транзакций и без корзины,
удаление необратимо, а ошибку в выборе главной компании видно только когда посмотришь
на результат. Между «склеили» и «удалили» обязан существовать момент, в который всё
ещё можно поправить.

Тесты покрывают ровно те решения, ценой ошибки в которых будет потерянная компания
с живыми сделками.
"""
import pytest

from app.routers import sales_reconcile as sr


@pytest.fixture
def bitrix(monkeypatch):
    """Подменяет Битрикс: список компаний, счётчики сделок и сам вызов удаления."""
    state = {
        "companies": [],
        "counts": {},
        "deleted": [],
        "fail_on": set(),      # bx_id, на которых Битрикс отвечает ошибкой
        "count_calls": [],     # для проверки, что счёт перезапрашивается
    }
    monkeypatch.setattr(sr, "_fetch_companies", lambda kind, refresh=False: state["companies"])

    def _count(cid, refresh=False):
        state["count_calls"].append((cid, refresh))
        v = state["counts"].get(cid)
        if v is None:
            raise RuntimeError("Битрикс не ответил")
        return v
    monkeypatch.setattr(sr, "_bx_deal_count", _count)

    def _delete(path):
        bx = path.rsplit("/", 1)[-1]
        if bx in state["fail_on"]:
            raise RuntimeError("Битрикс отклонил")
        state["deleted"].append(bx)
        return {"ok": True}
    monkeypatch.setattr(sr, "vibecode_delete", _delete)
    return state


def _co(bx_id, title):
    return {"id": str(bx_id), "title": title}


# ---- отбор кандидатов ----

def test_only_prefixed_companies_are_candidates(bitrix):
    """Удаляем только то, что сами пометили.

    Компания без префикса — либо не проходила склейку, либо её переименовали обратно
    вручную. В обоих случаях это чужой объект, и трогать его нельзя.
    """
    bitrix["companies"] = [_co(1, "XXX_Старое агентство"), _co(2, "OKKAM | Оккам"), _co(3, "Realweb")]
    bitrix["counts"] = {"1": 0, "2": 0, "3": 0}
    got = sr._retired_candidates("agencies")
    assert [x["bx_id"] for x in got] == ["1"]


def test_candidate_count_is_always_refetched(bitrix):
    """Счётчик берётся мимо кэша: между предпросмотром и нажатием кнопки сделку
    могли привязать заново, а кэш живёт пять минут."""
    bitrix["companies"] = [_co(1, "XXX_A")]
    bitrix["counts"] = {"1": 0}
    sr._retired_candidates("agencies")
    assert bitrix["count_calls"] == [("1", True)]


def test_unreachable_count_is_not_zero(bitrix):
    """Битрикс не ответил — это «неизвестно», а не «сделок ноль».

    Молчаливое приравнивание одного к другому стоило бы удалённой компании со сделками.
    """
    bitrix["companies"] = [_co(1, "XXX_A")]
    bitrix["counts"] = {}          # ответа нет
    got = sr._retired_candidates("agencies")
    assert got[0]["deal_count"] is None


# ---- само удаление ----

def test_deletes_only_empty_companies(bitrix, monkeypatch):
    bitrix["companies"] = [_co(1, "XXX_Пустая"), _co(2, "XXX_Со сделками")]
    bitrix["counts"] = {"1": 0, "2": 4}
    monkeypatch.setattr(sr, "log_action", lambda *a, **k: None)
    res = sr.retired_delete("agencies", db=_FakeDb(), current_user=None)
    assert bitrix["deleted"] == ["1"]
    assert [x["bx_id"] for x in res["skipped"]] == ["2"]


def test_skipped_company_says_why(bitrix, monkeypatch):
    """Пропуск обязан быть назван. Молча пропустить — значит дать оператору решить,
    что всё удалилось, и оставить мусор незамеченным."""
    bitrix["companies"] = [_co(2, "XXX_Со сделками")]
    bitrix["counts"] = {"2": 4}
    monkeypatch.setattr(sr, "log_action", lambda *a, **k: None)
    res = sr.retired_delete("agencies", db=_FakeDb(), current_user=None)
    assert res["deleted"] == []
    assert "сделки" in res["skipped"][0]["reason"]


def test_bitrix_refusal_does_not_stop_the_rest(bitrix, monkeypatch):
    """Одна упавшая компания не должна прерывать проход: иначе половина мусора
    останется, а оператор увидит только ошибку."""
    bitrix["companies"] = [_co(1, "XXX_A"), _co(2, "XXX_B"), _co(3, "XXX_C")]
    bitrix["counts"] = {"1": 0, "2": 0, "3": 0}
    bitrix["fail_on"] = {"2"}
    monkeypatch.setattr(sr, "log_action", lambda *a, **k: None)
    res = sr.retired_delete("agencies", db=_FakeDb(), current_user=None)
    assert bitrix["deleted"] == ["1", "3"]
    assert [x["bx_id"] for x in res["skipped"]] == ["2"]


def test_backup_is_written_before_deleting(bitrix, monkeypatch, tmp_path):
    """Имя и id удалённой компании — единственное, что от неё останется."""
    import json
    monkeypatch.setattr(sr, "CONSOLIDATE_BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(sr, "log_action", lambda *a, **k: None)
    bitrix["companies"] = [_co(7, "XXX_Исчезающая")]
    bitrix["counts"] = {"7": 0}
    res = sr.retired_delete("agencies", db=_FakeDb(), current_user=None)
    saved = json.loads(open(res["backup"], encoding="utf-8").read())
    assert saved["items"][0]["title"] == "XXX_Исчезающая"


def test_preview_splits_deletable_and_blocked(bitrix):
    bitrix["companies"] = [_co(1, "XXX_A"), _co(2, "XXX_B")]
    bitrix["counts"] = {"1": 0, "2": 3}
    res = sr.retired_preview("agencies")
    assert [x["bx_id"] for x in res["deletable"]] == ["1"]
    assert [x["bx_id"] for x in res["blocked"]] == ["2"]


class _FakeDb:
    """Достаточно для retired_delete: он пишет только в аудит, который замокан."""
    def add(self, *a, **k): pass
    def flush(self): pass
    def commit(self): pass
