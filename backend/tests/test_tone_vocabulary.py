# -*- coding: utf-8 -*-
"""Тон уведомления — одно слово на всю систему.

Прибор поставлен 14.09.2026 после разбора: слов было два. Реестр событий говорил
`danger | warning | success`, а сканер, каталог площадок, письмо и панель —
`bad | warn | ok`. Пересекались они только на `info`, поэтому расхождение не падало
ни одним тестом и проявлялось тихо:

* письмо про просроченный счёт (`tone="danger"`) не находило себя в таблице пилюль и
  уезжало «к сведению»;
* счётчики дайджеста считали по каноническим словам — письмо из пяти событий писало
  «срочно 3» и про оставшиеся два молчало;
* в панели у `danger` не было веса в сортировке, и строка падала ниже «готово».

Найдено это было глазами на отрисовке, а не прогоном. Тесты ниже — чтобы в следующий
раз нашлось прогоном.
"""
import re
from pathlib import Path

from app.mail import render
from app.notify import registry
from app.notify import tone as tone_of
from app.notify.outward import kinds as outward_kinds

APP = Path(__file__).resolve().parent.parent / "app"


def test_registry_speaks_the_canonical_words():
    """Каждое событие реестра отдаёт тон из словаря — без приведения."""
    bad = {e.key: e.tone for e in registry.EVENTS.values()
           if e.tone not in tone_of.TONES}
    assert not bad, f"события с чужим словом тона: {bad}"


def test_publisher_catalog_speaks_the_same_words():
    """Внешний контур — тот же словарь: письмо площадке собирает тот же сборщик."""
    bad = {k.key: k.tone for k in outward_kinds.KINDS if k.tone not in tone_of.TONES}
    assert not bad, f"виды рассылки площадкам с чужим тоном: {bad}"


def test_mail_knows_every_tone():
    """У каждого тона есть пилюля. Пропущенный уезжает в умолчание — то есть
    срочное письмо выглядит справкой, и никто об этом не узнаёт."""
    assert set(render.PILLS) == set(tone_of.TONES)


def test_weight_order_is_one_list():
    """Порядок тяжести у письма и у шины совпадает.

    Почта не импортирует словарь уведомлений намеренно (гейт не должен зависеть от
    шины), поэтому списка два — и держать их согласованными обязан прибор, а не
    память. Разойдясь, они дали бы дайджест, где карточки идут в одном порядке,
    а счётчики над ними — в другом.
    """
    assert render.TONE_ORDER == tone_of.TONES


def test_old_words_still_understood():
    """История не переписывается: в `notifications.tone` лежат строки со старыми
    словами, и панель обязана их показать, а не уронить в умолчание."""
    assert tone_of.norm("danger") == "bad"
    assert tone_of.norm("warning") == "warn"
    assert tone_of.norm("success") == "ok"
    assert tone_of.norm("") == "info" and tone_of.norm(None) == "info"
    assert tone_of.norm("лиловый") == "info"       # незнакомое не падает


def test_worse_matches_the_order():
    """Ухудшение тона — единственная причина зажечь строку непрочитанной снова."""
    assert tone_of.worse("bad", "warn") and tone_of.worse("warn", "info")
    assert tone_of.worse("info", "ok")
    assert not tone_of.worse("ok", "info") and not tone_of.worse("bad", "bad")
    assert tone_of.worse("danger", "warning"), "старые слова участвуют в сравнении"


def test_no_stray_tone_words_left_in_the_code():
    """Ратчет: `tone="danger"` больше не появляется в коде.

    Ищется КОНТУР УВЕДОМЛЕНИЙ, а не слово `danger` вообще: своя шкала тона законно
    живёт у журнала кабинета и у фильтра стадий («Сделка провалена» красится красным),
    и запрещать им слово значило бы объявить чужую шкалу ошибкой.
    """
    scope = [APP / "notify", APP / "mail", APP / "routers" / "notifications.py"]
    files = [f for d in scope for f in ([d] if d.is_file() else d.rglob("*.py"))]
    stray = []
    for p in files:
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if re.search(r'tone\s*=\s*["\'](danger|warning|success)["\']', line):
                stray.append(f"{p.relative_to(APP)}:{i}")
    assert not stray, "старые слова тона вернулись: " + ", ".join(stray)
