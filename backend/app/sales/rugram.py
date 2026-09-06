# -*- coding: utf-8 -*-
"""Родительный падеж для шапки документа: «в лице Генерального директора Макарова
Дениса Сергеевича».

Зачем отдельный модуль, а не библиотека: pymorphy2 тянет словарь на десятки мегабайт и
пересборку образа ради двух конструкций — должности и ФИО. Обе устроены регулярно, и
правила ниже покрывают то, что реально лежит в справочнике.

Главное правило модуля: **не угадывать**. Слово, не подошедшее ни под одно правило,
возвращается КАК ЕСТЬ. В документе останется именительный падеж — это видно глазами при
вычитке, в отличие от выдуманного окончания, которое выглядит правдоподобно и потому
уезжает в подпись.
"""
from typing import Optional

# ── должность ────────────────────────────────────────────────────────────────

# Прилагательное в должности: «Генеральный директор» → «Генерального директора».
_ADJ_M = (("ый", "ого"), ("ий", "его"), ("ой", "ого"))
# «-кий/-гий/-хий» после заднеязычной дают «-кого», а не «-кего»: «Коммерческий».
_ADJ_HARD_STEM = ("к", "г", "х")

# Существительные-должности: мужской род на согласный → +а/я.
_SOFT_END = ("ь", "й")

# Слова, которые в должности не склоняются: аббревиатуры и латиница.
def _is_word(s: str) -> bool:
    return any(ch.isalpha() for ch in s)


def _same_case(src: str, out: str) -> str:
    """Сохранить регистр первой буквы: «Генеральный» → «Генерального»."""
    return out[:1].upper() + out[1:] if src[:1].isupper() else out


def gen_word(w: str) -> str:
    """Одно слово должности в родительном падеже."""
    if not _is_word(w) or w.isupper():        # аббревиатура — не трогаем
        return w
    low = w.lower()
    for end, repl in _ADJ_M:
        if low.endswith(end) and len(low) > 3:
            stem = low[:-2]
            if end == "ий" and stem[-1:] in _ADJ_HARD_STEM:
                repl = "ого"
            return _same_case(w, stem + repl)
    if low.endswith("ая"):                    # «Генеральная» → «Генеральной»
        return _same_case(w, low[:-2] + "ой")
    if low.endswith("а"):                     # «глава» → «главы»
        return _same_case(w, low[:-1] + _a_end(low[:-1]))
    if low.endswith(_SOFT_END):               # «руководитель» → «руководителя»
        return _same_case(w, low[:-1] + "я")
    if low[-1:].isalpha() and low[-1] not in "аеёиоуыэюя":
        return _same_case(w, low + "а")       # «директор» → «директора»
    return w


def gen_position(pos: Optional[str]) -> Optional[str]:
    """Должность целиком: «Генеральный директор» → «Генерального директора».

    Предлоги и слова после них не склоняются: «директор по развитию» остаётся
    «директора по развитию», а не «директора по развития».
    """
    if not pos or not pos.strip():
        return pos
    stop = False
    out = []
    for w in pos.split():
        if stop or w.lower() in ("по", "в", "на", "при", "и"):
            stop = stop or w.lower() in ("по", "в", "на", "при")
            out.append(w)
            continue
        out.append(gen_word(w))
    return " ".join(out)


# ── ФИО ──────────────────────────────────────────────────────────────────────

# После заднеязычных и шипящих пишется «и», а не «ы»: «Ольга» → «Ольги», «Лука» → «Луки».
_HUSH = "гкхжчшщ"


def _a_end(stem: str) -> str:
    return "и" if stem[-1:].lower() in _HUSH else "ы"


def _is_female(parts: list) -> bool:
    """Пол определяется по отчеству, а не по имени: «Женя» и «Саша» ничего не говорят."""
    return len(parts) > 2 and parts[2].lower().endswith(("вна", "чна", "нична"))


def _gen_surname(s: str, female: bool) -> str:
    low = s.lower()
    if low.endswith(("ых", "их", "ко", "енко", "ово", "аго", "яго")):
        return s                                   # несклоняемые
    if female:
        if low.endswith(("ова", "ева", "ёва", "ина", "ына")):
            return s[:-1] + "ой"
        if low.endswith(("ская", "цкая", "ая")):
            return s[:-2] + "ой"
        if low.endswith("а"):
            return s[:-1] + _a_end(s[:-1])         # «Глинка» → «Глинки», не «Глинкой»
        return s                                   # женская на согласный не склоняется
    if low.endswith(("ов", "ев", "ёв", "ин", "ын")):
        return s + "а"
    if low.endswith(("ский", "цкий", "ний")):
        return s[:-2] + "ого"
    if low.endswith(("ый", "ой")):
        return s[:-2] + "ого"                      # Толстой → Толстого
    if low.endswith("ий"):
        return s[:-2] + "его"
    if low.endswith("а"):
        return s[:-1] + _a_end(s[:-1])
    if low.endswith("я"):
        return s[:-1] + "и"
    if low.endswith(("й", "ь")):
        return s[:-1] + "я"
    if low[-1:].isalpha() and low[-1] not in "аеёиоуыэюя":
        return s + "а"
    return s


# Беглая гласная правилом не выводится: «Павел» → «Павла», а не «Павела». Список, а не
# алгоритм — таких имён считанные единицы, и каждое нужно знать в лицо.
_GIVEN_EXC = {"павел": "Павла", "пётр": "Петра", "петр": "Петра", "лев": "Льва"}


def _gen_given(s: str, female: bool) -> str:
    low = s.lower()
    if not female and low in _GIVEN_EXC:
        return _GIVEN_EXC[low]
    if female:
        if low.endswith("ия"):
            return s[:-1] + "и"                    # Мария → Марии
        if low.endswith("ья"):
            return s[:-1] + "и"                    # Наталья → Натальи
        if low.endswith("а"):
            return s[:-1] + _a_end(s[:-1])         # Анна → Анны, Ольга → Ольги
        if low.endswith("я"):
            return s[:-1] + "и"                    # Ксения → Ксении
        if low.endswith("ь"):
            return s[:-1] + "и"                    # Любовь → Любови
        return s
    if low.endswith("ия"):
        return s[:-1] + "и"
    if low.endswith("я"):
        return s[:-1] + "и"                        # Илья → Ильи
    if low.endswith("а"):
        return s[:-1] + _a_end(s[:-1])             # Никита → Никиты, Лука → Луки
    if low.endswith(("й", "ь")):
        return s[:-1] + "я"                        # Сергей → Сергея, Игорь → Игоря
    if low[-1:].isalpha() and low[-1] not in "аеёиоуыэюя":
        return s + "а"                             # Денис → Дениса
    return s


def _gen_patronymic(s: str, female: bool) -> str:
    low = s.lower()
    if female and low.endswith("на"):
        return s[:-1] + "ы"                        # Сергеевна → Сергеевны
    if not female and low.endswith(("ич", "ыч")):
        return s + "а"                             # Сергеевич → Сергеевича
    return s


def gen_fio(full: Optional[str]) -> Optional[str]:
    """ФИО в родительном падеже: «Макаров Денис Сергеевич» → «Макарова Дениса Сергеевича».

    Порядок частей — как в справочнике: Фамилия Имя Отчество. Одно слово считается
    фамилией.
    """
    if not full or not full.strip():
        return full
    parts = full.split()
    female = _is_female(parts)
    out = [_gen_surname(parts[0], female)]
    if len(parts) > 1:
        out.append(_gen_given(parts[1], female))
    if len(parts) > 2:
        out.append(_gen_patronymic(parts[2], female))
    out.extend(parts[3:])
    return " ".join(out)


# ── основание полномочий и согласование ──────────────────────────────────────

# «действующего на основании Устава» — оборот требует родительного падежа и от
# основания тоже. В справочнике его пишут и так и так: «Устав» и «Устава» встречаются
# у разных контрагентов. Склоняются только два известных слова; всё остальное —
# доверенности с номерами, уставы иностранных юрлиц — остаётся как ввели.
_BASIS = {"устав": "Устава", "устава": "Устава",
          "доверенность": "Доверенности", "доверенности": "Доверенности"}


def gen_basis(basis: Optional[str]) -> Optional[str]:
    """«Устав» → «Устава», «Доверенность № 5 от 01.01.2026» → «Доверенности № 5 …»."""
    if not basis or not basis.strip():
        return basis
    words = basis.split()
    head = _BASIS.get(words[0].lower().strip(",."))
    if not head:
        return basis
    return " ".join([head] + words[1:])


def acting(full: Optional[str]) -> str:
    """«действующего» или «действующей» — по полу подписанта.

    Причастие согласуется с ФИО, и «Ивановой Марии Петровны, действующего» — ошибка,
    которую в документе видно сразу, а в коде не видно вовсе.
    """
    parts = (full or "").split()
    return "действующей" if _is_female(parts) else "действующего"
