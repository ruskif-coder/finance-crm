# -*- coding: utf-8 -*-
"""Перепроверить загруженные баннеры: готовы ли они для нашей DSP (владелец 25.09.2026).

Зачем. С 25.09.2026 архив при загрузке готовится для DSP (`sandbox.prepare_for_dsp`):
размер не объявлен — вшивается адаптивный `ad.size`, ссылка клика с заглушкой чужой
системы — меняется на макрос DSP. Загруженное раньше лежит как было. Этот скрипт проходит
по всем архивам креативов и приводит их к тому же виду.

Правится только баннер креатива, у которого в составе есть ВЕБ-площадка с НАШИМ кодом
(`targeting_creative.for_our_web_dsp`): под чужую DSP баннер несёт её макросы, и подмена
сломала бы клик там. Такие только перечисляются.

Заодно пересчитывается размер (`ratio`) у ВСЕХ архивов: с v2.6.6 до 25.09.2026 он не
читался ни у одного баннера — чтение упиралось в проверку границы хранилища, и каждый
баннер показывался «адаптивным».

Исправленный архив записывается поверх, песочница разворачивается заново (новый адрес
предпросмотра), старая удаляется. Чего подготовкой не исправить — баннер без ссылки или
со ссылкой на настоящий адрес — печатается отдельно: это решает человек.

Без `--apply` только показывает. Повторный прогон безопасен: готовый архив не меняется.

    docker exec finance_backend python -m scripts.2026-09-25_prepare_creatives_for_dsp
    docker exec finance_backend python -m scripts.2026-09-25_prepare_creatives_for_dsp --apply
"""
import os
import sys
import zipfile

# Реестр моделей целиком: у комплекта внешние ключи на сделки и пользователей, и без их
# моделей SQLAlchemy падает на commit — уже после печати, то есть вывод выглядел бы как
# успех (так случилось со скриптом 21.09.2026).
import app.models  # noqa: F401
import app.notify.models  # noqa: F401
import app.sales.models  # noqa: F401
from app.database import SessionLocal
from app.dsp.targeting_creative import for_our_web_dsp
from app.files_safe import inside_uploads
from app.launch_prep import sandbox
from app.launch_prep.models import LaunchPrepCreativeFile, LaunchPrepCreativeSet
from app.sales.models import SalesDeal

UPLOADS_ROOT = "/app/uploads"


def _entry_html(data: bytes) -> str:
    import io
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            entry = sandbox._pick_entry([i.filename for i in z.infolist() if not i.is_dir()])
            return z.read(entry).decode("utf-8", "ignore") if entry else ""
    except (zipfile.BadZipFile, KeyError):
        return ""


def main(apply: bool) -> int:
    db = SessionLocal()
    rows = (db.query(LaunchPrepCreativeFile, LaunchPrepCreativeSet, SalesDeal)
            .join(LaunchPrepCreativeSet, LaunchPrepCreativeSet.id == LaunchPrepCreativeFile.set_id)
            .join(SalesDeal, SalesDeal.id == LaunchPrepCreativeSet.deal_id)
            .filter(LaunchPrepCreativeFile.is_archive.is_(True))
            .order_by(LaunchPrepCreativeFile.id).all())
    fixed = ready = foreign = missing = 0
    by_hand = []
    ratios = 0
    for f, s, d in rows:
        label = f"{d.code or d.id} · креатив №{s.no} · {f.original_name}"
        path = inside_uploads(f.path)
        if not path or not os.path.exists(path):
            missing += 1
            print(f"  нет файла        {label}")
            continue
        with open(path, "rb") as fh:
            data = fh.read()

        if not for_our_web_dsp(db, s.id):
            foreign += 1
            print(f"  чужая DSP        {label} — не трогаем")
        else:
            out, changes = sandbox.prepare_for_dsp(data)
            problem = sandbox.click_problem(_entry_html(out))
            if problem:
                by_hand.append(f"{label}: {problem}")
            if not changes:
                ready += 1
                print(f"  готов            {label}")
            else:
                fixed += 1
                print(f"  {'поправлен' if apply else 'поправим':<10} {'+'.join(changes):<13} {label}")
                if apply:
                    with open(path, "wb") as fh:
                        fh.write(out)
                    old = f.sandbox_token
                    token, entry = sandbox.unpack(path, UPLOADS_ROOT)
                    f.sandbox_token, f.entry_path, f.size_bytes = token, entry, len(out)
                    db.commit()
                    sandbox.remove(UPLOADS_ROOT, old)

        # Размер — у всех архивов, и у чужих: чтение его было сломано для всех.
        if f.sandbox_token and not f.ratio:
            r = sandbox.read_size(UPLOADS_ROOT, f.sandbox_token, f.entry_path)
            if r:
                ratios += 1
                print(f"  размер {r:<10}{label}")
                if apply:
                    f.ratio = r
                    db.commit()

    print(f"\nархивов {len(rows)}: {'поправлено' if apply else 'поправим'} {fixed}, "
          f"готовы {ready}, под чужую DSP {foreign}, без файла {missing}; "
          f"размер {'записан' if apply else 'запишем'} у {ratios}")
    if by_hand:
        print("\nСсылку клика подготовкой не исправить — нужен человек:")
        for line in by_hand:
            print("  " + line)
    if not apply:
        print("\nСухой прогон. Записать: --apply")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
