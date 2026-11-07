# -*- coding: utf-8 -*-
"""Шаблоны ДС: «Приложение…», вписанное текстом, → подстановка вида документа (владелец 07.11.2026).

С v2.7.38 слово документа, вписанное в шаблон руками, печатается как написано; следует виду договора только подстановка
`{вид_документа…}`. Во всех шаблонах слово стояло текстом — остаток старого текста по умолчанию, его никто не выбирал, —
и в шаблонах договоров вида «ДС» напечаталось бы «Приложение» внутри «Дополнительного соглашения». Владелец: «по умолчанию —
переменная», заменить во всех шаблонах.

Меняется только единственное число с заглавной: «Приложение / Приложения / Приложению / Приложением / Приложении».
Не трогается: «Соглашение» (его вписали аккаунты), «приложение» со строчной (услуга), множественное число («отдельными
Приложениями к Договору» — ссылка на другие документы договора). Каждый изменённый шаблон получает НОВУЮ версию от
«система» тем же путём, что сохранение в конструкторе (`service.save_version`); история не стирается.

По умолчанию — только показать; `--apply` пишет:
    docker exec finance_backend python -m scripts.annex_word_to_tags_2026_11_07 [--apply]
"""
import copy
import re
import sys
from types import SimpleNamespace

TAG = {"е": "{вид_документа}", "я": "{вид_документа_род}", "ю": "{вид_документа_дат}",
       "ем": "{вид_документа_твор}", "и": "{вид_документа_пред}"}
WORD = re.compile(r"(?<![А-Яа-яЁё{_])Приложени(ем|е|я|ю|и)(?![А-Яа-яЁё])")


def to_tags(text):
    """Слово документа в единственном числе — в подстановку своего падежа."""
    if not text:
        return text
    return WORD.sub(lambda m: TAG[m.group(1)], text)


def convert(blocks: list) -> list:
    out = copy.deepcopy(blocks or [])
    for b in out:
        if isinstance(b, dict) and isinstance(b.get("text"), str):
            b["text"] = to_tags(b["text"])
    return out


def main(argv=None) -> int:
    import app.model_registry  # noqa: F401
    from app.annex_tpl import service as S
    from app.annex_tpl.models import AnnexTplTemplate
    from app.database import SessionLocal

    apply = "--apply" in (argv if argv is not None else sys.argv[1:])
    user = SimpleNamespace(id=None, name="система")
    db = SessionLocal()
    try:
        changed = 0
        for t in db.query(AnnexTplTemplate).order_by(AnnexTplTemplate.scope, AnnexTplTemplate.id):
            cur = S.current(db, t.id)
            if cur is None:
                continue
            new = convert(cur.blocks)
            if new == cur.blocks:
                continue
            n = sum(len(WORD.findall(b.get("text") or "")) for b in cur.blocks or [] if isinstance(b, dict))
            changed += 1
            print(f"{t.id:>4} {t.scope:6} v{cur.version} → замен: {n}  {(t.title or '')[:40]}")
            if apply:
                S.save_version(db, t.id, new, user)
        if apply:
            db.commit()
            print(f"записано: {changed} шаблонов, по новой версии")
        else:
            print(f"к замене: {changed} шаблонов; --apply чтобы записать")
        return 0
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    sys.exit(main())
