"""
Тесты хеша полезной нагрузки (append-only слой сырья не должен плодить версии
при неизменных данных).

Тесты правил синхронизации с Битриксом удалены 03.10.2026 вместе с правилами —
Битрикс больше не источник.
"""
from app.sales.sync import payload_hash


def test_payload_hash_is_stable_regardless_of_key_order():
    """Иначе каждая синхронизация плодила бы версии на ровном месте."""
    assert payload_hash({"a": 1, "b": 2}) == payload_hash({"b": 2, "a": 1})


def test_payload_hash_changes_when_value_changes():
    assert payload_hash({"amount": "100"}) != payload_hash({"amount": "101"})
