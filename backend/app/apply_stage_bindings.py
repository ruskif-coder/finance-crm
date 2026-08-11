"""Разовая миграция: привязки наших стадий к стадиям Битрикса (our_stage → Bitrix).

Переносит на любое окружение (в т.ч. прод) конфиг привязок, заданный в
«Настройки—Стадии». Матч по ИМЕНАМ (этап + стадия, воронка по имени) — НЕ по id,
поэтому безопасно при несовпадении id между локалью и продом; sales_deals.our_stage_id
не затрагивается. Идемпотентно. По умолчанию dry-run.

Предусловие: на целевом окружении уже есть каталог стадий (те же этапы/стадии по
именам) и воронки (sales_pipelines) с этими именами.

Запуск на сервере (после деплоя кода):
  docker exec finance_backend python -m app.apply_stage_bindings           # предпросмотр
  docker exec finance_backend python -m app.apply_stage_bindings --commit   # запись
"""
import sys
from app.database import SessionLocal
from app.sales.models import SalesStage, SalesStagePhase, SalesPipeline

# (этап, стадия, воронка-Битрикса, status_id). Снято с локали 2026-08-12.
BINDINGS = [
    ("Песочница", "МП Подготовка", "Песочница", "NEW"),
    ("Песочница", "МП согласование", "Песочница", "UC_ZLUZT8"),
    ("Песочница", "МП Отправлено", "Песочница", "UC_ZLUZT8"),
    ("Песочница", "Сделка не случилась", "Песочница", "LOSE"),
    ("Услуги", "Бронь", "Pharm", "C8:NEW"),
    ("Услуги", "Готовятся к старту", "Pharm", "C8:PREPARATION"),
    ("Услуги", "В размещении", "Pharm", "C8:PREPAYMENT_INVOICE"),
    ("Услуги", "Предварительная сверка", "Pharm", "C8:EXECUTING"),
    ("Услуги", "Сделка сорвалась", "Pharm", "C8:LOSE"),
    ("Документооборот (ДО)", "Подготовка ДС", "ДО", "C10:NEW"),
    ("Документооборот (ДО)", "Согласование ДС", "ДО", "C10:UC_VZHRMZ"),
    ("Документооборот (ДО)", "Подготовка закрывающих", "ДО", "C10:PREPARATION"),
    ("Документооборот (ДО)", "ЭДО", "ДО", "C10:PREPAYMENT_INVOIC"),
    ("Документооборот (ДО)", "Отчёты в ОРД", "ДО", "C10:EXECUTING"),
    ("Документооборот (ДО)", "Оплата", "ДО", "C10:UC_SGW6QZ"),
    ("Документооборот (ДО)", "Архив успешных сделок", "ДО", "C10:WON"),
]


def main(commit: bool):
    db = SessionLocal()
    try:
        pipe_by_name = {p.name: p.id for p in db.query(SalesPipeline).all()}
        applied, missing_stage, missing_pipe = 0, [], []
        for phase_name, stage_name, pipe_name, status_id in BINDINGS:
            st = (db.query(SalesStage)
                  .join(SalesStagePhase, SalesStagePhase.id == SalesStage.phase_id)
                  .filter(SalesStagePhase.name == phase_name, SalesStage.name == stage_name)
                  .first())
            if not st:
                missing_stage.append(f"{phase_name} / {stage_name}")
                continue
            pid = pipe_by_name.get(pipe_name)
            if pid is None:
                missing_pipe.append(pipe_name)
            st.bitrix_pipeline_id = pid
            st.bitrix_status_id = status_id
            applied += 1
        print(f"Привязок в списке: {len(BINDINGS)}; применимо к стадиям: {applied}")
        if missing_stage:
            print("  НЕ НАЙДЕНЫ стадии (пропущены):", "; ".join(missing_stage))
        if missing_pipe:
            print("  НЕ НАЙДЕНЫ воронки (bitrix_pipeline_id=NULL):", "; ".join(sorted(set(missing_pipe))))
        if commit:
            db.commit()
            print("Записано.")
        else:
            db.rollback()
            print("DRY-RUN (без записи). Повторить с --commit для записи.")
    finally:
        db.close()


if __name__ == "__main__":
    main(commit="--commit" in sys.argv)
