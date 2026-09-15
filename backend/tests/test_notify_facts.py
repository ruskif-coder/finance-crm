# -*- coding: utf-8 -*-
"""Плашки фактов: собирает событие, каналы только отрисовывают.

Правило хендоффа (PINS_плашки_фактов.md, §8): одно уведомление показывает ОДИНАКОВЫЕ
числа в панели, в письме и в телеграме. Значит факты едут по одной дороге — правило →
шина → журнал → канал, — и ни один канал их не пересчитывает.

Прибор поставлен после двух находок 14.09.2026:

* `_queue_facts` читал `d.amount_net` — поля с таким именем у сделки нет, оно есть у
  МЕДИАПЛАНА. `getattr` отдавал None, плашка суммы просто не появлялась, и ошибка была
  неотличима от «у сделки не заполнена сумма»;
* досылка в телеграм собирала текст сама и слала один заголовок — без тела и без чисел.
"""
import inspect
import re

import pytest

from app.mail import render
from app.notify import channels, scanner
from app.notify.models import NotificationDelivery
from app.models import Notification
from app.sales.models import SalesDeal


def test_facts_reach_every_channel_the_same():
    """Один и тот же набор фактов виден в письме, в текстовой части и в телеграме."""
    facts = [{"k": "сумма", "v": "188 400 ₽"},
             {"k": "просрочено", "v": "14 дн.", "fg": "danger", "hot": True}]
    html = render.notification_html(title="Т", body=None, link_abs=None, facts=facts)
    txt = render.text_body("Т", None, None, facts)
    tg = channels.tg_text("Т", None, facts)
    for f in facts:
        assert f["v"] in html, f"{f['k']} потерялся в письме"
        assert f["v"] in txt, f"{f['k']} потерялся в текстовой части"
        assert f["v"] in tg, f"{f['k']} потерялся в телеграме"
    assert txt.endswith(tg.splitlines()[-1]), "разделители разошлись между каналами"


def test_journal_keeps_the_facts():
    """Факты лежат в журнале доставки. Досылка через сутки не пересобирает их заново:
    состояние к тому времени другое, и пересчитанные числа спорили бы с заголовком,
    с которым приехали."""
    assert hasattr(NotificationDelivery, "facts")
    assert hasattr(NotificationDelivery, "code")
    assert hasattr(Notification, "facts")
    assert hasattr(Notification, "code")


def test_deferred_telegram_says_the_same_as_the_live_one():
    """Досылка зовёт ОБЩИЙ сборщик текста, а не свой.

    Пока она собирала сообщение сама, отложенное уведомление приходило одним заголовком.
    Проверяется вызов, а не результат: отправку в телеграм со стенда не сделать.
    """
    src = inspect.getsource(__import__("app.notify.dispatch", fromlist=["x"]))
    assert "channels.tg_text(" in src
    assert not re.search(r"send_message\(\s*ch\.tg_chat_id,\s*r\.title", src), \
        "досылка снова собирает текст сама"


@pytest.mark.parametrize("fname", ["_queue_facts"])
def test_fact_builders_read_fields_that_exist(fname):
    """Сборщик фактов сделки обращается только к реальным полям `SalesDeal`.

    Опечатка в имени поля здесь не падает — `getattr` отдаёт None, а плашка молча
    исчезает. Ровно это и случилось с `amount_net` (поле медиаплана, не сделки).
    """
    src = inspect.getsource(getattr(scanner, fname))
    used = set(re.findall(r"\bd\.([a-z_]+)", src))
    used |= set(re.findall(r'getattr\(d,\s*"([a-z_]+)"', src))
    missing = sorted(f for f in used if not hasattr(SalesDeal, f))
    assert not missing, f"{fname} читает несуществующие поля сделки: {missing}"


def test_every_scanner_rule_builds_facts_or_says_why():
    """У каждого правила, у которого есть сработки, плашки собраны.

    Проверяется РЕЗУЛЬТАТ, а не текст правила: `rule_backlog_overdue` собирает плашки
    в отдельной функции, и поиск `facts=` в его теле честно ничего бы не нашёл.

    Правила без сработок на стенде пропускаются и НАЗЫВАЮТСЯ в сообщении: «все правила
    прошли» при нулевых данных — это отчёт ни о чём, и такое уже принимали за проверку.
    """
    from app.database import SessionLocal
    from app.notify import registry

    db = SessionLocal()
    try:
        checked, empty, bare = [], [], []
        for key, fn in scanner.RULES.items():
            ev = registry.get(key)
            if ev is None:
                continue
            try:
                hits = fn(db, ev)
            except Exception as e:                      # noqa: BLE001
                pytest.fail(f"правило {key} упало: {type(e).__name__}: {e}")
            if not hits:
                empty.append(key)
                continue
            checked.append(key)
            if not any(h.facts for h in hits):
                bare.append(key)
    finally:
        db.close()

    assert not bare, f"правила без плашек: {bare}"
    assert checked, "ни одно правило не сработало — проверять было нечего"
    print(f"проверено правил: {len(checked)}, без сработок на стенде: {empty}")


def test_only_one_fact_is_hot():
    """Покрашено не больше одного значения в карточке.

    Если покрасить два, теряется смысл выделения: глаз ищет одну цифру, ради которой
    уведомление и пришло.
    """
    from app.database import SessionLocal
    from app.notify import registry

    db = SessionLocal()
    try:
        for key, fn in scanner.RULES.items():
            ev = registry.get(key)
            if ev is None:
                continue
            for h in fn(db, ev):
                hot = [f for f in h.facts if isinstance(f, dict) and f.get("hot")]
                assert len(hot) <= 1, f"{key}: покрашено {len(hot)} значений"
    finally:
        db.close()


def test_facts_count_stays_readable():
    """Две, три или четыре плашки. Пять превращают карточку в таблицу, одна означает,
    что факту место в заголовке."""
    import app.notify.scanner as sc
    lists = re.findall(r"facts=\[(.*?)\],\n", inspect.getsource(sc), flags=re.S)
    for chunk in lists:
        n = chunk.count('{"k"') + chunk.count("hot,")
        assert 1 <= n <= 4, f"плашек {n}: {chunk[:80]}"
