# -*- coding: utf-8 -*-
"""Заводит базовый шаблон ДС и его версию 1 из JSON-файла (14.10.2026).

Реальный базовый шаблон даёт владелец; схема от его текстов не зависит, поэтому данные заводятся отдельно от миграции.
Повторный запуск ничего не меняет: шаблон с таким названием пропускается.

    docker exec finance_backend python -m scripts.seed_annex_templates /tmp/annex_base.json [--dry]

Файл: `{"title": "Основной (клиентский)", "formats": ["Клиент", …], "blocks": [блоки…]}`; блок — `id`, `title`, `sys` или `text`,
флаги `sub`, `req`, `pin`, `money`. `formats` — какие форматы сотрудничества договора обслуживает шаблон (по умолчанию все известные).
Шаблон проходит ту же проверку, что и сохранение на экране; не прошёл — ничего не пишется.
"""
import json
import sys

import app.model_registry  # noqa: F401  (разовый скрипт — отдельный процесс: модели нужны до первой записи)
from app.annex_tpl import service as S
from app.annex_tpl.check import check
from app.annex_tpl.formats import KNOWN_FORMATS
from app.database import SessionLocal

AUTHOR = "перенос действующего шаблона"


def main(path: str, dry: bool = False) -> int:
    data = json.load(open(path, encoding="utf-8"))
    title, blocks = data.get("title"), data.get("blocks")
    formats = data.get("formats", list(KNOWN_FORMATS))
    if not title or not blocks:
        print("В файле должны быть title и blocks")
        return 2
    issues = check(blocks)
    if issues:
        for i in issues:
            print(f"{i['where']}{i['text']}")
        print("Шаблон не прошёл проверку — ничего не записано")
        return 1
    db = SessionLocal()
    try:
        existed = S.base_by_title(db, title) is not None
        v = S.seed_base(db, title, blocks, AUTHOR, formats)
        tpl = db.query(S.AnnexTplTemplate).filter_by(id=v.template_id).first()
        print(f"«{title}»: {'уже есть, v' + str(v.version) if existed else 'заведён, v1'}; форматы: {', '.join(S.formats_of(db, tpl.id)) or '—'}")
        if dry:
            db.rollback()
            print("--dry: откат, ничего не записано")
        else:
            db.commit()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], "--dry" in sys.argv))
