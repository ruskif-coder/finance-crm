# -*- coding: utf-8 -*-
"""Сборка приложения к договору: номер, дата, стороны, текст формулировки.

Чистая часть генератора — всё, что можно посчитать и проверить без документа. Сам файл
(docx и PDF) собирается поверх этих данных, и оба формата берут их отсюда: два места,
считающие сумму или номер по-своему, разошлись бы на первой правке.

Схема заведена миграцией `backend/migrations/2026-09-05_annex_generator.sql`.
"""
import calendar
import re
from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.sales import mp_row

from app.models import Contract, Counterparty
from app import own_company
from app.sales.models import AnnexTemplate, SalesAnnex
from app.sales.rubles import rub_phrase, vat_of
from app.sales import rugram

# Номер, вытащенный из старых операций, — только ПОДСКАЗКА. В `operations.ds_num` лежит
# свободный текст в шести форматах, и среди чисел встречается мусор: у одного контрагента
# «590425» — очевидно не номер приложения. Поэтому подсказка ограничена сверху: всё, что
# выше, показываем, но за максимум не выдаём.
HINT_MAX = 999


def next_no(db: Session, contract: Contract) -> int:
    """Следующий номер приложения ВНУТРИ ДОГОВОРА (владелец 05.09.2026).

    Считается от двух величин: стартового номера, который человек проставил на договоре
    (последний, выданный вне системы), и максимума наших собственных. Берётся больший —
    иначе первое же приложение после переноса заняло бы номер, который уже у клиента.
    """
    ours = (db.query(func.max(SalesAnnex.no))
            .filter(SalesAnnex.contract_id == contract.id).scalar()) or 0
    start = contract.annex_start_no or 0
    return max(ours, start) + 1


def no_hint(db: Session, contract: Contract) -> Optional[int]:
    """Подсказка «в операциях по этому контрагенту максимальный номер — 73».

    Справочно, для поля стартового номера. Никогда не подставляется автоматически:
    ровно из-за таких значений, как 590425, — см. `HINT_MAX`.
    """
    if not contract.counterparty_id:
        return None
    from app.models import Operation
    rows = (db.query(Operation.ds_num)
            .filter(Operation.counterparty_id == contract.counterparty_id,
                    Operation.ds_num.isnot(None)).all())
    best = 0
    for (raw,) in rows:
        digits = re.sub(r"\D", "", raw or "")
        if not digits:
            continue
        n = int(digits)
        if n <= HINT_MAX:
            best = max(best, n)
    return best or None


def annex_date(period_from: date) -> date:
    """Дата приложения — ПОСЛЕДНИЙ ДЕНЬ ПРЕДЫДУЩЕГО МЕСЯЦА (владелец 05.09.2026).

    По закону приложение должно существовать на момент запуска, а подписывают его обычно
    позже — отсюда и оговорка в теле документа о распространении на отношения с первого
    дня периода.

    Правило чисто календарное, поэтому производственный календарь не нужен: 31 мая для
    июньского размещения считается арифметикой, а таблицу праздников пришлось бы
    обновлять каждый год.
    """
    y, m = period_from.year, period_from.month
    if m == 1:
        y, m = y - 1, 12
    else:
        m -= 1
    return date(y, m, calendar.monthrange(y, m)[1])


def party(cp: Optional[Counterparty]) -> dict:
    """Сторона договора для шапки: «в лице Генерального директора Иванова Ивана
    Ивановича, действующего на основании Устава».

    Отдаёт и `missing` — чего не хватает. Документ с пустым местом на месте директора
    хуже отказа: его подпишут не глядя. Замерено 05.09.2026: ИНН заполнен у 191 из 211
    контрагентов, адрес у 64, ФИО директора у 78.
    """
    if not cp:
        return {"name": None, "missing": ["контрагент не указан"]}
    miss = []
    if not (cp.inn or "").strip():
        miss.append("ИНН")
    if not (cp.director_name or "").strip():
        miss.append("ФИО подписанта")
    if not (cp.signer_position or "").strip():
        miss.append("должность подписанта")
    if not (cp.signer_basis or "").strip():
        miss.append("основание полномочий")
    return {
        "id": cp.id, "name": cp.name, "inn": cp.inn, "kpp": cp.kpp,
        "address": cp.address, "director": cp.director_name,
        "position": cp.signer_position, "basis": cp.signer_basis,
        # Родительный падеж — ТОЛЬКО для оборота «в лице …» в шапке. В подписях внизу
        # должность стоит в именительном («Генеральный директор:»), и это не разные
        # данные, а одно и то же поле в двух падежах — поэтому обе формы считаются
        # здесь, а не на печатной странице: docx получит те же самые.
        "position_gen": rugram.gen_position(cp.signer_position),
        "director_gen": rugram.gen_fio(cp.director_name),
        "basis_gen": rugram.gen_basis(cp.signer_basis),
        "acting": rugram.acting(cp.director_name),
        "short_fio": short_fio(cp.director_name),
        "missing": miss,
    }


def short_fio(full: Optional[str]) -> Optional[str]:
    """«Макаров Денис Сергеевич» → «Макаров Д.С.» — форма подписи в документе."""
    parts = [p for p in (full or "").split() if p]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return parts[0] + " " + "".join(f"{p[0].upper()}." for p in parts[1:3])


def pick_template(db: Session, payer_id: Optional[int]) -> Optional[AnnexTemplate]:
    """Шаблон формулировки: свой у плательщика, иначе типовой.

    Привязка к ПЛАТЕЛЬЩИКУ, а не к рекламодателю: подписывает и платит он.
    """
    if payer_id:
        own = (db.query(AnnexTemplate)
               .filter(AnnexTemplate.payer_id == payer_id)
               .order_by(AnnexTemplate.is_default.desc(), AnnexTemplate.id).first())
        if own:
            return own
    return (db.query(AnnexTemplate)
            .filter(AnnexTemplate.payer_id.is_(None))
            .order_by(AnnexTemplate.is_default.desc(), AnnexTemplate.id).first())


def render_body(template: Optional[AnnexTemplate], ctx: dict) -> str:
    """Подстановки в тело шаблона. Незакрытый ключ ОСТАЁТСЯ как есть — видимая дыра
    лучше молча пустого места: человек её заметит при проверке."""
    body = (template.body if template else "") or ""
    for k, v in ctx.items():
        body = body.replace("{" + k + "}", "" if v is None else str(v))
    return body


# Подписи инвентаря — те же, что в конструкторе и печатной форме медиаплана. Третий
# словарь для одних и тех же трёх значений разъехался бы с ними при первом добавлении.
INVENTORY_LABEL = {"web": "WEB", "app": "APP", "cross": "Кросс-девайс"}

# Формат размещения по-русски: в документе он на языке договора, а не на языке справочника.
FORMAT_LABEL = {"banners": "Баннеры", "native": "Нативный", "video": "Видео"}

# Место размещения. Сегодня у всех наших услуг оно одно — наша сеть. Константа, а не
# поле: пока значение единственное, колонка в справочнике была бы столбцом из одного
# повторяющегося слова. Появится второе — заведём (владельцу это отмечено 05.09.2026).
PLACEMENT_NETWORK = "SIMB-AD"


def deal_brand(db: Session, deal_ids) -> Optional[str]:
    """Чей бренд рекламируется — из сделок, которые закрывает приложение.

    В документе стоит «материалов бренда: «…»», и до 05.09.2026 туда подставлялась пустая
    строка: `brand` был аргументом, а звали `build` без него. Пустые кавычки в подписанном
    документе — та ошибка, которую замечает клиент, а не мы.

    Рекламодатель и бренд пишутся парой через « / », как в образце, и схлопываются, когда
    совпадают (у половины рекламодателей бренд назван так же). Имя рекламодателя берётся
    `short_name` — наш стандарт именования, а не битриксовое `name`.
    """
    from sqlalchemy import text as sa_text
    ids = [i for i in (deal_ids or []) if i]
    if not ids:
        return None
    rows = db.execute(sa_text("""
        SELECT DISTINCT COALESCE(NULLIF(btrim(a.short_name), ''), a.name) AS adv,
                        b.name AS brand
          FROM sales_deals d
          LEFT JOIN sales_advertisers a ON a.id = d.advertiser_id
          LEFT JOIN sales_brands b ON b.id = d.brand_id
         WHERE d.id = ANY(:d)
    """), {"d": ids}).mappings().all()
    out = []
    for r in rows:
        parts, seen = [], set()
        for v in (r["adv"], r["brand"]):
            v = (v or "").strip()
            if v and v.lower() not in seen:
                seen.add(v.lower())
                parts.append(v)
        line = " / ".join(parts)
        if line and line not in out:
            out.append(line)
    return ", ".join(out) or None


def plan_rows(db: Session, deal_ids) -> list:
    """Строки медиаплана для таблицы в документе — из ПОСЛЕДНЕГО неотклонённого плана
    каждой сделки, тем же условием выбора, что план показов и цели.

    Колонки повторяют таблицу подписанного образца: место размещения, позиция, гео,
    формат, девайс, тип ротации, модель закупки, объём, период, цена за единицу,
    стоимость, НДС, стоимость с НДС.

    В образце таблица вставлена КАРТИНКОЙ из экселя. Собираем настоящей: суммы совпадают
    с базой по построению, а не потому что кто-то аккуратно скопировал, и документ ищется
    текстом.

    Описание позиции и тип ротации берутся из СПРАВОЧНИКА УСЛУГ (`doc_position`,
    `rotation_type`, миграция 2026-09-05_service_doc_fields.sql). Незаполненные отдаются
    пустыми, а не выдумываются: пустая ячейка в документе видна при вычитке, выдуманная
    формулировка — нет.
    """
    from sqlalchemy import text as sa_text
    ids = [i for i in (deal_ids or []) if i]
    if not ids:
        return []
    rows = db.execute(sa_text("""
        SELECT r.position, r.format, r.model, r.inventory, r.volume, r.unit_price,
               r.discount, mp.deal_id, g.name AS geo,
               mp.date_from, mp.date_to, s.doc_position, s.rotation_type
          FROM sales_media_plan_rows r
          JOIN sales_media_plans mp ON mp.id = r.plan_id
          LEFT JOIN sales_geo g ON g.id = mp.geo_id
          LEFT JOIN sales_services s ON lower(btrim(s.name)) = lower(btrim(r.position))
         WHERE mp.deal_id = ANY(:d)
           AND mp.id = (SELECT id FROM sales_media_plans
                         WHERE deal_id = mp.deal_id AND status <> 'rejected'
                         ORDER BY version DESC, id DESC LIMIT 1)
         ORDER BY mp.deal_id, r.sort_order, r.id
    """), {"d": ids}).mappings().all()
    out = []
    for r in rows:
        vol = float(r["volume"] or 0)
        price = float(r["unit_price"] or 0)
        disc = float(r["discount"] or 0)
        # Формула ОДНА на весь проект (app/sales/mp_row.py). Здесь стояла своя копия
        # с безусловным /1000, и строка «Фикс · 1 ед × 80 000» печаталась в подписываемом
        # документе как 80 ₽. Владелец 08.09.2026: чинить.
        net = round(mp_row.row_net(r["model"], vol, price, disc), 2) if (vol and price) else None
        fmt = (r["format"] or "").strip()
        out.append({
            "network": PLACEMENT_NETWORK,
            "position": r["position"],
            # Описание из справочника услуг; пусто — в документе останется одно название.
            "doc_position": (r["doc_position"] or "").strip() or None,
            "rotation": (r["rotation_type"] or "").strip() or None,
            "geo": r["geo"],
            "format": FORMAT_LABEL.get(fmt.lower(), fmt or None),
            "device": INVENTORY_LABEL.get((r["inventory"] or "").lower(), "Кросс-девайс"),
            "model": r["model"],
            "volume": vol or None,
            "date_from": r["date_from"], "date_to": r["date_to"],
            "unit_price": price or None,
            "amount": net,
        })
    return out


def build(db: Session, contract: Contract, *, period_from: date, period_to: date,
          amount: float, brand: Optional[str] = None,
          vat_rate: Optional[float] = None, no: Optional[int] = None,
          deal_ids=None) -> dict:
    """Всё, что нужно документу, одним словарём — и для docx, и для PDF.

    Ничего не пишет в базу: это предпросмотр. Запись происходит при подтверждении, когда
    номер занимается насовсем.
    """
    payer = contract.counterparty
    us = contract.own_company or own_company.sole(db)
    # Ставка берётся из `vat_rate_income` нашего юрлица — это НДС по нашим УСЛУГАМ
    # (22 % на 05.09.2026). Поле `vat_rate` у того же контрагента означает ставку по
    # его расходам и стоит нулём; перепутать их значит выпустить документ без налога.
    rate = vat_rate if vat_rate is not None else (
        getattr(us, "vat_rate_income", None) or getattr(us, "vat_rate", None) or 0)
    n = no or next_no(db, contract)

    # НДС по строке НАЧИСЛЯЕТСЯ, а не извлекается: `r["amount"]` — стоимость размещения
    # БЕЗ налога (объём × цена ÷ 1000 со скидкой), тогда как `vat_of` вынимает налог из
    # суммы С налогом. Спутать их — ошибка на 22/122 против 22/100: 06.09.2026 строка на
    # 500 000,20 давала НДС 90 163,97 вместо 110 000,04, и таблица переставала сходиться
    # с суммой сделки, хотя данные были верны.
    rows = [{**r, "vat": round(r["amount"] * rate / 100.0, 2) if r["amount"] else None,
             "gross": (round(r["amount"] * (100.0 + rate) / 100.0, 2)
                       if r["amount"] else None)}
            for r in plan_rows(db, deal_ids)]
    plan_total = round(sum(r["gross"] or 0 for r in rows), 2) if rows else None
    # НДС документа СКЛАДЫВАЕТСЯ ИЗ СТРОК, когда строки есть, а не извлекается из общей
    # суммы. Извлечение давало расхождение на копейки уже при двух строках: Σ round(net×22
    # /100) ≠ round(Σ round(net×122/100) × 22/122). Замерено 06.09.2026 на трёх строках —
    # 207 777,82 в таблице против 207 777,83 в пункте 1.1, и обе цифры в одном документе.
    # Без строк (предпросмотр по сумме) считаем по-прежнему извлечением.
    vat = (round(sum(r["vat"] or 0 for r in rows), 2) if rows else vat_of(amount, rate))

    tpl = pick_template(db, payer.id if payer else None)
    # Бренд приходит либо явно (примерка на экране), либо выводится из сделок приложения.
    brand = brand or deal_brand(db, deal_ids)
    ctx = {
        "бренд": brand or "",
        "период_с": period_from.strftime("%d.%m.%Y"),
        "период_по": period_to.strftime("%d.%m.%Y"),
        "сумма": f"{amount:,.2f}".replace(",", " "),
        "сумма_прописью": rub_phrase(amount),
        "ндс_ставка": f"{rate:g}",
        "ндс_сумма": f"{vat:,.2f}".replace(",", " "),
        "ндс_сумма_прописью": rub_phrase(vat),
        "номер": str(n),
        "договор_номер": contract.contract_number or "",
        "договор_дата": (contract.contract_date.strftime("%d.%m.%Y")
                         if contract.contract_date else ""),
    }
    us_party, payer_party = party(us), party(payer)
    return {
        "no": n,
        "number": f"Приложение № {n}",
        "date": annex_date(period_from),
        "period_from": period_from, "period_to": period_to,
        "signed_place": (getattr(us, "signed_place", None) or "г. Москва"),
        # Ссылка на договор в ЭДО и признак прикреплённого файла — чтобы с экрана сборки
        # можно было открыть сам договор, а не искать его в реестре. Файл отдаёт РУЧКА
        # ДОГОВОРОВ (`/contracts/{id}/download`): вторая точка выдачи того же файла
        # означала бы вторые правила доступа к нему.
        "contract": {"id": contract.id, "number": contract.contract_number,
                     "date": contract.contract_date,
                     "link": contract.document_link,
                     "has_file": bool(contract.attached_filename)},
        "executor": us_party,          # мы
        "customer": payer_party,       # плательщик
        "brand": brand,
        "amount": amount, "amount_words": rub_phrase(amount),
        # Сумма ПО МЕДИАПЛАНУ — источник истины (владелец 06.09.2026). Приложение
        # выпускается уже на этапе сборки, когда план зафиксирован, поэтому расхождению
        # взяться неоткуда: если оно всё же есть, значит план правили после сборки, и
        # печатать документ нельзя — в тексте одна сумма, в таблице другая, и это видит
        # подписант.
        "plan_total": plan_total,
        "vat_rate": rate, "vat": vat, "vat_words": rub_phrase(vat),
        "template_id": tpl.id if tpl else None,
        # Таблица размещения — из медиаплана сделок, которые закрывает это приложение.
        # НДС по строке считается ТОЙ ЖЕ функцией, что общий: одна формула на документ,
        # иначе сумма колонки не сойдётся с суммой в тексте.
        "rows": rows,
        "body": render_body(tpl, ctx),
        # Чего не хватает для печати — одним списком, чтобы экран не собирал его заново.
        "missing": ([f"исполнитель: {m}" for m in us_party["missing"]]
                    + [f"заказчик: {m}" for m in payer_party["missing"]]
                    + ([] if tpl else ["не задан шаблон формулировки услуги"])
                    + ([] if brand else ["бренд/рекламодатель"])
                    + ([] if plan_total is None or abs(plan_total - round(amount, 2)) < 0.01
                       else [f"сумма приложения {amount:,.2f} не сходится с медиапланом "
                             f"{plan_total:,.2f}".replace(",", " ")])),
    }
