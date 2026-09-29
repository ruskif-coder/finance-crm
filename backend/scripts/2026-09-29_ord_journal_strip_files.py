"""Разовая чистка журнала ОРД: base64 файлов креатива → размер и sha256 (аудит 29.09.2026).

До v2.6.44 журнал `ord_submissions.request` хранил баннер целиком (1–3 МБ на строку).
Запросы уже ушли в ОРД, файлы лежат у нас в креативах — в журнале остаётся след.

    python -m scripts.2026-09-29_ord_journal_strip_files          # сухой прогон
    python -m scripts.2026-09-29_ord_journal_strip_files --apply
"""
import json
import sys

from sqlalchemy import text

from app.database import SessionLocal
from app.ord.submit import _strip


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT id, request FROM ord_submissions "
            "WHERE request::text LIKE '%fileContentBase64\": \"%' ORDER BY id")).all()
        before = after = 0
        for rid, req in rows:
            new = _strip(req)
            before += len(json.dumps(req))
            after += len(json.dumps(new))
            if apply:
                db.execute(text("UPDATE ord_submissions SET request = CAST(:r AS jsonb) "
                                "WHERE id = :i"), {"r": json.dumps(new, ensure_ascii=False), "i": rid})
        if apply:
            db.commit()
        print(f"{'применено' if apply else 'сухой прогон'}: строк {len(rows)}, "
              f"{before / 1e6:.1f} МБ → {after / 1e6:.2f} МБ")
    finally:
        db.close()


if __name__ == "__main__":
    main("--apply" in sys.argv)
