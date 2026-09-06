# -*- coding: utf-8 -*-
"""Родительный падеж в шапке документа.

Ошибка здесь не падает и не видна в коде — она видна клиенту в подписанном документе
(«в лице Генеральный директор Макаров Денис Сергеевич»). Поэтому проверяются не
внутренности правил, а сами строки, которые попадут в бумагу.
"""
from app.sales.rugram import gen_fio, gen_position


def test_positions_of_our_directory():
    """Должности, реально встречающиеся в справочнике контрагентов."""
    assert gen_position("Генеральный директор") == "Генерального директора"
    assert gen_position("Директор") == "Директора"
    assert gen_position("Коммерческий директор") == "Коммерческого директора"
    assert gen_position("Индивидуальный предприниматель") == "Индивидуального предпринимателя"
    assert gen_position("Управляющий") == "Управляющего"
    assert gen_position("Президент") == "Президента"
    assert gen_position("Главный бухгалтер") == "Главного бухгалтера"


def test_preposition_stops_the_declension():
    """«Директор по развитию»: склоняется только то, что до предлога. Иначе вышло бы
    «директора по развития» — фраза, которую человек прочитает как опечатку."""
    assert gen_position("Директор по развитию") == "Директора по развитию"


def test_our_own_signers():
    """Подписанты, которые стоят в живых документах прямо сейчас."""
    assert gen_fio("Макаров Денис Сергеевич") == "Макарова Дениса Сергеевича"
    assert gen_fio("Титченко Максим Витальевич") == "Титченко Максима Витальевича"


def test_indeclinable_surnames_are_left_alone():
    """Фамилии на -ко, -ых, -их не склоняются. Приписать им окончание — выдумать
    человеку другую фамилию."""
    assert gen_fio("Титченко Иван Иванович").split()[0] == "Титченко"
    assert gen_fio("Черных Иван Иванович").split()[0] == "Черных"


def test_female_is_detected_by_patronymic_not_by_name():
    """«Женя» и «Саша» о поле не говорят, отчество — говорит."""
    assert gen_fio("Иванова Мария Петровна") == "Ивановой Марии Петровны"
    assert gen_fio("Иванова Женя Петровна") == "Ивановой Жени Петровны"


def test_adjectival_surnames():
    assert gen_fio("Достоевский Фёдор Михайлович") == "Достоевского Фёдора Михайловича"
    assert gen_fio("Толстой Лев Николаевич") == "Толстого Льва Николаевича"


def test_fluent_vowel_is_a_list_not_a_rule():
    """«Павел» → «Павла». Правилом это не выводится, и «Павела» выглядит правдоподобно —
    ровно поэтому такие имена перечислены поимённо."""
    assert gen_fio("Кинчиков Павел Сергеевич") == "Кинчикова Павла Сергеевича"
    assert gen_fio("Смирнов Пётр Львович") == "Смирнова Петра Львовича"


def test_spelling_rule_after_velars():
    """После г/к/х пишется «и», а не «ы»: «Ольга» → «Ольги»."""
    assert gen_fio("Ким Ольга Сергеевна") == "Ким Ольги Сергеевны"
    assert gen_fio("Сковорода Лука Петрович") == "Сковороды Луки Петровича"


def test_unknown_input_is_returned_unchanged_not_guessed():
    """Молчаливое «как есть» — сознательный выбор: именительный падеж в документе видно
    глазами, выдуманное окончание — нет."""
    assert gen_position(None) is None and gen_fio(None) is None
    assert gen_position("") == "" and gen_fio("") == ""
    assert gen_fio("Ли") == "Ли"
    assert gen_position("ООО") == "ООО"


def test_party_carries_both_cases(monkeypatch):
    """Шапка и подписи берут ОДНО поле в двух падежах, а не два разных поля."""
    from types import SimpleNamespace
    from app.sales import annex
    cp = SimpleNamespace(id=1, name="ООО Ромашка", inn="1", kpp=None, address=None,
                         director_name="Макаров Денис Сергеевич",
                         signer_position="Генеральный директор", signer_basis="Устава")
    out = annex.party(cp)
    assert out["position"] == "Генеральный директор"
    assert out["position_gen"] == "Генерального директора"
    assert out["director_gen"] == "Макарова Дениса Сергеевича"
    assert out["short_fio"] == "Макаров Д.С."
