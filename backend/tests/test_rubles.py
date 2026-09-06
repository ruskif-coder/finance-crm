# -*- coding: utf-8 -*-
"""Сумма прописью: пропись обязана совпадать с цифрой.

Это не косметика. В приложении к договору пропись — юридически значимый текст: при
расхождении цифры и слов силу имеют слова. Ошибка здесь не падает, не подсвечивается и
всплывает у клиента на подписании.

Эталон — живой документ «Приложение № 68» от 01.06.2026: 732 000 (Семьсот тридцать две
тысячи) рублей 00 копеек, в том числе НДС 22 % — 132 000 (Сто тридцать две тысячи).
"""
import pytest

from app.sales.rubles import in_words, plural, rub_phrase, split_kopecks, vat_of


def test_sample_document_matches_word_for_word():
    """Обе суммы из образца — буква в букву.

    Разряды разделены НЕРАЗРЫВНЫМ пробелом ( ), и это осознанно: в документе
    «732 000» не должно разорваться переносом строки на «732» и «000». Проверяем явно,
    чтобы никто не «починил» его на обычный пробел, не зная зачем он такой.
    """
    NB = " "
    assert rub_phrase(732000) == f"732{NB}000 (Семьсот тридцать две тысячи) рублей 00 копеек"
    assert rub_phrase(132000) == f"132{NB}000 (Сто тридцать две тысячи) рублей 00 копеек"


def test_vat_is_extracted_from_the_gross_not_added_to_it():
    """22 % от 732 000 это 161 040, а в документе стоит 132 000.

    Налог ВЫДЕЛЯЕТСЯ из суммы с налогом, а не начисляется сверху. Перепутать эти две
    операции — самая дорогая ошибка в документе: разница уходит в цену.
    """
    assert vat_of(732000, 22) == 132000.0
    assert vat_of(732000, 22) != round(732000 * 0.22, 2)
    assert vat_of(120000, 20) == 20000.0
    assert vat_of(0, 22) == 0.0 and vat_of(100, 0) == 0.0


def test_gender_of_thousands_and_millions():
    """Тысяча женского рода, миллион мужского. «Два тысячи» и «одна миллион» — самая
    частая ошибка самописных функций."""
    assert in_words(1000) == "одна тысяча"
    assert in_words(2000) == "две тысячи"
    assert in_words(5000) == "пять тысяч"
    assert in_words(21000) == "двадцать одна тысяча"
    assert in_words(1000000) == "один миллион"
    assert in_words(2000000) == "два миллиона"
    assert in_words(5000000) == "пять миллионов"


def test_teens_are_not_built_from_tens_and_ones():
    """11–19 — отдельные слова, а не «десять один»."""
    assert in_words(11) == "одиннадцать"
    assert in_words(14) == "четырнадцать"
    assert in_words(19) == "девятнадцать"
    assert in_words(111) == "сто одиннадцать"


def test_plural_rule_covers_the_eleven_trap():
    """11–14 всегда третья форма, хотя кончаются на 1–4: «одиннадцать рублей», а не
    «одиннадцать рубль»."""
    forms = ("рубль", "рубля", "рублей")
    assert plural(1, forms) == "рубль"
    assert plural(11, forms) == "рублей"
    assert plural(21, forms) == "рубль"
    assert plural(112, forms) == "рублей"
    assert plural(122, forms) == "рубля"
    assert plural(5, forms) == "рублей"
    assert plural(0, forms) == "рублей"


def test_kopecks_are_digits_and_always_two_places():
    """В образце «00 копеек». Одна цифра («0 копеек») в документе выглядит опечаткой."""
    assert rub_phrase(1500.5).endswith("50 копеек")
    assert rub_phrase(1500.05).endswith("05 копеек")
    assert rub_phrase(1500).endswith("00 копеек")
    assert split_kopecks(1500.5) == (1500, 50)
    assert split_kopecks(0.99) == (0, 99)


def test_zero_and_small_amounts_do_not_produce_empty_words():
    """Пустая пропись в документе хуже нуля: она читается как незаполненное поле."""
    assert rub_phrase(0) == "0 (Ноль) рублей 00 копеек"
    assert rub_phrase(1) == "1 (Один) рубль 00 копеек"
    assert rub_phrase(2) == "2 (Два) рубля 00 копеек"


def test_gaps_inside_the_number_are_not_swallowed():
    """1 000 005 — миллион и пять, без «тысяч» посередине. Пропуск разряда — классика
    самописных прописей."""
    assert in_words(1000005) == "один миллион пять"
    assert in_words(1000500) == "один миллион пятьсот"
    assert in_words(2000001) == "два миллиона один"


@pytest.mark.parametrize("n", [7, 42, 100, 999, 1001, 12345, 999999, 1234567, 90000000])
def test_words_never_come_out_empty_or_double_spaced(n):
    """Прибор от разметки: лишние пробелы попадают прямо в документ."""
    w = in_words(n)
    assert w and "  " not in w and w == w.strip()
