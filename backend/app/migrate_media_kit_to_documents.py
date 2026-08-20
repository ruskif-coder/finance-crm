"""
Разовый перенос: медиакит из полей площадки → таблица документов.

    docker exec finance_backend python -m app.migrate_media_kit_to_documents [--apply]

Медиакит перестал быть отдельным полем и стал типом документа (миграция
2026-08-19_publisher_documents.sql). Файлы, загруженные до этого, остались в
media_kit_filename и в интерфейсе не показываются — карточка читает documents.

Заодно переименовывает файл на диске под новую схему префиксов: раньше имя строилось
как «{id}_{файл}», и медиакит площадки №7 сталкивался с документом договора №7 в общем
каталоге. Теперь префикс несёт вид сущности: pub / con / doc.
"""
import os
import sys

from app.database import SessionLocal
from app.routers.publishers import UPLOADS_DIR, _original_name, _stored_prefix
from app.sales.models import SalesPublisher, SalesPublisherDocument

DOC_TYPE = "Медиакит"


def main(apply=False):
    db = SessionLocal()
    moved, missing = [], []

    rows = (db.query(SalesPublisher)
            .filter(SalesPublisher.media_kit_filename.isnot(None)).all())
    for p in rows:
        old_name = p.media_kit_filename
        old_path = os.path.join(UPLOADS_DIR, old_name)
        original = _original_name(p.id, old_name, "pub")

        doc = SalesPublisherDocument(publisher_id=p.id, doc_type=DOC_TYPE,
                                     filename="", uploaded_at=p.media_kit_uploaded_at)
        db.add(doc)
        db.flush()   # нужен id: он идёт префиксом имени на диске

        new_name = f"{_stored_prefix('doc', doc.id)}{original}"
        doc.filename = new_name
        doc.path = os.path.join(UPLOADS_DIR, new_name)

        if os.path.exists(old_path):
            if apply:
                os.rename(old_path, os.path.join(UPLOADS_DIR, new_name))
            moved.append((p.domain, original, new_name))
        else:
            # Записи без файла на диске переносим тоже: строка в документах честнее
            # молчаливой потери, а отсутствие файла видно при скачивании.
            missing.append((p.domain, old_name))

        p.media_kit_filename = None
        p.media_kit_path = None
        p.media_kit_uploaded_at = None

    if apply:
        db.commit()
    else:
        db.rollback()

    print("ЗАПИСАНО" if apply else "ПРОГОН БЕЗ ЗАПИСИ")
    print(f"перенесено медиакитов: {len(moved)}")
    for domain, original, new_name in moved:
        print(f"   {domain}: {original} → {new_name}")
    if missing:
        print(f"файл на диске не найден ({len(missing)}):")
        for domain, name in missing:
            print(f"   {domain}: {name}")
    db.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
