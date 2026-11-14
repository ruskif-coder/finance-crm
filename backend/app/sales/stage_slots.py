"""Место стадии в дашборде аккаунта — «слот» (макет «акки 3», владелец 28.09.2026).

Слот — не новая классификация стадий, а ключ, по которому дашборд решает, что показать в
строке: у «В размещении» и «Итоговой сверки» одна позиция 2/2/2 (launch), у трёх стадий
документооборота — одна (closing), а показывать им надо разное. Различить их можно только
по имени; русские имена стадий в проекте и так сравниваются буквально (группы очереди,
разметка), и держать это сравнение надо в ОДНОМ месте — здесь.

Переименование стадии в справочнике без правки этой таблицы не ломает ничего, кроме
строки дашборда: стадия получит слот None и покажет причину срочности вместо фактов.
"""
from typing import Optional

# ── Имена стадий и этапов каталога — единственное место, где они записаны (владелец 14.11.2026) ──────────────────────
# Модули ссылаются на эти константы, а не пишут строку сами: прибор `tests/test_stage_names_one_place.py`.
# Переименовали стадию в справочнике — правится одна строка здесь.
SANDBOX_PHASE, SERVICES_PHASE, DO_PHASE = "Песочница", "Услуги", "Документооборот (ДО)"
MP_PREP, MP_SENT, NOT_HAPPENED = "МП Подготовка", "МП Отправлено", "Сделка не случилась"
BOOKING, PREP, LIVE, RECON, LOST = "Бронь", "Готовятся к старту", "В размещении", "Итоговая сверка", "Сделка сорвалась"
DS_PREP, DS_AGREE, CLOSING = "Подготовка ДС", "Согласование ДС", "Подготовка закрывающих"
EDO, ORD, PAY, ARCHIVE = "ЭДО", "Отчёты в ОРД", "Оплата", "Архив успешных сделок"

PHASE_NAMES = (SANDBOX_PHASE, SERVICES_PHASE, DO_PHASE)
STAGE_NAMES = (MP_PREP, MP_SENT, NOT_HAPPENED, BOOKING, PREP, LIVE, RECON, LOST,
               DS_PREP, DS_AGREE, CLOSING, EDO, ORD, PAY, ARCHIVE)
DO_STAGES = (DS_PREP, DS_AGREE, CLOSING, EDO, ORD, PAY, ARCHIVE)     # этап «Документооборот (ДО)»

SLOT_OF_NAME = {
    MP_PREP: "mp_prep",
    MP_SENT: "mp_sent",
    BOOKING: "booking",
    PREP: "prep",
    LIVE: "live",
    RECON: "recon",
    DS_PREP: "ds_prep",
    DS_AGREE: "ds_agree",
    CLOSING: "closing",
    EDO: "edo",
    ORD: "ord",
    PAY: "pay",
}

# Участок финменеджера: в списке ниже рабочих строк (владелец 27.09.2026).
TAIL_SLOTS = ("edo", "pay")


def slot_of(stage) -> Optional[str]:
    """Слот стадии; «unmapped» — стадия не отнесена к слою денег (или её нет вовсе)."""
    if stage is None or not getattr(stage, "money_layer", None):
        return "unmapped"
    return SLOT_OF_NAME.get(stage.name)
