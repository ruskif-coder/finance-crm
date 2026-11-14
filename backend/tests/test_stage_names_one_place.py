# -*- coding: utf-8 -*-
"""Имена стадий и этапов каталога записаны в ОДНОМ месте — `app/sales/stage_slots.py` (владелец 14.11.2026: «логика движения
сделки проектировалась как подсистема — всё должно быть на её базе»). Русские имена сравниваются буквально; до 14.11 их держали
свои константы в 11 модулях («Итоговая сверка» — трижды), и переименование стадии в справочнике тихо развело бы их.

Сломать: объявить в любом модуле `RECON = "Итоговая сверка"` или сравнить `stage.name == "В размещении"` — тест назовёт файл.
Исключения — подписи, совпадающие со словом (канал «ЭДО», назначение «Оплата», кнопка «Бронь»), перечислены ниже с причиной."""
import pathlib
import re

from app.sales import stage_slots as SS

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
# файл → слова, которые там означают НЕ стадию
NOT_A_STAGE = {
    "doc_names.py": {"ЭДО"},
    "models.py": {"ЭДО"},                       # комментарий к каналу договора                    # канал выставления документа
    "master_deal/doc_sign.py": {"ЭДО"},
    "routers/contracts.py": {"ЭДО", "Услуги"},   # канал выставления; колонка выгрузки договоров
    "routers/counterparties.py": {"ЭДО"},
    "sales/annex_signed.py": {"ЭДО"},
    "onec_desk/invoice_xml.py": {"Оплата"},      # назначение платежа
    "routers/traffic_balancer.py": {"Услуги"},  # подпись колонки
    "sales/plan_xlsx.py": {"Услуги"},
    "sales/stages.py": {"Бронь"},               # подпись позиции светофора 2/2/2
    "sales/queue_state.py": {"Бронь"},          # подпись кнопки
    "sales/stage_scope.py": {"Итоговая сверка"},  # заголовок блока карточки
}


def test_stage_names_live_only_in_stage_slots():
    names = set(SS.STAGE_NAMES) | set(SS.PHASE_NAMES)
    pat = re.compile(r"[\"'](" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")[\"']")
    bad = []
    for f in APP.rglob("*.py"):
        rel = f.relative_to(APP).as_posix()
        if rel == "sales/stage_slots.py":
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for m in pat.finditer(line):
                if m.group(1) not in NOT_A_STAGE.get(rel, set()):
                    bad.append(f"{rel}:{i} «{m.group(1)}»")
    assert not bad, "имя стадии вне stage_slots: " + "; ".join(bad)


def test_every_catalog_stage_has_a_name_constant():
    assert len(SS.STAGE_NAMES) == 15 and len(set(SS.STAGE_NAMES)) == 15
    assert set(SS.SLOT_OF_NAME) <= set(SS.STAGE_NAMES)
