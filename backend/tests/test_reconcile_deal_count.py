"""
Счётчик сделок компании Битрикса — от него зависит защита от удаления.

Измерено на боевом Битриксе 2026-08-23: `meta.total` приходит ТОЛЬКО когда выборка
пуста. Как только на компании есть сделки, вместо total отдаются `hasMore` и
`nextAfterId`. Прежний код брал `meta.total or 0` и потому возвращал НОЛЬ для любой
непустой компании: bx 2034 с 92 сделками и bx 16 с 69 считались пустыми.

Цена ошибки — не косметическая. `retired_delete` удаляет компании, у которых
`deal_count == 0`; при всегда-нулевом счётчике защита «удаляем только пустые»
не отсекала ничего, а удаление в Битриксе необратимо.
"""
from app.routers import sales_reconcile as sr


def _no_cache():
    sr._DEAL_COUNT_CACHE.clear()


def test_absent_total_means_deals_exist_and_are_counted(monkeypatch):
    """Нет total — значит выборка непустая. Ноль здесь вернуть нельзя."""
    _no_cache()
    monkeypatch.setattr(sr, "vibecode_get",
                        lambda path, params=None: {"meta": {"hasMore": True, "nextAfterId": 5}})
    monkeypatch.setattr(sr, "list_deal_ids_for_company", lambda cid: ["1", "2", "3"])
    assert sr._bx_deal_count("2034", refresh=True) == 3


def test_zero_total_is_trusted_without_extra_request(monkeypatch):
    """Пустую компанию Битрикс называет прямо — перебирать нечего."""
    _no_cache()
    calls = []
    monkeypatch.setattr(sr, "vibecode_get",
                        lambda path, params=None: {"meta": {"total": 0, "hasMore": False}})
    monkeypatch.setattr(sr, "list_deal_ids_for_company",
                        lambda cid: calls.append(cid) or [])
    assert sr._bx_deal_count("750", refresh=True) == 0
    assert calls == [], "при total=0 перебор не нужен"


def test_explicit_total_is_used_as_is(monkeypatch):
    """Если Битрикс когда-нибудь начнёт отдавать total и для непустых — верим ему."""
    _no_cache()
    monkeypatch.setattr(sr, "vibecode_get",
                        lambda path, params=None: {"meta": {"total": 42, "hasMore": True}})
    monkeypatch.setattr(sr, "list_deal_ids_for_company",
                        lambda cid: (_ for _ in ()).throw(AssertionError("перебор не нужен")))
    assert sr._bx_deal_count("16", refresh=True) == 42


def test_count_is_cached_until_refresh(monkeypatch):
    """Кэш живёт, но refresh=True обязан перезапросить: между предпросмотром и
    удалением сделку могли привязать заново."""
    _no_cache()
    seen = {"n": 0}

    def _get(path, params=None):
        seen["n"] += 1
        return {"meta": {"total": 0}}
    monkeypatch.setattr(sr, "vibecode_get", _get)
    sr._bx_deal_count("900", refresh=True)
    sr._bx_deal_count("900")
    assert seen["n"] == 1
    sr._bx_deal_count("900", refresh=True)
    assert seen["n"] == 2
    _no_cache()
