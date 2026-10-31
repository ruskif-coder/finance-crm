# -*- coding: utf-8 -*-
"""Проверка шаблона ДС — ОДНА на весь проект (сервер при сохранении; с макета 13.10.2026 экран повторяет её же).

Блок: `id`, `title`, для системных `sys` (head|place|pre|table|sign), для текстовых `text`; флаги `sub` (подпункт),
`req` (обязательный), `pin` (закреплён: нельзя убрать и снять обязательность в следующих версиях), `money` (пункт
с деньгами — обязан содержать защищённые подстановки).

Порядок: системные блоки идут head, place, pre, table, sign; текстовые — только между `pre` и `sign`.
Зона из положения относительно таблицы МП: до неё правит аккаунт, после — юрист. Поля зоны и номера нет —
они выводятся из порядка (иначе поле и порядок расходятся при первой перестановке).
"""
import re
from typing import List, Optional

from app.annex_tpl.subs import PROTECTED_GROUPS, SUBS

SYS_ORDER = ("head", "place", "pre", "table", "sign")
MAX_BLOCKS = 60
MAX_TEXT = 8000
PLACEHOLDER = "Текст пункта."
NEW_TITLE = "Новый пункт"
_KEY = re.compile(r"\{([^{}]+)\}")


def numbering(blocks: List[dict]) -> dict:
    """Номера пунктов из порядка: основной 1., 2.; подпункт — к предыдущему основному."""
    num, main, sub = {}, 0, 0
    for b in blocks:
        if b.get("sys"):
            continue
        if b.get("sub") and main:
            sub += 1
            num[b["id"]] = f"{main}.{sub}."
        else:
            main += 1
            sub = 0
            num[b["id"]] = f"{main}."
    return num


def zone_at(blocks: List[dict], i: int) -> str:
    t = next((k for k, b in enumerate(blocks) if b.get("sys") == "table"), len(blocks))
    return "acc" if i < t else "law"


# Нумерованные подстановки: `юр_название_2`, `юр_название_3`, … Списком их не объявить —
# у одного плательщика 116 рекламодателей (замер 31.10.2026), и никакое разумное N не
# покрывает. Поэтому проверка понимает образец имени, а сборка подставляет то, что есть.
#
# С двойки: первый рекламодатель — это `юр_название` без номера, и второго способа сказать
# то же самое быть не должно. Ноль и единица отвергаются намеренно.
NUMBERED = re.compile(r"^(юр_название)_(?:[2-9]|[1-9]\d+)$")

# Слово, которое с 31.10.2026 обязано быть подстановкой `{вид_документа}`, а не текстом:
# иначе тумблер договора «Приложение / ДС» этот пункт не изменит. Это ПРЕДУПРЕЖДЕНИЕ, а не
# ошибка: 17 шаблонов на проде написаны со словом, и запрет на сохранение остановил бы
# работу вместо того, чтобы её направить (владелец: «все шаблоны пересохранят девчата»).
WORD_LITERALS = ("Приложени", "Доп.соглашени", "Доп. соглашени", "доп.соглашени", "доп. соглашени")


def unknown_keys(text: str) -> List[str]:
    return [m for m in _KEY.findall(text or "")
            if m not in SUBS and not NUMBERED.match(m)]


def literal_word_notes(blocks) -> List[dict]:
    """Пункты, где вид документа написан словом, а не подстановкой — что пересохранить.

    Отдельно от `check()`: сохранять такой шаблон можно, но человек, открывший его,
    должен увидеть, что именно поправить. Без этого «пересохранят все шаблоны»
    делается вслепную.
    """
    if not isinstance(blocks, list):
        return []
    num = numbering(blocks)
    out = []
    for b in blocks:
        if not isinstance(b, dict) or b.get("sys"):
            continue
        t = b.get("text") or ""
        hit = next((w for w in WORD_LITERALS if w in t), None)
        if hit:
            out.append(_issue(b, num, "вид документа написан словом — заменить на {вид_документа}; "
                                      "иначе тумблер договора «Приложение / ДС» этот пункт не изменит"))
    return out


def _issue(block: Optional[dict], num: dict, text: str) -> dict:
    bid = block.get("id") if block else None
    where = f"{num.get(bid, '')} {block.get('title', '')} · " if block else ""
    return {"id": bid, "where": where, "text": text}


def structure_issues(blocks) -> List[dict]:
    if not isinstance(blocks, list) or not blocks:
        return [_issue(None, {}, "шаблон пуст")]
    if len(blocks) > MAX_BLOCKS:
        return [_issue(None, {}, f"блоков больше {MAX_BLOCKS}")]
    out, seen = [], set()
    for b in blocks:
        if not isinstance(b, dict) or not isinstance(b.get("id"), str) or not b["id"].strip():
            return [_issue(None, {}, "у блока нет идентификатора")]
        if b["id"] in seen:
            return [_issue(None, {}, f"повтор идентификатора блока {b['id']}")]
        seen.add(b["id"])
        if b.get("sys") is not None and b["sys"] not in SYS_ORDER:
            return [_issue(None, {}, f"неизвестный системный блок {b['sys']}")]
    sys_seq = [b["sys"] for b in blocks if b.get("sys")]
    if sys_seq != list(SYS_ORDER):
        out.append(_issue(None, {}, "системные блоки должны идти по порядку: заголовок, место и дата, преамбула, таблица МП, подписи — по одному"))
        return out
    first = next(i for i, b in enumerate(blocks) if b.get("sys") == "pre")
    last = next(i for i, b in enumerate(blocks) if b.get("sys") == "sign")
    for i, b in enumerate(blocks):
        if not b.get("sys") and not (first < i < last):
            out.append(_issue(b, {}, "текстовый пункт стоит вне области между преамбулой и подписями"))
    return out


def check(blocks) -> List[dict]:
    """Список ошибок вида `{id, where, text}`; пусто — шаблон годен к сохранению."""
    issues = structure_issues(blocks)
    if issues:
        return issues
    num = numbering(blocks)
    for b in blocks:
        if b.get("sys"):
            continue
        t = b.get("text")
        title = (b.get("title") or "").strip()
        if not isinstance(t, str) or len(t.strip()) < 3 or t.strip() == PLACEHOLDER:
            issues.append(_issue(b, num, "пункт не заполнен"))
            t = t if isinstance(t, str) else ""
        if len(t) > MAX_TEXT:
            issues.append(_issue(b, num, f"текст длиннее {MAX_TEXT} знаков"))
        bad = unknown_keys(t)
        if bad:
            issues.append(_issue(b, num, "неизвестная подстановка " + ", ".join("{" + k + "}" for k in bad)))
        if b.get("money"):
            for group in PROTECTED_GROUPS:
                if not any("{" + k + "}" in t for k in group):
                    issues.append(_issue(b, num, "убрана защищённая подстановка " + " или ".join("{" + k + "}" for k in group)))
        if not title or title == NEW_TITLE:
            issues.append(_issue(b, num, "у пункта нет названия"))
    return issues


def check_transition(prev: Optional[List[dict]], nxt: List[dict]) -> List[dict]:
    """Закреплённый (`pin`) пункт прошлой версии нельзя убрать и нельзя снять с него обязательность и закрепление."""
    if not prev:
        return []
    out, byid = [], {b["id"]: b for b in nxt if isinstance(b, dict) and "id" in b}
    for p in prev:
        if not p.get("pin"):
            continue
        n = byid.get(p["id"])
        label = f"{p.get('title', '')} · "
        if n is None:
            out.append({"id": p["id"], "where": label, "text": "закреплённый пункт убрать нельзя"})
        elif not (n.get("req") and n.get("pin")):
            out.append({"id": p["id"], "where": label, "text": "с закреплённого пункта нельзя снять обязательность"})
    return out
