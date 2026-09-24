# -*- coding: utf-8 -*-
"""Наружу не уходят наши деньги и наши примеры.

Три правила владельца, каждое из которых ломается ТИХО — письмо уходит, выглядит
нормально, и узнаём мы об этом от площадки:

1. **денег в письме площадке нет никогда.** Наши суммы это наша маржа и наши условия с
   клиентом; площадке они не принадлежат. Проверяется и в объявлении видов, и на самой
   отправке — заслон снимает плашку молча для получателя, но громко для лога;
2. **плашка не повторяет строку контекста.** В ней уже стоят площадка, бренд и период;
   дубль занимает место, не добавляя смысла (разбор письма 16.09.2026);
3. **примерные данные предпросмотра НЕ УХОДЯТ в рассылку.** «Максавит» и «Хелинорм» в
   предпросмотре — подстановка с живой строки базы, чтобы видеть реальную длину имён.
   Если бы её хоть раз собрал отправитель, письмо про чужую площадку ушло бы всем.
"""
import io
from pathlib import Path

import pytest

from app.notify.outward import kinds
from app.notify.outward.send import MONEY_WORDS, strip_money

# Строка контекста внешнего письма: домен · бренд · период. Эти же слова в плашке —
# дубль, а не факт.
CONTEXT_WORDS = ("площадк", "бренд", "период", "сайт", "домен")

# Слова, называющие ЧИСЛО В ДЕНЬГАХ. Уже отдельно от `MONEY_WORDS`: там список для
# КЛЮЧЕЙ плашек, и в нём есть «оплат» — плашка с таким ключом несёт сумму. А в связном
# тексте «оплата ждёт подписи» это про ход дела, а не про наши деньги, и запрещать его
# значит запрещать говорить с площадкой о платежах вообще.
AMOUNT_WORDS = ("сумм", "цена", "ценой", "стоим", "бюджет", "ставк", "тариф", "прайс",
                "руб", "₽", "cpm", "cpc")


def test_ни_один_вид_не_объявляет_денежную_плашку():
    bad = [(k.key, f) for k in kinds.KINDS for f in (k.facts or ())
           if any(w in f.lower() for w in MONEY_WORDS)]
    assert bad == [], f"деньги в плашках площадке: {bad}"


def test_плашки_не_повторяют_строку_контекста():
    bad = [(k.key, f) for k in kinds.KINDS for f in (k.facts or ())
           if any(w in f.lower() for w in CONTEXT_WORDS)]
    assert bad == [], f"плашка дублирует контекст письма: {bad}"


def test_плашек_не_больше_четырёх():
    """Пять и больше — карточка перестаёт читаться за секунду и превращается в таблицу
    (PINS_плашки_фактов.md). Ноль допустим: событие-факт обходится заголовком."""
    bad = [(k.key, len(k.facts)) for k in kinds.KINDS if len(k.facts or ()) > 4]
    assert bad == [], f"слишком много плашек: {bad}"


@pytest.mark.parametrize("fact", [
    ("сумма", "500 000 ₽"),
    ("за размещение", "120000 руб"),
    ("CPM", "250"),
    ("бюджет кампании", "1 млн"),
])
def test_заслон_снимает_деньги_в_любой_форме(fact):
    """Ключ И значение: «за размещение» с денежным значением прошло бы проверку только
    по ключу."""
    assert strip_money([fact, ("план показов", "1 200 000")]) == [("план показов", "1 200 000")]


def test_заслон_стоит_перед_ВСЕМИ_каналами():
    """Бот и панель показывают те же плашки. «Убрали из письма, оставили в телеграме» —
    это не выполненное правило, а его видимость."""
    src = io.open(Path(kinds.__file__).parent / "send.py", encoding="utf-8").read()
    i_strip = src.index("facts = strip_money(facts)")
    assert i_strip < src.index('"tg": _to_bot('), "заслон стоит после бота"
    assert i_strip < src.index("render.notification_html("), "заслон стоит после сборки письма"


def test_примерные_данные_живут_только_в_предпросмотре():
    """`editor.sample` берёт ПЕРВУЮ живую площадку и ПОСЛЕДНЮЮ сделку — «Максавит» и
    «Хелинорм» на стенде. Позови её отправитель, и письмо про чужую площадку ушло бы
    каждому получателю.

    Прибор смотрит, кто её зовёт: только предпросмотр и редактор шаблонов. Отправка
    (`notify/`, `mail/send.py`, `mail/flush.py`) обязана собирать письмо из данных
    события, а не из примера.
    """
    root = Path(kinds.__file__).resolve().parents[2]          # backend/app
    callers = []
    for p in root.rglob("*.py"):
        rel = str(p.relative_to(root)).replace("\\", "/")
        if rel in ("mail/editor.py", "mail/preview.py"):
            continue
        src = io.open(p, encoding="utf-8").read()
        if "editor.sample(" in src or "from app.mail.editor import sample" in src:
            callers.append(rel)
    assert callers == [], f"пример подставляется в отправке: {callers}"


def test_отправитель_шлёт_то_что_объявлено_в_каталоге():
    """Состав плашек у отправителя и в каталоге обязан совпадать.

    Разойдись они — экран «Шаблоны писем» показывает один набор, а получатель видит
    другой, и правят текст под плашки, которых в письме не будет. Ровно это и случилось
    16.09.2026: у «старт рк» план показов убрали из каталога, а отправитель продолжал
    бы его слать.

    Прибор разбирает вызовы `notify_publisher` в коде и сверяет ЛИТЕРАЛЬНЫЕ ключи
    плашек. Вызов, собирающий плашки переменной, пропускается: угадывать содержимое
    переменной значило бы проверять свою фантазию.
    """
    import ast

    root = Path(kinds.__file__).resolve().parents[2]
    declared = {k.key: set(k.facts or ()) for k in kinds.KINDS}
    bad = []
    for p in root.rglob("*.py"):
        tree = ast.parse(io.open(p, encoding="utf-8").read())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and getattr(node.func, "id", "") == "notify_publisher"):
                continue
            key = next((a.value for a in node.args
                        if isinstance(a, ast.Constant) and isinstance(a.value, str)), None)
            facts = next((kw.value for kw in node.keywords if kw.arg == "facts"), None)
            if key is None or not isinstance(facts, (ast.List, ast.Tuple)):
                continue
            keys = {e.elts[0].value for e in facts.elts
                    if isinstance(e, (ast.Tuple, ast.List)) and e.elts
                    and isinstance(e.elts[0], ast.Constant)}
            extra = keys - declared.get(key, set())
            if extra:
                bad.append((str(p.relative_to(root)), key, sorted(extra)))
    assert bad == [], f"отправитель шлёт плашки, которых нет в каталоге: {bad}"


def test_в_текстах_видов_нет_наших_сумм():
    """Деньги утекают не только плашкой. Подпись «Размещение вышло в эфир — с планом и
    ценой» нашлась 16.09.2026 случайно, при разборе соседнего вида: она ОБЕЩАЛА площадке
    наши числа, и заметить это можно было только прочитав все шестнадцать подписей.

    Проверяются название и пояснение — то, что видит получатель. Поле `repeat` это наша
    служебная заметка о частоте, наружу она не уходит.
    """
    bad = []
    for k in kinds.KINDS:
        for field in ("label", "hint"):
            text = (getattr(k, field, "") or "").lower()
            hit = [w for w in AMOUNT_WORDS if w in text]
            if hit:
                bad.append((k.key, field, hit))
    assert bad == [], f"деньги в тексте письма площадке: {bad}"


def test_подстановки_суммы_у_внешнего_контура_нет():
    """Редактор не предлагает того, что нельзя использовать: предложенная подстановка
    читается как разрешение. Вписать её руками всё ещё можно — на это стоит проверка
    перед сохранением, отдельным пунктом «Во внешнем письме нет наших сумм»."""
    from app.mail import editor

    assert "сумма" not in editor.fields_of(editor.PUB)
    assert "сделка" not in editor.fields_of(editor.PUB)
    assert "сумма" in editor.fields_of(editor.STAFF)


def test_the_screen_cuts_money_not_words():
    """Аудит 23.09.2026, 5.L1. Заслон искал подстроку: «ставк» в «Доставка креатива»,
    «cpm» внутри ЕРИД — и из письма «ЕРИД выпущен» пропадал сам ЕРИД. Слово-деньги
    ищется с НАЧАЛА слова; знак рубля — где угодно."""
    kept = [("этап", "Доставка креатива"), ("ЕРИД", "Kra23cpmXyZ"),
            ("ЕРИД", "2VtzqwCpcAb")]
    assert strip_money(kept) == kept
    for money in (("стоимость", "1 200 ₽"), ("ставка", "150 руб"),
                  ("условия", "CPM 250"), ("итог", "1 200 ₽")):
        assert strip_money([money]) == [], money
