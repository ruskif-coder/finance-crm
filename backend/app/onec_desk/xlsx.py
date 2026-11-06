# -*- coding: utf-8 -*-
"""Выгрузка пакета для бухгалтера — формат прототипа обмена с 1С (15.10.2026, `docs/Прототип_пакет_1С_две_мастер_сделки_v3.xlsx`):
лист «Строки» — строка на позицию УПД, договор номером и датой раздельно, ИНН сразу после покупателя, основание последним
столбцом; лист «Закрывающие» — комплект = одна УПД. Без оформления: это формат обмена, не отчёт."""
from io import BytesIO

from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.onec_desk import queue as Q
from app.xlsx_safe import save_workbook
from app.onec_desk import service as SV

LINES = ("Мастер-сделка", "Номер договора", "Дата договора", "Покупатель", "ИНН покупателя", "КПП покупателя", "Плательщик",
         "Период", "ДС №", "Дата ДС", "№ УПД в мастер-сделке", "Бренд", "Услуга", "Вид строки", "Модель", "Бонус",
         "Дата с", "Дата по", "Объём", "Цена за ед.", "Сумма без НДС", "Ставка НДС, %", "НДС", "Сумма с НДС",
         "Основание для закрытия")
KITS = ("Мастер-сделка", "№ УПД в мастер-сделке", "ДС №", "Бренд", "Услуга", "Сумма без НДС", "НДС", "Сумма с НДС",
        "Предлагаемая дата УПД", "№ счёта 1С", "Дата счёта", "№ УПД 1С", "Дата УПД", "Состояние", "Основание для закрытия")


def build(db: Session, m) -> bytes:
    wb = Workbook()
    ws, wk = wb.active, wb.create_sheet("Закрывающие")
    ws.title = "Строки"
    ws.append(LINES)
    wk.append(KITS)
    from app.master_deal import to_annex as TA
    upds = TA.upds_of(db, m)            # один раз на пакет: основание каждой УПД — по модели её ДС
    for k in SV.kits(db, m):
        c = Q.card(db, k, upds)
        buyer, payer = c["buyer"] or {}, c["payer"] or {}
        head = (m.code, c["contract"]["number"], c["contract"]["date"], buyer.get("name"), buyer.get("inn"), buyer.get("kpp"),
                payer.get("name") or buyer.get("name"), m.period, c["annex"]["number"], c["annex"]["date"], k.upd_no)
        kit = next((u for u in upds if u["upd_no"] == k.upd_no), {})
        line_basis = {x.get("row_id"): x["text"] for x in kit.get("lines") or []}
        for ln in c["lines"]:
            ws.append(head + (ln["brand"], ln["service"], ln["kind"], ln["model"], "да" if ln["bonus"] else "нет",
                              ln["date_from"], ln["date_to"], ln["volume"], ln["unit_price"], ln["net"], ln["vat_rate"],
                              ln["vat"], ln["gross"], line_basis.get(ln.get("row_id")) or c["basis"]))
        o, t = c["onec"], c["totals"]
        wk.append((m.code, k.upd_no, c["annex"]["number"], k.brand, k.service, t["net"], t["vat"], t["gross"],
                   c["upd_date_suggested"], o["invoice_no"], o["invoice_date"], o["upd_no"], o["upd_date"],
                   k.onec_state or "ждёт бухгалтера", c["basis"]))
    buf = BytesIO()
    save_workbook(wb, buf)          # формула в имени контрагента не исполнится у бухгалтера
    return buf.getvalue()
