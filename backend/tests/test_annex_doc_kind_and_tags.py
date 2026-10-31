# -*- coding: utf-8 -*-
"""Вид документа («Приложение» / «Доп. соглашение») и новые подстановки конструктора ДС.

Решения владельца 31.10.2026:

* у ДОГОВОРА тумблер, каким словом документ себя называет — историческое название тянется
  за договором, а не за контрагентом (у контрагента договоров может быть несколько);
* **в интерфейсе — «ДС», в тексте документа — «Доп. соглашение»**. Значит и номер внутри
  документа печатается полной формой: «Доп. соглашение № 68», а сокращение живёт только
  на наших экранах;
* формы слова — **в коде, не в настройках**: следить за ними владелец не должен;
* `{юр_название}` берётся из новой колонки справочника рекламодателей и печатается
  БУКВАЛЬНО. Прогонять его через `legal_name()` нельзя: смысл юридического названия в
  том, что оно вписано точно как в реестре, а тихая правка чужих реквизитов — ровно то,
  от чего предостерегает докстрока самого `legal_name.py`;
* рекламодателей в одном ДС может быть несколько — теги нумерованные.

Почему слово обязано быть подстановкой, а не флагом: до этой правки оно было вшито в
тексты по умолчанию, причём непоследовательно — `P1_ADDONS` называл документ
«Приложением», а `CLOSING_DEFAULT` в том же документе «Доп.соглашению». Флаг не изменил
бы ни одной такой строки, и тумблер выглядел бы сломанным.
"""
import inspect
import re

import pytest

from app.annex_tpl import check, doc_kind
from app.annex_tpl.subs import SUBS


# ── вид документа ────────────────────────────────────────────────────────────

def test_default_keeps_what_the_documents_say_today():
    """Договор без тумблера печатается как раньше — «Приложение».

    185 договоров на проде стартуют с пустой колонкой, и выкладка не должна молча
    переименовать документы по ним.
    """
    assert doc_kind.kind_of(None) == doc_kind.DEFAULT == "приложение"
    assert doc_kind.number_text(doc_kind.kind_of(None), "68") == "Приложение № 68"


def test_the_document_spells_it_out_even_though_we_say_DS():
    """Тумблер «дс»: в документе полная форма, сокращения там нет.

    Решение владельца: «в настройках можешь везде использовать ДС, а в тексте —
    Доп. соглашение». Номер печатается В ДОКУМЕНТЕ, значит он тоже полной формой.
    """
    assert doc_kind.number_text("дс", "68") == "Доп. соглашение № 68"
    forms = doc_kind.forms("дс")
    assert "ДС" not in " ".join(forms[k] for k in ("nom", "gen", "dat")), (
        'сокращение «ДС» просочилось в текст документа')


def test_the_interface_calls_it_DS():
    """А на экранах — коротко, как уже называются кнопка «ДС договора» и окно «Шаблон ДС»."""
    assert doc_kind.forms("дс")["ui"] == "ДС"
    assert doc_kind.forms("приложение")["ui"] == "Приложение"


@pytest.mark.parametrize("kind", ["приложение", "дс"])
def test_three_cases_are_declared_for_both_variants(kind):
    """Падежи заданы явно, а не склоняются на ходу.

    Слово стоит в документе в трёх падежах: «Приложение № 68» (им.), «настоящего
    Приложения» (род.), «согласно Доп. соглашению» (дат.). Вариантов всего два, поэтому
    явные формы надёжнее угадывания — `rugram.py` незнакомое намеренно не угадывает.
    """
    f = doc_kind.forms(kind)
    assert {"ui", "nom", "gen", "dat"} <= set(f)
    assert all(f[k] and f[k].strip() for k in ("ui", "nom", "gen", "dat"))
    assert f["gen"] != f["nom"] and f["dat"] != f["nom"], f


def test_an_unknown_toggle_value_falls_back_instead_of_crashing():
    """Чужое значение в колонке не роняет выгрузку документа.

    Колонка текстовая, и в неё когда-нибудь попадёт опечатка. Документ нужен как раз в
    плохую минуту — поэтому деградируем к умолчанию.
    """
    assert doc_kind.kind_of("ерунда") == doc_kind.DEFAULT


# ── подстановки ──────────────────────────────────────────────────────────────

def test_full_date_of_the_annex_is_available_as_a_tag():
    """`{дата_дс}` — полная дата. Краткая `{дата_дс_кратко}` остаётся как была."""
    assert "дата_дс" in SUBS, 'нет подстановки полной даты ДС'
    assert "дата_дс_кратко" in SUBS, 'краткая дата потерялась'
    assert re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", SUBS["дата_дс"]["sample"]), SUBS["дата_дс"]["sample"]


def test_the_word_itself_is_a_substitution_in_three_cases():
    for k in ("вид_документа", "вид_документа_род", "вид_документа_дат"):
        assert k in SUBS, f'нет подстановки {k}'


def test_legal_name_of_the_advertiser_is_a_tag_and_blocks_export_when_empty():
    """Пустое юр. название запирает выгрузку и говорит, где заполнить.

    226 рекламодателей на проде стартуют с пустой колонкой. Без этого первый же ДС
    напечатал бы пустое место в реквизитах — и подписали бы его.
    """
    assert "юр_название" in SUBS
    v = SUBS["юр_название"]
    assert v.get("empty_ok") is True and v.get("where"), v


def test_numbered_advertiser_tags_are_accepted_by_the_template_check():
    """`{юр_название_2}` и дальше проходят проверку шаблона.

    Фиксированный список тут не годится: у одного плательщика 116 рекламодателей (замер
    31.10.2026), и никакое разумное N не покрывает. Поэтому проверка понимает ОБРАЗЕЦ
    имени, а сборка подставляет то, что есть.
    """
    assert check.unknown_keys("{юр_название} и {юр_название_2} и {юр_название_7}") == []


def test_a_misspelled_numbered_tag_is_still_rejected():
    """Образец не должен превратиться в «принимаем что угодно»."""
    bad = check.unknown_keys("{юр_название_} {юр_название_x} {юр_названия_2} {юр_название_0}")
    assert set(bad) == {"юр_название_", "юр_название_x", "юр_названия_2", "юр_название_0"}, bad


def test_the_legal_name_is_printed_verbatim():
    """Юр. название приезжает из справочника БЕЗ правок.

    `legal_name()` переставляет форму вперёд и ставит кавычки («ГРИНДЕКС РУС ООО» →
    «ООО «ГРИНДЕКС РУС»»). Он нужен сторонам документа, выведенным из реестра контрагентов,
    но не здесь: юр. название вписано руками и уже готово. Поэтому берём название именно в той
    форме, которую этот модуль переписал бы, — и проверяем, что оно дошло целым.
    """
    from sqlalchemy import text as sa

    from app.annex_tpl.assemble import _legal_names
    from app.annex_tpl.legal_name import legal_name
    from app.database import SessionLocal

    RAW = "ГРИНДЕКС РУС ООО"
    assert legal_name(RAW) != RAW, "подобрать форму, которую legal_name() меняет"

    MARK = "ПРОВЕРКА-ЮРНАЗВАНИЯ-31-10"
    db, adv, deal, prev = SessionLocal(), None, None, None
    try:
        deal = db.execute(sa("SELECT id FROM sales_deals WHERE advertiser_id IS NOT NULL LIMIT 1")).scalar()
        if deal is None:
            pytest.skip("на стенде нет сделок с рекламодателем")
        prev = db.execute(sa("SELECT advertiser_id FROM sales_deals WHERE id = :d"), {"d": deal}).scalar()
        adv = db.execute(sa("INSERT INTO sales_advertisers (name, short_name, legal_name, is_active) "
                            "VALUES (:n, :n, :l, true) RETURNING id"), {"n": MARK, "l": RAW}).scalar()
        db.execute(sa("UPDATE sales_deals SET advertiser_id = :a WHERE id = :d"), {"a": adv, "d": deal})
        db.commit()
        assert _legal_names(db, [deal]) == [RAW], "юр. название переписали по дороге"
    finally:
        # Сделку возвращаем владельцу, удаляем ТОЛЬКО свою строку.
        if deal is not None and prev is not None:
            db.execute(sa("UPDATE sales_deals SET advertiser_id = :a WHERE id = :d"), {"a": prev, "d": deal})
        db.execute(sa("DELETE FROM sales_advertisers WHERE name = :n"), {"n": MARK})
        db.commit()
        db.close()


# ── гейт на буквальное слово в шаблонах ──────────────────────────────────────

def test_default_texts_no_longer_hardcode_the_word():
    """В текстах по умолчанию слова нет — только подстановка.

    Иначе тумблер не изменит ни один такой пункт, и это будет выглядеть как поломка
    тумблера, а не как недоделанный шаблон.
    """
    from app.annex_tpl import assemble

    src = inspect.getsource(assemble)
    texts = re.findall(r'^(?:CLOSING_DEFAULT|P1_ADDONS)\s*=\s*\((.*?)\)\s*$', src,
                       re.S | re.M)
    assert texts, 'тексты по умолчанию не найдены — прибор смотрит не туда'
    joined = " ".join(texts)
    for word in ("Приложени", "Доп.соглашени", "Доп. соглашени"):
        assert word not in joined, (
            f'в текстах по умолчанию осталось буквальное «{word}» — тумблер его не изменит')


# ── ручки: юр. название и тумблер доезжают до базы и не стираются ────────────

def test_saving_an_advertiser_without_the_field_does_not_erase_it():
    """Сохранение рекламодателя БЕЗ юр. названия его не стирает.

    `update_advertiser` перезаписывает остальные поля целиком. Сделай юр. название так
    же — и любой экран, который о нём не знает (справочник, «Добавить данные», карточка
    сделки), стирал бы его при каждом сохранении. Тот же дефект аудит 23.09.2026 (2.L11)
    чинил у договоров. Поэтому поле пишется только если прислано.
    """
    from sqlalchemy import text as sa

    from app.database import SessionLocal
    from app.routers.sales_directories import AdvertiserIn, update_advertiser

    MARK = "ПРОВЕРКА-СТИРАНИЯ-ЮРНАЗВАНИЯ-31-10"
    db = SessionLocal()
    try:
        adv = db.execute(sa("INSERT INTO sales_advertisers (name, short_name, legal_name, is_active) "
                            "VALUES (:n, :n, :l, true) RETURNING id"),
                         {"n": MARK, "l": "ООО «Проверка»"}).scalar()
        db.commit()
        from app.models import User
        user = db.query(User).order_by(User.id).first()   # настоящая учётка: её читает журнал
        # Экран, не знающий о юр. названии: присылает только короткое имя.
        update_advertiser(adv, AdvertiserIn(short_name=MARK), db=db, current_user=user)
        db.expire_all()
        got = db.execute(sa("SELECT legal_name FROM sales_advertisers WHERE id = :i"), {"i": adv}).scalar()
        assert got == "ООО «Проверка»", f"юр. название стёрто сохранением без поля: {got!r}"
        # А присланное — пишется, и БУКВАЛЬНО.
        update_advertiser(adv, AdvertiserIn(short_name=MARK, legal_name="  ГРИНДЕКС РУС ООО  "),
                          db=db, current_user=user)
        db.expire_all()
        got = db.execute(sa("SELECT legal_name FROM sales_advertisers WHERE id = :i"), {"i": adv}).scalar()
        assert got == "ГРИНДЕКС РУС ООО", f"юр. название переписано: {got!r}"
    finally:
        db.execute(sa("DELETE FROM sales_advertisers WHERE name = :n"), {"n": MARK})
        db.commit()
        db.close()


def test_the_toggle_is_saved_and_journaled_and_typos_are_refused():
    """Тумблер договора принимается ручкой, опечатка — отказ словом."""
    import pytest as _p
    from fastapi import HTTPException

    from app.routers.contracts import _annex_word

    assert _annex_word("дс") == "дс" and _annex_word("ДС") == "дс"
    assert _annex_word("приложение") == "приложение"
    assert _annex_word(None) is None and _annex_word("  ") is None
    with _p.raises(HTTPException):
        _annex_word("доп")

    import inspect

    from app.routers import contracts
    assert '"annex_word": "вид ДС"' in inspect.getsource(contracts), 'смена тумблера не попадёт в журнал действий'


# ── вкладка «Шаблоны»: что пересохранить ─────────────────────────────────────

def test_literal_word_notes_find_the_word_and_ignore_the_substitution():
    """Подсказка девчатам находит слово текстом и молчит там, где уже подстановка.

    Иначе список «что пересохранить» либо пропускал бы шаблоны, либо не пустел бы
    никогда — и пересохранять стало бы нечем проверить.
    """
    blocks = [
        {"id": "h", "sys": "head"},
        {"id": "a", "title": "Предмет", "text": "На условиях настоящего Приложения № {номер_дс}"},
        {"id": "b", "title": "Основание", "text": "согласно Доп.соглашению {номер_дс}"},
        {"id": "c", "title": "Уже исправлен", "text": "согласно {вид_документа_дат} {номер_дс}"},
        {"id": "t", "sys": "table"},
    ]
    notes = check.literal_word_notes(blocks)
    assert [n["id"] for n in notes] == ["a", "b"], notes
    assert check.literal_word_notes([{"id": "x", "title": "Т", "text": "{вид_документа} № 1"}]) == []


def test_template_list_tells_what_to_resave():
    """Список шаблонов отдаёт число пунктов со словом и договор — для поиска и обработки."""
    from app.database import SessionLocal
    from app.models import User
    from app.routers.annex_templates import list_templates

    db = SessionLocal()
    try:
        user = db.query(User).order_by(User.id).first()
        items = list_templates(db=db, user=user)["items"]
    finally:
        db.close()
    assert items, "на стенде нет шаблонов — проверить нечего"
    assert all("literal_words" in r for r in items), "нет счётчика «слово текстом»"
    custom = [r for r in items if r["scope"] == "custom"]
    assert all("contract_number" in r for r in custom), "у шаблона договора не видно, чей он"


# ── «синхронизировать» (владелец 31.10.2026): одно слово на весь документ ─────

# Все формы, в которых старые тексты называют документ, — из `annex_docx._DS_WORDS` и
# текстов по умолчанию. Слева то, что написано, справа — что должно стать при виде «дс».
OLD_FORMS = [
    ("настоящему Приложению", "настоящему Доп. соглашению"),       # дательный
    ("настоящим Приложением", "настоящим Доп. соглашением"),       # творительный
    ("Настоящее Приложение", "Настоящее Доп. соглашение"),         # именительный
    ("настоящего Приложения", "настоящего Доп. соглашения"),       # родительный
    ("отдельными Приложениями", "отдельными Доп. соглашениями"),   # творительный, мн.
    ("Приложение составлено", "Доп. соглашение составлено"),
]


@pytest.mark.parametrize("old,new", OLD_FORMS)
def test_every_case_of_the_old_word_follows_the_kind(old, new):
    """Каждый падеж и число старого слова переходят в вид документа.

    Работает основой, потому что «Приложение» и «Доп. соглашение» — оба среднего рода на
    -ение и склоняются одинаково. Прибор держит это допущение: появится форма, которая
    склоняется иначе, — упадёт он, а не договор.
    """
    assert doc_kind.rebrand(old, "дс") == new
    assert doc_kind.rebrand(old, "приложение") == old, "вид «приложение» текст не меняет"


def test_the_mobile_app_is_not_the_document():
    """«мобильное приложение» (еФарм · APP) — не документ, и его не переименовываем.

    Документ в текстах пишется с заглавной; услуга — со строчной. Тихо переписать
    название услуги в договоре было бы хуже, чем не переписать слово документа.
    """
    s = "размещение в мобильном приложении и в приложении Купера"
    assert doc_kind.rebrand(s, "дс") == s


def test_toggle_wins_then_master_deal_then_default():
    """Вид: явный → тумблер договора → у мастер-сделки «дс» → «приложение».

    Мастер-сделка по умолчанию — доп. соглашение: решение владельца 15.10.2026 («ДС
    мастер-сделки называются ДС») остаётся в силе, пока тумблер договора не сказал иное.
    Без этого правки «синхронизировать» все пакеты молча стали бы «Приложением».
    """
    assert doc_kind.resolve() == "приложение"
    assert doc_kind.resolve(is_master=True) == "дс"
    assert doc_kind.resolve(contract_word="приложение", is_master=True) == "приложение", "тумблер договора важнее"
    assert doc_kind.resolve(explicit="дс", contract_word="приложение") == "дс", "зафиксированное при выпуске важнее"
    assert doc_kind.resolve(contract_word="опечатка", is_master=True) == "дс", "незнакомое — как не заданное"


@pytest.mark.parametrize("kind,number,dative", [
    ("дс", "Доп. соглашение № 7", "Доп. соглашению № 7"),
    ("приложение", "Приложение № 7", "Приложению № 7"),
    ("дс", "Доп. соглашение № 7-01", "Доп. соглашению № 7-01"),
])
def test_dative_of_the_number(kind, number, dative):
    """«К Доп. соглашению № 7 к Договору» — дательный от вида, а не заменой строки.

    `annex_docx` переводил в дательный заменой «Приложение» → «Приложению». Пока номер
    мастер-сделки был «ДС № N», падежу не за что было зацепиться. С полной формой
    вышло бы «К Доп. соглашение № 7» — неверный падеж в юридическом документе.
    """
    assert doc_kind.to_dative(number, kind) == dative


def test_a_numbered_legal_name_without_an_advertiser_is_empty_not_printed_raw():
    """`{юр_название_2}` в шаблоне, а рекламодатель в ДС один: подставить нечего (ревью 31.10.2026).

    Раньше тег считался «незнакомым» и печатался буквально, с фигурными скобками, а подтверждение
    его не останавливало — документ уходил клиенту с «{юр_название_2}». Теперь это пустое поле:
    в тексте пусто, в списке недостающего — объяснение, что сделать.
    """
    from app.annex_tpl.assemble import _missing, _parts

    parts = _parts("Рекламодатели: {юр_название}, {юр_название_2}.", {"юр_название": "ООО «Альфа»"})
    second = next(p for p in parts if p.get("key") == "юр_название_2")
    assert second["t"] == "" and second.get("empty") and not second.get("unknown")

    miss = _missing({"юр_название_2": True}, {"missing": []}, {"missing": []}, [{"amount": 1}], "бренд")
    assert len(miss) == 1 and "2" in miss[0]["text"] and "рекламодател" in miss[0]["where"]


def test_a_truly_unknown_tag_is_still_marked_unknown():
    from app.annex_tpl.assemble import _parts
    p = next(x for x in _parts("{неизвестный_тег}", {}) if x.get("key"))
    assert p.get("unknown") and p["t"] == "{неизвестный_тег}"
