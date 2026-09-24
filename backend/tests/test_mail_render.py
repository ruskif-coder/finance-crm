# -*- coding: utf-8 -*-
"""Письмо уведомления: карточка вместо трёх строк.

Проверяется не вёрстка, а то, что ломается молча и обнаруживается у получателя:
разметка, съеденная почтовым клиентом, и чужой текст, попавший в неё без экранирования.
"""
import re

from app.mail import render


def test_nothing_load_bearing_lives_in_the_style_block():
    """`<style>` в письме есть, но письмо без него не ломается.

    Часть клиентов вырезает блок целиком, и это ТИХАЯ деградация — письмо приходит без
    цветов, а мы об этом не узнаем. Поэтому в блоке только сбросы и мобильные правила:
    каждый цвет, отступ и размер написан инлайном в атрибуте. И никаких `var(--x)` —
    переменные в почте не работают нигде.
    """
    html = render.notification_html(title="Заголовок", body="Текст", tone="warn",
                                    link_abs="https://x.ru/a")
    # правило для ссылок — единственный цвет в блоке, и оно только подстраховка:
    # у каждой ссылки письма цвет написан в атрибуте
    block = html[html.index(chr(60)+chr(115)+chr(116)+chr(121)+chr(108)+chr(101)+chr(62)) + 7:html.index(chr(60)+chr(47)+chr(115)+chr(116)+chr(121)+chr(108)+chr(101)+chr(62))]
    block = block.replace('a{color:' + render.ACCENT + ';text-decoration:none}', '')
    assert 'var(--' not in html
    assert 'flex' not in html, 'flex в почте не работает — раскладка таблицами'
    for tone_colors in render.PILLS.values():
        for c in tone_colors[:3]:
            assert c not in block, f'цвет {c} держится стилем, а не атрибутом'
    assert 'padding:' not in block or '!important' in block,         'в блоке появилась раскладка, которой нет в атрибутах'


def test_layout_is_tables_with_fixed_width():
    """600px и таблицы: Outlook рисует движком Word, процентная ширина у него едет."""
    html = render.notification_html(title="Заголовок", body=None, link_abs=None)
    assert 'width="600"' in html
    assert html.count("<table") >= 3


def test_user_text_is_escaped():
    """Имя сделки и комментарий пишут люди. Угловая скобка в комментарии не должна
    ломать разметку письма — а ломается она у ПОЛУЧАТЕЛЯ, и мы об этом не узнаем."""
    html = render.notification_html(
        title='Сделка <b>жирная</b> & "кавычки"',
        body="комментарий с <script>alert(1)</script>", link_abs=None)
    assert "<script>" not in html
    assert "<b>жирная</b>" not in html
    assert "&lt;script&gt;" in html


def test_newlines_survive_in_the_body():
    """Комментарий в несколько строк остаётся многострочным: в HTML перенос — `<br>`,
    иначе абзацы слипаются в один."""
    html = render.notification_html(title="Т", body="первая\nвторая", link_abs=None)
    assert "первая<br>вторая" in html


def test_card_stays_neutral_at_every_tone():
    """Подложка и рамка карточки НЕ красятся тоном.

    Это и есть спокойная схема. Прошлая редакция красила фон, рамку и полосу — письмо из
    семи просроченных событий становилось сплошным красным полотном, и внутри него уже
    ничего не различалось. Прибор сторожит возврат: у четырёх тонов разметка карточки
    обязана совпадать всюду, кроме пилюли важности.
    """
    bodies = {}
    for tone in ("bad", "warn", "ok", "info"):
        html = render.notification_html(title="Т", body="текст", tone=tone,
                                        link_abs="https://x.ru/a")
        # вырезаем пилюлю и подзаголовок — единственное, чему положено меняться
        html = re.sub(r"<table[^>]*margin-right:6px.*?</table>", "", html, flags=re.S)
        html = re.sub(r"<td style=\"font-family:[^\"]*font-size:13px.*?</td>", "", html,
                      flags=re.S)
        bodies[tone] = html
    assert len(set(bodies.values())) == 1, "тон подкрасил что-то помимо пилюли"
    for tone, html in bodies.items():
        for bg, _, _, _ in render.PILLS.values():
            assert f"background-color:{bg}" not in html, (
                f"тон {tone} попал в подложку карточки")


def test_pill_carries_the_tone_by_word():
    """Важность несёт СЛОВО, а не только цвет.

    Пилюля читается в чёрно-белой печати, при дальтонизме и в клиенте, вырезавшем фоны —
    в этих условиях подложка исчезает молча, и письмо о сорванном запуске становится
    неотличимо от письма к сведению.
    """
    words = set()
    for tone, word in (("bad", "срочно"), ("warn", "нужно решение"),
                       ("ok", "готово"), ("info", "к сведению")):
        html = render.notification_html(title="Т", body=None, link_abs=None, tone=tone)
        assert word in html, f"у тона {tone} нет слова «{word}»"
        words.add(word)
    assert len(words) == 4


def test_pill_and_tag_are_nested_tables_not_spans():
    """Outlook теряет `border` у строчного элемента: пилюля осталась бы словом без
    подложки. Поэтому и она, и тег вида собраны вложенными таблицами."""
    html = render.notification_html(title="Т", body=None, link_abs=None, tone="bad",
                                    tag="очередь сделок")
    assert "<span style=" + chr(34) + "border" not in html
    assert html.count('align="left"') >= 2


def test_tag_never_wears_the_tone():
    """Тег вида — классификация, а не важность. Два цветных элемента рядом снова дали
    бы светофор, поэтому тег серый при любом тоне."""
    for tone in ("bad", "warn", "ok", "info"):
        html = render.notification_html(title="Т", body=None, link_abs=None, tone=tone,
                                        tag="креативы")
        i = html.index("креативы")
        chunk = html[max(0, i - 400):i]
        assert render.SOFT in chunk, f"тег покрашен тоном {tone}"


def test_button_appears_only_with_a_link():
    """Кнопка без адреса — обманка: выглядит нажимаемой и никуда не ведёт."""
    with_link = render.notification_html(title="Т", body=None,
                                         link_abs="https://x.ru/a", action="Открыть сделку")
    assert "Открыть сделку" in with_link and "https://x.ru/a" in with_link
    without = render.notification_html(title="Т", body=None, link_abs=None,
                                       action="Открыть сделку")
    assert "Открыть сделку" not in without


def test_facts_fill_the_letter_that_has_no_body():
    """У пяти событий тело пустое — всё содержание в заголовке. Для колокольчика это
    нормально, для письма означало бы пустую карточку; факты её наполняют."""
    html = render.notification_html(title="Т", body=None, link_abs=None,
                                    facts=[("показов", "1 508 299"), ("площадок", "19")])
    assert "1 508 299" in html and "площадок" in html


def test_text_part_repeats_the_same_content():
    """Текстовая часть обязательна: часть получателей читает без разметки, а письмо
    без неё выглядит подозрительным для фильтров. И содержание в ней то же."""
    txt = render.text_body("Заголовок", "Текст", "https://x.ru/a",
                           [("ждёт", "6 дн."), ("к оплате", "188 400 ₽")])
    assert txt.splitlines()[0] == "Заголовок"
    assert "Текст" in txt and txt.strip().endswith("https://x.ru/a")
    assert "ждёт: 6 дн. · к оплате: 188 400 ₽" in txt, (
        "факты обязаны доехать и в текстовую часть — иначе каналы говорят разное")
    assert "<" not in txt


# ── Каркас письма и дайджест ─────────────────────────────────────────────────

def test_button_is_blue_at_every_tone():
    """Кнопка одна и та же при любом тоне.

    Красная кнопка в тревожном письме не добавляет срочности, но ломает привычку:
    основное действие в системе выглядит одинаково везде. Цветом остаётся
    предупреждение, не действие.
    """
    seen = set()
    for tone in ("bad", "warn", "ok", "info"):
        html = render.notification_html(title="Т", body=None, link_abs="https://x.ru/a",
                                        tone=tone, action="Сделать")
        seen |= set(re.findall(r"background-color:(#[0-9A-Fa-f]{6});color:#FFFFFF", html))
    assert seen == {render.ACCENT}, f"кнопка покрасилась тоном: {seen}"


def test_button_has_an_outlook_variant():
    """Движок Word не красит фон у ссылки — без `v:roundrect` кнопка в Outlook выглядит
    обычным текстом. Оба варианта спрятаны условными комментариями, поэтому каждый
    клиент видит ровно один."""
    html = render.notification_html(title="Т", body=None, link_abs="https://x.ru/a")
    assert "v:roundrect" in html and "<!--[if mso]>" in html
    assert "<!--[if !mso]><!-->" in html


def test_exactly_one_fact_is_painted():
    """Покрашено ровно одно значение — то, ради которого письмо пришло.

    Если покрасить два, теряется смысл выделения: глаз ищет одну цифру. И тон карточки
    плашки НЕ наследуют — в «просрочке 14 дней» красное только «14 дн.», сумма и период
    нейтральны.
    """
    html = render.notification_html(
        title="Т", body=None, link_abs=None, tone="bad",
        facts=[{"k": "ждёт", "v": "6 дн.", "fg": "danger", "hot": True},
               {"k": "к оплате", "v": "188 400 ₽"},
               {"k": "период", "v": "2026-08", "fg": "muted"}])
    bad_bg = render.PILLS["bad"][0]
    # подложка тона встречается дважды: пилюля важности и ровно одна плашка
    assert html.count("background-color:" + bad_bg) == 2
    painted = html.count("font-weight:700;color:" + render.FACT_FG["danger"])
    assert painted == 1, f"покрашено значений: {painted}"


def test_sender_mark_degrades_to_a_word():
    """Знак отправителя — растр по макету, но письмо без картинок остаётся подписанным.

    Клиенты по умолчанию не грузят изображения, и шапка была бы пустой строкой. Поэтому
    `alt` несёт имя отправителя, а без `DOMAIN` (стенд) знак собирается разметкой.
    """
    with_logo = render.notification_html(title="Т", body=None, link_abs=None,
                                         brand="SIMB-AD", logo_url="https://x.ru/l.png")
    assert "<img" in with_logo and 'alt="SIMB-AD"' in with_logo
    without = render.notification_html(title="Т", body=None, link_abs=None,
                                       brand="SIMB-AD")
    assert "<img" not in without and "SIMB-AD" in without


def _digest(items, name=""):
    """Дайджест так, как его собирает живая отправка: оболочка «Шаблонов писем» поверх
    карточек (с 24.09.2026 — `mail.live.digest`, аудит 5.M1). Правок в оболочке на стенде
    нет, значит это умолчание — правило."""
    from app.database import SessionLocal
    from app.mail import live

    db = SessionLocal()
    try:
        return live.digest(db, "staff", items, {"имя": name or "коллеги"},
                           brand="SIMB-AD", logo_url=None, settings_url=None)[1]
    finally:
        db.close()


def test_counters_are_outlined_not_filled():
    """Счётчики дайджеста контурные: залитые спорили бы с пилюлями карточек за
    внимание, а их работа — только сказать, чего сколько."""
    html = _digest([{"title": "x", "tone": "bad"}, {"title": "y", "tone": "ok"}])
    head = html[:html.index("padding:14px 22px 6px")]
    for bg, _, _, _ in render.PILLS.values():
        assert f"background-color:{bg}" not in head, "счётчик залит цветом тона"


def test_digest_counts_by_tone_and_orders_by_weight():
    """Дайджест: счётчики в шапке и порядок по тяжести.

    «У вас 6 уведомлений» без разбивки заставляет читать все шесть, чтобы понять, есть ли
    срочное. И первым в письме должно идти то, что блокирует работу, а не то, что пришло
    последним."""
    items = [
        {"title": "Хорошо", "tone": "ok"},
        {"title": "Плохо", "tone": "bad"},
        {"title": "Внимание", "tone": "warn"},
        {"title": "Ещё плохо", "tone": "bad"},
    ]
    html = _digest(items, "Валерия")
    assert "Валерия, за сутки 4 события" in html
    assert "3 требуют действия сегодня, остальные — к сведению" in html
    assert html.index("Плохо") < html.index("Внимание") < html.index("Хорошо")


def test_digest_does_not_promise_a_remainder_that_is_not_there():
    """Когда действия требуют ВСЕ события, «остальные — к сведению» обещает остаток,
    которого нет. Мелочь, но письмо на этом перестаёт читаться как правда. Переезд
    дайджеста на оболочку редактора (24.09.2026) чуть не вернул ровно эту ошибку:
    подзаголовок по умолчанию дописывал «Остальное — к сведению» всегда."""
    html = _digest([{"title": "a", "tone": "bad"}, {"title": "b", "tone": "warn"}])
    assert "Все требуют действия сегодня" in html
    assert "стальн" not in html


def test_digest_says_it_plainly_when_nothing_needs_action():
    """Письмо из одних хороших новостей не должно пугать словом «требуют»."""
    html = _digest([{"title": "ЕРИД выпущен", "tone": "ok"}], "Пётр")
    assert "к сведению, действий не требуется" in html
    assert "требуют" not in html


def test_plural_agrees_with_the_number():
    """«1 событие», «2 события», «5 событий», «11 событий» — согласование своё, и
    одиннадцать здесь главная ловушка: по последней цифре оно было бы «событие»."""
    from app.mail import editor
    for n, word in ((1, "событие"), (2, "события"), (5, "событий"), (11, "событий"),
                    (21, "событие"), (104, "события")):
        got = editor.computed([{"title": "x", "tone": "info"}] * n)["всего"]
        assert got == f"{n} {word}", f"{n} → {got}"


def test_rounded_tables_declare_a_separate_border_model():
    """Скругление у таблицы не работает при схлопнутых границах.

    По спецификации `border-radius` не действует, пока `border-collapse: collapse` —
    и в почтовом бойлерплейте это правило стоит по делу, оно убирает щели в Outlook.
    Скруглено же у нас всё таблицами: карточка, пилюля, тег, плашка, счётчик, конверт.
    В итоге круглой была одна кнопка (она ссылка, а не таблица), остальное — прямые
    углы, и правка радиусов «с 7 на 9» ничего не меняла вовсе.

    Деградация тихая: разметка верная, тесты зелёные, а письмо выглядит не так.
    Нашлось глазами владельца, а не прогоном — прибор ставится, чтобы в следующий раз
    нашлось прогоном.
    """
    import re
    html = render.notification_html(
        title="Т", body="текст", link_abs="https://x.ru/a", tone="bad", tag="орд",
        facts=[{"k": "ждёт", "v": "6 дн.", "hot": True}, {"k": "сумма", "v": "1 ₽"}])
    # каждое объявление радиуса внутри открывающего тега <table …>
    for m in re.finditer(r"<table[^>]*border-radius:(\d+)px", html):
        tag = m.group(0)
        assert "border-collapse:separate" in tag, (
            "у таблицы скругление без раздельной модели — радиус не применится: "
            + tag[-120:])
    # и глобальное правило не должно давить инлайн
    block = html[html.index("<style>"):html.index("</style>")]
    assert "border-collapse:collapse !important" not in block


def test_the_letter_is_actually_rounded():
    """Скругления не пропали совсем: конверт, карточка и плашки объявлены.

    Парный прибор к предыдущему — тот проверяет «радиус применится», этот «радиус есть».
    Поодиночке любой из них зелён и при квадратном письме.
    """
    html = render.notification_html(title="Т", body=None, link_abs="https://x.ru/a",
                                    facts=[{"k": "а", "v": "1"}])
    for px, what in ((render.R_LETTER, "конверт"), (render.R_CARD, "карточка"),
                     (render.R_CHIP, "пилюля и плашки"), (render.R_BUTTON, "кнопка")):
        assert f"border-radius:{px}px" in html, f"{what}: скругление пропало"


def test_letter_shows_moscow_time_not_utc():
    """Время в шапке — московское.

    Контейнеры и postgres живут в UTC (`app/timez.py`), и `datetime.now()` внутри
    контейнера даёт время на три часа в прошлом. Получатель в Москве видит правдоподобное
    неправильное время и потому не задаёт вопросов — ошибка тихая по определению.

    Проверяется УМОЛЧАНИЕ: параметр `when` можно забыть, и тогда правильным должно быть
    то, что подставится само.
    """
    from datetime import datetime, timedelta

    from app import timez

    html = render.notification_html(title="Т", body=None, link_abs=None)
    m = re.search(r"(\d\d)\.(\d\d)\.(\d{4}) · (\d\d):(\d\d)", html)
    assert m, "в шапке нет даты и времени"
    shown = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)),
                     int(m.group(4)), int(m.group(5)))
    delta = abs((shown - timez.msk_now()).total_seconds())
    assert delta < 120, f"письмо показывает не московское время: разница {delta / 60:.0f} мин"
    # и это НЕ UTC — иначе разница была бы ровно тремя часами
    assert abs((shown - datetime.utcnow()).total_seconds()
               - timedelta(hours=timez.MSK_OFFSET).total_seconds()) < 120


def test_digest_time_defaults_the_same_way():
    """У дайджеста то же умолчание: два письма одной системы не должны показывать
    время по разным часам."""
    from datetime import datetime

    from app import timez

    html = render.composed_html(cards_data=[{"title": "x", "tone": "info"}], headline="h",
                                sub="", preheader="", footer="")
    m = re.search(r"(\d\d)\.(\d\d)\.(\d{4}) · (\d\d):(\d\d)", html)
    shown = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)),
                     int(m.group(4)), int(m.group(5)))
    assert abs((shown - timez.msk_now()).total_seconds()) < 120
