# -*- coding: utf-8 -*-
"""Проверки ПАКЕТА премодерации — то, что одинаково у всех заявок одного креатива.

Порт `premodLogic.checksOf` из макета (docs/design_handoff_premoderation.zip) с решением владельца
08.11.2026: распознавания текста с картинки нет (замер 07.11 — мелкую юридическую строку не читает,
треть чистых креативов получила бы ложное «нарушение»). Поэтому у статики проверки текста — «посмотреть
глазами» (`warn`), а не «нарушение». У HTML5 текст берётся из разметки: найденное подтверждает проверку,
ненайденное — «посмотреть» (canvas-баннеры рисуют текст, в разметке его нет). Нарушение по тексту не
ставится никогда; «Одобрить чистые» отсекают ЕРИД, сведения для ОРД — то, что читается из разметки точно.

Каждая проверка — `{key, title, state, short, full, note}`; `state`: ok — в порядке, bad — нарушение,
warn — посмотреть человеку, na — не применимо / нечем проверить, off — подключим позже.
Проверки ЗАЯВКИ (ЕРИД, сведения для ОРД) считаются в `checks.py`; здесь они сводятся по пакету.
Фронт эти правила не повторяет — показывает то, что посчитал сервер.
"""
import re
from typing import List, Optional

OK, BAD, WARN, NA, OFF = "ok", "bad", "warn", "na", "off"
DRUGS, SUPPLEMENTS = "лекарства", "БАД"
LOOK = "сверьте глазами по увеличенной полосе"
# Текст разметки подтверждает, но не опровергает: у canvas-баннеров (все 30 HTML5 стенда, 08.11.2026)
# текст нарисован, и «нет в разметке» не значит «нет на баннере». Поэтому отсутствие — «посмотреть».
NOT_IN_MARKUP = "в тексте разметки нет — посмотрите на баннере: "

STOP_WORDS = [
    (re.compile(r"№\s?1|номер один|лучший", re.I), "«№ 1» / «лучший»", "нужно подтверждение источником"),
    (re.compile(r"гарантир", re.I), "«гарантированно»", "недопустимо без подтверждения"),
    (re.compile(r"вылечит|излечит", re.I), "обещание излечения", "ст. 24 закона о рекламе"),
    (re.compile(r"казино|ставк|букмекер", re.I), "азартные игры", "отдельные требования к рекламе"),
    (re.compile(r"пиво|вино|водк|алкогол", re.I), "алкоголь", "ст. 21 закона о рекламе"),
]
_MARK = re.compile(r"(^|[^а-яё])реклама", re.I)
_WARNINGS = {
    DRUGS: (re.compile(r"имеются противопоказания[\s\S]*консультироваться со специалистом", re.I),
            "«Имеются противопоказания…»", "ст. 24 — не менее 5 % площади"),
    SUPPLEMENTS: (re.compile(r"не является лекарственным средством", re.I),
                  "«не является лекарственным средством»", "ст. 25"),
}
_LEGAL_FORM = re.compile(r"^\s*(ООО|АО|ПАО|ЗАО|ОАО|НАО|ИП|АНО)\s+", re.I)
_QUOTES = re.compile(r"[\"«»“”„']")


def _c(key, title, state, short, full=None, note=""):
    return {"key": key, "title": title, "state": state, "short": short, "full": full or short, "note": note}


def short_name(name: Optional[str]) -> str:
    """Короткое имя заказчика для очереди: без организационно-правовой формы и кавычек."""
    if not name or not name.strip():
        return "Заказчик не указан"
    return " ".join(_QUOTES.sub(" ", _LEGAL_FORM.sub("", name.strip())).split())


def _warning(text: Optional[str], category: Optional[str]) -> dict:
    rule = _WARNINGS.get(category)
    if not rule:
        return _c("warning", "Предупреждение", NA, "не требуется · " + (category or "категория не задана"))
    rx, phrase, note = rule
    title = "Предупреждение · " + category
    if text is None:
        return _c("warning", title, WARN, f"{LOOK}: {phrase}", note=note)
    ok = bool(rx.search(text))
    return _c("warning", title, OK if ok else WARN, "есть" if ok else NOT_IN_MARKUP + phrase, note=note)


def _mentions_advertiser(text: str, adv: dict) -> bool:
    last = (adv.get("short") or "").split()[-1:]
    return bool(adv.get("inn") and adv["inn"] in text) or bool(last and last[0].lower() in text.lower())


def _text_checks(text: Optional[str], adv: dict) -> List[dict]:
    if text is None:   # статика: текста нет, смотрит человек
        return [_c("mark", "Пометка «Реклама»", WARN, LOOK, note="ст. 18.1 закона о рекламе"),
                _c("adv", "Рекламодатель на креативе", WARN, LOOK + ": наименование и ИНН"),
                _warning(None, adv.get("category")),
                _c("stop", "Стоп-слова", WARN, "посмотрите текст на баннере")]
    has_mark, has_adv = bool(_MARK.search(text)), _mentions_advertiser(text, adv)
    hits = [(label, why) for rx, label, why in STOP_WORDS if rx.search(text)]
    return [_c("mark", "Пометка «Реклама»", OK if has_mark else WARN,
               "есть" if has_mark else NOT_IN_MARKUP + "«Реклама»", note="ст. 18.1 закона о рекламе"),
            _c("adv", "Рекламодатель на креативе", OK if has_adv else WARN,
               "наименование и ИНН есть" if has_adv else NOT_IN_MARKUP + "наименования и ИНН"),
            _warning(text, adv.get("category")),
            _c("stop", "Стоп-слова", WARN if hits else OK,
               hits[0][0] + (f" +{len(hits) - 1}" if len(hits) > 1 else "") if hits else "не найдены",
               " · ".join(f"{label} — {why}" for label, why in hits) or None)]


def _bad_of(key: str, request_checks: List[List[dict]]) -> List[dict]:
    return [c for checks in request_checks for c in checks if c.get("key") == key and c.get("state") == BAD]


def package_checks(kind: str, text: Optional[str], adv: dict, size: Optional[str], hosts: List[str],
                   request_checks: List[List[dict]]) -> List[dict]:
    """`text` — видимый текст HTML5 или None у статики; `request_checks` — проверки каждой заявки пакета."""
    out = _text_checks(text, adv)
    n, bad = len(request_checks), len(_bad_of("erid", request_checks))
    out.append(_c("erid", "ЕРИД", BAD if bad else OK,
                  f"не совпадает у {bad} из {n}" if bad else f"совпадает у всех {n}",
                  f"У {bad} из {n} заявок ЕРИД в ссылке клика или разметке не совпадает с заявкой" if bad
                  else "Совпадает в заявке, разметке и ссылке"))
    ords = _bad_of("ord", request_checks)
    out.append(_c("ord", "Сведения для ОРД", BAD if ords else OK,
                  ords[0].get("detail", "") if ords else f"ИНН {adv.get('inn') or '—'} · как у заказчика"))
    if size is None:
        out.append(_c("size", "Размер", WARN, "не объявлен", "В разметке нет ad.size — посмотрите глазами"))
    else:
        out.append(_c("size", "Размер", NA, f"{size} · с блоками не сверяем",
                      "Сверка с блоками площадок выключена, пока учётки SSP не сопоставлены"))
    out.append(_c("scripts", "Внешние скрипты", WARN if hosts else OK, ", ".join(hosts) or "нет"))
    out.append(_c("contract", "Договор с заказчиком", OFF, "подключим реестр договоров"))
    out.append(_c("ord_registry", "ЕРИД в реестре ОРД", OFF, "подключим API ОРД"))
    return out


def is_clean(checks: List[dict]) -> bool:
    """Для «Одобрить чистые»: пакет с любым нарушением в массовое одобрение не попадает."""
    return not any(c.get("state") == BAD for c in checks)


def _text_change(old: Optional[str], new: Optional[str]) -> Optional[dict]:
    """Отличающийся кусок текста — по словам, без общего начала и конца."""
    if (old or "") == (new or ""):
        return None
    a, b = (old or "").split(), (new or "").split()
    head = 0
    while head < min(len(a), len(b)) and a[head] == b[head]:
        head += 1
    tail = 0
    while tail < min(len(a), len(b)) - head and a[-1 - tail] == b[-1 - tail]:
        tail += 1
    return {"label": "текст", "from": " ".join(a[head:len(a) - tail]), "to": " ".join(b[head:len(b) - tail]),
            "kind": "changed"}


def changes(old: dict, new: dict) -> List[dict]:
    """Что изменилось против прежней версии: `{label, from, to, kind}`, kind — changed / added / same.

    `old` / `new` — `{"size", "text", "hosts"}`.
    """
    out = []
    if old.get("size") != new.get("size"):
        out.append({"label": "размер", "from": old.get("size") or "не объявлен",
                    "to": new.get("size") or "не объявлен", "kind": "changed"})
    text = _text_change(old.get("text"), new.get("text"))
    if text:
        out.append(text)
    was, now = set(old.get("hosts") or []), set(new.get("hosts") or [])
    out += [{"label": "скрипт", "from": "", "to": "+ " + h, "kind": "added"} for h in sorted(now - was)]
    out += [{"label": "скрипт", "from": h, "to": "убран", "kind": "changed"} for h in sorted(was - now)]
    return out or [{"label": "креатив", "from": "", "to": "изменилась картинка или разметка", "kind": "same"}]
