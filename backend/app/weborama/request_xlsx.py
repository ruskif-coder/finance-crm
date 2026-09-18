# -*- coding: utf-8 -*-
"""Пиксели Weborama по креативу: готовые теги и заявка на недостающие — одним файлом.

ДВА ЛИСТА, ПОТОМУ ЧТО ВОПРОСА ДВА. «Дай пиксели» у этой кнопки означает разное в
зависимости от того, получены они уже или нет:

  · лист **Пиксели** — то, что отдают площадке: ИТОГОВЫЙ тег, в котором `[RANDOM]`
    заменён макросом рандомизатора, а в хвост подставлен адрес ЭТОЙ площадки. Сырой
    пиксель, как он пришёл от Weborama, площадке бесполезен;
  · лист **Mediaplan** — заявка менеджеру на те размещения, по которым пикселя ещё нет.

ЗАЧЕМ ЗАЯВКА, КОГДА ЕСТЬ API. Через API вставки заводятся только там, где нашей стороне
есть что заводить. Часть площадок крутит сама, часть случаев решается перепиской, и тогда
менеджеру Weborama уходит ровно этот файл — как уходил до 09.09.2026. Ручной путь стал
запасным, а не исчез, и собирать его в Excel руками по двадцать строк — работа, которую
делает машина.

ФОРМАТ СВЕРЕН ПО ФАЙЛУ ВЛАДЕЛЬЦА, А НЕ ПО ИНСТРУКЦИИ (замер 09.09.2026). Три расхождения,
каждое ломает файл молча:

  1. PDF описывает колонку D формулой из колонки E. Настоящий D короче ровно на
     «аккаунт_формат», и генератор, написанный по тексту инструкции, даёт неверный D и
     сломанную E.
  2. В `Site name` у владельца стоит АККАУНТ (`SIMB-AD`), а не сайт.
  3. Строки 14–18 — легенда допустимых значений, а не данные. Данные начинаются с 19-й,
     и вписанное выше менеджер прочитает как исправление легенды.

Имена собираются ТЕМИ ЖЕ функциями `naming`, которыми их строит заведение через API:
файл и API обязаны называть одно и то же одинаково, иначе ответ менеджера не сойдётся с
тем, что у нас уже заведено.
"""
from io import BytesIO
from typing import Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.weborama import naming, tags as wtags

ACCOUNT = "SIMB-AD"        # он же Site name в шаблоне — так заполнено у владельца
FORMAT = "banner"
FIRST_ROW = 19             # данные начинаются здесь; выше легенда

# Наша поверхность → их Channel (лист `techlist`: Desktop/Mobile/App/ALL/Smart TV).
CHANNEL = {"WEB": "Desktop", "APP": "App"}

HEAD = [
    ("B", "Site name"), ("C", "Format"), ("D", "Name (SHOULD BE UNIQUE)"),
    ("E", "Position's name (WCM)"), ("F", "Channel"),
    ("G", "Buying units (thousands)"), ("I", "Choose ERID"),
    ("L", "Choose Adloox options"),
]


def rows_for_set(db: Session, set_id: int) -> Tuple[dict, list]:
    """Шапка и строки заявки по комплекту креатива.

    Строка — на ПЛОЩАДКУ этой пары, а не на креатив: вставка у Weborama заводится на
    размещение, и второй креатив на той же площадке новой строки не требует.
    """
    head = db.execute(text("""
        SELECT d.id AS deal_id, d.code AS deal_code, b.name AS brand
          FROM launch_prep_creative_set cs
          JOIN sales_deals d ON d.id = cs.deal_id
          LEFT JOIN sales_brands b ON b.id = d.brand_id
         WHERE cs.id = :s
    """), {"s": set_id}).mappings().first()
    if not head:
        raise ValueError("Комплект не найден")
    if not head["brand"]:
        raise ValueError("У сделки не указан бренд — имя кампании собирать не из чего")

    campaign = naming.campaign_label(head["brand"], head["deal_code"])
    rows = db.execute(text("""
        SELECT pb.name, pb.domain, t.surface_kind, pl.plan_show
          FROM launch_prep_pair p
          JOIN launch_prep_target t ON t.id = p.target_id
          JOIN sales_publishers pb ON pb.id = t.publisher_id
          LEFT JOIN ad_campaign c ON c.deal_id = t.deal_id
          LEFT JOIN ad_campaign_placement pl
                 ON pl.campaign_id = c.id AND pl.publisher_id = t.publisher_id
         WHERE p.set_id = :s AND t.archived_at IS NULL
         ORDER BY pb.name
    """), {"s": set_id}).mappings().all()

    out = []
    for r in rows:
        if not (r["domain"] or "").strip():
            # Без домена строка бессмысленна: имя позиции собирается из него, и пустое
            # место менеджер заполнит наугад.
            continue
        channel = CHANNEL.get((r["surface_kind"] or "WEB").upper(), "Desktop")
        name = naming.row_name(channel, campaign, r["domain"])
        out.append({
            "site": ACCOUNT, "format": FORMAT, "name": name,
            "position": naming.position_name(ACCOUNT, FORMAT, name),
            "channel": channel,
            # Единицы закупки — В ТЫСЯЧАХ: так подписана колонка. Пусто лучше нуля:
            # ноль менеджер прочитает как «показов не планируется».
            "units": (round((r["plan_show"] or 0) / 1000) or None),
            "erid": "NO", "adloox": "FULL",
        })
    return {"campaign": campaign, "deal_code": head["deal_code"]}, out


def build(db: Session, set_id: int) -> Tuple[str, bytes]:
    """Готовый файл: (имя, содержимое)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    meta, rows = rows_for_set(db, set_id)
    if not rows:
        raise ValueError("Ни у одной площадки комплекта нет домена — собирать не из чего")

    wb = Workbook()

    # ЛИСТ ПЕРВЫЙ И ГЛАВНЫЙ — готовые теги: за ними и приходят.
    px = wb.active
    px.title = "Пиксели"
    px.append(["Площадка", "Домен", "Куда вшивать", "Итоговый тег показа", "Замечание"])
    for c in px[1]:
        c.font = Font(bold=True, size=10)
        c.fill = PatternFill("solid", fgColor="EFEFEF")
    for r in pixels_for_set(db, set_id):
        px.append([r["publisher"], r["domain"], r["kind"], r["tag"] or "", r["why"] or ""])
    for col, width in (("A", 26), ("B", 26), ("C", 18), ("D", 96), ("E", 52)):
        px.column_dimensions[col].width = width

    ws = wb.create_sheet("Mediaplan")
    ws["B4"], ws["C4"] = "Account ID", ACCOUNT
    ws["B6"], ws["C6"] = "Campaign name", meta["campaign"]
    for cell in ("B4", "B6"):
        ws[cell].font = Font(bold=True)

    grey = PatternFill("solid", fgColor="EFEFEF")
    for col, title in HEAD:
        c = ws[f"{col}{FIRST_ROW - 1}"]
        c.value, c.font, c.fill = title, Font(bold=True, size=10), grey
        c.alignment = Alignment(wrap_text=True, vertical="center")

    for i, r in enumerate(rows):
        n = FIRST_ROW + i
        ws[f"B{n}"] = r["site"]
        ws[f"C{n}"] = r["format"]
        ws[f"D{n}"] = r["name"]
        ws[f"E{n}"] = r["position"]
        ws[f"F{n}"] = r["channel"]
        ws[f"G{n}"] = r["units"]
        ws[f"I{n}"] = r["erid"]
        ws[f"L{n}"] = r["adloox"]

    for col, width in (("B", 14), ("C", 12), ("D", 46), ("E", 56), ("F", 12),
                       ("G", 22), ("I", 12), ("L", 22)):
        ws.column_dimensions[col].width = width

    buf = BytesIO()
    wb.save(buf)
    return f"weborama-{meta['campaign']}.xlsx", buf.getvalue()


def pixels_for_set(db: Session, set_id: int) -> list:
    """Готовые теги по площадкам комплекта.

    МАКРОС ЗАВИСИТ ОТ ТОГО, КТО КРУТИТ. У площадки с нашим кодом показ идёт через наш
    DSP — там рандомизатор пишется `{RND}`. Площадка без нашего кода ставит тег в своём
    сервере, и туда едет `%system.random%`. Перепутать — значит отдать тег, который
    считает показы неверно; узнаётся это по расхождению цифр через месяц.

    Строка без пикселя из файла НЕ ВЫБРАСЫВАЕТСЯ: пустая клетка с причиной честнее
    отсутствующей строки — иначе человек пересчитает площадки и решит, что часть потерял.
    """
    rows = db.execute(text("""
        SELECT pb.name, pb.domain, pb.our_code, pl.weborama_pixel,
               cs.erid,
               (SELECT f.ratio FROM launch_prep_creative_file f
                 WHERE f.set_id = cs.id AND f.is_archive IS TRUE
                 ORDER BY f.id LIMIT 1) AS ratio
          FROM launch_prep_pair p
          JOIN launch_prep_target t ON t.id = p.target_id
          JOIN launch_prep_creative_set cs ON cs.id = p.set_id
          JOIN sales_publishers pb ON pb.id = t.publisher_id
          LEFT JOIN ad_campaign c ON c.deal_id = t.deal_id
          LEFT JOIN ad_campaign_placement pl
                 ON pl.campaign_id = c.id AND pl.publisher_id = t.publisher_id
         WHERE p.set_id = :s AND t.archived_at IS NULL
         ORDER BY pb.name
    """), {"s": set_id}).mappings().all()
    out = []
    for r in rows:
        kind = "dsp" if (r["our_code"] or "").strip() else "adfox"
        tag, why = None, None
        try:
            tag = naming.final_tag(r["weborama_pixel"], r["domain"] or "", kind)
        except ValueError as e:
            why = str(e)

        # ССЫЛКА СОБИРАЕТСЯ ДО КОНЦА (владелец 18.09.2026). Файл существует для того,
        # чтобы тег можно было ПРОВЕРИТЬ — открыть, вставить, сверить. Тег с
        # недоподставленными макросами проверить нельзя: он уедет как есть, и в счётчик
        # попадёт мусор вместо размера.
        if tag:
            w, h = _wh(r["ratio"])
            if w and h:
                tag = wtags.fill_size(tag, w, h)
            if r["erid"]:
                # Маркер в теге, если их формат его просит. Подставляем НАСТОЯЩИЙ: файл
                # уходит человеку для сверки, и заглушка в нём означала бы проверку не
                # того, что поедет в эфир.
                tag = (tag.replace("[ERID_VALUE]", r["erid"])
                          .replace("[ERID_ID]", r["erid"]))
            # Оставшееся называем вслух. Молчать нельзя: тег выглядит рабочим, а DSP
            # чужих макросов не знает и подставлять их не будет (замер 09.09.2026).
            left = wtags.leftovers(tag)
            if left:
                why = ("в теге осталось подставить: " + ", ".join(left)
                       + (" — размер объявлен адаптивным (0x0), его задаёт площадка"
                          if ("~WIDTH~" in left or "~HEIGHT~" in left) else ""))

        out.append({"publisher": r["name"], "domain": r["domain"],
                    "kind": "наш DSP" if kind == "dsp" else "сервер площадки",
                    "tag": tag, "why": why})
    return out


def _wh(ratio):
    """`«240x400»` → (240, 400). Пусто и `0x0` — размера нет: баннер адаптивный, и
    выдумывать за него нельзя."""
    parts = str(ratio or "").lower().replace("х", "x").split("x")
    if len(parts) != 2:
        return None, None
    try:
        w, h = int(parts[0]), int(parts[1])
    except ValueError:
        return None, None
    return (w, h) if w and h else (None, None)


__all__ = ["build", "rows_for_set", "pixels_for_set", "ACCOUNT", "FORMAT",
           "FIRST_ROW", "CHANNEL"]
